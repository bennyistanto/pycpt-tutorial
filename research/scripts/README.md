# Research pipelines

Run these scripts from the repository root with the pinned Debian environment.
Their prepared inputs and model-run outputs remain under `~/CPT/`;
case results use `research/cases/`. Audit, verification and planning scripts, with
their evidence and reports, are working records kept outside the published
repository (in the ignored `temp/` folder).

The `prepare_indonesia_*` and `run_indonesia_*` families correspond to the completed
cases in `../cases/`. Their filenames and sibling imports remain consistent. Reuse
validated caches; read the case report before running a script that can generate
outputs.

```bash
conda activate pycpt-tutorial
python research/scripts/document_indonesia_all_seasons.py --output-dir temp/report-preview
```

The preview command reads saved results and writes a report preview without fitting
models or replacing the frozen case metadata. The runtime smoke check is
`python scripts/check_cpt.py`.

## Trials and lead-time inputs

- `run_indonesia_005_trial.py` and `plot_indonesia_005_trial.py` produce the
  [0.05° predictand trial](../cases/indonesia-ond-2023-005deg-trial/README.md).
- `run_indonesia_all_seasons_005.py` produces the
  [twelve-season run at 0.05°](../cases/indonesia-all-seasons-2021-2024-005deg/README.md)
  that the published twelve-season case and Fit & diagnose use.
- `check_mme_availability.py` records which seasonal models qualify for the
  multi-model ensemble of Learn PyCPT chapter 6
  (`docs/data/learn/mme-availability.json`).
- `check_lead_mme_availability.py` does the same for one issue date and its leads,
  for the seasonal and monthly ensemble cases.
- `seasonal_mme_fits.py` runs the fits of the seasonal and monthly ensemble cases,
  and `subseasonal_mme_fits.py` downloads, prepares and fits the five SubX models of
  the dekad, weekly and pentad ensemble cases. Both run one process per fit and
  reuse finished fits.
- `skill_calendar_scan.py` and `subseasonal_skill_scan.py` scan skill at 0.25° across
  issue dates and leads; the ensemble pages cite their tables.
- `check_subseasonal_values.py` checks that the SubX hindcasts and 2023 runs hold
  values, not only missing data.
- `no_model_cv_baseline.py` scores a forecast with no model in cross-validation, the
  baseline quoted by the single-model seasonal and monthly cases.
- `download_gefs_dekads.py` downloads the GEFSv12 starts used by the dekad
  lead-time case; resumable, with unit, member, lead, grid and missing-value checks
  per start. The weekly and pentad scripts reuse its helpers and cache.
- `download_gefs_weeks.py` and `download_gefs_pentads.py` define the weekly and pentad
  lead-time designs (`design()`, imported by their notebooks) and download the starts
  they need. The pentad design records one substitution: IRI's 5 December 2023
  real-time run holds only missing values, so that issue date uses the 4 December run.
- `weekly_fits.py` runs the 0.05° CPT fits of the weekly and pentad cases in parallel,
  one Python process per fit, and reuses a fit only when its input values and settings
  are unchanged.
- `gee_daily_to_netcdf.py` and `gee_pentad_to_netcdf.py` convert the Earth Engine
  exports (daily and pentad CHIRPS v3.0 for the Indonesia box) into yearly NetCDF files,
  checking every calendar day or pentad, the grid and the values.
- `download_chirps3_daily.py` downloads CHIRPS v3.0 daily NetCDF files from the
  Climate Hazards Center, gently (one file at a time, waiting when the server asks).

## Input-only GEFSv12 / CHIRPS3 preparation

- `prepare_gefs_indonesia_inputs.py` defaults to a dry plan. `--prepare` downloads
  bounded examples; repeatable `--hindcast-date` / `--forecast-date` arguments
  select explicit starts. `--variant both` is the rnl-primary/sat-check design.
  Caches are resumable; no fitting imports or subprocesses allowed.

Regional acquisition through Earth Engine is documented in
[gee/README.md](gee/README.md): monthly multi-band daily subsets, and yearly pentad
subsets (`chirps3_pentad_to_drive.js`), each with a manifest. Both have been exported
and checked against the local dekadal archive.

These scripts are reproducible research tools. Exploratory drafts belong in `temp/`.
