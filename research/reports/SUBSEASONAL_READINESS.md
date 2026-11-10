# Full-Indonesia subseasonal rainfall readiness audit

**Follow-up, 2026-11-02:** the user subsequently selected GEFSv12 and rnl-primary
with sat sensitivity. The [input-adapter report](GEFSV12_INPUT_ADAPTER.md) records
two prepared/verified examples, corrects the provisional lead selection below
by one day, and proposes periods before fits. This readiness evidence remains
a historical snapshot; its model samples are not aligned verification inputs.

**Checked 2026-11-02.** Several archives can support an Indonesia investigation,
but the installed PyCPT subseasonal prototype is **not ready to use unchanged**.
No model, forecast case or training period has been selected. No CPT fits ran.

This is a readiness audit, separate from the two completed seasonal tutorials.
It inventories model versions and coordinate coverage, reads bounded rainfall
samples, checks daily-observation availability and exercises downloader/API
compatibility without fitting. It does not certify every date, member or country
pixel in an entire training/verification archive.

## What was verified

| Check | Evidence and limit |
| --- | --- |
| Installed workflow | PyCPT Python metadata 2.10.4.dev0; actual subseasonal source is byte-identical to official release commit 084bb5c380c200b5f65f11ba224a965547b91da1 |
| Available archive families | Live IRI directories: 8 SubX providers / 17 model-version entries; 12 S2S provider directories |
| Coordinate coverage | 31 hindcast/forecast branch coordinate profiles decoded, with dates, members, lead slots and geographical grids |
| Model rainfall | Nine bounded NetCDF samples over 94–143°E, 12°S–7°N; this rectangle encloses Indonesia and also contains neighbouring land and ocean |
| Observations | Actual CHIRPS3 daily filename sequences and two readable global daily GeoTIFFs, one per variant |
| Compatibility | Installed function bodies exercised with networking, parsing and fitting stubbed; concrete fresh-download/PCR/raw-branch issues reproduced |
| Preservation | Seasonal notebook, kit and scientific output checks remain unchanged; no installed-package edits |

The [complete model table](../audits/subseasonal-readiness/model-table.md) and
[machine-readable availability CSV](../audits/subseasonal-readiness/model-availability.csv)
contain all 17 SubX entries, including legacy versions. Different directory
entries are not necessarily independent models. Coordinate slots are not counts
of usable, independent forecasts.

## Model choices and actual archive coverage

The following are **live IRI coordinate ranges**, not a promised common training
period. Partial first/last years must be handled explicitly. All listed grids
enclose Indonesia; this is distinct from confirming complete rainfall values.

| SubX model/version | Hindcast coordinate range | HC / FC member slots | Forecast coordinate range | Grid |
| --- | --- | ---: | --- | ---: |
| GEFSv12_CPC | 1989-01-04–2019-08-28 | 11 / 31 | 2022-04-02–2026-10-31 | 1° |
| CFSv2 | 1999-01-01–2017-09-30 | 1 / 4 | 2017-10-15–2026-11-01 | 1° |
| FIMr1p1 | 1999-01-06–2017-06-28 | 4 / 4 | 2017-08-02–2026-10-28 | 1° |
| GEPS7 | 2001-01-01–2020-12-31 | 4 / 21 | 2021-12-02–2024-06-06 | 1° |
| GEPS8 | 2001-01-01–2020-12-31 | 4 / 21 | 2024-06-13–2026-10-29 | 1° |
| GEOS_V3 | 1999-01-01–2024-08-29 | 15 / 15 | 2026-03-02–2026-10-28 | 0.5° |

Other profiled branches include GEM, GEPS5/6, GEOS_V2p1 and its five-day subset,
CCSM4, NESM, CESM30/46 and older GEFS paths. GEOS_V2p1 and CCSM4 have forecast
coordinate ranges spanning 2023. GEPS8 and the checked GEOS_V3 forecast branch
start later; they cannot simply be substituted into a 2023 operational replay.
The probed CESM forecast paths and one legacy GEFSv12 hindcast path returned 404;
those specific paths remain unresolved, rather than proving that no such data
exist elsewhere.

**Do not reuse 1991–2020 automatically.** None of the profiled SubX branches
provides that entire interval. GEFSv12_CPC has all Wednesday coordinate slots in
1989–2018, then only 35 starts in 2019. Its installed template further restricts
the data to 6 January 1999–28 June 2017. A full year of coordinates still does not
establish full fields or a homogeneous model archive.

