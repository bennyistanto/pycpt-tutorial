"""Read-only source/metadata audit; never imports a fitter or launches CPT.

Run with the pinned Debian environment. Credentials stay in the native file;
only boolean presence and sanitized HTTP outcomes enter the evidence record.
"""
from __future__ import annotations
import argparse
import ast
import datetime as dt
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import re
import stat
import struct
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import requests

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / 'research/audits/subseasonal-readiness'
SCRATCH = ROOT / 'temp/subseasonal-readiness'
STAMP = '2026-11-02'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def source_inventory():
    dist = metadata.distribution('pycpt')
    records = {}
    for relative in ['pycpt/subseasonal.py', 'cptdl/catalog.py', 'cptdl/utilities.py']:
        path = Path(dist.locate_file(relative))
        text = path.read_text()
        tree = ast.parse(text)
        (SCRATCH/('installed-'+relative.replace('/','-'))).write_text(text)
        dictionaries, functions = {}, {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        dictionaries[target.id] = {str(ast.literal_eval(k)): ast.literal_eval(v)
                            for k, v in zip(node.value.keys, node.value.values)
                            if isinstance(k, ast.Constant) and isinstance(v, (ast.Constant, ast.Dict, ast.List))}
            if isinstance(node, ast.FunctionDef):
                functions[node.name] = {'line': node.lineno, 'end_line': node.end_lineno,
                    'signature': ast.unparse(node.args)}
        records[relative] = {'path': str(path), 'sha256': sha(path), 'functions': functions,
            'dictionary_keys': {k: list(v) for k, v in dictionaries.items()}}
        if relative.endswith('subseasonal.py'):
            records[relative]['templates'] = dictionaries
            records[relative]['source_notes'] = {
                'download_authentication': 'use_dlauth=False in all three downloader calls',
                'hindcast_date_restriction': '6 Jan 1999 to 28 Jun 2017 in the literal URL',
                'lead_edges': 'day1=lead_low+0.5; day2=lead_high+0.5; nday=lead_high-lead_low+1',
                'amount_multiplier': 'Literal 7.0 days even when nday differs from seven',
                'predictand': 'CHIRPS v2 daily-improved; observed climatology comes from ECMWF S2S CHIRPS',
                'data_values': 'Precomputed model/observation day-of-year climatologies subtracted',
                'time_encoding': 'Artificial monthly time axis from Jan 1700 replaces native sample dates',
                'pcr': 'evaluate_models explicitly raises PCR not yet implemented for subseasonal',
                'raw_branch': 'hindcast1/Y1 assigned only in CCA branch; else refers to these names',
                'local_predictand': 'download_data has no local_predictand_file parameter',
                'download_utility': 'cptdl.download requires kwargs[target] after parsing; driver does not supply target',
            }
    notebook = ROOT / 'temp/official-notebooks/raw/Subseasonal/pycpt-s2s.ipynb'
    nb = json.loads(notebook.read_text())
    settings = ''.join(nb['cells'][6]['source'])
    record = {'date': STAMP, 'python': sys.version.split()[0], 'pycpt_python_metadata': dist.version,
        'installed_sources': records, 'pinned_example': {
            'commit': '1c975316910b9e047ce685d9b8cdefb2c4b73551', 'sha256': sha(notebook),
            'models': ['GEFSv12.PRCP'], 'leads': [['Week 1',1,7],['Week 2',8,14]],
            'validation': 'retroactive', 'initial_training_percent':45,'step_percent':10,
            'crossvalidation_window_samples':5, 'executed':False},
        'fits_run':0, 'installed_packages_modified':False}
    (AUDIT/'source-inventory.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps({'stage':'source','models':records['pycpt/subseasonal.py']['dictionary_keys']['hindcasts'],
                      'pycpt':dist.version,'fits_run':0}), flush=True)

def native_auth():
    path = Path.home()/'.pycpt_dlauth'
    info = {'credential_file_present': path.is_file()}
    if not path.is_file():
        return {}, info
    info['credential_file_mode'] = oct(stat.S_IMODE(path.stat().st_mode))
    try:
        token = json.loads(path.read_bytes()).get('key')
        info['credential_loaded'] = bool(token)
        return ({'__dlauth_id': token} if token else {}), info
    except Exception:
        info['credential_loaded'] = False
        return {}, info

