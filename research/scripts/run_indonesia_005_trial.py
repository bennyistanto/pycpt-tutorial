"""Trial: OND 2023 CCA/PCR with the CHIRPS v3.0 predictand at native 0.05 degree vs 0.25 degree.

Same predictor (PyCPT-downloaded CFSv2, Learn PyCPT chapter 2), same settings
(CCA 3/3/2, PCR 3, cyclic cross-validation window 5, 1991-2020), same CHIRPS v3.0
archive and Indonesia boundary as chapter 3. Only the predictand resolution differs.

Records runtime and peak memory of each fit, then compares the two on a common grid:
the 0.05-degree results are aggregated to the 0.25-degree cells with the tutorial's
country-land rule and scored against the same observations as the 0.25-degree fit.

    python research/scripts/run_indonesia_005_trial.py

Outputs: research/cases/indonesia-ond-2023-005deg-trial/ (summary JSON and small
NetCDFs). Native CPT session files stay in ~/pycpt-005-trial (not in the repository).
"""
from pathlib import Path
import datetime as dt
import json
import resource
import shutil
import sys
import time

import numpy as np
import pandas as pd
import shapely
import xarray as xr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pycpt_tutorial.country_grid import aggregate_country_rainfall
from pycpt_tutorial.export import save_netcdf

SOURCE = Path("/mnt/e/temp/chirps/rolling_dekad/wld_cli_chirps3_month3_bydekad_1981_2025.nc")
DOMAIN = Path.home() / "PyCPT/indonesia-ond-2023-sep-init/85W-155E_to_-20S-20N"
OUT = ROOT / "research/cases/indonesia-ond-2023-005deg-trial"
SCRATCH = Path.home() / "pycpt-005-trial"
BOX = {"west": 94, "east": 142, "south": -12, "north": 7}
TRAIN = list(range(1991, 2021))
SETTINGS = dict(x_eof_modes=(3, 3), validation="CROSSVALIDATION", crossvalidation_window=5,
                synchronous_predictors=True, transform_predictand=None, tailoring=None,
                drymask_threshold=None, skillmask_threshold=None)
CCA_SETTINGS = dict(SETTINGS, y_eof_modes=(3, 3), cca_modes=(2, 2))


def log(*args):
    print(dt.datetime.now().strftime("%H:%M:%S"), *args, flush=True)


def country_mask(lat, lon):
    import cartopy.io.shapereader as shapereader
    records = shapereader.Reader(shapereader.natural_earth("10m", "cultural", "admin_0_countries")).records()
    geometry = next(r.geometry for r in records if r.attributes["ADM0_A3"] == "IDN")
    shapely.prepare(geometry)
    lon2d, lat2d = np.meshgrid(lon, lat)
    return xr.DataArray(shapely.contains_xy(geometry, lon2d, lat2d), dims=("lat", "lon"),
                        coords={"lat": lat, "lon": lon})


def build_observations(model_time):
    years = TRAIN + [2023]
    with xr.open_dataset(SOURCE) as source:
        times = pd.DatetimeIndex(source.time.values)
        stamps = [int(np.flatnonzero((times.year == y) & (times.month == 12) & (times.day == 21))[0]) for y in years]
        bounds = source.time_bnds.isel(time=stamps).values
        assert all(pd.Timestamp(b[0]) == pd.Timestamp(f"{y}-10-01") and pd.Timestamp(b[1]) == pd.Timestamp(f"{y + 1}-01-01")
                   for y, b in zip(years, bounds))
        native = (source.precip.sel(lon=slice(BOX["west"], BOX["east"]), lat=slice(BOX["south"], BOX["north"]))
                  .isel(time=stamps).load())
    country = country_mask(native.lat, native.lon)
    inside = native.where(country)
    train = inside.isel(time=slice(0, 30))
    complete = train.notnull().all("time")
    # CHIRPS stores 0.05-degree centres in single precision (6.975 as 6.97499847). CPT writes
    # them back rounded, and cptcore's snap_to then fails near the equator, so use the exact
    # centres (multiples of 0.05 offset by 0.025), rounded to 3 decimals.
    y005 = xr.DataArray(train.where(complete).values, dims=("T", "Y", "X"),
                        coords={"T": model_time["T"].values, "Y": np.round(native.lat.values.astype(float), 3),
                                "X": np.round(native.lon.values.astype(float), 3)})
    y005 = y005.assign_coords(Ti=("T", model_time["Ti"].values), Tf=("T", model_time["Tf"].values))
    y005 = y005.sortby("Y", ascending=False).rename("precipitation")
    y005.attrs = {"units": "mm", "missing": -999.0, "long_name": "CHIRPS v3.0 OND total, Indonesia land pixels, 0.05 degree"}
    obs2023 = inside.isel(time=30, drop=True)
    return y005, obs2023, country, int(country.sum()), int(complete.sum())


