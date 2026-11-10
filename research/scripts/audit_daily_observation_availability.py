"""Check CHIRPS3 daily file-index continuity; no bulk rainfall download."""
import calendar
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_subseasonal_readiness import bounded_get, ROOT, STAMP

AUDIT=ROOT/'research/audits/subseasonal-readiness'
BASE='https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/'

def listing(variant,year):
    info,body=bounded_get(f'{BASE}{variant}/{year}/',cap=1_000_000)
    text=body.decode('utf8',errors='replace')
    dates=sorted(set(re.findall(r'>(chirps-v3\.0\.'+variant+r'\.(\d{4})\.(\d{2})\.(\d{2})\.tif)<',text)))
    actual=sorted({f'{y}-{m}-{d}' for _,y,m,d in dates})
    expected={(dt.date(year,1,1)+dt.timedelta(days=k)).isoformat() for k in range(366 if calendar.isleap(year) else 365)}
    return {'variant':variant,'year':year,'status':info.get('status'),'error_type':info.get('error_type'),
            'url':info['url'],'listing_sha256':hashlib.sha256(body).hexdigest(),
            'daily_tiff_files':len(actual),'first':actual[0] if actual else None,'last':actual[-1] if actual else None,
            'missing_dates':sorted(expected-set(actual)),'unexpected_dates':sorted(set(actual)-expected)}

def sample():
    import numpy as np
    from PIL import Image
    scratch=ROOT/'temp/subseasonal-readiness'
    scratch.mkdir(parents=True,exist_ok=True)
    records=[]
    for variant in ['rnl','sat']:
        url=BASE+variant+'/2023/chirps-v3.0.'+variant+'.2023.09.01.tif'
        path=scratch/('CHIRPS3-'+variant+'-2023-09-01.tif')
        if path.exists():
            body=path.read_bytes();info={'url':url,'status':200,'truncated':False,'cached_audit_sample':True}
        else:
            info,body=bounded_get(url,cap=30_000_000)
        info.update(variant=variant,sample_date='2023-09-01')
        if info.get('status')==200 and not info['truncated'] and body[:4] in [b'II*\x00',b'MM\x00*']:
            path.write_bytes(body)
            info['sha256']=hashlib.sha256(body).hexdigest()
            with Image.open(path) as ds:
                sx,sy,_=ds.tag_v2[33550];tie=ds.tag_v2[33922]
                west,north=tie[3]-tie[0]*sx,tie[4]+tie[1]*sy
                bbox=[int(round((94-west)/sx)),int(round((north-7)/sy)),
                      int(round((143-west)/sx)),int(round((north+12)/sy))]
                a=np.asarray(ds.crop(tuple(bbox)))
                nodata_tag=ds.tag_v2.get(42113)
                nodata=float(str(nodata_tag).strip('\x00')) if nodata_tag is not None else None
                values=a[np.isfinite(a)&(a>=0)]
                geo=list(ds.tag_v2.get(34735,[]));keys={geo[i]:geo[i+3] for i in range(4,len(geo),4) if geo[i+1]==0}
                info.update(crs='EPSG:'+str(keys.get(2048,'unresolved')),bounds=[west,north-ds.height*sy,west+ds.width*sx,north],resolution=[sx,sy],
                    raster_shape=[ds.height,ds.width],nodata=nodata,
                    indonesia_enclosing_window=[94,-12,143,7],window_shape=list(a.shape),
                    window_nonnegative_finite_pixels=int(values.size),window_negative_values=[float(v) for v in np.unique(a[np.isfinite(a)&(a<0)])],finite=bool(np.isfinite(values).all()),
                    nonnegative=bool((values>=0).all()),min=float(values.min()),max=float(values.max()),
                    scope='One enclosing rectangle, including neighbouring land; not the country mask or full daily pixel-continuity audit.')
        records.append(info)
        print(json.dumps({'variant':variant,'status':info.get('status'),'bytes':len(body),
                          'raster_shape':info.get('raster_shape'),'nonnegative_pixels':info.get('window_nonnegative_finite_pixels')}),flush=True)
    (AUDIT/'daily-raster-samples.json').write_text(json.dumps({'date':STAMP,'samples':records,'fits_run':0},indent=2)+'\n')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sample',action='store_true');args=parser.parse_args()
    AUDIT.mkdir(parents=True,exist_ok=True)
    if args.sample:
        sample();return
    root_lists=[];jobs=[]
    for variant in ['rnl','sat']:
        info,body=bounded_get(BASE+variant+'/')
        years=sorted(set(int(y) for y in re.findall(rb'href="(\d{4})/"',body)))
        root_lists.append({'variant':variant,'url':info['url'],'status':info.get('status'),'years':years,
                           'listing_sha256':hashlib.sha256(body).hexdigest()})
        jobs.extend((variant,y) for y in years)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda args:listing(*args),jobs))
    record={'date':STAMP,'root_listings':root_lists,'annual_listings':results,
            'scope':'Filename/index continuity, not daily raster-pixel completeness or independent rain-gauge validation.',
            'daily_rainfall_files_downloaded':0,'fits_run':0}
    (AUDIT/'daily-observations.json').write_text(json.dumps(record,indent=2)+'\n')
    for variant in ['rnl','sat']:
        rows=[r for r in results if r['variant']==variant]
        print(json.dumps({'variant':variant,'years_indexed':len(rows),
            'complete_years':[r['year'] for r in rows if not r['missing_dates'] and r['daily_tiff_files']>0],
            'other_years':[{k:r[k] for k in ['year','daily_tiff_files','first','last','status','error_type']} for r in rows if r['missing_dates']]}),flush=True)

if __name__=='__main__':main()
