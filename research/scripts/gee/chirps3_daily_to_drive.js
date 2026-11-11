/* Paste this complete file into https://code.earthengine.google.com/.
 * Monthly multi-band GeoTIFFs: ONE DAILY VALUE PER BAND, no temporal sum.
 * Creates task definitions only. Start exports yourself in the Tasks panel.
 * Reference/instructions: README.md beside this file. Version: 2026-11-11-v2.
 *
 * Presets:
 *   'pilot'    six small images overlapping daily CHC inputs already prepared locally (run this first)
 *   'full'     the whole record of each variant: rnl from its first day (1981), sat from its first day
 *              (1998), both up to the latest day in the Earth Engine collection, read at run time
 *   'proposed' the GEFS training/forecast cohorts only (2000-2019 and 2023-2026)
 *   'custom'   CONFIG.customRanges
 * With 'full' and 'proposed', export one year per run: set CONFIG.years to [1981], then [1982], ...
 */

var CONFIG = {
  preset: 'pilot',                 // 'pilot', 'full', 'proposed' or 'custom'
  variants: ['rnl', 'sat'],        // sat has no data before 1998; years before 1998 export rnl only
  years: null,                     // 'full'/'proposed': one year per run, e.g. [1981]
  months: null,                    // Optional [1, 2, ...]; null = all selected months
  customRanges: [['2023-01-01', '2024-01-01']], // End dates EXCLUSIVE
  fullEnd: 'auto',                 // 'auto' = day after the collection's last image; or 'YYYY-MM-DD' (exclusive)
  // 'full' skips days already exported. The 'proposed' cohorts (incl. the pilot days) are on
  // H:/temp/chirps/daily as of 2026-11-11; set to [] to export everything.
  alreadyExported: [['2000-01-12', '2019-01-23'], ['2023-01-11', '2026-01-28']],
  bbox: [94, -12, 142, 7],          // west, south, east, north; includes Indonesia
  aoiTag: 'idn_bbox',
  driveFolderPrefix: 'pycpt_CHIRPS3_IDN', // Unique folder name, not a path
  createTasks: true,               // false = inventory check / preview only
  maxImageTasks: 24,                // Local batch guard (one year of both variants); not a GEE quota
  noData: -9999
};

var COLLECTIONS = {
  rnl: 'UCSB-CHC/CHIRPS/V3/DAILY_RNL',
  sat: 'UCSB-CHC/CHIRPS/V3/DAILY_SAT'
};
var PRESETS = {
  pilot: [['2018-09-05', '2018-09-26'], ['2023-08-31', '2023-09-21']],
  proposed: [['2000-01-12', '2019-01-23'], ['2023-01-11', '2026-01-28']]
};
var DAY_MS = 86400000;
var VERSION = '2026-11-11-v2';

function parseDate(text) {
  var d = new Date(text + 'T00:00:00Z');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text) || !isFinite(d.getTime()) || iso(d) !== text) {
    throw new Error('Invalid YYYY-MM-DD date: ' + text);
  }
  return d;
}
function iso(d) { return d.toISOString().slice(0, 10); }
function dayList(start, end) {
  var days = [];
  for (var t = parseDate(start).getTime(); t < parseDate(end).getTime(); t += DAY_MS) {
    days.push(iso(new Date(t)));
  }
  return days;
}

// Ranges for one variant. 'full' needs fullRanges = {rnl: [[start, end]], sat: [[start, end]]}
// (filled at run time from the collections' own first and last dates).
function rangesFor(config, variant, fullRanges) {
  if (config.preset === 'full') {
    if (!fullRanges || !fullRanges[variant]) { throw new Error('Full ranges unknown for ' + variant); }
    return subtractRanges(fullRanges[variant], config.alreadyExported || []);
  }
  return config.preset === 'custom' ? config.customRanges : PRESETS[config.preset];
}

