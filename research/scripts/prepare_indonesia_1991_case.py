"""Audit and prepare1991–2020 inputs before fitting the0.25° Indonesia case."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys

import cptdl
from cptdl.utilities import read_dlauth
from cptio import open_cptdataset
import numpy as np
import pandas as pd
import requests
import xarray as xr

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from pycpt_tutorial.export import save_netcdf
import prepare_indonesia_025_case as observations

OLD=Path.home()/"CPT/cases/indonesia-ond-2023"
PREVIOUS=Path.home()/"CPT/cases/indonesia-ond-2023-025deg"
ROOT=Path.home()/"CPT/cases/indonesia-ond-2023-025deg-1991-2020"
TRAIN=list(range(1991,2021))
BASE="https://iridl.ldeo.columbia.edu/SOURCES/.Models/.NMME/.NCEP-CFSv2/.HINDCAST/.PENTAD_SAMPLES_FULL/.prec/"


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    with xr.open_dataset(path) as ds: return ds.load()


def fetch(url,path,key):
    if not path.exists():
        with requests.get(url,cookies={"__dlauth_id":key},timeout=240) as response:
            response.raise_for_status()
            if path.suffix==".tsv" and not response.content.startswith(b"xmlns:cpt"):
                raise RuntimeError("IRI returned non-CPT content; credentials not logged")
            path.write_bytes(response.content)


def parse_monthly(path):
    text=path.read_text()
    dates=[pd.Timestamp(v.strip()) for v in re.findall(r"cpt:S=([^,\r\n]+)",text)]
    assert len(dates)==90 and all(v.month==9 and v.day==1 and v.hour==0 for v in dates)
    assert [v.year for v in dates]==[year for year in TRAIN for _ in range(3)]
    parsing=path.with_suffix(".parsing.tsv")
    parsing.write_text(re.sub(r",\s*cpt:S=[^,\r\n]+","",text))
    ds=open_cptdataset(str(parsing))
    da=ds[list(ds.data_vars)[0]].sortby("T").transpose("T","Y","X")
    expected=pd.to_datetime([f"{year}-{month:02d}-16" for year in TRAIN for month in (10,11,12)])
    assert len(np.unique(da["T"].values))==90
    np.testing.assert_array_equal(da["T"].dt.year,expected.year)
    np.testing.assert_array_equal(da["T"].dt.month,expected.month)
    np.testing.assert_allclose(da.X,np.arange(85,156),atol=1e-8)
    np.testing.assert_allclose(da.Y,np.arange(20,-21,-1),atol=1e-8)
    assert bool(np.isfinite(da).all())
    return da


def main():
    if (ROOT/"continuity.json").exists() and json.loads((ROOT/"continuity.json").read_text()).get("audit_schema_version")==2:
        print("Completed continuity audit retained."); return
    (ROOT/"inputs").mkdir(parents=True,exist_ok=True)
    key=read_dlauth(); assert key
    args=dict(fdate=dt.datetime(2023,9,1),first_year=1991,final_year=2020,target="Oct-Dec",
              predictor_extent=dict(west=85,east=155,south=-20,north=20),lead_low=1.5,lead_high=3.5,filetype="cptv10.tsv")
    url=cptdl.evaluate_url(cptdl.hindcasts["CFSv2.PRCP"],**args)
    url=url.replace("%5BL%5D//keepgrids/average/","").replace("/92/mul/","/")
    raw=ROOT/"inputs/cfsv2_hindcasts_monthly.tsv"
    print("FETCHING_FULL_DOMAIN_MONTHLY_MEANS",flush=True)
    fetch(url,raw,key)
    monthly=parse_monthly(raw)
    assert monthly.attrs["units"]=="mm/day" and float(monthly.min())>=0
    #0*valid+1 yields1; missing values remain missing. Sum over members counts
    # valid members without transferring the entire ensemble. Independently
    # verify the operation against actual member values at a Java point.
    count_url=url.replace("%5BM%5D/average/","0/mul/1/add/%5BM%5D/sum/")
    assert count_url!=url
    count_path=ROOT/"inputs/cfsv2_valid_member_counts_monthly.tsv"
    print("FETCHING_FULL_DOMAIN_VALID_MEMBER_COUNTS",flush=True)
    fetch(count_url,count_path,key)
    counts=parse_monthly(count_path)
    member_url=url.replace("%5BM%5D/average/","").replace("%5BX/Y%5D%5BL/S/add%5D/cptv10.tsv","data.nc")
    member_url=member_url.replace("Y/-20/20/RANGEEDGES","Y/-7/-7/RANGEEDGES").replace("X/85/155/RANGEEDGES","X/110/110/RANGEEDGES")
    member_path=ROOT/"inputs/cfsv2_members_java_point.nc"
    fetch(member_url,member_path,key)
    with xr.open_dataset(member_path,decode_times=False) as ensemble:
        print("ENSEMBLE_LAYOUT",dict(ensemble.sizes),list(ensemble.data_vars),flush=True)
        members=ensemble["prec"].transpose("S","L","M","Y","X").load()
    assert members.shape[:2]==(30,3)
    np.testing.assert_allclose(members.S,(np.asarray(TRAIN)-1960)*12+8)
    np.testing.assert_allclose(members.L,[1.5,2.5,3.5])
    np.testing.assert_allclose(members.X,[110]); np.testing.assert_allclose(members.Y,[-7])
    np.testing.assert_array_equal(members.count("M").values.reshape(90),counts.sel(X=110,Y=-7).values)
    ensemble_means=members.mean("M").values.reshape(90)
    # CPT text rates are rounded; native NetCDF means must agree to that precision.
    np.testing.assert_allclose(ensemble_means,monthly.sel(X=110,Y=-7).values,atol=1e-4,rtol=1e-5)
    assert float(counts.min())>=1
    np.testing.assert_allclose(counts,np.round(counts),atol=1e-8)
    counts.attrs={"units":"1","long_name":"Number of valid CFSv2 members before ensemble averaging"}
    valid_fraction=xr.DataArray(np.isfinite(members.values).mean(axis=(1,3,4)),dims=("initialization_year","member"),
                               coords={"initialization_year":TRAIN,"member":members.M.values},attrs={"units":"1","long_name":"Java point110E7S: member valid fraction across three target months"})
    save_netcdf(xr.Dataset({"precipitation_rate":monthly,"valid_member_count":counts,"java_point_member_valid_fraction":valid_fraction}),ROOT/"inputs/cfsv2_monthly_continuity.nc",overwrite=True,
                metadata={"rate_units":"mm/day","period":"1991–2020","purpose":"Full-domain monthly completeness and member coverage audit"})
    totals=[]
    for year in TRAIN:
        part=monthly.sel(T=monthly["T"].dt.year==year)
        days=(part.Tf-part.Ti)/np.timedelta64(1,"D")+1
        np.testing.assert_array_equal(days,[31,30,31])
        np.testing.assert_array_equal(part.Ti,pd.to_datetime([f"{year}-{m:02d}-01" for m in (10,11,12)]))
        np.testing.assert_array_equal(part.Tf,pd.to_datetime([f"{year}-10-31",f"{year}-11-30",f"{year}-12-31"]))
        totals.append((part*days).sum("T",skipna=False).drop_vars(["Ti","Tf","S"],errors="ignore"))
    starts=pd.to_datetime([f"{year}-10-01" for year in TRAIN]); ends=pd.to_datetime([f"{year}-12-31" for year in TRAIN])
    rain=xr.concat(totals,dim=pd.Index(starts+(ends-starts)/2,name="T"))
    rain=rain.assign_coords(Ti=("T",starts),Tf=("T",ends),S=("T",pd.to_datetime([f"{year}-09-01" for year in TRAIN]))).rename("precipitation")
    rain.attrs={"units":"mm","missing":-999.,"standard_name":"precipitation_amount","cell_methods":"time: sum","long_name":"CFSv2 ensemble-mean OND rainfall accumulation"}
    old_x=read(OLD/"inputs/cfsv2_hindcasts_ond.nc").precipitation
    overlap=rain.sel(T=rain["T"].dt.year<=2010)
    original=old_x.sel(T=old_x["T"].dt.year>=1991)
    xr.testing.assert_allclose(overlap,original)
    model_difference=float(abs(overlap-original).max())
    save_netcdf(rain,ROOT/"inputs/cfsv2_hindcasts_ond.nc",overwrite=True,metadata={"source":BASE,"aggregation":"Monthly rate times31/30/31days; no statistical transition adjustment"})

    metadata_path=ROOT/"inputs/cfsv2_source_metadata.html"
    fetch(BASE,metadata_path,key)
    text=re.sub(r"\s+"," ",re.sub(r"<[^>]*>"," ",metadata_path.read_text()))
    (ROOT/"inputs/cfsv2_source_metadata.txt").write_text(text)
    assert "1 Apr 2011" in text and "FORECAST" in text and "MONTHLY" in text

    # Reuse the established native-pixel aggregation implementation with a new
    # case root and period. It only reads the source and never writes old cases.
    observations.ROOT=ROOT; observations.TRAIN=TRAIN; observations.YEARS=TRAIN+[2023]
    observations.main()
    # Correct period-specific metadata from the original fixed-period helper.
    for name in ("observations_chirps3_ond_025.nc","indonesia_analysis_mask_025.nc"):
        path=ROOT/"inputs"/name; ds=read(path)
        ds.attrs.update(case_id=ROOT.name,coverage_rule="At least 99 percent valid native country weight in every 1991–2020 training season; 2023 withheld")
        save_netcdf(ds,path,overwrite=True)
    preparation=json.loads((ROOT/"preparation.json").read_text())
    preparation.update(case_id=ROOT.name,training_years=[1991,2020],model_input_sha256=sha(ROOT/"inputs/cfsv2_hindcasts_ond.nc"))
    if "unchanged_model_and_boundary_input_sha256" in preparation:
        preparation["frozen_reference_model_and_boundary_input_sha256"]=preparation.pop("unchanged_model_and_boundary_input_sha256")
    (ROOT/"preparation.json").write_text(json.dumps(preparation,indent=2)+"\n")
    obs=read(ROOT/"inputs/observations_chirps3_ond_025.nc").precipitation
    old_obs=read(PREVIOUS/"outputs/observations_chirps3_ond_025.nc").precipitation
    old_mask=read(PREVIOUS/"outputs/indonesia_analysis_mask_025.nc").analysis_mask.astype(bool)
    new_country=read(ROOT/"inputs/indonesia_analysis_mask_025.nc")
    new_mask=new_country.analysis_mask.astype(bool)
    common=old_mask&new_mask
    common_years=list(range(1991,2011))+[2023]
    a=obs.sel(T=obs["T"].dt.year.isin(common_years)).where(common)
    b=old_obs.sel(T=old_obs["T"].dt.year.isin(common_years)).where(common)
    xr.testing.assert_allclose(a,b)
    # Descriptive transition diagnostics, not evidence of statistical homogeneity:
    # ten-year means mix climate variability and operational-system differences.
    domain_mean=rain.weighted(np.cos(np.deg2rad(rain.Y))).mean(("Y","X"))
    before=rain.sel(T=rain["T"].dt.year<=2010)
    after=rain.sel(T=rain["T"].dt.year>=2011)
    shift=after.mean("T")-before.mean("T")
    land_weights=new_country.country_land_weight.where(new_mask,0)
    train_obs=obs.sel(T=obs["T"].dt.year.isin(TRAIN))
    model_indonesia=rain.interp(X=obs.X,Y=obs.Y).where(new_mask).weighted(land_weights).mean(("Y","X"))
    observed_indonesia=train_obs.weighted(land_weights).mean(("Y","X"))
    transition={}
    for label,selection in (("1991_2010",rain["T"].dt.year<=2010),("2011_2020",rain["T"].dt.year>=2011)):
        mx=model_indonesia.sel(T=selection); oy=observed_indonesia.sel(T=selection)
        transition[label]={"years":int(mx.sizes["T"]),"indonesia_model_mean_mm":float(mx.mean()),"indonesia_observed_mean_mm":float(oy.mean()),
                           "indonesia_model_bias_mm":float((mx-oy).mean()),"indonesia_model_interannual_std_mm":float(mx.std("T",ddof=1)),"indonesia_observed_interannual_std_mm":float(oy.std("T",ddof=1))}
    per_year=[]
    for year in TRAIN:
        sub=monthly.sel(T=monthly["T"].dt.year==year)
        member=counts.sel(T=counts["T"].dt.year==year)
        per_year.append({"year":year,"monthly_records":sub.sizes["T"],"finite_values":int(sub.count()),"expected_values":sub.size,
                         "minimum_members":int(member.min()),"maximum_members":int(member.max()),"java_point_active_member_ids":valid_fraction.member.where(valid_fraction.sel(initialization_year=year)>0,drop=True).values.tolist(),
                         "domain_mean_ond_mm":float(domain_mean.sel(T=domain_mean["T"].dt.year==year).item()),"indonesia_model_mean_mm":float(model_indonesia.sel(T=model_indonesia["T"].dt.year==year).item()),
                         "indonesia_observed_mean_mm":float(observed_indonesia.sel(T=observed_indonesia["T"].dt.year==year).item())})
    report={"case_id":ROOT.name,"audit_schema_version":2,"checked_at":dt.datetime.now(dt.timezone.utc).isoformat(),"status":"PASS_COMPLETENESS_WITH_SOURCE_TRANSITION",
            "training_years":[1991,2020],"monthly_records":90,"spatial_cells":monthly.sizes["X"]*monthly.sizes["Y"],
            "missing_or_nonfinite_monthly_values":int((~np.isfinite(monthly)).sum()),"minimum_valid_members":int(counts.min()),"maximum_valid_members":int(counts.max()),
            "model_overlap_1991_2010_max_difference_mm":model_difference,"observed_overlap_1991_2010_and2023_max_difference_mm":float(abs(a-b).max()),
            "observation_training_cells":int(new_mask.sum()),"old_training_cells":int(old_mask.sum()),"common_fine_cells":int(common.sum()),
            "observed_2023_finite_on_common_cells":int(obs.sel(T=obs["T"].dt.year==2023).where(common).count()),
            "appended_operational_source_from":"2011-04-01","source_transition_note":"Completeness passes, but the source blends retrospective hindcasts and operational forecasts. No homogeneity guarantee or transition correction.",
            "pre2011_domain_mean_mm":float(domain_mean.sel(T=domain_mean["T"].dt.year<=2010).mean()),"post2011_domain_mean_mm":float(domain_mean.sel(T=domain_mean["T"].dt.year>=2011).mean()),
            "post_minus_pre_grid_mean_shift_rmse_mm":float(np.sqrt((shift**2).mean())),"indonesia_transition_diagnostics":transition,"member_coordinate_ids":members.M.values.tolist(),"per_year":per_year,
            "sources":{"ensemble_mean":{"url":url,"sha256":sha(raw)},"valid_member_counts":{"url":count_url,"sha256":sha(count_path)},"java_point_members":{"url":member_url,"sha256":sha(member_path)},"metadata":{"url":BASE,"sha256":sha(metadata_path)}},
            "limitations":["Descriptive pre/post shifts cannot separate climate variability from archive/system changes","Ensemble member count equality does not establish member identity or statistical homogeneity","No2023 values used to fit either training mask or model"]}
    (ROOT/"continuity.json").write_text(json.dumps(report,indent=2)+"\n")
    print("CONTINUITY_COMPLETE",json.dumps({k:v for k,v in report.items() if k not in ("sources","per_year")},indent=2),flush=True)


if __name__=="__main__": main()
