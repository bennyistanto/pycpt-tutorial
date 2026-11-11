# Regional daily CHIRPS3 exports from Earth Engine

Use [chirps3_daily_to_drive.js](chirps3_daily_to_drive.js) in the
[Earth Engine Code Editor](https://code.earthengine.google.com/).
This is source preparation, separate from PyCPT fitting: regional Drive exports
instead of downloading global files. The script runs only in your own Earth Engine
session. The pilot and the `proposed` cohorts were exported with version 1 (files on
`H:/temp/chirps/daily/`, 3 November 2026); their values have not yet been compared
with the CHC files.

## Whole record: the `full` preset (version 2026-11-11-v2)

`preset: 'full'` exports each variant's whole Earth Engine record, rnl from its first
day (1981) and sat from its first day (1998), up to the last day each collection holds,
which the script reads at run time. Days already exported are skipped through
`CONFIG.alreadyExported`, which by default lists the `proposed` cohorts already on
`H:/temp/chirps/daily/` (1 January 2000 to 22 January 2019 and 11 January 2023 to
27 January 2026). The remaining jobs fill the gaps exactly, including the partial edge
months (for example `..._20000101_20000111.tif` next to the existing
`..._20000112_20000131.tif`).

Run one year at a time: `years: [1981]`, then `[1982]`, and so on. Years before 1998 have
rnl only (12 tasks), so two of them fit in one run (`years: [1981, 1982]`). Years that
need both variants have 24 tasks. Years whose days are all already exported stop with
"No dates match". After the tasks finish, move the files from Drive into the matching
folders under `H:/temp/chirps/daily/` (`pycpt_CHIRPS3_IDN_rnl`, `_sat`, `_manifest`)
and delete them from Drive.

## First run: the comparison pilot

1. Paste the complete JavaScript file into a new Code Editor script.
2. Keep `preset: 'pilot'`, both variants and the Indonesia bounding box.
3. Click **Run**. Wait for the Console's daily inventory check to finish.
4. If it passes, the **Tasks** panel receives **six image task definitions and
   one CSV manifest task**. Start those tasks in the panel. Creating definitions
   does not start the exports automatically.
5. Keep the TIFFs and CSV together after downloading from Drive. We will compare
   the pilot with the existing CHC Final daily inputs before using GEE in bulk.

The pilot uses exactly the already prepared daily reference dates:

| Input check | Daily interval, start inclusive / end exclusive | Monthly chunks per variant |
| --- | --- | ---: |
| Hindcast2018-08-29 | 2018-09-05 / 2018-09-26 | 1 |
| Forecast2023-08-24 | 2023-08-31 / 2023-09-21 | 2 |

That is42 daily bands per variant /84 total, split into six TIFFs. These are
daily observations; the script does **not** sum months or weeks. Monthly files
are simply containers of at most31 daily bands. Each band has a name such as
`d20230901`; the CSV supplies the authoritative band-number/date/source-ID map.

## Full proposed experiment, one observation year per batch

After the pilot is verified, change these settings:

```javascript
preset: 'proposed',
years: [2000],
months: null,
```

Repeat for observation years2000 through2019, then2023 through2026. The preset
restricts the first/last years to the exact requested dates, so2019 and2026 only
contain the required part of January. The `years` filter refers to **observation
dates**, not forecast initialization years. Keep the January spillover batches.

| Initialization cohort | Required daily observations, inclusive |
| --- | --- |
| Wednesday hindcasts2000–2018 | 2000-01-12–2019-01-22 |
| Wednesday archived forecasts2023–2025 | 2023-01-11–2026-01-27 |

This is8,064 days per variant, matching both verified wget lists exactly.
Across all years there are532 monthly image tasks, plus a manifest task for
each batch. A full observation year produces at most24 image tasks for both
variants. The default `maxImageTasks: 24` is a script batching guard, not a
claimed Earth Engine service quota. It prevents accidentally defining the
whole archive in one run. Use `months: [9]`, for example, to repeat only September.
Set `createTasks: false` for an inventory-only preview.

For other dates, use `preset: 'custom'`, edit `customRanges`, and set `years` and
`months` as needed. Each range is `[start, endExclusive]`. Overlapping ranges,
invalid dates and empty batches are rejected.

## AOI, grid, units and missing data

Default AOI: **94–142°E, 12°S–7°N**, the same observation rectangle as our input
adapter. It includes Indonesia, ocean and some neighbouring land. It is a
bounding-box subset, not a country-only mask. Apply our verified Indonesia
geometry locally later; this avoids importing a different administrative mask.
To change it, edit `CONFIG.bbox` and `aoiTag`. For a polygon, replace the marked
`var aoi = ...` line with an imported/drawn `ee.Geometry` and change the tag.

The official [rnl catalog](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHC_CHIRPS_V3_DAILY_RNL)
and [sat catalog](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHC_CHIRPS_V3_DAILY_SAT)
both identify a `precipitation` band in `mm/d`, at0.05degree. The script retains
each daily value numerically as the depth for that UTC day; it does not multiply
by86,400. Native projection metadata is read from the selected collection and
passed through `crs` plus `crsTransform`. **No arbitrary metre scale, spatial
aggregation, interpolation or weekly accumulation is applied.**

Google documents that `scale` alone can shift an output grid; native CRS and
affine alignment are therefore used. See the
[export guide](https://developers.google.com/earth-engine/guides/exporting_images).
Projection orientation/spacing and every selected image's CRS/transform are
checked before task definitions. The exported grid still needs comparison with
our raw CHC grid, including any extra edge pixels caused by bounding-box snapping.

The output is float32 GeoTIFF with cloud-optimized layout. Missing pixels are
encoded as **−9999**, also declared as GeoTIFF nodata; valid zeros remain zero.
Daily temporal labels are retained. The CSV stores UTC start/end bounds, GEE
source IDs, source units, native affine transform and script version. Its first
row also contains actual AOI GeoJSON and configuration JSON; retain the full CSV.
Band descriptions should be checked after download rather than relying only on
the TIFF filename. Keep all files if an export is spatially split.

For the default bbox, the complete two-variant array contains approximately
23.5GB of uncompressed float32 pixel values before compression, overviews and
possible grid-edge padding. This is not a promise of Drive file size.

Drive outputs use folders with these literal names:

- `pycpt_CHIRPS3_IDN_rnl`
- `pycpt_CHIRPS3_IDN_sat`
- `pycpt_CHIRPS3_IDN_manifest`

Change `driveFolderPrefix` if desired; use a unique folder name, not a slash
path. Existing duplicate Drive folder names can affect routing. See Google's
[Drive export reference](https://developers.google.com/earth-engine/apidocs/export-image-todrive).
Avoid rerunning completed batches unnecessarily; task/file prefixes are
deterministic but exporting again does not implement local wget continuation.

## What is checked and what remains

Before any task definitions, the script obtains a sorted date/source/grid
inventory for every selected monthly chunk. A missing day, duplicate date,
non-midnight timestamp, unexpected CRS or within-variant projection change
stops the inventory gate. It never fills in a missing daily image or silently
shortens a month. Pixel-level missingness and rainfall values are **not**
certified by this metadata check.

The code was syntax-checked locally. Its offline planner exactly reproduces
the pilot's84 daily bands and all16,128 proposed variant/date pairs from our
saved URL lists; leap days, year filters and rejection of bad inventories were
also checked. Evidence:
[gee-script-verification.json](../../audits/gefs-input-adapter/gee-script-verification.json).
The [offline check](../../../temp/check-gee-export-plan.cjs) is a development
artifact, not a substitute for executing Earth Engine exports.

The catalog's coverage descriptions do not establish byte-for-byte equivalence
with CHC Final TIFFs. In particular, the GEE SAT catalog uses a near-real-time
title; **do not assume GEE and our CHC Final source are identical without the
pilot comparison**. Check actual values, dates, masks, native grid and units
for both references. The GEE export script has not yet been authenticated/run,
nor has a GEE raster been compared locally. No model fits have run.

The existing input reader currently expects global daily TIFFs (or its own
country caches). Regional monthly multi-band GEE exports require a separate
reader using this CSV; **do not pass these files to the global-TIFF crop reader**.
That adaptation and full-cohort pixel QC come after the pilot is available.

API contracts checked2026-11-02:
[toBands](https://developers.google.com/earth-engine/apidocs/ee-imagecollection-tobands),
[filterDate](https://developers.google.com/earth-engine/apidocs/ee-imagecollection-filterdate),
[unmask](https://developers.google.com/earth-engine/apidocs/ee-image-unmask),
[projection transform (WKT)](https://developers.google.com/earth-engine/apidocs/ee-projection-transform).

## Pentad totals: `chirps3_pentad_to_drive.js` (version 2026-11-11-p1)

CHC builds daily CHIRPS v3.0 by sharing each pentad's amount between its days with
ERA5 (`rnl`) or IMERG (`sat`) timing, and recommends pentadal or longer totals
wherever the science allows ([daily readme](https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/readme.txt)).
This script exports the pentad product itself, `UCSB-CHC/CHIRPS/V3/PENTAD`: one
GeoTIFF per year (72 bands named `pYYYYMMDD` by the pentad's first day) on the same
native grid and box as the daily export, plus one CSV manifest per year with each
image's ID, start, end, year, month and pentad number. Set `CONFIG.years`, run, and
start the tasks in the Tasks panel.

`research/scripts/gee_pentad_to_netcdf.py` converts the files to yearly NetCDF and
checks them. For the 2000-2018 and 2023 exports: 72 pentads per year in date order;
Earth Engine stores each pentad's end as the day after it and numbers pentads 1-6
within the month; the grid equals the daily export's. In the pentad notebook, two
pentads add up exactly to the local dekadal archive, and summed daily `rnl` values
equal the pentad product to within 0.0001 mm.

