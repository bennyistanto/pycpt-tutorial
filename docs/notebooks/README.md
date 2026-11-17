# Executed companion notebooks

The first [executed teaching notebook](indonesia-seasons-2023.ipynb) reproduces
the twelve-season2023 story. Default execution is offline; the optional OND
CCA/PCR rerun writes only to a new scratch directory.

Run `python scripts/execute_tutorial.py` from the repository root to refresh its
outputs and generated story findings. Read the [reproduction guide](../guides/reproduce.qmd).
Exploratory and downloaded reference notebooks stay in ignored `temp/`.

The second [executed fitting notebook](fit-diagnose-2023.ipynb) makes four actual
CCA/PCR calls for OND/JJA2023and saves every returned dataset plus checked
diagnostics. Executing it requires the full PyCPT fitting environment and its
compatible engine; local inputs need no credentials or source downloads.
Refresh this notebook separately with `python scripts/execute_fitting_tutorial.py`.
Package its dedicated kit with `package_fitting_tutorial.py`; keep the first case
unchanged.

The lead-time notebooks follow the site's order: seasonal, monthly, dekad, week, pentad.

The third, [seasonal lead-time notebook](seasonal-leads-2023.ipynb), takes the CFSv2
run started on 1 November 2023, builds CHIRPS v3.0 totals for each of the next six
three-month seasons from the local dekadal archive at the native 0.05° grid and fits
CCA and PCR for each through PyCPT's `evaluate_models`, plus CCA for October-December
from six earlier starts. It writes `docs/data/seasonal-leads-2023/` and
`docs/assets/seasonal-leads-2023/`. Its season-against-month comparison reads the
monthly notebook's `skill-by-lead.csv`, so when both are refreshed, execute the
monthly notebook first.

The [seasonal ensemble notebook](seasonal-mme-2023.ipynb) calibrates seven models
started on 1 June 2023 for the next six seasons (78 fits through
`research/scripts/seasonal_mme_fits.py`, which reuses finished fits) and combines them
with PyCPT's `construct_mme`. It writes `docs/data/seasonal-mme-2023/` and
`docs/assets/seasonal-mme-2023/`. One ensemble at 0.05° needs about 60 GB of memory.

The [monthly ensemble notebook](monthly-mme-2023.ipynb) does the same for the single
months July to December 2023 (82 fits, because SEAS51c reaches November). It writes
`docs/data/monthly-mme-2023/` and `docs/assets/monthly-mme-2023/`.

The fourth, [monthly lead-time notebook](monthly-leads-2023.ipynb), applies the same
steps to each of the next six months (and November from six earlier starts). At 0.05°
each fit takes about 15-18 minutes, so the eighteen fits run side by side in separate
processes. It writes `docs/data/monthly-2023/` and `docs/assets/monthly-2023/`.
Refresh it in the full PyCPT environment with
`python scripts/execute_learn_chapter.py docs/notebooks/monthly-leads-2023.ipynb --timeout 14400`.

The fifth, [dekad lead-time notebook](dekad-leads-2023.ipynb), downloads the GEFSv12
starts listed by `research/scripts/download_gefs_dekads.py` (kept in
`~/PyCPT/indonesia-ond-2023-dekads/gefs/`, shared with the weekly and pentad cases),
reads the CHIRPS v3.0 dekad product at 0.05°, builds dekad anomalies and fits CCA and
PCR through `cptcore` at three leads, six fits in parallel through
`research/scripts/weekly_fits.py`; execute it with `--timeout 14400`. It writes
`docs/data/dekad-leads-2023/` and `docs/assets/dekad-leads-2023/`.

The sixth, [weekly lead-time notebook](week-leads-2023.ipynb), reads daily CHIRPS
v3.0 for Indonesia (yearly NetCDF files from `research/scripts/gee_daily_to_netcdf.py`),
reuses the GEFSv12 starts listed by `research/scripts/download_gefs_weeks.py` and fits
CCA and PCR at 0.05° for five leads. At that resolution one fit takes over an hour,
so `research/scripts/weekly_fits.py` runs the ten fits in parallel and reuses a fit
whose inputs and settings are unchanged; execute it with
`python scripts/execute_learn_chapter.py docs/notebooks/week-leads-2023.ipynb --timeout 14400`.
It writes `docs/data/week-leads-2023/` and `docs/assets/week-leads-2023/`.

The seventh, [pentad lead-time notebook](pentad-leads-2023.ipynb), reads the CHIRPS v3.0
pentad product for Indonesia (exported from Earth Engine by
`research/scripts/gee/chirps3_pentad_to_drive.js` and converted by
`research/scripts/gee_pentad_to_netcdf.py`), uses the GEFSv12 starts listed by
`research/scripts/download_gefs_pentads.py` and fits CCA and PCR at 0.05° for six leads,
twelve fits in parallel through `weekly_fits.py`; execute it with `--timeout 21600`.
It writes `docs/data/pentad-leads-2023/` and `docs/assets/pentad-leads-2023/`.

The subseasonal ensemble notebooks ([dekad](dekad-mme-2023.ipynb),
[weekly](week-mme-2023.ipynb), [pentad](pentad-mme-2023.ipynb)) calibrate five SubX
models for one issue date and average them. `research/scripts/subseasonal_mme_fits.py`
downloads the hindcasts and 2023 runs, prepares the inputs and runs the fits (28, 50
and 58), one process per fit, reusing finished fits; run it with `--fit` before
executing a notebook, since a CCA fit at 0.05° takes one to several hours and about
6 GB of memory. They write `docs/data/<case>-mme-2023/` and
`docs/assets/<case>-mme-2023/`.
