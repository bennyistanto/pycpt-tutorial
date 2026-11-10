"""Prepare a separate 0.25-degree case; preserve all original 1-degree artifacts."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import shapely
import shapely.geometry
import xarray as xr

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from pycpt_tutorial.country_grid import aggregate_country_rainfall, training_complete_mask
from pycpt_tutorial.export import save_netcdf

OLD=Path.home()/"CPT/cases/indonesia-ond-2023"
ROOT=Path.home()/"CPT/cases/indonesia-ond-2023-025deg"
SOURCE=Path("/mnt/e/temp/chirps/rolling_dekad/wld_cli_chirps3_month3_bydekad_1981_2025.nc")
TRAIN=list(range(1982,2011)); YEARS=TRAIN+[2023]


def main():
    if (ROOT/"preparation.json").exists():
        print("Prepared 0.25-degree inputs already exist; retaining cache.")
        return
    (ROOT/"inputs").mkdir(parents=True,exist_ok=True)
    geometry=shapely.geometry.shape(json.loads((OLD/"inputs/indonesia_boundary.geojson").read_text()))
    shapely.prepare(geometry)
    rains=[]; valid_weights=[]
    with xr.open_dataset(SOURCE) as source:
        times=pd.DatetimeIndex(source.time.values)
        indices=[int(np.flatnonzero((times.year==year)&(times.month==12)&(times.day==21))[0]) for year in YEARS]
        for year,bounds in zip(YEARS,source.time_bnds.isel(time=indices).values):
            assert pd.Timestamp(bounds[0])==pd.Timestamp(f"{year}-10-01")
            assert pd.Timestamp(bounds[1])==pd.Timestamp(f"{year+1}-01-01")
        native=source.precip.sel(lon=slice(94,142),lat=slice(-12,7))
        assert native.sizes["lat"]==380 and native.sizes["lon"]==960
        lon,lat=np.meshgrid(native.lon.values,native.lat.values)
        country=xr.DataArray(shapely.contains_xy(geometry,lon,lat),dims=("lat","lon"),coords={"lat":native.lat,"lon":native.lon})
        for year,index in zip(YEARS,indices):
            print("AGGREGATING_CHIRPS_025",year,flush=True)
            data=native.isel(time=index).load()
            assert not bool((data<0).any())
            block=aggregate_country_rainfall(data,country,5,minimum_coverage=.99)
            rains.append(block.precipitation.drop_vars("time",errors="ignore"))
            valid_weights.append(block.valid_land_weight.drop_vars("time",errors="ignore"))
        fraction=block.indonesia_fraction
        country_weight=block.country_land_weight
    starts=pd.to_datetime([f"{year}-10-01" for year in YEARS])
    ends=pd.to_datetime([f"{year}-12-31" for year in YEARS])
    T=pd.Index(starts+(ends-starts)/2,name="T")
    rain=xr.concat(rains,dim=T)
    valid_weight=xr.concat(valid_weights,dim=T)
    def grid(da):
        da=da.rename({"lat":"Y","lon":"X"})
        da=da.assign_coords(Y=-12+.125+np.arange(76)*.25,X=94+.125+np.arange(192)*.25)
        return da.sortby("Y",ascending=False)
    rain=grid(rain).assign_coords(Ti=("T",starts),Tf=("T",ends)).transpose("T","Y","X")
    valid_weight=grid(valid_weight).transpose("T","Y","X")
    fraction=grid(fraction); country_weight=grid(country_weight)
    mask=training_complete_mask(rain,TRAIN)
    rain=rain.where(mask)
    rain.attrs={"units":"mm","missing":-999.,"standard_name":"precipitation_amount","long_name":"Indonesia country-land OND accumulated rainfall at 0.25 degrees","cell_methods":"time: sum area: mean"}
    valid_weight.attrs={"units":"1","long_name":"Sum of native cosine-latitude weights with valid observed rainfall"}
    country_weight.attrs={"units":"1","long_name":"Sum of native cosine-latitude weights for all Indonesia pixels"}
    fraction.attrs={"units":"1","long_name":"Fraction of native pixel centres inside Indonesia"}
    mask=mask.astype("int8")
    mask.attrs={"flag_values":np.array([0,1],dtype="int8"),"flag_meanings":"excluded included","long_name":"Country grid cells with complete training-year coverage at the 99-percent rule"}
    obs=xr.Dataset({"precipitation":rain,"valid_land_weight":valid_weight})
    mask_ds=xr.Dataset({"analysis_mask":mask,"country_land_weight":country_weight,"indonesia_fraction":fraction})
    metadata={"case_id":"indonesia-ond-2023-025deg","source":"Local CHIRPS v3.0","source_file":str(SOURCE),"resolution_degrees":.25,
              "aggregation":"Country-masked native 0.05-degree rainfall, cosine-latitude-weighted mean in 5x5 blocks",
              "coverage_rule":"At least 99 percent of native country weight valid in each training season; mask fitted on 1982–2010 only",
              "coordinate_rule":"Exact nominal 0.25-degree block centres; native coordinate storage-rounding noise removed"}
    save_netcdf(obs,ROOT/"inputs/observations_chirps3_ond_025.nc",metadata=metadata,overwrite=True)
    save_netcdf(mask_ds,ROOT/"inputs/indonesia_analysis_mask_025.nc",metadata=metadata,overwrite=True)
    valid_cells=int(mask.sum()); total_cells=int((fraction>0).sum())
    retained=float(country_weight.where(mask.astype(bool),0).sum()/country_weight.sum())
    source_hashes={name:hashlib.sha256((OLD/"inputs"/name).read_bytes()).hexdigest() for name in ["cfsv2_hindcasts_ond.nc","cfsv2_forecasts_ond.nc","indonesia_boundary.geojson"]}
    record={"case_id":"indonesia-ond-2023-025deg","created_at":dt.datetime.now(dt.timezone.utc).isoformat(),"training_years":[1982,2010],"verification_year":2023,
            "observations_source":str(SOURCE),"source_size_bytes":SOURCE.stat().st_size,"resolution_degrees":.25,"native_block_factor":5,
            "grid_shape":{"Y":76,"X":192},"country_cells_with_land":total_cells,"included_cells":valid_cells,"retained_native_country_land_weight_fraction":retained,
            "unchanged_model_and_boundary_input_sha256":source_hashes,"predictor_resolution_degrees":1.,"minimum_training_coverage":.99}
    (ROOT/"preparation.json").write_text(json.dumps(record,indent=2)+"\n")
    print("PREPARATION_COMPLETE",json.dumps(record,indent=2),flush=True)


if __name__=="__main__": main()
