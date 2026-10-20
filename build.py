"""Build the single-file app: inline fonts, engine, model (+evidence), scan library, cardiac-MRI libraries + sample, WebMCP core, 3D anatomy and the page modules.

    python build.py                  web/index.html          three.js from cdnjs (small; what the browser tests load)
                                     web/index.offline.html  three.js inlined: ONE self-contained file, no third-party request at all
                                                             (this is the file to deploy; the Dockerfile and the Pages workflow publish it)
                                     web/web_model.slim.json engine-only copy of the model used by the parity tests
    python build.py --check          build in memory and compare with the files on disk; exit 1 if any is stale (used by CI)
    python build.py --artifact       also write web/artifact.html (same page without the document wrapper, for hosts that add their own skeleton)
    python build.py --bundle-webmcp  rebuild web/webmcp.iife.js from vendor/webmcp-core with esbuild first (needs a local esbuild or network)

Gates (any failure stops the build): the slim model reproduces the sklearn pipelines (parity cases), no placeholder is left in the page,
every inline script parses, and the bundled fonts are present.
"""
import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

R = Path(__file__).resolve().parent
W = R / "web"
J = W / "js"
CORE = R / "vendor" / "webmcp-core"  # MIT, see vendor/webmcp-core/LICENSE
THREE = R / "node_modules" / "three" / "build" / "three.min.js"
CDN = '<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>'

# Latin subsets of two SIL-OFL fonts (web/fonts/LICENSE.txt), inlined so the page makes no request to a font host.
FONTS = [("Public Sans", "100 900", "PublicSans-latin-var.woff2"), ("IBM Plex Mono", "400", "IBMPlexMono-latin-400.woff2"),
         ("IBM Plex Mono", "500", "IBMPlexMono-latin-500.woff2"), ("IBM Plex Mono", "600", "IBMPlexMono-latin-600.woff2")]


