"""Run independently calibrated all-season fixed-period holdouts and save NetCDFs."""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import cartopy.crs as ccrs
import shapely.geometry
import numpy as np
import pandas as pd
import pycpt
from cptcore import canonical_correlation_analysis, principal_components_regression
import xarray as xr

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from pycpt_tutorial.export import save_netcdf
from pycpt_tutorial.seasons import SEASONS, season_window
from pycpt_tutorial.cpt_dates import verified_midnight_reader
from prepare_indonesia_all_seasons import ROOT, PERIODS, EVAL_YEARS, OLD, RECENT, HOLDOUTS, read, sha
from run_indonesia_025_case import COMMON, historical_fields, forecast_metrics, stack_forecasts
from run_indonesia_ond_holdouts import freeze_benchmarks

OUT=ROOT/"outputs"
VARIANTS=("raw_cfsv2","climatology_1983_2010","climatology_1991_2020","cca_1983_2010","cca_1991_2020","pcr_1983_2010","pcr_1991_2020")
SETS={"all_four_years":EVAL_YEARS,"additional_years":[2021,2022,2024]}
META={"case_id":ROOT.name,"year_convention":"Season ending year;NDJ/DJF start in preceding year","grid_resolution_degrees":.25,
      "older_training_period":"1983–2010(28seasons)","recent_training_period":"1991–2020(30seasons)","verification_years":"2021,2022,2023,2024",
      "model":"CFSv2 ensemble mean at1degree","observations":"CHIRPS3 country-land weighted seasonal accumulation",
      "validation_note":"All holdouts after training target periods; seasonal training masks only; fixed mode counts; retrospective current-vintage data",
      "archive_note":"Source appends operational forecasts fromApril2011; completeness does not establish homogeneity","probability_note":"Native categories use effective CPT climatological dates, not necessarily training dates; rainfall auto-zero-bounded; see research/reports/METHODOLOGY_AUDIT.md; no probabilistic skill claim"}


def save(ds,name,attrs=None):
    return save_netcdf(ds,OUT/name,metadata={**META,**(attrs or {})},overwrite=True)


def freeze_all():
    frozen=freeze_benchmarks()
    m=json.loads((HOLDOUTS/"case_manifest.json").read_text())
    for name,info in m["outputs"].items():
        p=HOLDOUTS/"outputs"/name; assert sha(p)==info["sha256"]
        frozen[str(p)]=info["sha256"]
    return frozen


