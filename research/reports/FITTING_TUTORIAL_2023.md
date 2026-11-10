# Executed PyCPT fitting tutorial: OND and JJA2023

Completed2026-11-02. The second Quarto case pairs an interactive story with an
executed notebook containing four actual local-input PyCPT fits. It preserves
the first case and the original research controls.

## Delivered material

- Story: `docs/chapters/fit-diagnose-2023.qmd`.
- Executed notebook: `docs/notebooks/fit-diagnose-2023.ipynb`,18code cells,0errors.
- Inputs and controls:26files plus provenance in `docs/data/fitting-2023/`.
- Derived outputs:30NetCDFs,5CSV tables,6PNG figures and an execution manifest
  in `docs/assets/fitting-2023/`.
- Six reactive story panels: inputs, national scores, spectra, paired patterns/
  score series, CV-year errors and forecast/error maps. Tables filter, sort and
  export all matching rows; chart SVG and selected-view PNG downloads are provided.
- Separate fitting kit and fitted-output archive in `docs/downloads/`.
- Home, sidebar and setup guide link both cases. The local book has9pages.

The story presents the same Python-computed values as the notebook. Browser code
does not fit models or recompute aggregate verification scores.

## Fits and comparisons

The four fits are OND/JJA × CCA/PCR, all trained on1991–2020with30seasonal samples.
CCA retains3X EOFs,3Y EOFs and2CCA modes; PCR retains3X EOFs. The native cyclic
CV window is5. Actual command records are checked for `534` followed by `5`.
The final forecast uses the separate2023F input; training X/Y dates coincide and
all training targets precede the forecast initialization.

All four new deterministic forecasts and all four CV hindcast arrays match their
frozen controls with **maximum absolute difference0mm**. Other native forecast
fields, skill variables and cleaned diagnostics pass their variable-specific
comparisons. These are replication checks, not proof of general forecast skill.

|2023target | Raw RMSE(mm) | Climatology | CCA | PCR |
| --- | ---: | ---: | ---: | ---: |
| OND |292.3895|226.4961|120.3460|117.3561|
| JJA |377.8240|130.6912|177.9793|175.5869|

Both calibrations improve on raw in both selected cases; climatology beats them
in JJA2023. This preserves the original result, including the negative comparison.

The notebook also computes deterministic CV-year residuals. Its climatology
baseline omits the same cyclic five observations as each calibrated hindcast;
the raw model is uncalibrated. Pooled CV RMSE is calculated from averaged squared
errors, not averaged annual RMSE. The resulting CV national RMSE values are:

| Training season | Raw | Leave-window climatology | CCA | PCR |
| --- | ---: | ---: | ---: | ---: |
| OND |389.2003|211.9982|168.0983|170.0261|
| JJA |371.4935|238.3252|216.0234|221.3467|

These within-training diagnostics and the selected2023forecast errors are
labeled separately. They are not independent confirmation of a setting selected
by inspecting these examples. The balanced cyclic climatology can have zero
pooled bias by construction while retaining substantial errors.

## NetCDF exports and interpretation

| Files | Count |
| --- | ---: |
| Native forecasts, hindcasts and native skill |12|
| Returned X/Y pattern datasets |6|
| Clean predictor/predictand diagnostic datasets |6|
| Native/recomputed canonical-correlation tables |2|
| Forecast comparison, national scores, CV-year scores, CV residual fields |4|

The cleaned files separate EOF,CCA and spectrum axes. Native exported weights
are retained under explicit names and masked using original complete-input
support; outside-support -999values are decoded only in derived copies. Field–score
correlation maps are calculated explicitly. Score series are standardized
separately for display. Full-training patterns are not per-fold EOF diagnostics.

The prior audit's small absolute EOF eigenvalue-scale discrepancy remains
unresolved. The lesson uses checked correlations and variance percentages and
does not claim amplitude reconstruction. Native probabilities and prediction-error
variance fields are preserved with provenance but not treated as independently
validated probability skill; see the [methodology audit](METHODOLOGY_AUDIT.md).
No physical ENSO/IOD attribution or cause of the JJA residuals is established.

## Runtime, isolation and complete-kit test

