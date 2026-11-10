"""Refit CCA/PCR at 0.25 degrees and compare on both native and common grids."""
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
from cptcore import canonical_correlation_analysis, principal_components_regression
import shapely.geometry
import xarray as xr

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from pycpt_tutorial.export import save_netcdf
from prepare_indonesia_025_case import ROOT, OLD, main as prepare

OUT=ROOT/"outputs"
COMMON=dict(x_eof_modes=(3,3),validation="CROSSVALIDATION",crossvalidation_window=5,
            synchronous_predictors=True,transform_predictand=None,tailoring=None,drymask_threshold=None,skillmask_threshold=None)


def read(path):
    with xr.open_dataset(path) as ds: return ds.load()


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def weighted_mean(da,weights):
    return float(da.weighted(weights.fillna(0)).mean(("Y","X"),skipna=True).item())


def forecast_metrics(pred,truth,weights):
    error=(pred-truth).squeeze("T",drop=True)
    return {"rmse_mm":np.sqrt(weighted_mean(error**2,weights)),"mae_mm":weighted_mean(abs(error),weights),"bias_mm":weighted_mean(error,weights)}


def historical_fields(pred,truth):
    error=pred-truth
    result=xr.Dataset({"rmse":np.sqrt((error**2).mean("T")),"mae":abs(error).mean("T"),"bias":error.mean("T"),"pearson":xr.corr(pred,truth,dim="T")})
    for name in result: result[name].attrs["units"]="1" if name=="pearson" else "mm"
    return result


def stack_forecasts(predictions,truth,initialization):
    stacked=xr.concat([p.reset_coords(drop=True) for p in predictions.values()],dim=pd.Index(list(predictions),name="forecast_variant"),join="exact")
    stacked=stacked.assign_coords(Ti=truth.Ti,Tf=truth.Tf,S=initialization)
    ds=xr.Dataset({"forecast_rainfall":stacked,"observed_rainfall":truth,"error":stacked-truth,"absolute_error":abs(stacked-truth)})
    for variable in ds.values(): variable.attrs={"units":"mm"}
    return ds


