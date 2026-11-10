"""Frozen-training OND holdout tests at0.25° for Indonesia,2021–2024."""
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
import matplotlib.ticker as mticker
import cartopy.crs as ccrs
import numpy as np
import pandas as pd
import pycpt
from cptcore import canonical_correlation_analysis, principal_components_regression
import shapely.geometry
import xarray as xr

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from pycpt_tutorial.export import save_netcdf
from prepare_indonesia_ond_holdouts import ROOT, OLD, PREVIOUS, RECENT, YEARS, NEW_YEARS, main as prepare, read, sha
from run_indonesia_025_case import COMMON, forecast_metrics, stack_forecasts
from run_indonesia_1991_case import benchmark_hashes

OUT=ROOT/"outputs"
PERIODS={"1982_2010":dict(root=PREVIOUS,xpath=OLD/"inputs/cfsv2_hindcasts_ond.nc",years=list(range(1982,2011))),
         "1991_2020":dict(root=RECENT,xpath=RECENT/"inputs/cfsv2_hindcasts_ond.nc",years=list(range(1991,2021)))}
SETS={"new_holdouts":NEW_YEARS,"all_four_years":YEARS}


def freeze_benchmarks():
    frozen=benchmark_hashes()
    manifest=json.loads((RECENT/"case_manifest.json").read_text())
    for name,info in manifest["outputs"].items():
        path=RECENT/"outputs"/name; assert sha(path)==info["sha256"]
        frozen[str(path)]=info["sha256"]
    return frozen


