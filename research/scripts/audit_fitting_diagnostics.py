"""Recover and check retained OND/JJA diagnostics without refitting any model."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
import pandas as pd
import xarray as xr
from cptio import open_cptdataset

ROOT=Path(__file__).resolve().parents[2]
NATIVE=Path('/home/bennyistanto/CPT/cases/indonesia-all-seasons-2021-2024-025deg')
AUDIT=ROOT/'research/audits/fitting-diagnostics'
sys.path.insert(0,str(ROOT))
from pycpt_tutorial.export import save_netcdf


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    with xr.open_dataset(p) as ds: return ds.load()
def field(p):
    ds=open_cptdataset(str(p));assert len(ds.data_vars)==1
    return ds[next(iter(ds.data_vars))]
def scores(folder,side,kind):
    a=field(folder/f'{side}_{kind}_timeseries.txt')
    return a.rename({'index':kind+'_mode'}).transpose('T',kind+'_mode')
def loadings(folder,side,kind):
    a=field(folder/f'{side}_{kind}_spatial_loadings.txt')
    return a.rename({'Mode':kind+'_mode'}).transpose(kind+'_mode','Y','X')
def correlations(data,score,dim):
    # Correlation maps are derived explicitly; the native exported weights are not correlations.
    np.testing.assert_array_equal(data['T'],score['T'])
    centred=data-data.mean('T');s=score-score.mean('T')
    return (centred*s).sum('T')/np.sqrt((centred**2).sum('T')*(s**2).sum('T'))

def valid_weights(weights,data):
    valid=data.notnull().all('T')
    # These native files omit cpt:missing in the header; validate the sentinel
    # against the separately stored original-input mask before decoding it.
    outside=weights.values[:,~valid.values]
    assert outside.size==0 or np.all(outside==-999)
    assert np.isfinite(weights.values[:,valid.values]).all()
    decoded=weights.where(valid)
    decoded.attrs['missing_value_handling']='-999 outside original complete training-input support decoded to NaN; native file unchanged'
    return decoded


def main():
    AUDIT.mkdir(exist_ok=True);out=AUDIT/'outputs';out.mkdir(exist_ok=True)
    inv=json.loads((AUDIT/'inventory.json').read_text())
    benchmark=ROOT/'research/cases/indonesia-all-seasons-2021-2024-025deg'
    protected={str(p):sha(p) for p in (benchmark/'outputs').iterdir() if p.is_file()}
    protected[str(ROOT/'docs/notebooks/indonesia-seasons-2023.ipynb')]=sha(ROOT/'docs/notebooks/indonesia-seasons-2023.ipynb')
    protected[str(ROOT/'docs/downloads/indonesia-seasons-2023-kit.zip')]=sha(ROOT/'docs/downloads/indonesia-seasons-2023-kit.zip')
    result={};recovered=[]
    for key,entry in inv.items():
        folder=Path(entry['native_output_directory'])
        for item in entry['files']: assert sha(folder/item['name'])==item['sha256']
        season=entry['record']['season'];method=entry['record']['method']
        fitting=entry['record'];assert fitting['training_samples']==30
        for name,value in fitting['input_sha256'].items(): assert sha(NATIVE/season/name)==value
        for name,value in fitting['outputs_sha256'].items():
            assert sha(NATIVE/'outputs'/name)==value
            assert sha(benchmark/'outputs'/name)==value
        xs=field(folder/'original_predictor');ys=field(folder/'original_predictand')
        assert xs.sizes['T']==ys.sizes['T']==30
        assert np.array_equal(xs['T'].dt.year,np.arange(1991,2021))
        np.testing.assert_array_equal(xs['T'],ys['T'])
        info={'season':season,'method':method,'source_files_hash_verified':len(entry['files']),
              'training_years':[1991,2020],'x_grid_cells':xs.sizes['Y']*xs.sizes['X'],
              'y_valid_cells':int(ys.notnull().all('T').sum()),'sides':{},
              'wrapper_source_sha256':sha(Path(entry['wrapper_source'])),
              'session_log_sha256':sha(NATIVE/f'cpt-{key}.log'),
              'commands_sha256':sha(NATIVE/f'cpt-{key}-commands.txt')}
        side_data={}
        for side,data in [('predictor',xs)]+([('predictand',ys)] if method=='cca' else []):
            pc=scores(folder,side,'eof');weights=loadings(folder,side,'eof')
            assert pc.sizes['T']==30 and pc.sizes['eof_mode']==weights.sizes['eof_mode']==3
            # Native mode-header parsing is zero-based in this cptio; use explicit file/table labels.
            weights=weights.assign_coords(eof_mode=pc.eof_mode)
            weights=valid_weights(weights,data)
            assert np.isfinite(pc).all()
            spec=np.genfromtxt(folder/f'{side}_explained_variance.txt',skip_header=3,delimiter='\t')
            assert spec.shape==(30,4) and np.isfinite(spec).all()
            np.testing.assert_array_equal(spec[:,0],np.arange(1,31))
            assert np.all(spec[:,1:]>=-1e-6)
            np.testing.assert_allclose(np.cumsum(spec[:,2]),spec[:,3],atol=2e-5,rtol=0)
            np.testing.assert_allclose(spec[-1,3],100,atol=2e-5,rtol=0)
            np.testing.assert_allclose(spec[:,1]/spec[:,1].sum()*100,spec[:,2],atol=2e-5,rtol=0)
            # Independent EOF check using the *printed* training inputs actually sent to CPT.
            a=data.transpose('T','Y','X').values
            mask=np.isfinite(a).all(axis=0);mat=a[:,mask]
            z=(mat-mat.mean(axis=0))/mat.std(axis=0,ddof=1)
            latitude=np.broadcast_to(data.Y.values[:,None],mask.shape)[mask]
            z*=np.sqrt(np.cos(np.deg2rad(latitude)))
            u,s,v=np.linalg.svd(z,full_matrices=False)
            eigen=s*s/29
            eigen_gap=float(np.max(abs(eigen-spec[:,1])))
            variance_gap=float(np.max(abs(eigen/eigen.sum()*100-spec[:,2])))
            score_r=[float(abs(np.corrcoef((u*s)[:,i],pc.values[:,i])[0,1])) for i in range(3)]
            # Report precision gaps explicitly; no sign matching is written into native arrays.
            assert min(score_r)>0.99999,(key,side,score_r)
            np.testing.assert_allclose(eigen,spec[:,1],atol=.002,rtol=2e-5)
            np.testing.assert_allclose(eigen/eigen.sum()*100,spec[:,2],atol=2e-5,rtol=0)
            corr=correlations(data,pc,'eof_mode').transpose('eof_mode','Y','X')
            assert int(corr.notnull().all('eof_mode').sum())==int(mask.sum())
            ds=xr.Dataset({'eof_native_weight':weights,'eof_score':pc,'eof_correlation':corr,
                'eigenvalue':('spectrum_mode',spec[:,1]),'explained_variance_percent':('spectrum_mode',spec[:,2]),
                'cumulative_variance_percent':('spectrum_mode',spec[:,3])},coords={'spectrum_mode':np.arange(1,31)})
            ds.eof_native_weight.attrs['interpretation']='Native exported weights; not correlation coefficients or rainfall forecasts'
            ds.eof_correlation.attrs['interpretation']='Pearson correlation of original printed training input and full-training diagnostic score'
            ds.eof_correlation.attrs['units']='1'
            if method=='cca':
                cs=scores(folder,side,'cca');cw=valid_weights(loadings(folder,side,'cca').assign_coords(cca_mode=cs.cca_mode),data)
                assert cs.sizes['T']==30 and cs.sizes['cca_mode']==cw.sizes['cca_mode']==2
                ds['cca_score']=cs;ds['cca_native_weight']=cw
                ds['cca_correlation']=correlations(data,cs,'cca_mode').transpose('cca_mode','Y','X')
                ds.cca_native_weight.attrs['interpretation']='Native exported CCA weights; not correlation coefficients or rainfall forecasts'
                ds.cca_correlation.attrs['interpretation']='Pearson correlation of original printed training input and full-training CCA score'
                ds.cca_correlation.attrs['units']='1'
            ds.attrs.update(season=season,method=method,side=side,training_period='1991-2020',
                validation='Training-period model diagnostics; not per-fold EOFs or independent skill.',
                source_directory=str(folder),normalization='Independent EOF reconstruction: ddof=1 standardized anomalies, sqrt(cos(latitude)) weighting.',
                provenance='research/audits/fitting-diagnostics/inventory.json')
            path=out/f'{key}_{side}_diagnostics.nc'
            save_netcdf(ds,path,overwrite=True)
            recovered.append({'file':str(path.relative_to(ROOT)),'sha256':sha(path),'variables':list(ds.data_vars)})
            side_data[side]=ds
            info['sides'][side]={'retained_eof_variance_percent':float(spec[2,3]),
                'first_three_eof_variance_percent':spec[:3,2].tolist(),'independent_eigenvalue_max_gap':eigen_gap,
                'independent_variance_percent_max_gap':variance_gap,
                'independent_pc_absolute_correlations':score_r,'finite_input_cells':int(mask.sum()),
                'decoded_missing_weight_values':int(weights.isnull().sum()),
                'native_weight_range':[float(weights.min()),float(weights.max())],
                'derived_correlation_range':[float(corr.min()),float(corr.max())]}
        if method=='cca':
            native_r=np.genfromtxt(folder/'cca_canonical_correlation.txt',skip_header=3,delimiter='\t')
            r=np.array([np.corrcoef(side_data['predictor'].cca_score.values[:,i],side_data['predictand'].cca_score.values[:,i])[0,1] for i in range(2)])
            np.testing.assert_allclose(native_r[:,1],r,atol=2e-6,rtol=0)
            info['canonical_correlations']=native_r[:,1].tolist();info['score_correlation_max_gap']=float(abs(native_r[:,1]-r).max())
        # Verify these saved X diagnostics coincide for the two fixed-three-mode methods.
        if method=='pcr':
            for suffix in ['eof_spatial_loadings','eof_timeseries','explained_variance']:
                assert sha(folder/f'predictor_{suffix}.txt')==sha(folder.with_name(f'cpt-{season}_cca_1991_2020')/f'predictor_{suffix}.txt')
            info['x_eof_files_identical_to_cca']=True
        result[key]=info
    # Original case study comparison, independently read from existing teaching scores.
    score=read(ROOT/'docs/assets/seasonal-2023/verification-2023.nc')
    comparisons={season:{variant:float(score.rmse.sel(season=season,forecast_variant=variant)) for variant in ['raw_cfsv2','climatology_1991_2020','cca_1991_2020','pcr_1991_2020']} for season in ['OND','JJA']}
    for path,value in protected.items(): assert sha(Path(path))==value
    report={'date':'2026-11-02','result':'PASS','fits':result,'comparison_2023_rmse_mm':comparisons,
        'recovered_outputs':recovered,'new_fits':0,'protected_files_unchanged':len(protected),
        'audit_script_sha256':sha(Path(__file__)),
        'numeric_tolerances':{'spectrum_cumulative_percent_atol':2e-5,'independent_eigenvalue_atol':.002,
            'independent_eigenvalue_rtol':2e-5,'independent_variance_percent_atol':2e-5,'canonical_correlation_atol':2e-6},
        'checks':'Raw hashes, fitting input/output hashes, mode/time counts, variance arithmetic, independent full-training weighted standardized SVD, CCA score correlations, CCA/PCR X equality, existing case preservation.',
        'scope':'Saved full-training diagnostics recovered; no physical attribution, optimized setting, per-fold pattern or new independent skill claim.'}
    (AUDIT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['recovered_outputs']},indent=2))


if __name__=='__main__':main()