def bounded_get(url, *, cookies=None, cap=2_000_000, headers=None):
    # No authentication flows, agreement forms, raw headers or credential values.
    try:
        with requests.get(url, cookies=cookies or {}, headers=headers or {},
                          timeout=(12,35), stream=True, allow_redirects=False) as response:
            body = bytearray()
            for chunk in response.iter_content(16384):
                body.extend(chunk)
                if len(body)>cap:
                    break
            info = {'url':url,'status':response.status_code,'content_type':response.headers.get('Content-Type',''),
                    'bytes_sampled':len(body),'truncated':len(body)>cap}
            if response.is_redirect:
                location = response.headers.get('Location','')
                info['redirect_path'] = urlsplit(location).path
            return info, bytes(body[:cap])
    except requests.RequestException as exc:
        return {'url':url,'error_type':type(exc).__name__}, b''

def access_probe():
    cookies, auth_info = native_auth()
    roots = {
        'SubX_GEFSv12_CPC_weekly': 'https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX/.EMC/.GEFSv12_CPC/.hindcast/.weekly/.pr',
        'SubX_GEFSv12_CPC_forecast': 'https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX/.EMC/.GEFSv12_CPC/.forecast/.pr',
        'SubX_root': 'https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX',
        'S2S_root': 'https://iridl.ldeo.columbia.edu/SOURCES/.ECMWF/.S2S',
        'CHIRPS_v2_daily': 'https://iridl.ldeo.columbia.edu/SOURCES/.UCSB/.CHIRPS/.v2p0/.daily-improved/.global/.0p25/.prcp',
    }
    items=[]
    for name, base in roots.items():
        info, body=bounded_get(base+'/dods.dds',cookies=cookies)
        info['name']=name
        text=body.decode('utf8',errors='replace')
        if 'Dataset {' in text and info.get('status')==200:
            # DDS contains data-variable names/dimensions, never account details.
            info['dds']=text
            (SCRATCH/(name+'.dds')).write_bytes(body)
        elif 'Please sign in' in text or info.get('redirect_path','').startswith('/auth'):
            info['access']='authentication_required_or_credential_not_accepted'
        else:
            info['access']='not_a_DDS_response'
        items.append(info)
        print(json.dumps({'stage':'access','name':name,'status':info.get('status'),'error':info.get('error_type'),
                          'dds':'dds' in info,'redirect':info.get('redirect_path')}),flush=True)
    (AUDIT/'access.json').write_text(json.dumps({'date':STAMP,'auth':auth_info,'probes':items,
        'credentials_recorded':False,'fits_run':0},indent=2)+'\n')

def metadata_probe():
    cookies, _ = native_auth()
    gefs='https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX/.EMC/.GEFSv12_CPC'
    requests_to_make={
        'GEFS_weekly_attributes':gefs+'/.hindcast/.weekly/.pr/dods.das',
        'GEFS_weekly_coordinates':gefs+'/.hindcast/.weekly/.pr/dods.ascii?S,L,M,X,Y',
        'GEFS_forecast_attributes':gefs+'/.forecast/.pr/dods.das',
        'GEFS_forecast_coordinates':gefs+'/.forecast/.pr/dods.ascii?S,L,M,X,Y',
        'SubX_index':'https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX/index.html',
        'S2S_index':'https://iridl.ldeo.columbia.edu/SOURCES/.ECMWF/.S2S/index.html',
    }
    items=[]
    for name,url in requests_to_make.items():
        info,body=bounded_get(url,cookies=cookies)
        text=body.decode('utf8',errors='replace')
        info['name']=name
        if 'Attributes {' in text or 'Dataset {' in text:
            (SCRATCH/(name+'.txt')).write_text(text)
            info['metadata_file']=str((SCRATCH/(name+'.txt')).relative_to(ROOT))
            info['sha256']=hashlib.sha256(body).hexdigest()
        elif name.endswith('index') and info.get('status')==200 and 'Please sign in' not in text:
            # Keep dataset-navigation targets only, not user account navigation.
            info['dataset_links']=sorted(set(re.findall(r'href=["\']([^"\']*\.[A-Za-z][^"\']*)["\']',text)))
            info['dataset_links']=[link for link in info['dataset_links'] if '/.' in link or link.startswith('.')]
        items.append(info)
        print(json.dumps({'stage':'metadata','name':name,'status':info.get('status'),
            'error':info.get('error_type'),'metadata':'metadata_file' in info,
            'links':len(info.get('dataset_links',[]))}),flush=True)
    (AUDIT/'live-metadata.json').write_text(json.dumps({'date':STAMP,'probes':items,'fits_run':0},indent=2)+'\n')