NOAA's [GEFS reforecast description](https://noaa-gefs-retrospective.s3.amazonaws.com/Description_of_reforecast_data.pdf)
describes the 2000–2019 open-data collection and extended weekly runs. The
[31-year reforecast publication record](https://repository.library.noaa.gov/view/noaa/53301)
distinguishes the earlier initialization/reanalysis phase. The IRI subset, the
NOAA distribution and the template's date filter must not be treated as identical.

The older [IRI SubX guide](https://iri.columbia.edu/~awr/pycpt/html/SubX.html)
describes CFSv2, GEFS, FIM and ECCC workflows. That historical availability list
does not describe the current installed PyCPT2 selector: its actual subseasonal
dictionary contains only `GEFSv12.PRCP`.

### What the bounded rainfall samples revealed

- GEFS hindcast starts in 1989, 2000 and 2018: all 231,000 requested values per
  sample were finite, with 11 populated members and 21 lead slots. The separate
  June 2023 forecast sample had all 651,000 values finite and 31 populated members.
- CFSv2 and FIM sampled hindcasts were finite throughout the requested rectangle.
- GEPS7's first coordinate date, 2001-01-01, returned **all 84,000 values missing**.
  This is direct evidence that coordinate coverage cannot establish usable samples.
- GEPS8's sampled date was populated, but contained 775 negative rate values,
  down to approximately -3.66e-7 kg m-2 s-1. Their cause and treatment require an
  explicit check; they were not silently clipped.
- GEOS_V3's sampled first hindcast date populated only members 1–5 of 15 declared
  slots: 405,405 / 1,216,215 values finite. Ensemble membership changes need auditing.

These fixed dates are availability probes, not selected forecast examples or
evidence of forecast skill. No country-only score was calculated.

## S2S alternatives and access

IRI exposes provider directories for BoM, CMA, CNRM, ECCC, ECMF, HMCR, IAP-CAS,
ISAC, JMA, KMA, NCEP and UKMO. The ECMF directory separates CY41–47, CY48 and CY49.
The [live inventory](../audits/subseasonal-readiness/live-catalog.json) records
these exact names; archive labels must not be replaced with assumed versions.

The [ECMWF S2S model table](https://confluence.ecmwf.int/spaces/S2S/pages/40796876/Models)
provides model-specific reforecast periods, schedules and horizons. The common
atmospheric archive grid is 1.5°, apart from documented exceptions. The dedicated
[ECMWF model page](https://confluence.ecmwf.int/spaces/S2S/pages/47288128/ECMWF%2BModel)
lists CY50R1 from May 2026, whereas the summary table still lists CY49R1. It also
documents the June 2023 cycle/frequency change and rolling 20-year reforecasts.
Consequently, a historical case needs its own issue-date/cycle pairing.

The [ECCC page](https://confluence.ecmwf.int/spaces/S2S/pages/58146780/ECCC%2BModel)
distinguishes GEPS7 and GEPS8 and their changed schedules/horizons. The
[NCEP page](https://confluence.ecmwf.int/spaces/S2S/pages/47294070/NCEP%2BModel)
describes CFSv2 S2S reforecasts for 1999–2010; that period differs from the SubX
CFSv2 coordinates checked above. These are separate archive products.

**Field access is not established for ECMWF S2S.** Both probed CY48/CY49
precipitation metadata URLs redirected to `/auth/credential` despite the existing
native credential. This could require dataset authorization/credential handling;
the redirect does not establish the precise cause, variable availability or
missing years. No login, agreement acceptance, key rotation or access-setting
change was attempted. Directory visibility is not data access.

Conversely, the GEFSv12_CPC SubX DDS endpoint returned 200 **without a credential**.
Do not teach that every subseasonal dataset needs an IRIDL key. The other signed
SubX probes do not establish anonymous access for every model or full payload.

## Weekly leads and temporal alignment

The installed example describes calendar offsets relative to initialization:

| Label | First date offset | Last date offset, inclusive | Midpoint L slots used by the prototype |
| --- | ---: | ---: | --- |
| Week 1 | +1 day | +7 days | 1.5–7.5 |
| Week 2 | +8 days | +14 days | 8.5–14.5 |
| Week 3 | +15 days | +21 days | 15.5–21.5 |
| Week 4 | +22 days | +28 days | 22.5–28.5 |

For an initialization on 1 June, the prototype's Week 1 means 2–8 June; it does
not include 1 June. This convention is provisional for the new tutorial until
the source accumulation intervals and daily observation labels are reconciled.
Store start/end bounds explicitly, with an exclusive end bound in the new data
model, instead of relying on a week label alone.

GEFS hindcasts expose L=0.5…34.5, while the checked forecast branch exposes
1.5…34.5. The seven required slots for each of the four rows exist in both;
that does not justify requesting a fifth week by the same convention. The
[lead-slot CSV](../audits/subseasonal-readiness/weekly-lead-slots.csv) records
these checks for all profiled branches.

GEFS hindcast precipitation is labelled kg m-2, while its forecast and most
other checked sources are kg m-2 s-1. The sampled GEFS hindcasts vary up and down
between leads, so the samples do not support assuming simple cumulative totals
since initialization. Neither units nor half-day midpoint coordinates alone
fully specify the accumulation interval. Verify the conversion independently
before combining raw forecasts, observations or calibrated results.

## Daily observations for full Indonesia

| CHIRPS3 Final variant | Complete daily filename years checked | Latest files checked | Daily timing source |
| --- | --- | --- | --- |
| `rnl` | 1981–2025 | 2026-09-30 | ERA5 |
| `sat` | 1998–2025 | 2026-09-30 | IMERG Late V07 |

Every expected calendar date, including leap days, was found in those complete
years. The 2026 directories each contain 273 daily TIFFs. Empty 2027–2030
directories are placeholders, not evidence of future observations. This is
**filename continuity**, not all-date raster-pixel QC.

Both sampled 2023-09-01 files opened successfully: EPSG:4326, 7200×2400 cells,
approximately 0.05° spacing, covering the enclosing Indonesia rectangle. Each
had 105,063 finite nonnegative values in its 980×380 rectangle. No GDAL nodata
tag was present; -9999 values were recorded explicitly, rather than inventing
metadata. These counts include neighbouring land and are not the existing
country-mask support count.

The sample reader uses installed Pillow/NumPy rather than adding rasterio to the
pinned environment. Lead coordinates in model NetCDF samples are read with
`decode_timedelta=False` to retain explicit day values; otherwise xarray exposes
nanosecond timedeltas. Saved rainfall values and source files were not changed.

The [CHC daily-product documentation](https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/readme.txt)
explains that daily rainfall allocates a shared pentadal amount using ERA5 or
IMERG timing. There is no separate daily gauge-blending stage. The two variants
are therefore sensitivity references, not independent validation datasets.
Daily labels follow UTC disaggregation conventions; contributing station windows
can differ. The same document notes that CHIRPS2 daily uses CFSv2 and is being
retired. That dependence matters for a CFSv2 verification reference.

The [CHIRPS3 overview](https://www.chc.ucsb.edu/data/chirps3) documents the
underlying rainfall product and spatial coverage. The supplied local inputs are
dekadal/monthly products; no daily-labelled file was identified under the
provided CHIRPS root. Arbitrary seven-day totals cannot be reconstructed from
dekadal or monthly totals. A chosen daily source must be prepared separately.

NASA's [IMERG product page](https://gpm.nasa.gov/data/imerg) describes daily and
sub-daily alternatives and recommends the Final run for retrospective research.
An independent IMERG ingestion/access test was not performed here; it remains
an optional alternative, not a certified ready input.

## Installed PyCPT workflow: changes required before fitting

The [official pinned subseasonal source](https://github.com/iri-pycpt/pycpt/blob/084bb5c380c200b5f65f11ba224a965547b91da1/pycpt/src/pycpt/subseasonal.py)
is byte-identical to the installed file. This audit also reused the previously
pinned [example notebook](https://github.com/iri-pycpt/notebooks/blob/1c975316910b9e047ce685d9b8cdefb2c4b73551/Subseasonal/pycpt-s2s.ipynb).
It was not executed. The following are checked implementation facts:

1. The subseasonal dictionary has one GEFS precipitation model and one CHIRPS2
   observation mapping. Seasonal `cptdl.hindcasts` keys do not imply weekly support.
2. The fresh-download call omits `target`, but the installed `cptdl.download`
   applies a seasonal-month check requiring it. The isolated call reproduced
   `KeyError('target')` after the mocked parser boundary. Supplying a fake seasonal
   target would not constitute correct weekly validation.
3. The PCR branch explicitly raises “PCR not yet implemented for subseasonal”.
   The no-MOS branch reproduced an unbound-variable error. These are high-level
   driver limitations, not evidence that CPT/core PCR cannot fit weekly data.
4. All three downloader calls hardcode authentication off. A protected-data
   adapter needs explicit, tested authentication handling; the sampled anonymous
   GEFS metadata endpoint remains readable without a key.
5. The local-predictand example comment is not implemented by `download_data`.
   A new local CHIRPS3 preparation path is required.
6. The URL recipes subtract precomputed model/observed day-of-year climatologies,
   replace true sample dates with a synthetic monthly axis beginning in 1700,
   and multiply by a literal seven days even when another window length is given.
   Retain original issue/target dates separately; do not reuse the fixed multiplier
   for a 14-day target. Retroactive validation of anomalies needs a separate audit
   of which years contributed to those external climatologies.

The executable checks used actual installed function bodies, with all network,
parser and fitter boundaries stubbed. They establish those compatibility issues,
not a complete end-to-end test of all driver branches or any fitted output.
The installed environment and sibling reference checkout remain unchanged.

## Readiness decision and next gates

**Data candidates exist; the unchanged prototype is not ready for a full case.**
GEFS is closest to the existing subseasonal template. CFSv2, FIM, GEOS_V2p1 and
CCSM4 are other potential historical candidates, subject to input/membership QC
and an adapter. This is a shortlist for discussion, not a selection based on skill.

Before any fits:

1. Review the availability table and choose a model/version, issue-date cohort
   and feasible common years. Do not inherit seasonal 1991–2020 by default.
2. Build and verify an input-only adapter: source units/accumulation intervals,
   weekly bounds, true calendar coordinates, member handling, daily totals and
   full-country missing-data masks. Keep installed libraries untouched.
3. Audit every requested date/member/lead/country cell for that chosen cohort;
   the bounded samples here cannot substitute for that check.
4. Freeze validation by year/time blocks, with buffers for overlapping targets.
   Five weekly rows are not five years. Fit climatologies/preprocessing using
   training information only; do not tune settings on the verification outcomes.
5. Compare raw and training-only climatology on identical samples. Compare leads
   on matched target windows where schedules permit, and state differences when
   they do not. Add calibration only after the input/validation checks pass.

Use multiple years for skill estimation; a 2023 map can illustrate a result but
cannot establish skill across leads. Probabilistic reliability is a later, separate
validation task. Retain source grids and distinguish a 0.25° output grid from
independent dynamical forecast resolution.

## Evidence and reproduction

Evidence directory: [research/audits/subseasonal-readiness](../audits/subseasonal-readiness/).
Key records: `source-inventory.json`, `upstream-source.json`, `driver-checks.json`,
`live-catalog.json`, `model-grids.json`, `coordinates.json`, `field-samples.json`,
`s2s-metadata.json`, `anonymous-access.json`, `daily-observations.json`,
`daily-raster-samples.json` and `summary.json`. Some exploratory root DDS requests
timed out; successful field metadata and directory requests provide the reported
evidence. Unsupported ASCII projection requests were replaced with decoded DAP2
coordinate-only responses.

Scripts: [source/metadata audit](../scripts/audit_subseasonal_readiness.py),
[daily observations](../scripts/audit_daily_observation_availability.py),
[isolated driver checks](../scripts/check_subseasonal_driver_readiness.py),
and [table summarizer](../scripts/summarize_subseasonal_readiness.py).
The [offline verifier](../scripts/verify_subseasonal_readiness.py) reopens the nine
NetCDF samples, checks member/lead counts and masks, cross-checks daily indices
and raster hashes, and verifies preserved tutorial/style files. Its
[verification record](../audits/subseasonal-readiness/verification.json) passes.
Run them with the pinned Debian Python; network stages are explicit `--stage`
options. Observation indices and `--sample` are separate operations.
Do not rerun field downloads merely to read this report.

Only sanitized metadata/statistics/hashes are retained in durable evidence.
Raw model probes and public raster samples stay in ignored `temp/`; no raw model
data were added to learner downloads. Credentials stayed in the native Debian
file and were never printed or copied. No agreement was accepted, fits run,
notebooks executed, packages installed, files staged, commits made or site deployed.
