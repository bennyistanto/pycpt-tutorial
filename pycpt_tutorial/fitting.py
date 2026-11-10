"""Input checks, diagnostic exports and presentation for the fitting tutorial.

The notebook contains the actual PyCPT calls and statistical scoring formulas.
These helpers preserve all returned datasets and verify them against frozen controls.
"""
from pathlib import Path
from contextlib import contextmanager
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import shutil
import sys
import tempfile
import numpy as np
import pandas as pd
import xarray as xr
from .export import save_netcdf
from .cpt_dates import verified_midnight_reader

SEASONS=['OND','JJA']
METHODS=['Raw CFSv2','Climatology','CCA','PCR']
COLORS=['#9b7164','#6b7280','#147d92','#c08325']
SETTINGS=dict(x_eof_modes=(3,3),validation='CROSSVALIDATION',crossvalidation_window=5,
              synchronous_predictors=True,transform_predictand=None,tailoring=None,
              drymask_threshold=None,skillmask_threshold=None)
_OFFLINE=None

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):
    with xr.open_dataset(p) as ds:return ds.load()

def offline_guard():
    """Reject credential reads and remote connections; keep loopback kernel traffic."""
    global _OFFLINE
    if _OFFLINE is not None:return _OFFLINE
    counters={'credential_reads':0,'remote_connections':0}
    def audit(event,args):
        if event=='open' and isinstance(args[0],(str,bytes)):
            name=str(args[0]).lower()
            if 'dlauth' in name or '.iridlauth' in name or Path(name).name=='.env':
                counters['credential_reads']+=1;raise RuntimeError('This local-input lesson does not use credentials.')
        if event=='socket.connect':
            address=args[1]
            if isinstance(address,tuple) and str(address[0]) not in ('127.0.0.1','::1','localhost'):
                counters['remote_connections']+=1;raise RuntimeError('This local-input lesson does not download data.')
    sys.addaudithook(audit);_OFFLINE=counters
    return counters

def preflight():
    version=importlib.metadata.version('pycpt')
    packages={json.loads(p.read_text())['name']:json.loads(p.read_text())['version'] for p in (Path(sys.prefix)/'conda-meta').glob('*.json')}
    if packages.get('pycpt')!='2.10.4' or version not in ['2.10.4','2.10.4.dev0']:
        raise RuntimeError('Use the tested conda PyCPT 2.10.4 fitting environment for this controlled replay.')
    engine=Path(sys.prefix)/'opt/cpt/bin/CPT.x'
    if not engine.exists():raise RuntimeError('Activate the full PyCPT fitting environment; the analysis-only environment cannot fit models.')
    expected='3457c93ee3d7a69005e32c231a976c50a056da53868c02757f344a46a81a139e'
    if sha(engine)!=expected:raise RuntimeError('The fitting engine differs from the verified control. Use the supplied fitting lock.')
    os.environ['CPT_BIN_DIR']=str(engine.parent)
    import inspect
    from cptcore import canonical_correlation_analysis,principal_components_regression
    wrapper_hashes={}
    for name,function,expected in [('cca',canonical_correlation_analysis,'938e2969bbbca4383657374f0c0ecec3cf2752a2acb5acb270874ad045e3253a'),
       ('pcr',principal_components_regression,'e8393bac45c1e5fe5007e6c672f3f2b8dae27c1d6299f7f608006b696063e2c7')]:
        wrapper_hashes[name]=sha(inspect.getsourcefile(function))
        assert wrapper_hashes[name]==expected,'Fitting wrapper differs from audited source.'
    return {'python':sys.version.split()[0],'pycpt':packages['pycpt'],'python_package_metadata':version,
            'cptio':packages['cptio'],'cptio_python_metadata':importlib.metadata.version('cptio'),'wrapper_hashes':json.dumps(wrapper_hashes),
            'engine':'CPT 17.8.3','engine_sha256':sha(engine),'engine_directory':str(engine.parent)}

def verify_inputs(folder):
    record=json.loads((folder/'provenance.json').read_text())
    for name,info in record['outputs'].items():assert sha(folder/name)==info['sha256'],name
    return record

