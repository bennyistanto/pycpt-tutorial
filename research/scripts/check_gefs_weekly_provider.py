"""Compare Python daily integration with independent IRI server reduction."""
import json
from pathlib import Path
import sys
import datetime as dt
import hashlib
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_gefs_indonesia_inputs import ROOT,WORK,AUDIT,BASE,get_bytes
import numpy as np
import xarray as xr

def main():
    rows=[]
    for kind,date in [('hindcast','2018-08-29'),('forecast','2023-08-24')]:
        s=dt.date.fromisoformat(date)
        label=f'0000 {s.day} {s:%b} {s.year}'.replace(' ','%20')
        branch='/.hindcast/.weekly/.pr' if kind=='hindcast' else '/.forecast/.pr'
        # Published IRI recipes use lead averages. Integrate with unit-aware
        # duration for rate data and seven daily bins for amount data.
        factor='7/mul' if kind=='hindcast' else 'c%3A/604800/(s)/%3Ac/mul'
        url=BASE+branch+f'/S/({label})/VALUES/X/94/143/RANGE/Y/-12/7/RANGE/L/7.5/13.5/RANGE/%5BL%5Daverage/'+factor+'/data.nc'
        path=WORK/f'provider-week2-{kind}.nc'
        if not path.exists():
            body=get_bytes(url,4_000_000)
            if not body.startswith((b'CDF',b'\x89HDF')):raise ValueError('Not a provider NetCDF response')
            path.write_bytes(body)
        with xr.open_dataset(path,decode_timedelta=False) as ds:
            if len(ds.data_vars)!=1:raise ValueError('Expected one reduced precipitation variable')
            field=next(iter(ds.data_vars))
            reference=ds[field].isel(S=0,drop=True).load()
            if 'L' in reference.dims:reference=reference.squeeze('L',drop=True)
            reference=reference.rename({'M':'member','Y':'latitude','X':'longitude'}).sortby('latitude',ascending=False).sortby('longitude')
            provider_units=ds[field].attrs.get('units')
        with xr.open_dataset(AUDIT/'outputs'/f'gefs-{kind}-{date}-weeks234.nc') as ds:
            actual=ds.rainfall_amount.isel(initialization=0).sel(lead_week=2).load()
        reference,actual=xr.align(reference,actual,join='exact')
        reference=reference.transpose(*actual.dims)
        if not np.allclose(actual,reference,rtol=2e-6,atol=.002):
            raise AssertionError(f'Provider reduction differs: max {float(abs(actual-reference).max())} mm')
        rows.append({'kind':kind,'initialization':date,'provider_url':url,
            'provider_file_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'provider_output_units':provider_units,'values_compared':actual.size,
            'max_absolute_difference_mm':float(abs(actual-reference).max()),
            'rule':'sum seven daily amounts' if kind=='hindcast' else 'sum seven daily mean rates times 86400 seconds',
            'target_start':str(np.datetime64(date)+np.timedelta64(7,'D')),
            'target_end_exclusive':str(np.datetime64(date)+np.timedelta64(14,'D'))})
    out={'date':'2026-11-02','result':'PASS','checks':rows,'fits_run':0,
         'scope':'Numerical integration checked against independent server-side reduction; daily UTC-bin semantics are documented separately from source references.'}
    (AUDIT/'provider-integration.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2))

if __name__=='__main__':main()
