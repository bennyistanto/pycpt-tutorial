"""PCR on the frozen Indonesia OND2023 case, with a four-method comparison."""
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
from cptcore import principal_components_regression
import shapely.geometry
import xarray as xr

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from pycpt_tutorial.export import save_netcdf
from run_indonesia_case import ROOT, load, spatial_mean

COMPARISON=ROOT/"pcr-comparison"
OUTPUT=COMPARISON/"outputs"
CONFIG=dict(x_eof_modes=(3,3),validation="CROSSVALIDATION",crossvalidation_window=5,
            synchronous_predictors=True,transform_predictand=None,tailoring=None,
            drymask_threshold=None,skillmask_threshold=None)


def read_dataset(path):
    with xr.open_dataset(path) as ds:
        return ds.load()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if (COMPARISON/"comparison_manifest.json").exists():
        print("Completed PCR comparison exists; retaining its verified outputs.")
        return
    engine=Path(os.environ.get("CPT_BIN_DIR",""))/"CPT.x"
    assert engine == Path.home()/"miniforge3/envs/pycpt-tutorial/opt/cpt/bin/CPT.x"
    assert pycpt.__version__ == "2.10.4"
    cca_manifest=json.loads((ROOT/"case_manifest.json").read_text())
    original_hashes={name:digest(ROOT/"outputs"/name) for name in cca_manifest["outputs"]}
    assert all(original_hashes[name]==info["sha256"] for name,info in cca_manifest["outputs"].items())
    input_names=["observations_chirps3_ond.nc","cfsv2_hindcasts_ond.nc","cfsv2_forecasts_ond.nc","indonesia_analysis_mask.nc"]
    input_hashes={name:digest(ROOT/"inputs"/name) for name in input_names}
    all_y=load(input_names[0]).precipitation
    y=all_y.sel(T=all_y["T"].dt.year <= 2010)
    observed=all_y.sel(T=all_y["T"].dt.year == 2023)
    x=load(input_names[1]).precipitation
    f=load(input_names[2]).precipitation
    country=load(input_names[3]); mask=country.analysis_mask.astype(bool)
    weights=(country.indonesia_fraction*np.cos(np.deg2rad(y.Y))).where(mask,0)
    np.testing.assert_array_equal(x["T"],y["T"])
    np.testing.assert_array_equal(y["T"].dt.year,np.arange(1982,2011))
    assert 2023 not in y["T"].dt.year.values
    OUTPUT.mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    print("RUNNING_PCR",CONFIG,flush=True)
    hcst,fcst,native_skill,patterns=principal_components_regression(
        x,y,F=f,**CONFIG,cpt_kwargs={"outputdir":COMPARISON/"cpt","log":COMPARISON/"cpt-session.log","project_file":COMPARISON/"cpt-commands.txt"})
    elapsed=time.monotonic()-start
    hcst,fcst,native_skill=[ds.reindex(X=y.X,Y=y.Y,method="nearest",tolerance=1e-3).where(mask) for ds in (hcst,fcst,native_skill)]
    np.testing.assert_array_equal(hcst["T"].dt.year,np.arange(1982,2011))
    np.testing.assert_array_equal(fcst.S.values,pd.to_datetime(["2023-09-01"]).values)
    np.testing.assert_array_equal(fcst.Ti.values,pd.to_datetime(["2023-10-01"]).values)
    np.testing.assert_array_equal(fcst.Tf.values,pd.to_datetime(["2023-12-31"]).values)
    for name in ("deterministic","probabilistic","prediction_error_variance"):
        assert int(fcst[name].count()) == 369*(3 if name=="probabilistic" else 1)
    probabilities=fcst.probabilistic
    np.testing.assert_allclose(probabilities.sum("C").isel(T=0).values[mask.values],100,atol=.1)
    assert float(probabilities.min())>=0 and float(probabilities.max())<=100
    assert float(fcst.prediction_error_variance.min())>=0
    meta={"case_id":"indonesia-ond-2023","calibration":"PCR","model":"NCEP CFSv2 ensemble mean","observation_product":"Local CHIRPS v3.0",
          "data_kind":"historical_replay","training_start_year":1982,"training_end_year":2010,"forecast_initialization":"2023-09-01",
          "target_period":"2023-10-01/2023-12-31","pycpt_version":"2.10.4","cpt_version":"17.8.3","resolution_degrees":1.,
          "validation_note":"CPT built-in leave-5-out deterministic hindcasts; forecast year excluded; no probabilistic hindcast skill claim"}
    for name,ds in (("pcr_hindcasts.nc",hcst),("pcr_forecast_2023.nc",fcst),("pcr_native_skill.nc",native_skill),("pcr_predictor_patterns.nc",patterns)):
        save_netcdf(ds,OUTPUT/name,metadata=meta,overwrite=True)

    cca_forecast=read_dataset(ROOT/"outputs/cca_forecast_2023.nc").deterministic
    cca_hindcasts=read_dataset(ROOT/"outputs/cca_hindcasts.nc").deterministic
    baselines=read_dataset(ROOT/"outputs/forecast_2023_baselines_and_observed.nc")
    forecasts={"climatology":baselines.training_climatology,"raw_cfsv2":baselines.raw_model_forecast,"cca":cca_forecast,"pcr":fcst.deterministic}
    stacked=xr.concat([value.reset_coords(drop=True) for value in forecasts.values()],dim=pd.Index(list(forecasts),name="forecast_method"),join="exact")
    stacked=stacked.assign_coords(S=f.S,Ti=f.Ti,Tf=f.Tf)
    stacked.attrs={"units":"mm","long_name":"OND2023 accumulated rainfall forecast"}
    comparison=xr.Dataset({"forecast_rainfall":stacked,"observed_rainfall":observed,"error":stacked-observed,"absolute_error":abs(stacked-observed)})
    for da in comparison.data_vars.values(): da.attrs["units"]="mm"
    comparison_meta={**meta,"calibration":"Climatology, raw CFSv2, CCA and PCR","comparison_rule":"Identical frozen inputs, verification year, grid and country weights; unchanged CCA benchmark"}
    save_netcdf(comparison,OUTPUT/"forecast_2023_four_method_comparison.nc",metadata=comparison_meta,overwrite=True)

    predictions={"raw_cfsv2":x.interp(X=y.X,Y=y.Y).where(mask),"cca":cca_hindcasts,"pcr":hcst.deterministic}
    historical=[]
    for name,prediction in predictions.items():
        error=prediction-y
        historical.append(xr.Dataset({"rmse":np.sqrt((error**2).mean("T")),"mae":abs(error).mean("T"),"bias":error.mean("T"),"pearson":xr.corr(prediction,y,dim="T")}))
    historical=xr.concat(historical,dim=pd.Index(list(predictions),name="forecast_method"))
    for name,da in historical.data_vars.items(): da.attrs["units"]="1" if name=="pearson" else "mm"
    save_netcdf(historical,OUTPUT/"deterministic_hindcast_three_method_comparison.nc",metadata={**comparison_meta,"comparison_rule":"Raw archive versus CPT cross-validated CCA/PCR predictions on the same 29 years/cells; no historical climatology-CV score inferred"},overwrite=True)
    np.testing.assert_allclose(historical.rmse.sel(forecast_method="pcr"),native_skill.root_mean_squared_error,atol=.002,rtol=0)
    np.testing.assert_allclose(historical.pearson.sel(forecast_method="pcr"),native_skill.pearson,atol=1e-5,rtol=0)
    forecast_metrics={}
    for name in forecasts:
        error=comparison.error.sel(forecast_method=name).isel(T=0)
        forecast_metrics[name]={"area_weighted_rmse_mm":np.sqrt(spatial_mean(error**2,weights)),"area_weighted_mae_mm":spatial_mean(abs(error),weights),"area_weighted_bias_mm":spatial_mean(error,weights)}
    prior=json.loads((ROOT/"metrics.json").read_text())["forecast_metrics"]
    for now,before in (("climatology","training_climatology"),("raw_cfsv2","raw_cfsv2"),("cca","cca_cfsv2")):
        for statistic in forecast_metrics[now]:
            np.testing.assert_allclose(forecast_metrics[now][statistic],prior[before][statistic],atol=1e-8,rtol=0)
    hindcast_metrics={name:{"area_weighted_mean_grid_rmse_mm":spatial_mean(historical.rmse.sel(forecast_method=name),weights),"area_weighted_mean_grid_pearson":spatial_mean(historical.pearson.sel(forecast_method=name),weights)} for name in predictions}
    report={"forecast_year":2023,"training_years":[1982,2010],"training_sample_count":29,"resolution_degrees":1.,"country_grid_cells":369,
            "forecast_metrics":forecast_metrics,"hindcast_metrics":hindcast_metrics,"pcr_config":CONFIG,"cpt_elapsed_seconds":elapsed,
            "negative_pcr_forecast_cells":int(((fcst.deterministic.isel(T=0)<0)&mask).sum()),
            "probability_sum_max_absolute_error_percent":float(abs(probabilities.sum("C").where(mask)-100).max()),
            "interpretation":"Same-input comparison of one held-out historical forecast; not a general ranking of methods or nested-CV skill assessment"}
    (COMPARISON/"metrics.json").write_text(json.dumps(report,indent=2)+"\n")

    geometry=shapely.geometry.shape(json.loads((ROOT/"inputs/indonesia_boundary.geojson").read_text()))
    projection=ccrs.PlateCarree()
    fig,axes=plt.subplots(2,2,figsize=(16,8),subplot_kw={"projection":projection},layout="constrained")
    titles={"climatology":"Climatology (1982–2010)","raw_cfsv2":"Uncalibrated CFSv2","cca":"CCA • 3 X EOFs / 3 Y EOFs / 2 CCA modes","pcr":"PCR • 3 X EOFs"}
    vmax=float(np.nanpercentile(stacked.values,99))
    for ax,name in zip(axes.ravel(),forecasts):
        field=stacked.sel(forecast_method=name).isel(T=0)
        im=ax.pcolormesh(field.X,field.Y,field,transform=projection,cmap="YlGnBu",vmin=0,vmax=vmax)
        ax.add_geometries([geometry],projection,facecolor="none",edgecolor="#333333",linewidth=.35)
        ax.set_extent([94,142,-12,7]); ax.gridlines(draw_labels={"bottom":"x","left":"y"},linewidth=.25,alpha=.4)
        ax.set_title(titles[name]+f"\n2023 RMSE {forecast_metrics[name]['area_weighted_rmse_mm']:.1f} mm",fontsize=11)
    fig.colorbar(im,ax=axes.ravel().tolist(),label="OND accumulated rainfall (mm)",shrink=.8)
    fig.suptitle("Full Indonesia • OND2023 • same inputs, grid and verification • 1° country-land averages",fontsize=14)
    fig.savefig(OUTPUT/"indonesia_ond2023_four_method_comparison.png",dpi=180); plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(16,4.5),subplot_kw={"projection":projection},layout="constrained")
    fields=[abs(comparison.error.sel(forecast_method="pcr").isel(T=0))-abs(comparison.error.sel(forecast_method="cca").isel(T=0)),historical.rmse.sel(forecast_method="pcr")-historical.rmse.sel(forecast_method="cca")]
    for ax,field,title in zip(axes,fields,["2023 absolute error: PCR minus CCA","1982–2010 cross-validated RMSE: PCR minus CCA"]):
        limit=max(1.,float(np.nanpercentile(abs(field.values),98)))
        im=ax.pcolormesh(field.X,field.Y,field,transform=projection,cmap="RdBu_r",vmin=-limit,vmax=limit)
        ax.add_geometries([geometry],projection,facecolor="none",edgecolor="#333333",linewidth=.35)
        ax.set_extent([94,142,-12,7]); ax.set_title(title,fontsize=11)
        ax.gridlines(draw_labels={"bottom":"x","left":"y"},linewidth=.25,alpha=.4)
        fig.colorbar(im,ax=ax,label="mm • blue: PCR lower error; red: CCA lower error",shrink=.8)
    fig.savefig(OUTPUT/"pcr_minus_cca_error_comparison.png",dpi=180); plt.close(fig)

    assert all(digest(ROOT/"outputs"/name)==value for name,value in original_hashes.items())
    assert all(digest(ROOT/"inputs"/name)==value for name,value in input_hashes.items())
    files={p.name:{"bytes":p.stat().st_size,"sha256":digest(p)} for p in sorted(OUTPUT.iterdir()) if p.is_file()}
    manifest={"case_id":"indonesia-ond-2023-pcr-comparison","completed_at":dt.datetime.now(dt.timezone.utc).isoformat(),"pcr_config":CONFIG,
              "frozen_input_sha256":input_hashes,"unchanged_cca_output_sha256":original_hashes,"engine":str(engine),"engine_sha256":digest(engine),
              "script_sha256":digest(Path(__file__)),"outputs":files,"metrics":report,
              "verification":{"input_and_cca_output_hashes_unchanged":True,"all_exports_readback_verified":True,"forecast_dates_and_probability_bounds":"PASS","native_vs_direct_skill":"PASS","prior_three_method_metrics_unchanged":True}}
    (COMPARISON/"comparison_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps(report,indent=2),flush=True)
    print("PCR_COMPARISON_COMPLETE",COMPARISON,flush=True)


if __name__=="__main__": main()
