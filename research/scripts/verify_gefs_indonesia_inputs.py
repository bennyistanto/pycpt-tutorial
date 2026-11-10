"""Independent offline arithmetic/identity checks of the bounded input examples."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_gefs_indonesia_inputs import ROOT,AUDIT,WORK  # activates no-fit/no-process guards
import numpy as np
import requests
import xarray as xr

def forbidden(*args,**kwargs):
    raise RuntimeError('Offline verifier cannot make network requests')
requests.sessions.Session.send=forbidden
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_text())

def same(a,b):
    if not np.allclose(a,b,rtol=1e-12,atol=1e-10,equal_nan=True):
        raise AssertionError('Independent arithmetic differs from saved output')

def main():
    manifest=load(AUDIT/'preparation.json')
    assert manifest['fits_run']==0 and not manifest['full_training_archive_prepared']
    for name,expected in manifest['source_code_sha256'].items():assert sha(ROOT/name)==expected
    g=manifest['country_grid'];assert sha(ROOT/g['output'])==g['sha256']
    assert sha(AUDIT/'inputs/indonesia_boundary.geojson')==g['geometry_sha256']
    with xr.open_dataset(ROOT/g['output']) as opened:grid=opened.load()
    assert grid.sizes['point']==61192 and int((grid.country_land_weight>0).sum())==3242
    # Reconstruct geometry independently at stored pixel centres.
    import shapely
    from shapely.geometry import shape
    geometry=shape(load(AUDIT/'inputs/indonesia_boundary.geojson'))
    assert np.all(shapely.contains_xy(geometry,grid.native_longitude.values,grid.native_latitude.values))
    same(grid.native_weight,np.cos(np.deg2rad(grid.native_latitude)))
    mass=grid.country_land_weight.values.ravel();index=grid.coarse_index.values;weight=grid.native_weight.values
    reconstructed=np.zeros(len(mass));np.add.at(reconstructed,index,weight);same(mass,reconstructed)
    source_records={(r['variant'],r['date']):r for r in manifest['daily_sources']}
    assert len(source_records)==len(manifest['daily_sources'])==84
    for r in source_records.values():
        p=ROOT/r['cache'];assert sha(p)==r['cache_sha256']
        with xr.open_dataset(p) as d:
            assert str(d.time.values)[:10]==r['date'] and d.attrs['variant']==r['variant']
            assert d.attrs['source_sha256']==r['source_sha256'] and d.attrs['grid_id']==g['grid_id']
            assert d.rainfall_amount.attrs['units']=='mm'
            assert np.array_equal(d.point,grid.point)
            a=d.rainfall_amount.values;assert np.all(a[np.isfinite(a)]>=0)
            assert np.isnan(a).sum()==r['missing_country_pixels'] and (a==0).sum()==r['zero_country_pixels']
    model_checks=[]
    for r in manifest['models']:
        assert sha(ROOT/r['cache'])==r['source_sha256'] and sha(ROOT/r['output'])==r['output_sha256']
        with xr.open_dataset(ROOT/r['cache'],decode_timedelta=False) as d:raw=d.load()
        with xr.open_dataset(ROOT/r['output']) as d:out=d.load()
        n=11 if r['kind']=='hindcast' else 31
        factor=1 if r['kind']=='hindcast' else 86400
        assert np.array_equal(raw.M,np.arange(n)) and np.array_equal(out.member,np.arange(n))
        assert np.array_equal(raw.L,np.arange(7.5,28,1)) and raw.L.attrs['units']=='days'
        assert raw.pr.attrs['units']==('kg m-2' if n==11 else 'kg m-2 s-1')
        assert np.isfinite(raw.pr).all() and (raw.pr>=0).all()
        assert out.daily_count.attrs['units']==out.member_count.attrs['units']=='1'
        assert (out.daily_count==7).all() and (out.member_count==n).all()
        init=np.datetime64(r['initialization'],'ns')
        assert raw.S.values[0]==out.initialization.values[0]==init
        for offset,week in enumerate([2,3,4]):
            daily=raw.pr.isel(S=0,L=slice(offset*7,(offset+1)*7)).transpose('M','L','Y','X')
            # Explicit NumPy arithmetic, without the preparation helper.
            expected=daily.values.astype('float64')*factor
            expected=expected.sum(axis=1)[:,np.argsort(raw.Y.values)[::-1],:][:,:,np.argsort(raw.X.values)]
            same(out.rainfall_amount.values[0,offset],expected)
            same(out.ensemble_mean.values[0,offset],expected.mean(axis=0))
            assert out.target_start.values[0,offset]==init+np.timedelta64(week*7-7,'D')
            assert out.target_end.values[0,offset]==init+np.timedelta64(week*7,'D')
        model_checks.append({'kind':r['kind'],'members':n,'daily_values_verified':raw.pr.size,
                             'weekly_values_verified':out.rainfall_amount.size})
    obs_checks=[];missing_points=set();weekly={}
    for r in manifest['observations']:
        assert sha(ROOT/r['output'])==r['output_sha256']
        with xr.open_dataset(ROOT/r['output']) as d:out=d.load()
        init=np.datetime64(r['initialization'],'D');required=[];area=[];cells=[]
        for offset,week in enumerate([2,3,4]):
            start=init+np.timedelta64(7*week-7,'D');end=start+np.timedelta64(7,'D')
            dates=np.arange(start,end);required.extend(str(day) for day in dates)
            arrays=[]
            for day in dates:
                record=source_records[(r['variant'],str(day))]
                with xr.open_dataset(ROOT/record['cache']) as d:arrays.append(d.rainfall_amount.values.copy())
            a=np.stack(arrays).astype('float64');valid=np.isfinite(a).all(axis=0)
            missing_points.update(np.flatnonzero(~valid).tolist())
            totals=a.sum(axis=0);numerator=np.zeros(len(mass));denominator=np.zeros(len(mass))
            np.add.at(numerator,index[valid],totals[valid]*weight[valid])
            np.add.at(denominator,index[valid],weight[valid])
            coverage=np.divide(denominator,mass,out=np.full_like(mass,np.nan),where=mass>0)
            expected=np.divide(numerator,denominator,out=np.full_like(mass,np.nan),where=denominator>0)
            expected[(mass<=0)|(coverage<.99)]=np.nan
            same(out.rainfall_amount.values[0,offset].ravel(),expected)
            same(out.country_coverage_fraction.values[0,offset].ravel(),coverage)
            assert out.target_start.values[0,offset]==start and out.target_end.values[0,offset]==end
            area.append(float(denominator.sum()/mass.sum()));cells.append(int(np.isfinite(expected).sum()))
        assert required==r['source_dates'] and len(set(required))==21
        same(area,r['native_country_area_coverage_per_week'])
        assert cells==r['valid_cells_per_week']
        obs_checks.append({'kind':r['kind'],'variant':r['variant'],'valid_cells_per_week':cells,
                           'country_area_coverage_per_week':area})
        weekly[(r['kind'],r['variant'])]=out.rainfall_amount.values
    missing=[{'native_longitude':float(grid.native_longitude[i]),'native_latitude':float(grid.native_latitude[i]),
              'cell_longitude':float(grid.longitude[int(index[i])%192]),
              'cell_latitude':float(grid.latitude[int(index[i])//192])} for i in sorted(missing_points)]
    differences=[]
    for kind in ['hindcast','forecast']:
        delta=weekly[(kind,'sat')]-weekly[(kind,'rnl')]
        differences.append({'kind':kind,'max_absolute_difference_mm':float(np.nanmax(abs(delta))),
            'mean_absolute_difference_mm':float(np.nanmean(abs(delta))),
            'scope':'Reference sensitivity only; not forecast skill or independent validation'})
    protected=load(ROOT/'research/audits/fitting-tutorial-2023/baseline.json')['protected']
    appearance=load(ROOT/'research/audits/appearance/baseline.json')
    native=load(ROOT/'docs/assets/fitting-2023/execution-manifest.json')['netcdf_outputs']
    for p,h in {**protected,**appearance}.items():assert sha(ROOT/p)==h
    for p,h in native.items():assert sha(ROOT/'docs/assets/fitting-2023'/p)==h
    first=WORK/'first-pass/outputs'
    # Scientific values remained unchanged when count metadata was corrected.
    for path in (AUDIT/'outputs').glob('*.nc'):
        if not (first/path.name).exists():continue
        with xr.open_dataset(path) as a,xr.open_dataset(first/path.name) as b:
            assert set(a.variables)==set(b.variables)
            for name in a.variables:
                if np.issubdtype(a[name].dtype,np.datetime64):assert np.array_equal(a[name],b[name])
                else:same(a[name].values,b[name].values)
    provider=load(AUDIT/'provider-integration.json');assert provider['result']=='PASS'
    for row in provider['checks']:assert sha(WORK/f'provider-week2-{row["kind"]}.nc')==row['provider_file_sha256']
    record={'date':'2026-11-02','result':'PASS','fits_run':0,'network_requests':0,
        'netcdf_outputs_verified':7,'daily_country_caches_verified':len(source_records),
        'model_checks':model_checks,'observation_checks':obs_checks,'missing_native_pixels':missing,
        'reference_sensitivity':differences,'case_one_files_unchanged':len(protected),
        'notebooks_kits_logos_unchanged':len(appearance),'native_case_two_outputs_unchanged':len(native),
        'scope':'Two bounded input checks only; no full-cohort pixel QC, calibration, or skill validation.'}
    (AUDIT/'verification.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))

if __name__=='__main__':main()
