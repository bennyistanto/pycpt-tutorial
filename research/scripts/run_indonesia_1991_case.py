"""Fit the audited1991–2020 case and compare periods on a common0.25° grid."""
from __future__ import annotations
import datetime as dt
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
from prepare_indonesia_1991_case import ROOT, OLD, PREVIOUS, TRAIN, main as prepare, read, sha
from run_indonesia_025_case import COMMON, historical_fields, forecast_metrics, weighted_mean, stack_forecasts

OUT=ROOT/"outputs"


def benchmark_hashes():
    saved={}
    for root,manifest,prefix in ((OLD,"case_manifest.json","outputs"),(OLD,"pcr-comparison/comparison_manifest.json","pcr-comparison/outputs"),(PREVIOUS,"case_manifest.json","outputs")):
        content=json.loads((root/manifest).read_text())
        for name,info in content["outputs"].items():
            path=root/prefix/name
            assert sha(path)==info["sha256"],str(path)
            saved[str(path)]=info["sha256"]
    return saved


def main():
    if (ROOT/"case_manifest.json").exists():
        print("Completed period comparison retained."); return
    prepare()
    audit=json.loads((ROOT/"continuity.json").read_text())
    assert audit["status"]=="PASS_COMPLETENESS_WITH_SOURCE_TRANSITION"
    assert audit["missing_or_nonfinite_monthly_values"]==0
    assert pycpt.__version__=="2.10.4"
    engine=Path(os.environ.get("CPT_BIN_DIR",""))/"CPT.x"
    assert engine==Path.home()/"miniforge3/envs/pycpt-tutorial/opt/cpt/bin/CPT.x"
    frozen=benchmark_hashes()
    x=read(ROOT/"inputs/cfsv2_hindcasts_ond.nc").precipitation
    f=read(OLD/"inputs/cfsv2_forecasts_ond.nc").precipitation
    obs=read(ROOT/"inputs/observations_chirps3_ond_025.nc")
    country=read(ROOT/"inputs/indonesia_analysis_mask_025.nc")
    y=obs.precipitation.sel(T=obs["T"].dt.year.isin(TRAIN))
    truth=obs.precipitation.sel(T=obs["T"].dt.year==2023)
    mask=country.analysis_mask.astype(bool); count=int(mask.sum())
    np.testing.assert_array_equal(x["T"],y["T"])
    np.testing.assert_array_equal(y["T"].dt.year,TRAIN)
    np.testing.assert_array_equal(f["T"],truth["T"])
    OUT.mkdir(parents=True,exist_ok=True)
    meta={"case_id":ROOT.name,"data_kind":"historical_replay","model":"NCEP CFSv2 ensemble mean","observation_product":"Local CHIRPS v3.0",
          "training_start_year":1991,"training_end_year":2020,"forecast_initialization":"2023-09-01","target_period":"2023-10-01/2023-12-31",
          "predictand_resolution_degrees":.25,"predictor_resolution_degrees":1.,"pycpt_version":"2.10.4","cpt_version":"17.8.3",
          "archive_transition":"The training source appends operational forecasts from April2011; no homogeneity correction applied",
          "validation_note":"Fixed modes; built-in leave5-out deterministic CV;2023 withheld; no probabilistic hindcast skill claim"}
    def save(ds,name,attrs=None):
        return save_netcdf(ds,OUT/name,metadata={**meta,**(attrs or {})},overwrite=True)
    results={}; timings={}; score_checks={}; probability_checks={}
    for method in ("cca","pcr"):
        config=dict(COMMON)
        if method=="cca": config.update(y_eof_modes=(3,3),cca_modes=(2,2))
        function=canonical_correlation_analysis if method=="cca" else principal_components_regression
        print("RUNNING",method,"training",[1991,2020],"cells",count,flush=True)
        start=time.monotonic()
        result=function(x,y,F=f,**config,cpt_kwargs={"outputdir":ROOT/f"cpt-{method}","log":ROOT/f"cpt-{method}-session.log","project_file":ROOT/f"cpt-{method}-commands.txt"})
        timings[method]=time.monotonic()-start
        h,fc,skill=[ds.reindex(X=y.X,Y=y.Y,method="nearest",tolerance=1e-3).where(mask) for ds in result[:3]]
        np.testing.assert_array_equal(h["T"].dt.year,TRAIN)
        np.testing.assert_array_equal(fc.S,pd.to_datetime(["2023-09-01"]))
        np.testing.assert_array_equal(fc.Ti,pd.to_datetime(["2023-10-01"]))
        np.testing.assert_array_equal(fc.Tf,pd.to_datetime(["2023-12-31"]))
        assert int(h.deterministic.count())==count*30
        for variable,multiplier in (("deterministic",1),("probabilistic",3),("prediction_error_variance",1)):
            assert int(fc[variable].count())==count*multiplier
        assert float(fc.probabilistic.min())>=0 and float(fc.probabilistic.max())<=100
        assert float(fc.prediction_error_variance.min())>=0
        np.testing.assert_allclose(fc.probabilistic.sum("C").isel(T=0).values[mask.values],100,atol=.1)
        direct=historical_fields(h.deterministic,y)
        np.testing.assert_allclose(direct.rmse,skill.root_mean_squared_error,atol=.01,rtol=1e-5)
        np.testing.assert_allclose(direct.pearson,skill.pearson,atol=1e-4,rtol=0)
        score_checks[method]={"maximum_native_direct_rmse_difference_mm":float(abs(direct.rmse-skill.root_mean_squared_error).max()),"maximum_native_direct_pearson_difference":float(abs(direct.pearson-skill.pearson).max())}
        probability_checks[method]={"maximum_sum_error_percentage_points":float(abs(fc.probabilistic.sum("C").where(mask)-100).max()),"negative_forecast_cells":int(((fc.deterministic.isel(T=0)<0)&mask).sum())}
        results[method]={"hindcasts":h,"forecast":fc,"skill":skill,"config":config}
        for suffix,ds in (("hindcasts",h),("forecast_2023",fc),("native_skill",skill)):
            save(ds,f"{method}_{suffix}_025.nc",{"calibration":method.upper()})
        save(result[3],f"{method}_predictor_patterns_025.nc",{"calibration":method.upper()})
        if method=="cca": save(result[4],"cca_predictand_patterns_025.nc",{"calibration":"CCA"})
        print("COMPLETED",method,"seconds",timings[method],flush=True)

    old_country=read(PREVIOUS/"outputs/indonesia_analysis_mask_025.nc")
    old_obs=read(PREVIOUS/"outputs/observations_chirps3_ond_025.nc").precipitation
    old_y=old_obs.sel(T=old_obs["T"].dt.year<=2010)
    old_results={m:{"forecast":read(PREVIOUS/f"outputs/{m}_forecast_2023_025.nc"),"hindcasts":read(PREVIOUS/f"outputs/{m}_hindcasts_025.nc")} for m in ("cca","pcr")}
    common_mask=mask&old_country.analysis_mask.astype(bool)
    # Fit masks use training years only. Verification availability is a separate
    # common evaluation mask, not an input into either fit.
    evaluation_mask=common_mask&truth.isel(T=0).notnull()
    xr.testing.assert_allclose(country.country_land_weight,old_country.country_land_weight)
    xr.testing.assert_allclose(truth.where(evaluation_mask),old_obs.sel(T=old_obs["T"].dt.year==2023).where(evaluation_mask))
    weights=country.country_land_weight.where(evaluation_mask,0)
    predictions={"climatology_1982_2010":old_y.mean("T").expand_dims(T=f["T"]),"climatology_1991_2020":y.mean("T").expand_dims(T=f["T"]),
                 "raw_cfsv2":f.interp(X=y.X,Y=y.Y),"cca_1982_2010":old_results["cca"]["forecast"].deterministic,"pcr_1982_2010":old_results["pcr"]["forecast"].deterministic,
                 "cca_1991_2020":results["cca"]["forecast"].deterministic,"pcr_1991_2020":results["pcr"]["forecast"].deterministic}
    predictions={key:value.where(evaluation_mask) for key,value in predictions.items()}
    for key,value in predictions.items(): assert int(value.count())==int(evaluation_mask.sum()),key
    comparison_meta={"data_kind":"period_sensitivity_comparison","training_periods_compared":"1982–2010 (29seasons) versus1991–2020 (30seasons)",
                     "comparison_rule":"Identical0.25degree observations/cells/native countryweights; common training masks and available2023 observations",
                     "probability_note":"CPT category references: older fits1991–2010,recent1991–2020; see research/reports/METHODOLOGY_AUDIT.md; this comparison contains deterministic rainfall only"}
    save(stack_forecasts(predictions,truth.where(evaluation_mask),f.S),"period_forecast_comparison_025.nc",comparison_meta)
    save(xr.Dataset({"new_training_mask":country.analysis_mask,"old_training_mask":old_country.analysis_mask,
                     "common_training_mask":common_mask.astype("int8"),"evaluation_mask":evaluation_mask.astype("int8"),"evaluation_country_land_weight":weights}),"period_comparison_footprint_025.nc",comparison_meta)
    save(obs,"observations_chirps3_ond_025.nc",{"data_kind":"observed_reference"})
    save(country,"indonesia_analysis_mask_025.nc")
    save(x.to_dataset(),"cfsv2_training_predictors.nc")
    save(f.to_dataset(),"cfsv2_forecast_predictor_2023.nc",{"data_kind":"unchanged_forecast_input"})
    save(read(ROOT/"inputs/cfsv2_monthly_continuity.nc"),"cfsv2_monthly_continuity.nc",{"data_kind":"input_completeness_audit"})

    historical={}; fields=[]; variants=[]; shared_predictions={}
    overlap_years=np.arange(1991,2011)
    for period,train_y,models,predictors in (("1982_2010",old_y,old_results,read(OLD/"inputs/cfsv2_hindcasts_ond.nc").precipitation),("1991_2020",y,results,x)):
        for method in ("raw_cfsv2","cca","pcr"):
            pred=predictors.interp(X=y.X,Y=y.Y) if method=="raw_cfsv2" else models[method]["hindcasts"].deterministic
            pred=pred.where(evaluation_mask); reference=train_y.where(evaluation_mask)
            ds=historical_fields(pred,reference)
            key=f"{method}_{period}"; fields.append(ds); variants.append(key)
            historical[key]={"mean_grid_rmse_mm":weighted_mean(ds.rmse,weights),"mean_grid_pearson":weighted_mean(ds.pearson,weights),"years":[int(train_y["T"].dt.year.min()),int(train_y["T"].dt.year.max())]}
            shared_predictions[key]=pred.sel(T=pred["T"].dt.year.isin(overlap_years)).reset_coords(drop=True)
    save(xr.concat(fields,dim=pd.Index(variants,name="forecast_variant")),"training_period_historical_diagnostics_025.nc",{**comparison_meta,"warning":"Each variant uses its own training-period verification years; full-period summaries are not like-for-like skill comparisons"})
    shared_truth=y.sel(T=y["T"].dt.year.isin(overlap_years)).where(evaluation_mask)
    shared_fields={key:historical_fields(pred,shared_truth) for key,pred in shared_predictions.items()}
    shared=xr.concat(list(shared_predictions.values()),dim=pd.Index(list(shared_predictions),name="forecast_variant"),join="exact")
    save(xr.Dataset({"deterministic":shared,"observed_rainfall":shared_truth}),"shared_year_hindcasts_1991_2010_025.nc",{**comparison_meta,"warning":"Common verifying years, but training samples/folds differ; older CV also uses1982–1990 and newer CV2011–2020"})
    save(xr.concat(list(shared_fields.values()),dim=pd.Index(list(shared_fields),name="forecast_variant")),"shared_year_historical_diagnostics_025.nc",{**comparison_meta,"warning":"Common years1991–2010; training sets/folds still differ"})
    forecast_scores={key:forecast_metrics(pred,truth.where(evaluation_mask),weights) for key,pred in predictions.items()}
    report={"case_id":ROOT.name,"training_years":[1991,2020],"comparison_training_years":[1982,2010],"training_sample_counts":{"old":29,"new":30},"target":"OND2023",
            "new_training_cells":count,"old_training_cells":int(old_country.analysis_mask.sum()),"common_training_cells":int(common_mask.sum()),"evaluation_cells":int(evaluation_mask.sum()),
            "fraction_original_fine_land_weight_retained":float(weights.sum()/old_country.country_land_weight.where(old_country.analysis_mask.astype(bool),0).sum()),
            "forecast_metrics_common_025":forecast_scores,"training_period_historical_metrics_descriptive_only":historical,
            "shared_1991_2010_historical_metrics":{key:{"mean_grid_rmse_mm":weighted_mean(ds.rmse,weights),"mean_grid_pearson":weighted_mean(ds.pearson,weights)} for key,ds in shared_fields.items()},
            "fit_elapsed_seconds":timings,"native_score_checks":score_checks,"probability_checks":probability_checks,
            "continuity_status":audit["status"],"limitations":["1991–2020 blends reforecasts and operational forecasts","Changing period also changes training sample count29to30","One held-out2023 target is not general skill evidence","Probability categories depend on calibration period; no probabilistic skill comparison","Historical CV samples/folds differ, even on shared verification years"]}
    (ROOT/"metrics.json").write_text(json.dumps(report,indent=2)+"\n")
    plot(predictions,truth,evaluation_mask)
    assert all(sha(Path(path))==value for path,value in frozen.items())
    input_paths=[ROOT/"inputs/cfsv2_hindcasts_ond.nc",ROOT/"inputs/observations_chirps3_ond_025.nc",ROOT/"inputs/indonesia_analysis_mask_025.nc",OLD/"inputs/cfsv2_forecasts_ond.nc",OLD/"inputs/indonesia_boundary.geojson"]
    manifest={"case_id":ROOT.name,"completed_at":dt.datetime.now(dt.timezone.utc).isoformat(),"engine":str(engine),"engine_sha256":sha(engine),
              "configurations":{m:r["config"] for m,r in results.items()},"input_sha256":{str(p):sha(p) for p in input_paths},"unchanged_benchmark_artifacts_sha256":frozen,
              "outputs":{p.name:{"bytes":p.stat().st_size,"sha256":sha(p)} for p in sorted(OUT.iterdir()) if p.is_file()},
              "pipeline_script_sha256":{str(p.relative_to(Path(__file__).parents[2])):sha(p) for p in (Path(__file__),Path(__file__).with_name("prepare_indonesia_1991_case.py"),Path(__file__).with_name("prepare_indonesia_025_case.py"),Path(__file__).with_name("run_indonesia_025_case.py"),Path(__file__).parents[2]/"pycpt_tutorial/country_grid.py",Path(__file__).parents[2]/"pycpt_tutorial/export.py")},"metrics":report}
    (ROOT/"case_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print("CASE_COMPLETE",json.dumps(report,indent=2),flush=True)


def plot(predictions,truth,mask):
    geometry=shapely.geometry.shape(json.loads((OLD/"inputs/indonesia_boundary.geojson").read_text()))
    projection=ccrs.PlateCarree()
    fig,axes=plt.subplots(2,2,figsize=(16,8),subplot_kw={"projection":projection},layout="constrained")
    keys=["cca_1982_2010","cca_1991_2020","pcr_1982_2010","pcr_1991_2020"]
    vmax=float(np.nanpercentile(np.concatenate([predictions[key].values.ravel() for key in keys]),99))
    def decorate(ax,title):
        ax.add_geometries([geometry],projection,facecolor="none",edgecolor="#333333",linewidth=.3)
        ax.set_extent([94,142,-12,7]); ax.set_title(title,fontsize=12)
        ax.gridlines(draw_labels={"bottom":"x","left":"y"},linewidth=.25,alpha=.4)
    for ax,key in zip(axes.ravel(),keys):
        da=predictions[key].isel(T=0)
        im=ax.pcolormesh(da.X,da.Y,da,transform=projection,cmap="YlGnBu",vmin=0,vmax=vmax)
        method,first,last=key.split("_"); decorate(ax,f"{method.upper()} • training {first}–{last}")
    fig.colorbar(im,ax=axes.ravel().tolist(),label="OND accumulated rainfall(mm)",shrink=.8,extend="max")
    fig.suptitle("Indonesia OND2023 • 0.25° forecasts • training-period sensitivity",fontsize=14)
    fig.savefig(OUT/"training_period_forecasts.png",dpi=180); plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(16,4.5),subplot_kw={"projection":projection},layout="constrained")
    for ax,method in zip(axes,("cca","pcr")):
        da=(abs(predictions[f"{method}_1991_2020"]-truth)-abs(predictions[f"{method}_1982_2010"]-truth)).where(mask).isel(T=0)
        limit=max(1.,float(np.nanpercentile(abs(da.values),98)))
        im=ax.pcolormesh(da.X,da.Y,da,transform=projection,cmap="RdBu_r",vmin=-limit,vmax=limit)
        decorate(ax,f"{method.upper()} • newer minus older training: absolute error")
        fig.colorbar(im,ax=ax,label="Change in absolute error (mm)",shrink=.8,extend="both")
    fig.suptitle("Indonesia OND 2023 • blue: newer training has lower error; red: older has lower error",fontsize=12)
    fig.savefig(OUT/"training_period_error_changes.png",dpi=180); plt.close(fig)