def coordinate_probe():
    cookies,_=native_auth()
    base='https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX/.EMC/.GEFSv12_CPC'
    items=[]
    for kind,path in [('hindcast','/.hindcast/.weekly/.pr'),('forecast','/.forecast/.pr')]:
        info,body=bounded_get(base+path+'/dods.dods?S,L,M,X,Y',cookies=cookies)
        info['kind']=kind
        if b'Data:\n' in body:
            header,payload=body.split(b'Data:\n',1)
            dimensions=re.findall(rb'Float32\s+(\w+)\[\w+\s*=\s*(\d+)\]',header)
            offset=0;coords={}
            for name,size in dimensions:
                count=int(size)
                n1,n2=struct.unpack_from('>II',payload,offset);offset+=8
                assert n1==n2==count,(kind,name,count,n1,n2)
                values=struct.unpack_from('>'+str(count)+'f',payload,offset);offset+=4*count
                coords[name.decode()]=list(values)
            assert offset==len(payload),(offset,len(payload))
            info['coordinates']=coords
            dates=[dt.datetime(1960,1,1)+dt.timedelta(days=v) for v in coords['S']]
            info['start_range']=[min(dates).isoformat(),max(dates).isoformat()]
            info['initialization_weekdays']=sorted(set(d.strftime('%A') for d in dates))
            info['year_counts']={str(y):sum(d.year==y for d in dates) for y in sorted(set(d.year for d in dates))}
            (SCRATCH/(kind+'-coordinates.dods')).write_bytes(body)
        items.append(info)
        print(json.dumps({'stage':'coordinates','kind':kind,'status':info.get('status'),
                          'range':info.get('start_range'),'error':info.get('error_type')}),flush=True)
    (AUDIT/'coordinates.json').write_text(json.dumps({'date':STAMP,'probes':items,'fits_run':0},indent=2)+'\n')

def decode_coordinates(body):
    header,payload=body.split(b'Data:\n',1)
    arrays=re.findall(rb'(Float32|Float64|Int32)\s+(\w+)((?:\[\w+\s*=\s*\d+\])+)',header)
    offset=0;coords={}
    for dtype,name,shape in arrays:
        sizes=[int(v) for v in re.findall(rb'=\s*(\d+)',shape)]
        count=1
        for n in sizes:count*=n
        n1,n2=struct.unpack_from('>II',payload,offset);offset+=8
        assert n1==n2==count,(name,count,n1,n2)
        code,width={b'Float32':('f',4),b'Float64':('d',8),b'Int32':('i',4)}[dtype]
        values=struct.unpack_from('>'+str(count)+code,payload,offset);offset+=width*count
        coords[name.decode()]={'shape':sizes,'values':list(values)}
    assert offset==len(payload),(offset,len(payload))
    return coords