def prepare_inputs(folder,season):
    X=load(folder/f'{season}-X.nc').precipitation
    Y=load(folder/f'{season}-Y.nc').precipitation
    F=load(folder/f'{season}-F.nc').precipitation
    assert X.sizes['T']==Y.sizes['T']==30 and F.sizes['T']==1
    np.testing.assert_array_equal(X['T'],Y['T'])
    np.testing.assert_array_equal(X['T'].dt.year,np.arange(1991,2021))
    assert int(F['T'].dt.year.item())==2023
    assert pd.Timestamp(Y.Tf.max().item())<pd.Timestamp(F.S.item())
    assert all(a.attrs['units']=='mm' for a in [X,Y,F])
    assert int(Y.notnull().all('T').sum())==3240
    return X,Y,F

@contextmanager
def native_session(work,season,method,function,X,F):
    key=f'{season}-{method}';folder=work/key;folder.mkdir()
    session={'key':key,'season':season,'method':method,'folder':folder,
       'kwargs':{'outputdir':folder,'log':work/f'{key}.log','project_file':work/f'{key}-commands.txt'}}
    dates=[pd.Timestamp(v).to_pydatetime() for v in np.concatenate([X.S.values,F.S.values])]
    with verified_midnight_reader(function,dates) as events:
        session['date_parsing']=events
        yield session

def field(path):
    from cptio import open_cptdataset
    ds=open_cptdataset(str(path));assert len(ds.data_vars)==1
    return ds[next(iter(ds.data_vars))]

def correlation_map(data,score):
    np.testing.assert_array_equal(data['T'],score['T'])
    a=data-data.mean('T');b=score-score.mean('T')
    return (a*b).sum('T')/np.sqrt((a*a).sum('T')*(b*b).sum('T'))

def clean_diagnostics(raw,folder,side):
    """Separate axes and decode missing native weights against printed-input support."""
    prefix='x' if side=='predictor' else 'y'
    original=field(folder/f'original_{side}')
    valid=original.notnull().all('T');out={}
    for kind,n in [('eof',3)]+([('cca',2)] if f'{prefix}_cca_scores' in raw else []):
        scores=raw[f'{prefix}_{kind}_scores'].sel(Mode=np.arange(1,n+1)).rename({'Mode':f'{kind}_mode'}).transpose('T',f'{kind}_mode')
        weights=raw[f'{prefix}_{kind}_loadings'].sel(Mode=np.arange(1,n+1)).rename({'Mode':f'{kind}_mode'}).transpose(f'{kind}_mode','Y','X')
        weights=weights.reindex(X=original.X,Y=original.Y,method='nearest',tolerance=1e-3)
        outside=weights.values[:,~valid.values]
        assert outside.size==0 or np.all((outside==-999)|np.isnan(outside))
        weights=weights.where(valid)
        assert np.isfinite(weights.values[:,valid.values]).all()
        out[f'{kind}_native_weight']=weights
        out[f'{kind}_score']=scores
        out[f'{kind}_correlation']=correlation_map(original,scores).transpose(f'{kind}_mode','Y','X')
        out[f'{kind}_native_weight'].attrs={'interpretation':'Native exported weights; outside complete-input support decoded to NaN; not correlation coefficients or rainfall forecasts.'}
        out[f'{kind}_correlation'].attrs={'units':'1','interpretation':'Pearson correlation of printed original training field with saved full-training score; not forecast skill.'}
    spec=np.genfromtxt(folder/f'{side}_explained_variance.txt',skip_header=3,delimiter='\t')
    assert spec.shape==(30,4)
    np.testing.assert_allclose(np.cumsum(spec[:,2]),spec[:,3],atol=2e-5,rtol=0)
    np.testing.assert_allclose(spec[-1,3],100,atol=2e-5,rtol=0)
    out.update(eigenvalue=('spectrum_mode',spec[:,1]),explained_variance_percent=('spectrum_mode',spec[:,2]),cumulative_variance_percent=('spectrum_mode',spec[:,3]))
    ds=xr.Dataset(out,coords={'spectrum_mode':np.arange(1,31)})
    for name in ['explained_variance_percent','cumulative_variance_percent']:ds[name].attrs['units']='%'
    ds.attrs.update(side=side,training_period='1991-2020',validation='Full-training diagnostics; not per-fold patterns or independent predictive skill.',
       scale_note='Native eigenvalue/weight amplitude convention is not independently established; correlations and variance percentages are checked.')
    return ds

