"""Independent NumPy/calendar validation of every all-season forecast and score."""
import calendar
import datetime as dt
import json
import re
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from prepare_indonesia_all_seasons import ROOT, SEASONS, PERIODS, EVAL_YEARS, ALL_YEARS, read, sha

END_MONTH=dict(zip(SEASONS,(2,3,4,5,6,7,8,9,10,11,12,1)))


def independent_window(season,year):
    end=pd.Timestamp(year,END_MONTH[season],1)+pd.offsets.MonthEnd(0)
    start=end.replace(day=1)-pd.DateOffset(months=2)
    issue=start-pd.DateOffset(months=1)
    months=pd.date_range(start,periods=3,freq="MS")
    days=[calendar.monthrange(value.year,value.month)[1] for value in months]
    return issue,start,end,start+(end-start)/2,days


def bilinear_numpy(model,fine_X,fine_Y):
    """Independent bilinear interpolation on the validated regular1° source grid."""
    ascending=model[:,::-1,:]
    ix=np.floor(fine_X-85).astype(int); iy=np.floor(fine_Y+20).astype(int)
    tx=fine_X-(85+ix); ty=fine_Y-(-20+iy)
    a=ascending[:,iy[:,None],ix[None,:]]; b=ascending[:,iy[:,None],ix[None,:]+1]
    c=ascending[:,iy[:,None]+1,ix[None,:]]; d=ascending[:,iy[:,None]+1,ix[None,:]+1]
    return (a*(1-tx)+b*tx)*(1-ty[:,None])+(c*(1-tx)+d*tx)*ty[:,None]


