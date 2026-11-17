"""Twelve seasons, 2021-2024, at CHIRPS v3.0's native 0.05 degree grid: observations, fits and scores.

The 0.25 degree benchmark (run_indonesia_all_seasons.py) stays as it is. This script repeats its
design on the native grid:

  * predictors: the audited CFSv2 seasonal totals of the 0.25 degree case, unchanged
    (~/CPT/cases/indonesia-all-seasons-2021-2024-025deg/<season>/predictors.nc);
  * observations: CHIRPS v3.0 three-month totals from the rolling archive, at every 0.05 degree
    pixel that touches Indonesia. "Indonesia" is the supplied 38-province boundary, unsimplified
    (about 19,000 polygons), so coastal pixels and small islands are kept;
  * masks: a pixel enters a fit when it has data in every training season and its training values
    are not all equal; scores use the pixels shared by all twelve seasons, both training periods
    and the four verification years;
  * fits: CCA (3 X EOFs, 3 Y EOFs, 2 modes) and PCR (3 X EOFs) through cptcore, for the training
    periods 1983-2010 and 1991-2020, each forecasting the ending years 2021-2024: 48 fits, one
    process each;
  * forecasts compared: raw CFSv2 (interpolated), the two climatologies, CCA and PCR for each
    period, with the same RMSE / MAE / bias definitions as the 0.25 degree case.

Each pixel also gets the province that covers most of it, for the province scores.

    python research/scripts/run_indonesia_all_seasons_005.py [--workers 16] [--seasons OND JJA]
    python research/scripts/run_indonesia_all_seasons_005.py --summarize-only

Working folder: ~/CPT/cases/indonesia-all-seasons-2021-2024-005deg. A finished fit is reused.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import multiprocessing
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

os.environ.setdefault("CPT_BIN_DIR", str(Path(sys.prefix) / "opt" / "cpt" / "bin"))
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from pycpt_tutorial.seasons import SEASONS, season_window
from pycpt_tutorial.country_grid import read_provinces, touching_pixels
from pycpt_tutorial.cpt_dates import verified_midnight_reader

SOURCE_CASE = Path.home() / "CPT/cases/indonesia-all-seasons-2021-2024-025deg"
ROOT = Path.home() / "CPT/cases/indonesia-all-seasons-2021-2024-005deg"
OUT = ROOT / "outputs"
CHIRPS = Path("/mnt/e/temp/chirps/rolling_dekad/wld_cli_chirps3_month3_bydekad_1981_2025.nc")
PROVINCES = Path("/mnt/f/temp/hybrid-bias-correction/data/subset/bnd/idn_bnd_adm1")
BOX = dict(west=94, east=142, south=-12, north=7)
ALL_YEARS = list(range(1983, 2025))
EVAL_YEARS = [2021, 2022, 2023, 2024]
PERIODS = {"1983_2010": list(range(1983, 2011)), "1991_2020": list(range(1991, 2021))}
VARIANTS = ("raw_cfsv2", "climatology_1983_2010", "climatology_1991_2020", "cca_1983_2010", "cca_1991_2020", "pcr_1983_2010", "pcr_1991_2020")
SETS = {"all_four_years": EVAL_YEARS, "additional_years": [2021, 2022, 2024]}
COMMON = dict(x_eof_modes=(3, 3), validation="CROSSVALIDATION", crossvalidation_window=5, synchronous_predictors=True,
              transform_predictand=None, tailoring=None, drymask_threshold=None, skillmask_threshold=None)
ENCODING = {"zlib": True, "complevel": 5, "dtype": "float32"}
META = {"case_id": ROOT.name, "year_convention": "Season ending year; NDJ/DJF start in the preceding year", "grid_resolution_degrees": 0.05,
        "pixel_rule": "Every native pixel with any overlap with the supplied 38-province boundary (unsimplified)",
        "model": "CFSv2 ensemble mean at 1 degree (audited inputs of the 0.25 degree case)", "observations": "CHIRPS v3.0 three-month totals, native grid",
        "validation_note": "Holdouts after the training targets; training-only masks; fixed mode counts; retrospective current-vintage data"}


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    with xr.open_dataset(path) as ds:
        return ds.load()


def save(ds, path, **attrs):
    ds = ds.copy()
    ds.attrs = {**META, **{k: str(v) for k, v in attrs.items()}}
    tmp = Path(str(path) + ".part")
    ds.to_netcdf(tmp, encoding={v: ENCODING for v in ds.data_vars if ds[v].dtype.kind == "f"})
    tmp.replace(path)


def prepare():
    """Pixel mask, province labels and observed seasonal totals for every season and year."""
    grid_file = ROOT / "grid.nc"
    if grid_file.exists() and all((ROOT / season / "observations.nc").exists() for season in SEASONS):
        return
    ROOT.mkdir(parents=True, exist_ok=True)
    provinces = read_provinces(PROVINCES)
    with xr.open_dataset(CHIRPS) as source:
        times = pd.DatetimeIndex(source.time.values)
        native = source.precip.sel(lon=slice(BOX["west"], BOX["east"]), lat=slice(BOX["south"], BOX["north"]))
        t0 = time.monotonic()
        touching, label = touching_pixels(native.lon.values, native.lat.values, provinces)
        print(f"pixels touching the {len(provinces)} provinces: {int(touching.sum()):,} ({time.monotonic() - t0:.0f} s)", flush=True)
        Y = np.round(native.lat.values.astype(float), 3)[::-1].copy()
        X = np.round(native.lon.values.astype(float), 3)
        to_grid = lambda a: xr.DataArray(np.asarray(a)[::-1].copy(), dims=("Y", "X"), coords={"Y": Y, "X": X})
        country = to_grid(touching)
        for season in SEASONS:
            model = read(SOURCE_CASE / season / "predictors.nc").precipitation
            np.testing.assert_array_equal(model.season_year, ALL_YEARS)
            fields = []
            for year in ALL_YEARS:
                window = season_window(season, year)
                index = np.flatnonzero((times.year == window.end.year) & (times.month == window.end.month) & (times.day == 21))
                assert index.size == 1, (season, year)
                bounds = source.time_bnds.isel(time=int(index[0])).values
                assert pd.Timestamp(bounds[0]) == pd.Timestamp(window.start) and pd.Timestamp(bounds[1]) == pd.Timestamp(window.end) + pd.Timedelta(days=1)
                values = native.isel(time=int(index[0])).load().values
                assert not (values < 0).any()
                fields.append(to_grid(values).where(country))
            rain = xr.concat(fields, dim=pd.Index(model["T"].values, name="T")).astype("float32")
            rain = rain.assign_coords(Ti=("T", model.Ti.values), Tf=("T", model.Tf.values), season_year=("T", ALL_YEARS)).rename("precipitation")
            rain.attrs = {"units": "mm", "missing": -999.0, "long_name": f"CHIRPS v3.0 {season} rainfall total, pixels touching Indonesia, native 0.05 degree"}
            masks = []
            for period, years in PERIODS.items():
                training = rain.sel(T=rain.season_year.isin(years))
                masks.append((training.notnull().all("T") & (training.std("T") > 0)).astype("int8"))
            analysis = xr.concat(masks, dim=pd.Index(list(PERIODS), name="training_period"))
            evaluation = analysis.astype(bool).all("training_period") & rain.sel(T=rain.season_year.isin(EVAL_YEARS)).notnull().all("T")
            (ROOT / season).mkdir(exist_ok=True)
            save(xr.Dataset({"precipitation": rain, "analysis_mask": analysis, "season_evaluation_mask": evaluation.astype("int8")}),
                 ROOT / season / "observations.nc", season=season)
            print(f"{season}: training pixels {[int(m.sum()) for m in masks]}, evaluation pixels {int(evaluation.sum()):,}", flush=True)
        common = xr.concat([read(ROOT / season / "observations.nc").season_evaluation_mask.astype(bool) for season in SEASONS], "season").all("season")
        weight = (np.cos(np.deg2rad(common["Y"])) * common).transpose("Y", "X")
        grid = xr.Dataset({"touching": country.astype("int8"), "province_index": to_grid(label).astype("int16"),
                           "evaluation_mask": common.astype("int8"), "evaluation_weight": weight},
                          coords={"province": [name for name, _ in provinces]})
        grid.attrs["province_rule"] = "The province covering the largest part of the pixel; -1 where no province touches it"
        grid.to_netcdf(grid_file)
        print(f"shared evaluation pixels: {int(common.sum()):,}", flush=True)


def fit(job):
    """One (season, method, period) fit. Returns a status record; never raises."""
    season, method, period = job
    key = f"{season}_{method}_{period}"
    record = {"season": season, "method": method, "training_period": period}
    result = ROOT / season / f"{method}_{period}.nc"
    t0 = time.monotonic()
    try:
        from cptcore import canonical_correlation_analysis, principal_components_regression

        if result.exists():
            with xr.open_dataset(result) as old:
                return dict(record, status="reused", seconds=float(old.attrs["fit_seconds"]), pixels=int(old.attrs["training_pixels"]))
        years = PERIODS[period]
        model = read(SOURCE_CASE / season / "predictors.nc").precipitation
        observed = read(ROOT / season / "observations.nc")
        mask = observed.analysis_mask.sel(training_period=period, drop=True).astype(bool)
        x = model.sel(T=model.season_year.isin(years)).drop_vars("season_year")
        y = observed.precipitation.sel(T=observed.season_year.isin(years)).where(mask).drop_vars("season_year").astype("float64")
        y.attrs = {"units": "mm", "missing": -999.0}
        f = model.sel(T=model.season_year.isin(EVAL_YEARS)).drop_vars("season_year")
        np.testing.assert_array_equal(x["T"], y["T"])
        windows = [season_window(season, year) for year in EVAL_YEARS]
        assert pd.Timestamp(y.Tf.max().item()) < min(w.initialization for w in windows)       # training ends before any forecast starts
        config = dict(COMMON)
        if method == "cca":
            config.update(y_eof_modes=(3, 3), cca_modes=(2, 2))
        function = canonical_correlation_analysis if method == "cca" else principal_components_regression
        expected = [pd.Timestamp(v).to_pydatetime() for v in np.concatenate([x.S.values, f.S.values])]
        workdir = ROOT / f"cpt-{key}"
        t1 = time.monotonic()
        with verified_midnight_reader(function, expected) as repairs:
            returned = function(x, y, F=f, **config, cpt_kwargs={"outputdir": workdir, "log": ROOT / f"cpt-{key}.log", "project_file": ROOT / f"cpt-{key}-commands.txt"})
        seconds = time.monotonic() - t1
        h, fc, skill = [ds.reindex(X=y.X, Y=y.Y, method="nearest", tolerance=1e-3).where(mask) for ds in returned[:3]]
        n = int(mask.sum())
        np.testing.assert_array_equal(fc.S, pd.to_datetime([w.initialization for w in windows]))
        np.testing.assert_array_equal(fc.Ti, pd.to_datetime([w.start for w in windows]))
        np.testing.assert_array_equal(fc.Tf, pd.to_datetime([w.end for w in windows]))
        assert int(h.deterministic.count()) == len(years) * n and int(fc.deterministic.count()) == 4 * n
        error = h.deterministic - y
        direct_rmse = np.sqrt((error ** 2).mean("T"))
        direct_pearson = xr.corr(h.deterministic, y, dim="T")
        checks = {"rmse_direct_minus_native_max_mm": float(abs(direct_rmse - skill.root_mean_squared_error).max()),
                  "pearson_direct_minus_native_max": float(abs(direct_pearson - skill.pearson).max()),
                  "probability_sum_max_error_pp": float(abs(fc.probabilistic.sum("C").where(mask) - 100).max())}
        assert checks["rmse_direct_minus_native_max_mm"] < 0.05 and checks["pearson_direct_minus_native_max"] < 1e-3, checks
        ds = xr.Dataset({"forecast": fc.deterministic.reset_coords(drop=True), "forecast_probability": fc.probabilistic.reset_coords(drop=True),
                         "forecast_pev": fc.prediction_error_variance.reset_coords(drop=True),
                         "cv_hindcast": h.deterministic.reset_coords(drop=True).rename({"T": "Th"}),
                         **{f"skill_{name}": skill[name].reset_coords(drop=True) for name in skill.data_vars}})
        for name in ("x_eof_scores", "x_cca_scores", "x_explained_variance", "y_eof_scores", "y_cca_scores", "y_explained_variance"):
            for part in returned[3:]:
                if name in part:
                    ds[name] = part[name].where(part[name] > -999).isel(Mode=slice(0, 3)).reset_coords(drop=True).rename({"T": "Th"}) if "T" in part[name].dims else part[name].isel(Mode=slice(0, 3)).reset_coords(drop=True)
        for side, part in zip(("x", "y"), returned[3:]):
            for kind in ("eof", "cca"):
                name = f"{side}_{kind}_loadings"
                if name in part:
                    load = part[name].where(part[name] > -999).isel(Mode=slice(0, 3)).reset_coords(drop=True)
                    ds[name] = load.rename({"Y": "Yx", "X": "Xx"}) if side == "x" else load.reindex(X=y.X, Y=y.Y, method="nearest", tolerance=1e-3)
        ds.attrs = {"fit_seconds": round(seconds, 1), "training_pixels": n, "training_seasons": len(years), "config": json.dumps(config),
                    "checks": json.dumps(checks), "date_parsing_normalizations": len(repairs), "cpt_folder": str(workdir)}
        save(ds, result, season=season, calibration=method.upper(), training_period=period,
             **{k: v for k, v in ds.attrs.items()})
        return dict(record, status="fitted", seconds=round(seconds, 1), pixels=n, **checks)
    except Exception as error:
        return dict(record, status="failed", seconds=round(time.monotonic() - t0, 1), error=f"{type(error).__name__}: {str(error)[:300]}",
                    traceback=traceback.format_exc().splitlines()[-10:])


def weighted(values, weights):
    return float((values * weights).sum() / weights.sum())


def summarize():
    """Comparison fields per season, the shared footprint and the national scores (definitions of the 0.25 degree case)."""
    OUT.mkdir(parents=True, exist_ok=True)
    grid = read(ROOT / "grid.nc")
    mask = grid.evaluation_mask.astype(bool)
    weights = grid.evaluation_weight
    grid.to_netcdf(OUT / "evaluation_footprint.nc", encoding={"evaluation_weight": ENCODING, "touching": {"zlib": True}, "province_index": {"zlib": True}, "evaluation_mask": {"zlib": True}})
    annual = np.empty((12, 7, 4, 3))
    pooled = np.empty((12, 7, 2, 3))
    fits = []
    for si, season in enumerate(SEASONS):
        model = read(SOURCE_CASE / season / "predictors.nc").precipitation
        observed = read(ROOT / season / "observations.nc").precipitation
        truth = observed.sel(T=observed.season_year.isin(EVAL_YEARS)).where(mask)
        f = model.sel(T=model.season_year.isin(EVAL_YEARS))
        predictions = {"raw_cfsv2": f.interp(X=truth.X, Y=truth.Y).where(mask)}
        for period, years in PERIODS.items():
            training = observed.sel(T=observed.season_year.isin(years))
            predictions[f"climatology_{period}"] = training.mean("T").expand_dims(T=truth["T"]).where(mask)
            for method in ("cca", "pcr"):
                fitted = read(ROOT / season / f"{method}_{period}.nc")
                predictions[f"{method}_{period}"] = fitted.forecast.assign_coords(T=truth["T"].values).where(mask)
                fits.append({"season": season, "method": method, "training_period": period, "seconds": float(fitted.attrs["fit_seconds"]),
                             "training_pixels": int(fitted.attrs["training_pixels"]), **json.loads(fitted.attrs["checks"])})
        stacked = xr.concat([predictions[key].reset_coords(drop=True).transpose("T", "Y", "X") for key in VARIANTS], dim=pd.Index(list(VARIANTS), name="forecast_variant"))
        comparison = xr.Dataset({"forecast_rainfall": stacked.astype("float32"), "observed_rainfall": truth.reset_coords(drop=True).astype("float32")})
        comparison = comparison.assign_coords(Ti=("T", truth.Ti.values), Tf=("T", truth.Tf.values), S=("T", f.S.values), season_year=("T", EVAL_YEARS))
        for variable in comparison.values():
            variable.attrs = {"units": "mm"}
        save(comparison, OUT / f"{season}_forecast_comparison.nc", season=season, evaluation_rule="Identical pixels and weights across 12 seasons, 2 periods, 4 years")
        w = weights.values[mask.values]
        o = truth.values[:, mask.values].astype("float64")
        for vi, key in enumerate(VARIANTS):
            error = stacked.sel(forecast_variant=key).values[:, mask.values].astype("float64") - o
            assert np.isfinite(error).all(), (season, key)
            for yi in range(4):
                annual[si, vi, yi] = [np.sqrt(weighted(error[yi] ** 2, w)), weighted(abs(error[yi]), w), weighted(error[yi], w)]
        for gi, years in enumerate(SETS.values()):
            index = [EVAL_YEARS.index(year) for year in years]
            pooled[si, :, gi, 0] = np.sqrt(np.mean(annual[si][:, index, 0] ** 2, axis=1))       # square before averaging the years
            pooled[si, :, gi, 1:] = np.mean(annual[si][:, index, 1:], axis=1)
        print("summarized", season, flush=True)
    coords = {"season": list(SEASONS), "forecast_variant": list(VARIANTS), "season_year": EVAL_YEARS, "evaluation_set": list(SETS)}
    scores = xr.Dataset()
    for index, name in enumerate(("rmse", "mae", "bias")):
        scores[name] = xr.DataArray(annual[..., index], dims=("season", "forecast_variant", "season_year"), coords={d: coords[d] for d in ("season", "forecast_variant", "season_year")}, attrs={"units": "mm"})
        scores["pooled_" + name] = xr.DataArray(pooled[..., index], dims=("season", "forecast_variant", "evaluation_set"), coords={d: coords[d] for d in ("season", "forecast_variant", "evaluation_set")}, attrs={"units": "mm"})
    for coord, attribute in (("S", "initialization"), ("Ti", "start"), ("Tf", "end")):
        scores = scores.assign_coords({coord: (("season", "season_year"), np.array([[np.datetime64(getattr(season_window(s, y), attribute), "ns") for y in EVAL_YEARS] for s in SEASONS]))})
    scores.attrs = {**META, "pooling_rule": "Square root of the mean annual spatial MSE; equal year weights; windows overlap and are not independent"}
    scores.to_netcdf(OUT / "verification_scores.nc")
    report = {"case_id": ROOT.name, "training_periods": {p: [y[0], y[-1], len(y)] for p, y in PERIODS.items()}, "evaluation_years": EVAL_YEARS,
              "common_evaluation_pixels": int(mask.sum()), "pixels_touching_indonesia": int(grid.touching.sum()),
              "calibrated_forecast_cases": 192, "CPT_calls": len(fits), "fit_seconds_total": sum(x["seconds"] for x in fits), "fits": fits,
              "pooled_rmse_all_four_years": {s: {k: float(pooled[si, vi, 0, 0]) for vi, k in enumerate(VARIANTS)} for si, s in enumerate(SEASONS)}}
    (ROOT / "metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    manifest = {"case_id": ROOT.name, "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "outputs": {p.name: {"bytes": p.stat().st_size, "sha256": sha(p)} for p in sorted(OUT.iterdir()) if p.is_file()},
                "source_predictors_sha256": {s: sha(SOURCE_CASE / s / "predictors.nc") for s in SEASONS},
                "script_sha256": sha(Path(__file__)), "metrics": {k: v for k, v in report.items() if k != "fits"}}
    (ROOT / "case_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    sizes = sum(v["bytes"] for v in manifest["outputs"].values())
    print(f"outputs: {len(manifest['outputs'])} files, {sizes / 1e6:.0f} MB; shared pixels {int(mask.sum()):,}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--seasons", nargs="+", choices=SEASONS, default=list(SEASONS))
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()
    t0 = time.monotonic()
    prepare()
    if not args.summarize_only:
        jobs = [(season, method, period) for season in args.seasons for period in PERIODS for method in ("cca", "pcr")]
        failed = 0
        with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context("fork")) as pool:
            for record in pool.map(fit, jobs):
                failed += record["status"] == "failed"
                print(json.dumps(record), flush=True)
        print(f"fits finished in {(time.monotonic() - t0) / 60:.1f} min; failed: {failed}", flush=True)
        if failed or set(args.seasons) != set(SEASONS):
            return
    summarize()


if __name__ == "__main__":
    main()
