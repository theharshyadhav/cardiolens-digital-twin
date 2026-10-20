"""CardioLens API + page server.

    uvicorn backend.server:app --reload          ->  http://127.0.0.1:8000   (interactive API docs at /docs)

Single source of truth = web/web_model.json (exported by cardiolens/final.py). The maths below is the same as web/engine.js; at start-up it is
cross-checked against the original sklearn pipelines (models/*.joblib) whenever scikit-learn, pandas and joblib are installed (the slim Docker
image does not ship them, so it skips the check; the test suite always runs it).
Patient data is processed in memory only - nothing is stored or logged.

Configuration (environment variables, all optional):
    CARDIOLENS_CORS_ORIGINS   comma-separated allowed origins for the API (default "*": the API is stateless, read-only and carries no credentials)
    CARDIOLENS_MAX_BODY       maximum request body in bytes (default 65536)
"""
from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger("cardiolens")
ROOT = Path(__file__).resolve().parents[1]
MODEL = json.loads((ROOT / "web" / "web_model.json").read_text())
FEATS = {f["key"]: f for f in MODEL["features"]}
TARGETS = MODEL["meta"]["targets"]
DISCLAIMER = MODEL["meta"]["disclaimer"]
MAX_BODY = int(os.environ.get("CARDIOLENS_MAX_BODY", "65536"))
CORS_ORIGINS = [o.strip() for o in os.environ.get("CARDIOLENS_CORS_ORIGINS", "*").split(",") if o.strip()]

# The page to serve at "/": the self-contained build (no third-party request at all) when present, else the cdnjs build.
PAGE = next((p for p in (ROOT / "web" / "index.offline.html", ROOT / "web" / "index.html") if p.exists()), None)
PAGE_SELF_CONTAINED = PAGE is not None and PAGE.name == "index.offline.html"
# Everything the page does is inline, so 'unsafe-inline' is needed; connect-src 'self' is what keeps patient numbers on this origin.
CSP = ("default-src 'none'; script-src 'unsafe-inline'" + ("" if PAGE_SELF_CONTAINED else " https://cdnjs.cloudflare.com")
       + "; style-src 'unsafe-inline'; img-src 'self' data: blob:; font-src data:; connect-src 'self'; "
         "base-uri 'none'; form-action 'none'; frame-ancestors 'self'")


def _sig(z: float) -> float:
    """numerically stable logistic function (no OverflowError for large |z|)"""
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def _tf(f: dict, v: float) -> float:
    return math.log1p(v) if f["log"] else v


def predict(x: dict[str, float]) -> dict:
    out = {}
    for t in TARGETS:
        T = MODEL["targets"][t]
        z, phi = T["base"], {}
        for k, f in FEATS.items():
            phi[k] = T["w"][k] * (_tf(f, x[k]) - f["mu"]) / f["sd"]
            z += phi[k]
        out[t] = dict(z=z, p=_sig(z), base=T["base"], phi=phi)
    cad = out["CAD"]["p"]
    for t in TARGETS:  # a stenotic vessel implies CAD -> cap vessel probability by P(CAD)
        out[t]["p_model"] = out[t]["p"]
        out[t]["capped"] = t != "CAD" and out[t]["p"] > cad
        out[t]["p"] = min(out[t]["p"], cad) if t != "CAD" else cad
    return out


def _self_check() -> str:
    """Compare this module with the sklearn pipelines. A numeric mismatch is fatal; an unusable environment (missing or
    incompatible scikit-learn / joblib / pandas) is reported and skipped, so a deployment never fails to start because of a library version."""
    p = ROOT / "models" / "cardiolens_models.joblib"
    try:
        import joblib
        import pandas as pd
        if not p.exists():
            return "skipped: models/cardiolens_models.joblib not found"
        pack = joblib.load(p)
        x = {k: f["median"] for k, f in FEATS.items()}
        row = pd.DataFrame([{k: (math.log1p(x[k]) if FEATS[k]["log"] else x[k]) for k in FEATS}])
        ref = {t: _sig(pack[t]["a"] * pack[t]["pipeline"].decision_function(row)[0] + pack[t]["b"]) for t in TARGETS}
    except ImportError:
        return "skipped: scikit-learn / pandas / joblib not installed"
    except Exception as e:  # noqa: BLE001 - unpickling across library versions can fail in many ways
        log.warning("self-check skipped: %s: %s", type(e).__name__, e)
        return f"skipped: {type(e).__name__}"
    ours = predict(x)
    for t in TARGETS:
        assert abs(ref[t] - ours[t]["p_model"]) < 1e-9, f"backend/sklearn mismatch for {t}"
    return "ok"


