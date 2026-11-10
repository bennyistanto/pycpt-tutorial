"""Audit archived OND2021–2024 forecasts and aggregate held-out CHIRPS at0.25°."""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path
import re
import sys

import cptdl
from cptdl.utilities import read_dlauth
from cptio import open_cptdataset
import numpy as np
import pandas as pd
import shapely
import shapely.geometry
import xarray as xr

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from pycpt_tutorial.country_grid import aggregate_country_rainfall
from pycpt_tutorial.export import save_netcdf
from prepare_indonesia_1991_case import OLD, PREVIOUS, ROOT as RECENT, read, sha, fetch

ROOT=Path.home()/"CPT/cases/indonesia-ond-2021-2024-025deg"
YEARS=[2021,2022,2023,2024]
NEW_YEARS=[2021,2022,2024]
SOURCE=Path("/mnt/e/temp/chirps/rolling_dekad/wld_cli_chirps3_month3_bydekad_1981_2025.nc")


def parse_months(path):
    text=path.read_text()
    initializations=[pd.Timestamp(value.strip()) for value in re.findall(r"cpt:S=([^,\r\n]+)",text)]
    assert initializations==[pd.Timestamp(f"{year}-09-01") for year in YEARS for _ in range(3)]
    # Retain raw source dates; work around cptio1.4 repeated-S deduplication.
    parsing=path.with_suffix(".parsing.tsv")
    parsing.write_text(re.sub(r",\s*cpt:S=[^,\r\n]+","",text))
    ds=open_cptdataset(str(parsing)); da=ds[list(ds.data_vars)[0]].sortby("T").transpose("T","Y","X")
    assert da.shape==(12,41,71) and len(np.unique(da["T"].values))==12
    np.testing.assert_array_equal(da["T"].dt.year,np.repeat(YEARS,3))
    np.testing.assert_array_equal(da["T"].dt.month,np.tile([10,11,12],4))
    np.testing.assert_allclose(da.X,np.arange(85,156)); np.testing.assert_allclose(da.Y,np.arange(20,-21,-1))
    assert bool(np.isfinite(da).all())
    return da


