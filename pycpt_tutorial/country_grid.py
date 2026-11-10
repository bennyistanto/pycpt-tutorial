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
