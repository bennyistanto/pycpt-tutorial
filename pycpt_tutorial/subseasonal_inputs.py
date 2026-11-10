"""Input-only GEFS/CHIRPS preparation. No PyCPT/CPT imports or model fitting.

Weeks use elapsed UTC intervals [7,14), [14,21), [21,28). Model L values are
daily midpoints; CHIRPS dates label the beginning of a UTC disaggregation day.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
import shapely
from shapely.geometry import shape
import xarray as xr

WEEKS=(2,3,4)
SECONDS_PER_DAY=86400.0
OBS_SHAPE=(76,192)
VERSION='gefs-chirps-inputs-v1'

def utc_initialization(value):
    """Require unambiguous midnight UTC; never silently normalize a time of day."""
    stamp=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if stamp.tzinfo is not None:
        if stamp.utcoffset()!=dt.timedelta(0):
            raise ValueError('Initialization must explicitly use UTC')
        stamp=stamp.replace(tzinfo=None)
    if stamp.time()!=dt.time():
        raise ValueError('Only 00 UTC initialization is supported')
    return np.datetime64(stamp,'ns')

def week_bounds(initialization,week):
    if type(week) is not int or week not in WEEKS:
        raise ValueError('Supported lead weeks are 2, 3 and 4')
    start=utc_initialization(initialization)+np.timedelta64(7*(week-1),'D')
    return start,start+np.timedelta64(7,'D')

def week_dates(initialization,week):
    start,end=week_bounds(initialization,week)
    return np.arange(start.astype('datetime64[D]'),end.astype('datetime64[D]'))

def expected_leads(week):
    if type(week) is not int or week not in WEEKS:
        raise ValueError('Supported lead weeks are 2, 3 and 4')
    return np.arange(7*(week-1)+.5,7*week,1.0)

def gefs_weekly(ds,kind,initialization):
    """Convert seven daily amounts/rates per member, requiring every value.

    Contracts checked by the adapter audit: hindcast kg m-2 daily amount -> mm;
    forecast kg m-2 s-1 daily mean rate -> mm using exactly 86400 seconds.
    Neither branch is treated as a cumulative-since-initialization series.
    """
    if kind not in ['hindcast','forecast']:
        raise ValueError('kind must be hindcast or forecast')
    if 'pr' not in ds or set(ds.pr.dims)!={'S','M','L','Y','X'}:
        raise ValueError('Expected raw GEFS pr(S,M,L,Y,X)')
    start=utc_initialization(initialization)
    if ds.sizes['S']!=1 or np.datetime64(ds.S.values[0],'ns')!=start:
        raise ValueError('Source initialization does not match requested UTC date')
    if kind=='hindcast' and dt.date.fromisoformat(str(start)[:10]).weekday()!=2:
        raise ValueError('GEFSv12 weekly hindcasts must initialize on Wednesday')
    members=np.arange(11 if kind=='hindcast' else 31)
    if not np.array_equal(ds.M.values,members):
        raise ValueError('Missing, reordered or unexpected ensemble member IDs')
    units=ds.pr.attrs.get('units')
    expected='kg m-2' if kind=='hindcast' else 'kg m-2 s-1'
    if units!=expected:
        raise ValueError(f'Unknown GEFS unit contract: expected {expected!r}, got {units!r}')
    if ds.L.attrs.get('units')!='days' or np.issubdtype(ds.L.dtype,np.timedelta64):
        raise ValueError('Open raw GEFS with decode_timedelta=False; L must be numeric days')
    if len(np.unique(ds.L.values))!=ds.sizes['L']:
        raise ValueError('Duplicate daily lead midpoint')
    converted=[]
    for week in WEEKS:
        leads=expected_leads(week)
        if not all(v in ds.L.values for v in leads):
            raise ValueError(f'Week {week} does not contain seven exact daily leads')
        a=ds.pr.sel(L=leads).isel(S=0,drop=True).transpose('M','L','Y','X').astype('float64')
        if not bool(np.isfinite(a).all()):
            raise ValueError(f'Week {week} has missing member/day/grid values')
        if bool((a<0).any()):
            raise ValueError('Negative GEFS rainfall must be investigated, not clipped')
        if kind=='forecast':a=a*SECONDS_PER_DAY
        converted.append(a.sum('L',skipna=False))
    rain=xr.concat(converted,dim=xr.IndexVariable('lead_week',list(WEEKS)))
    rain=rain.rename({'M':'member','Y':'latitude','X':'longitude'}).sortby('latitude',ascending=False).sortby('longitude')
    rain=rain.expand_dims(initialization=[start]).transpose('initialization','lead_week','member','latitude','longitude')
    rain.name='rainfall_amount'
    rain.attrs={'units':'mm','standard_name':'precipitation_amount','cell_methods':'time: sum',
                'source_units':units,'daily_conversion_factor':1.0 if kind=='hindcast' else SECONDS_PER_DAY}
    output=rain.to_dataset()
    output['ensemble_mean']=rain.mean('member',skipna=False)
    output.ensemble_mean.attrs={'units':'mm','cell_methods':'time: sum realization: mean'}
    output['daily_count']=xr.full_like(rain,7,dtype='int8')
    output['member_count']=xr.full_like(output.ensemble_mean,len(members),dtype='int16')
    output.daily_count.attrs={'units':'1','long_name':'Complete daily intervals per member and target week'}
    output.member_count.attrs={'units':'1','long_name':'Complete source ensemble members per target week'}
    attach_bounds(output,start)
    output.attrs={'adapter_version':VERSION,'kind':kind,'calendar':'proleptic_gregorian','time_zone':'UTC',
                  'interval_convention':'Half-open UTC [7,14), [14,21), [21,28) days after initialization',
                  'climatology_subtracted':'none','fitting':'none','member_rule':'All source members, equal weight; no lagged ensemble'}
    return output

def attach_bounds(ds,initialization):
    starts,ends=zip(*(week_bounds(str(initialization),w) for w in WEEKS))
    ds['target_start']=(('initialization','lead_week'),np.asarray([starts],dtype='datetime64[ns]'))
    ds['target_end']=(('initialization','lead_week'),np.asarray([ends],dtype='datetime64[ns]'))
    ds.target_start.attrs={'long_name':'Inclusive UTC start of seven-day target'}
    ds.target_end.attrs={'long_name':'Exclusive UTC end of seven-day target'}
    ds.lead_week.attrs={'long_name':'Model week; days numbered from the initialization day'}

def country_grid(geojson):
    """Static country geometry only, independent of training/verification values."""
    payload=Path(geojson).read_bytes();geometry=shape(json.loads(payload))
    if not geometry.is_valid:raise ValueError('Country geometry is invalid')
    longitude=94.025+.05*np.arange(960)
    latitude=6.975-.05*np.arange(380)
    xx,yy=np.meshgrid(longitude,latitude)
    inside=shapely.contains_xy(geometry,xx,yy)
    row,col=np.nonzero(inside)
    weights=np.cos(np.deg2rad(yy[inside]))
    coarse=(row//5)*192+col//5
    mass=np.bincount(coarse,weights=weights,minlength=76*192).reshape(OBS_SHAPE)
    counts=np.bincount(coarse,minlength=76*192).reshape(OBS_SHAPE)
    ds=xr.Dataset({
        'native_row':('point',row.astype('int16')),'native_col':('point',col.astype('int16')),
        'native_latitude':('point',yy[inside]),'native_longitude':('point',xx[inside]),
        'native_weight':('point',weights),'coarse_index':('point',coarse.astype('int32')),
        'country_land_weight':(('latitude','longitude'),mass),
        'country_fraction':(('latitude','longitude'),counts/25.0)},
        coords={'point':np.arange(len(row)),'latitude':6.875-.25*np.arange(76),'longitude':94.125+.25*np.arange(192)})
    ds.attrs={'geometry_sha256':hashlib.sha256(payload).hexdigest(),'adapter_version':VERSION,
        'mask_rule':'Country polygon containment at nominal 0.05-degree pixel centres; no training-derived mask',
        'area_weights':'cosine(latitude); block averages are rainfall depths, not spatial rainfall sums'}
    ds.attrs['grid_id']=hashlib.sha256((ds.attrs['geometry_sha256']+VERSION).encode()).hexdigest()
    return ds

def read_chirps_country(body,grid):
    """Read real daily GeoTIFF data; preserve dry zeros, flag -9999 explicitly."""
    with Image.open(io.BytesIO(body)) as image:
        if image.size!=(7200,2400):raise ValueError('Unexpected CHIRPS3 dimensions')
        sx,sy,_=image.tag_v2[33550];tie=image.tag_v2[33922]
        if not np.allclose([sx,sy],[.05,.05],atol=1e-8,rtol=0):raise ValueError('Unexpected CHIRPS3 pixel spacing')
        if not np.allclose(tie[3:5],[-180,60],atol=1e-8,rtol=0):raise ValueError('Unexpected CHIRPS3 georeferencing')
        # 94–142E, -12–7N; nominal grid removes storage-rounding noise only.
        window=np.asarray(image.crop((5480,1060,6440,1440)),dtype='float32')
        values=window[grid.native_row.values,grid.native_col.values].copy()
    if bool((~np.isfinite(values)).any()):raise ValueError('Nonfinite CHIRPS raster value')
    if bool(((values<0)&(values!=-9999)).any()):raise ValueError('Unknown negative CHIRPS rainfall/sentinel')
    values[values==-9999]=np.nan
    return values

def chirps_weekly(daily,grid,initialization,variant,minimum_coverage=.99):
    """Sum seven complete days at native pixels, then country-area block mean."""
    if variant not in ['rnl','sat']:raise ValueError('Unknown CHIRPS3 daily variant')
    if not 0<minimum_coverage<=1:raise ValueError('Invalid coverage threshold')
    if daily.attrs.get('grid_id')!=grid.attrs['grid_id']:raise ValueError('Cached country grid differs')
    if daily.rainfall_amount.attrs.get('units')!='mm':raise ValueError('Daily CHIRPS units must be mm')
    if not np.array_equal(daily.point,grid.point):raise ValueError('Native pixel index differs')
    dates=daily.time.values.astype('datetime64[D]')
    if len(dates)!=len(set(dates.tolist())):raise ValueError('Duplicate daily observation date')
    weight=grid.native_weight.values;index=grid.coarse_index.values;mass=grid.country_land_weight.values
    amounts=[];coverages=[]
    for week in WEEKS:
        expected=week_dates(initialization,week)
        if not set(expected.tolist()).issubset(set(dates.tolist())):raise ValueError('Missing daily observation file/date')
        a=daily.rainfall_amount.sel(time=expected.astype('datetime64[ns]')).values.astype('float64')
        if bool((a[np.isfinite(a)]<0).any()):raise ValueError('Negative observed rainfall')
        valid=np.isfinite(a).all(axis=0)
        totals=np.sum(a,axis=0)
        valid_mass=np.bincount(index[valid],weights=weight[valid],minlength=76*192).reshape(OBS_SHAPE)
        numerator=np.bincount(index[valid],weights=weight[valid]*totals[valid],minlength=76*192).reshape(OBS_SHAPE)
        coverage=np.divide(valid_mass,mass,out=np.full_like(mass,np.nan),where=mass>0)
        amount=np.divide(numerator,valid_mass,out=np.full_like(mass,np.nan),where=valid_mass>0)
        amount[(mass<=0)|(coverage<minimum_coverage)]=np.nan
        amounts.append(amount);coverages.append(coverage)
    output=xr.Dataset({
        'rainfall_amount':(('initialization','lead_week','latitude','longitude'),np.asarray([amounts])),
        'country_coverage_fraction':(('initialization','lead_week','latitude','longitude'),np.asarray([coverages]))},
        coords={'initialization':[utc_initialization(initialization)],'lead_week':list(WEEKS),
                'latitude':grid.latitude,'longitude':grid.longitude})
    output.rainfall_amount.attrs={'units':'mm','standard_name':'precipitation_amount','cell_methods':'time: sum area: mean'}
    output.country_coverage_fraction.attrs={'units':'1','long_name':'Country area fraction with all seven daily values'}
    attach_bounds(output,initialization)
    output.attrs={'adapter_version':VERSION,'grid_id':grid.attrs['grid_id'],'observation_product':'CHIRPS3 Final '+variant,
        'minimum_country_cell_coverage':minimum_coverage,'time_zone':'UTC','fitting':'none',
        'missing_rule':'Every native pixel requires seven days; country block coverage then tested; no zero filling',
        'training_mask':'none; a fixed common analysis mask must be selected from training data later'}
    return output
