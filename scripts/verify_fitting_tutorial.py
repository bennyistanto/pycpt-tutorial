"""Independent NumPy checks for fitting outputs, presentation data and preservation."""
from pathlib import Path
import hashlib,json,re,zipfile
import numpy as np
import xarray as xr
import nbformat
ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'research/audits/fitting-tutorial-2023'
DATA=ROOT/'docs/data/fitting-2023';OUT=ROOT/'docs/assets/fitting-2023'
METHODS=['Raw CFSv2','Climatology','CCA','PCR'];SEASONS=['OND','JJA']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    with xr.open_dataset(p) as ds:return ds.load()

def bilinear(a,x,y,tx,ty):
    """Direct vectorized bilinear interpolation; independent of xarray.interp."""
    sx=np.argsort(x);sy=np.argsort(y);x=x[sx];y=y[sy];a=a[:,sy,:][:,:,sx]
    ix=np.searchsorted(x,tx)-1;iy=np.searchsorted(y,ty)-1
    assert ((ix>=0)&(ix<len(x)-1)).all() and ((iy>=0)&(iy<len(y)-1)).all()
    fx=(tx-x[ix])/(x[ix+1]-x[ix]);fy=(ty-y[iy])/(y[iy+1]-y[iy])
    lo=a[:,iy[:,None],ix[None,:]]*(1-fx)+a[:,iy[:,None],(ix+1)[None,:]]*fx
    hi=a[:,(iy+1)[:,None],ix[None,:]]*(1-fx)+a[:,(iy+1)[:,None],(ix+1)[None,:]]*fx
    return lo*(1-fy)[None,:,None]+hi*fy[None,:,None]