def fit(method, X, Y, F, label):
    from cptcore import canonical_correlation_analysis, principal_components_regression
    folder = SCRATCH / label
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    function, settings = ((canonical_correlation_analysis, CCA_SETTINGS) if method == "cca"
                          else (principal_components_regression, SETTINGS))
    log("fitting", label)
    start = time.monotonic()
    result = function(X, Y, F=F, **settings, cpt_kwargs={"outputdir": folder})
    elapsed = time.monotonic() - start
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    size = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
    log("done", label, f"{elapsed:.0f} s")
    return result, {"seconds": round(elapsed, 1), "largest_child_process_rss_mb_so_far": round(usage.ru_maxrss / 1024, 1),
                    "python_rss_mb_so_far": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
                    "cpt_output_folder_mb": round(size / 1e6, 1)}


def to_quarter(field, country):
    """Aggregate a 0.05-degree (Y, X) field to 0.25-degree cells with the tutorial's country-land rule."""
    values = field.rename({"Y": "lat", "X": "lon"}).sortby("lat").reindex(
        lat=country.lat, lon=country.lon, method="nearest", tolerance=1e-3)
    block = aggregate_country_rainfall(values, country, 5, minimum_coverage=.99).precipitation
    return block.rename({"lat": "Y", "lon": "X"}).assign_coords(
        Y=BOX["south"] + .125 + np.arange(76) * .25, X=BOX["west"] + .125 + np.arange(192) * .25).sortby("Y", ascending=False)


def scores(hindcast, forecast, y025, obs2023, cells):
    weights = np.cos(np.deg2rad(y025["Y"])) * cells
    error = (hindcast - y025).where(cells)
    a, b = hindcast - hindcast.mean("T"), y025 - y025.mean("T")
    pearson = ((a * b).sum("T") / np.sqrt((a * a).sum("T") * (b * b).sum("T"))).where(cells)
    e23 = (forecast - obs2023).where(cells)
    return {"cv_rmse_mm": float(np.sqrt((error ** 2).weighted(weights).mean(("Y", "X")).mean("T"))),
            "median_cell_pearson_cv": float(pearson.median()),
            "rmse_2023_mm": float(np.sqrt((e23 ** 2).weighted(weights).mean(("Y", "X"))))}