def fit_season(season):
    folder=ROOT/season
    assert (folder/"preparation.json").exists(),f"Prepare{season} first"
    inputs={name:read(folder/name) for name in ("predictors.nc","observations.nc","footprint.nc")}
    model=inputs["predictors.nc"].precipitation; obs=inputs["observations.nc"].precipitation; footprint=inputs["footprint.nc"]
    f=model.sel(T=model.season_year.isin(EVAL_YEARS))
    np.testing.assert_array_equal(f.season_year,EVAL_YEARS)
    windows=[season_window(season,year) for year in EVAL_YEARS]
    for period,years in PERIODS.items():
        x=model.sel(T=model.season_year.isin(years))
        y=obs.sel(T=obs.season_year.isin(years))
        mask=footprint.analysis_mask.sel(training_period=period,drop=True).astype(bool)
        y=y.where(mask); n=int(mask.sum())
        np.testing.assert_array_equal(x["T"],y["T"])
        np.testing.assert_array_equal(x.season_year,years)
        assert pd.Timestamp(y.Tf.max().item())<min(window.initialization for window in windows)
        for method in ("cca","pcr"):
            key=f"{season}_{method}_{period}"; record_path=folder/f"{method}_{period}_fit.json"
            if record_path.exists():
                record=json.loads(record_path.read_text())
                for name,expected in record["outputs_sha256"].items(): assert sha(OUT/name)==expected
                print("FIT_REUSED",key,flush=True); continue
            config=dict(COMMON)
            if method=="cca": config.update(y_eof_modes=(3,3),cca_modes=(2,2))
            function=canonical_correlation_analysis if method=="cca" else principal_components_regression
            # Extra label coordinates are for the audit, not CPT's text protocol.
            xc=x.drop_vars("season_year"); yc=y.drop_vars("season_year"); fc_input=f.drop_vars("season_year")
            print("FITTING",key,"samples",len(years),"cells",n,"forecast_years",EVAL_YEARS,flush=True)
            started=time.monotonic()
            expected_dates=[pd.Timestamp(value).to_pydatetime() for value in np.concatenate([xc.S.values,fc_input.S.values])]
            with verified_midnight_reader(function,expected_dates) as date_repairs:
                result=function(xc,yc,F=fc_input,**config,cpt_kwargs={"outputdir":ROOT/f"cpt-{key}","log":ROOT/f"cpt-{key}.log","project_file":ROOT/f"cpt-{key}-commands.txt"})
            elapsed=time.monotonic()-started
            h,fc,skill=[ds.reindex(X=y.X,Y=y.Y,method="nearest",tolerance=1e-3).where(mask) for ds in result[:3]]
            np.testing.assert_array_equal(h["T"],x["T"])
            np.testing.assert_array_equal(fc.S,pd.to_datetime([window.initialization for window in windows]))
            np.testing.assert_array_equal(fc.Ti,pd.to_datetime([window.start for window in windows]))
            np.testing.assert_array_equal(fc.Tf,pd.to_datetime([window.end for window in windows]))
            np.testing.assert_array_equal(fc["T"],f["T"])
            assert int(h.deterministic.count())==len(years)*n
            for variable,multiplier in (("deterministic",1),("probabilistic",3),("prediction_error_variance",1)):
                assert int(fc[variable].count())==4*n*multiplier,(key,variable,int(fc[variable].count()),4*n*multiplier)
            assert float(fc.probabilistic.min())>=0 and float(fc.probabilistic.max())<=100
            assert float(fc.prediction_error_variance.min())>=0
            np.testing.assert_allclose(fc.probabilistic.sum("C").transpose("T","Y","X").values[:,mask.values],100,atol=.1)
            direct=historical_fields(h.deterministic,y.drop_vars("season_year"))
            np.testing.assert_allclose(direct.rmse,skill.root_mean_squared_error,atol=.01,rtol=1e-5)
            np.testing.assert_allclose(direct.pearson,skill.pearson,atol=1e-4,rtol=0)
            fc=fc.assign_coords(season_year=("T",EVAL_YEARS))
            h=h.assign_coords(season_year=("T",years))
            names=[]
            for suffix,ds in (("forecasts",fc),("hindcasts",h),("native_skill",skill)):
                name=f"{key}_{suffix}.nc"; save(ds,name,{"season":season,"calibration":method.upper(),"training_period":period}); names.append(name)
            record={"season":season,"method":method,"training_period":period,"config":config,"training_samples":len(years),"training_cells":n,"forecast_cases":4,"elapsed_seconds":elapsed,
                    "native_direct_rmse_max_difference_mm":float(abs(direct.rmse-skill.root_mean_squared_error).max()),"native_direct_pearson_max_difference":float(abs(direct.pearson-skill.pearson).max()),
                    "probability_sum_max_error_percentage_points":float(abs(fc.probabilistic.sum("C").where(mask)-100).max()),
                    "date_parsing_normalizations":date_repairs,"input_sha256":{name:sha(folder/name) for name in inputs},"outputs_sha256":{name:sha(OUT/name) for name in names}}
            record_path.write_text(json.dumps(record,indent=2)+"\n")
            print("FIT_COMPLETE",key,"seconds",round(elapsed,2),flush=True)


