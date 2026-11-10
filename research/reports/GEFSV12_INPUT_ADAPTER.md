# GEFSv12 / CHIRPS3 Indonesia input adapter

**Acquisition follow-up, 2026-11-02:** the user prefers regional Earth Engine
exports. The [GEE script](../scripts/gee/README.md) preserves daily bands on the
native grid and creates Drive task definitions after a date/grid inventory gate.
Offline planning checks pass; live export and comparison with these CHC Final
inputs are pending. Regional multi-band exports need a separate local reader.

**Verified 2026-11-02. Input preparation only; zero fits.** The user selected
CHIRPS3 **rnl as primary**, with **sat as a reference sensitivity check**.
Neither completed seasonal tutorial nor installed PyCPT/CPT libraries changed.
Dark-mode surfaces were separately changed to neutral black/charcoal in
`docs/styles/`; scientific colour scales remain unchanged.

## Executed scope

The [adapter](../../pycpt_tutorial/subseasonal_inputs.py) and
[runner](../scripts/prepare_gefs_indonesia_inputs.py) prepare calendar-based inputs
without importing PyCPT/cptcore/cptdl, launching CPT, or reading an IRIDL key.
The runner blocks those imports and subprocess launches. Actual source requests
succeeded without application-supplied credentials.

Two bounded checks exercised both archive branches. These are engineering checks,
**not selected forecast-skill cases**:

| Branch / initialization, 00 UTC | Members retained | CHIRPS daily dates used, inclusive | Targets |
| --- | ---: | --- | --- |
| Hindcast / 2018-08-29 | 11, IDs 0–10 | 2018-09-05–2018-09-25 | Weeks 2, 3, 4 |
| Forecast / 2023-08-24 | 31, IDs 0–30 | 2023-08-31–2023-09-20 | Weeks 2, 3, 4 |

All 21 daily lead slots, members and model points in 94–143°E, 12°S–7°N are
finite/nonnegative: **882,000 daily values**, yielding 126,000 member/week/grid
values. The deterministic mean equally weights all members. There is no lagged
ensemble, climatology subtraction or fitted mask.

GEFS remains on its actual **1° grid** (20 × 50 rectangle points). CHIRPS3 is read
at 0.05° and aggregated to country portions of **0.25° cells**. A fine observation
grid does not increase model resolution. Raw-model regridding for future matched
scores remains a separate analysis decision, not an already executed comparison.

## Unit and UTC contract

| Input | Actual returned units / interpretation | Conversion to weekly mm |
| --- | --- | --- |
| IRI GEFSv12_CPC weekly hindcast | `kg m-2`, daily amount | Sum seven amounts, factor 1 |
| IRI GEFSv12_CPC forecast | `kg m-2 s-1`, daily mean rate | Each day × 86,400 seconds; sum seven |
| CHIRPS3 Final rnl / sat | Daily rainfall depth, mm | Decode −9999 as missing; sum seven complete days |

The hindcast's `standard_name=precipitation_flux` conflicts with its amount units.
The adapter checks the actual branch/unit contract and rejects unknown units. It
does not multiply hindcast amounts by seconds, difference a cumulative series,
clip negatives or sum an incomplete week. Model lead coordinates must be opened
with `decode_timedelta=False` so numeric days remain days.

| Lead | Half-open elapsed UTC interval | Daily midpoint L values |
| --- | --- | --- |
| Week 2 | [initialization + 7 days, +14 days) | 7.5, …, 13.5 |
| Week 3 | [+14 days, +21 days) | 14.5, …, 20.5 |
| Week 4 | [+21 days, +28 days) | 21.5, …, 27.5 |

Week 2 of the 2023-08-24 forecast is **August 31 00 UTC to September 7 00 UTC**,
excluding the end; CHIRPS filenames are August 31–September 6. This corrects the
earlier readiness prototype's **provisional one-day-later selection**, L8.5–14.5.
Its historical sample files remain unchanged and are not aligned verification
inputs. Every new NetCDF records real initialization and target bounds; no
synthetic 1700 dates are used.

