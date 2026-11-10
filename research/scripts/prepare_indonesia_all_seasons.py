"""Audit and prepare all12 ending-year seasonal targets with resumable caches."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests
import shapely
import shapely.geometry
import xarray as xr
from cptdl.utilities import read_dlauth
from cptio import open_cptdataset

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from pycpt_tutorial.seasons import SEASONS, season_window
from pycpt_tutorial.country_grid import aggregate_country_rainfall, training_complete_mask
from pycpt_tutorial.export import save_netcdf
from prepare_indonesia_1991_case import OLD, PREVIOUS, ROOT as RECENT, BASE, read, sha
from prepare_indonesia_ond_holdouts import ROOT as HOLDOUTS, SOURCE

ROOT=Path.home()/"CPT/cases/indonesia-all-seasons-2021-2024-025deg"
ALL_YEARS=list(range(1983,2025))
EVAL_YEARS=[2021,2022,2023,2024]
PERIODS={"1983_2010":list(range(1983,2011)),"1991_2020":list(range(1991,2021))}


def download(url,path,key):
    if path.exists(): return
    temporary=path.with_suffix(path.suffix+".part")
    for attempt in range(3):
        try:
            start=time.monotonic()
            with requests.get(url,cookies={"__dlauth_id":key},timeout=(30,90),stream=True) as response:
                response.raise_for_status()
                with temporary.open("wb") as output:
                    for chunk in response.iter_content(65536):
                        if time.monotonic()-start>900: raise TimeoutError("Archive transfer exceeded15minutes")
                        output.write(chunk)
            if path.suffix==".nc":
                with temporary.open("rb") as stream: signature=stream.read(8)
                if not (signature.startswith(b"CDF") or signature.startswith(b"\x89HDF")):
                    raise RuntimeError("Archive returned non-NetCDF content; credentials not logged")
            temporary.replace(path)
            print("DOWNLOADED",path.name,path.stat().st_size,flush=True); return
        except (requests.RequestException,TimeoutError) as exc:
            if attempt==2: raise
            print("RETRY",path.name,type(exc).__name__,flush=True)
            time.sleep(2)


def urls(season):
    windows=[season_window(season,year) for year in ALL_YEARS]
    first=windows[0].initialization; last=windows[-1].initialization
    selection=quote(f"(0000 1 {first.strftime('%b')} {first.year}-{last.year})",safe="")
    prefix=BASE+f"S/{selection}/VALUES/L/1.5/3.5/RANGEEDGES/Y/-20/20/RANGEEDGES/X/85/155/RANGEEDGES/"
    return prefix+"%5BM%5D/average/data.nc",prefix+"0/mul/1/add/%5BM%5D/sum/data.nc"


def source_boundary(key):
    path=ROOT/"raw/source_metadata.html"; download(BASE,path,key)
    text=re.sub(r"\s+"," ",re.sub(r"<[^>]*>"," ",path.read_text()))
    assert re.search(r"S grid:.*?1 Jan 1982",text)
    record={"initialization_start":"1982-01-01","metadata_sha256":sha(path),"source":BASE,
            "unavailable1982_target_seasons_under_ending_year_convention":[name for name in SEASONS if season_window(name,1982).initialization<dt.datetime(1982,1,1)],
            "decision":"Use1983–2010(28seasons) and1991–2020(30seasons) for every season; preserve older1982–2010 OND cases",
            "first_initialization_in_new_matrix":min(season_window(name,1983).initialization for name in SEASONS).isoformat(),
            "year_convention":"Season labelled by ending year; NDJ/DJF start in preceding year","archive_transition":"Operational forecasts appended fromApril2011; no homogeneity correction"}
    (ROOT/"calendar_decision.json").write_text(json.dumps(record,indent=2)+"\n")
    return record


def model_data(season):
    raw=ROOT/"raw"/f"{season}_monthly_means.nc"; count_raw=ROOT/"raw"/f"{season}_member_counts.nc"
    windows=[season_window(season,year) for year in ALL_YEARS]
    def load(path):
        with xr.open_dataset(path,decode_times=False) as source:
            da=source.prec.transpose("S","L","Y","X").sel(X=np.arange(85,156),Y=np.arange(20,-21,-1)).load()
        assert da.shape==(42,3,41,71)
        expected=[(window.initialization.year-1960)*12+window.initialization.month-1 for window in windows]
        np.testing.assert_allclose(da.S,expected,atol=1e-8,rtol=0)
        np.testing.assert_allclose(da.L,[1.5,2.5,3.5],atol=1e-8,rtol=0)
        assert bool(np.isfinite(da).all())
        return da
    rates=load(raw); counts=load(count_raw)
    assert "".join(rates.attrs["units"].split())=="mm/day" and float(rates.min())>=0
    np.testing.assert_array_equal(counts,np.round(counts)); assert float(counts.min())>=1
    days=np.array([window.days for window in windows])
    seasonal=(rates.values.astype("float64")*days[:,:,None,None]).sum(axis=1)
    starts=pd.to_datetime([window.start for window in windows]); ends=pd.to_datetime([window.end for window in windows])
    T=pd.Index(starts+(ends-starts)/2,name="T")
    da=xr.DataArray(seasonal,dims=("T","Y","X"),coords={"T":T,"Y":rates.Y.values,"X":rates.X.values,
                   "Ti":("T",starts),"Tf":("T",ends),"S":("T",pd.to_datetime([window.initialization for window in windows])),"season_year":("T",ALL_YEARS)},name="precipitation")
    transport_difference=0.; precision={}
    if season=="OND":
        # Keep the exact existing text-rounded predictor values for the control:
        # only the older training year's removal should change its calibration.
        old=read(OLD/"inputs/cfsv2_hindcasts_ond.nc").precipitation
        recent=read(RECENT/"inputs/cfsv2_hindcasts_ond.nc").precipitation
        forecasts=read(HOLDOUTS/"outputs/cfsv2_forecast_predictors.nc").precipitation
        cached=xr.concat([old.sel(T=old["T"].dt.year.isin(range(1983,1991))),recent,forecasts],dim="T")
        np.testing.assert_array_equal(da["T"],cached["T"])
        # The earlier CPT text transport prints approximately6 significant
        # digits after single-precision arithmetic. Validate EVERY overlapping
        # monthly value against that precision before reusing cached amounts.
        parts=[]; source_hashes={}
        for label,root,name,first,last in (("older",OLD,"cfsv2_hindcasts_monthly.tsv",1983,1990),("recent",RECENT,"cfsv2_hindcasts_monthly.tsv",1991,2020),("forecasts",HOLDOUTS,"cfsv2_forecasts_monthly.tsv",2021,2024)):
            original=root/"inputs"/name; source_hashes[str(original)]=sha(original)
            parsing=ROOT/"raw"/f"OND_previous_{label}.parsing.tsv"
            parsing.write_text(re.sub(r",\s*cpt:S=[^,\r\n]+","",original.read_text()))
            text_ds=open_cptdataset(str(parsing)); text_rate=text_ds[list(text_ds.data_vars)[0]].sortby("T")
            parts.append(text_rate.sel(T=(text_rate["T"].dt.year>=first)&(text_rate["T"].dt.year<=last)))
        previous_rates=xr.concat(parts,dim="T").transpose("T","Y","X").values.reshape(rates.shape)
        absolute=abs(rates.values)
        quantum=np.where(absolute>0,10.**(np.floor(np.log10(np.maximum(absolute,1e-40)))-5),0)
        monthly_bound=.5*quantum+2*np.spacing(absolute.astype("float32")).astype("float64")
        monthly_difference=abs(rates.values-previous_rates)
        assert np.all(monthly_difference<=monthly_bound+1e-12)
        reconstructed=(previous_rates*days[:,:,None,None]).sum(axis=1)
        np.testing.assert_allclose(reconstructed,cached.values,atol=1e-9,rtol=0)
        transport_difference=float(abs(da-cached).max())
        seasonal_bound=float((monthly_bound*days[:,:,None,None]).sum(axis=1).max())
        assert transport_difference<=seasonal_bound+1e-9
        precision={"ond_monthly_binary_vs_text_max_difference_mm_per_day":float(monthly_difference.max()),
                   "ond_binary_vs_cached_seasonal_rounding_bound_mm":seasonal_bound,"ond_monthly_rounding_bound_violations":0,
                   "ond_rounding_rule":"Half quantum at6significantdigits plus2single-precision ULPs; every monthly value checked; original amounts reused exactly",
                   "ond_previous_monthly_source_sha256":source_hashes}
        da.values=cached.transpose("T","Y","X").values
    da.attrs={"units":"mm","missing":-999.,"standard_name":"precipitation_amount","cell_methods":"time: sum","long_name":f"CFSv2 ensemble-mean {season} rainfall"}
    # Raw model/member arrays retain initialization and lead axes; year and days
    # are supplied explicitly, avoiding ambiguous CF month decoding.
    rate_da=xr.DataArray(rates.values,dims=("season_year","lead","predictor_Y","predictor_X"),coords={"season_year":ALL_YEARS,"lead":[1.5,2.5,3.5],"predictor_Y":rates.Y.values,"predictor_X":rates.X.values},attrs={"units":"mm/day"})
    count_da=rate_da.copy(data=counts.values); count_da.attrs={"units":"1","long_name":"Valid ensemble-member count before averaging"}
    audit=xr.Dataset({"precipitation_rate":rate_da,"valid_member_count":count_da,"target_month_days":(("season_year","lead"),days)})
    return da,audit,{"model_finite_monthly_values":int(rates.count()),"valid_member_count_range":[int(counts.min()),int(counts.max())],"ond_binary_vs_cached_predictor_max_difference_mm":transport_difference,**precision}


def prepare_season(season):
    folder=ROOT/season; folder.mkdir(parents=True,exist_ok=True)
    if (folder/"preparation.json").exists(): return json.loads((folder/"preparation.json").read_text())
    model,audit,record=model_data(season)
    print("MODEL_AUDIT_PASS",season,record,flush=True)
    geometry=shapely.geometry.shape(json.loads((OLD/"inputs/indonesia_boundary.geojson").read_text())); shapely.prepare(geometry)
    windows=[season_window(season,year) for year in ALL_YEARS]
    rains=[]; valid=[]
    with xr.open_dataset(SOURCE) as source:
        times=pd.DatetimeIndex(source.time.values)
        native=source.precip.sel(lon=slice(94,142),lat=slice(-12,7))
        lon,lat=np.meshgrid(native.lon,native.lat)
        country=xr.DataArray(shapely.contains_xy(geometry,lon,lat),dims=("lat","lon"),coords={"lat":native.lat,"lon":native.lon})
        for window in windows:
            candidates=np.flatnonzero((times.year==window.end.year)&(times.month==window.end.month)&(times.day==21)); assert candidates.size==1
            index=int(candidates[0]); bounds=source.time_bnds.isel(time=index).values
            assert pd.Timestamp(bounds[0])==pd.Timestamp(window.start)
            assert pd.Timestamp(bounds[1])==pd.Timestamp(window.end)+pd.Timedelta(days=1)
            values=native.isel(time=index).load(); assert not bool((values<0).any())
            block=aggregate_country_rainfall(values,country,5,minimum_coverage=.99)
            def grid(da):
                da=da.drop_vars("time",errors="ignore").rename({"lat":"Y","lon":"X"})
                return da.assign_coords(Y=-12+.125+np.arange(76)*.25,X=94+.125+np.arange(192)*.25).sortby("Y",ascending=False)
            rains.append(grid(block.precipitation)); valid.append(grid(block.valid_land_weight))
    rain=xr.concat(rains,dim=model["T"]).assign_coords(Ti=model.Ti,Tf=model.Tf,season_year=model.season_year).transpose("T","Y","X")
    rain.name="precipitation"; rain.attrs={"units":"mm","missing":-999.,"standard_name":"precipitation_amount","cell_methods":"time: sum area: mean","long_name":f"CHIRPS3 country-land {season} rainfall"}
    country_weights=grid(block.country_land_weight); fraction=grid(block.indonesia_fraction)
    masks=[]; mask_records={}
    for period,years in PERIODS.items():
        training=rain.sel(T=rain.season_year.isin(years))
        mask=training_complete_mask(training,years) if season!="NDJ" else training.notnull().all("T")
        # training_complete_mask expects T.year, which is the ending year for all
        # midpoint dates except NDJ(midpointDecember). Verify labelled years too.
        np.testing.assert_array_equal(training.season_year,years)
        constant=(training.std("T")==0)&mask
        mask=mask&(~constant)
        masks.append(mask.astype("int8")); mask_records[period]={"included_cells":int(mask.sum()),"constant_cells_excluded":int(constant.sum())}
    analysis=xr.concat(masks,dim=pd.Index(list(PERIODS),name="training_period"))
    evaluation=analysis.astype(bool).all("training_period")&rain.sel(T=rain.season_year.isin(EVAL_YEARS)).notnull().all("T")
    obs=xr.Dataset({"precipitation":rain,"valid_land_weight":xr.concat(valid,dim=model["T"]).transpose("T","Y","X")})
    footprint=xr.Dataset({"analysis_mask":analysis,"season_evaluation_mask":evaluation.astype("int8"),"country_land_weight":country_weights,"indonesia_fraction":fraction})
    metadata={"case_id":ROOT.name,"season":season,"year_convention":"Ending year, includingNDJ/DJF","source_file":str(SOURCE),"training_mask_rule":"At least99percent native countryland coverage in every training season; constant training cells excluded; no verification values fit masks"}
    for ds,name in ((model.to_dataset(),"predictors.nc"),(audit,"monthly_audit.nc"),(obs,"observations.nc"),(footprint,"footprint.nc")):
        save_netcdf(ds,folder/name,metadata=metadata,overwrite=True)
    record.update(season=season,training_masks=mask_records,season_evaluation_cells=int(evaluation.sum()),observation_windows_verified=len(windows),
                  first_initialization=windows[0].initialization.isoformat(),last_initialization=windows[-1].initialization.isoformat(),
                  urls=dict(zip(("monthly_means","valid_member_counts"),urls(season))),raw_sha256={name:sha(ROOT/"raw"/f"{season}_{name}.nc") for name in ("monthly_means","member_counts")},
                  input_sha256={name:sha(folder/name) for name in ("predictors.nc","monthly_audit.nc","observations.nc","footprint.nc")})
    (folder/"preparation.json").write_text(json.dumps(record,indent=2)+"\n")
    print("SEASON_PREPARED",season,mask_records,"evaluation_cells",int(evaluation.sum()),flush=True)
    return record


def main(selected=SEASONS,workers=3):
    (ROOT/"raw").mkdir(parents=True,exist_ok=True)
    key=read_dlauth(); assert key
    decision=source_boundary(key)
    jobs={}
    for season in selected:
        for label,url in zip(("monthly_means","member_counts"),urls(season)):
            jobs[(season,label)]=(url,ROOT/"raw"/f"{season}_{label}.nc")
    # Only HTTP downloads run concurrently. netCDF4/HDF5 and CHIRPS reads stay
    # in the main thread because those libraries are not reliably thread-safe.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending={pool.submit(download,url,path,key):(season,label) for (season,label),(url,path) in jobs.items()}
        ready=set()
        for future in as_completed(pending):
            season,label=pending[future]; future.result()
            if season not in ready and all((ROOT/"raw"/f"{season}_{name}.nc").exists() for name in ("monthly_means","member_counts")):
                prepare_season(season); ready.add(season)
    for season in selected: prepare_season(season)
    if all((ROOT/season/"preparation.json").exists() for season in SEASONS):
        fields=[read(ROOT/season/"footprint.nc") for season in SEASONS]
        common=xr.concat([ds.season_evaluation_mask.astype(bool) for ds in fields],dim="season").all("season")
        weights=fields[0].country_land_weight
        footprint=xr.Dataset({"evaluation_mask":common.astype("int8"),"country_land_weight":weights,"evaluation_weight":weights.where(common,0),
                              "season_evaluation_mask":xr.concat([ds.season_evaluation_mask for ds in fields],dim=pd.Index(SEASONS,name="season"))})
        save_netcdf(footprint,ROOT/"evaluation_footprint.nc",overwrite=True,metadata={"scope":"Scoring only, never used to refit any model","rule":"All12seasons/bothperiods/all4verificationyears share same cells/weights"})
        report={"status":"PASS","case_id":ROOT.name,"calendar_decision":decision,"seasons":{season:json.loads((ROOT/season/"preparation.json").read_text()) for season in SEASONS},
                "common_evaluation_cells":int(common.sum()),"approximate_country_land_weight_retained":float(weights.where(common,0).sum()/weights.sum()),"training_periods":PERIODS,"evaluation_years":EVAL_YEARS}
        (ROOT/"availability.json").write_text(json.dumps(report,indent=2)+"\n")
        print("ALL_SEASONS_PREPARED","shared_cells",int(common.sum()),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--seasons",nargs="+",choices=SEASONS,default=list(SEASONS)); parser.add_argument("--workers",type=int,default=3)
    args=parser.parse_args(); main(args.seasons,args.workers)