def compare_array(actual,expected,atol,rtol=0):
    actual=actual.transpose(*expected.dims)
    for coord in expected.dims:np.testing.assert_array_equal(actual[coord],expected[coord])
    np.testing.assert_allclose(actual.values,expected.values,atol=atol,rtol=rtol,equal_nan=True)
    gap=float(np.nanmax(abs(actual.values-expected.values)))
    return {'maximum_absolute_difference':gap,'absolute_tolerance':atol,'relative_tolerance':rtol}

def export_fit(result,session,root,artifacts,Y):
    """Retain the whole PyCPT return value and compare with verified original fits."""
    season,method=session['season'],session['method'];key=session['key'];folder=session['folder']
    data=root/'docs/data/fitting-2023';mask=Y.notnull().all('T')
    names=['hindcasts','forecasts','native-skill','x-patterns']+(['y-patterns'] if method=='cca' else [])
    assert len(result)==len(names)
    datasets={}
    for name,ds in zip(names,result):
        ds=ds.copy()
        if name in ['hindcasts','forecasts','native-skill']:
            ds=ds.reindex(X=Y.X,Y=Y.Y,method='nearest',tolerance=1e-3)
            for var in ds.data_vars:
                if 'Y' in ds[var].dims and 'X' in ds[var].dims:ds[var]=ds[var].where(mask)
        if name=='y-patterns':
            for var in ds.data_vars:
                if 'Y' in ds[var].dims and 'X' in ds[var].dims:ds[var]=ds[var].where(mask)
        datasets[name]=ds
    comparison={}
    fc_control=load(data/f'controls/{key}-forecasts.nc')
    for var in fc_control.data_vars:
        atol,rtol={'deterministic':(.01,0),'probabilistic':(.001,0),'prediction_error_variance':(.1,2e-6)}[var]
        comparison[f'forecast_{var}']=compare_array(datasets['forecasts'][var],fc_control[var],atol,rtol)
    hc_control=load(data/f'controls/{key}-hindcasts.nc')
    comparison['cv_hindcasts']=compare_array(datasets['hindcasts'].deterministic,hc_control.deterministic,.01)
    skill_control=load(data/f'controls/{key}-native_skill.nc')
    for var in skill_control.data_vars:
        tol=.01 if var=='root_mean_squared_error' else .001
        comparison[f'native_skill_{var}']=compare_array(datasets['native-skill'][var],skill_control[var],tol)
    for side,raw_name in [('predictor','x-patterns')]+([('predictand','y-patterns')] if method=='cca' else []):
        ds=clean_diagnostics(datasets[raw_name],folder,side)
        control=load(data/f'controls/{key}-{side}-diagnostics.nc')
        for var in control.data_vars:
            # Preserve native signs; sign alignment is for checking paired arrays only.
            actual=ds[var]
            if any(t in var for t in ['score','weight','correlation']):
                kind='cca' if var.startswith('cca') else 'eof';dim=f'{kind}_mode'
                signs=[]
                for mode in ds[dim].values:
                    a=ds[f'{kind}_score'].sel({dim:mode}).values
                    b=control[f'{kind}_score'].sel({dim:mode}).values
                    signs.append(1 if np.corrcoef(a,b)[0,1]>=0 else -1)
                actual=actual*xr.DataArray(signs,dims=dim,coords={dim:ds[dim]})
            comparison[f'{side}_{var}']=compare_array(actual,control[var],2e-5)
        datasets[f'{side}-diagnostics']=ds
    if method=='cca':
        r=np.genfromtxt(folder/'cca_canonical_correlation.txt',skip_header=3,delimiter='\t')[:,1]
        x=datasets['predictor-diagnostics'].cca_score;y=datasets['predictand-diagnostics'].cca_score
        direct=np.array([np.corrcoef(x.sel(cca_mode=i),y.sel(cca_mode=i))[0,1] for i in [1,2]])
        np.testing.assert_allclose(r,direct,atol=2e-6,rtol=0)
        datasets['canonical-correlations']=xr.Dataset({'native_correlation':('cca_mode',r),'recomputed_correlation':('cca_mode',direct)},coords={'cca_mode':[1,2]})
    files={}
    for name,ds in datasets.items():
        ds.attrs.update(case='PyCPT fitting tutorial',season=season,method=method,training_period='1991-2020',
          forecast_target_year=2023,validation_note='Deterministic CV5 hindcasts; separate 2023 forecast; full-training diagnostic patterns. Native probabilities are not evidence of empirical reliability.',
          configuration=json.dumps({**SETTINGS,**({'y_eof_modes':(3,3),'cca_modes':(2,2)} if method=='cca' else {})},sort_keys=True))
        path=artifacts/f'{key}-{name}.nc';save_netcdf(ds,path,overwrite=True)
        files[path.name]={'sha256':sha(path),'bytes':path.stat().st_size}
    archive=artifacts/'sessions';archive.mkdir(exist_ok=True)
    for name in ['log','project_file']:
        source=session['kwargs'][name];target=archive/source.name;shutil.copyfile(source,target)
        files[f'sessions/{target.name}']={'sha256':sha(target),'bytes':target.stat().st_size}
    record={'key':key,'season':season,'method':method,'training_samples':30,'forecast_samples':1,
      'native_directory':str(folder),'configuration':{**SETTINGS,**({'y_eof_modes':(3,3),'cca_modes':(2,2)} if method=='cca' else {})},
      'comparison':comparison,'outputs':files,'date_parsing':session['date_parsing'],
      'native_file_hashes':{p.name:sha(p) for p in sorted(folder.iterdir()) if p.is_file()}}
    (artifacts/f'{key}-fit.json').write_text(json.dumps(record,indent=2)+'\n')
    print(f'{key}: retained {len(result)} returned datasets; forecast/CV/diagnostic control checks passed.')
    return datasets,record

