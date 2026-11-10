# Official PyCPT notebook comparison

Reviewed 2026-11-01, following the [methodology audit](METHODOLOGY_AUDIT.md).
Source: [iri-pycpt/notebooks](https://github.com/iri-pycpt/notebooks), pinned at
commit `1c975316910b9e047ce685d9b8cdefb2c4b73551` (2025-10-14).
This is a configuration and workflow-source survey of all **18 notebooks**, with
focused inspection of the seasonal cases, operational template, station example,
subseasonal templates and flexible-forecast debugging cells. The upstream notebooks
were **not executed**. Their datasets, local paths, saved figures and claimed
compatibility have not been independently reproduced here.

All 21 downloaded notebook/Markdown/YAML files were checked against their Git blob
hashes. A separate installed-helper calculation uses our existing Indonesia data;
it performs no new CPT fits and changes no benchmark outputs.

## Examples relevant to this project

Cell numbers below are zero-based notebook cell indexes, retained in the evidence manifest.
The ranges are allowed mode counts, not the final numbers chosen by CPT.

| Notebook | Configuration inspected | Relevance to Indonesia |
| --- | --- | --- |
| [Operational seasonal template](https://github.com/iri-pycpt/notebooks/blob/1c975316910b9e047ce685d9b8cdefb2c4b73551/Operations/pycpt-operational.ipynb), cell6 | CV5; X EOF1–8, Y EOF1–6, CCA1–3; no transform/tailoring; masks None; minimum PyCPT2.10.0 | Strongest starting structure for a current learner workflow, availability summary, diagnostics, MME and flexible forecasts. |
| [Niger JAS](https://github.com/iri-pycpt/notebooks/blob/1c975316910b9e047ce685d9b8cdefb2c4b73551/Examples/pycpt-seasonal-v251-NigerJAS-Jan2024.ipynb), cell6 | CV5; X1–6, Y1–3, CCA1–3; no transform | A regional seasonal case with different mode ranges. |
| [Guyana JFM, local observations](https://github.com/iri-pycpt/notebooks/blob/1c975316910b9e047ce685d9b8cdefb2c4b73551/Examples/pycpt-seasonal-v251-Guyana-JFM-local_predictand.ipynb), cell8 | CV3; X3–8, Y3–6, CCA1–3; local CPT TSV predictand | Useful structure for teaching local CHIRPS preparation and December initialization for JFM. |
| [Greater Horn OND2023](https://github.com/iri-pycpt/notebooks/blob/1c975316910b9e047ce685d9b8cdefb2c4b73551/Examples/pycpt-sesasonal-v251-OND2023_GHAfrica-CanSIPSIC3.ipynb), cell6 | CV3; X3–8, Y3–6, CCA1–3 | Comparable target-season worked example; does not prescribe Indonesian domains or tuning. |
| [Chile station/grid](https://github.com/iri-pycpt/notebooks/blob/1c975316910b9e047ce685d9b8cdefb2c4b73551/Station/pycpt-seasonal-station-grid-Chile.ipynb), cell8 | CV5; X1–8, Y1–6, CCA1–3; no transform | Station identifiers, local verification locations, grid/station alternatives; potential later station chapter. |
| [Subseasonal template](https://github.com/iri-pycpt/notebooks/blob/1c975316910b9e047ce685d9b8cdefb2c4b73551/Subseasonal/pycpt-s2s.ipynb), cell6 | Retroactive validation; CV5; initial training45%, step10%; weekly lead definitions | Supports treating subseasonal training and verification as a separate design. Not a tested Indonesia configuration. |
| [Older Greater Horn S2S example](https://github.com/iri-pycpt/notebooks/blob/1c975316910b9e047ce685d9b8cdefb2c4b73551/Examples/pycpt-s2s-v250-GHAfrica-ECMWF-precip.ipynb), cell9 | Value is `crossvalidation`, but adjacent comment says only retroactive is supported | A concrete inconsistency: do not assume a comment accurately describes execution. |
| [CPT-Core demo](https://github.com/iri-pycpt/notebooks/blob/1c975316910b9e047ce685d9b8cdefb2c4b73551/Demo/cptcore_demo.ipynb), cells3/6 | Calls CCA/PCR directly with xarray inputs and a separate forecast predictor | Supports the lower-level architecture used in our fixed-input experiments. |

The literal configuration extractor records no direct `cpt_args` assignment for
the configuration-file test or the Colab notebook. That does **not** mean those
notebooks lack settings: the former loads an external configuration; the latter
places Python inside an IPython bash cell, which the ordinary AST parser skips.
The cache retains their source for inspection; their effective external/runtime
configuration is not certified by this review.

## What agrees with our experiments

Five-sample cross-validation is used in the maintained seasonal template and Niger
case; three is used in Guyana and the Greater Horn seasonal case. This agrees with
the IRI teaching reference's discussion of either choice. There is no single
universal CV-window setting across examples. We used five consistently.

Our direct `cptcore` calls are a demonstrated API pattern. They return xarray
hindcasts, forecasts, skill fields and model diagnostics. Our fixed counts
(CCA3X/3Y/2CCA; PCR3X) deliberately differ from the searched ranges in the seasonal
examples. They should be described as a controlled comparison, not as a reproduction
of an optimized example configuration or proof of optimal mode counts.

Local predictands are supported in the example structure. This supports a tutorial
chapter on preparing and validating CHIRPS units, seasonal totals, coordinates,
coverage and country aggregation. It does not independently validate our particular
CHIRPS preprocessing; that evidence remains in the existing case audits.

The notebooks plot both EOF and CCA patterns. Our existing model outputs provide
diagnostics, but a scientific interpretation of their physical plausibility has not
yet been completed. That remains a real gap to address before recommending settings.

## Probability scores need variable-level provenance

The operational seasonal notebook explicitly labels individual-model generalized
ROC and ranked-probability skill as in-sample (cell18). Its MME plotting section
lists those scores again without repeating that warning. The underlying installed
PyCPT2.10.4 source resolves the provenance:

- `evaluate_models` first computes native CV hindcasts and separate forecasts.
- It calls CCA/PCR again with the training predictors re-dated by **48 years** as
  forecast inputs, then shifts the returned probability dates back.
- Those probabilities are generated by a model fitted on the same observations
  against which they are scored. The source explicitly warns about optimistic scores.
- It merges those fitted probabilities and variances into a dataset that also
  contains deterministic CV hindcasts, and writes a file named as cross-validated
  hindcasts. That filename does not establish independent provenance for every variable.
- `construct_mme` calls `construct_mme_new` and `evaluate_mme`, which score the supplied
  probability series. Averaging members does not remove their in-sample provenance.

These statements are source-confirmed for our installed2.10.4; this review does not
make an execution claim about every older example or the subseasonal driver.
The installed module is byte-identical to the
[official PyCPT2.10.4 source](https://github.com/iri-pycpt/pycpt/blob/084bb5c380c200b5f65f11ba224a965547b91da1/pycpt/src/pycpt/notebook.py#L366).
Its hash and function ranges are recorded in the linked evidence below.

Our Indonesia experiments used the core functions directly and did **not** use
this high-level re-dating step or publish these in-sample probability scores.
This reinforces the existing audit: a notebook's probability-skill map must not
be presented as independent forecast validation merely because it is an official example.
For future probability work, validate a dedicated double-CV/retroactive/independent
workflow on the pinned runtime rather than assuming changing the seasonal template's
`validation` string alone makes all its downstream probability scores independent.

## Flexible probabilities are not an exact native-CPT reconstruction

The operational notebook calls `construct_flex_fcst` for threshold exceedances.
For untransformed data, the installed helper uses

```
helper_df = N
helper_scale = sqrt((N - 2) / N * saved_prediction_error_variance)
```

The audited native CPT17 calculation for our fixed-three-X-EOF fits instead uses
`df = N - 4` and `scale = sqrt(saved_prediction_error_variance)`.
Moreover, the helper takes the supplied deterministic forecast as its location,
which cannot recover an unclipped negative location from a saved zero-bound value.
Its percentile option calls `Y.quantile`; the caller must determine which years
are in Y and must check quantile conventions before equating it with CPT thresholds.

A controlled check on the saved **OND2023 CCA1991–2020** case holds the physical
67th-percentile thresholds, positive forecast locations and saved squared scales
identical. It supplies those thresholds in physical units to avoid introducing a
separate quantile-definition discrepancy. All3240cells have positive forecast
values in this case. Native degrees of freedom are26, versus30 in the helper.

- Maximum helper-versus-native probability difference: **0.881985 percentage points**.
- Mean absolute difference: **0.624328 percentage points**.
- At the largest-difference cell: native probability15.860502%, helper14.978517%.
- The independent native-formula reconstruction differs from the saved CPT
  probabilities by at most0.000123percentagepoints, within the earlier audit tolerance.

This establishes non-equivalence of these particular implementations; it does
not establish which is empirically better calibrated. No native output was
replaced. Flexible exceedance tools are useful tutorial candidates, but their
distribution, reference years, threshold convention and zero-bound behavior must
be documented and checked before being described as equivalent to native CPT maps.

## Version and capability cautions supported by the repository

The [operations changelog](https://github.com/iri-pycpt/notebooks/blob/1c975316910b9e047ce685d9b8cdefb2c4b73551/Operations/CHANGELOG.md)
marks predictand transformations as non-working in2.9.0; the current seasonal,
station and subseasonal templates retain warnings. Older Gamma/Empirical notebooks
in `Debugging/` are not evidence that these transformations are supported correctly
in our runtime. Keep them outside the learner's tested path until separately verified.

The root environment file pins PyCPT2.9.1, CPT17.8.3 and cptio1.3.0 and includes a
development channel, while the operational notebook requires PyCPT>=2.10.0.
These files therefore do not form one mutually consistent current installation
recipe. Retain our tested lock files. The operations changelog notes the PCR fix in
2.9.0 and model-availability handling in2.10.0; a minimum-version check alone does
not prove an older example's data catalog and arguments still work.

NetCDF export is already present in the upstream high-level workflow and older
examples through xarray `to_netcdf`. Our export tooling adds project-specific
metadata handling and checks; basic NetCDF output should not be presented as a
missing PyCPT capability. Upstream NetCDF filenames likewise do not certify
validation independence or all scientific metadata.

No inspected seasonal configuration explicitly sets the effective CPT category
climatology or exports an unclipped location and native t degrees of freedom as a
complete probability reconstruction package. These examples therefore do not
supersede the actual stdout/source findings in METHODOLOGY_AUDIT.md.

## Recommended tutorial changes

1. Use the current Operations sequence for an accessible worked example, with
   local CHIRPS preparation from the Guyana pattern and version checks against our locks.
2. Add explicit teaching distinctions between fixed counts and model selection,
   deterministic CV diagnostics and fitted probability scores, training years and
   category reference years, and native and flexible probabilities.
3. Complete physical EOF/CCA-pattern and regional/dry-season review using the existing
   frozen artifacts; these steps are more urgent than adding new model combinations.
4. Develop a separately verified probability-validation example with common events
   and explicit thresholds/location/scale/dof exports. Keep the existing native
   benchmark unchanged; do not add in-sample RPSS as evidence of forecast skill.
5. Treat MME, station verification, flexible thresholds and subseasonal forecasts
   as later extensions with their own data and validation checks.

Evidence: [source/configuration manifest](../audits/methodology-2026-11-01/notebooks/source_manifest.json),
[official-versus-installed source identity](../audits/methodology-2026-11-01/notebooks/installed_source_provenance.json),
and [saved-case helper comparison](../audits/methodology-2026-11-01/notebooks/installed_workflow_check.json).
The source cache is `temp/official-notebooks/`; download/hash helper is
`temp/review-official-notebooks.py`. Reproduce the local comparison with the Debian
environment's Python and [research/scripts/check_notebook_workflow.py](../scripts/check_notebook_workflow.py)
after preparing that pinned cache. No upstream code cells are executed by the cache helper.