def clean(a):
    return a.where(a > -999)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    X = xr.open_dataset(DOMAIN / "data/CFSv2.PRCP.nc").prec.load()
    F = xr.open_dataset(DOMAIN / "data/CFSv2.PRCP_f2023.nc").prec.load()
    y025 = xr.open_dataset(DOMAIN / "data/local-CHIRPS3-OND-1991-2020.nc").precipitation.load()
    log("building 0.05-degree observations")
    y005, obs2023_005, country, country_pixels, complete_pixels = build_observations(X)
    log("pixels in Indonesia", country_pixels, "complete in all 30 seasons", complete_pixels)

    context = xr.open_dataset(ROOT / "docs/data/fitting-2023/comparison-context.nc")
    obs2023_025 = context.observed_rainfall.sel(season="OND").reset_coords(drop=True)
    cells = y025.notnull().all("T")
    obs_check = to_quarter(y005, country)
    obs_gap = float(np.nanmax(np.abs((obs_check - y025.transpose("T", "Y", "X")).where(cells))))
    log("0.05 observations aggregated back to 0.25, largest difference from the chapter 3 file:", obs_gap)

    record = {"date": dt.date.today().isoformat(), "predictor": "CFSv2.PRCP from PyCPT download_data (Learn PyCPT chapter 2)",
              "settings": {"cca": {k: str(v) for k, v in CCA_SETTINGS.items()}, "pcr": {k: str(v) for k, v in SETTINGS.items()}},
              "indonesia_pixels_0p05": country_pixels, "complete_pixels_0p05": complete_pixels,
              "cells_0p25": int(cells.sum()), "aggregation_check_max_abs_mm": obs_gap, "fits": {}, "common_grid": {}}
    keep = {}
    for method in ["cca", "pcr"]:
        res025, use025 = fit(method, X, y025, F, f"{method}-0p25")
        res005, use005 = fit(method, X, y005, F, f"{method}-0p05")
        record["fits"][f"{method}_0p25"] = use025
        record["fits"][f"{method}_0p05"] = use005
        h025 = clean(res025[0].deterministic).reindex(X=y025.X, Y=y025.Y, method="nearest", tolerance=1e-3)
        f025 = clean(res025[1].deterministic).isel(T=0, drop=True).reindex(X=y025.X, Y=y025.Y, method="nearest", tolerance=1e-3)
        h005 = clean(res005[0].deterministic)
        f005 = clean(res005[1].deterministic).isel(T=0, drop=True)
        h005_q = xr.concat([to_quarter(h005.isel(T=i, drop=True), country) for i in range(h005.sizes["T"])],
                           dim=y025["T"]).transpose("T", "Y", "X")
        f005_q = to_quarter(f005, country)
        native_pearson = {"0p25_cells": float(clean(res025[2].pearson).median()),
                          "0p05_pixels": float(clean(res005[2].pearson).median())}
        record["common_grid"][method] = {
            "fit_at_0p25": scores(h025.reset_coords(drop=True), f025.reset_coords(drop=True), y025.reset_coords(drop=True), obs2023_025, cells),
            "fit_at_0p05_aggregated_to_0p25": scores(h005_q.reset_coords(drop=True), f005_q.reset_coords(drop=True), y025.reset_coords(drop=True), obs2023_025, cells),
            "max_abs_difference_2023_forecast_mm": float(np.nanmax(np.abs((f005_q - f025).where(cells)))),
            "median_cpt_pearson_native_scale": native_pearson,
        }
        log(method, json.dumps(record["common_grid"][method]))
        keep[method] = (f005, clean(res005[1].probabilistic).isel(T=0, drop=True), f005_q, f025)

    ds = xr.Dataset({f"{m}_forecast_0p05": keep[m][0].reset_coords(drop=True) for m in keep})
    for m in keep:
        ds[f"{m}_probabilistic_0p05"] = keep[m][1].reset_coords(drop=True)
    ds["observed_2023_0p05"] = obs2023_005.rename({"lat": "Y", "lon": "X"}).sortby("Y", ascending=False).reindex(
        Y=ds.Y, X=ds.X, method="nearest", tolerance=1e-3)
    save_netcdf(ds, OUT / "forecast-2023-0p05.nc", overwrite=True,
                metadata={"note": "OND 2023 forecasts from fits with a 0.05-degree predictand; trial, not a tutorial result"})
    common = xr.Dataset({f"{m}_forecast_0p05_aggregated": keep[m][2].reset_coords(drop=True) for m in keep})
    for m in keep:
        common[f"{m}_forecast_0p25"] = keep[m][3].reset_coords(drop=True)
    save_netcdf(common, OUT / "forecast-2023-common-0p25.nc", overwrite=True)
    (OUT / "trial.json").write_text(json.dumps(record, indent=2) + "\n")
    log("written", OUT)


if __name__ == "__main__":
    main()