// [start, end) ranges minus [start, end) holes; returns the remaining pieces in order.
function subtractRanges(ranges, holes) {
  var out = [];
  ranges.forEach(function(r) {
    var pieces = [[parseDate(r[0]).getTime(), parseDate(r[1]).getTime()]];
    holes.forEach(function(h) {
      var hs = parseDate(h[0]).getTime(), he = parseDate(h[1]).getTime(), next = [];
      pieces.forEach(function(p) {
        if (he <= p[0] || hs >= p[1]) { next.push(p); return; }
        if (hs > p[0]) { next.push([p[0], hs]); }
        if (he < p[1]) { next.push([he, p[1]]); }
      });
      pieces = next;
    });
    pieces.forEach(function(p) { out.push([iso(new Date(p[0])), iso(new Date(p[1]))]); });
  });
  return out;
}

// Client-side planning: reusable without Earth Engine for independent date checks.
function makeJobs(config, fullRanges) {
  if (['pilot', 'full', 'proposed', 'custom'].indexOf(config.preset) < 0) {
    throw new Error('Choose the pilot, full, proposed or custom preset.');
  }
  if (!config.variants.length || config.variants.some(function(v) { return !COLLECTIONS[v]; }) ||
      config.variants.length !== config.variants.filter(function(v, i, a) { return a.indexOf(v) === i; }).length) {
    throw new Error('Choose unique rnl/sat variants.');
  }
  if (!/^[A-Za-z0-9_-]+$/.test(config.aoiTag)) { throw new Error('Use a simple aoiTag.'); }
  ['years', 'months'].forEach(function(field) {
    if (config[field] !== null && (!Array.isArray(config[field]) || !config[field].length ||
        config[field].some(function(v) { return typeof v !== 'number' || Math.floor(v) !== v ||
          (field === 'months' && (v < 1 || v > 12)); }))) {
      throw new Error(field + ' must be null or a nonempty integer array.');
    }
  });
  var jobs = [];
  config.variants.forEach(function(variant) {
    var ranges = rangesFor(config, variant, fullRanges);
    if (!ranges || !ranges.length) { throw new Error('No ranges for ' + variant); }
    ranges = ranges.slice().sort(function(a, b) { return a[0].localeCompare(b[0]); });
    var previousEnd = null;
    ranges.forEach(function(r) {
      if (r.length !== 2 || parseDate(r[0]) >= parseDate(r[1]) || (previousEnd && r[0] < previousEnd)) {
        throw new Error('Ranges must be increasing and nonoverlapping.');
      }
      previousEnd = r[1];
    });
    ranges.forEach(function(r) {
      var cursor = parseDate(r[0]);
      var stop = parseDate(r[1]);
      while (cursor < stop) {
        var year = cursor.getUTCFullYear();
        var month = cursor.getUTCMonth() + 1;
        var nextMonth = new Date(Date.UTC(year, month, 1));
        var end = new Date(Math.min(nextMonth.getTime(), stop.getTime()));
        if ((!config.years || config.years.indexOf(year) >= 0) &&
            (!config.months || config.months.indexOf(month) >= 0)) {
          var startText = iso(cursor), endText = iso(end);
          var days = dayList(startText, endText);
          var name = 'chirps3_' + variant + '_' + config.aoiTag + '_' +
            startText.replace(/-/g, '') + '_' + days[days.length - 1].replace(/-/g, '');
          jobs.push({key: name, variant: variant, start: startText, end: endText, dates: days});
        }
        cursor = end;
      }
    });
  });
  if (!jobs.length) { throw new Error('No dates match the selected batch (for sat, no data before 1998).'); }
  return jobs;
}

// Fail BEFORE creating any task if a day is missing, duplicated or shifted.
function validateInventory(jobs, rows) {
  if (!rows || rows.length !== jobs.length) { throw new Error('Incomplete inventory response.'); }
  var gridByVariant = {};
  jobs.forEach(function(job, i) {
    var row = rows[i];
    if (row.key !== job.key || !row.times || row.times.length !== job.dates.length ||
        !row.ids || row.ids.length !== job.dates.length || !row.crs || !row.wkt ||
        row.crs.length !== job.dates.length || row.wkt.length !== job.dates.length) {
      throw new Error('Missing or unexpected daily records: ' + job.key);
    }
    row.times.forEach(function(ms, j) {
      if (typeof ms !== 'number' || ms % DAY_MS !== 0 || iso(new Date(ms)) !== job.dates[j] ||
          !row.ids[j] || row.crs[j] !== 'EPSG:4326') {
        throw new Error('Daily date, ID or CRS mismatch: ' + job.key + ' / ' + job.dates[j]);
      }
      if (!gridByVariant[job.variant]) { gridByVariant[job.variant] = row.wkt[j]; }
      if (!row.wkt[j] || row.wkt[j] !== gridByVariant[job.variant]) {
        throw new Error('Source projection changes within variant: ' + job.key);
      }
    });
  });
}