def main():
    if (ROOT/"case_manifest.json").exists():
        print("Completed OND holdout case retained."); return
    prepare()
    audit=json.loads((ROOT/"availability.json").read_text()); assert audit["status"]=="PASS"
    frozen=freeze_benchmarks()
    assert pycpt.__version__=="2.10.4"
    engine=Path(os.environ.get("CPT_BIN_DIR",""))/"CPT.x"
    assert engine==Path.home()/"miniforge3/envs/pycpt-tutorial/opt/cpt/bin/CPT.x"
    f=read(ROOT/"inputs/cfsv2_forecast_predictors.nc").precipitation
    obs=read(ROOT/"inputs/observations_chirps3_ond_2021_2024.nc")
    footprint=read(ROOT/"inputs/evaluation_footprint.nc")
    evaluation=footprint.evaluation_mask.astype(bool); weights=footprint.evaluation_weight
    truth=obs.precipitation.where(evaluation)
    OUT.mkdir(parents=True,exist_ok=True)
    meta={"case_id":ROOT.name,"data_kind":"retrospective_fixed_period_holdout","pycpt_version":"2.10.4","cpt_version":"17.8.3",
          "target":"OND","forecast_years":"2021,2022,2023,2024","initialization_rule":"1September of target year","target_rule":"1October–31December of same year",
          "predictand_resolution_degrees":.25,"predictor_resolution_degrees":1.,"model":"CFSv2 ensemble mean","observations":"CHIRPS3 country-land seasonal accumulation",
          "validation_note":"Fixed training periods and modes; all forecast target years outside both training periods;2023 cached motivating case; primary additional holdouts2021,2022,2024",
          "probability_note":"CPT category references: older fits1991–2010,recent1991–2020; rainfall auto-zero-bounded; see research/reports/METHODOLOGY_AUDIT.md; no probabilistic skill claim"}
    def save(ds,name,attrs=None): return save_netcdf(ds,OUT/name,metadata={**meta,**(attrs or {})},overwrite=True)
    predictions={}; configs={}; checks={}; timings={}; inputs={}
    for period,settings in PERIODS.items():
        root=settings["root"]; years=settings["years"]
        x=read(settings["xpath"]).precipitation
        all_y=read(root/"outputs/observations_chirps3_ond_025.nc").precipitation
        y=all_y.sel(T=all_y["T"].dt.year.isin(years))
        country=read(root/"outputs/indonesia_analysis_mask_025.nc")
        mask=country.analysis_mask.astype(bool); count=int(mask.sum())
        np.testing.assert_array_equal(x["T"],y["T"]); np.testing.assert_array_equal(y["T"].dt.year,years)
        assert set(years).isdisjoint(YEARS)
        for p in (settings["xpath"],root/"outputs/observations_chirps3_ond_025.nc",root/"outputs/indonesia_analysis_mask_025.nc"):
            inputs[str(p)]=sha(p)
        predictions[f"climatology_{period}"]=y.mean("T").expand_dims(T=f["T"]).assign_coords(Ti=f.Ti,Tf=f.Tf).where(evaluation)
        period_hindcasts=[]
        for method in ("cca","pcr"):
            key=f"{method}_{period}"; config=dict(COMMON)
            if method=="cca": config.update(y_eof_modes=(3,3),cca_modes=(2,2))
            configs[key]=config; checks[key]={}; timings[key]={}
            frozen_h=read(root/f"outputs/{method}_hindcasts_025.nc")
            forecast_cases={2023:read(root/f"outputs/{method}_forecast_2023_025.nc")}
            inputs[str(root/f"outputs/{method}_forecast_2023_025.nc")]=sha(root/f"outputs/{method}_forecast_2023_025.nc")
            function=canonical_correlation_analysis if method=="cca" else principal_components_regression
            for year in NEW_YEARS:
                forecast_input=f.sel(T=f["T"].dt.year==year)
                print("RUNNING",key,year,"training_samples",len(years),"cells",count,flush=True)
                cache=ROOT/"fit-cache"/f"{key}_{year}.nc"
                if cache.exists():
                    fc=read(cache); checks[key][str(year)]={"cached_forecast":True,"hindcast_match_checked_before_cache_write":True}
                else:
                    start=time.monotonic()
                    result=function(x,y,F=forecast_input,**config,cpt_kwargs={"outputdir":ROOT/f"cpt-{key}-{year}","log":ROOT/f"cpt-{key}-{year}-session.log","project_file":ROOT/f"cpt-{key}-{year}-commands.txt"})
                    timings[key][str(year)]=time.monotonic()-start
                    h,fc,skill=[ds.reindex(X=y.X,Y=y.Y,method="nearest",tolerance=1e-3).where(mask) for ds in result[:3]]
                    np.testing.assert_array_equal(h["T"],frozen_h["T"])
                    np.testing.assert_allclose(h.deterministic.values,frozen_h.deterministic.values,atol=1e-8,rtol=0,equal_nan=True)
                    checks[key][str(year)]={"hindcast_maximum_difference_from_frozen_mm":float(np.nanmax(abs(h.deterministic.values-frozen_h.deterministic.values)))}
                    save_netcdf(fc,cache,metadata={**meta,"calibration":method.upper(),"training_period":period,"forecast_year":year},overwrite=True)
                np.testing.assert_array_equal(fc.S,pd.to_datetime([f"{year}-09-01"]))
                np.testing.assert_array_equal(fc.Ti,pd.to_datetime([f"{year}-10-01"]))
                np.testing.assert_array_equal(fc.Tf,pd.to_datetime([f"{year}-12-31"]))
                assert int(fc.deterministic.count())==count
                assert int(fc.probabilistic.count())==3*count and int(fc.prediction_error_variance.count())==count
                assert float(fc.probabilistic.min())>=0 and float(fc.probabilistic.max())<=100
                assert float(fc.prediction_error_variance.min())>=0
                np.testing.assert_allclose(fc.probabilistic.sum("C").isel(T=0).values[mask.values],100,atol=.1)
                forecast_cases[year]=fc
                print("COMPLETED",key,year,flush=True)
            combined=xr.concat([forecast_cases[year] for year in YEARS],dim="T",join="exact",combine_attrs="drop_conflicts")
            np.testing.assert_array_equal(combined["T"].dt.year,YEARS)
            save(combined,f"{key}_forecasts_2021_2024.nc",{"training_period":period,"calibration":method.upper(),"source_2023":"Frozen verified2023 case, retained unchanged"})
            predictions[key]=combined.deterministic.where(evaluation)
            period_hindcasts.append(frozen_h.deterministic.reset_coords(drop=True))
        save(xr.Dataset({"deterministic":xr.concat(period_hindcasts,dim=pd.Index(["cca","pcr"],name="calibration")),"observed_rainfall":y.reset_coords(drop=True)}),
             f"training_hindcasts_{period}.nc",{"training_period":period,"data_kind":"unchanged_CPT_crossvalidated_training_diagnostics"})
    predictions["raw_cfsv2"]=f.interp(X=truth.X,Y=truth.Y).where(evaluation)
    # Stable order makes tables and score coordinates easy to compare.
    order=["raw_cfsv2","climatology_1982_2010","climatology_1991_2020","cca_1982_2010","cca_1991_2020","pcr_1982_2010","pcr_1991_2020"]
    predictions={key:predictions[key] for key in order}
    for key,da in predictions.items(): assert int(da.count())==int(evaluation.sum())*4,key
    comparison=stack_forecasts(predictions,truth,f.S)
    save(comparison,"forecast_comparison_025.nc")
    save(obs,"observations_chirps3_ond_2021_2024.nc",{"data_kind":"heldout_observed_reference"})
    save(footprint,"evaluation_footprint.nc")
    save(f.to_dataset(),"cfsv2_forecast_predictors.nc")
    save(read(ROOT/"inputs/cfsv2_forecast_monthly_audit.nc"),"cfsv2_forecast_monthly_audit.nc")
    yearly={str(year):{key:forecast_metrics(da.sel(T=da["T"].dt.year==year),truth.sel(T=truth["T"].dt.year==year),weights) for key,da in predictions.items()} for year in YEARS}
    pooled={}
    for group,selected in SETS.items():
        pooled[group]={}
        for key in order:
            values=[yearly[str(year)][key] for year in selected]
            pooled[group][key]={"pooled_rmse_mm":float(np.sqrt(np.mean([item["rmse_mm"]**2 for item in values]))),
                                "mean_annual_rmse_mm":float(np.mean([item["rmse_mm"] for item in values])),
                                "mae_mm":float(np.mean([item["mae_mm"] for item in values])),"bias_mm":float(np.mean([item["bias_mm"] for item in values])),"years":selected}
    coords={"forecast_variant":order,"T":truth["T"],"evaluation_set":list(SETS)}
    score_ds=xr.Dataset({name:xr.DataArray([[yearly[str(year)][key][name+"_mm"] for year in YEARS] for key in order],dims=("forecast_variant","T"),coords={d:coords[d] for d in ("forecast_variant","T")}) for name in ("rmse","mae","bias")})
    for name in ("pooled_rmse_mm","mean_annual_rmse_mm","mae_mm","bias_mm"):
        score_ds[name.replace("_mm","") if name.startswith("pooled") or name.startswith("mean_") else "pooled_"+name.replace("_mm","")]=xr.DataArray([[pooled[group][key][name] for group in SETS] for key in order],dims=("forecast_variant","evaluation_set"),coords={d:coords[d] for d in ("forecast_variant","evaluation_set")})
    score_ds=score_ds.assign_coords(S=f.S,Ti=truth.Ti,Tf=truth.Tf)
    for variable in score_ds.values(): variable.attrs["units"]="mm"
    save(score_ds,"verification_scores.nc",{"pooling_rule":"Equal year weights and shared spatial weights; pooled RMSE=sqrt(mean annual MSE), not mean annual RMSE","new_holdouts":"2021,2022,2024","all_four_years":"2021,2022,2023,2024"})
    grid_sets=[]
    for group,selected in SETS.items():
        error=comparison.error.sel(T=comparison["T"].dt.year.isin(selected))
        fields=xr.Dataset({"rmse":np.sqrt((error**2).mean("T")),"mae":abs(error).mean("T"),"bias":error.mean("T")})
        for variable in fields.values(): variable.attrs["units"]="mm"
        grid_sets.append(fields)
    save(xr.concat(grid_sets,dim=pd.Index(list(SETS),name="evaluation_set")),"multiyear_error_fields.nc",{"warning":"Only3additional/4total years; maps are descriptive, no significance or reliability claim"})
    period_changes={}
    for method in ("cca","pcr"):
        period_changes[method]={"per_year":{str(year):{"older_rmse_mm":yearly[str(year)][method+"_1982_2010"]["rmse_mm"],"recent_rmse_mm":yearly[str(year)][method+"_1991_2020"]["rmse_mm"],
                                                     "recent_minus_older_rmse_mm":yearly[str(year)][method+"_1991_2020"]["rmse_mm"]-yearly[str(year)][method+"_1982_2010"]["rmse_mm"]} for year in YEARS},
                                "recent_lower_rmse_new_holdout_years":[year for year in NEW_YEARS if yearly[str(year)][method+"_1991_2020"]["rmse_mm"]<yearly[str(year)][method+"_1982_2010"]["rmse_mm"]]}
    report={"case_id":ROOT.name,"years":YEARS,"new_holdout_years":NEW_YEARS,"training_periods":{"1982_2010":29,"1991_2020":30},"evaluation_cells":int(evaluation.sum()),
            "per_year":yearly,"pooled_metrics":pooled,"period_changes":period_changes,"fit_elapsed_seconds":timings,"frozen_hindcast_checks":checks,
            "limitations":["Three additional years and one motivating2023 case; no significance or general seasonal skill claim","Both training periods fixed; different sample counts29and30","1991–2020 mixes reforecast and operational archive segments","Current-vintage CHIRPS3/archived forecasts, not exact as-issued vintages","Period-specific probability categories differ; no probabilistic skill comparison"]}
    (ROOT/"metrics.json").write_text(json.dumps(report,indent=2)+"\n")
    plot(comparison,yearly)
    assert all(sha(Path(path))==value for path,value in frozen.items())
    for path in (ROOT/"inputs").glob("*.nc"): inputs[str(path)]=sha(path)
    manifest={"case_id":ROOT.name,"completed_at":dt.datetime.now(dt.timezone.utc).isoformat(),"engine":str(engine),"engine_sha256":sha(engine),"configurations":configs,
              "unchanged_benchmark_artifacts_sha256":frozen,"input_sha256":inputs,"outputs":{p.name:{"bytes":p.stat().st_size,"sha256":sha(p)} for p in sorted(OUT.iterdir()) if p.is_file()},
              "pipeline_script_sha256":{str(p.relative_to(Path(__file__).parents[2])):sha(p) for p in (Path(__file__),Path(__file__).with_name("prepare_indonesia_ond_holdouts.py"),Path(__file__).with_name("run_indonesia_025_case.py"),Path(__file__).parents[2]/"pycpt_tutorial/country_grid.py",Path(__file__).parents[2]/"pycpt_tutorial/export.py")},"metrics":report}
    (ROOT/"case_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print("CASE_COMPLETE",json.dumps({k:v for k,v in report.items() if k not in ("fit_elapsed_seconds","frozen_hindcast_checks")},indent=2),flush=True)


def plot(comparison,yearly):
    labels={"raw_cfsv2":"Raw CFSv2","climatology_1982_2010":"Climatology 1982–2010","climatology_1991_2020":"Climatology 1991–2020", "cca_1982_2010":"CCA 1982–2010","cca_1991_2020":"CCA 1991–2020","pcr_1982_2010":"PCR 1982–2010","pcr_1991_2020":"PCR 1991–2020"}
    styles={"raw_cfsv2":("#666666",":"),"climatology_1982_2010":("#39834b","--"),"climatology_1991_2020":("#39834b","-"),"cca_1982_2010":("#1c69a6","--"),"cca_1991_2020":("#1c69a6","-"),"pcr_1982_2010":("#cf6c12","--"),"pcr_1991_2020":("#cf6c12","-")}
    fig,axes=plt.subplots(1,2,figsize=(15,5.5),layout="constrained")
    for key in styles:
        color,line=styles[key]
        for ax,metric,title in zip(axes,("rmse_mm","bias_mm"),("Area-weighted spatial RMSE","Area-weighted bias (forecast−observed)")):
            ax.plot(YEARS,[yearly[str(year)][key][metric] for year in YEARS],label=labels[key],color=color,linestyle=line,marker="o",markersize=4)
            ax.set_xticks(YEARS); ax.set_ylabel("Seasonal rainfall (mm)"); ax.set_title(title); ax.grid(alpha=.2)
    axes[1].axhline(0,color="#333",linewidth=.8)
    fig.suptitle("Indonesia OND 2021–2024 • common 0.25° cells • fixed training periods",fontsize=14)
    handles,legend=axes[0].get_legend_handles_labels()
    fig.legend(handles,legend,loc="outside lower center",ncol=4,fontsize=9)
    fig.savefig(OUT/"holdout_scores.png",dpi=180); plt.close(fig)
    geometry=shapely.geometry.shape(json.loads((OLD/"inputs/indonesia_boundary.geojson").read_text()))
    projection=ccrs.PlateCarree()
    differences={method:comparison.absolute_error.sel(forecast_variant=method+"_1991_2020",drop=True)-comparison.absolute_error.sel(forecast_variant=method+"_1982_2010",drop=True) for method in ("cca","pcr")}
    limit=max(1.,float(np.nanpercentile(np.concatenate([da.values.ravel() for da in differences.values()]),98)))
    fig,axes=plt.subplots(4,2,figsize=(15,13),subplot_kw={"projection":projection},layout="constrained")
    for row,year in enumerate(YEARS):
        for col,method in enumerate(("cca","pcr")):
            ax=axes[row,col]; da=differences[method].sel(T=differences[method]["T"].dt.year==year).isel(T=0)
            im=ax.pcolormesh(da.X,da.Y,da,transform=projection,cmap="RdBu_r",vmin=-limit,vmax=limit)
            ax.add_geometries([geometry],projection,facecolor="none",edgecolor="#333",linewidth=.25)
            ax.set_extent([94,142,-12,7]); ax.set_title(f"{year} • {method.upper()}",fontsize=11)
            grid=ax.gridlines(draw_labels={"bottom":"x","left":"y"},linewidth=.2,alpha=.3,x_inline=False,y_inline=False)
            grid.xlocator=mticker.FixedLocator([100,110,120,130,140]); grid.ylocator=mticker.FixedLocator([-10,-5,0,5]); grid.xlabel_style={"size":8}; grid.ylabel_style={"size":8}
    fig.colorbar(im,ax=axes.ravel().tolist(),label="Newer minus older training: absolute error (mm)",shrink=.75,extend="both")
    fig.suptitle("Indonesia OND • blue: newer training lower error; red: older lower error • common colour scale",fontsize=13)
    fig.savefig(OUT/"holdout_error_changes.png",dpi=170); plt.close(fig)


def refresh_figures():
    """Redraw saved results without executing calibration again."""
    manifest=json.loads((ROOT/"case_manifest.json").read_text())
    for name,info in manifest["outputs"].items(): assert sha(OUT/name)==info["sha256"],name
    freeze_benchmarks()
    report=json.loads((ROOT/"metrics.json").read_text())
    plot(read(OUT/"forecast_comparison_025.nc"),report["per_year"])
    for name in ("holdout_scores.png","holdout_error_changes.png"):
        path=OUT/name; manifest["outputs"][name]={"bytes":path.stat().st_size,"sha256":sha(path)}
    manifest["pipeline_script_sha256"]["scripts/run_indonesia_ond_holdouts.py"]=sha(Path(__file__))
    manifest["figure_refresh"]={"at":dt.datetime.now(dt.timezone.utc).isoformat(),"reason":"Label spacing after visual review; all model/NetCDF data retained"}
    (ROOT/"case_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print("FIGURES_REFRESHED")


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-figures",action="store_true",help="Redraw saved results without running CPT")
    args=parser.parse_args()
    if args.refresh_figures: refresh_figures()
    else: main()
