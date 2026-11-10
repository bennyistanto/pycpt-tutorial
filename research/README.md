# Research evidence and reproducible pipelines

This folder contains durable work supporting the tutorial. These are completed
analyses and reusable research pipelines, not disposable intermediate files.

| Folder | Contents |
| --- | --- |
| [cases/](cases/) | Frozen case reports, NetCDF results, figures, metrics and provenance |
| [audits/](audits/) | Numeric checks, source identity records and scientific-method evidence |
| [reports/](reports/) | Methodology audit, official-notebook review and repository layout |
| [scripts/](scripts/README.md) | Preparation, fitting, verification and report-generation pipelines |

Start with the [all-twelve-season benchmark](cases/indonesia-all-seasons-2021-2024-025deg/README.md),
the [methodology audit](reports/METHODOLOGY_AUDIT.md), and the
[official notebook review](reports/NOTEBOOK_REFERENCE_REVIEW.md).
The [reader requirements audit](reports/READER_REQUIREMENTS_AUDIT.md) records
which notebook activities need PyCPT, CPT or protected-data authentication.
The [fresh analysis environment test](reports/ANALYSIS_ENVIRONMENT_VALIDATION.md)
confirms complete-kit execution with the smaller specification on Debian WSL2.
The [OND/JJA diagnostics audit](reports/FITTING_DIAGNOSTICS_AUDIT.md) supports the
second-case design. The
[completed fitting tutorial report](reports/FITTING_TUTORIAL_2023.md) records its
executed fits, NetCDF exports and separate kit validation.
The [subseasonal readiness audit](reports/SUBSEASONAL_READINESS.md) inventories
live model/observation coverage and identifies workflow work required before
selecting or fitting the next case.
The [GEFSv12 input-adapter report](reports/GEFSV12_INPUT_ADAPTER.md) follows it
with two verified full-Indonesia input checks, seven NetCDFs, rnl/sat sensitivity
and proposed training/validation periods. It runs no fits.
The earlier [OND2023 case](cases/indonesia-ond-2023/README.md) and its sensitivity
experiments remain preserved controls.

Development-only runtime investigations are in
[runtime development notes](reports/RUNTIME_DEVELOPMENT_NOTES.md) and
[CPT compatibility findings](reports/CPT_COMPATIBILITY.md). They are separate
from the PyCPT learner setup and are not included in the rendered tutorial.

Large input caches, native CPT session files and raw observations remain in their
existing Debian locations under `/home/bennyistanto/CPT/`. Historical JSON records
retain original paths and execution hashes. See the
[repository relocation record](reports/REPOSITORY_LAYOUT.md) for the current paths.

Scratch analyses, reference downloads, temporary previews and caches belong in
the ignored repository `temp/` directory. Research evidence does not automatically
become book content; use selected verified results in [docs/](../docs/README.md).

## Opening the case outputs

Every case keeps its NetCDF results in its `outputs/` folder, next to a README that
describes them and JSON manifests that record each file's SHA-256 hash. The files
are standard NetCDF4 and open with xarray, for example
`xarray.open_dataset("cases/indonesia-all-seasons-2021-2024-025deg/outputs/verification_scores.nc")`.
