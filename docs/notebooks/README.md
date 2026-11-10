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

The third [executed lead-time notebook](monthly-leads-2023.ipynb) builds November
CHIRPS v3.0 totals from the local dekadal archive, downloads CFSv2 for six start
dates and fits CCA and PCR at each. It writes `docs/data/monthly-2023/` and
`docs/assets/monthly-2023/`. Refresh it in the full PyCPT environment with
`python scripts/execute_learn_chapter.py docs/notebooks/monthly-leads-2023.ipynb`.

The fourth, [seasonal lead-time notebook](seasonal-leads-2023.ipynb), applies the same
steps to October-December and reads the monthly notebook's `skill-by-lead.csv` for
its comparison, so run the monthly one first. It writes `docs/data/ond-leads-2023/`
and `docs/assets/ond-leads-2023/`.

The fifth, [dekad lead-time notebook](dekad-leads-2023.ipynb), downloads 293 GEFSv12
starts with `research/scripts/download_gefs_dekads.py` (about 1.2 GB, kept in
`~/PyCPT/indonesia-ond-2023-dekads/`), builds dekad anomalies and fits CCA and PCR
through `cptcore` at three leads. It writes `docs/data/dekad-leads-2023/` and
`docs/assets/dekad-leads-2023/`.
