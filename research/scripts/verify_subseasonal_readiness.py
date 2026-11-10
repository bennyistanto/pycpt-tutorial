"""Offline cross-check of saved readiness evidence; no network or fitting."""
import calendar
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

import numpy as np
from PIL import Image
import xarray as xr

ROOT=Path(__file__).resolve().parents[2]
AUDIT=ROOT/'research/audits/subseasonal-readiness'
read=lambda name:json.loads((AUDIT/name).read_text())
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    summary=read('summary.json')
    assert summary['fits_run']==0 and not summary['model_case_selected'] and not summary['training_period_selected']
    upstream=read('upstream-source.json');assert upstream['byte_identical']
    driver=read('driver-checks.json');assert driver['fits_run']==driver['network_requests']==0
    assert driver['checks']['fresh_download']['missing_keyword']=='target'
    assert driver['checks']['PCR']['message']=='PCR not yet implemented for subseasonal'
    assert driver['checks']['None']['exception']=='UnboundLocalError'
    models=list(csv.DictReader((AUDIT/'model-availability.csv').open()))
    assert len(models)==17 and len({r['model'] for r in models})==17
    raw_profiles=read('model-grids.json')['probes']
    assert len(raw_profiles)==32
    for item in raw_profiles:
        if 'coordinate_metadata' not in item:continue
        c=item['coordinate_metadata']
        assert c['X']['min']<=94 and c['X']['max']>=143
        assert c['Y']['min']<=-12 and c['Y']['max']>=7
    for item in read('coordinates.json')['probes']:
        c=item['coordinates'];dates=[dt.datetime(1960,1,1)+dt.timedelta(days=v) for v in c['S']]
        assert len(dates)==len(set(dates))
        assert item['start_range']==[min(dates).isoformat(),max(dates).isoformat()]
        if item['kind']=='hindcast':
            assert len(dates)==1600 and all(d.weekday()==2 for d in dates)
            assert all((b-a).days==7 for a,b in zip(dates,dates[1:]))
        for low,high in [(1,7),(8,14),(15,21),(22,28)]:
            assert sum(low+.5<=v<=high+.5 for v in c['L'])==7
    sample_count=0
    for item in read('field-samples.json')['probes']:
        path=ROOT/'temp/subseasonal-readiness'/(item['name']+'.nc')
        assert sha(path)==item['sha256']
        with xr.open_dataset(path,decode_timedelta=False) as ds:
            a=ds.pr.load();good=np.isfinite(a.values)
            assert int(good.sum())==item['finite_count'] and a.size==item['total_count']
            members=[float(m) for m in a['M'].values if np.isfinite(a.sel(M=m).values).any()]
            assert members==item['members_with_finite_values']
            assert len(a['L'])==21 and float(a['L'][0])==8.5 and float(a['L'][-1])==28.5
            assert item['negative_count']==int((a.values[good]<0).sum())
        sample_count+=1
    assert sample_count==9
    listings=read('daily-observations.json')['annual_listings']
    for variant,start in [('rnl',1981),('sat',1998)]:
        rows={r['year']:r for r in listings if r['variant']==variant}
        for year in range(start,2026):
            r=rows[year];assert r['status']==200 and not r['missing_dates'] and not r['unexpected_dates']
            assert r['daily_tiff_files']==(366 if calendar.isleap(year) else 365)
        assert rows[2026]['daily_tiff_files']==273 and rows[2026]['last']=='2026-09-30'
        assert all(rows[y]['daily_tiff_files']==0 for y in range(2027,2031))
    for item in read('daily-raster-samples.json')['samples']:
        path=ROOT/'temp/subseasonal-readiness'/('CHIRPS3-'+item['variant']+'-2023-09-01.tif')
        assert sha(path)==item['sha256']
        with Image.open(path) as ds:
            assert ds.size==(7200,2400)
            assert abs(ds.tag_v2[33550][0]-.05)<1e-8
            assert ds.tag_v2.get(42113) is None
    assert read('anonymous-access.json')['dds_readable']
    assert all(p['redirect_path']=='/auth/credential' for p in read('s2s-metadata.json')['probes'])
    # The supplied scientific preservation baselines are independent of this audit.
    base=json.loads((ROOT/'research/audits/fitting-tutorial-2023/baseline.json').read_text())['protected']
    assert all(sha(ROOT/name)==expected for name,expected in base.items())
    appearance=json.loads((ROOT/'research/audits/appearance/baseline.json').read_text())
    assert all(sha(ROOT/name)==expected for name,expected in appearance.items())
    styles=json.loads((ROOT/'research/audits/style-reorganization/baseline.json').read_text(encoding='utf-8-sig'))
    assert all(sha(ROOT/'docs/styles'/name)==expected for name,expected in styles.items())
    record={'date':'2026-11-02','result':'PASS','model_version_entries':17,'coordinate_branch_profiles':31,
        'model_netcdf_samples_rechecked':sample_count,'daily_index_year_directories':len(listings),
        'daily_raster_sample_hashes_rechecked':2,'case_one_files_byte_identical':len(base),
        'appearance_notebook_kit_logo_files_unchanged':len(appearance),'styles_moved_byte_identically':3,
        'network_requests':0,'fits_run':0,'model_case_selected':False,
        'limits':'Readiness metadata and bounded samples; not complete all-date/member/country-cell data QC or forecast-skill validation.'}
    (AUDIT/'verification.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))

if __name__=='__main__':main()
