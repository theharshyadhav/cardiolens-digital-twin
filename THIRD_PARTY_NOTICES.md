# Third-party components, data and licences

| Component | Where | Licence | Attribution / obligation |
|---|---|---|---|
| **Extension of Z-Alizadeh Sani dataset** (UCI #411, DOI 10.24432/C5461K), Alizadehsani, Roshanzamir & Sani | `data/ext/` (training data) | CC BY 4.0 | Cite the data set (see UCI page). |
| **BodyParts3D** © The Database Center for Life Science, via simonreisinger/Interactive-3D-Human-Heart-Visualization | `web/anatomy.b64` (derived mesh, embedded in the pages) | CC BY-SA 2.1 Japan | Attribution: "BodyParts3D, Copyright © The Database Center for Life Science licensed by CC Attribution-Share Alike 2.1 Japan". The derived mesh must stay under the same licence (ShareAlike). The credit is shown on the page footer. |
| **Sunnybrook Cardiac Data**, one cine MRI subject | `web/cine_sample.json` (decoded sample) | CC0 as stated by its publisher | None required; credited on the page. |
| **WebMCP core** (`@thegreataxios/webmcp-core`) | `vendor/webmcp-core/`, bundled in `web/webmcp.iife.js` | MIT (c) 2026 Sawyer Cutler | Keep `vendor/webmcp-core/LICENSE`. |
| **three.js r128** | inlined in `web/index.offline.html`; `node_modules/three` at build time | MIT | Licence text ships inside the minified file header. |
| **Public Sans** (variable), **IBM Plex Mono** 400/500/600, Latin subsets | `web/fonts/`, inlined in the pages | SIL OFL 1.1 | Keep `web/fonts/LICENSE.txt`. |
| Faraday (design inspiration only, no code) | none | MIT | Credited in the README. |
| jsdom, scikit-learn, FastAPI, Playwright, etc. | development / server dependencies, not redistributed here | their own licences | Installed from PyPI / npm. |

Removed from the repository for launch because their licence is unconfirmed: the 16-slice real CT excerpt `real_ct_slab_16x2.5mm.nii.gz` (from the owner-supplied Heart CT & MRI data set).

The project's own code is MIT-licensed (see `LICENSE`), except the BodyParts3D-derived mesh noted above.