def main():
    baseline=json.loads((AUDIT/'baseline.json').read_text())['protected']
    for path,value in baseline.items():assert sha(ROOT/path)==value,path
    provenance=json.loads((DATA/'provenance.json').read_text())
    for path,info in provenance['outputs'].items():assert sha(DATA/path)==info['sha256'],path
    nb=nbformat.read(ROOT/'docs/notebooks/fit-diagnose-2023.ipynb',4)
    code=[c for c in nb.cells if c.cell_type=='code'];assert len(code)==18
    assert all(c.execution_count is not None and not any(o.output_type=='error' for o in c.outputs) for c in code)
    assert sum(c.id.startswith('fit-') for c in code)==4
    manifest=json.loads((OUT/'execution-manifest.json').read_text())
    assert len(manifest['fits'])==4 and len(manifest['netcdf_outputs'])==30
    assert manifest['offline_guard']=={'credential_reads':0,'remote_connections':0}
    for name,value in manifest['netcdf_outputs'].items():assert sha(OUT/name)==value,name
    for record in manifest['fits']:
        assert record['training_samples']==30 and record['forecast_samples']==1
        assert record['configuration']['crossvalidation_window']==5
        assert record['configuration']['x_eof_modes']==[3,3]
        if record['method']=='cca':assert record['configuration']['cca_modes']==[2,2] and record['configuration']['y_eof_modes']==[3,3]
        for name,info in record['outputs'].items():assert sha(OUT/name)==info['sha256'],name
        commands=(OUT/'sessions'/f"{record['key']}-commands.txt").read_text()
        assert re.search(r'(?:^|\n)534\s*\n5(?:\n|$)',commands),record['key']
    comparison=read(OUT/'forecast-comparison.nc');scores=read(OUT/'deterministic-scores.nc');yearly=read(OUT/'cv-yearly-scores.nc');residual=read(OUT/'cv-residual-summary.nc')
    mask=comparison.evaluation_mask.values.astype(bool);assert mask.sum()==3240
    weights=comparison.evaluation_weight.values[mask];weights=weights/weights.sum()
    f=comparison.forecast_rainfall.transpose('season','forecast_method','Y','X').values[:,:,mask]
    y=comparison.observed_rainfall.transpose('season','Y','X').values[:,mask]
    e=f-y[:,None,:]
    assert np.isfinite(f).all() and np.isfinite(y).all()
    independent={'rmse':np.sqrt(np.sum(e*e*weights,axis=-1)),'mae':np.sum(abs(e)*weights,axis=-1),'bias':np.sum(e*weights,axis=-1)}
    max_gap=0
    for metric,array in independent.items():
        saved=scores[metric].sel(verification='forecast_2023').transpose('season','forecast_method').values
        np.testing.assert_allclose(array,saved,atol=1e-8,rtol=0);max_gap=max(max_gap,float(abs(array-saved).max()))
    max_native_gap=0
    for si,season in enumerate(SEASONS):
        X=read(DATA/f'{season}-X.nc').precipitation;Y=read(DATA/f'{season}-Y.nc').precipitation;F=read(DATA/f'{season}-F.nc').precipitation
        np.testing.assert_array_equal(X['T'],Y['T']);np.testing.assert_array_equal(X['T'].dt.year,np.arange(1991,2021))
        assert Y.Tf.max()<F.S.min()
        raw=bilinear(X.transpose('T','Y','X').values,X.X.values,X.Y.values,Y.X.values,Y.Y.values)[:,mask]
        fy=Y.transpose('T','Y','X').values[:,mask]
        climo=np.stack([fy[np.setdiff1d(np.arange(30),(np.arange(i-2,i+3)%30))].mean(axis=0) for i in range(30)])
        hcs=[read(OUT/f'{season}-{m}-hindcasts.nc').deterministic.transpose('T','Y','X').values[:,mask] for m in ['cca','pcr']]
        cv=np.stack([raw,climo,*hcs]);err=cv-fy[None,:,:]
        annual={'rmse':np.sqrt(np.sum(err**2*weights,axis=-1)),'mae':np.sum(abs(err)*weights,axis=-1),'bias':np.sum(err*weights,axis=-1)}
        for metric,array in annual.items():
            saved=yearly[metric].sel(season=season).transpose('forecast_method','training_year').values
            np.testing.assert_allclose(array,saved,atol=1e-8,rtol=0);max_gap=max(max_gap,float(abs(array-saved).max()))
        pooled={'rmse':np.sqrt(np.mean(annual['rmse']**2,axis=1)),'mae':annual['mae'].mean(axis=1),'bias':annual['bias'].mean(axis=1)}
        spatial={'rmse':np.sqrt(np.mean(err**2,axis=1)),'mae':np.mean(abs(err),axis=1),'bias':np.mean(err,axis=1)}
        for metric,array in pooled.items():
            saved=scores[metric].sel(season=season,verification='cross_validation').values
            np.testing.assert_allclose(array,saved,atol=1e-8,rtol=0);max_gap=max(max_gap,float(abs(array-saved).max()))
            np.testing.assert_allclose(spatial[metric],residual[metric].sel(season=season).transpose('forecast_method','Y','X').values[:,mask],atol=1e-8,rtol=0)
        for i,method in enumerate(['cca','pcr']):
            sk=read(OUT/f'{season}-{method}-native-skill.nc')
            gap=float(abs(spatial['rmse'][i+2]-sk.root_mean_squared_error.values[mask]).max());max_native_gap=max(max_native_gap,gap)
            assert gap<.01
            a=hcs[i]-hcs[i].mean(axis=0);b=fy-fy.mean(axis=0)
            corr=(a*b).sum(axis=0)/np.sqrt((a*a).sum(axis=0)*(b*b).sum(axis=0))
            np.testing.assert_allclose(corr,sk.pearson.values[mask],atol=1e-4,rtol=0)
            fc=read(OUT/f'{season}-{method}-forecasts.nc');control=read(DATA/f'controls/{season}-{method}-forecasts.nc')
            np.testing.assert_allclose(fc.deterministic,control.deterministic,atol=.01,rtol=0,equal_nan=True)
        # Single-year raw/climatology are independently recovered from fitting inputs.
        raw2023=bilinear(F.transpose('T','Y','X').values,F.X.values,F.Y.values,Y.X.values,Y.Y.values)[0][mask]
        np.testing.assert_allclose(raw2023,f[si,0],atol=1e-8,rtol=0)
        np.testing.assert_allclose(fy.mean(axis=0),f[si,1],atol=1e-8,rtol=0)
    payload=json.loads((OUT/'interactive-data.json').read_text());matched=0
    def exact(values,expected):
        nonlocal matched
        array=np.asarray(values,dtype=float);expected=np.asarray(expected,dtype=float)
        assert array.shape==expected.shape
        np.testing.assert_array_equal(array,expected);matched+=int(np.isfinite(expected).sum())
    for row in payload['scores']:
        for metric in ['rmse','mae','bias']:exact(row[metric],scores[metric].sel(season=row['season'],verification=row['verification'],forecast_method=row['method']).values)
    for row in payload['yearly']:
        for metric in ['rmse','mae','bias']:exact(row[metric],yearly[metric].sel(season=row['season'],training_year=row['year'],forecast_method=row['method']).values)
    score_series=0
    for season in SEASONS:
        for side in ['predictor','predictand']:
            ds=read(OUT/f'{season}-cca-{side}-diagnostics.nc');item=payload['diagnostics'][season][side]
            exact(item['longitude'],ds.X);exact(item['latitude'],ds.Y);exact(item['years'],ds['T'].dt.year)
            exact(item['variance'],ds.explained_variance_percent);exact(item['cumulative'],ds.cumulative_variance_percent)
            for kind,n in [('eof',3),('cca',2)]:
                exact(item[kind]['fields'],ds[f'{kind}_correlation'].transpose(f'{kind}_mode','Y','X'))
                native=ds[f'{kind}_score'].transpose(f'{kind}_mode','T').values
                exact(item[kind]['score'],native)
                z=(native-native.mean(axis=1)[:,None])/native.std(axis=1,ddof=1)[:,None]
                np.testing.assert_allclose(item[kind]['standardizedScore'],z,atol=1e-14,rtol=0);score_series+=z.size
                valid=read(DATA/f"{season}-{'X' if side=='predictor' else 'Y'}.nc").precipitation.notnull().all('T').values
                assert np.isfinite(ds[f'{kind}_native_weight'].values[:,valid]).all()
                assert np.isnan(ds[f'{kind}_native_weight'].values[:,~valid]).all()
        canonical=read(OUT/f'{season}-cca-canonical-correlations.nc');exact(payload['diagnostics'][season]['canonical'],canonical.native_correlation)
        exact(payload['maps'][season]['longitude'],comparison.X);exact(payload['maps'][season]['latitude'],comparison.Y)
        for field,var in [('rainfall','forecast_rainfall'),('absoluteError','absolute_error'),('signedError','signed_error')]:
            for method in METHODS:exact(payload['maps'][season][field][method],comparison[var].sel(season=season,forecast_method=method))
    source=ROOT/'docs/notebooks/fit-diagnose-2023.ipynb'
    assert sha(ROOT/'docs/downloads'/source.name)==sha(source)
    kit_record=json.loads((AUDIT/'kit.json').read_text())
    for name in ['kit','output_archive']:
        item=kit_record[name];assert sha(ROOT/item['file'])==item['sha256']
    with zipfile.ZipFile(ROOT/kit_record['output_archive']['file']) as z:
        assert sum(n.endswith('.nc') for n in z.namelist())==30
        for path,value in manifest['netcdf_outputs'].items():assert hashlib.sha256(z.read(path)).hexdigest()==value
    for path,value in baseline.items():assert sha(ROOT/path)==value,path
    story=(ROOT/'docs/_book/chapters/fit-diagnose-2023.html').read_text()
    assert all(f'data-fitting-panel="{name}"' in story for name in ['inputs','scores','scree','patterns','cv','errors'])
    assert 'CPT19' not in story and 'CPT 19' not in story
    rendered_notebook=(ROOT/'docs/_book/notebooks/fit-diagnose-2023.html').read_text()
    assert not re.findall(r'<script[^>]*src="https?://',rendered_notebook)
    result={'date':'2026-11-02','result':'PASS','case_one_files_byte_identical':len(baseline),'code_cells':18,'authoring_fits_in_current_notebook':4,
        'netcdf_outputs_verified':30,'prepared_files_hash_verified':len(provenance['outputs']),
        'independent_numpy_max_score_gap_mm':max_gap,'native_cv_rmse_max_gap_mm':max_native_gap,
        'browser_values_exactly_matched':matched,'standardized_series_values_checked':score_series,
        'interactive_panels':6,'canonical_notebook_sha256':sha(source),'kit_sha256':kit_record['kit']['sha256'],
        'source_code_sha256':{name:sha(ROOT/name) for name in ['pycpt_tutorial/fitting.py','docs/assets/fitting-2023/fitting.js','scripts/verify_fitting_tutorial.py']}}
    (AUDIT/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
