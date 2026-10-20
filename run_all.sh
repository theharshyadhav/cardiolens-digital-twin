#!/usr/bin/env bash
# Reproduce every number, figure and exported artefact from the raw spreadsheet, rebuild the app, and run every test.
# ~10 min on 1 CPU for the model part; the browser tests add ~3 min (software WebGL is fine).
set -euo pipefail
cd "$(dirname "$0")"

# --- 1. model: nested repeated CV -> final models -> report ------------------------------------------------------
python3 cardiolens/benchmark.py        # 7 model families x 4 targets, 5x5 nested CV    -> results/cv_folds.csv, oof_probs.npz
python3 cardiolens/final.py            # select, calibrate, exact SHAP, figures, web/web_model.json, models/*.joblib
python3 cardiolens/report.py           # results/RESULTS.md
python3 -m cardiolens.evidence         # web/evidence.json (ROC, reliability, confusion, importance for the in-app Model card)

# --- 2. 3D anatomy (optional: web/anatomy.b64 is committed) ------------------------------------------------------
# git clone https://github.com/simonreisinger/Interactive-3D-Human-Heart-Visualization data/anatomy_src
# python tools/prep_anatomy.py data/anatomy_src/data/Postnatal_anatomical_structure

# --- 3. app: one standalone HTML file ----------------------------------------------------------------------------
npm ci --no-audit --no-fund      # jsdom + three@0.128.0 (tests only)
python3 build.py                       # web/index.html (standalone) and web/artifact.html

# --- 4. tests ----------------------------------------------------------------------------------------------------
node tests/test_parity.js             # JS engine == sklearn pipelines (1e-9) and SHAP additivity
python3 tests/test_api.py              # backend contract + leakage guard
node tests/test_scan.js               # NIfTI parser + calcium finder vs phantom ground truth
node tests/test_room.js               # WebMCP tools, approval gate, epoch cancel (jsdom)
node tests/test_dicom.js              # DICOM reader + classifier (set CARDIOLENS_DICOM_DIR / CARDIOLENS_DICOM_REF for the real-file part)
node tests/test_cine.js               # cine LV tracer + volumes == Python reference, mesh watertight
python3 tests/test_browser.py          # real Chromium: 3D, hover, fly-to, scan flow, agent gate, layout, no-WebGL (needs: playwright install chromium)
python3 tests/run_all.py               # the same suites in one go: one line per suite, results/test_summary.json (exit 1 on any failure)