def draw_map(ax,field,title,data_folder,*,predictor=False,vmin=-1,vmax=1,cmap='RdBu_r'):
    from matplotlib.collections import LineCollection
    from . import teaching as teach
    a=field.transpose('Y','X')
    image=ax.pcolormesh(a.X,a.Y,a,cmap=cmap,vmin=vmin,vmax=vmax,shading='nearest',rasterized=True)
    if predictor:
        geo=json.loads((data_folder/'predictor-boundaries.geojson').read_text());lines=[]
        def rings(g):
            if g['type']=='Polygon':return g['coordinates']
            if g['type']=='MultiPolygon':return [r for p in g['coordinates'] for r in p]
            if g['type']=='GeometryCollection':return [r for p in g['geometries'] for r in rings(p)]
            return []
        for f in geo['features']:lines.extend(rings(f['geometry']))
        ax.add_collection(LineCollection(lines,colors='#596966',linewidths=.4))
        ax.set(xlim=(85,155),ylim=(-20,20))
    else:
        teach.draw_boundaries(ax);ax.set(xlim=(94,142),ylim=(-12,8))
    ax.set(title=title,xlabel='Longitude',ylabel='Latitude');ax.set_aspect(1)
    return image

def forecast_score_figure(scores):
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(13,4.5),layout='constrained')
    for ax,metric in zip(axes,['rmse','mae','bias']):
        x=np.arange(2)
        for i,method in enumerate(METHODS):ax.bar(x+(i-1.5)*.19,scores[metric].sel(verification='forecast_2023',forecast_method=method),width=.18,label=method,color=COLORS[i])
        ax.set(xticks=x,xticklabels=SEASONS,ylabel=f'{metric.upper()} (mm)',title=f'2023 forecast {metric.upper()}')
        if metric=='bias':ax.axhline(0,color='#182e39',lw=.7)
        ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    axes[0].legend(frameon=False,fontsize=8)
    return fig