SELF_CHECK = _self_check()

app = FastAPI(title="CardioLens API", version=MODEL["meta"]["version"],
              description="Research prototype - " + DISCLAIMER)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["content-type"])


@app.middleware("http")
async def limits_and_headers(request: Request, call_next):
    if int(request.headers.get("content-length") or 0) > MAX_BODY:
        return JSONResponse({"detail": f"request body larger than {MAX_BODY} bytes"}, status_code=413)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")  # clinical numbers must never be cached
    return resp


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    """422 without echoing the offending input back (FastAPI's default does, and crashes when the input is NaN / Infinity)."""
    return JSONResponse({"detail": [{"loc": [str(p) for p in e["loc"]], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]}, status_code=422)


Num = Annotated[float, Field(allow_inf_nan=False, ge=-1e6, le=1e6)]


class PredictIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    features: dict[str, Num] = Field(..., description="feature key -> raw value; missing keys are imputed (median / 0) and reported")


@app.get("/api/health")
def health():
    return {"status": "ok", "model_version": MODEL["meta"]["version"], "self_check": SELF_CHECK, "disclaimer": DISCLAIMER}


@app.get("/api/schema")
def schema():
    return {"meta": MODEL["meta"], "features": MODEL["features"], "presets": MODEL["presets"],
            "metrics": {t: {"model": MODEL["targets"][t]["model"], **MODEL["targets"][t]["metrics"],
                            "auc_ci95": MODEL["targets"][t]["auc_ci95"]} for t in TARGETS}}


@app.post("/api/predict")
def predict_endpoint(body: PredictIn):
    unknown = set(body.features) - set(FEATS)
    if unknown:
        raise HTTPException(422, f"unknown features: {sorted(unknown)}")
    bad = sorted(k for k, v in body.features.items() if FEATS[k]["log"] and v <= -1)
    if bad:
        raise HTTPException(422, f"values must be greater than -1 for: {bad}")
    x, imputed = {}, []
    for k, f in FEATS.items():
        if k in body.features:
            x[k] = float(body.features[k])
        else:
            x[k] = f["median"] if f["kind"] == "num" else 0.0
            imputed.append(k)
    res = predict(x)
    band = MODEL["meta"]["risk_bands"]
    label = lambda p: "High" if p >= band["high"] else "Intermediate" if p >= band["low"] else "Low"
    return {
        "disclaimer": DISCLAIMER, "imputed": imputed,
        "out_of_training_range": [k for k, f in FEATS.items() if f["kind"] == "num" and not f["train_min"] <= x[k] <= f["train_max"]],
        "predictions": {t: {"probability": round(res[t]["p"], 4), "probability_uncapped": round(res[t]["p_model"], 4),
                            "capped_by_cad": res[t]["capped"], "band": label(res[t]["p"]), "baseline": round(_sig(res[t]["base"]), 4),
                            "shap_log_odds": {k: round(v, 4) for k, v in sorted(res[t]["phi"].items(), key=lambda kv: -abs(kv[1]))}}
                        for t in TARGETS},
    }


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def index():
    if PAGE is None:
        raise HTTPException(503, "web/index.offline.html is missing - run `python build.py`")
    return FileResponse(PAGE, media_type="text/html; charset=utf-8",
                        headers={"Content-Security-Policy": CSP, "Cache-Control": "no-cache"})  # revalidate (ETag) so a new build is picked up at once
