# Audit of the Indonesia experiments against CPT references

Audited 2026-11-01. Scope: every completed Indonesia CCA/PCR experiment,
from the original OND 2023 pilot through the twelve-season 2021–2024 benchmark.
The conclusion is **consistent use of CPT's five-sample cross-validation and
native probability construction, with important corrections to the probability
documentation and no demonstration yet of empirical probability reliability**.

Follow-up: [official notebook source comparison](NOTEBOOK_REFERENCE_REVIEW.md),
covering 18 notebooks at a pinned commit, high-level in-sample probability scoring,
and a measured difference between flexible and native probability calculations.

This audit supersedes earlier descriptions that equated the category-reference
period with the training period, treated every deterministic output as the
unbounded probability location, or implied that numerical checks proved calibration.
The original data, forecasts, scores and figures remain frozen.

## References and versions

1. [IRI seasonal book: CPT](https://iri.columbia.edu/~awr/pycpt/seasonal-jupyterbook/html_2sep2023/cpt.html):
   per-year model reconstruction, recommended three/five-sample windows,
   deterministic validation, parametric probabilities and selection bias.
2. [Configuration in the same book](https://iri.columbia.edu/~awr/pycpt/seasonal-jupyterbook/html_2sep2023/configuration.html):
   example CV window five, mode ranges and diagnostic inspection.
3. [CPT forecast probabilities](https://cpthelp.iri.columbia.edu/Tools_Forecast_Probs.html):
   Student's t error distribution and cross-validated error variance, with optional alternatives.
4. [CPT verification](https://cpthelp.iri.columbia.edu/Tools_Verify.html) and
   [attributes diagrams](https://cpthelp.iri.columbia.edu/Tools_Verify_Attributes.html):
   probability verification is a distinct analysis of probabilistic hindcasts.
5. [CPT user guide, Calculate → Cross-Validated](https://iri.columbia.edu/~awr/wiki/Downscaling/HydroOutlooks/Documents/cpttutorial_june08.html):
   EOF/model reconstruction and cyclic boundary handling. This is an older guide;
   its description is checked against source and executable behavior below.
6. [CPT customising results](https://cptplus.org/Help/CPT_use_custom.html),
   [tailoring](https://cpthelp.iri.columbia.edu/Options_Tailor.html), and
   [release history](https://cptplus.org/whatsnew.html):
   default 1991–2020 category climatology, clipping to available dates, 33% outer
   categories, and zero-bounding after probability calculation (17.1.1 release).
7. [Official CPT 17.8.3 source archive](https://academiccommons.columbia.edu/doi/10.7916/fdp6-v391/download),
   SHA256 `58423f04b517ae63d1e6ff17f81e29dceaeb5ad74aad9945d44a8eb4c4ca5512`.
8. [SciPy Student's t reference](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.t.html):
   independent CDF/survival calculations with explicit location, scale and degrees of freedom.

The cited seasonal book documents PyCPT 2.5. The executed environment is
PyCPT 2.10.4, cptio 1.4.0, packaged CPT 17.8.3. The general help is maintained
for other releases too; it is not sufficient by itself to establish CPT17 behavior.
The installed `cptcore/functional/cca.py` and `pcr.py`, actual command streams,
session stdout, saved numeric outputs and isolated executable experiments supply
the version-specific evidence. No CPT19 production behavior was tested here.

## Findings by claim

| Claim | Finding | Evidence / qualification |
| --- | --- | --- |
| Omit the verification sample and refit CCA/PCR | Confirmed for the executed CV pathway | All 66 sessions send `534 → 5` and request native CV. Eight perturbation checks directly test first/middle/last-year exclusion for both methods. Matching source recalculates EOFs and regression in each fold. |
| Use three or five withheld samples | Five used consistently | Five means the predicted year plus two neighbours on either side, wrapping cyclically at the ends. It does not mean five additional years, random five-fold CV, or forward-only validation. |
| Separate final forecasts from CV hindcasts | Confirmed | CPT cross-validates within training, then fits all training years for the later forecasts. Saved training and forecast target sets do not overlap. |
| Probabilities use hindcast error information | Confirmed | Native commands request deterministic forecasts, prediction-error variance and probabilities. Saved variance has the spatial pattern of CV SSE with a predictor-dependent forecast multiplier; Student's t reconstruction matches probabilities. |
| A normal PDF is the exact implementation | Incorrect as an exact description | The book gives a normal PDF as an example. CPT17 uses a Student's t approximation. No observation transform was enabled. |
| Saved deterministic value always equals PDF location | Incorrect at zero-bounded outputs | CPT automatically enables zero-bounding for rainfall names; probabilities precede bounding. Isolated replays recover the unclipped locations at all 472 affected forecast cells. |
| Category climatology equals training years | Incorrect in our earlier descriptions | Actual logs show 1991–2010 for older within-year fits, not 1982/1983–2010. DJF/NDJ have additional boundary effects; see table below. |
| Probability sums/variance checks prove reliability | Not demonstrated | Bounds, sums and reconstruction check numerical construction. Reliability diagrams, Brier/RPS skill and distribution diagnostics have not been evaluated on a sufficiently long independent sample. |
| These settings identify the best CCA/PCR model | Not demonstrated | Counts are fixed, not a searched range: CCA 3 X EOFs / 3 Y EOFs / 2 CCA modes; PCR 3 X EOFs. Physical EOF/CCA-pattern review and nested selection were not completed. |
| Four years prove all-season operational skill | Not demonstrated | These are descriptive current-vintage replays; seasons overlap, fields are spatially dependent, and the model archive mixes reforecasts and operational data. |

## What cross-validation actually did

There are 66 successful historical-case sessions: two original 1° OND fits,
two 0.25° older-period OND fits, two recent-period OND fits, twelve additional
OND holdout fits, and 48 all-season batched fits. The four 2023 OND holdout
forecasts were reused, not counted as new sessions.

The wrapper sends `534` with value `5`, followed by the native analysis request.
Its ordinary-CV branch returns deterministic hindcasts; it does not produce a
verified probabilistic hindcast series. Full-period model construction after CV
is correct for the separate 2021–2024 forecast inputs, all outside training.
Raw model and climatology are deterministic baselines, not CCA/PCR fits.

In the all-season comparison, older folds train on 23 of 28 seasons and recent
folds on 25 of 30. Earlier 29-season OND folds use 24. The final forecast model
uses all 28, 30 or 29 training seasons respectively.

The isolated tests change one observed grid value by 100,000 mm at 1991, 2005
or 2020 in the OND 1991–2020 data. Both CCA and PCR return exactly unchanged
printed hindcasts whenever that sample belongs to the omitted window, while
hindcasts from folds containing it change substantially. For example, perturbing
1991 leaves 1991–1993 and 2019–2020 predictions unchanged: the window wraps.
Separate predictor perturbations at 2005 leave 2003, 2004, 2006 and 2007
hindcasts unchanged for both methods, supporting fold-specific predictor EOFs.
The 2005 prediction itself is not required to remain unchanged when its predictor changes.

These are targeted exclusion tests, not an independent reimplementation of all
CCA/PCR linear algebra. Source inspection supports the refitting mechanism:
`arrays.F95:get_cvsample`, `cca.F95:cv_cca`, `pcr.F95:cv_pcr`, and
`pcs.F95:get_pcs`. Retained input series are complete in all 66 audited sessions;
there is no intermittent missing-data imputation to contaminate these folds.
The geographic coverage masks were constructed from whole training intervals,
not independently within each fold; this distinction should remain explicit.

## Probability construction and the discovered defaults

The wrappers request CPT output IDs `511` (values), `514` (prediction-error
variance), and `501` (category probabilities). No recorded session invokes
forecast-settings override `552`. The source default uses cross-validated errors.
For our untransformed, fixed-three-X-EOF fits, the inspected source computes

```
nu = N - 3 - 1
s2_cv(grid) = sum((observation - CV_hindcast)**2) / nu
scale2(forecast, grid) = s2_cv(grid) * (1 + predictor_uncertainty(forecast))
P(below) = StudentT_CDF((lower_threshold - unbounded_estimate)/sqrt(scale2), nu)
P(above) = StudentT_SF((upper_threshold - unbounded_estimate)/sqrt(scale2), nu)
P(normal) = 1 - P(below) - P(above)
```

The native `cpt:dof` tags agree with `nu`. Across retained cells the saved
`scale2 / s2_cv` is spatially constant for each forecast, within printed-data
precision, as expected for these gridded CCA/PCR fits. It is not simply RMSE².
The source's predictor term is method-specific; this audit checks the native
construction and does not certify every formula against statistical theory.
In particular, `cca_predict` literally uses `1/N + Sum(prjc(1:ncc))**2`, while
PCR uses `1/N + Sum((projected_X_scores / singular_values)**2)`.
Do not replace these with a generic leverage formula when reproducing CPT17.

Also, CPT's named `prediction_error_variance` is the squared scale passed to its
t distribution. The variance of an unbounded mathematical t PDF is
`scale2 * nu/(nu-2)` when `nu > 2`. Its name should not be interpreted as proof
of a normal PDF, a confidence interval, or the variance of a bounded rainfall PDF.
Relevant routines are `prediction.F95:calc_errvar/calc_fcast`,
`distribs.F95:get_errvar/s_student_t`, `regression.F95:calc_pesd/calc_reg_probs`,
and the variance writer in `cpt_output.F95`.

The categories have 33% / 34% / 33% climatological probabilities, with empirical
33rd/67th-percentile thresholds, rather than exact mathematical thirds.
The effective category-reference periods in the all-season logs are:

| Target seasons | Older training 1983–2010 | Recent training 1991–2020 |
| --- | --- | --- |
| JFM through OND (ten within-year seasons) | 1991–2010, 20 seasons | 1991–2020, 30 seasons |
| DJF and NDJ, using our ending-year labels | 1992–2010, 19 seasons | 1992–2020, 29 seasons |

For example, the DJF log reports `1991/92 to 2009/10` for the older fit.
That corresponds to ending years 1992–2010. These effective dates were recovered
from stdout and used to reconstruct the saved probabilities; they are not inferred
from a NetCDF `training_period` label. The older standalone OND experiments also
use 1991–2010 category climatology. The deterministic climatology baseline in our
comparisons remains the explicitly calculated **full-training-period mean**.
Those two uses of climatology must not be conflated.
Some frozen NetCDF attributes describe events as dependent on the training period;
the precise category dates in this audit and its session inventory supersede that
shorthand. A filename's training-period label identifies fitting data, not necessarily
the period used to set its probability thresholds.

The automatic rainfall zero bound affects 472 forecast grid/time cells in six
all-season fits (JAS both methods/periods, JJA both older-period methods).
For these cells, the saved zero replaces a negative regression estimate after
probabilities have been calculated. Six isolated replays change only the Y field
label to suppress this automatic guess. Their full-fit estimates agree with the
original positive forecasts, and their unclipped locations, combined with the
**original** saved variances, reproduce the affected original probabilities.
Replay variances are deliberately not substituted: disabling the bound can change
CV hindcasts and hence CV errors. No frozen case was changed.

Across all 66 sessions, independent SciPy t calculations reproduce the native
probabilities within **0.000233 percentage points**, including bounded cells
using these recovered locations. CPT uses the AS27 approximation and printed
text, so this comparison uses a tolerance rather than exact SciPy equality. This is construction verification,
not an empirical reliability result.

## Provenance and reproducible evidence

- [Session inventory](../audits/methodology-2026-11-01/session_inventory.json): all 66
  command-file hashes, log paths, CV settings and effective climatological periods.
- [Numeric reconstruction](../audits/methodology-2026-11-01/probability_reconstruction.json):
  every fit's degrees of freedom, CV-variance ratio, bounded-cell count and probability discrepancy.
- [Withholding experiments](../audits/methodology-2026-11-01/withholding_experiments.json)
  and [summary](../audits/methodology-2026-11-01/summary.json).
- [Source archive comparison](../audits/methodology-2026-11-01/archive_comparison.json)
  and [bundled-source provenance](../audits/methodology-2026-11-01/source_provenance.json).
- Reproducible audit: [research/scripts/audit_indonesia_methods.py](../scripts/audit_indonesia_methods.py),
  run with the existing Debian `pycpt-tutorial` Python.

The initial bundled-source archive checksum did not match the recipe. The official
DOI download does match the recipe checksum. Comparing all 4,507 archived files
finds differences only in `data_version.F95`, `maps.F95` and `verif.F95`.
All fold, EOF, regression, probability, climatology and output routines cited above
are byte-identical across the two archives. The differences concern release date,
score-map handling and printed verification-table layout. This resolves provenance
for the formulas inspected here; this audit did not rebuild the executable.
The build recipe patches directory lengths and compiler-name handling, not these formulas.

Large raw evidence is retained in Debian at
`/home/bennyistanto/CPT/audits/reference-2026-11-01/`.
The engine SHA256 is
`3457c93ee3d7a69005e32c231a976c50a056da53868c02757f344a46a81a139e`.
Final hash checks confirm all 214 all-season artifacts in Debian and their repo
copies, plus 76 prior Debian artifacts, are unchanged. The existing 20 calendar,
parser, aggregation and export tests pass; those tests are not probability-reliability tests.

## Corrections and next scientific work

1. The deterministic comparisons remain usable as the reported retrospective
   experiments. The discovered category periods do not change their RMSE/MAE/bias
   or independently computed climatology baselines. Zero-bounding is part of the
   actual method evaluated and must be disclosed, including for CV hindcasts.
2. Treat existing probabilities as **native CPT probabilities with audited
   construction and effective thresholds**, not as demonstrated reliable forecasts.
   Existing files are preserved; this report supplies the missing interpretation.
3. Before comparing probability skill, explicitly fix category reference dates,
   calendar/ending-year convention and physical thresholds. Save thresholds, prior
   probabilities, t degrees of freedom, scale definition, zero-bound status and
   unclipped locations in a new versioned output set. Compare identical events.
4. Use double cross-validation or a suitably long retroactive/independent sequence
   to assess probabilities without recycling an observation both to estimate spread
   and to verify its own forecast. Our 2021–2024 forecasts already lie outside the
   fixed training windows; they can be scored descriptively, but four years do not
   establish reliable probability frequencies.
5. Add reliability/attributes diagrams, Brier and ranked-probability scores with
   reference forecasts and uncertainty estimates that respect temporal/spatial
   dependence; inspect residual distributions and dry-region behavior.
6. Examine EOF/CCA patterns and predefined regional diagnostics. Any tuning informed
   by 2021–2024 results makes those years development data for later model selection;
   reserve new independent data or use nested validation for subsequent claims.

No claim is made that fixed mode counts are optimal, that an untransformed t model
is adequate for every Indonesian rainfall regime, that the mixed model archive is
homogeneous, or that a 0.25° output grid establishes 0.25° dynamical predictability.
