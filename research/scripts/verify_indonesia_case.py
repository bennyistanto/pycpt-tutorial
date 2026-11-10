"""Independent checks on the historical case and selected original dekadal values."""
from pathlib import Path
import hashlib
import json
import numpy as np
import xarray as xr

ROOT = Path.home() / "CPT/cases/indonesia-ond-2023"
manifest = json.loads((ROOT/"case_manifest.json").read_text())
for name,info in manifest["outputs"].items():
    assert hashlib.sha256((ROOT/"outputs"/name).read_bytes()).hexdigest() == info["sha256"]
with xr.open_dataset(ROOT/"outputs/cca_forecast_2023.nc") as forecast:
    with xr.open_dataset(ROOT/"outputs/indonesia_analysis_mask.nc") as country:
        valid=country.analysis_mask.astype(bool)
        assert int(valid.sum()) == 369
        assert int(forecast.deterministic.isel(T=0).notnull().sum()) == 369
        for name in ("deterministic","prediction_error_variance","probabilistic"):
            assert not bool(forecast[name].where(~valid).notnull().any())
            expected = int(valid.sum()) * (forecast.sizes["C"] if name == "probabilistic" else 1)
            assert int(forecast[name].count()) == expected
        assert float(forecast.prediction_error_variance.min()) >= 0
        assert float(forecast.probabilistic.min()) >= 0
        assert float(forecast.probabilistic.max()) <= 100
        np.testing.assert_allclose(forecast.probabilistic.sum("C").isel(T=0).where(valid).values[valid.values],100,atol=.1)
        assert forecast.deterministic.attrs["units"] == "mm"
with xr.open_dataset(ROOT/"outputs/cfsv2_training_predictors.nc") as training:
    np.testing.assert_array_equal(training["T"].dt.year,np.arange(1982,2011))
    assert 2023 not in training["T"].dt.year.values
with xr.open_dataset(ROOT/"outputs/deterministic_hindcast_comparison.nc") as manual:
    with xr.open_dataset(ROOT/"outputs/cca_native_skill.nc") as native:
        np.testing.assert_allclose(manual.cca_rmse,native.root_mean_squared_error,atol=.002,rtol=0)
        np.testing.assert_allclose(manual.cca_pearson,native.pearson,atol=1e-5,rtol=0)

checks=[]
with xr.open_dataset("/mnt/e/temp/chirps/dekad/wld_cli_chirps3_dekad_1981_2025.nc") as raw:
    with xr.open_dataset("/mnt/e/temp/chirps/rolling_dekad/wld_cli_chirps3_month3_bydekad_1981_2025.nc") as rolling:
        for year in (1990,2023):
            for lon,lat in ((101.5,.5),(110.5,-7.5),(137.5,-3.5)):
                nine=raw.precip.sel(lon=lon,lat=lat,method="nearest").sel(time=slice(f"{year}-10-01",f"{year}-12-21")).load()
                assert nine.sizes["time"] == 9
                total=nine.sum("time",skipna=False)
                precomputed=rolling.precip.sel(lon=lon,lat=lat,method="nearest").sel(time=f"{year}-12-21").load()
                assert np.isfinite(total) and np.isfinite(precomputed)
                np.testing.assert_allclose(total,precomputed,rtol=1e-6,atol=.001)
                checks.append({"year":year,"requested_lon":lon,"requested_lat":lat,"raw_sum_mm":float(total),"rolling_total_mm":float(precomputed)})
report={"status":"PASS","output_hashes_verified":len(manifest["outputs"]),"country_mask_and_probability_checks":"PASS",
        "forecast_year_excluded_from_training":True,"native_vs_direct_rmse_tolerance_mm":.002,
        "native_vs_direct_pearson_tolerance":1e-5,"independent_dekad_sum_checks":checks}
(ROOT/"verification.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps(report,indent=2))
