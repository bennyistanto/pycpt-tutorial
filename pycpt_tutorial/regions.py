"""Province-weighted views of existing coarse-grid forecast errors."""
import numpy as np
import xarray as xr


def score_regions(forecast, observed, region_weight):
    """Score the same cell errors with region weights; never average RMSEs.

    Weights need not be normalized. All positively weighted cells must be finite
    for every supplied forecast/observation; missing support is an error.
    """
    forecast, observed, region_weight = xr.align(forecast, observed, region_weight, join="exact")
    if bool((region_weight < 0).any()) or not bool(np.isfinite(region_weight).all()):
        raise ValueError("Region weights must be finite and nonnegative")
    mass = region_weight.sum(("Y", "X"))
    if bool((mass <= 0).any()):
        raise ValueError("Every scored region needs positive support")
    error = forecast - observed
    support = region_weight.sum("region") > 0
    if bool((~np.isfinite(error) & support).any()):
        raise ValueError("A positively weighted forecast or observation is missing")
    normalized = region_weight / mass
    error = error.where(support, 0)
    result = xr.Dataset({"mse": (error**2 * normalized).sum(("Y", "X")),
                         "mae": (abs(error) * normalized).sum(("Y", "X")),
                         "bias": (error * normalized).sum(("Y", "X"))})
    result["rmse"] = np.sqrt(result.mse)
    for name in result:
        result[name].attrs["units"] = "mm2" if name == "mse" else "mm"
    return result


def pool_years(annual, dim="season_year"):
    """Equal-year pooling with complete annual data, squaring before averaging."""
    if any(bool((~np.isfinite(annual[v])).any()) for v in ("mse", "mae", "bias")):
        raise ValueError("Pooling requires complete annual scores")
    pooled = annual[["mse", "mae", "bias"]].mean(dim, keep_attrs=True)
    pooled["rmse"] = np.sqrt(pooled.mse)
    pooled.rmse.attrs["units"] = "mm"
    return pooled
