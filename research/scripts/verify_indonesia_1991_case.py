"""Independent integrity, calendar and comparison checks for the period experiment."""
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from prepare_indonesia_1991_case import ROOT, OLD, PREVIOUS, TRAIN, read, sha


def main():
    manifest=json.loads((ROOT/"case_manifest.json").read_text())
    metrics=json.loads((ROOT/"metrics.json").read_text())
    audit=json.loads((ROOT/"continuity.json").read_text())
    for name,info in manifest["outputs"].items(): assert sha(ROOT/"outputs"/name)==info["sha256"],name
    for group in ("input_sha256","unchanged_benchmark_artifacts_sha256"):
        for path,value in manifest[group].items(): assert sha(Path(path))==value,path
    for name,info in audit["sources"].items():
        filename={"ensemble_mean":"cfsv2_hindcasts_monthly.tsv","valid_member_counts":"cfsv2_valid_member_counts_monthly.tsv","java_point_members":"cfsv2_members_java_point.nc","metadata":"cfsv2_source_metadata.html"}[name]
        assert sha(ROOT/"inputs"/filename)==info["sha256"]
    country=read(ROOT/"outputs/indonesia_analysis_mask_025.nc")
    mask=country.analysis_mask.values.astype(bool)
    count=int(mask.sum())
    obs=read(ROOT/"outputs/observations_chirps3_ond_025.nc").precipitation
    np.testing.assert_array_equal(obs["T"].dt.year,TRAIN+[2023])
    np.testing.assert_allclose(np.diff(obs.X),.25,atol=1e-12)
    np.testing.assert_allclose(np.diff(obs.Y),-.25,atol=1e-12)
    continuity=read(ROOT/"outputs/cfsv2_monthly_continuity.nc")
    rates=continuity.precipitation_rate.transpose("T","Y","X")
    members=continuity.valid_member_count
    assert rates.shape==(90,41,71) and np.isfinite(rates.values).all()
    assert np.isfinite(members.values).all() and float(members.min())>=1
    np.testing.assert_array_equal(rates["T"].dt.year,np.repeat(TRAIN,3))
    np.testing.assert_array_equal(rates["T"].dt.month,np.tile([10,11,12],30))
    # Independent NumPy seasonal integration; the preparer uses per-year xarray.
    integrated=(rates.values.reshape(30,3,41,71)*np.array([31,30,31])[None,:,None,None]).sum(axis=1)
    predictors=read(ROOT/"outputs/cfsv2_training_predictors.nc").precipitation.transpose("T","Y","X")
    np.testing.assert_allclose(integrated,predictors.values,atol=1e-9,rtol=0)
    for method in ("cca","pcr"):
        forecast=read(ROOT/f"outputs/{method}_forecast_2023_025.nc")
        hindcast=read(ROOT/f"outputs/{method}_hindcasts_025.nc")
        np.testing.assert_array_equal(hindcast["T"].dt.year,TRAIN)
        assert int(hindcast.deterministic.count())==count*30
        np.testing.assert_array_equal(forecast.S,pd.to_datetime(["2023-09-01"]))
        np.testing.assert_array_equal(forecast.Ti,pd.to_datetime(["2023-10-01"]))
        np.testing.assert_array_equal(forecast.Tf,pd.to_datetime(["2023-12-31"]))
        assert int(forecast.deterministic.count())==count
        assert int(forecast.prediction_error_variance.count())==count
        assert int(forecast.probabilistic.count())==count*3
        assert float(forecast.prediction_error_variance.min())>=0
        assert float(forecast.probabilistic.min())>=0 and float(forecast.probabilistic.max())<=100
        np.testing.assert_allclose(forecast.probabilistic.sum("C").isel(T=0).values[mask],100,atol=.1)
    comparison=read(ROOT/"outputs/period_forecast_comparison_025.nc")
    footprint=read(ROOT/"outputs/period_comparison_footprint_025.nc")
    evaluation=footprint.evaluation_mask.values.astype(bool)
    weights=footprint.evaluation_country_land_weight.values[evaluation]
    assert weights.size==metrics["evaluation_cells"] and bool((weights>0).all())
    truth=comparison.observed_rainfall.transpose("T","Y","X").values[0,evaluation]
    np.testing.assert_array_equal(truth,obs.sel(T=obs["T"].dt.year==2023).values[0,evaluation])
    maximum_metric_difference=0.
    for key in comparison.forecast_variant.values:
        prediction=comparison.forecast_rainfall.sel(forecast_variant=key).transpose("T","Y","X").values[0,evaluation]
        assert np.isfinite(prediction).all()
        error=prediction-truth
        computed={"rmse_mm":float(np.sqrt(np.average(error**2,weights=weights))),"mae_mm":float(np.average(abs(error),weights=weights)),"bias_mm":float(np.average(error,weights=weights))}
        for name,value in computed.items():
            stored=metrics["forecast_metrics_common_025"][str(key)][name]
            np.testing.assert_allclose(value,stored,atol=1e-9,rtol=0)
            maximum_metric_difference=max(maximum_metric_difference,abs(value-stored))
        if key.startswith(("cca_","pcr_")):
            method,first,last=str(key).split("_")
            root=PREVIOUS if first=="1982" else ROOT
            source=read(root/f"outputs/{method}_forecast_2023_025.nc").deterministic
            np.testing.assert_array_equal(prediction,source.values[0,evaluation])
        elif key.startswith("climatology_"):
            root=PREVIOUS if "1982" in str(key) else ROOT
            source=read(root/"outputs/observations_chirps3_ond_025.nc").precipitation
            years=list(range(1982,2011)) if root==PREVIOUS else TRAIN
            expected=np.mean(source.sel(T=source["T"].dt.year.isin(years)).values[:,evaluation],axis=0)
            np.testing.assert_allclose(prediction,expected,atol=1e-9,rtol=0)
    shared=read(ROOT/"outputs/shared_year_hindcasts_1991_2010_025.nc")
    np.testing.assert_array_equal(shared["T"].dt.year,np.arange(1991,2011))
    assert int(shared.deterministic.count())==6*20*int(evaluation.sum())
    report={"status":"PASS","output_hashes_verified":len(manifest["outputs"]),"benchmark_artifacts_unchanged":len(manifest["unchanged_benchmark_artifacts_sha256"]),
            "training_years":[1991,2020],"verification_year_excluded_from_fitting":2023,"fine_training_cells":count,"common_evaluation_cells":int(evaluation.sum()),
            "full_domain_monthly_values_checked":rates.size,"missing_monthly_values":0,"member_count_range":[int(members.min()),int(members.max())],
            "independent_numpy_monthly_to_seasonal_max_difference_mm":float(abs(integrated-predictors.values).max()),"independent_numpy_forecast_metrics_max_difference_mm":maximum_metric_difference,
            "dates_counts_probability_bounds_sums_and_variances":"PASS","shared_verification_years":[1991,2010],"verification_script_sha256":sha(Path(__file__))}
    (ROOT/"verification.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))


if __name__=="__main__": main()
