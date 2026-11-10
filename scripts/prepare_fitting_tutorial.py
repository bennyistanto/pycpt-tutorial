"""Package audited OND/JJA local fitting inputs and controls; never refit."""
from pathlib import Path
import hashlib,json,shutil
import numpy as np
import xarray as xr
import shapefile
from shapely.geometry import shape,mapping,box
from shapely import make_valid
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from pycpt_tutorial.export import save_netcdf

NATIVE=Path('/home/bennyistanto/CPT/cases/indonesia-all-seasons-2021-2024-025deg')
DATA=ROOT/'docs/data/fitting-2023'
AUDIT=ROOT/'research/audits/fitting-tutorial-2023'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    with xr.open_dataset(p) as ds:return ds.load()

def main():
    AUDIT.mkdir(exist_ok=True)
    baseline=AUDIT/'baseline.json'
    if not baseline.exists():
        files={ROOT/'docs/notebooks/indonesia-seasons-2023.ipynb',ROOT/'docs/chapters/indonesia-seasons-2023.qmd',
               ROOT/'docs/downloads/indonesia-seasons-2023-kit.zip',ROOT/'docs/downloads/indonesia-seasons-2023.ipynb'}
        for folder in ['docs/assets/seasonal-2023','docs/assets/story','docs/data']:
            files.update(p for p in (ROOT/folder).rglob('*') if p.is_file() and 'fitting-2023' not in p.parts)
        baseline.write_text(json.dumps({'date':'2026-11-02','protected':{str(p.relative_to(ROOT)):sha(p) for p in sorted(files)}},indent=2)+'\n')
    protected=json.loads(baseline.read_text())['protected']
    DATA.mkdir(exist_ok=True);controls=DATA/'controls';controls.mkdir(exist_ok=True)
    records=json.loads((ROOT/'research/cases/indonesia-all-seasons-2021-2024-025deg/fit_records.json').read_text())
    native_hashes={};output={}
    def save(ds,name):
        p=DATA/name;save_netcdf(ds,p,overwrite=True);output[name]={'sha256':sha(p),'bytes':p.stat().st_size}
    context=read(ROOT/'docs/data/indonesia-seasons-2023.nc').sel(season=['OND','JJA'])
    context=context.sel(forecast_variant=['raw_cfsv2','climatology_1991_2020','cca_1991_2020','pcr_1991_2020'])
    save(context,'comparison-context.nc')
    for season in ['OND','JJA']:
        folder=NATIVE/season
        sources={n:read(folder/n) for n in ['predictors.nc','observations.nc','footprint.nc']}
        for name in sources:
            native_hashes[str(folder/name)]=sha(folder/name)
            for method in ['cca','pcr']:assert sha(folder/name)==records[f'{season}_{method}_1991_2020']['input_sha256'][name]
        x=sources['predictors.nc'].precipitation
        y=sources['observations.nc'].precipitation
        mask=sources['footprint.nc'].analysis_mask.sel(training_period='1991_2020',drop=True).astype(bool)
        np.testing.assert_array_equal(mask,context.evaluation_mask)
        train=x.season_year.isin(np.arange(1991,2021));forecast=x.season_year==2023
        X=x.sel(T=train).drop_vars('season_year');Y=y.sel(T=train).where(mask).drop_vars('season_year');F=x.sel(T=forecast).drop_vars('season_year')
        assert X.sizes['T']==Y.sizes['T']==30 and F.sizes['T']==1 and int(mask.sum())==3240
        np.testing.assert_array_equal(X['T'],Y['T'])
        assert Y.attrs['units']==X.attrs['units']==F.attrs['units']=='mm'
        for name,a in [('X',X),('Y',Y),('F',F)]:
            save(a.to_dataset(name='precipitation'),f'{season}-{name}.nc')
        for method in ['cca','pcr']:
            key=f'{season}_{method}_1991_2020'
            for suffix in ['forecasts','hindcasts','native_skill']:
                p=NATIVE/'outputs'/f'{key}_{suffix}.nc';native_hashes[str(p)]=sha(p)
                assert sha(p)==records[key]['outputs_sha256'][p.name]
                ds=read(p)
                if suffix=='forecasts':ds=ds.sel(T=ds.season_year==2023)
                save(ds,f'controls/{season}-{method}-{suffix}.nc')
            for side in ['predictor']+(['predictand'] if method=='cca' else []):
                p=ROOT/'research/audits/fitting-diagnostics/outputs'/f'{key}_{side}_diagnostics.nc'
                save(read(p),f'controls/{season}-{method}-{side}-diagnostics.nc')
    # A full predictor-domain outline is needed: case-one boundaries are cropped to Indonesia.
    base=Path('/mnt/f/temp/hybrid-bias-correction/data/subset/bnd/wld_bnd_adm0')
    prj=base.with_suffix('.prj');assert 'GCS_WGS_1984' in prj.read_text()
    for suffix in ['.shp','.shx','.dbf','.prj']:native_hashes[str(base.with_suffix(suffix))]=sha(base.with_suffix(suffix))
    features=[];clip=box(85,-20,155,20)
    with shapefile.Reader(str(base),encoding='utf-8') as reader:
        for row in reader.iterShapeRecords():
            geom=shape(row.shape.__geo_interface__)
            if not geom.is_valid:geom=make_valid(geom)
            if not geom.intersects(clip):continue
            geom=geom.intersection(clip).simplify(.025,preserve_topology=True)
            if geom.is_empty:continue
            features.append({'type':'Feature','properties':{},'geometry':mapping(geom)})
    p=DATA/'predictor-boundaries.geojson';p.write_text(json.dumps({'type':'FeatureCollection','features':features},separators=(',',':'))+'\n')
    output[p.name]={'sha256':sha(p),'bytes':p.stat().st_size}
    record={'date':'2026-11-02','case':'fit-diagnose-2023','training_period':'1991-2020','seasons':['OND','JJA'],
        'forecast_year':2023,'data_note':'Prepared local seasonal fields from audited archive; no source download.',
        'boundary_note':'Predictor-domain country outlines clipped/simplified from supplied world shapefile for display only.',
        'outputs':output,'source_hashes':native_hashes,
        'attribution':'CHIRPS3, Climate Hazards Center/UCSB (https://doi.org/10.15780/G2JQ0P); CFSv2, NCEP via IRI Data Library. Boundaries supplied by Benny Istanto; Indonesia boundaries credit BIG. See ../provenance.json and ../boundaries/provenance.json.',
        'controls':'Forecast/hindcast/skill from frozen all-season benchmark; diagnostics from fitting-diagnostics audit.',
        'method_note':'Fixed CCA3X/3Y/2CCA;PCR3X;cyclic CV5;no tuning or empirical probability reliability claim.'}
    (DATA/'provenance.json').write_text(json.dumps(record,indent=2)+'\n')
    for path,value in protected.items():assert sha(ROOT/path)==value,path
    (AUDIT/'preparation.json').write_text(json.dumps({'files':len(output),'protected_files_unchanged':len(protected),'source_files_verified':len(native_hashes),'provenance_sha256':sha(DATA/'provenance.json')},indent=2)+'\n')
    print(json.dumps({'packaged_files':len(output),'protected_case_one_files':len(protected),'source_hashes':len(native_hashes)},indent=2))

if __name__=='__main__':main()