def scree_figure(results):
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(11,7),layout='constrained')
    for i,season in enumerate(SEASONS):
        for j,side in enumerate(['predictor','predictand']):
            ds=results[season]['cca'][0][f'{side}-diagnostics'];ax=axes[i,j]
            ax.bar(ds.spectrum_mode,ds.explained_variance_percent,color=['#147d92' if m<=3 else '#d5deda' for m in ds.spectrum_mode.values])
            ax.set(xlabel='EOF mode',ylabel='Variance (%)',title=f'{season} · {side} · first 3 retained',xlim=(.3,30.7))
    return fig

def pattern_figure(results,folder,season='OND',kind='cca',mode=1):
    import matplotlib.pyplot as plt
    fig=plt.figure(figsize=(12,7.8),layout='constrained');grid=fig.add_gridspec(2,2,height_ratios=[1.2,1])
    series=[]
    for col,side in enumerate(['predictor','predictand']):
        ds=results[season]['cca'][0][f'{side}-diagnostics'];a=ds[f'{kind}_correlation'].sel({f'{kind}_mode':mode})
        ax=fig.add_subplot(grid[0,col]);image=draw_map(ax,a,f'{season} · {side} · {kind.upper()} {mode}',folder,predictor=side=='predictor')
        s=ds[f'{kind}_score'].sel({f'{kind}_mode':mode});series.append((side,(s-s.mean('T'))/s.std('T',ddof=1)))
    fig.colorbar(image,ax=fig.axes,shrink=.65,label='Training field–score correlation')
    ax=fig.add_subplot(grid[1,:])
    for (side,s),color in zip(series,['#147d92','#c08325']):ax.plot(s['T'].dt.year,s,color=color,marker='o',ms=3,label=side)
    ax.axhline(0,color='#6b7280',lw=.5);ax.legend(frameon=False);ax.set(xlabel='Training year',ylabel='Standardized diagnostic score',title='Native training scores standardized separately to sample standard deviation 1')
    return fig

def cv_figure(yearly):
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(11,7),layout='constrained')
    for ax,season in zip(axes,SEASONS):
        for method,color in zip(METHODS,COLORS):ax.plot(yearly.training_year,yearly.rmse.sel(season=season,forecast_method=method),label=method,color=color,lw=1.4)
        ax.set(title=f'{season} · deterministic CV-year spatial RMSE',ylabel='RMSE (mm)',xlabel='Training target year');ax.grid(alpha=.15)
    axes[0].legend(frameon=False,ncols=4)
    return fig

def error_figure(comparison,folder):
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,3,figsize=(13,5.2),layout='constrained')
    vmax=float(comparison.absolute_error.sel(forecast_method=['Climatology','CCA','PCR']).max())
    for i,season in enumerate(SEASONS):
        for j,method in enumerate(['Climatology','CCA','PCR']):
            image=draw_map(axes[i,j],comparison.absolute_error.sel(season=season,forecast_method=method),f'{season} 2023 · {method}',folder,vmin=0,vmax=vmax,cmap='YlOrRd')
    fig.colorbar(image,ax=axes.ravel().tolist(),shrink=.65,label='Absolute seasonal rainfall error (mm)')
    return fig

def save_figure(fig,folder,name):
    import matplotlib.pyplot as plt
    fig.savefig(folder/f'{name}.png',dpi=160,bbox_inches='tight')
    return fig

