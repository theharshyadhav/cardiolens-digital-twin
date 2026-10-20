# CardioLens 3D — developer notes

## Architecture
`cardiolens/` trains and exports the models (nested CV → logistic regressions → `web/web_model.json`, `models/*.joblib`, `web/evidence.json`).
`build.py` inlines engine, model, libraries, anatomy, fonts and page modules into one HTML file (`web/index.html`, and `web/index.offline.html` with three.js inlined).
`backend/server.py` is optional: same maths as `web/engine.js`, plus the page at `/`. Run `python build.py --check` in CI to catch a stale build.

## Invariants (do not break)
- No tool result may carry pixels, mesh vertices, contour radii or any array; `guard()` in `web/js/room.js` stays. `export_findings` stays human-approved and cancels when the study changes.
- Keep the honesty labels: generic atlas, "not an anatomical registration", "automatic estimate, not validated", "sensitivity range, not a confidence interval", visible clinical disclaimer.
- P(vessel) ≤ P(CAD); features are never drawn as anatomical coordinates; the teal→amber→red ramp is only for probability.
- The page stays one self-contained HTML file (≤ 16 MB), makes no third-party request (the offline build), and is usable without a GPU.
- Outcome columns (Cath, LAD, LCX, RCA) are never model inputs (leakage guard, tested).

## Privacy design
Patient DICOM tags are never read (whitelist parser). Scan labels are neutral ("CT volume (NIfTI)", "DICOM series, N images"); no file, folder or UID is shown. Tests sweep every tool result, the approval dialog, the export and the page text for planted identifying values.

## Reading room
- **Heart box:** mm box in the frame of `centroid_mm`; components are labelled on the whole scan first, so volume / peak / score do not change with the box; `ScanLib.restrict` only filters. Tool `set_heart_region` takes `{region:'auto'|'whole'}` or `{box_mm}`. `ScanLib.suggestHeartBox` is a guess (lungs → ~150×130×140 mm box, falls back to the central field of view), validated only on synthetic chests.
- **MRI:** geometry from ImagePositionPatient / ImageOrientationPatient (SliceLocation is unreliable); heart rate = 60000 / mean R-R; volume = modified Simpson; EF = (EDV−ESV)/EDV. Slice edits re-sum stored contours (`CineLib.volumes`), never re-trace. The LV in 3D is 1:1 scale, translated to the atlas LV centroid, labelled "not an anatomical registration".

## Known limits and defects
- No real DICOM CT / MR-from-disk file has been opened in a browser; DICOM UI tests use synthetic files (`CARDIOLENS_DICOM_DIR` adds the real-file part).
- The MRI image stage is a fixed square; non-square frames would be stretched.
- Compressed and multi-frame DICOM are refused with a message.
- Software-WebGL screenshots occasionally show an empty 3D view on the first frame; look at every screenshot before using it.
- Tested in headless Chromium only (not Safari, Firefox, a physical GPU).
- The Docker image was written and reviewed but could not be built in the authoring sandbox (no daemon); CI builds it.