function checkNativeProjection(info) {
  var t = info.transform;
  if (info.crs !== 'EPSG:4326' || !t || t.length !== 6 ||
      Math.abs(Math.abs(t[0]) - 0.05) > 1e-7 || Math.abs(Math.abs(t[4]) - 0.05) > 1e-7 ||
      Math.abs(t[1]) > 1e-12 || Math.abs(t[3]) > 1e-12) {
    throw new Error('Unexpected source grid; inspect it rather than exporting with an assumed scale.');
  }
}

// 'full': read each collection's first and last daily timestamp (metadata only), then plan.
function withFullRanges(collections, callback) {
  if (CONFIG.preset !== 'full') { callback(null); return; }
  var bounds = {};
  CONFIG.variants.forEach(function(variant) {
    bounds[variant] = ee.List([collections[variant].aggregate_min('system:time_start'),
                               collections[variant].aggregate_max('system:time_start')]);
  });
  ee.Dictionary(bounds).evaluate(function(result, error) {
    if (error) { print('Could not read collection dates; NO export tasks created:', error); return; }
    var ranges = {};
    CONFIG.variants.forEach(function(variant) {
      var first = iso(new Date(result[variant][0]));
      var end = CONFIG.fullEnd === 'auto' ? iso(new Date(result[variant][1] + DAY_MS)) : CONFIG.fullEnd;
      ranges[variant] = [[first, end]];
      print(variant + ' record in Earth Engine: ' + first + ' to ' + iso(new Date(result[variant][1])) +
            (CONFIG.fullEnd === 'auto' ? '' : ' (export stops before ' + end + ')'));
    });
    callback(ranges);
  });
}

function runEarthEngine() {
  // For a different AOI, replace this line with an imported/drawn ee.Geometry.
  // Keep the bbox default for the tutorial; country masking happens locally.
  var aoi = ee.Geometry.Rectangle(CONFIG.bbox, 'EPSG:4326', false);
  Map.centerObject(aoi, 5);
  Map.addLayer(aoi, {color: '666666'}, 'Export AOI', true);
  var collections = {};
  CONFIG.variants.forEach(function(variant) {
    collections[variant] = ee.ImageCollection(COLLECTIONS[variant]).select('precipitation')
      .sort('system:time_start').map(function(image) {
        var projection = image.projection();
        return image.set('_export_crs', projection.crs()).set('_export_wkt', projection.transform());
      });
  });
  withFullRanges(collections, function(fullRanges) {
    var jobs;
    try { jobs = makeJobs(CONFIG, fullRanges); } catch (problem) { print('Stopped:', String(problem)); return; }
    print('Monthly image tasks in this batch:', jobs.length);
    print('Batch:', jobs.map(function(j) { return [j.variant, j.start, j.end, j.dates.length]; }));
    if (CONFIG.createTasks && jobs.length > CONFIG.maxImageTasks) {
      print('Stopped: select CONFIG.years (for example [1981]) or months; batch exceeds maxImageTasks.');
      return;
    }
    exportJobs(jobs, collections, aoi);
  });
}

