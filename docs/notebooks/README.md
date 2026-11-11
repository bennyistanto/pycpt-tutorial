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

The third [executed lead-time notebook](monthly-leads-2023.ipynb) takes the CFSv2
run started on 1 November 2023, builds CHIRPS v3.0 totals for each of the next six
months from the local dekadal archive and fits CCA and PCR for each, plus CCA for
November from six earlier starts. It writes `docs/data/monthly-2023/` and
`docs/assets/monthly-2023/`. Refresh it in the full PyCPT environment with
`python scripts/execute_learn_chapter.py docs/notebooks/monthly-leads-2023.ipynb`.

The fourth, [seasonal lead-time notebook](seasonal-leads-2023.ipynb), applies the same
steps to the next six three-month seasons (and October-December from six earlier
starts) and reads the monthly notebook's `skill-by-lead.csv` for its comparison, so
run the monthly one first. It writes `docs/data/seasonal-leads-2023/` and
`docs/assets/seasonal-leads-2023/`.

The fifth, [dekad lead-time notebook](dekad-leads-2023.ipynb), downloads 293 GEFSv12
starts with `research/scripts/download_gefs_dekads.py` (about 1.2 GB, kept in
`~/PyCPT/indonesia-ond-2023-dekads/`), builds dekad anomalies and fits CCA and PCR
through `cptcore` at three leads. It writes `docs/data/dekad-leads-2023/` and
`docs/assets/dekad-leads-2023/`.

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