def rd(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def bundle_webmcp() -> None:
    """WebMCP core -> one IIFE. Normally the committed web/webmcp.iife.js is used as is."""
    esb = shutil.which("esbuild") or "npx"
    cmd = ([esb] if esb != "npx" else ["npx", "--yes", "esbuild"]) + [str(CORE / "src/index.ts"), "--bundle", "--format=iife",
           "--global-name=WebMCP", "--minify", f"--outfile={W / 'webmcp.iife.js'}"]
    subprocess.run(cmd, check=True, capture_output=True)


def slim_model() -> dict:
    """Engine fields + metrics + evidence for the Model card; gate: it must reproduce the sklearn pipelines."""
    m = json.loads(rd(W / "web_model.json"))
    r6 = lambda v: round(v, 6) if isinstance(v, float) else v
    keep = "key label group kind unit log step mu sd ui_min ui_max default train_min train_max".split()
    slim = dict(
        meta={k: m["meta"][k] for k in ("name", "version", "dataset", "protocol", "disclaimer", "targets", "risk_bands")},
        features=[{k: r6(f[k]) for k in keep} for f in m["features"]],
        targets={t: dict(model=v["model"], base=r6(v["base"]), w={k: r6(x) for k, x in v["w"].items()},
                         metrics={k: [round(a, 4) for a in v["metrics"][k]] for k in ("roc_auc", "accuracy", "recall", "f1", "precision")},
                         auc_ci95=[round(a, 4) for a in v["auc_ci95"]]) for t, v in m["targets"].items()},
        presets=[dict(name=p["name"], description=p["description"], n=p["n"], profile={k: r6(x) for k, x in p["profile"].items()}) for p in m["presets"]])
    return slim


def parity_gate(slim_path: Path) -> None:
    chk = f"""const E=require('{W}/engine.js').CardioEngine,m=require('{slim_path}'),c=require('{W}/parity_cases.json');let d=0;
for(const k of c){{const r=E.predictAll(m,k.x);for(const t of m.meta.targets)d=Math.max(d,Math.abs(r[t].p-k.expected[t]))}}
console.log('slim-model max|dp|='+d.toExponential(1));if(d>1e-4)process.exit(1)"""
    subprocess.run(["node", "-e", chk], check=True)


def fonts_css() -> str:
    out = []
    for fam, weight, fn in FONTS:
        p = W / "fonts" / fn
        if not p.exists():
            sys.exit(f"build: missing font file {p}")
        b64 = base64.b64encode(p.read_bytes()).decode()
        out.append(f'@font-face{{font-family:"{fam}";font-style:normal;font-weight:{weight};font-display:swap;'
                   f'src:url(data:font/woff2;base64,{b64}) format("woff2")}}')
    return "\n".join(out)


def build(want_artifact: bool) -> dict:
    """Return {path: text} for every generated file (nothing is written here, except a temp file for the parity gate)."""
    slim = slim_model()
    ev = W / "evidence.json"
    if ev.exists():
        slim["evidence"] = json.loads(rd(ev))
    slim_json = json.dumps(slim, separators=(",", ":"))
    out = {W / "web_model.slim.json": json.dumps({k: v for k, v in slim.items() if k != "evidence"}, separators=(",", ":"))}

    with tempfile.TemporaryDirectory() as td:  # gate against the in-memory model, not whatever is on disk
        tmp = Path(td) / "slim.json"
        tmp.write_text(out[W / "web_model.slim.json"])
        parity_gate(tmp)

    scene = rd(J / "scene.js").replace("/*ANATOMY*/", rd(W / "anatomy.b64").strip())
    parts = {"/*FONTS*/": fonts_css(), "/*ENGINE*/": rd(W / "engine.js"), "/*MODEL*/": slim_json, "/*SCAN*/": rd(W / "scan.js"),
             "/*DICOM*/": rd(W / "dicom.js"), "/*CINE*/": rd(W / "cine.js"), "/*CINESAMPLE*/": rd(W / "cine_sample.json").strip(),
             "/*WEBMCP*/": rd(W / "webmcp.iife.js"), "/*CORE*/": rd(J / "core.js"), "/*CHARTS*/": rd(J / "charts.js"),
             "/*SCENE*/": scene, "/*ROOM*/": rd(J / "room.js"), "/*CINEUI*/": rd(J / "cineui.js"), "/*BOOT*/": rd(J / "boot.js")}
    html = rd(W / "app.template.html")
    for k, v in parts.items():
        assert html.count(k) == 1, f"placeholder {k} must occur exactly once in app.template.html"
        html = html.replace(k, v)
    left = [k for k in parts if k in html]
    assert not left, f"placeholder left in the page: {left}"
    assert "fonts.googleapis.com" not in html and "fonts.gstatic.com" not in html, "the page must not load fonts from a third party"
    out[W / "index.html"] = html

    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    with tempfile.TemporaryDirectory() as td:  # every inline script must parse
        for i, s in enumerate(scripts):
            f = Path(td) / f"s{i}.js"
            f.write_text(s)
            r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
            if r.returncode:
                print(r.stderr)
                raise SystemExit(f"inline script {i} does not parse")

    if THREE.exists():
        src = rd(THREE)
        assert "</script" not in src.lower() and html.count(CDN) == 1
        out[W / "index.offline.html"] = html.replace(CDN, "<script>" + src + "</script>")
    else:
        print("note: node_modules/three is missing - run `npm install` to also build web/index.offline.html (the file to deploy)")

    if want_artifact:
        head = re.search(r"<head>(.*?)</head>", html, re.S).group(1)
        head = re.sub(r'<meta charset="utf-8">\s*|<meta name="viewport"[^>]*>\s*', "", head)
        body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
        out[W / "artifact.html"] = head.strip() + "\n" + body.strip() + "\n"

    print(f"{len(scripts)} inline scripts parse | model {len(slim_json) // 1024} KB | index.html {len(html) // 1024} KB"
          + (f" | index.offline.html {len(out[W / 'index.offline.html']) // 1024} KB" if W / "index.offline.html" in out else ""))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="do not write; fail if the committed outputs are stale")
    ap.add_argument("--artifact", action="store_true", help="also write web/artifact.html")
    ap.add_argument("--bundle-webmcp", action="store_true", help="rebuild web/webmcp.iife.js with esbuild first")
    a = ap.parse_args()
    if a.bundle_webmcp:
        bundle_webmcp()
    assert (W / "webmcp.iife.js").exists(), "web/webmcp.iife.js is missing; run with --bundle-webmcp"
    out = build(a.artifact)
    if a.check:
        stale = [p.relative_to(R).as_posix() for p, t in out.items() if not p.exists() or rd(p) != t]
        if stale:
            print("STALE (run `python build.py`):", ", ".join(stale))
            return 1
        print("build outputs are up to date")
        return 0
    for p, t in out.items():
        p.write_text(t, encoding="utf-8")
        print("wrote", p.relative_to(R).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
