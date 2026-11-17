"""Country-land rainfall aggregation using explicit native-pixel area weights."""
import numpy as np
import xarray as xr


def aggregate_country_rainfall(values, country_mask, factor, minimum_coverage=.99):
    """Average native rainfall over country pixels, preserving zeros and missingness.

    ``values`` and the Boolean ``country_mask`` use lat/lon coordinates. Each
    factor-by-factor block is a weighted mean, never a spatial rainfall sum.
    Weights approximate native-pixel areas with cosine(latitude). The coverage
    rule refers to valid country-land weight, not the whole bounding rectangle.
    """
    if type(factor) is not int or factor < 1:
        raise ValueError("factor must be a positive integer")
    if not 0 < minimum_coverage <= 1:
        raise ValueError("minimum_coverage must be in (0,1]")
    values, country_mask = xr.align(values, country_mask, join="exact")
    blocks=dict(lat=factor,lon=factor,boundary="exact")
    weights=country_mask.astype(float)*np.cos(np.deg2rad(values.lat))
    country_weight=weights.coarsen(**blocks).sum()
    valid_weight=weights.where(values.notnull(),0).coarsen(**blocks).sum()
    numerator=(values.fillna(0)*weights).coarsen(**blocks).sum()
    coverage=valid_weight/country_weight
    average=(numerator/valid_weight).where((country_weight>0)&(coverage>=minimum_coverage))
    return xr.Dataset({"precipitation":average,"valid_land_weight":valid_weight,
                       "country_land_weight":country_weight,
                       "indonesia_fraction":country_mask.astype(float).coarsen(**blocks).mean()})


def training_complete_mask(rainfall, years):
    """Select cells using training-year availability only; verification years cannot fit this mask."""
    selected=rainfall.sel(T=rainfall["T"].dt.year.isin(years))
    np.testing.assert_array_equal(selected["T"].dt.year,np.asarray(years))
    return selected.notnull().all("T")


def read_provinces(path):
    """Read a province shapefile as (name, geometry) pairs, unsimplified; the name field is ``a1name``."""
    import shapefile
    from shapely.geometry import shape

    reader = shapefile.Reader(str(path), encoding="utf-8")
    try:
        provinces = [(sr.record.as_dict()["a1name"], shape(sr.shape.__geo_interface__)) for sr in reader.iterShapeRecords()]
    finally:
        reader.close()
    if not provinces or not all(geometry.is_valid for _, geometry in provinces):
        raise ValueError("Province geometries must be present and valid")
    return provinces


def touching_pixels(lon, lat, provinces):
    """Pixels of a regular lon/lat grid that overlap any province, and the province each belongs to.

    A pixel is kept when any part of its box touches a province polygon, so coastal pixels and
    islands smaller than a pixel are included. ``label`` is the index of the province with the
    largest overlap area in the pixel (-1 where no province touches it).
    """
    import shapely

    lon, lat = np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)
    step_x, step_y = float(np.abs(np.diff(lon)).mean()), float(np.abs(np.diff(lat)).mean())
    lon2d, lat2d = np.meshgrid(lon, lat)
    boxes = shapely.box(lon2d - step_x / 2, lat2d - step_y / 2, lon2d + step_x / 2, lat2d + step_y / 2).ravel()
    tree = shapely.STRtree(boxes)
    # Overlap area of every (pixel, province) pair. A province is handled polygon by polygon (an
    # island at a time): pixels wholly inside a polygon need no geometry, the others are intersected
    # with that one polygon only.
    area = {}
    for index, (_, geometry) in enumerate(provinces):
        for part in getattr(geometry, "geoms", [geometry]):
            hit = tree.query(part, predicate="intersects")
            if hit.size == 0:
                continue
            inside = tree.query(part, predicate="contains_properly")
            partial = np.setdiff1d(hit, inside, assume_unique=True)
            overlap = np.maximum(shapely.area(shapely.intersection(part, boxes[partial])), 1e-300) if partial.size else np.empty(0)
            for pixels, values in ((inside, np.full(inside.size, step_x * step_y)), (partial, overlap)):   # touching along an edge still counts
                for pixel, value in zip(pixels.tolist(), values.tolist()):
                    area[pixel, index] = area.get((pixel, index), 0.0) + value
    best = np.zeros(boxes.size)
    label = np.full(boxes.size, -1, dtype=np.int16)
    for (pixel, index), value in area.items():
        if value > best[pixel]:
            best[pixel], label[pixel] = value, index
    shape2d = lon2d.shape
    return (label >= 0).reshape(shape2d), label.reshape(shape2d)
