# Research evidence and reproducible pipelines

This folder contains durable work supporting the tutorial: completed analyses and
the reusable pipelines that produced them, not disposable intermediate files.

| Folder | Contents |
| --- | --- |
| [cases/](cases/) | Frozen case reports, NetCDF results, figures, metrics and provenance |
| [scripts/](scripts/README.md) | Preparation, fitting, verification and report-generation pipelines |

Start with the [all-twelve-season benchmark](cases/indonesia-all-seasons-2021-2024-025deg/README.md).
The earlier [OND2023 case](cases/indonesia-ond-2023/README.md) and its sensitivity
experiments remain preserved controls.
The [0.05° predictand trial](cases/indonesia-ond-2023-005deg-trial/README.md) tests
fitting at the native CHIRPS v3.0 resolution against the 0.25° grid.

Audits, reviews, plans and their evidence made while preparing the tutorial are
working records. They are kept outside the published repository (in the ignored
`temp/` folder), so scripts that write such records put them there. What the
published pages rely on from them is stated on the pages themselves, and the
[Methods & limitations](https://bennyistanto.github.io/pycpt-tutorial/guides/methods.html)
page summarises what was checked.

Large input caches, native CPT session files and raw observations remain in their
existing Debian locations under `~/CPT/`. Historical JSON records keep their
execution hashes; local paths in them are written as `~` (home) and `<repo>` (this
repository), with every recorded hash and size updated to match.

Research evidence does not automatically become book content; use selected verified
results in [docs/](../docs/README.md).

## Opening the case outputs

Every case keeps its NetCDF results in its `outputs/` folder, next to a README that
describes them and JSON manifests that record each file's SHA-256 hash. The files
are standard NetCDF4 and open with xarray, for example
`xarray.open_dataset("cases/indonesia-all-seasons-2021-2024-025deg/outputs/verification_scores.nc")`.
