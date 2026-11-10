"""Independently verify holdout calendars, outputs, scores and immutable benchmarks."""
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from prepare_indonesia_ond_holdouts import ROOT, PREVIOUS, RECENT, YEARS, NEW_YEARS, read, sha


def main():
    manifest=json.loads((ROOT/"case_manifest.json").read_text())
    metrics=json.loads((ROOT/"metrics.json").read_text())
    availability=json.loads((ROOT/"availability.json").read_text())
    for name,info in manifest["outputs"].items(): assert sha(ROOT/"outputs"/name)==info["sha256"],name
    for group in ("input_sha256","unchanged_benchmark_artifacts_sha256"):
        for path,expected in manifest[group].items(): assert sha(Path(path))==expected,path
    for name,source in availability["sources"].items():
        filename="cfsv2_forecasts_monthly.tsv" if name=="monthly_means" else "cfsv2_valid_member_counts_monthly.tsv"
        assert sha(ROOT/"inputs"/filename)==source["sha256"]
    footprint=read(ROOT/"outputs/evaluation_footprint.nc")
    mask=footprint.evaluation_mask.values.astype(bool)
    weights=footprint.evaluation_weight.values[mask]
    assert np.all(weights>0) and int(mask.sum())==metrics["evaluation_cells"]
    obs=read(ROOT/"outputs/observations_chirps3_ond_2021_2024.nc").precipitation
    np.testing.assert_array_equal(obs["T"].dt.year,YEARS)
    np.testing.assert_allclose(np.diff(obs.X),.25,atol=1e-12); np.testing.assert_allclose(np.diff(obs.Y),-.25,atol=1e-12)
    assert int(obs.where(footprint.evaluation_mask.astype(bool)).count())==4*int(mask.sum())
    audit=read(ROOT/"outputs/cfsv2_forecast_monthly_audit.nc")
    rates=audit.precipitation_rate.transpose("T","Y","X").values
    assert rates.shape==(12,41,71) and np.isfinite(rates).all()
    assert bool(np.isfinite(audit.valid_member_count).all()) and float(audit.valid_member_count.min())>=1
    np.testing.assert_array_equal(audit["T"].dt.year,np.repeat(YEARS,3))
    np.testing.assert_array_equal(audit["T"].dt.month,np.tile([10,11,12],4))
    integrated=(rates.reshape(4,3,41,71)*np.array([31,30,31])[None,:,None,None]).sum(axis=1)
    predictors=read(ROOT/"outputs/cfsv2_forecast_predictors.nc").precipitation
    np.testing.assert_allclose(integrated,predictors.transpose("T","Y","X").values,atol=1e-9,rtol=0)
    expected_initializations=pd.to_datetime([f"{year}-09-01" for year in YEARS])
    expected_start=pd.to_datetime([f"{year}-10-01" for year in YEARS]); expected_end=pd.to_datetime([f"{year}-12-31" for year in YEARS])
    maximum_metric_difference=0.
    for period,root,train in (("1982_2010",PREVIOUS,np.arange(1982,2011)),("1991_2020",RECENT,np.arange(1991,2021))):
        assert set(train).isdisjoint(YEARS)
        native_mask=read(root/"outputs/indonesia_analysis_mask_025.nc").analysis_mask.values.astype(bool)
        n=int(native_mask.sum())
        for method in ("cca","pcr"):
            fc=read(ROOT/f"outputs/{method}_{period}_forecasts_2021_2024.nc")
            np.testing.assert_array_equal(fc["T"].dt.year,YEARS)
            np.testing.assert_array_equal(fc.S,expected_initializations); np.testing.assert_array_equal(fc.Ti,expected_start); np.testing.assert_array_equal(fc.Tf,expected_end)
            for variable,multiplier in (("deterministic",1),("probabilistic",3),("prediction_error_variance",1)):
                assert int(fc[variable].count())==4*n*multiplier
            assert float(fc.probabilistic.min())>=0 and float(fc.probabilistic.max())<=100
            assert float(fc.prediction_error_variance.min())>=0
            np.testing.assert_allclose(fc.probabilistic.sum("C").transpose("T","Y","X").values[:,native_mask],100,atol=.1)
            previous=read(root/f"outputs/{method}_forecast_2023_025.nc")
            for variable in ("deterministic","probabilistic","prediction_error_variance"):
                np.testing.assert_array_equal(fc[variable].sel(T=fc["T"].dt.year==2023),previous[variable])
        h=read(ROOT/f"outputs/training_hindcasts_{period}.nc")
        np.testing.assert_array_equal(h["T"].dt.year,train)
        assert int(h.deterministic.count())==2*len(train)*n
    comparison=read(ROOT/"outputs/forecast_comparison_025.nc")
    truth=comparison.observed_rainfall.transpose("T","Y","X").values[:,mask]
    np.testing.assert_array_equal(truth,obs.transpose("T","Y","X").values[:,mask])
    errors=comparison.forecast_rainfall.transpose("forecast_variant","T","Y","X").values[:,:,mask]-truth[None,:,:]
    assert np.isfinite(errors).all()
    score_file=read(ROOT/"outputs/verification_scores.nc")
    field_file=read(ROOT/"outputs/multiyear_error_fields.nc")
    for index,key in enumerate(comparison.forecast_variant.values):
        error=errors[index]
        rmse=np.sqrt(np.average(error**2,axis=1,weights=weights)); mae=np.average(abs(error),axis=1,weights=weights); bias=np.average(error,axis=1,weights=weights)
        for metric,array in (("rmse",rmse),("mae",mae),("bias",bias)):
            np.testing.assert_allclose(array,score_file[metric].sel(forecast_variant=key),atol=1e-9,rtol=0)
            for j,year in enumerate(YEARS):
                saved=metrics["per_year"][str(year)][str(key)][metric+"_mm"]
                np.testing.assert_allclose(array[j],saved,atol=1e-9,rtol=0)
                maximum_metric_difference=max(maximum_metric_difference,float(abs(array[j]-saved)))
        for group,years in (("new_holdouts",NEW_YEARS),("all_four_years",YEARS)):
            indices=[YEARS.index(year) for year in years]; subset=error[indices]
            pooled_rmse=float(np.sqrt(np.average(np.mean(subset**2,axis=0),weights=weights)))
            saved=metrics["pooled_metrics"][group][str(key)]["pooled_rmse_mm"]
            np.testing.assert_allclose(pooled_rmse,saved,atol=1e-9,rtol=0)
            np.testing.assert_allclose(pooled_rmse,score_file.pooled_rmse.sel(forecast_variant=key,evaluation_set=group),atol=1e-9,rtol=0)
            np.testing.assert_allclose(np.sqrt(np.mean(subset**2,axis=0)),field_file.rmse.sel(forecast_variant=key,evaluation_set=group).values[mask],atol=1e-9,rtol=0)
            maximum_metric_difference=max(maximum_metric_difference,abs(pooled_rmse-saved))
    result={"status":"PASS","output_hashes_verified":len(manifest["outputs"]),"benchmark_artifacts_unchanged":len(manifest["unchanged_benchmark_artifacts_sha256"]),
            "years":YEARS,"new_holdout_years":NEW_YEARS,"shared_evaluation_cells":int(mask.sum()),"finite_monthly_model_values":rates.size,
            "independent_numpy_monthly_integration_max_difference_mm":float(abs(integrated-predictors.transpose("T","Y","X").values).max()),
            "independent_numpy_score_maximum_difference_mm":maximum_metric_difference,"cached2023_forecasts_unchanged":True,"holdouts_disjoint_from_training":True,
            "dates_counts_probabilities_variances_grid_fields_and_pooled_scores":"PASS","verification_script_sha256":sha(Path(__file__))}
    (ROOT/"verification.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__": main()
