"""Backend contract tests + leakage guard (run from the project root)."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from backend.server import app, FEATS, PAGE_SELF_CONTAINED
from cardiolens.data import KEYS, LEAKAGE_COLS

c = TestClient(app)
N = 0


def chk(cond, msg=""):
    """an assertion that is also counted (so run_all.py can report passed / total); a failure still raises."""
    global N
    N += 1
    if not cond:
        raise AssertionError(msg or "API check %d failed" % N)


chk(c.get("/api/health").json()["status"] == "ok")
sch = c.get("/api/schema").json()
chk([f["key"] for f in sch["features"]] == KEYS)
leak = {x.lower() for x in LEAKAGE_COLS}
chk(not leak & {k.lower() for k in KEYS} and not leak & {f["label"].lower() for f in sch["features"]}, "target leaked into inputs")
r = c.post("/api/predict", json={"features": {"age": 70, "typ_cp": 1, "dm": 1, "ef": 35}}).json()
chk(set(r["predictions"]) == {"CAD", "LAD", "LCX", "RCA"} and "disclaimer" in r and len(r["imputed"]) == len(KEYS) - 4)
for t, v in r["predictions"].items():
    chk(0 <= v["probability"] <= 1)
    chk(abs(sum(v["shap_log_odds"].values())) < 20)
    if t != "CAD": chk(v["probability"] <= r["predictions"]["CAD"]["probability"] + 1e-9)
chk(c.post("/api/predict", json={"features": {"LAD": 1}}).status_code == 422, "target columns must be rejected as inputs")
chk(c.post("/api/predict", json={"features": {"age": 200}}).json()["out_of_training_range"] == ["age"])
low = c.post("/api/predict", json={"features": {"age": 35, "ef": 60}}).json()["predictions"]["CAD"]["probability"]
hi = c.post("/api/predict", json={"features": {"age": 70, "ef": 30, "typ_cp": 1, "tinv": 1, "rwma": 3, "dm": 1}}).json()["predictions"]["CAD"]["probability"]
chk(hi > low + 0.3, (low, hi))

# --- launch hardening -------------------------------------------------------------------------------------------------------------------
h = c.get("/api/health").json()
chk(h["self_check"] == "ok", "start-up cross-check against the sklearn pipelines did not run: %s" % h["self_check"])
LOGKEY = next(k for k, f in FEATS.items() if f["log"])
chk(c.post("/api/predict", content='{"features": {"age": NaN}}', headers={"content-type": "application/json"}).status_code == 422, "NaN must be rejected")
chk(c.post("/api/predict", content='{"features": {"age": Infinity}}', headers={"content-type": "application/json"}).status_code == 422, "Infinity must be rejected")
chk(c.post("/api/predict", json={"features": {"age": 1e300}}).status_code == 422, "absurd values must be rejected, not overflow")
chk(c.post("/api/predict", json={"features": {LOGKEY: -5}}).status_code == 422, "log-transformed feature below -1 must be rejected")
chk(c.post("/api/predict", json={"features": {"age": 1e6, "ef": -1e6}}).status_code == 200, "extreme but finite inputs must not crash the sigmoid")
chk(c.post("/api/predict", json={"features": {"age": "abc"}}).status_code == 422)
chk(c.post("/api/predict", json={"features": {"age": 60}, "extra": 1}).status_code == 422, "unknown top-level fields rejected")
chk(c.post("/api/predict", content="x" * 70000, headers={"content-type": "application/json"}).status_code == 413, "oversized body rejected")
chk(c.get("/api/health").headers["cache-control"] == "no-store" and c.get("/api/health").headers["x-content-type-options"] == "nosniff", "API headers")
r = c.get("/")
chk(r.status_code == 200 and "CardioLens 3D" in r.text and "text/html" in r.headers["content-type"], "the page is served at /")
chk(r.headers.get("content-encoding") == "gzip", "the page is gzip-compressed")
csp = r.headers.get("content-security-policy", "")
chk("connect-src 'self'" in csp and "default-src 'none'" in csp and "fonts.googleapis.com" not in csp, "page CSP: patient numbers can only go to this origin")
chk(PAGE_SELF_CONTAINED and "cdnjs" not in csp and "cdnjs.cloudflare.com" not in r.text, "the served page is the self-contained build and needs no CDN")
chk(c.head("/").status_code == 200, "HEAD / works (platform health probes)")
chk(c.get("/web_model.json").status_code == 404, "raw model / data files are not served as static files")
chk(c.options("/api/predict", headers={"origin": "https://example.org", "access-control-request-method": "POST"}).status_code == 200, "CORS pre-flight")
print("API OK  (%d checks; low-risk CAD p=%.2f, high-risk p=%.2f)" % (N, low, hi))
