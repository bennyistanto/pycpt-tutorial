# Map boundary overlays

Display-only derivatives of the three shapefiles supplied by Benny Istanto:
`idn_bnd_adm0.shp`, `idn_bnd_adm1.shp` and `wld_bnd_adm0.shp`.
The Indonesia metadata credits Badan Informasi Geospasial, modified by Benny Istanto,
and describes the province dataset as 2022. The supplied province file contains
38 features; this overlay is a snapshot, not a claim about current official limits.

The WGS84 geometries are simplified at 0.01° with topology preservation and clipped
to 94–142°E, 12°S–7°N. World features with `iso_3=IDN` are excluded from grey fills.
Invalid geometries, if encountered, are repaired in the display derivative with
Shapely `make_valid`; the stage and validity reason are recorded in provenance.
Indonesia is drawn with no fill, a country outline and thin province outlines.
The pale background indicates ocean; grey land indicates other countries.

These layers do not define the evaluation mask, weights or any scientific score.
`provenance.json` records source checksums, metadata credits and output checksums.
Regenerate with `python scripts/prepare_tutorial_boundaries.py --source-dir PATH`
in the pinned Debian environment. Reading the original shapefiles requires pyshp
and shapely, already present there; plotting uses the included GeoJSON and Matplotlib.