The runtime remains the existing tested Debian WSL2 environment. Conda identifies
PyCPT2.10.4; Python metadata reports2.10.4.dev0. Both are recorded. Engine and
CCA/PCR wrapper hashes match the audited control runtime. The initial strict
metadata check stopped before fitting; it was corrected to verify release and
source identity without changing any installed packages.

The final notebook completed18cells in97.3seconds. Its four fits have separate
scratch directories, native-file hashes, logs and command records. An earlier
successful authoring execution is retained in the audit folder; the notebook
was re-executed after correcting a clipped colour-bar label and map spacing.
These are two authoring passes through the same four configurations.

The distributed kit was then extracted into a new directory and executed with
the tested full fitting environment: another four isolated fits,18cells,0errors,
108.7seconds. All30NetCDF datasets are identical to the canonical outputs,
all5CSV tables agree, all6PNGs are byte-identical, and interactive values and
generated story findings agree. The canonical notebook was not modified by this test.
Credential-read and remote-connection counters are zero for all successful runs.
No source download, environment update or installed-library patch was performed.

Reading either case requires only a browser. Running this fitting notebook needs
the full PyCPT environment and compatible engine. The first case's analysis-only
workflow remains unchanged. The kit does not require the original E:/F: drives.

## Independent and presentation checks

- Independent NumPy bilinear interpolation, leave-five-out climatology and error
  reductions reproduce forecast/CV scores within7.39e-13mm. Native CV RMSE maps
  agree with residual-derived maps within0.001334mm, inside the0.01mmcheck.
- 142,298 finite presentation values, including coordinates, match saved NetCDF
  values exactly;600standardized score values pass independent checks.
- Actual downloads:5SVGs,278vector values exact, no raster images/external assets;
 4valid full-view PNGs; CSV checks include30filtered CV years and two3,240-cell
  coordinate/value exports. The CV table displays25rows per page but exports all30.
- Desktop1280and mobile390layouts, mobile navigation, code/figure display,
  dropdowns, keyboard/pointer details, sorting/filtering and export controls checked.
- First-case preservation:51snapshotted files byte-identical, including notebook,
  story source, data, interactive assets and kit;328frozen research files unchanged.
- Final book checks: nine pages, 1,091 local links, no broken links; all 25 tests
  pass. These checks do not execute either canonical notebook again.

Browser QA exposed and corrected missing CSV metadata columns in the reused
table defaults. The new tables now preserve year/mode/side/coordinate/value fields.
Training selectors explicitly say1991–2020rather than2023.

It also exposed a Quarto1.8.27static-notebook widget bootstrap conflict. The
installed renderer classifies plain HTML tables as possible JS widgets and
injects CDN jQuery/RequireJS. The local render helper now removes those three
bootstrap tags only when outputs are script-free text/HTML/PNG and widget metadata
is absent. Interactive/unknown outputs are left alone; no notebook bytes change.
Both notebook pages now have no remote script dependencies. This is consistent
with Quarto's [documented widget-related external dependencies](https://quarto.org/docs/advanced/html/external-sources.html),
checked against the installed renderer code. Final clean-tab review has no
application console errors and retains all six notebook figures.

## Evidence and reproduction

- [Preparation and case-one baseline](../audits/fitting-tutorial-2023/preparation.json).
- [Executed notebook record](../audits/fitting-tutorial-2023/execution.json).
- [Kit manifest](../audits/fitting-tutorial-2023/kit.json),
  [kit execution](../audits/fitting-tutorial-2023/kit-execution.json) and
  [kit output comparison](../audits/fitting-tutorial-2023/kit-verification.json).
- [Independent verification](../audits/fitting-tutorial-2023/verification.json),
  [download checks](../audits/fitting-tutorial-2023/download-verification.json) and
  [browser review](../audits/fitting-tutorial-2023/browser-validation.json).
- [Initial diagnostic audit](FITTING_DIAGNOSTICS_AUDIT.md) and
  [design/implementation plan](../plans/FITTING_DIAGNOSTICS_TUTORIAL.md).

Author workflow: `prepare_fitting_tutorial.py` → `execute_fitting_tutorial.py` →
`package_fitting_tutorial.py` → `test_fitting_tutorial_kit.py` → `render_tutorial.py`
→ `verify_fitting_tutorial.py`, plus the existing preservation/book verifiers.
Use the full tested environment. Ordinary Quarto rendering never fits models.
No staging, commits, pushes or hosting deployment were performed.