def grids_probe():
    cookies,_=native_auth()
    subx='https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX/'
    paths={
        'CFSv2_SubX':subx+'.NCEP/.CFSv2/',
        'FIM_SubX':subx+'.ESRL/.FIMr1p1/',
        'GEPS7_SubX':subx+'.ECCC/.GEPS7/',
        'GEPS8_SubX':subx+'.ECCC/.GEPS8/',
        'GEOS3_SubX':subx+'.GMAO/.GEOS_V3/',
        'GEPS6_SubX':subx+'.ECCC/.GEPS6/',
        'GEPS5_SubX':subx+'.ECCC/.GEPS5/',
        'GEM_SubX':subx+'.ECCC/.GEM/',
        'GEOS2p1_SubX':subx+'.GMAO/.GEOS_V2p1/',
        'GEOS2p1_5daily_SubX':subx+'.GMAO/.GEOS_V2p1_5daily/',
        'CCSM4_SubX':subx+'.RSMAS/.CCSM4/',
        'NESM_SubX':subx+'.NRL/.NESM/',
        'CESM30_SubX':subx+'.CESM/.30LCESM1/',
        'CESM46_SubX':subx+'.CESM/.46LCESM1/',
        'GEFS_legacy_SubX':subx+'.EMC/.GEFS/',
        'GEFSv12_legacy_SubX':subx+'.EMC/.GEFSv12/',
    }
    jobs=[(name,kind,base+branch+'/.pr') for name,base in paths.items()
          for kind,branch in [('hindcast','.hindcast'),('forecast','.forecast_weekly' if name=='FIM_SubX' else '.forecast')]]
    def one(args):
        name,kind,base=args
        info,body=bounded_get(base+'/dods.dds',cookies=cookies);info.update(name=name,kind=kind)
        header=body.decode('utf8',errors='replace')
        if 'Dataset {' not in header:return info
        dims=dict(re.findall(r'(?:Float32|Float64|Int32)\s+(\w+)\[\w+\s*=\s*(\d+)\]',header.split('Grid {')[0]))
        info['dimensions']={k:int(v) for k,v in dims.items()}
        ai,ab=bounded_get(base+'/dods.das',cookies=cookies)
        attrs=ab.decode('utf8',errors='replace')
        info['attributes_status']=ai.get('status')
        info['units']={k:re.search(r'String units "([^"]+)"',block).group(1)
            for k,block in re.findall(r'(\w+)\s*\{([^{}]+)\}',attrs)
            if re.search(r'String units "([^"]+)"',block)}
        ci,cb=bounded_get(base+'/dods.dods?'+','.join(dims),cookies=cookies)
        info['coordinates_status']=ci.get('status')
        if b'Data:\n' in cb:
            try:coords=decode_coordinates(cb)
            except (AssertionError,ValueError,struct.error):
                info['coordinate_parse']='unresolved';return info
            info['coordinate_metadata']={k:{'shape':v['shape'],'min':min(v['values']), 'max':max(v['values']),
                'first':v['values'][:3],'last':v['values'][-3:]} for k,v in coords.items() if v['values']}
            if 'S' in coords and info['units'].get('S')=='days since 1960-01-01':
                dates=[dt.datetime(1960,1,1)+dt.timedelta(days=v) for v in coords['S']['values']]
                info['start_range']=[min(dates).isoformat(),max(dates).isoformat()]
                info['year_counts']={str(y):sum(d.year==y for d in dates) for y in sorted(set(d.year for d in dates))}
                info['initialization_weekdays']=sorted(set(d.strftime('%A') for d in dates))
        print(json.dumps({'stage':'grids','model':name,'kind':kind,'status':info.get('status'),
                         'range':info.get('start_range'),'dims':info.get('dimensions')}),flush=True)
        return info
    previous=AUDIT/'model-grids.json'
    cached=json.loads(previous.read_text())['probes'] if previous.exists() else []
    done={(p['name'],p['kind']) for p in cached if 'coordinate_metadata' in p}
    jobs=[j for j in jobs if (j[0],j[1]) not in done]
    with ThreadPoolExecutor(max_workers=2) as pool:items=list(pool.map(one,jobs))
    items=[p for p in cached if (p['name'],p['kind']) in done]+items
    (AUDIT/'model-grids.json').write_text(json.dumps({'date':STAMP,'probes':items,'fits_run':0},indent=2)+'\n')

