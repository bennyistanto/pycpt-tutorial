# CPT installation findings and PyCPT compatibility

> Recorded: 2026-10-31. Tested on Debian WSL, Linux x86-64.
> Status: installation and diagnostic tests complete; production CPT 19 integration is not implemented.

## Conclusion and exact scope

CPT 19.2.6 was built and installed successfully. Unmodified PyCPT 2.10.4 does not
work with that executable in our seasonal CCA/PCR checks. The supported tutorial
environment remains PyCPT 2.10.4 with its packaged CPT 17.8.3.

A diagnostic that changes four skill-menu mappings in memory and omits predictor
initialization metadata completes CCA/PCR calculations, output parsing, and NetCDF
writing with CPT 19.2.6. This supports the feasibility of a focused compatibility
update, but does not establish seamless support or identify every required change.

The target in this report is **19.2.6**, not an unbounded claim about the latest CPT.
The [public CPT download page](https://cptplus.org/download.html) still listed 19.1.3
when checked, while the supplied archive and installed About menu identify 19.2.6.
The [PyCPT notebook releases](https://github.com/iri-pycpt/notebooks/releases)
listed 2.10.4 as the latest released notebook/environment set when checked.

## Tested software and evidence

| Component | Tested version |
| --- | --- |
| Python | 3.12.5 |
| PyCPT conda package / runtime version | 2.10.4 |
| cptio | 1.4.0 |
| Packaged CPT engine | 17.8.3 |
| Separately compiled CPT engine | 19.2.6 |
| Successful source-build compiler | gfortran 16.2.0 |

PyCPT's Python distribution metadata reports `2.10.4.dev0` in this released
environment; the conda package and runtime `__version__` report 2.10.4. The sibling
source checkout reports 2.10.5dev and is not the installed runtime tested here.

Evidence retained in this repository:

- [Installed package locks and result matrix](../../environment/verification-2026-10-31.json), including executable hashes.
- [Installation instructions](RUNTIME_DEVELOPMENT_NOTES.md), including exact build and environment commands.
- [Synthetic execution check](../../scripts/check_cpt.py), using a 2-by-3 grid, 31 hindcast years, and one forecast year.
- [Diagnostic-only menu adaptation](../../temp/cpt19-menu-check.py); installed Python packages were not modified.
- [Detailed installation notes](../../temp/cpt-installation-detail.md), including Debian log/output locations.

## Installation failures and confirmed fixes

| Failure | Diagnosis | Applied fix / result |
| --- | --- | --- |
| `./sfmakedepend: not found` | The executable helper existed, but its Perl shebang ended in CRLF, making the interpreter path invalid | Preserve the original helper, convert it to LF, regenerate `srcdeps` |
| `data_numbers.mod` missing | Dependency generation had failed before compilation | Regenerating dependencies resolves the initial ordering failure |
| Compiler segmentation fault in `cpt_file.F95` | Reproduced with gfortran 14.2.0 and 13.4.0; backtrace was in overloaded-operator resolution | Isolated gfortran 16.2.0 compiled it successfully; no scientific source routines changed |
| CPT could not open its labels file after `make install` | The install rule requested absent `data/labels.txt`, but the program reads `data/labels.toml`; the tar pipeline masked the missing-file error | Back up the Makefile; install `labels.toml` and the required CPTDM configuration |

Disabling optimization and increasing the compiler stack limit did not resolve
the compiler crash. These results establish a working toolchain on this machine,
not a universal compiler requirement for every CPT installation.

The default bundled LAPACK build also launches its full upstream test build.
Required BLAS/LAPACK archives were built; the extra test build was stopped and
the archives reused to link CPT. The full LAPACK suite was not completed.

Startup and About report CPT 19.2.6. Its linked runtime libraries resolve from
the `cpt-build` environment, which must be retained for this executable.

## Compatibility test results

| Engine and interface | Initialization coordinate S | CCA | PCR |
| --- | --- | --- | --- |
| CPT 17.8.3 + unmodified PyCPT 2.10.4 | Present on predictors | Pass | Pass |
| CPT 19.2.6 + unmodified PyCPT 2.10.4 | Present on predictors | Fail at skill-menu option 15 | Fail at skill-menu option 15 |
| CPT 19.2.6 + diagnostic score mapping | Present on predictors | Fail parsing initialization date | Not separately tested after this adaptation |
| CPT 19.2.6 + diagnostic score mapping | Omitted | Pass | Pass |

Successful checks verify finite deterministic forecasts/probabilities, correct
training and forecast years, probability totals, parsed outputs, and NetCDF writes.
They do not verify regional skill, full operational notebooks, live downloads,
every validation mode, all CPT methods, or other operating systems.

### Changed score-menu meanings

The observed cross-validated skill menu uses these IDs:

| Statistic requested by PyCPT | PyCPT 2.10.4 command | CPT 19.2.6 command | Meaning of the old command in CPT 19.2.6 |
| --- | --- | --- | --- |
| Pearson correlation | 1 | 1 | Pearson correlation |
| Spearman correlation | 2 | 2 | Spearman correlation |
| Two-alternative forced choice | 3 | 6 | Spearman's adjusted correlation |
| Root mean squared error | 7 | 10 | Percentage variance |
| ROC area below normal | 15 | 13 | No such option in the observed menu |
| ROC area above normal | 16 | 14 | No such option in the observed menu |

The invalid ROC command makes the current workflow fail. The still-valid old
commands are equally important: changing only the crashing commands could leave
incorrect statistics labelled as 2AFC or RMSE. Validation must check what was
calculated, not just whether the process finished or a file appeared.

These are the observed IDs for this menu and version. Other menus, including
probabilistic verification and other validation modes, still require an audit.

### Initialization-date representation

With score IDs adapted, the test reached output parsing and encountered:

```text
Timestamp missing T: 2012-09
```

CPT 19 wrote `cpt:S=2012-09`, while this cptio reader expects a complete timestamp
such as `2012-09-01T00:00`. Omission of S allowed the diagnostic to finish; it is
not an acceptable general fix for production forecasts.

A proper update should preserve the original forecast initialization coordinates
and validate their alignment with the returned forecast. It must distinguish
monthly shorthand from full timestamps. It must not silently assign day 1 to
every month-only output, especially when handling daily subseasonal initializations.

## Proposed compatibility update

Keep this work isolated from the tested tutorial environment. A future patch can
be developed in a separate checkout/environment and retain the existing public
Python workflow where supported.

| Work | Likely code areas, using the reviewed source layout |
| --- | --- |
| Identify the executable version and select tested menu mappings; reject unsupported combinations clearly | `pycpt/src/cptcore/base.py`, `utilities.py`, and functional wrappers |
| Audit score/output/configuration menus used by supported workflows, including silent meaning changes | `pycpt/src/cptcore/functional/cca.py`, `pcr.py`, verification wrappers |
| Handle output dates without losing initialization or target information | `cpt-io/src/cptio/fileio/cpt.py` and forecast-coordinate reconstruction in wrappers |
| Verify semantics and preserve existing supported behavior | Existing core tests plus recorded CPT 17/CPT 19 fixtures and integration checks |
| Ship a reproducible binary/environment and documented support matrix | CPT packaging recipe, activation scripts, notebook release locks and setup guide |

Compatibility with existing PyCPT features does not automatically expose every
CPT 19 feature. For example, the reviewed high-level subseasonal workflow rejects
PCR separately from the engine-version issue. New functionality needs its own design.

Suggested acceptance criteria:

1. The same supported Python calls run against both tested engines without manual monkey-patches.
2. Version and menu selection are explicit, with clear failures for unsupported versions.
3. Each exported statistic has the correct meaning and expected units; reference checks use the matching native CPT version.
4. Initialization dates, target periods, lead conventions, calendars and categories survive parsing and export.
5. Cross-validation, double cross-validation and retroactive paths are tested where supported; probability provenance is explicit.
6. Seasonal CCA/PCR work on at least one real archived case, followed by daily/lead-specific subseasonal cases and an MME workflow.
7. CPT 17 regression checks pass; deterministic differences between engine versions are investigated rather than assuming identical results.
8. A clean Debian environment can install the selected packages and execute the supported notebook path.

Windows/macOS packaging, station data, MLR, transformations and other optional
features need additional coverage before being included in a broad support claim.

## Effort assessment

These are rough engineering estimates based on two confirmed blockers and a
successful limited diagnostic, not measured commitments or an exhaustive audit.
One experienced developer is assumed, with working archived datasets available.

| Scope | Indicative focused effort | What the result would establish |
| --- | --- | --- |
| Limited seasonal prototype | 2–4 working days | Version-aware score mappings, initialization handling, and CCA/PCR integration checks for the small test cases |
| Debian seasonal support suitable for this tutorial | Approximately 1–2 working weeks total | Audited main paths, real-case validation, CPT 17 regression checks, reproducible setup and documentation |
| Broader seasonal/subseasonal support | Several weeks; allow roughly 3–6 weeks total as an initial planning range | More validation modes, daily leads, ensembles, probability outputs, packaging and regression coverage |

Cross-platform releases, upstream review, restricted-data access, and previously
unseen interface changes can extend those ranges. The first prototype should be
used to revise the estimate. A rewrite is not indicated by the current evidence;
testing and preserving scientific meaning are likely to dominate the work.

Recommendation: keep the tutorial moving with the verified environment, and treat
CPT 19.2.6 compatibility as a bounded parallel workstream if adopted. Begin with
seasonal CCA/PCR, then extend the supported scope only as its checks pass.

## Packaged CPT17 multi-forecast initialization dates

The all-season cross-year pilot exposed a separate issue in the working stack:
packaged CPT17.8.3 wrote a probability-output header containing
`cpt:S=2020-11-01`, while cptio1.4.0's timestamp reader requires a `T` time
delimiter. The underlying date matches the independently audited DJF2021
initialization, 1 November2020 at midnight.

`pycpt_tutorial/cpt_dates.py` provides a scoped reader around the specific
cptcore CCA/PCR call. It adds `T00:00` only to date-only initialization fields
already present in the audited input calendar. Unexpected dates and non-midnight
assumptions are rejected. Raw output text is retained; normalization copies,
dates and hashes are recorded in each fit manifest. Numerical data and target
bounds are unchanged. Five parser contract tests cover these rules, including
initialization fields at the end of a header line.

The original reader is restored on exit, and installed library files are not
modified. The all-season runner also independently checks returned initialization,
target-start and target-end arrays. This narrow CPT17/cptio parsing fix does not
implement the proposed CPT19 menu/protocol adapter.
