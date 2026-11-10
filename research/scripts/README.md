# Research pipelines

Run these scripts from the repository root with the pinned Debian environment.
Their prepared inputs and model-run outputs remain under `/home/bennyistanto/CPT/`;
repo-facing reports and audit evidence use `research/cases/` and `research/audits/`.

The `prepare_indonesia_*`, `run_indonesia_*` and `verify_indonesia_*` families
correspond to the completed cases in `../cases/`. Their filenames and sibling
imports remain consistent. Reuse validated caches; read the case report before
running a script that can generate outputs.

```bash
conda activate pycpt-tutorial
python research/scripts/document_indonesia_all_seasons.py --output-dir temp/report-preview
```

The preview command reads saved results and writes a report preview without fitting
models or replacing the frozen case metadata. The original runtime smoke-check
command remains `python scripts/check_cpt.py`.

- `audit_indonesia_methods.py` reconstructs native probability construction and
  checks withholding in isolated Debian audit directories.
- `check_notebook_workflow.py` compares the installed flexible helper with a saved
  OND case, using the pinned source cache in `temp/official-notebooks/`.
- `audit_subseasonal_readiness.py` inventories the installed subseasonal driver
  and uses explicit `--stage` options for bounded live metadata/sample requests.
- `audit_daily_observation_availability.py` checks public daily CHIRPS3 filename
  continuity; `--sample` separately reads one raster per variant.
- `check_subseasonal_driver_readiness.py` exercises installed function bodies
  with I/O and fitting stubbed. It cannot produce a fitted model.
- `summarize_subseasonal_readiness.py` builds availability CSV/Markdown tables;
  `verify_subseasonal_readiness.py` checks cached evidence offline, without fits.

Read [the readiness report](../reports/SUBSEASONAL_READINESS.md) before rerunning
network stages. These checks do not choose or fit a subseasonal teaching case.

These scripts are reproducible research tools. Exploratory drafts belong in `temp/`.

Regional daily acquisition is now the user's preferred next step:
[Earth Engine script and instructions](gee/README.md) create monthly multi-band
Indonesia subsets and a band/date/source manifest for Drive. Start with the
six-image pilot; live export/value comparison is pending. Existing global wget
lists remain an alternative. The current TIFF reader needs a separate adapter
for these regional multi-band files; no fitting or source equivalence is implied.

## Input-only GEFSv12 / CHIRPS3 follow-up

- `prepare_gefs_indonesia_inputs.py` defaults to a dry plan. `--prepare` downloads
  bounded examples; repeatable `--hindcast-date` / `--forecast-date` arguments
  select explicit starts. `--variant both` is the rnl-primary/sat-check design.
  Caches are resumable; no fitting imports or subprocesses allowed.
- `check_gefs_weekly_provider.py` compares week-2 integration with two small
  public IRI server reductions; responses are cached.
- `verify_gefs_indonesia_inputs.py` independently verifies all saved arithmetic,
  identities, coverage and protected seasonal outputs offline.
- `propose_gefs_periods.py` derives proposed cohorts, annual target purges and
  transfer estimates from the saved coordinate census; no network or fits.
- `make_chirps3_download_lists.py` writes deduplicated rnl/sat lists for manual
  `wget -c -i` downloads, checking all dates against the saved filename census.
  Optional `--check-links` makes eight HEAD requests, never fetching TIFF bodies.
  [Download instructions and lists](../audits/gefs-input-adapter/download-lists/README.md)
  cover the proposed cohorts; no fits or bulk downloads are triggered.

Read [the adapter report](../reports/GEFSV12_INPUT_ADAPTER.md) for the corrected
UTC lead contract, units, two missing coastal cells and full-cohort gates.
Evidence/NetCDFs use `research/audits/gefs-input-adapter/`; model/native-country
daily caches use ignored `temp/gefs-input-adapter/`. Review bandwidth and regional
alternatives before scaling the global TIFF route to an entire archive.