def main():
    if (ROOT/"case_manifest.json").exists():
        print("Completed 0.25-degree case exists; retaining verified results."); return
    prepare()
    assert pycpt.__version__=="2.10.4"
    engine=Path(os.environ.get("CPT_BIN_DIR",""))/"CPT.x"
    assert engine==Path.home()/"miniforge3/envs/pycpt-tutorial/opt/cpt/bin/CPT.x"
    original_files={}
    for manifest_name,prefix in (("case_manifest.json","outputs"),("pcr-comparison/comparison_manifest.json","pcr-comparison/outputs")):
        m=json.loads((OLD/manifest_name).read_text())
        for name,info in m["outputs"].items():
            rel=str(Path(prefix)/name); assert sha(OLD/rel)==info["sha256"]
            original_files[rel]=info["sha256"]
    input_names=["cfsv2_hindcasts_ond.nc","cfsv2_forecasts_ond.nc","indonesia_boundary.geojson"]
    input_hashes={name:sha(OLD/"inputs"/name) for name in input_names}
    x=read(OLD/"inputs/cfsv2_hindcasts_ond.nc").precipitation
    f=read(OLD/"inputs/cfsv2_forecasts_ond.nc").precipitation
    obs_ds=read(ROOT/"inputs/observations_chirps3_ond_025.nc")
    country=read(ROOT/"inputs/indonesia_analysis_mask_025.nc")
    all_y=obs_ds.precipitation
    y=all_y.sel(T=all_y["T"].dt.year<=2010)
    observed=all_y.sel(T=all_y["T"].dt.year==2023)
    mask=country.analysis_mask.astype(bool); count=int(mask.sum())
    np.testing.assert_array_equal(x["T"],y["T"])
    np.testing.assert_array_equal(y["T"].dt.year,np.arange(1982,2011))
    np.testing.assert_array_equal(f["T"],observed["T"])
    OUT.mkdir(parents=True,exist_ok=True)
    meta={"case_id":"indonesia-ond-2023-025deg","data_kind":"historical_replay","model":"NCEP CFSv2 ensemble mean","observation_product":"Local CHIRPS v3.0",
          "training_start_year":1982,"training_end_year":2010,"forecast_initialization":"2023-09-01","target_period":"2023-10-01/2023-12-31",
          "predictand_resolution_degrees":.25,"predictor_resolution_degrees":1.,"pycpt_version":"2.10.4","cpt_version":"17.8.3",
          "validation_note":"Fixed mode counts, CPT built-in leave-5-out deterministic hindcasts; 2023 withheld; no probabilistic hindcast skill claim"}
    def save(ds,name,attrs=None):
        return save_netcdf(ds,OUT/name,metadata={**meta,**(attrs or {})},overwrite=True)
    results={}; timings={}; score_checks={}; probability_checks={}
    for method in ("cca","pcr"):
        config=dict(COMMON)
        if method=="cca": config.update(y_eof_modes=(3,3),cca_modes=(2,2))
        print("RUNNING",method,"predictor",dict(x.sizes),"predictand",dict(y.sizes),"country_cells",count,flush=True)
        start=time.monotonic()
        function=canonical_correlation_analysis if method=="cca" else principal_components_regression
        result=function(x,y,F=f,**config,cpt_kwargs={"outputdir":ROOT/f"cpt-{method}","log":ROOT/f"cpt-{method}-session.log","project_file":ROOT/f"cpt-{method}-commands.txt"})
        timings[method]=time.monotonic()-start
        h,fc,skill=[ds.reindex(X=y.X,Y=y.Y,method="nearest",tolerance=1e-3).where(mask) for ds in result[:3]]
        np.testing.assert_array_equal(h["T"].dt.year,np.arange(1982,2011))
        np.testing.assert_array_equal(fc.S.values,pd.to_datetime(["2023-09-01"]).values)
        np.testing.assert_array_equal(fc.Ti.values,pd.to_datetime(["2023-10-01"]).values)
        np.testing.assert_array_equal(fc.Tf.values,pd.to_datetime(["2023-12-31"]).values)
        for name in ("deterministic","probabilistic","prediction_error_variance"):
            expected=count*(3 if name=="probabilistic" else 1)
            assert int(fc[name].count())==expected,(method,name,int(fc[name].count()),expected)
        assert int(h.deterministic.count())==count*29
        assert float(fc.probabilistic.min())>=0 and float(fc.probabilistic.max())<=100
        assert float(fc.prediction_error_variance.min())>=0
        np.testing.assert_allclose(fc.probabilistic.sum("C").isel(T=0).values[mask.values],100,atol=.1)
        direct=historical_fields(h.deterministic,y)
        np.testing.assert_allclose(direct.rmse,skill.root_mean_squared_error,atol=.01,rtol=1e-5)
        np.testing.assert_allclose(direct.pearson,skill.pearson,atol=1e-4,rtol=0)
        score_checks[method]={"maximum_native_direct_rmse_difference_mm":float(abs(direct.rmse-skill.root_mean_squared_error).max()),"maximum_native_direct_pearson_difference":float(abs(direct.pearson-skill.pearson).max())}
        probability_checks[method]={"maximum_sum_error_percentage_points":float(abs(fc.probabilistic.sum("C").where(mask)-100).max()),"negative_forecast_cells":int(((fc.deterministic.isel(T=0)<0)&mask).sum())}
        results[method]={"hindcasts":h,"forecast":fc,"skill":skill,"historical":direct,"config":config}
        for suffix,ds in (("hindcasts",h),("forecast_2023",fc),("native_skill",skill)):
            save(ds,f"{method}_{suffix}_025.nc",{"calibration":method.upper()})
        save(result[3],f"{method}_predictor_patterns_025.nc",{"calibration":method.upper()})
        if method=="cca": save(result[4],"cca_predictand_patterns_025.nc",{"calibration":"CCA"})
        print("COMPLETED",method,"seconds",timings[method],flush=True)

    climatology=y.mean("T").expand_dims(T=f["T"])
    raw_f=f.interp(X=y.X,Y=y.Y).where(mask)
    raw_h=x.interp(X=y.X,Y=y.Y).where(mask)
    fine_forecasts={"climatology":climatology,"raw_cfsv2":raw_f,"cca":results["cca"]["forecast"].deterministic,"pcr":results["pcr"]["forecast"].deterministic}
    native_comparison=stack_forecasts(fine_forecasts,observed,f.S)
    save(native_comparison,"native_025_forecast_comparison.nc")
    historical_fine={"raw_cfsv2":historical_fields(raw_h,y),"cca":results["cca"]["historical"],"pcr":results["pcr"]["historical"]}
    save(xr.concat(list(historical_fine.values()),dim=pd.Index(list(historical_fine),name="forecast_variant")),"native_025_hindcast_comparison.nc")
    save(obs_ds,"observations_chirps3_ond_025.nc",{"data_kind":"observed_reference"})
    save(country,"indonesia_analysis_mask_025.nc")
    save(x.to_dataset(),"cfsv2_training_predictors.nc",{"data_kind":"unchanged_model_input"})
    save(f.to_dataset(),"cfsv2_forecast_predictor_2023.nc",{"data_kind":"unchanged_model_input"})

    # Primary cross-resolution comparison: original 1-degree observations, one
    # common mask/weight set, and land-weighted 4x4 aggregation of deterministic forecasts.
    old_country=read(OLD/"outputs/indonesia_analysis_mask.nc")
    old_comparison=read(OLD/"pcr-comparison/outputs/forecast_2023_four_method_comparison.nc")
    old_observed=old_comparison.observed_rainfall
    old_all=read(OLD/"outputs/observations_chirps3_ond.nc").precipitation
    old_y=old_all.sel(T=old_all["T"].dt.year<=2010)
    old_mask=old_country.analysis_mask.astype(bool)
    full_fine_weight=country.country_land_weight
    fine_weight=full_fine_weight.where(mask,0)
    def label_old(da):
        np.testing.assert_allclose(da.Y,old_y.Y,atol=1e-4,rtol=0)
        np.testing.assert_allclose(da.X,old_y.X,atol=1e-4,rtol=0)
        return da.assign_coords(Y=old_y.Y,X=old_y.X)
    def coarse_sum(da): return label_old(da.coarsen(Y=4,X=4,boundary="exact").sum())
    coarse_full=coarse_sum(full_fine_weight)
    training_coverage=coarse_sum(fine_weight)/coarse_full
    eval_weight=fine_weight.where(observed.isel(T=0).notnull(),0)
    evaluation_coverage=coarse_sum(eval_weight)/coarse_full
    common_mask=old_mask&(training_coverage>=.99)&(evaluation_coverage>=.99)&old_observed.isel(T=0).notnull()
    assert int(common_mask.sum())>0
    def aggregate(da):
        valid_weight=fine_weight.where(da.notnull(),0)
        return (coarse_sum(da.fillna(0)*fine_weight)/coarse_sum(valid_weight)).where(common_mask)
    fine_observed_on_old=aggregate(observed)
    common_forecasts={"climatology_1deg":old_comparison.forecast_rainfall.sel(forecast_method="climatology",drop=True).where(common_mask),
                      "raw_cfsv2_1deg":old_comparison.forecast_rainfall.sel(forecast_method="raw_cfsv2",drop=True).where(common_mask),
                      "cca_1deg":old_comparison.forecast_rainfall.sel(forecast_method="cca",drop=True).where(common_mask),
                      "pcr_1deg":old_comparison.forecast_rainfall.sel(forecast_method="pcr",drop=True).where(common_mask),
                      "cca_025_aggregated":aggregate(results["cca"]["forecast"].deterministic),
                      "pcr_025_aggregated":aggregate(results["pcr"]["forecast"].deterministic)}
    common_truth=old_observed.where(common_mask)
    common_meta={"evaluation_resolution_degrees":1.,"comparison_rule":"Identical original 1-degree CHIRPS observations and common original-country weights; fine deterministic forecasts land-weighted to 1 degree; >=99 percent fine footprint coverage"}
    save(stack_forecasts(common_forecasts,common_truth,f.S),"common_1deg_forecast_comparison.nc",common_meta)
    footprint=xr.Dataset({"common_mask":common_mask.astype("int8"),"original_analysis_mask":old_country.analysis_mask,
                          "retained_fine_training_land_fraction":training_coverage,"retained_fine_verification_land_fraction":evaluation_coverage,
                          "fine_observed_aggregated":fine_observed_on_old,"fine_minus_original_observation":fine_observed_on_old-old_observed})
    footprint.fine_observed_aggregated.attrs["units"]="mm"; footprint.fine_minus_original_observation.attrs["units"]="mm"
    save(footprint,"cross_resolution_evaluation_footprint.nc",common_meta)
    common_hindcasts={"raw_cfsv2_1deg":x.interp(X=old_y.X,Y=old_y.Y).where(common_mask),
                      "cca_1deg":read(OLD/"outputs/cca_hindcasts.nc").deterministic.where(common_mask),
                      "pcr_1deg":read(OLD/"pcr-comparison/outputs/pcr_hindcasts.nc").deterministic.where(common_mask),
                      "cca_025_aggregated":aggregate(results["cca"]["hindcasts"].deterministic),
                      "pcr_025_aggregated":aggregate(results["pcr"]["hindcasts"].deterministic)}
    historical_common={key:historical_fields(value,old_y.where(common_mask)) for key,value in common_hindcasts.items()}
    save(xr.concat(list(historical_common.values()),dim=pd.Index(list(historical_common),name="forecast_variant")),"common_1deg_hindcast_comparison.nc",common_meta)
    native_eval=mask&observed.isel(T=0).notnull()
    native_weights=country.country_land_weight.where(native_eval,0)
    old_weights=old_country.indonesia_fraction*np.cos(np.deg2rad(old_y.Y))
    common_weights=old_weights.where(common_mask,0)
    native_metrics={key:forecast_metrics(value,observed,native_weights) for key,value in fine_forecasts.items()}
    common_metrics={key:forecast_metrics(value,common_truth,common_weights) for key,value in common_forecasts.items()}
    def summarize_historical(fields,weights):
        return {key:{"mean_grid_rmse_mm":weighted_mean(ds.rmse,weights),"mean_grid_pearson":weighted_mean(ds.pearson,weights)} for key,ds in fields.items()}
    report={"case_id":meta["case_id"],"training_years":[1982,2010],"forecast_initialization":"2023-09-01","target":"OND2023",
            "preparation":json.loads((ROOT/"preparation.json").read_text()),"fit_elapsed_seconds":timings,
            "native_025_forecast_metrics":native_metrics,"native_025_historical_metrics":summarize_historical(historical_fine,native_weights),
            "common_1deg_forecast_metrics":common_metrics,"common_1deg_historical_metrics":summarize_historical(historical_common,common_weights),
            "common_1deg_cells":int(common_mask.sum()),"original_1deg_cells":int(old_mask.sum()),
            "common_fraction_original_country_weight":float(common_weights.sum()/old_weights.where(old_mask,0).sum()),
            "native_025_verification_cells":int(native_eval.sum()),"fine_aggregate_vs_original_observation_rmse_mm":forecast_metrics(fine_observed_on_old,common_truth,common_weights)["rmse_mm"],
            "native_score_checks":score_checks,"probability_checks":probability_checks,
            "interpretation":"Primary resolution comparison uses common 1-degree observations/grid/footprint. Native 0.25-degree RMSE measures a different spatial scale and must not be ranked directly against native 1-degree RMSE."}
    (ROOT/"metrics.json").write_text(json.dumps(report,indent=2)+"\n")
    plot(meta,results,old_comparison,common_forecasts,common_truth)
    assert all(sha(OLD/path)==value for path,value in original_files.items())
    assert all(sha(OLD/"inputs"/name)==value for name,value in input_hashes.items())
    manifest={"case_id":meta["case_id"],"completed_at":dt.datetime.now(dt.timezone.utc).isoformat(),"engine":str(engine),"engine_sha256":sha(engine),
              "configurations":{name:result["config"] for name,result in results.items()},"frozen_model_and_boundary_input_sha256":input_hashes,
              "unchanged_original_case_artifacts_sha256":original_files,"metrics":report,
              "outputs":{p.name:{"bytes":p.stat().st_size,"sha256":sha(p)} for p in sorted(OUT.iterdir()) if p.is_file()},
              "pipeline_script_sha256":{str(Path("research/scripts")/Path(__file__).name):sha(Path(__file__)),"research/scripts/prepare_indonesia_025_case.py":sha(Path(__file__).with_name("prepare_indonesia_025_case.py")),"pycpt_tutorial/country_grid.py":sha(Path(__file__).parents[2]/"pycpt_tutorial/country_grid.py")},
              "limitations":["One historical target, not a general forecast-skill claim","Fixed small mode counts, no tuning to2023 and no nested-CV claim","Native fine probabilities and variances are not averaged into coarse probabilities/uncertainties","Source products are retrospective, not exact 2023 data vintages","Fine and coarse country footprints can differ; common mask and coverage are saved"]}
    (ROOT/"case_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print("CASE_COMPLETE",json.dumps(report,indent=2),flush=True)


def plot(meta,results,old_comparison,common_forecasts,truth):
    geometry=shapely.geometry.shape(json.loads((OLD/"inputs/indonesia_boundary.geojson").read_text()))
    projection=ccrs.PlateCarree()
    fig,axes=plt.subplots(2,2,figsize=(16,8),subplot_kw={"projection":projection},layout="constrained")
    fields=[old_comparison.forecast_rainfall.sel(forecast_method="cca",drop=True).isel(T=0),results["cca"]["forecast"].deterministic.isel(T=0),
            old_comparison.forecast_rainfall.sel(forecast_method="pcr",drop=True).isel(T=0),results["pcr"]["forecast"].deterministic.isel(T=0)]
    vmax=float(np.nanpercentile(np.concatenate([da.values.ravel() for da in fields]),99))
    for ax,field,title in zip(axes.ravel(),fields,["CCA • fitted at 1°","CCA • refitted at 0.25°","PCR • fitted at 1°","PCR • refitted at 0.25°"]):
        im=ax.pcolormesh(field.X,field.Y,field,transform=projection,cmap="YlGnBu",vmin=0,vmax=vmax)
        ax.add_geometries([geometry],projection,facecolor="none",edgecolor="#333333",linewidth=.3)
        ax.set_extent([94,142,-12,7]); ax.set_title(title,fontsize=12)
        ax.gridlines(draw_labels={"bottom":"x","left":"y"},linewidth=.25,alpha=.4)
    fig.colorbar(im,ax=axes.ravel().tolist(),label="OND accumulated rainfall (mm)",shrink=.8,extend="max")
    fig.suptitle("Indonesia OND2023 • same 1982–2010 training and model predictors • new predictand grid",fontsize=14)
    fig.savefig(OUT/"resolution_forecasts.png",dpi=180); plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(16,4.5),subplot_kw={"projection":projection},layout="constrained")
    for ax,method in zip(axes,["cca","pcr"]):
        field=(abs(common_forecasts[f"{method}_025_aggregated"]-truth)-abs(common_forecasts[f"{method}_1deg"]-truth)).isel(T=0)
        limit=max(1.,float(np.nanpercentile(abs(field.values),98)))
        im=ax.pcolormesh(field.X,field.Y,field,transform=projection,cmap="RdBu_r",vmin=-limit,vmax=limit)
        ax.add_geometries([geometry],projection,facecolor="none",edgecolor="#333333",linewidth=.3)
        ax.set_extent([94,142,-12,7]); ax.set_title(f"{method.upper()} • 0.25° aggregated minus 1° absolute error",fontsize=11)
        ax.gridlines(draw_labels={"bottom":"x","left":"y"},linewidth=.25,alpha=.4)
        fig.colorbar(im,ax=ax,label="mm • blue: finer fit lower error; red: coarser fit lower error",shrink=.8,extend="both")
    fig.savefig(OUT/"common_grid_error_changes.png",dpi=180); plt.close(fig)


if __name__=="__main__": main()