def presentation_data(root,artifacts,results,scores,yearly,comparison,input_table,runtime,offline):
    """Serialize Python outputs for presentation; browser code performs no scoring."""
    def values(a):
        arr=np.asarray(a,dtype=float)
        return np.where(np.isfinite(arr),arr,None).tolist()
    panels={}
    for season in SEASONS:
        panels[season]={}
        for side in ['predictor','predictand']:
            ds=results[season]['cca'][0][f'{side}-diagnostics']
            item={'longitude':ds.X.values.tolist(),'latitude':ds.Y.values.tolist(),
              'variance':ds.explained_variance_percent.values.tolist(),'cumulative':ds.cumulative_variance_percent.values.tolist(),
              'years':ds['T'].dt.year.values.tolist()}
            for kind in ['eof','cca']:
                s=ds[f'{kind}_score'];z=(s-s.mean('T'))/s.std('T',ddof=1)
                item[kind]={'fields':values(ds[f'{kind}_correlation'].transpose(f'{kind}_mode','Y','X')),
                            'score':values(s.transpose(f'{kind}_mode','T')),'standardizedScore':values(z.transpose(f'{kind}_mode','T'))}
            panels[season][side]=item
        panels[season]['canonical']=results[season]['cca'][0]['canonical-correlations'].native_correlation.values.tolist()
    score_rows=[];year_rows=[]
    for season in SEASONS:
        for validation in ['forecast_2023','cross_validation']:
            for method in METHODS:
                row={'season':season,'verification':validation,'method':method}
                row.update({m:float(scores[m].sel(season=season,verification=validation,forecast_method=method)) for m in ['rmse','mae','bias']});score_rows.append(row)
        for method in METHODS:
            for year in yearly.training_year.values:
                row={'season':season,'method':method,'year':int(year)}
                row.update({m:float(yearly[m].sel(season=season,forecast_method=method,training_year=year)) for m in ['rmse','mae','bias']});year_rows.append(row)
    maps={}
    for season in SEASONS:
        maps[season]={'longitude':comparison.X.values.tolist(),'latitude':comparison.Y.values.tolist(),
           'rainfall':{m:values(comparison.forecast_rainfall.sel(season=season,forecast_method=m)) for m in METHODS},
           'absoluteError':{m:values(comparison.absolute_error.sel(season=season,forecast_method=m)) for m in METHODS},
           'signedError':{m:values(comparison.signed_error.sel(season=season,forecast_method=m)) for m in METHODS}}
    payload={'case':'fit-diagnose-2023','training':'1991–2020','seasons':SEASONS,'methods':METHODS,
       'inputs':input_table.to_dict(orient='records'),'scores':score_rows,'yearly':year_rows,'diagnostics':panels,'maps':maps,
       'notes':{'cv':'30 training target years; calibrated CV5; climatology excludes the same cyclic 5-year window; raw model is uncalibrated.',
         'patterns':'Full-training field–score correlations; separately standardized score series; not forecast skill.',
         'forecast':'Spatial errors over 3,240 shared land cells; 2023 is outside training but these are selected development examples.'}}
    p=artifacts/'interactive-data.json';p.write_text(json.dumps(payload,separators=(',',':'),allow_nan=False)+'\n')
    summary={'date':'2026-11-02','fits':[results[s][m][1] for s in SEASONS for m in ['cca','pcr']],
      'runtime':runtime,'offline_guard':dict(offline),'scores':score_rows,'interactive_data_sha256':sha(p),
      'netcdf_outputs':{p.name:sha(p) for p in sorted(artifacts.glob('*.nc'))},
      'limitations':['Illustrative development cases, fixed modes, no tuning.','No empirical probability reliability or physical attribution.','Absolute EOF amplitude normalization remains outside the lesson.']}
    assert offline=={'credential_reads':0,'remote_connections':0}
    (artifacts/'execution-manifest.json').write_text(json.dumps(summary,indent=2)+'\n')
    includes=root/'docs/_includes';includes.mkdir(exist_ok=True)
    text=[]
    for season in SEASONS:
        r={row['method']:row['rmse'] for row in score_rows if row['season']==season and row['verification']=='forecast_2023'}
        text.append(f"**{season} 2023:** national spatial RMSE was {r['Raw CFSv2']:.2f} mm for raw CFSv2, {r['Climatology']:.2f} mm for climatology, {r['CCA']:.2f} mm for CCA and {r['PCR']:.2f} mm for PCR.")
    (includes/'fitting-findings.qmd').write_text('\n\n'.join(text)+'\n')
    return summary
