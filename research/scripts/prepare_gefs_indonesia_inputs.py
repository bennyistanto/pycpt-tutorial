"""Prepare bounded, input-only GEFS/CHIRPS examples; no CPT or fitted models.

Default is a dry plan. --prepare executes the two declared input checks, not a
full training archive. Global daily TIFFs are streamed, reduced to country pixels
and discarded from memory; small native-country caches support offline checks.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

class NoFitImports:
    def find_spec(self,fullname,*args):
        if fullname.split('.')[0] in {'pycpt','cptcore','cptdl'}:
            raise RuntimeError('Input-only adapter must not import fitting/download drivers')
sys.meta_path.insert(0,NoFitImports())
def no_process(event,args):
    if event=='subprocess.Popen':raise RuntimeError('No subprocess/CPT launches allowed')
sys.addaudithook(no_process)

import numpy as np
import requests
import xarray as xr
from pycpt_tutorial.export import save_netcdf
from pycpt_tutorial.subseasonal_inputs import (
    VERSION,WEEKS,country_grid,gefs_weekly,chirps_weekly,read_chirps_country,week_dates)

AUDIT=ROOT/'research/audits/gefs-input-adapter'
WORK=ROOT/'temp/gefs-input-adapter'
CHECKS=[('hindcast','2018-08-29'),('forecast','2023-08-24')]
BASE='https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX/.EMC/.GEFSv12_CPC'
CHIRPS='https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final'
BOUNDARY=Path('/home/bennyistanto/CPT/cases/indonesia-ond-2023/inputs/indonesia_boundary.geojson')
BOUNDARY_SHA='1b44b1d7e0ab4e7e3eff0efd9e0bff74c45ad7a390114e80b64b5369b51f4e78'
REFRESH_DERIVED=False

sha=lambda body:hashlib.sha256(body).hexdigest()

def get_bytes(url,cap):
    for attempt in range(3):
        try:
            with requests.get(url,stream=True,timeout=(12,60),allow_redirects=False) as r:
                if r.status_code!=200:raise ValueError(f'HTTP {r.status_code} for public source')
                if int(r.headers.get('Content-Length',0))>cap:raise ValueError('Source exceeds per-file transfer cap')
                out=bytearray()
                for chunk in r.iter_content(262144):
                    out.extend(chunk)
                    if len(out)>cap:raise ValueError('Source exceeds per-file transfer cap')
                return bytes(out)
        except (requests.RequestException,ValueError):
            if attempt==2:raise
            time.sleep(1+attempt)

def write_verified(ds,path):
    if path.exists() and REFRESH_DERIVED:
        if not path.resolve().is_relative_to((AUDIT/'outputs').resolve()):
            raise ValueError('Refresh is restricted to this adapter audit outputs folder')
        save_netcdf(ds,path,overwrite=True)
    elif path.exists():
        with xr.open_dataset(path) as old:xr.testing.assert_identical(ds,old.load())
    else:save_netcdf(ds,path)

def model_input(kind,date):
    rawpath=WORK/'model'/f'{kind}-{date}.nc';rawpath.parent.mkdir(parents=True,exist_ok=True)
    branch='/.hindcast/.weekly/.pr' if kind=='hindcast' else '/.forecast/.pr'
    import datetime as dt
    stamp=dt.date.fromisoformat(date)
    label=f'0000 {stamp.day} {stamp:%b} {stamp.year}'.replace(' ','%20')
    url=BASE+branch+f'/S/({label})/VALUES/X/94/143/RANGE/Y/-12/7/RANGE/L/7.5/27.5/RANGE/data.nc'
    cached=rawpath.exists()
    if not cached:
        body=get_bytes(url,8_000_000)
        if not (body.startswith(b'CDF') or body.startswith(b'\x89HDF')):raise ValueError('GEFS response is not NetCDF')
        rawpath.write_bytes(body)
    with xr.open_dataset(rawpath,decode_timedelta=False) as ds:
        prepared=gefs_weekly(ds.load(),kind,date)
    output=AUDIT/'outputs'/f'gefs-{kind}-{date}-weeks234.nc'
    write_verified(prepared,output)
    return prepared,{'kind':kind,'initialization':date,'url':url,'source_sha256':sha(rawpath.read_bytes()),
        'cache':str(rawpath.relative_to(ROOT)),'output':str(output.relative_to(ROOT)),
        'output_sha256':sha(output.read_bytes()),'source_units':prepared.rainfall_amount.attrs['source_units'],
        'member_count':prepared.sizes['member'],'days_per_week':7,'source_transfer_cached':cached,
        'all_member_day_grid_values_finite':True,'all_rainfall_nonnegative':True}

def daily_cache_path(grid,variant,date):
    return WORK/'daily-country'/grid.attrs['grid_id'][:12]/variant/(date+'.nc')

def fetch_daily(variant,date):
    url=f'{CHIRPS}/{variant}/{date[:4]}/chirps-v3.0.{variant}.{date.replace("-",".")}.tif'
    prior=ROOT/'temp/subseasonal-readiness'/f'CHIRPS3-{variant}-{date}.tif'
    if prior.exists():return prior.read_bytes(),url,True
    return get_bytes(url,36_000_000),url,False

def cache_daily(body,url,variant,date,grid,cached_source):
    if not body.startswith((b'II*\x00',b'MM\x00*')):raise ValueError('CHIRPS response is not a GeoTIFF')
    values=read_chirps_country(body,grid)
    ds=xr.Dataset({'rainfall_amount':('point',values)},coords={'point':grid.point,'time':np.datetime64(date,'ns')})
    ds.rainfall_amount.attrs={'units':'mm','cell_methods':'time: sum','long_name':'Native country-pixel daily rainfall amount'}
    ds.attrs={'adapter_version':VERSION,'grid_id':grid.attrs['grid_id'],'variant':variant,'date':date,
              'source_url':url,'source_sha256':sha(body),'source_bytes':len(body),'time_zone':'UTC',
              'nodata_rule':'-9999 decoded to NaN; zeros retained; all other negatives rejected',
              'source_transfer_cached':int(cached_source)}
    path=daily_cache_path(grid,variant,date);path.parent.mkdir(parents=True,exist_ok=True)
    write_verified(ds,path)
    return {'variant':variant,'date':date,'source_url':url,'source_sha256':sha(body),'source_bytes':len(body),
            'cache':str(path.relative_to(ROOT)),'cache_sha256':sha(path.read_bytes()),
            'missing_country_pixels':int(np.isnan(values).sum()),'zero_country_pixels':int((values==0).sum())}

def existing_daily(path,grid,variant,date):
    with xr.open_dataset(path) as ds:
        if ds.attrs['grid_id']!=grid.attrs['grid_id'] or ds.attrs['variant']!=variant or ds.attrs['date']!=date:
            raise ValueError('Stale observation cache identity')
        a=ds.rainfall_amount.values
        return {'variant':variant,'date':date,'source_url':ds.attrs['source_url'],'source_sha256':ds.attrs['source_sha256'],
            'source_bytes':int(ds.attrs['source_bytes']),'cache':str(path.relative_to(ROOT)),
            'cache_sha256':sha(path.read_bytes()),'missing_country_pixels':int(np.isnan(a).sum()),
            'zero_country_pixels':int((a==0).sum())}

def required_days(checks):
    return sorted({str(day) for _,date in checks for week in WEEKS for day in week_dates(date,week)})

def prepare_observations(checks,grid,variants,budget):
    jobs=[(v,d) for v in variants for d in required_days(checks)]
    records=[];missing=[]
    for v,d in jobs:
        path=daily_cache_path(grid,v,d)
        if path.exists():records.append(existing_daily(path,grid,v,d))
        else:missing.append((v,d))
    transferred=0
    # At most two compressed responses in flight; NetCDF/HDF5 access stays serial.
    with ThreadPoolExecutor(max_workers=2) as pool:
        for offset in range(0,len(missing),2):
            batch=missing[offset:offset+2]
            futures=[pool.submit(fetch_daily,v,d) for v,d in batch]
            for (v,d),future in zip(batch,futures):
                body,url,cached_source=future.result()
                transferred+=0 if cached_source else len(body)
                if transferred>budget:raise ValueError('Run transfer budget exceeded; resume from cache with a reviewed plan')
                records.append(cache_daily(body,url,v,d,grid,cached_source))
                print(f'CHIRPS {v} {d} · {len(records)}/{len(jobs)} cached country days',flush=True)
    outputs=[]
    for kind,date in checks:
        for variant in variants:
            required=sorted({str(day) for week in WEEKS for day in week_dates(date,week)})
            parts=[]
            for day in required:
                with xr.open_dataset(daily_cache_path(grid,variant,day)) as ds:parts.append(ds.load())
            daily=xr.concat(parts,dim='time',coords='minimal',compat='override')
            daily.attrs={'grid_id':grid.attrs['grid_id']}
            weekly=chirps_weekly(daily,grid,date,variant)
            path=AUDIT/'outputs'/f'chirps3-{variant}-{kind}-{date}-weeks234.nc'
            write_verified(weekly,path)
            mass=grid.country_land_weight.values
            coverage=weekly.country_coverage_fraction.values[0]
            valid=np.isfinite(weekly.rainfall_amount.values[0])
            outputs.append({'kind':kind,'initialization':date,'variant':variant,'output':str(path.relative_to(ROOT)),
                'output_sha256':sha(path.read_bytes()),'source_dates':required,
                'country_cells':int((mass>0).sum()),'valid_cells_per_week':[int(v.sum()) for v in valid],
                'native_country_area_coverage_per_week':[float(np.nansum(c*mass)/mass.sum()) for c in coverage],
                'eligible_cell_country_area_fraction_per_week':[float(mass[v].sum()/mass.sum()) for v in valid]})
    return records,outputs,transferred

def main():
    global REFRESH_DERIVED
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--variant',choices=['both','rnl','sat'],default='both')
    parser.add_argument('--transfer-budget-mb',type=int,default=2200)
    parser.add_argument('--hindcast-date',action='append',default=[],help='Explicit YYYY-MM-DD initialization; repeat for additional starts')
    parser.add_argument('--forecast-date',action='append',default=[],help='Explicit YYYY-MM-DD initialization; repeat for additional starts')
    parser.add_argument('--refresh-derived',action='store_true',help='Replace only this adapter audit derived outputs; retain source caches')
    args=parser.parse_args()
    REFRESH_DERIVED=args.refresh_derived
    checks=[('hindcast',d) for d in args.hindcast_date]+[('forecast',d) for d in args.forecast_date]
    checks=checks or CHECKS
    if len(checks)!=len(set(checks)):raise ValueError('Duplicate initialization/role')
    variants=['rnl','sat'] if args.variant=='both' else [args.variant]
    plan={'adapter_version':VERSION,'checks':checks,'weeks':list(WEEKS),'daily_references':variants,
          'unique_calendar_days':len(required_days(checks)),
          'daily_country_cache_files':len(required_days(checks))*len(variants),
          'full_training_archive_prepared':False,'fits_run':0,
          'scope':'Explicit full-Indonesia input checks; training/validation periods proposed separately',
          'global_tiff_transfer_upper_bound_mb':36*len(required_days(checks))*len(variants),
          'run_transfer_budget_mb':args.transfer_budget_mb}
    if not args.prepare:
        print(json.dumps(plan,indent=2));return
    AUDIT.mkdir(parents=True,exist_ok=True);(AUDIT/'outputs').mkdir(exist_ok=True);(AUDIT/'inputs').mkdir(exist_ok=True)
    WORK.mkdir(parents=True,exist_ok=True)
    boundary=BOUNDARY.read_bytes()
    if sha(boundary)!=BOUNDARY_SHA:raise ValueError('Saved authoritative country boundary changed')
    target=AUDIT/'inputs/indonesia_boundary.geojson'
    if target.exists() and target.read_bytes()!=boundary:raise ValueError('Prepared boundary differs')
    target.write_bytes(boundary)
    grid=country_grid(target);grid_path=AUDIT/'outputs/indonesia-country-grid.nc';write_verified(grid,grid_path)
    models=[]
    for kind,date in checks:
        _,record=model_input(kind,date);models.append(record)
        print(f'GEFS {kind} {date} · {record["member_count"]} complete members; weeks 2/3/4',flush=True)
    daily,observations,transferred=prepare_observations(checks,grid,variants,args.transfer_budget_mb*1_000_000)
    result=dict(plan,date='2026-11-02',models=models,daily_sources=daily,observations=observations,
        country_grid={'output':str(grid_path.relative_to(ROOT)),'sha256':sha(grid_path.read_bytes()),
                      'geometry_sha256':BOUNDARY_SHA,'native_pixels':grid.sizes['point'],
                      'country_cells':int((grid.country_land_weight>0).sum()),'grid_id':grid.attrs['grid_id']},
        http_bytes_downloaded_this_run=transferred,fitting_imports_or_processes_allowed=False,
        source_code_sha256={name:sha((ROOT/name).read_bytes()) for name in ['pycpt_tutorial/subseasonal_inputs.py','research/scripts/prepare_gefs_indonesia_inputs.py']})
    (AUDIT/'preparation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'result':'INPUTS_PREPARED','model_files':len(models),'observation_files':len(observations),
                      'native_pixels':grid.sizes['point'],'http_bytes_downloaded_this_run':transferred,
                      'minimum_country_area_coverage':min(v for r in observations for v in r['native_country_area_coverage_per_week']),
                      'fits_run':0},indent=2))

if __name__=='__main__':main()
