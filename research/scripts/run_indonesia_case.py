"""Run and verify the real full-Indonesia OND 2023 CCA historical replay."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import numpy as np
import pandas as pd
import pycpt
from cptcore import canonical_correlation_analysis
import shapely.geometry
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pycpt_tutorial.export import save_netcdf

ROOT = Path.home() / "CPT/cases/indonesia-ond-2023"
OUTPUT = ROOT / "outputs"
CONFIG = dict(x_eof_modes=(3,3), y_eof_modes=(3,3), cca_modes=(2,2),
              validation="CROSSVALIDATION", crossvalidation_window=5,
              synchronous_predictors=True, transform_predictand=None, tailoring=None,
              drymask_threshold=None, skillmask_threshold=None)


def load(name):
    with xr.open_dataset(ROOT / "inputs" / name) as ds:
        return ds.load()


def spatial_mean(values, weights):
    return float(values.weighted(weights.fillna(0)).mean(("Y","X"),skipna=True))


def main():
    if (ROOT / "case_manifest.json").exists():
        print("Completed case already exists; retaining verified outputs.")
        return
    engine = Path(os.environ.get("CPT_BIN_DIR", "")) / "CPT.x"
    expected_engine = Path.home() / "miniforge3/envs/pycpt-tutorial/opt/cpt/bin/CPT.x"
    assert engine == expected_engine and engine.exists(), "Activate the verified packaged CPT environment"
    assert pycpt.__version__ == "2.10.4"
    OUTPUT.mkdir(parents=True,exist_ok=True)
    all_observations = load("observations_chirps3_ond.nc").precipitation
    y = all_observations.sel(T=all_observations["T"].dt.year <= 2010)
    observed = all_observations.sel(T=all_observations["T"].dt.year == 2023)
    x = load("cfsv2_hindcasts_ond.nc").precipitation
    f = load("cfsv2_forecasts_ond.nc").precipitation
    country = load("indonesia_analysis_mask.nc")
    mask = country.analysis_mask.astype(bool)
    np.testing.assert_array_equal(x["T"].values,y["T"].values)
    np.testing.assert_array_equal(y["T"].dt.year.values,np.arange(1982,2011))
    np.testing.assert_array_equal(f["T"].values,observed["T"].values)
    assert 2023 not in y["T"].dt.year.values
    assert x.attrs["units"] == y.attrs["units"] == f.attrs["units"] == "mm"
    start = time.monotonic()
    print("RUNNING_CCA",dict(x.sizes),dict(y.sizes),"country_cells",int(mask.sum()),CONFIG,flush=True)
    hcsts, fcsts, skill, predictor_patterns, predictand_patterns = canonical_correlation_analysis(
        x,y,F=f, **CONFIG,
        cpt_kwargs={"outputdir":ROOT/"cpt", "log":ROOT/"cpt-session.log", "project_file":ROOT/"cpt-commands.txt"})
    elapsed = time.monotonic()-start
    print("CCA_RETURNED", "seconds",elapsed, "forecast_vars",list(fcsts.data_vars), flush=True)
    # CPT rounds grid labels; return to the exact documented observation grid.
    def align_country(ds):
        ds = ds.reindex(X=y.X,Y=y.Y,method="nearest",tolerance=1e-3)
        return ds.where(mask)
    hcsts, fcsts, skill = (align_country(ds) for ds in (hcsts,fcsts,skill))
    np.testing.assert_array_equal(hcsts["T"].dt.year,np.arange(1982,2011))
    np.testing.assert_array_equal(fcsts["T"].dt.year,[2023])
    np.testing.assert_array_equal(fcsts.S.values,pd.to_datetime(["2023-09-01"]).values)
    np.testing.assert_array_equal(fcsts.Ti.values,pd.to_datetime(["2023-10-01"]).values)
    np.testing.assert_array_equal(fcsts.Tf.values,pd.to_datetime(["2023-12-31"]).values)
    assert bool(fcsts.deterministic.where(mask).notnull().any())
    np.testing.assert_allclose(fcsts.probabilistic.sum("C").where(mask).values[mask.values[None,:,:]],100,atol=.1)
    valid_predictions = fcsts.deterministic.isel(T=0).notnull() & mask
    assert int(valid_predictions.sum()) == int(mask.sum()), "Some analysis cells have no forecast"
    meta = {"case_id":"indonesia-ond-2023", "data_kind":"historical_replay", "model":"NCEP CFSv2 ensemble mean", "calibration":"CCA",
            "observation_product":"Local CHIRPS v3.0", "training_start_year":1982,"training_end_year":2010,
            "forecast_initialization":"2023-09-01", "target_period":"2023-10-01/2023-12-31",
            "pycpt_version":pycpt.__version__, "cpt_version":"17.8.3", "resolution_degrees":1.,
            "validation_note":"CPT built-in leave-5-out deterministic hindcasts; 2023 withheld from fitting; no probabilistic hindcast skill claim"}
    for name,ds in (("cca_hindcasts.nc",hcsts),("cca_forecast_2023.nc",fcsts),("cca_native_skill.nc",skill),
                    ("cca_predictor_patterns.nc",predictor_patterns),("cca_predictand_patterns.nc",predictand_patterns)):
        save_netcdf(ds,OUTPUT/name,metadata=meta,overwrite=True)

    # Independent forecast-year comparison: all fitted quantities use 1982–2010 only.
    climatology = y.mean("T")
    raw_forecast = f.interp(X=y.X,Y=y.Y).where(mask)
    raw_hindcasts = x.interp(X=y.X,Y=y.Y).where(mask)
    calibrated = fcsts.deterministic
    baselines = xr.Dataset({"observed":observed,"raw_model_forecast":raw_forecast,
        "training_climatology":climatology.expand_dims(T=f["T"]),
        "calibrated_forecast":calibrated,
        "calibrated_anomaly":calibrated-climatology,
        "observed_anomaly":observed-climatology,
        "raw_error":raw_forecast-observed,"calibrated_error":calibrated-observed,
        "climatology_error":climatology-observed})
    for da in baselines.data_vars.values():
        da.attrs={"units":"mm"}
    save_netcdf(baselines,OUTPUT/"forecast_2023_baselines_and_observed.nc",metadata={**meta,"raw_model_interpolation":"Bilinear from native 1-degree model centres to observation block centres"},overwrite=True)
    save_netcdf(all_observations.to_dataset(),OUTPUT/"observations_chirps3_ond.nc",metadata={**meta,"data_kind":"observed_reference"},overwrite=True)
    save_netcdf(country,OUTPUT/"indonesia_analysis_mask.nc",metadata={"case_id":meta["case_id"],"mask_fitting_period":"1982–2010"},overwrite=True)
    save_netcdf(x.to_dataset(),OUTPUT/"cfsv2_training_predictors.nc",metadata={**meta,"data_kind":"model_hindcast_input"},overwrite=True)
    save_netcdf(f.to_dataset(),OUTPUT/"cfsv2_forecast_predictor_2023.nc",metadata={**meta,"data_kind":"archived_model_forecast_input"},overwrite=True)
    cv = xr.Dataset({
        "cca_rmse":np.sqrt(((hcsts.deterministic-y)**2).mean("T")),
        "raw_rmse":np.sqrt(((raw_hindcasts-y)**2).mean("T")),
        "cca_pearson":xr.corr(hcsts.deterministic,y,dim="T"),
        "raw_pearson":xr.corr(raw_hindcasts,y,dim="T")})
    cv["rmse_change_cca_minus_raw"] = cv.cca_rmse-cv.raw_rmse
    for name in cv.data_vars:
        cv[name].attrs["units"]="1" if "pearson" in name else "mm"
    save_netcdf(cv,OUTPUT/"deterministic_hindcast_comparison.nc",metadata={**meta,"comparison":"CPT cross-validated calibrated predictions versus uncalibrated archive values on identical years/cells; raw model has no fitted local calibration"},overwrite=True)

    weights = country.indonesia_fraction*np.cos(np.deg2rad(y.Y))
    weights = weights.where(mask,0)
    metrics = {}
    for name,prediction in (("training_climatology",baselines.training_climatology),("raw_cfsv2",raw_forecast),("cca_cfsv2",calibrated)):
        error = (prediction-observed).isel(T=0)
        metrics[name]={"area_weighted_rmse_mm":np.sqrt(spatial_mean(error**2,weights)),
                       "area_weighted_mae_mm":spatial_mean(abs(error),weights),
                       "area_weighted_bias_mm":spatial_mean(error,weights)}
    hindcast_metrics = {"cca_area_weighted_mean_grid_rmse_mm":spatial_mean(cv.cca_rmse,weights),
                       "raw_area_weighted_mean_grid_rmse_mm":spatial_mean(cv.raw_rmse,weights),
                       "cca_area_weighted_mean_grid_pearson":spatial_mean(cv.cca_pearson,weights),
                       "raw_area_weighted_mean_grid_pearson":spatial_mean(cv.raw_pearson,weights),
                       "fraction_country_weight_with_lower_cca_rmse":spatial_mean((cv.cca_rmse<cv.raw_rmse).where(mask),weights)}
    report={"forecast_year":2023,"training_years":[1982,2010],"training_sample_count":29,"country_grid_cells":int(mask.sum()),
            "forecast_metrics":metrics,"hindcast_metrics":hindcast_metrics,"cpt_elapsed_seconds":elapsed,
            "negative_calibrated_forecast_cells":int(((calibrated.isel(T=0)<0)&mask).sum()),
            "probability_sum_max_absolute_error_percent":float(abs(fcsts.probabilistic.sum("C").where(mask)-100).max()),
            "interpretation":"Single historical replay, not independent evidence of operational national forecast skill. Built-in CPT cross-validation is not claimed to be nested model-selection validation."}
    (ROOT/"metrics.json").write_text(json.dumps(report,indent=2)+"\n")
    print("METRICS",json.dumps(report,indent=2),flush=True)

    geometry=shapely.geometry.shape(json.loads((ROOT/"inputs/indonesia_boundary.geojson").read_text()))
    fig,axes=plt.subplots(2,2,figsize=(16,8),subplot_kw={"projection":ccrs.PlateCarree()},layout="constrained")
    panels=[("Training climatology (1982–2010)",climatology),("Uncalibrated CFSv2 forecast",raw_forecast.isel(T=0)),
            ("CCA forecast — training excludes 2023",calibrated.isel(T=0)),("CHIRPS v3 observed OND 2023",observed.isel(T=0))]
    vmax=float(np.nanpercentile(np.concatenate([v.values.ravel() for _,v in panels]),99))
    for ax,(title,field) in zip(axes.ravel(),panels):
        artist=ax.pcolormesh(field.X,field.Y,field,transform=ccrs.PlateCarree(),cmap="YlGnBu",vmin=0,vmax=vmax)
        ax.add_geometries([geometry],ccrs.PlateCarree(),facecolor="none",edgecolor="#333333",linewidth=.35)
        ax.set_extent([94,142,-12,7]); ax.set_title(title,fontsize=11)
        ax.gridlines(draw_labels={"bottom":"x","left":"y"},linewidth=.25,alpha=.4)
    fig.colorbar(artist,ax=axes.ravel().tolist(),label="OND accumulated rainfall (mm)",shrink=.8)
    fig.suptitle("Full Indonesia • OND 2023 historical replay • 1° country-land averages",fontsize=15)
    fig.savefig(OUTPUT/"indonesia_ond_2023_comparison.png",dpi=180)
    plt.close(fig)
    files={path.name:{"bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(OUTPUT.glob("*")) if path.is_file()}
    availability=json.loads((ROOT/"availability.json").read_text())
    manifest={"case_id":meta["case_id"],"completed_at":dt.datetime.now(dt.timezone.utc).isoformat(),"availability":availability,
              "cpt_config":CONFIG,"engine":str(engine),"engine_sha256":hashlib.sha256(engine.read_bytes()).hexdigest(),
              "outputs":files,"metrics":report,
              "limitations":["CHIRPS v3 and current archive revisions make this a retrospective replay, not exact reproduction of information available in September 2023",
                             "1-degree country-only land averages do not resolve small islands or local administrative detail",
                             "29 training seasons from 1982–2010; 2011–2022 are not appended to this hindcast product",
                             "Fixed small mode counts were chosen before looking at forecast outcomes; no tuning to 2023",
                             "CPT deterministic built-in CV diagnostics are reported; no in-sample probabilistic hindcast scores are presented as out-of-sample",
                             "The supplied 1991–2020 LTA was not used to fit calibration or the matched-period climatology baseline"]}
    (ROOT/"case_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print("CASE_COMPLETE",ROOT,flush=True)


if __name__=="__main__":
    main()