def summarize():
    assert (ROOT/"availability.json").exists()
    availability=json.loads((ROOT/"availability.json").read_text())
    footprint=read(ROOT/"evaluation_footprint.nc"); mask=footprint.evaluation_mask.astype(bool); weights=footprint.evaluation_weight
    save(footprint,"evaluation_footprint.nc")
    annual=np.empty((12,7,4,3)); pooled=np.empty((12,7,2,3)); field_sets=[]; fits=[]
    for si,season in enumerate(SEASONS):
        folder=ROOT/season; model=read(folder/"predictors.nc").precipitation; obs=read(folder/"observations.nc").precipitation
        truth=obs.sel(T=obs.season_year.isin(EVAL_YEARS)).where(mask)
        f=model.sel(T=model.season_year.isin(EVAL_YEARS))
        predictions={"raw_cfsv2":f.interp(X=truth.X,Y=truth.Y).where(mask)}
        for period,years in PERIODS.items():
            training=obs.sel(T=obs.season_year.isin(years))
            predictions[f"climatology_{period}"]=training.mean("T").expand_dims(T=f["T"]).where(mask)
            for method in ("cca","pcr"):
                fc=read(OUT/f"{season}_{method}_{period}_forecasts.nc")
                predictions[f"{method}_{period}"]=fc.deterministic.where(mask)
                fits.append(json.loads((folder/f"{method}_{period}_fit.json").read_text()))
        predictions={key:predictions[key] for key in VARIANTS}
        clean_truth=truth.drop_vars("season_year")
        predictions={key:da.drop_vars("season_year",errors="ignore") for key,da in predictions.items()}
        comparison=stack_forecasts(predictions,clean_truth,f.S).assign_coords(season_year=("T",EVAL_YEARS))
        save(comparison,f"{season}_forecast_comparison.nc",{"season":season,"evaluation_rule":"Identical common cells/weights across12seasons,2periods,4years"})
        for vi,key in enumerate(VARIANTS):
            for yi,year in enumerate(EVAL_YEARS):
                score=forecast_metrics(predictions[key].isel(T=[yi]),clean_truth.isel(T=[yi]),weights)
                annual[si,vi,yi]=[score[name] for name in ("rmse_mm","mae_mm","bias_mm")]
        season_fields=[]
        for gi,(group,years) in enumerate(SETS.items()):
            indices=[EVAL_YEARS.index(year) for year in years]
            pooled[si,:,gi,0]=np.sqrt(np.mean(annual[si,:,:,0][:,indices]**2,axis=1))
            pooled[si,:,gi,1:]=np.mean(annual[si,:,:,:][:,indices,1:],axis=1)
            error=comparison.error.isel(T=indices).drop_vars(["season_year","S","Ti","Tf"],errors="ignore")
            fields=xr.Dataset({"rmse":np.sqrt((error**2).mean("T")),"mae":abs(error).mean("T"),"bias":error.mean("T")})
            season_fields.append(fields)
        field_sets.append(xr.concat(season_fields,dim=pd.Index(list(SETS),name="evaluation_set")))
        for name in ("predictors.nc","observations.nc","footprint.nc","monthly_audit.nc"):
            save(read(folder/name),f"{season}_{name}",{"season":season,"data_kind":"audited_inputs_and_masks"})
    scores=xr.Dataset()
    coords={"season":list(SEASONS),"forecast_variant":list(VARIANTS),"season_year":EVAL_YEARS,"evaluation_set":list(SETS)}
    for index,name in enumerate(("rmse","mae","bias")):
        scores[name]=xr.DataArray(annual[:,:,:,index],dims=("season","forecast_variant","season_year"),coords={d:coords[d] for d in ("season","forecast_variant","season_year")},attrs={"units":"mm"})
        scores["pooled_"+name]=xr.DataArray(pooled[:,:,:,index],dims=("season","forecast_variant","evaluation_set"),coords={d:coords[d] for d in ("season","forecast_variant","evaluation_set")},attrs={"units":"mm"})
    for coord,attribute in (("S","initialization"),("Ti","start"),("Tf","end")):
        scores=scores.assign_coords({coord:(("season","season_year"),np.array([[np.datetime64(getattr(season_window(season,year),attribute),"ns") for year in EVAL_YEARS] for season in SEASONS]))})
    save(scores,"verification_scores.nc",{"pooling_rule":"Square root of mean annual spatialMSE; equal year weights/common spatial weights; windows overlap, not independent","additional_years":"2021,2022,2024"})
    grid=xr.concat(field_sets,dim=pd.Index(SEASONS,name="season"))
    for var in grid.values(): var.attrs["units"]="mm"
    save(grid,"multiyear_error_fields.nc",{"warning":"Only4years; no significance, reliability or probabilistic skill inference"})
    control=ond_control(weights,mask)
    rows=[]
    for si,season in enumerate(SEASONS):
        values={key:{"rmse_mm":float(pooled[si,vi,0,0]),"mae_mm":float(pooled[si,vi,0,1]),"bias_mm":float(pooled[si,vi,0,2])} for vi,key in enumerate(VARIANTS)}
        best=min(values,key=lambda key:values[key]["rmse_mm"])
        rows.append({"season":season,"pooled_four_year_metrics":values,"lowest_rmse_variant":best,
                     "recent_training_lower_rmse_years":{method:[year for yi,year in enumerate(EVAL_YEARS) if annual[si,VARIANTS.index(method+"_1991_2020"),yi,0]<annual[si,VARIANTS.index(method+"_1983_2010"),yi,0]] for method in ("cca","pcr")}})
    report={"case_id":ROOT.name,"training_periods":{p:[years[0],years[-1],len(years)] for p,years in PERIODS.items()},"evaluation_years":EVAL_YEARS,
            "seasons":rows,"common_evaluation_cells":int(mask.sum()),"country_land_weight_retained":availability["approximate_country_land_weight_retained"],
            "calibrated_forecast_cases":192,"CPT_calls":len(fits),"fit_elapsed_seconds_total":sum(item["elapsed_seconds"] for item in fits),"ond_control":control,
            "limitations":["Four ending-year labels; adjacent rolling seasons share months and are not independent","Common older period changed to1983–2010 because1981initializations unavailable","28vs30trainingseasons; fixed mode counts, no test-year tuning","Current-vintage observations/forecast archive; source operational append fromApril2011","No significance or probabilistic skill claim"]}
    (ROOT/"metrics.json").write_text(json.dumps(report,indent=2)+"\n")
    write_calibration_gains(scores)
    plot(scores)
    return report


