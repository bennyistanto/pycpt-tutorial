# Research pipelines

Run these scripts from the repository root with the pinned Debian environment.
Their prepared inputs and model-run outputs remain under `/home/bennyistanto/CPT/`;
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
- `check_mme_availability.py` records which seasonal models qualify for the
  multi-model ensemble of Learn PyCPT chapter 6
  (`docs/data/learn/mme-availability.json`).
- `download_gefs_dekads.py` downloads the GEFSv12 starts used by the dekad
  lead-time case; resumable, with unit, member, lead and grid checks per start.
- `download_chirps3_daily.py` downloads CHIRPS v3.0 daily NetCDF files from the
  Climate Hazards Center, gently (one file at a time, waiting when the server asks).

## Input-only GEFSv12 / CHIRPS3 preparation

- `prepare_gefs_indonesia_inputs.py` defaults to a dry plan. `--prepare` downloads
  bounded examples; repeatable `--hindcast-date` / `--forecast-date` arguments
  select explicit starts. `--variant both` is the rnl-primary/sat-check design.
  Caches are resumable; no fitting imports or subprocesses allowed.

Regional daily acquisition through Earth Engine is documented in
[gee/README.md](gee/README.md); it creates monthly multi-band Indonesia subsets and
a band/date/source manifest. Live export and value comparison are pending.

These scripts are reproducible research tools. Exploratory drafts belong in `temp/`.