function exportJobs(jobs, collections, aoi) {
  // Date/grid metadata only, not pixel arrays. One asynchronous inventory request.
  var inventory = jobs.map(function(job) {
    var c = collections[job.variant].filterDate(job.start, job.end);
    return ee.Dictionary({key: job.key,
      times: c.aggregate_array('system:time_start'), ids: c.aggregate_array('system:index'),
      crs: c.aggregate_array('_export_crs'), wkt: c.aggregate_array('_export_wkt')});
  });
  ee.List(inventory).evaluate(function(rows, error) {
    if (error) { print('Inventory failed; NO export tasks created:', error); return; }
    try {
      validateInventory(jobs, rows);
      var projections = {};
      jobs.map(function(j) { return j.variant; }).filter(function(v, i, a) { return a.indexOf(v) === i; })
        .forEach(function(variant) {
          var firstJob = jobs.filter(function(j) { return j.variant === variant; })[0];
          var reference = collections[variant].filterDate(firstJob.start, firstJob.end).first();
          // getInfo gives the actual six-element affine array; transform() is WKT.
          projections[variant] = ee.Image(reference).projection().getInfo();
          checkNativeProjection(projections[variant]);
        });
      print('PASS: every daily timestamp, source ID and per-variant grid checked.');
      print('Native export grids:', projections);
      if (!CONFIG.createTasks) { print('Preview only: no tasks created.'); return; }
      // Retain actual AOI in the manifest (first row), even if user edits it.
      var aoiJSON = JSON.stringify(aoi.getInfo());
      var manifest = [];
      jobs.forEach(function(job, i) {
        var projection = projections[job.variant];
        var names = job.dates.map(function(day) { return 'd' + day.replace(/-/g, ''); });
        var c = collections[job.variant].filterDate(job.start, job.end).sort('system:time_start');
        var image = c.toBands().rename(names).toFloat().clip(aoi)
          .unmask({value: CONFIG.noData, sameFootprint: false});
        Export.image.toDrive({
          image: image, description: job.key, fileNamePrefix: job.key,
          folder: CONFIG.driveFolderPrefix + '_' + job.variant,
          region: aoi, crs: projection.crs, crsTransform: projection.transform,
          maxPixels: 1e10, fileFormat: 'GeoTIFF',
          formatOptions: {cloudOptimized: true, noData: CONFIG.noData}
          // No scale/dimensions/resample/reduce: preserve the native source grid.
        });
        job.dates.forEach(function(day, bandIndex) {
          manifest.push(ee.Feature(null, {
            export_name: job.key, variant: job.variant, collection_id: COLLECTIONS[job.variant],
            date_utc: day, band_number: bandIndex + 1, band_name: names[bandIndex],
            source_index: rows[i].ids[bandIndex], source_time_ms: rows[i].times[bandIndex],
            interval_start_utc: day + 'T00:00:00Z',
            interval_end_utc: iso(new Date(parseDate(day).getTime() + DAY_MS)) + 'T00:00:00Z',
            catalog_units: 'mm/d', interpretation: 'one UTC daily rainfall depth; no numeric conversion',
            nodata: CONFIG.noData, crs: projection.crs, transform_json: JSON.stringify(projection.transform),
            aoi_tag: CONFIG.aoiTag, aoi_geojson: manifest.length === 0 ? aoiJSON : '',
            config_json: manifest.length === 0 ? JSON.stringify(CONFIG) : '',
            script_version: VERSION
          }));
        });
      });
      var manifestName = 'chirps3_manifest_' + CONFIG.aoiTag + '_' + CONFIG.preset + '_' +
        jobs[0].dates[0].replace(/-/g, '') + '_' +
        jobs[jobs.length - 1].dates.slice(-1)[0].replace(/-/g, '');
      Export.table.toDrive({collection: ee.FeatureCollection(manifest), description: manifestName,
        fileNamePrefix: manifestName, folder: CONFIG.driveFolderPrefix + '_manifest', fileFormat: 'CSV',
        selectors: ['export_name', 'variant', 'collection_id', 'date_utc', 'band_number', 'band_name',
          'source_index', 'source_time_ms', 'interval_start_utc', 'interval_end_utc', 'catalog_units',
          'interpretation', 'nodata', 'crs', 'transform_json', 'aoi_tag', 'aoi_geojson', 'config_json', 'script_version']});
      print('Created ' + jobs.length + ' image task definitions + 1 CSV manifest. Start them in Tasks.');
      print('Move finished files to H:/temp/chirps/daily/pycpt_CHIRPS3_IDN_{rnl,sat,manifest}/ and free the Drive space.');
    } catch (problem) {
      print('Stopped:', String(problem));
      print('If a task-definition error occurred after inventory validation, inspect Tasks for partial definitions.');
    }
  });
}

// Node exposes only planning/validation helpers; Earth Engine runs the exporter.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {CONFIG: CONFIG, makeJobs: makeJobs, validateInventory: validateInventory,
    checkNativeProjection: checkNativeProjection, rangesFor: rangesFor, subtractRanges: subtractRanges};
} else {
  runEarthEngine();
}
