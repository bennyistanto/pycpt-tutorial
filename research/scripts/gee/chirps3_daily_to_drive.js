/* Paste this complete file into https://code.earthengine.google.com/.
 * Monthly multi-band GeoTIFFs: ONE DAILY VALUE PER BAND, no temporal sum.
 * Default pilot overlaps our previously downloaded CHC daily inputs.
 * Creates task definitions only. Start exports yourself in the Tasks panel.
 * Reference/instructions: README.md beside this file. Version: 2026-11-02-v1.
 */

var CONFIG = {
  preset: 'pilot',                 // 'pilot', 'proposed', or 'custom'
  variants: ['rnl', 'sat'],
  years: null,                     // For proposed: [2000], then [2001], etc.
  months: null,                    // Optional [1, 2, ...]; null = all selected months
  customRanges: [['2023-01-01', '2024-01-01']], // End dates EXCLUSIVE
  bbox: [94, -12, 142, 7],          // west, south, east, north; includes Indonesia
  aoiTag: 'idn_bbox',
  driveFolderPrefix: 'pycpt_CHIRPS3_IDN', // Unique folder name, not a path
  createTasks: true,               // false = inventory check / preview only
  maxImageTasks: 24,                // Local batch guard; not a GEE quota
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

// Client-side planning: reusable without Earth Engine for independent date checks.
function makeJobs(config) {
  var ranges = config.preset === 'custom' ? config.customRanges : PRESETS[config.preset];
  if (!ranges || !ranges.length) { throw new Error('Choose pilot, proposed or custom ranges.'); }
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
  ranges = ranges.slice().sort(function(a, b) { return a[0].localeCompare(b[0]); });
  var previousEnd = null;
  ranges.forEach(function(r) {
    if (r.length !== 2 || parseDate(r[0]) >= parseDate(r[1]) || (previousEnd && r[0] < previousEnd)) {
      throw new Error('Ranges must be increasing and nonoverlapping.');
    }
    previousEnd = r[1];
  });
  var jobs = [];
  config.variants.forEach(function(variant) {
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
  if (!jobs.length) { throw new Error('No dates match the selected batch.'); }
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

function runEarthEngine() {
  var jobs = makeJobs(CONFIG);
  print('Monthly image tasks in this batch:', jobs.length);
  print('Batch:', jobs.map(function(j) { return [j.variant, j.start, j.end, j.dates.length]; }));
  if (CONFIG.createTasks && jobs.length > CONFIG.maxImageTasks) {
    throw new Error('Select CONFIG.years (for example [2000]) or months; batch exceeds maxImageTasks.');
  }
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
      CONFIG.variants.forEach(function(variant) {
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
            script_version: '2026-11-02-v1'
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
      print('Pilot outputs still need local comparison with our CHC TIFF inputs before bulk use.');
    } catch (problem) {
      print('Stopped:', String(problem));
      print('If a task-definition error occurred after inventory validation, inspect Tasks for partial definitions.');
    }
  });
}

// Node exposes only planning/validation helpers; Earth Engine runs the exporter.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {CONFIG: CONFIG, makeJobs: makeJobs, validateInventory: validateInventory,
    checkNativeProjection: checkNativeProjection};
} else {
  runEarthEngine();
}