def field_probe():
    import numpy as np
    import xarray as xr
    cookies=None
    subx='https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX/'
    # Fixed availability samples, not a selected teaching or verification case.
    jobs=[
        ('GEFS_1989',subx+'.EMC/.GEFSv12_CPC/.hindcast/.weekly/.pr','0000 4 Jan 1989'),
        ('GEFS_2000',subx+'.EMC/.GEFSv12_CPC/.hindcast/.weekly/.pr','0000 5 Jan 2000'),
        ('GEFS_2018',subx+'.EMC/.GEFSv12_CPC/.hindcast/.weekly/.pr','0000 26 Dec 2018'),
        ('GEFS_forecast_2023',subx+'.EMC/.GEFSv12_CPC/.forecast/.pr','0000 1 Jun 2023'),
        ('CFSv2_hindcast',subx+'.NCEP/.CFSv2/.hindcast/.pr','0000 1 Jan 1999'),
        ('FIM_hindcast',subx+'.ESRL/.FIMr1p1/.hindcast/.pr','0000 6 Jan 1999'),
        ('GEPS7_hindcast',subx+'.ECCC/.GEPS7/.hindcast/.pr','0000 1 Jan 2001'),
        ('GEPS8_hindcast',subx+'.ECCC/.GEPS8/.hindcast/.pr','0000 1 Jan 2001'),
        ('GEOS3_hindcast',subx+'.GMAO/.GEOS_V3/.hindcast/.pr','0000 1 Jan 1999'),
    ]
    items=[]
    for name,base,date in jobs:
        url=base+'/S/('+date.replace(' ','%20')+')/VALUES/X/94/143/RANGE/Y/-12/7/RANGE/L/8.5/28.5/RANGE/data.nc'
        path=SCRATCH/(name+'.nc')
        if path.exists():
            body=path.read_bytes();info={'url':url,'status':200,'cached_audit_sample':True}
        else:
            if cookies is None:cookies,_=native_auth()
            info,body=bounded_get(url,cookies=cookies,cap=8_000_000)
        info['name']=name
        if body.startswith(b'CDF') or body.startswith(b'\x89HDF'):
            path.write_bytes(body)
            with xr.open_dataset(path,decode_timedelta=False) as ds:
                da=ds['pr'].load();a=da.values
                good=np.isfinite(a)
                info.update(sha256=sha(path),dimensions=dict(ds.sizes),units=da.attrs.get('units'),
                            finite_count=int(good.sum()),total_count=int(a.size),
                            min=float(a[good].min()) if good.any() else None,
                            max=float(a[good].max()) if good.any() else None,
                            negative_count=int((a[good]<0).sum()))
                if 'M' in da.dims:
                    info['members_with_finite_values']=[float(m) for m in da['M'].values if np.isfinite(da.sel(M=m).values).any()]
                if 'L' in ds:
                    info['lead_values']=[float(v) for v in ds['L'].values]
                    info['lead_units']=ds['L'].attrs.get('units')
                info['time_coordinates']={k:[str(v) for v in ds[k].values.reshape(-1)[:3]] for k in ['S','T'] if k in ds}
        items.append(info)
        print(json.dumps({'stage':'field','name':name,'status':info.get('status'),'finite':info.get('finite_count'),
                          'total':info.get('total_count'),'units':info.get('units'),'error':info.get('error_type')}),flush=True)
    (AUDIT/'field-samples.json').write_text(json.dumps({'date':STAMP,'scope':'Availability samples in enclosing rectangle, not complete country-mask/period QC or fitting.',
                        'probes':items,'fits_run':0,'raw_model_files_published':False},indent=2)+'\n')

def s2s_probe():
    cookies,_=native_auth()
    items=[]
    for version in ['CY48','CY49']:
        base='https://iridl.ldeo.columbia.edu/SOURCES/.ECMWF/.S2S/.ECMF/.'+version+'/.reforecast/.perturbed/.sfc_precip/.tp'
        info,body=bounded_get(base+'/dods.dds',cookies=cookies)
        info['version_branch']=version
        text=body.decode('utf8',errors='replace')
        if 'Dataset {' in text:
            info['dds']=text
            ai,ab=bounded_get(base+'/dods.das',cookies=cookies)
            attrs=ab.decode('utf8',errors='replace')
            info['attributes_status']=ai.get('status')
            if 'Attributes {' in attrs:
                info['attributes']=attrs
        items.append(info)
        print(json.dumps({'stage':'s2s','branch':version,'status':info.get('status'),'dds':'dds' in info}),flush=True)
    (AUDIT/'s2s-metadata.json').write_text(json.dumps({'date':STAMP,'probes':items,'fits_run':0},indent=2)+'\n')

def upstream_probe():
    url='https://raw.githubusercontent.com/iri-pycpt/pycpt/084bb5c380c200b5f65f11ba224a965547b91da1/pycpt/src/pycpt/subseasonal.py'
    info,body=bounded_get(url)
    installed=Path(metadata.distribution('pycpt').locate_file('pycpt/subseasonal.py'))
    if info.get('status')==200:
        info['upstream_sha256']=hashlib.sha256(body).hexdigest()
        info['installed_sha256']=sha(installed)
        info['byte_identical']=info['upstream_sha256']==info['installed_sha256']
    (AUDIT/'upstream-source.json').write_text(json.dumps(info,indent=2)+'\n')
    print(json.dumps(info),flush=True)

