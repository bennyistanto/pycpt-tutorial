# Twelve seasons, 2021-2024, at native 0.05°

The source of the "Twelve seasons over Indonesia" case study. It repeats the design of
[indonesia-all-seasons-2021-2024-025deg](../indonesia-all-seasons-2021-2024-025deg/README.md)
on CHIRPS v3.0's native grid. That 0.25° case is unchanged and remains the control.

Produced by `research/scripts/run_indonesia_all_seasons_005.py` on 16 November 2026.

## Design

| Item | Choice |
| --- | --- |
| Predictor | CFSv2 ensemble-mean seasonal totals at 1°, 85-155°E, 20°S-20°N: the audited inputs of the 0.25° case, unchanged (hashes in `case_manifest.json`) |
| Observations | CHIRPS v3.0 three-month totals from the rolling archive, native 0.05° grid |
| Pixels | Every pixel with any overlap with the supplied 38-province boundary (`idn_bnd_adm1`, unsimplified), so coastal pixels and small islands are kept |
| Training | 1983-2010 (28 seasons) and 1991-2020 (30 seasons) |
| Verification | Ending years 2021, 2022, 2023, 2024 |
| Methods | CCA (3 X EOFs, 3 Y EOFs, 2 modes) and PCR (3 X EOFs), cross-validation window 5, through `cptcore` |
| Compared | Raw CFSv2 (interpolated), climatology and CCA and PCR for each training period |

Seasons are labelled by their ending year; NDJ and DJF start in the preceding year.

## Measured

- 70,215 pixels touch the boundary; 69,640 have data in every training and
  verification season of all twelve seasons and both periods. Those 69,640 are scored.
- 48 fits, 192 calibrated forecasts, no failures. One fit took 6.2 to 9.6 minutes
  (median 8.3) with 22 running side by side.
- For every fit, RMSE and Pearson correlation recomputed from the cross-validated
  hindcasts match CPT's own skill maps to within 0.0022 mm and 0.000014.

## Files

`outputs/` (14 NetCDF files):

- `<SEASON>_forecast_comparison.nc`: the seven forecasts and the observation for the
  four verification years, in millimetres.
- `evaluation_footprint.nc`: the pixel mask, the area weights, and each pixel's
  province (`province_index`, the province covering most of the pixel).
- `verification_scores.nc`: national RMSE, MAE and bias by season, forecast and year,
  and pooled over the years (squares averaged before the root).

`metrics.json` lists every fit with its run time and checks. `case_manifest.json`
holds the SHA-256 hash of every output.

CPT's own text files, the cross-validated hindcasts, probabilities and EOF and CCA
patterns of each fit stay in the working folder
(`~/CPT/cases/indonesia-all-seasons-2021-2024-005deg`, 18 GB) and are not part of
the repository.

## Limits

Four verification years and overlapping seasons are not independent samples. The
forecasts come from a 1° model: a 0.05° output does not establish 0.05° predictability.
Observations and model archive are current vintages, not what was available when each
forecast would have been issued. No significance or probabilistic skill is claimed.
