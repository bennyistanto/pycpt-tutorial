"""Independently verify fine-grid outputs and NumPy-based cross-scale aggregation."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import xarray as xr

ROOT=Path.home()/"CPT/cases/indonesia-ond-2023-025deg"
OLD=Path.home()/"CPT/cases/indonesia-ond-2023"


def load(path):
    with xr.open_dataset(path) as ds: return ds.load()


def main():
    manifest=json.loads((ROOT/"case_manifest.json").read_text())
    for name,info in manifest["outputs"].items():
        assert hashlib.sha256((ROOT/"outputs"/name).read_bytes()).hexdigest()==info["sha256"]
    for name,value in manifest["unchanged_original_case_artifacts_sha256"].items():
        assert hashlib.sha256((OLD/name).read_bytes()).hexdigest()==value
    for name,value in manifest["frozen_model_and_boundary_input_sha256"].items():
        assert hashlib.sha256((OLD/"inputs"/name).read_bytes()).hexdigest()==value
    country=load(ROOT/"outputs/indonesia_analysis_mask_025.nc")
    mask=country.analysis_mask.values.astype(bool)
    assert int(mask.sum())==3240
    np.testing.assert_allclose(np.diff(country.X),.25,atol=1e-12)
    np.testing.assert_allclose(np.diff(country.Y),-.25,atol=1e-12)
    weight=np.where(mask,country.country_land_weight.values,0)
    footprint=load(ROOT/"outputs/cross_resolution_evaluation_footprint.nc")
    common_mask=footprint.common_mask.values.astype(bool)
    assert common_mask.sum()==369
    common=load(ROOT/"outputs/common_1deg_forecast_comparison.nc")
    differences={}

    def aggregate_numpy(array):
        # Native arrays are T,Y,X, north-to-south and west-to-east. Sum 4x4
        # blocks with explicit NumPy axes, independently of xarray.coarsen.
        values=np.asarray(array)
        valid=np.isfinite(values)
        numerator=np.where(valid,values,0)*weight
        denominator=valid*weight
        shape=values.shape[:-2]+(19,4,48,4)
        summed=numerator.reshape(shape).sum(axis=(-3,-1))
        total_weight=denominator.reshape(shape).sum(axis=(-3,-1))
        return np.divide(summed,total_weight,out=np.full_like(summed,np.nan),where=total_weight>0)

    for method in ("cca","pcr"):
        forecast=load(ROOT/f"outputs/{method}_forecast_2023_025.nc")
        hindcast=load(ROOT/f"outputs/{method}_hindcasts_025.nc")
        np.testing.assert_array_equal(forecast.S.values,pd.to_datetime(["2023-09-01"]).values)
        np.testing.assert_array_equal(forecast.Ti.values,pd.to_datetime(["2023-10-01"]).values)
        np.testing.assert_array_equal(forecast.Tf.values,pd.to_datetime(["2023-12-31"]).values)
        np.testing.assert_array_equal(hindcast["T"].dt.year,np.arange(1982,2011))
        assert int(hindcast.deterministic.count())==3240*29
        assert int(forecast.deterministic.count())==3240
        assert int(forecast.probabilistic.count())==3240*3
        assert int(forecast.prediction_error_variance.count())==3240
        assert float(forecast.probabilistic.min())>=0 and float(forecast.probabilistic.max())<=100
        assert float(forecast.prediction_error_variance.min())>=0
        np.testing.assert_allclose(forecast.probabilistic.sum("C").isel(T=0).values[mask],100,atol=.1)
        aggregated=aggregate_numpy(forecast.deterministic.transpose("T","Y","X").values)
        stored=common.forecast_rainfall.sel(forecast_variant=f"{method}_025_aggregated").transpose("T","Y","X").values
        np.testing.assert_allclose(aggregated[:,common_mask],stored[:,common_mask],atol=1e-9,rtol=0)
        differences[method]=float(np.nanmax(abs(aggregated[:,common_mask]-stored[:,common_mask])))
    fine_obs=load(ROOT/"outputs/observations_chirps3_ond_025.nc").precipitation
    old_obs=load(OLD/"outputs/observations_chirps3_ond.nc").precipitation
    np.testing.assert_array_equal(fine_obs["T"],old_obs["T"])
    reconstructed=aggregate_numpy(fine_obs.transpose("T","Y","X").values)
    error=(reconstructed-old_obs.transpose("T","Y","X").values)[:,common_mask]
    assert np.nanmax(abs(error))<1e-8
    report={"status":"PASS","output_hashes_verified":len(manifest["outputs"]),"original_case_artifacts_unchanged":len(manifest["unchanged_original_case_artifacts_sha256"]),
            "fine_grid_cells":3240,"common_1deg_cells":369,"probabilities_dates_counts_and_variances":"PASS",
            "independent_numpy_aggregation_maximum_difference_mm":differences,
            "all_30_seasons_fine_observations_reconstruct_original_1deg_max_difference_mm":float(np.nanmax(abs(error))),
            "training_years":[1982,2010],"verification_year_excluded_from_fitting":2023,
            "verification_script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (ROOT/"verification.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))


if __name__=="__main__": main()