def ond_control(weights,mask):
    old=read(HOLDOUTS/"outputs/forecast_comparison_025.nc")
    new=read(OUT/"OND_forecast_comparison.nc")
    # A legacy scalar CHIRPS selection-time coordinate can accompany the old
    # comparison. Compare actual forecast/target/grid dates explicitly, then
    # compare values without unrelated non-index metadata coordinates.
    for coordinate in ("T","S","Ti","Tf","Y","X"):
        np.testing.assert_array_equal(old[coordinate],new[coordinate])
    xr.testing.assert_allclose(old.observed_rainfall.where(mask).reset_coords(drop=True),new.observed_rainfall.where(mask).reset_coords(drop=True))
    predictions={str(key):old.forecast_rainfall.sel(forecast_variant=key,drop=True).where(mask) for key in old.forecast_variant.values}
    for method in ("cca","pcr"):
        predictions[method+"_1983_2010"]=new.forecast_rainfall.sel(forecast_variant=method+"_1983_2010",drop=True)
    predictions["climatology_1983_2010"]=new.forecast_rainfall.sel(forecast_variant="climatology_1983_2010",drop=True)
    comparison=stack_forecasts(predictions,new.observed_rainfall.drop_vars("season_year"),new.S)
    save(comparison,"OND_training_period_bridge.nc",{"season":"OND","purpose":"Separate dropping1982from all-season effect; originals remain unchanged"})
    report={}
    for method in ("cca","pcr"):
        recent_old=old.forecast_rainfall.sel(forecast_variant=method+"_1991_2020",drop=True).where(mask)
        recent_new=new.forecast_rainfall.sel(forecast_variant=method+"_1991_2020",drop=True)
        difference=float(abs(recent_old-recent_new).max()); assert difference<.01
        report[method]={"recent_four_year_batch_vs_prior_max_difference_mm":difference,"per_year_old82_old83_recent_rmse_mm":{str(year):{period:forecast_metrics(comparison.forecast_rainfall.sel(forecast_variant=method+"_"+period,drop=True).isel(T=[yi]),comparison.observed_rainfall.isel(T=[yi]),weights)["rmse_mm"] for period in ("1982_2010","1983_2010","1991_2020")} for yi,year in enumerate(EVAL_YEARS)}}
    return report


