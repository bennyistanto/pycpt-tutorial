"""Package the forecast products of the twelve-season run: tercile probabilities, the normal and the tercile boundaries.

A user of CPT wants the forecast itself: how much rain, how that compares with normal, and
the chance of a dry, normal or wet season. The twelve-season run at 0.05 degree
(research/scripts/run_indonesia_all_seasons_005.py) saved all of that for every fit; the
tutorial's first data bundle kept the rainfall totals only. This script adds the rest for
the main 1991-2020 calibrations, without refitting anything:

  probability        CPT's tercile probabilities (%) of the CCA and PCR forecasts, per season
  normal             mean of the 30 observed training totals, 1991-2020 (mm)
  tercile_lower/upper  the 33rd and 67th percentiles of those totals (hazen rule, the rule that
                     reproduces CPT's probabilities; Learn chapter 5 checks it)
  observed_category  0 below, 1 near, 2 above normal: the observed total against those boundaries
  forecast_scale, climatology_scale
                     the ingredients of PyCPT's flexible forecast (construct_flex_fcst): the forecast is a Student's t
                     distribution centred on the forecast total with scale sqrt((N - 2) / N x prediction error variance)
                     and N degrees of freedom; the climatology is a normal distribution with the mean of the N = 30
                     training totals and scale sqrt((N - 2) / N) x their standard deviation. The script checks its numbers against PyCPT's function.

Output: docs/data/indonesia-seasons-2023-products.nc
"""
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
CASE = Path.home() / "CPT/cases/indonesia-all-seasons-2021-2024-005deg"
DEST = ROOT / "docs/data"
SEASONS = "DJF JFM FMA MAM AMJ MJJ JJA JAS ASO SON OND NDJ".split()
METHODS = ["cca", "pcr"]
YEARS = list(range(1991, 2021))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    bundle = xr.open_dataset(DEST / "indonesia-seasons-2023.nc").load()
    mask = bundle.evaluation_mask.astype(bool)
    pixels = int(mask.sum())
    sources, probability, normal, lower, upper, category, scale, climate_scale = {}, [], [], [], [], [], [], []
    import pycpt
    from scipy.stats import t as student_t
    for season in SEASONS:
        midpoint = pd.Timestamp(bundle.target_midpoint.sel(season=season).item())
        with xr.open_dataset(CASE / season / "observations.nc") as ds:
            observed = ds.precipitation.sel(T=ds.season_year.isin(YEARS)).load()
            train_mask = ds.analysis_mask.sel(training_period="1991_2020", drop=True).astype(bool).load()
        sources[f"{CASE.name}/{season}/observations.nc"] = sha(CASE / season / "observations.nc")
        assert observed.sizes["T"] == 30 and bool((train_mask == mask).all())
        values = observed.where(mask).values
        bounds = np.nanpercentile(values, [33, 67], axis=0, method="hazen")
        normal.append(xr.DataArray(np.nanmean(values, axis=0), dims=("Y", "X")))
        lower.append(xr.DataArray(bounds[0], dims=("Y", "X")))
        upper.append(xr.DataArray(bounds[1], dims=("Y", "X")))
        obs = bundle.observed_rainfall.sel(season=season).values
        cat = np.where(obs < bounds[0], 0, np.where(obs > bounds[1], 2, 1)).astype("int8")
        category.append(xr.DataArray(np.where(mask.values, cat, -1).astype("int8"), dims=("Y", "X")))
        climate_scale.append(xr.DataArray(np.sqrt(28 / 30) * np.nanstd(values, axis=0), dims=("Y", "X")))   # PyCPT shrinks the climatological spread too
        Y = observed.where(mask)
        per_method, per_scale = [], []
        for method in METHODS:
            path = CASE / season / f"{method}_1991_2020.nc"
            sources[f"{CASE.name}/{season}/{path.name}"] = sha(path)
            with xr.open_dataset(path) as fitted:
                chosen = fitted.sel(T=midpoint)
                p = chosen.forecast_probability.transpose("C", "Y", "X").load()
                forecast = chosen.forecast.load()
                pev = chosen.forecast_pev.load()
            # the probabilities belong to the forecast already in the bundle
            packaged = bundle.forecast_rainfall.sel(season=season, forecast_variant=f"{method}_1991_2020")
            np.testing.assert_allclose(forecast.where(mask).values, packaged.where(mask).values, atol=1e-3, equal_nan=True)
            p = p.where(p > -999).where(mask)
            total = p.sum("C", skipna=False).values[mask.values]
            assert np.abs(total - 100).max() < 0.01, (season, method, float(np.abs(total - 100).max()))
            per_method.append(p.assign_coords(C=["below", "near", "above"]).rename(C="category").reset_coords(drop=True))
            # PyCPT's flexible forecast for this fit; its ingredients must equal the formulas in the module text
            pev = pev.where(pev > -999).where(mask)
            flex = pycpt.construct_flex_fcst(method.upper(), {"transform_predictand": None, "tailoring": None}, forecast.where(mask), 0.5, True, Y, pev)
            exceed, fcst_scale, climo_scale, fcst_mu, climo_mu, ntrain = flex[0], flex[1], flex[2], flex[3], flex[4], flex[6]
            assert int(ntrain) == 30
            own = np.sqrt(28 / 30 * pev.values)
            np.testing.assert_allclose(np.asarray(fcst_scale)[mask.values], own[mask.values], rtol=1e-6)
            np.testing.assert_allclose(np.asarray(climo_scale)[mask.values], climate_scale[-1].values[mask.values], rtol=1e-5)
            np.testing.assert_allclose(np.asarray(climo_mu)[mask.values], normal[-1].values[mask.values], rtol=1e-5)
            median = np.nanquantile(values, .5, axis=0)
            rebuilt = student_t.sf(median, 30, loc=forecast.values, scale=own)
            np.testing.assert_allclose(np.asarray(exceed)[mask.values], rebuilt[mask.values], atol=1e-6)
            per_scale.append(xr.DataArray(own, dims=("Y", "X")))
        probability.append(xr.concat(per_method, pd.Index(METHODS, name="method")))
        scale.append(xr.concat(per_scale, pd.Index(METHODS, name="method")))
        print("packaged", season, flush=True)

    index = pd.Index(SEASONS, name="season")
    coords = {"Y": bundle.Y, "X": bundle.X}
    out = xr.Dataset({"probability": xr.concat(probability, index).assign_coords(coords),
                      "normal": xr.concat(normal, index).assign_coords(coords),
                      "tercile_lower": xr.concat(lower, index).assign_coords(coords),
                      "tercile_upper": xr.concat(upper, index).assign_coords(coords),
                      "observed_category": xr.concat(category, index).assign_coords(coords),
                      "forecast_scale": xr.concat(scale, index).assign_coords(coords),
                      "climatology_scale": xr.concat(climate_scale, index).assign_coords(coords)})
    out["evaluation_mask"] = bundle.evaluation_mask
    out.probability.attrs = {"units": "%", "long_name": "CPT tercile probability of the 2023-centred forecast, 1991-2020 calibration"}
    out.normal.attrs = {"units": "mm", "long_name": "mean observed seasonal total, 1991-2020"}
    out.tercile_lower.attrs = {"units": "mm", "long_name": "33rd percentile of the 1991-2020 observed totals (hazen)"}
    out.tercile_upper.attrs = {"units": "mm", "long_name": "67th percentile of the 1991-2020 observed totals (hazen)"}
    out.forecast_scale.attrs = {"units": "mm", "long_name": "scale of the flexible forecast's Student's t distribution: sqrt(28/30 x prediction error variance)", "degrees_of_freedom": 30}
    out.climatology_scale.attrs = {"units": "mm", "long_name": "scale of the flexible forecast's climatological normal distribution: sqrt(28/30) x standard deviation of the 30 training totals"}
    out.observed_category.attrs = {"flag_values": [0, 1, 2], "flag_meanings": "below_normal near_normal above_normal", "long_name": "observed tercile category; -1 outside the scored pixels"}
    out.attrs = {"title": "Forecast products of the twelve seasons centred on 2023, native 0.05 degree",
                 "source_case": CASE.name, "training_period": "1991-2020",
                 "probability_note": "CPT's native forecast probabilities; they are not verified here over many years",
                 "category_note": "Boundaries from the 30 training totals with NumPy's hazen rule; the observed total is compared with them"}
    assert int(out.probability.count()) == 12 * 2 * 3 * pixels
    encoding = {"probability": {"dtype": "int16", "scale_factor": 0.01, "_FillValue": -32768, "zlib": True, "complevel": 5},
                **{v: {"dtype": "float32", "zlib": True, "complevel": 5} for v in ("normal", "tercile_lower", "tercile_upper", "forecast_scale", "climatology_scale")},
                "observed_category": {"zlib": True, "complevel": 5}, "evaluation_mask": {"zlib": True, "complevel": 5}}
    path = DEST / "indonesia-seasons-2023-products.nc"
    out.to_netcdf(path, encoding=encoding)
    record = {"output": {path.name: {"sha256": sha(path), "bytes": path.stat().st_size}}, "pixels": pixels, "source_files": sources,
              "note": "Derived teaching copy; nothing refitted."}
    (DEST / "products-provenance.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"file": path.name, "MB": round(path.stat().st_size / 1e6, 1), "pixels": pixels}))


if __name__ == "__main__":
    main()