def auth_scope_probe():
    url='https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX/.EMC/.GEFSv12_CPC/.hindcast/.weekly/.pr/dods.dds'
    info,body=bounded_get(url)
    info['credential_used']=False
    info['dds_readable']=b'Dataset {' in body
    (AUDIT/'anonymous-access.json').write_text(json.dumps(info,indent=2)+'\n')
    print(json.dumps(info),flush=True)

def catalog_probe():
    cookies,_=native_auth()
    subx='https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX/'
    s2s='https://iridl.ldeo.columbia.edu/SOURCES/.ECMWF/.S2S/'
    providers=[(f'SubX_{name}',subx+'.'+name+'/') for name in ['CESM','ECCC','EMC','ESRL','GMAO','NCEP','NRL','RSMAS']]
    providers += [(f'S2S_{name}',s2s+'.'+name+'/') for name in ['BOM','CMA','CNRM','ECCC','ECMF','HMCR','IAP-CAS','ISAC','JMA','KMA','NCEP','UKMO']]
    def one(pair):
        name,url=pair;info,body=bounded_get(url+'index.html',cookies=cookies)
        text=body.decode('utf8',errors='replace');info['name']=name
        if info.get('status')==200 and 'Please sign in' not in text:
            links=sorted(set(re.findall(r'href=["\']([^"\']+)["\']',text)))
            info['child_datasets']=[link for link in links if link.startswith('.') and link.endswith('/')]
        return info
    with ThreadPoolExecutor(max_workers=2) as pool:
        items=list(pool.map(one,providers))
    (AUDIT/'live-catalog.json').write_text(json.dumps({'date':STAMP,'providers':items,'fits_run':0},indent=2)+'\n')
    print(json.dumps({'stage':'catalog','providers':len(items),'readable':sum('child_datasets' in i for i in items),
                      'datasets':{i['name']:i.get('child_datasets',[]) for i in items}}),flush=True)

def detail_probe():
    cookies,_=native_auth()
    roots={
        'CFSv2_SubX':'https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX/.NCEP/.CFSv2/',
        'FIM_SubX':'https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX/.ESRL/.FIMr1p1/',
        'GEPS7_SubX':'https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX/.ECCC/.GEPS7/',
        'GEPS8_SubX':'https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX/.ECCC/.GEPS8/',
        'GEOS3_SubX':'https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX/.GMAO/.GEOS_V3/',
        'ECMWF_CY48_S2S':'https://iridl.ldeo.columbia.edu/SOURCES/.ECMWF/.S2S/.ECMF/.CY48/',
        'ECMWF_CY49_S2S':'https://iridl.ldeo.columbia.edu/SOURCES/.ECMWF/.S2S/.ECMF/.CY49/',
    }
    items=[]
    for name,url in roots.items():
        for kind in ['', '.hindcast/','.reforecast/']:
            if kind and kind not in children:
                continue
            info,body=bounded_get(url+kind+'index.html',cookies=cookies)
            text=body.decode('utf8',errors='replace');info.update(name=name,branch=kind)
            links=sorted(set(re.findall(r'href=["\']([^"\']+)["\']',text)))
            info['children']=[link for link in links if link.startswith('.') and link.endswith('/')]
            if not kind:children=info['children']
            items.append(info)
    (AUDIT/'model-details.json').write_text(json.dumps({'date':STAMP,'probes':items},indent=2)+'\n')
    print(json.dumps({'stage':'details','items':[{k:p[k] for k in ['name','branch','status','children'] if k in p} for p in items]}),flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',choices=['source','access','metadata','coordinates','catalog','details','grids','fields','s2s','upstream','auth-scope','all'],default='source')
    args=parser.parse_args()
    AUDIT.mkdir(parents=True,exist_ok=True);SCRATCH.mkdir(parents=True,exist_ok=True)
    if args.stage in ['source','all']:source_inventory()
    if args.stage in ['access','all']:access_probe()
    if args.stage=='metadata':metadata_probe()
    if args.stage=='coordinates':coordinate_probe()
    if args.stage=='catalog':catalog_probe()
    if args.stage=='details':detail_probe()
    if args.stage=='grids':grids_probe()
    if args.stage=='fields':field_probe()
    if args.stage=='s2s':s2s_probe()
    if args.stage=='upstream':upstream_probe()
    if args.stage=='auth-scope':auth_scope_probe()

if __name__=='__main__':main()