def plot(scores):
    pooled=scores.pooled_rmse.sel(evaluation_set="all_four_years")
    labels=["Raw","Clim 83–10","Clim 91–20","CCA 83–10","CCA 91–20","PCR 83–10","PCR 91–20"]
    fig,ax=plt.subplots(figsize=(12,7.5),layout="constrained")
    values=pooled.transpose("season","forecast_variant").values
    im=ax.imshow(values,cmap="YlGnBu",aspect="auto")
    ax.set_xticks(range(7),labels,rotation=25,ha="right"); ax.set_yticks(range(12),SEASONS)
    for i in range(12):
        for j in range(7):
            red,green,blue,_=im.cmap(im.norm(values[i,j]))
            luminance=.2126*red+.7152*green+.0722*blue
            ax.text(j,i,f"{values[i,j]:.0f}",ha="center",va="center",fontsize=10,color="white" if luminance<.45 else "#111")
    fig.colorbar(im,ax=ax,label="Pooled spatial RMSE (mm)",shrink=.8)
    ax.set_title("Indonesia • 12 seasons • 2021–2024 • 0.25° common footprint\nFixed lead, older 1983–2010 versus recent 1991–2020",fontsize=13)
    fig.savefig(OUT/"seasonal_rmse_matrix.png",dpi=180); plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(14,6),layout="constrained",sharex=True)
    for ax,method in zip(axes,("cca","pcr")):
        old=pooled.sel(forecast_variant=method+"_1983_2010").values
        recent=pooled.sel(forecast_variant=method+"_1991_2020").values
        improvement=100*(old-recent)/old
        ax.barh(np.arange(12),improvement,color=np.where(improvement>=0,"#2878aa","#c75843"))
        ax.set_yticks(np.arange(12),SEASONS); ax.invert_yaxis(); ax.axvline(0,color="#333",linewidth=.8)
        ax.set_xlabel("RMSE reduction with recent training (%)"); ax.set_title(method.upper()); ax.grid(axis="x",alpha=.2)
    fig.suptitle("Training-period sensitivity • positive: recent lower error; negative: older lower error",fontsize=13)
    fig.savefig(OUT/"training_period_sensitivity.png",dpi=180); plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,6),layout="constrained")
    for key,label,style in (("cca_1983_2010","CCA 1983–2010","--"),("cca_1991_2020","CCA 1991–2020","-"),("pcr_1983_2010","PCR 1983–2010","--"),("pcr_1991_2020","PCR 1991–2020","-")):
        ax.plot(np.arange(12),scores.pooled_bias.sel(forecast_variant=key,evaluation_set="all_four_years"),label=label,linestyle=style,marker="o",color="#176ba1" if key.startswith("cca") else "#c47519")
    ax.set_xticks(np.arange(12),SEASONS); ax.axhline(0,color="#333",linewidth=.8); ax.set_ylabel("Pooled bias (mm)"); ax.grid(alpha=.2); ax.legend(ncol=2)
    ax.set_title("Indonesia 2021–2024 • seasonal bias trades off with RMSE")
    fig.savefig(OUT/"seasonal_bias.png",dpi=180); plt.close(fig)
    fields=read(OUT/"multiyear_error_fields.nc").rmse.sel(evaluation_set="all_four_years")
    gains={method:fields.sel(forecast_variant=method+"_1983_2010",drop=True)-fields.sel(forecast_variant=method+"_1991_2020",drop=True) for method in ("cca","pcr")}
    limit=max(10.,float(np.nanpercentile(abs(np.concatenate([da.values.ravel() for da in gains.values()])),98)))
    geometry=shapely.geometry.shape(json.loads((OLD/"inputs/indonesia_boundary.geojson").read_text()))
    projection=ccrs.PlateCarree()
    for method in ("cca","pcr"):
        fig,axes=plt.subplots(6,2,figsize=(14,17),subplot_kw={"projection":projection},layout="constrained")
        for ax,season in zip(axes.ravel(),SEASONS):
            da=gains[method].sel(season=season)
            im=ax.pcolormesh(da.X,da.Y,da,transform=projection,cmap="RdBu",vmin=-limit,vmax=limit)
            ax.add_geometries([geometry],projection,facecolor="none",edgecolor="#333",linewidth=.25)
            ax.set_extent([94,142,-12,7]); ax.set_title(season,fontsize=10)
            grid=ax.gridlines(draw_labels={"bottom":"x","left":"y"},linewidth=.2,alpha=.3,x_inline=False,y_inline=False)
            grid.xlocator=mticker.FixedLocator([100,110,120,130,140]); grid.ylocator=mticker.FixedLocator([-10,-5,0,5]); grid.xlabel_style={"size":7}; grid.ylabel_style={"size":7}
        fig.colorbar(im,ax=axes.ravel().tolist(),label="Older minus recent pooled RMSE (mm)",shrink=.75,extend="both")
        fig.suptitle(f"{method.upper()} • 2021–2024 • blue: recent training lower error; red: older lower error",fontsize=12)
        fig.savefig(OUT/f"{method}_period_gain_maps.png",dpi=170); plt.close(fig)