SubX's published daily convention is 00–00 UTC; see section 2 of
[L’Heureux, Tippett & Becker (2021)](https://repository.library.noaa.gov/view/noaa/60112/noaa_60112_DS1.pdf).
The [CHIRPS daily documentation](https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/readme.txt)
defines UTC date labels for disaggregation while warning that contributing
station windows vary. We use these labels without an Indonesian local-time shift.

A [provider-side numerical check](../audits/gefs-input-adapter/provider-integration.json)
compared week 2 with IRI's independent lead-average × duration reduction for all
11,000 hindcast and 31,000 forecast member/grid values. Maximum differences:
**0.000020385 mm** and **0 mm**, respectively. This verifies integration, not an
independent reconstruction from NOAA's sub-daily GRIBs. Source responses/hashes
are cached. The historical [IRI dictionary](https://iri.columbia.edu/~awr/pycpt/html/pycpt_dict.html)
also averages daily leads; its old rate description does not override current
hindcast amount units.

## Country support and reference sensitivity

The copied [country boundary](../audits/gefs-input-adapter/inputs/indonesia_boundary.geojson)
has SHA-256 `1b44b1d7e0ab4e7e3eff0efd9e0bff74c45ad7a390114e80b64b5369b51f4e78`.
Polygon containment at native pixel centres gives **61,192 country pixels** and
**3,242 country-containing 0.25° cells**. The older seasonal `native-membership.nc`
already contains a seasonal evaluation mask; it was deliberately not reused.

Each native pixel needs all seven days before summation. Then cosine-latitude
weighted 5 × 5 block means yield rainfall depth over each cell's country portion.
At least 99% of that cell's country weight must have complete observations.
This is an area mean of depths, not a spatial sum of millimetres. No zero filling.

All twelve reference/week combinations retain **3,240 cells**, representing
**99.996726%** of static country weight. Two single country pixels lack data in
both variants throughout these checks:

| Native centre (°E, °N) | Containing cell centre (°E, °N) |
| --- | --- |
| 107.775, 3.025 | 107.875, 3.125 |
| 120.625, 1.075 | 120.625, 1.125 |

Those cells remain NaN. Full Indonesia is the intended domain; **100% observed
coverage is not claimed**. Other dates may have additional gaps. A full-cohort
training mask and fixed comparison support remain future work.

rnl and sat share pentad totals, with ERA5 and IMERG daily allocation respectively.
They are **not independent observations**. The unweighted mean absolute difference
over retained cell/week pairs is 5.753 mm (hindcast targets), 5.442 mm (forecast
targets); maxima are 73.306 and 137.231 mm. These describe reference sensitivity,
not forecast error. Seven-day windows can split pentads. CHC gives no universal
variant preference; rnl-primary is our project design, not its recommendation.

## Outputs and evidence

Seven compressed NetCDFs (about 1.74 MB total):

- [Country grid / weights](../audits/gefs-input-adapter/outputs/indonesia-country-grid.nc)
- [GEFS hindcast](../audits/gefs-input-adapter/outputs/gefs-hindcast-2018-08-29-weeks234.nc)
- [GEFS forecast](../audits/gefs-input-adapter/outputs/gefs-forecast-2023-08-24-weeks234.nc)
- [rnl hindcast targets](../audits/gefs-input-adapter/outputs/chirps3-rnl-hindcast-2018-08-29-weeks234.nc)
- [sat hindcast targets](../audits/gefs-input-adapter/outputs/chirps3-sat-hindcast-2018-08-29-weeks234.nc)
- [rnl forecast targets](../audits/gefs-input-adapter/outputs/chirps3-rnl-forecast-2023-08-24-weeks234.nc)
- [sat forecast targets](../audits/gefs-input-adapter/outputs/chirps3-sat-forecast-2023-08-24-weeks234.nc)

The [manifest](../audits/gefs-input-adapter/preparation.json) records source URLs,
global TIFF hashes/bytes, 84 daily country-cache hashes, code identity, units,
members, exact dates and coverage. Raw models/country daily caches remain in
ignored `temp/gefs-input-adapter/`. Global TIFFs were streamed, reduced and
discarded except two earlier readiness samples. Final cache-only preparation
downloaded zero bytes. Source TIFF bodies represented total 1.440 GB; initial
transfer was 1.406 GB after reusing those samples.

The [offline verifier](../scripts/verify_gefs_indonesia_inputs.py) independently
recomputes every weekly model sum and weighted observation amount with NumPy,
checks identities/hashes and blocks network requests. Its
[PASS record](../audits/gefs-input-adapter/verification.json) also confirms
51 case-one files, seven notebook/kit/logo files and 30 case-two NetCDFs unchanged.
All **35 tests pass**, including ten scientific adapter tests for date shifts,
leap/year boundaries, missing days/members, units, dry zeros and spatial weighting.
No packages were installed and no fits ran.

Run from the repo root in the pinned Debian environment:

```bash
# Dry plan; no downloads or fits.
python research/scripts/prepare_gefs_indonesia_inputs.py
# Bounded examples, using resumable caches.
python research/scripts/prepare_gefs_indonesia_inputs.py --prepare
# Explicit dates; omit --prepare to inspect the plan first.
python research/scripts/prepare_gefs_indonesia_inputs.py \
  --hindcast-date 2018-08-29 --forecast-date 2023-08-24
python research/scripts/verify_gefs_indonesia_inputs.py
python research/scripts/propose_gefs_periods.py
```

Initial preparation uses the pinned native country-boundary path; its copied
geometry supports verification. `--refresh-derived` only replaces this adapter
audit's derived outputs; use after an intentional adapter change. Normal cached
reruns verify existing content. The IRI CHIRPS3 interface checked here exposed
monthly data, without a discovered daily regional route; this adapter therefore
uses public CHC daily TIFFs and retains only country pixels locally.

## Proposed periods — not selected or fitted

The [proposal](../audits/gefs-input-adapter/period-proposal.json) is derived from
the saved coordinate census, not assumed year ranges.

| Role | Proposed initialization years | Coordinate starts |
| --- | --- | ---: |
| Initial training candidate | 2000–2009 | 522 before target purge |
| Expanding annual validation | 2010–2018 | 469 over nine future years |
| Final training after freezing design | 2000–2018 | 991 |
| Archived forecast verification | Wednesdays, 2023–2025 | 157 (52 / 52 / 53) |

2000 follows the period explicitly covered by
[NOAA's reforecast documentation](https://noaa-gefs-retrospective.s3.amazonaws.com/Description_of_reforecast_data.pdf).
Exclude the earlier IRI segment until its provenance is resolved. 2018 is the
last complete initialization year in this IRI branch; 2019 ends in August.
NOAA's native sub-daily GRIB and IRI's processed daily 1° archive are distinct
products; this adapter has not reconstructed the latter.

At each annual validation cutoff, use earlier years only and remove training
rows whose week-4 target ends after January 1 of that validation year. Use the
same retained starts at all leads. For 2010, four December 2009 starts are purged,
leaving **518** training starts; the latest target ends December 30, 2009.
Weekly rows are not independent years.

Use training-only calendar-season climatologies, anomalies, masks, scaling and
EOFs with separate lead models. Mode/window tuning needs inner time-block
validation with overlap purges; freeze it before outer-year scoring. Compare raw,
climatology and calibration on identical targets/support; additionally compare
leads on matched target weeks from different issues, so different rainfall
events are not mistaken for a lead effect. Quantify uncertainty by year/time
blocks. This proposed design is not automatically supplied by seasonal CV options.

CHIRPS3 Final is retrospective, not the product vintage available at each issue.
Call this research verification, not an operational data-vintage replay. The last
2025 Wednesday is December 31: week 4 ends **2026-01-28 exclusive**. January 2026
observation filenames exist in the earlier census; their pixels are unchecked.

Before fitting: agree on design, check every proposed model field and observation
date/pixel, verify archive version consistency, freeze comparison support,
regridding/baselines and separately resolve the subseasonal fitter/calendar/PCR
limitations in the readiness report. Neither skill nor probability reliability
is established by these input checks.

Before bulk acquisition: the proposal requires **8,064 daily dates / 16,128 files**
for both references. Blindly scaling global TIFF downloads is approximately
**276.5 GB**, estimated from the pilot (580.6 GB at the per-file cap). Prefer a
regional daily source or a reviewed staged country-cache plan. The default
adapter remains bounded to two examples and does not fetch that archive.
