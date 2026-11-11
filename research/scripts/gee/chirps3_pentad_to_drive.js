/* Paste this complete file into https://code.earthengine.google.com/.
 * CHIRPS v3.0 PENTAD totals for the Indonesia box: one GeoTIFF per year, ONE PENTAD PER BAND
 * (72 bands, named pYYYYMMDD by the pentad's first day), plus one CSV manifest per year listing
 * every image's ID, start, end, and its year/month/pentad properties, so the pentad calendar can
 * be checked rather than assumed.
 * Creates task definitions only. Start exports yourself in the Tasks panel.
 * Grid: the collection's own projection (as the daily script), clipped to the same box, so the
 * pentad and daily files line up pixel for pixel. Version: 2026-11-11-p1.
 */

var CONFIG = {
  years: [2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009,
          2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2023],   // cases' training years + 2023
  bbox: [94, -12, 142, 7],               // west, south, east, north: same box as the daily export
  driveFolder: 'pycpt_CHIRPS3_IDN_pentad',
  createTasks: true,                     // false = check and print only
  noData: -9999
};

var COLLECTION = 'UCSB-CHC/CHIRPS/V3/PENTAD';
var VERSION = '2026-11-11-p1';
var aoi = ee.Geometry.Rectangle(CONFIG.bbox, null, false);
var collection = ee.ImageCollection(COLLECTION);

// Native grid of the collection (checked once; every export uses it)
var projection = collection.first().projection().getInfo();
if (projection.crs !== 'EPSG:4326' || !projection.transform || Math.abs(projection.transform[0] - 0.05) > 1e-9) {
  throw new Error('Unexpected native grid: ' + JSON.stringify(projection));
}
print('Native grid:', projection);
print('Collection range:', collection.aggregate_min('system:time_start'), collection.aggregate_max('system:time_start'));

function pad(n) { return (n < 10 ? '0' : '') + n; }

CONFIG.years.forEach(function(year) {
  var start = ee.Date.fromYMD(year, 1, 1), end = ee.Date.fromYMD(year + 1, 1, 1);
  var images = collection.filterDate(start, end).sort('system:time_start');
  var info = images.map(function(img) {
    return ee.Feature(null, {
      id: img.id(), start: ee.Date(img.get('system:time_start')).format('YYYY-MM-dd'),
      end: ee.Date(img.get('system:time_end')).format('YYYY-MM-dd'),
      year: img.get('year'), month: img.get('month'), pentad: img.get('pentad'),
      crs: img.projection().crs(), script_version: VERSION
    });
  });
  var starts = info.aggregate_array('start').getInfo();
  if (starts.length !== 72) { throw new Error(year + ': expected 72 pentads, found ' + starts.length); }
  var names = starts.map(function(d) { return 'p' + d.replace(/-/g, ''); });
  var key = 'chirps3_pentad_idn_bbox_' + year;
  print(year + ': ' + starts.length + ' pentads, first ' + starts[0] + ', last ' + starts[starts.length - 1]);
  if (!CONFIG.createTasks) { return; }
  var image = images.select('precipitation').toBands().rename(names).toFloat().clip(aoi)
    .unmask({value: CONFIG.noData, sameFootprint: false});
  Export.image.toDrive({
    image: image, description: key, fileNamePrefix: key, folder: CONFIG.driveFolder,
    region: aoi, crs: projection.crs, crsTransform: projection.transform,
    maxPixels: 1e10, fileFormat: 'GeoTIFF', formatOptions: {cloudOptimized: true, noData: CONFIG.noData}
  });
  Export.table.toDrive({
    collection: ee.FeatureCollection(info), description: key + '_manifest', fileNamePrefix: key + '_manifest',
    folder: CONFIG.driveFolder, fileFormat: 'CSV',
    selectors: ['id', 'start', 'end', 'year', 'month', 'pentad', 'crs', 'script_version']
  });
});
print('Tasks created: ' + (CONFIG.createTasks ? 2 * CONFIG.years.length : 0) +
      '. Start them in the Tasks panel, then move the files to H:/temp/chirps/pentad/pycpt_CHIRPS3_IDN_pentad/.');