def refresh_figures():
    manifest=json.loads((ROOT/"case_manifest.json").read_text())
    for name,info in manifest["outputs"].items(): assert sha(OUT/name)==info["sha256"]
    freeze_all()
    scores=read(OUT/"verification_scores.nc")
    write_calibration_gains(scores)
    plot(scores)
    manifest["outputs"]={p.name:{"bytes":p.stat().st_size,"sha256":sha(p)} for p in sorted(OUT.iterdir()) if p.is_file()}
    manifest["pipeline_script_sha256"]["scripts/run_indonesia_all_seasons.py"]=sha(Path(__file__))
    manifest["figure_refresh"]={"at":dt.datetime.now(dt.timezone.utc).isoformat(),"reason":"Final labels, geographic maps and MSE-skill diagnostics from saved scores; no model fits repeated"}
    (ROOT/"case_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print("FIGURES_REFRESHED",flush=True)


def write_calibration_gains(scores):
    """Express deterministic MSE gains relative to matched climatology and raw."""
    variants=[f"{method}_{period}" for method in ("cca","pcr") for period in PERIODS]
    fields=[]
    for key in variants:
        period=key.split("_",1)[1]
        calibrated=scores.pooled_rmse.sel(forecast_variant=key,drop=True)
        climatology=scores.pooled_rmse.sel(forecast_variant="climatology_"+period,drop=True)
        raw=scores.pooled_rmse.sel(forecast_variant="raw_cfsv2",drop=True)
        ds=xr.Dataset({"mse_skill_vs_climatology":1-(calibrated/climatology)**2,"mse_skill_vs_raw":1-(calibrated/raw)**2,
                       "rmse_reduction_vs_climatology":climatology-calibrated})
        ds.mse_skill_vs_climatology.attrs={"units":"1","interpretation":"1−MSEcalibrated/MSEclimatology; positive=lower error than own-period climatology"}
        ds.mse_skill_vs_raw.attrs={"units":"1","interpretation":"1−MSEcalibrated/MSEraw; positive=lower error than raw model"}
        ds.rmse_reduction_vs_climatology.attrs={"units":"mm"}
        fields.append(ds)
    ds=xr.concat(fields,dim=pd.Index(variants,name="calibrated_variant"))
    save(ds,"calibration_gains.nc",{"scope":"Deterministic descriptive gains from pooled errors; no significance/probabilistic skill claim"})


def main(selected=SEASONS,fit_only=False,wait_for_inputs=False):
    OUT.mkdir(parents=True,exist_ok=True)
    frozen=freeze_all()
    assert pycpt.__version__=="2.10.4"
    engine=Path(os.environ.get("CPT_BIN_DIR",""))/"CPT.x"
    assert engine==Path.home()/"miniforge3/envs/pycpt-tutorial/opt/cpt/bin/CPT.x"
    if (ROOT/"case_manifest.json").exists(): print("Completed all-season benchmark retained."); return
    for season in selected:
        last_notice=0.
        while wait_for_inputs and not (ROOT/season/"preparation.json").exists():
            if time.monotonic()-last_notice>60:
                print("WAITING_FOR_AUDITED_INPUTS",season,flush=True); last_notice=time.monotonic()
            time.sleep(10)
        fit_season(season)
    if fit_only: return
    assert set(selected)==set(SEASONS)
    while wait_for_inputs and not (ROOT/"availability.json").exists(): time.sleep(5)
    report=summarize()
    assert all(sha(Path(path))==expected for path,expected in frozen.items())
    manifest={"case_id":ROOT.name,"completed_at":dt.datetime.now(dt.timezone.utc).isoformat(),"engine":str(engine),"engine_sha256":sha(engine),"unchanged_benchmark_artifacts_sha256":frozen,
              "outputs":{p.name:{"bytes":p.stat().st_size,"sha256":sha(p)} for p in sorted(OUT.iterdir()) if p.is_file()},"input_sha256":{str(p.relative_to(ROOT)):sha(p) for season in SEASONS for p in (ROOT/season).glob("*.nc")},
              "pipeline_script_sha256":{str(p.relative_to(Path(__file__).parents[2])):sha(p) for p in (Path(__file__),Path(__file__).with_name("prepare_indonesia_all_seasons.py"),Path(__file__).parents[2]/"pycpt_tutorial/seasons.py",Path(__file__).parents[2]/"pycpt_tutorial/country_grid.py",Path(__file__).parents[2]/"pycpt_tutorial/cpt_dates.py",Path(__file__).parents[2]/"pycpt_tutorial/export.py")},"metrics":report}
    (ROOT/"case_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print("ALL_SEASONS_COMPLETE","forecast_cases",report["calibrated_forecast_cases"],"outputs",len(manifest["outputs"]),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--seasons",nargs="+",choices=SEASONS,default=list(SEASONS)); parser.add_argument("--fit-only",action="store_true"); parser.add_argument("--wait-for-inputs",action="store_true"); parser.add_argument("--refresh-figures",action="store_true")
    args=parser.parse_args()
    if args.refresh_figures: refresh_figures()
    else: main(args.seasons,args.fit_only,args.wait_for_inputs)