def main():
    manifest=json.loads((ROOT/"case_manifest.json").read_text()); metrics=json.loads((ROOT/"metrics.json").read_text())
    for name,info in manifest["outputs"].items(): assert sha(ROOT/"outputs"/name)==info["sha256"],name
    for path,expected in manifest["unchanged_benchmark_artifacts_sha256"].items(): assert sha(Path(path))==expected,path
    for path,expected in manifest["input_sha256"].items(): assert sha(ROOT/path)==expected,path
    footprint=read(ROOT/"outputs/evaluation_footprint.nc")
    common=footprint.evaluation_mask.values.astype(bool); weights=footprint.evaluation_weight.values[common]
    assert int(common.sum())==metrics["common_evaluation_cells"] and np.all(weights>0)
    scores=read(ROOT/"outputs/verification_scores.nc"); field_scores=read(ROOT/"outputs/multiyear_error_fields.nc")
    max_score_difference=0.; max_integration_difference=0.; parsing_copies=0; model_values=0; cases=0; per_season=[]
    for season in SEASONS:
        negative_forecasts={}
        model=read(ROOT/f"outputs/{season}_predictors.nc").precipitation
        observations=read(ROOT/f"outputs/{season}_observations.nc").precipitation
        country=read(ROOT/f"outputs/{season}_footprint.nc")
        monthly=read(ROOT/f"outputs/{season}_monthly_audit.nc")
        preparation=json.loads((ROOT/season/"preparation.json").read_text())
        for kind,expected in preparation["raw_sha256"].items(): assert sha(ROOT/"raw"/f"{season}_{kind}.nc")==expected
        windows=[independent_window(season,year) for year in ALL_YEARS]
        for coord,index in (("S",0),("Ti",1),("Tf",2),("T",3)):
            np.testing.assert_array_equal(model[coord],pd.to_datetime([window[index] for window in windows]))
        np.testing.assert_array_equal(model.season_year,ALL_YEARS)
        np.testing.assert_array_equal(model.X,np.arange(85,156)); np.testing.assert_array_equal(model.Y,np.arange(20,-21,-1))
        np.testing.assert_array_equal(observations["T"],model["T"])
        np.testing.assert_allclose(np.diff(observations.X),.25,atol=1e-12); np.testing.assert_allclose(np.diff(observations.Y),-.25,atol=1e-12)
        rates=monthly.precipitation_rate.values; counts=monthly.valid_member_count.values
        assert rates.shape==(42,3,41,71) and np.isfinite(rates).all() and np.isfinite(counts).all()
        np.testing.assert_array_equal(counts,np.round(counts)); assert counts.min()>=1
        days=np.array([window[4] for window in windows])
        np.testing.assert_array_equal(days,monthly.target_month_days)
        integrated=np.array([sum(rates[i,j]*days[i,j] for j in range(3)) for i in range(42)])
        difference=float(abs(integrated-model.values).max())
        if season=="OND":
            absolute=abs(rates)
            quantum=np.where(absolute>0,10.**(np.floor(np.log10(np.maximum(absolute,1e-40)))-5),0)
            bound=(.5*quantum+2*np.spacing(absolute.astype("float32")).astype("float64"))*days[:,:,None,None]
            assert difference<=float(bound.sum(axis=1).max())+1e-9
            assert preparation["ond_monthly_rounding_bound_violations"]==0
            for path,expected in preparation["ond_previous_monthly_source_sha256"].items(): assert sha(Path(path))==expected
        else: assert difference<1e-9
        max_integration_difference=max(max_integration_difference,difference); model_values+=rates.size
        obs=observations.values
        for period,train in PERIODS.items():
            indices=[ALL_YEARS.index(year) for year in train]; training=obs[indices]
            expected_mask=np.isfinite(training).all(axis=0)&(np.nan_to_num(training,nan=0.).std(axis=0)>0)
            mask=country.analysis_mask.sel(training_period=period).values.astype(bool)
            np.testing.assert_array_equal(mask,expected_mask)
            assert np.all(mask[common])
            for method in ("cca","pcr"):
                key=f"{season}_{method}_{period}"
                fit=json.loads((ROOT/season/f"{method}_{period}_fit.json").read_text())
                assert fit["config"]["x_eof_modes"]==[3,3]
                if method=="cca": assert fit["config"]["y_eof_modes"]==[3,3] and fit["config"]["cca_modes"]==[2,2]
                for event in fit["date_parsing_normalizations"]:
                    assert sha(Path(event["source"]))==event["source_sha256"]
                    assert sha(Path(event["parsing_copy"]))==event["parsing_sha256"]
                    before=Path(event["source"]).read_text(); after=Path(event["parsing_copy"]).read_text()
                    tokens=r"cpt:S=([^,\s]+)"
                    raw_dates=re.findall(tokens,before); parsed_dates=re.findall(tokens,after)
                    assert len(raw_dates)==len(parsed_dates)
                    changed=set(event["dates"])
                    for raw_value,parsed_value in zip(raw_dates,parsed_dates):
                        assert parsed_value==(raw_value+"T00:00" if raw_value in changed else raw_value)
                    assert re.sub(tokens,"",before)==re.sub(tokens,"",after)
                    parsing_copies+=1
                fc=read(ROOT/f"outputs/{key}_forecasts.nc"); hind=read(ROOT/f"outputs/{key}_hindcasts.nc")
                expected=[independent_window(season,year) for year in EVAL_YEARS]
                for coord,index in (("S",0),("Ti",1),("Tf",2),("T",3)):
                    np.testing.assert_array_equal(fc[coord],pd.to_datetime([window[index] for window in expected]))
                np.testing.assert_array_equal(fc.season_year,EVAL_YEARS); np.testing.assert_array_equal(hind.season_year,train)
                assert pd.Timestamp(hind.Tf.max().item())<expected[0][0]
                assert int(hind.deterministic.count())==len(train)*int(mask.sum())
                for variable,multiplier in (("deterministic",1),("probabilistic",3),("prediction_error_variance",1)):
                    assert int(fc[variable].count())==4*int(mask.sum())*multiplier
                assert float(fc.prediction_error_variance.min())>=0
                negative_forecasts[method+"_"+period]=int((fc.deterministic<0).sum())
                assert float(fc.probabilistic.min())>=0 and float(fc.probabilistic.max())<=100
                np.testing.assert_allclose(fc.probabilistic.sum("C").transpose("T","Y","X").values[:,mask],100,atol=.1)
                cases+=4
        comparison=read(ROOT/f"outputs/{season}_forecast_comparison.nc")
        observed=comparison.observed_rainfall.transpose("T","Y","X").values[:,common]
        eval_indices=[ALL_YEARS.index(year) for year in EVAL_YEARS]
        np.testing.assert_array_equal(observed,obs[eval_indices][:,common])
        interpolated=bilinear_numpy(model.values[eval_indices],observations.X.values,observations.Y.values)
        np.testing.assert_allclose(interpolated[:,common],comparison.forecast_rainfall.sel(forecast_variant="raw_cfsv2").values[:,common],atol=1e-8,rtol=0)
        for vi,key in enumerate(comparison.forecast_variant.values):
            pred=comparison.forecast_rainfall.sel(forecast_variant=key).values[:,common]
            assert np.isfinite(pred).all()
            if str(key).startswith("climatology"):
                period=str(key).replace("climatology_","")
                expected=obs[[ALL_YEARS.index(year) for year in PERIODS[period]]][:,common].mean(axis=0)
                np.testing.assert_allclose(pred,np.broadcast_to(expected,pred.shape),atol=1e-9,rtol=0)
            elif str(key).startswith(("cca","pcr")):
                native=read(ROOT/f"outputs/{season}_{key}_forecasts.nc").deterministic.values[:,common]
                np.testing.assert_array_equal(pred,native)
            error=pred-observed
            calculated={"rmse":np.sqrt(np.average(error**2,axis=1,weights=weights)),"mae":np.average(abs(error),axis=1,weights=weights),"bias":np.average(error,axis=1,weights=weights)}
            for metric,value in calculated.items():
                saved=scores[metric].sel(season=season,forecast_variant=key).values
                np.testing.assert_allclose(value,saved,atol=1e-8,rtol=0)
                max_score_difference=max(max_score_difference,float(abs(value-saved).max()))
            for group,years in (("all_four_years",EVAL_YEARS),("additional_years",[2021,2022,2024])):
                subset=error[[EVAL_YEARS.index(year) for year in years]]
                fields={"rmse":np.sqrt(np.mean(subset**2,axis=0)),"mae":np.mean(abs(subset),axis=0),"bias":np.mean(subset,axis=0)}
                for metric,field in fields.items():
                    pooled=np.sqrt(np.average(np.mean(subset**2,axis=0),weights=weights)) if metric=="rmse" else np.average(field,weights=weights)
                    np.testing.assert_allclose(pooled,scores["pooled_"+metric].sel(season=season,forecast_variant=key,evaluation_set=group),atol=1e-8,rtol=0)
                    np.testing.assert_allclose(field,field_scores[metric].sel(season=season,forecast_variant=key,evaluation_set=group).values[common],atol=1e-8,rtol=0)
        per_season.append({"season":season,"source_monthly_values":rates.size,"valid_members":[int(counts.min()),int(counts.max())],"integration_max_difference_mm":difference,"negative_forecast_cells_across4years":negative_forecasts})
        print("VERIFIED",season,flush=True)
    assert cases==192
    gains=read(ROOT/"outputs/calibration_gains.nc")
    for key in gains.calibrated_variant.values:
        period=str(key).split("_",1)[1]
        rmse=scores.pooled_rmse.sel(forecast_variant=key,drop=True)
        climate=scores.pooled_rmse.sel(forecast_variant="climatology_"+period,drop=True)
        raw=scores.pooled_rmse.sel(forecast_variant="raw_cfsv2",drop=True)
        np.testing.assert_allclose(gains.mse_skill_vs_climatology.sel(calibrated_variant=key,drop=True),1-rmse**2/climate**2,atol=1e-12,rtol=0)
        np.testing.assert_allclose(gains.mse_skill_vs_raw.sel(calibrated_variant=key,drop=True),1-rmse**2/raw**2,atol=1e-12,rtol=0)
    report={"status":"PASS","forecast_cases_verified":cases,"seasons_verified":12,"output_hashes_verified":len(manifest["outputs"]),"prior_artifacts_unchanged":len(manifest["unchanged_benchmark_artifacts_sha256"]),
            "shared_evaluation_cells":int(common.sum()),"source_monthly_model_values_verified":model_values,"max_model_integration_difference_mm":max_integration_difference,
            "max_annual_score_difference_mm":max_score_difference,"date_only_parsing_copies_verified":parsing_copies,"per_season":per_season,
            "checks":"Dates/leapyears/masks/trainingseparation/membercounts/probabilities/variances/rawbilinear/climatologies/annual-pooled-griderrors PASS","verification_script_sha256":sha(Path(__file__))}
    (ROOT/"verification.json").write_text(json.dumps(report,indent=2)+"\n")
    print("VERIFICATION_COMPLETE",json.dumps(report,indent=2),flush=True)


if __name__=="__main__": main()