def main():
    if (ROOT/"availability.json").exists():
        print("Completed held-out input audit retained."); return
    (ROOT/"inputs").mkdir(parents=True,exist_ok=True)
    key=read_dlauth(); assert key
    args=dict(fdate=dt.datetime(2023,9,1),first_year=2021,final_year=2024,target="Oct-Dec",lead_low=1.5,lead_high=3.5,
              predictor_extent=dict(west=85,east=155,south=-20,north=20),filetype="cptv10.tsv")
    # The established forecast template uses this same extended source. Query
    # all four September initializations to audit the cached2023 overlap too.
    url=cptdl.evaluate_url(cptdl.hindcasts["CFSv2.PRCP"],**args).replace("%5BL%5D//keepgrids/average/","").replace("/92/mul/","/")
    original=json.loads((OLD/"availability.json").read_text())["model_sources"]["forecasts"]["url"]
    assert url.replace("2021-2024","2023")==original
    raw=ROOT/"inputs/cfsv2_forecasts_monthly.tsv"
    print("FETCHING_FORECAST_MONTHS",YEARS,flush=True); fetch(url,raw,key)
    monthly=parse_months(raw)
    assert monthly.attrs["units"]=="mm/day" and float(monthly.min())>=0
    count_url=url.replace("%5BM%5D/average/","0/mul/1/add/%5BM%5D/sum/")
    count_path=ROOT/"inputs/cfsv2_valid_member_counts_monthly.tsv"
    print("FETCHING_VALID_MEMBER_COUNTS",flush=True); fetch(count_url,count_path,key)
    counts=parse_months(count_path)
    assert float(counts.min())>=1
    np.testing.assert_array_equal(counts,np.round(counts))
    counts.attrs={"units":"1","long_name":"Valid-member count before ensemble averaging"}
    save_netcdf(xr.Dataset({"precipitation_rate":monthly,"valid_member_count":counts}),ROOT/"inputs/cfsv2_forecast_monthly_audit.nc",overwrite=True)
    totals=[]
    for year in YEARS:
        part=monthly.sel(T=monthly["T"].dt.year==year)
        np.testing.assert_array_equal(part.Ti,pd.to_datetime([f"{year}-{month:02d}-01" for month in (10,11,12)]))
        np.testing.assert_array_equal(part.Tf,pd.to_datetime([f"{year}-10-31",f"{year}-11-30",f"{year}-12-31"]))
        days=(part.Tf-part.Ti)/np.timedelta64(1,"D")+1
        np.testing.assert_array_equal(days,[31,30,31])
        totals.append((part*days).sum("T",skipna=False).drop_vars(["Ti","Tf","S"],errors="ignore"))
    starts=pd.to_datetime([f"{year}-10-01" for year in YEARS]); ends=pd.to_datetime([f"{year}-12-31" for year in YEARS])
    T=pd.Index(starts+(ends-starts)/2,name="T")
    forecast=xr.concat(totals,dim=T).assign_coords(Ti=("T",starts),Tf=("T",ends),S=("T",pd.to_datetime([f"{year}-09-01" for year in YEARS]))).rename("precipitation")
    forecast.attrs={"units":"mm","missing":-999.,"standard_name":"precipitation_amount","cell_methods":"time: sum","long_name":"Archived CFSv2 ensemble-mean OND accumulation"}
    frozen_f=read(OLD/"inputs/cfsv2_forecasts_ond.nc").precipitation
    xr.testing.assert_allclose(forecast.sel(T=forecast["T"].dt.year==2023),frozen_f)
    save_netcdf(forecast,ROOT/"inputs/cfsv2_forecast_predictors.nc",overwrite=True,metadata={"source":url,"integration":"Calendar month rates multiplied by31/30/31days"})

    old_country=read(PREVIOUS/"outputs/indonesia_analysis_mask_025.nc")
    recent_country=read(RECENT/"outputs/indonesia_analysis_mask_025.nc")
    xr.testing.assert_allclose(old_country.country_land_weight,recent_country.country_land_weight)
    common=old_country.analysis_mask.astype(bool)&recent_country.analysis_mask.astype(bool)
    geometry=shapely.geometry.shape(json.loads((OLD/"inputs/indonesia_boundary.geojson").read_text())); shapely.prepare(geometry)
    rain=[]; valid_weights=[]
    with xr.open_dataset(SOURCE) as source:
        times=pd.DatetimeIndex(source.time.values)
        native=source.precip.sel(lon=slice(94,142),lat=slice(-12,7))
        lon,lat=np.meshgrid(native.lon,native.lat)
        country=xr.DataArray(shapely.contains_xy(geometry,lon,lat),dims=("lat","lon"),coords={"lat":native.lat,"lon":native.lon})
        for year in YEARS:
            indices=np.flatnonzero((times.year==year)&(times.month==12)&(times.day==21)); assert indices.size==1
            index=int(indices[0]); bounds=source.time_bnds.isel(time=index).values
            assert pd.Timestamp(bounds[0])==pd.Timestamp(f"{year}-10-01") and pd.Timestamp(bounds[1])==pd.Timestamp(f"{year+1}-01-01")
            print("AGGREGATING_HELD_OUT_CHIRPS",year,flush=True)
            values=native.isel(time=index).load(); assert not bool((values<0).any())
            block=aggregate_country_rainfall(values,country,5,minimum_coverage=.99)
            def grid(da):
                da=da.drop_vars("time",errors="ignore").rename({"lat":"Y","lon":"X"})
                return da.assign_coords(Y=-12+.125+np.arange(76)*.25,X=94+.125+np.arange(192)*.25).sortby("Y",ascending=False)
            rain.append(grid(block.precipitation)); valid_weights.append(grid(block.valid_land_weight))
    observations=xr.concat(rain,dim=T).assign_coords(Ti=("T",starts),Tf=("T",ends)).transpose("T","Y","X").where(common)
    observations.name="precipitation"
    observations.attrs={"units":"mm","missing":-999.,"standard_name":"precipitation_amount","cell_methods":"time: sum area: mean","long_name":"Held-out OND country-land rainfall at0.25degrees"}
    valid=xr.concat(valid_weights,dim=T).transpose("T","Y","X")
    frozen_obs=read(PREVIOUS/"outputs/observations_chirps3_ond_025.nc").precipitation
    xr.testing.assert_allclose(observations.sel(T=observations["T"].dt.year==2023),frozen_obs.sel(T=frozen_obs["T"].dt.year==2023).where(common))
    # This additional mask affects scoring only; both training masks and all
    # model fits remain frozen and independent of verification-year availability.
    evaluation=common&observations.notnull().all("T")
    footprint=xr.Dataset({"old_training_mask":old_country.analysis_mask,"recent_training_mask":recent_country.analysis_mask,
                          "common_training_mask":common.astype("int8"),"evaluation_mask":evaluation.astype("int8"),
                          "country_land_weight":old_country.country_land_weight,"evaluation_weight":old_country.country_land_weight.where(evaluation,0)})
    save_netcdf(xr.Dataset({"precipitation":observations,"valid_land_weight":valid}),ROOT/"inputs/observations_chirps3_ond_2021_2024.nc",overwrite=True,
                metadata={"source_file":str(SOURCE),"aggregation":"Native0.05degree country-only5x5 cosine-latitude weighted means;>=99percent coverage","mask_rule":"Unchanged training masks; common verification mask used only for evaluation"})
    save_netcdf(footprint,ROOT/"inputs/evaluation_footprint.nc",overwrite=True)
    report={"case_id":ROOT.name,"status":"PASS","checked_at":dt.datetime.now(dt.timezone.utc).isoformat(),"years":YEARS,"new_forecast_years":NEW_YEARS,
            "monthly_records":12,"predictor_grid_cells":2911,"finite_monthly_values":int(monthly.count()),"valid_member_count_range":[int(counts.min()),int(counts.max())],
            "training_masks_unchanged":True,"common_training_cells":int(common.sum()),"all_years_evaluation_cells":int(evaluation.sum()),
            "original_common_land_weight_retained":float(footprint.evaluation_weight.sum()/old_country.country_land_weight.where(common,0).sum()),
            "forecast_2023_matches_frozen_case":True,"observed_2023_matches_frozen_case":True,
            "per_year":[{"year":year,"finite_model_monthly_values":int(monthly.sel(T=monthly["T"].dt.year==year).count()),"minimum_members":int(counts.sel(T=counts["T"].dt.year==year).min()),
                         "maximum_members":int(counts.sel(T=counts["T"].dt.year==year).max()),"observed_common_cells":int(observations.sel(T=observations["T"].dt.year==year).count())} for year in YEARS],
            "sources":{"monthly_means":{"url":url,"sha256":sha(raw)},"valid_member_counts":{"url":count_url,"sha256":sha(count_path)}},
            "limitations":["Retrospective current-vintage archive/CHIRPS3 replay","1991–2020 calibration retains previously audited reforecast/operational transition","Evaluation mask uses verification availability only, never refits models"]}
    (ROOT/"availability.json").write_text(json.dumps(report,indent=2)+"\n")
    print("PREPARATION_COMPLETE",json.dumps(report,indent=2),flush=True)


if __name__=="__main__": main()