def refresh_figures():
    """Render saved comparisons without repeating model fits or changing data."""
    manifest=json.loads((ROOT/"case_manifest.json").read_text())
    for name,info in manifest["outputs"].items(): assert sha(OUT/name)==info["sha256"],name
    benchmark_hashes()
    ds=read(OUT/"period_forecast_comparison_025.nc")
    footprint=read(OUT/"period_comparison_footprint_025.nc")
    predictions={str(key):ds.forecast_rainfall.sel(forecast_variant=key,drop=True) for key in ds.forecast_variant.values}
    plot(predictions,ds.observed_rainfall,footprint.evaluation_mask.astype(bool))
    for name in ("training_period_forecasts.png","training_period_error_changes.png"):
        p=OUT/name; manifest["outputs"][name]={"bytes":p.stat().st_size,"sha256":sha(p)}
    manifest["pipeline_script_sha256"]["scripts/run_indonesia_1991_case.py"]=sha(Path(__file__))
    manifest["figure_refresh"]={"at":dt.datetime.now(dt.timezone.utc).isoformat(),"reason":"Shorter colourbar labels and separate sign legend after visual review; all model/NetCDF outputs retained"}
    (ROOT/"case_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print("FIGURES_REFRESHED_FROM_SAVED_COMPARISON")


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-figures",action="store_true",help="Redraw saved results without running CPT")
    args=parser.parse_args()
    if args.refresh_figures: refresh_figures()
    else: main()
