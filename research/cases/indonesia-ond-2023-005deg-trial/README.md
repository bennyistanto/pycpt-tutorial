# Indonesia OND 2023: predictand at native 0.05° (trial)

**Question.** The case studies calibrate CFSv2 against CHIRPS v3.0 averaged to 0.25°.
Can PyCPT/CPT use the native 0.05° CHIRPS v3.0 grid as the predictand instead, at what
cost, and does it change the forecast or its skill?

**Answer, for this case.** Yes, it runs. A fit takes about 70 s instead of 4 s and
writes about 280 MB of CPT files instead of 12 MB. At the 0.25° scale the results are
practically unchanged: CCA moves slightly, PCR not at all. Per-location correlations
are lower at 0.05° than at 0.25°.

## Setup

Only the predictand resolution differs between the two fits.

| | |
| --- | --- |
| Predictor | CFSv2.PRCP from PyCPT `download_data`, 1° (Learn PyCPT chapter 2) |
| Predictand | CHIRPS v3.0 OND totals from the local 3-month archive (chapter 3), Indonesia land only (Natural Earth 1:10m) |
| 0.05° predictand | 61,192 Indonesian pixels; 61,190 complete in all 30 seasons |
| 0.25° predictand | The chapter 3 file: 3,240 cells, 5 × 5 pixels, 99% coverage rule |
| Settings | CCA 3 X EOFs, 3 Y EOFs, 2 CCA modes; PCR 3 X EOFs; cyclic cross-validation window 5; training 1991-2020; forecast OND 2023 |
| Engine | PyCPT 2.10.4 `cptcore` calls, CPT 17.8.3 |

Check: the 0.05° observations aggregated back to 0.25° with the tutorial's rule equal
the chapter 3 file exactly (largest difference 0.0 mm).

## Cost

| Fit | Runtime | CPT output folder |
| --- | --- | --- |
| CCA, 0.25° | 4.4 s | 12.7 MB |
| CCA, 0.05° | 72.6 s | 294.0 MB |
| PCR, 0.25° | 3.7 s | 11.8 MB |
| PCR, 0.05° | 67.4 s | 273.0 MB |

The Python process peaked at about 1.16 GB during the 0.05° runs. The memory of the
CPT executable itself was not isolated: the child-process figure recorded by the
script (604.8 MB) is identical to the Python process size at that point, which
suggests it measures a copy of Python rather than CPT, so it is not used here. `evaluate_models` fits each model twice (chapter 4), so the
runtime there roughly doubles.

## Results on a common grid

The 0.05° results are aggregated to the 3,240 cells of the 0.25° grid with the same
country-land rule and scored against the same 0.25° observations.

| Method | Fit | CV RMSE (mm) | Median cell CV correlation | 2023 RMSE (mm) |
| --- | --- | --- | --- | --- |
| CCA | at 0.25° | 167.40 | 0.588 | 124.08 |
| CCA | at 0.05°, aggregated | 167.28 | 0.587 | 123.67 |
| PCR | at 0.25° | 169.10 | 0.572 | 118.68 |
| PCR | at 0.05°, aggregated | 169.10 | 0.572 | 118.68 |

Largest difference between the two OND 2023 forecasts after aggregation: 18.3 mm for
CCA, 0.003 mm for PCR. A likely reason PCR does not change: it fits each location
separately on the same predictor components, so averaging pixels and averaging their
forecasts give the same result. CCA also compresses the predictand into EOF patterns,
and those patterns differ between grids. This explanation was not tested separately.

CPT's own Pearson correlation, at each grid's native scale: median 0.588 (CCA) and
0.572 (PCR) over 0.25° cells; 0.552 (CCA) and 0.537 (PCR) over 0.05° pixels. The two
describe different spatial scales and are not a ranking.

## What it means

A 0.05° predictand gives forecast maps with the detail of the observed rainfall
patterns, and the cost is manageable for single fits. It does not make the forecast
better at the 0.25° scale here: the predictor is still the 1° CFSv2 field. This is one
season (OND), one model and one setup.

## Files

- `trial.json`: settings, pixel counts, runtimes, output sizes and all scores above
- `forecast-2023-0p05.nc`: OND 2023 CCA and PCR forecasts (deterministic and tercile probabilities) and the observed OND 2023 total, at 0.05°
- `forecast-2023-common-0p25.nc`: both forecasts on the common 0.25° grid
- `cca-forecast-0p05-vs-0p25.png`: the CCA forecast at both resolutions, their difference and the observation

Reproduce with `research/scripts/run_indonesia_005_trial.py` and
`research/scripts/plot_indonesia_005_trial.py` in the pinned PyCPT environment. Native
CPT session files were kept outside the repository (`~/pycpt-005-trial`).
