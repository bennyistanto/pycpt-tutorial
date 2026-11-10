"""Independent NumPy audit of province weights, scores, calendars and baselines."""
from pathlib import Path
import hashlib
import json
import numpy as np
import xarray as xr

ROOT=Path(__file__).resolve().parents[1]
CASE=ROOT/'research/cases/indonesia-all-seasons-2021-2024-025deg'
DATA=ROOT/'docs/data/regions'
OUT=ROOT/'docs/assets/seasonal-2023'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def read(path):
    with xr.open_dataset(path) as ds: return ds.load()


def main():
    info=json.loads((DATA/'provenance.json').read_text())
    for name,record in info['outputs'].items(): assert sha(DATA/name)==record['sha256'],name
    for name,expected in info['source_files'].items():
        assert sha(Path(name) if name.startswith('/') else ROOT/name)==expected,name
    baseline=json.loads((ROOT/'research/audits/regional-2023/baseline.json').read_text())
    assert all(sha(ROOT/p)==h for p,h in baseline.items())
    weights=read(DATA/'province-weights.nc')
    native=read(DATA/'native-membership.nc')
    main=read(ROOT/'docs/data/indonesia-seasons-2023.nc')
    label=native.original_province_index.values.astype(int)
    row=native.coarse_row.values.astype(int); col=native.coarse_col.values.astype(int)
    assert native.sizes['point']==61190
    np.testing.assert_array_equal(row,np.floor((7-native.latitude.values)/.25).astype(int))
    np.testing.assert_array_equal(col,np.floor((native.longitude.values-94)/.25).astype(int))
    np.testing.assert_allclose(native.native_weight,np.cos(np.deg2rad(native.latitude)),atol=0,rtol=0)
    assert np.all(label[native.membership_count.values==0]==38)
    assert np.all(label[native.membership_count.values>1]==39)
    native_w=native.native_weight.values
    rebuilt=np.bincount(label*76*192+row*192+col,weights=native_w,minlength=40*76*192).reshape(40,76,192)
    selected=rebuilt[info['region_order_original_indices']]
    np.testing.assert_allclose(selected,weights.region_weight,atol=1e-12,rtol=0)
    np.testing.assert_allclose(selected.sum(0),main.evaluation_weight,atol=1e-12,rtol=0)
    np.testing.assert_array_equal((selected>0).sum((1,2)),weights.contributing_cells)
    np.testing.assert_allclose(selected.max((1,2))/selected.sum((1,2)),weights.largest_cell_weight_fraction,atol=1e-14,rtol=0)
    mask=main.evaluation_mask.values.astype(bool)
    w=selected[:,mask]; mass=w.sum(1); norm=w/mass[:,None]
    share=mass/mass.sum()
    def calculate(forecast,observed):
        err=forecast-observed[...,None,:]
        assert np.isfinite(err).all()
        return {'mse':np.einsum('...k,rk->...r',err**2,norm),
                'mae':np.einsum('...k,rk->...r',np.abs(err),norm),
                'bias':np.einsum('...k,rk->...r',err,norm)}
    f=main.forecast_rainfall.transpose('season','forecast_variant','Y','X').values[:,:,mask]
    y=main.observed_rainfall.transpose('season','Y','X').values[:,mask]
    independent=calculate(f,y); independent['rmse']=np.sqrt(independent['mse'])
    saved=read(OUT/'province-verification-2023.nc')
    gaps={}
    for key,array in independent.items():
        actual=saved[key].transpose('season','forecast_variant','region').values
        np.testing.assert_allclose(array,actual,atol=1e-6 if key=='mse' else 1e-8,rtol=0)
        gaps[key]=float(abs(array-actual).max())
    annual=read(DATA/'province-context-annual.nc')
    pooled=read(DATA/'province-context-pooled.nc')
    national=read(CASE/'outputs/verification_scores.nc')
    context=[]
    for season in main.season.values:
        field=read(CASE/'outputs'/f'{season}_forecast_comparison.nc')
        np.testing.assert_array_equal(field.season_year,[2021,2022,2023,2024])
        a=calculate(field.forecast_rainfall.transpose('T','forecast_variant','Y','X').values[:,:,mask],
                    field.observed_rainfall.transpose('T','Y','X').values[:,mask])
        a['rmse']=np.sqrt(a['mse']); context.append(a)
        for key,array in a.items():
            actual=annual[key].sel(season=season).transpose('season_year','forecast_variant','region').values
            np.testing.assert_allclose(array,actual,atol=1e-6 if key=='mse' else 1e-8,rtol=0)
        for key in ('rmse','mae','bias'):
            combined=np.sqrt(a['mse']@share) if key=='rmse' else a[key]@share
            expected=national[key].sel(season=season).transpose('season_year','forecast_variant').values
            np.testing.assert_allclose(combined,expected,atol=1e-8,rtol=0)
        source_year=int(main.source_season_year.sel(season=season))
        for key,array in independent.items():
            np.testing.assert_allclose(array[list(main.season.values).index(season)],a[key][source_year-2021],atol=1e-6 if key=='mse' else 1e-8,rtol=0)
    expected_pooled={}
    for key in ('mse','mae','bias'):
        expected_pooled[key]=np.stack([c[key].mean(0) for c in context])
    expected_pooled['rmse']=np.sqrt(expected_pooled['mse'])
    for key,array in expected_pooled.items():
        np.testing.assert_allclose(array,pooled[key].transpose('season','forecast_variant','region'),atol=1e-6 if key=='mse' else 1e-8,rtol=0)
    summary=json.loads((OUT/'regional-findings.json').read_text())
    variants=list(main.forecast_variant.values); base=variants.index('climatology_1991_2020')
    provinces=weights.is_province.values.astype(bool)
    assert provinces.sum()==38
    for context_name, values in [('2023',independent['rmse']),('Four-year',expected_pooled['rmse'])]:
        for method in ('CCA','PCR'):
            ix=variants.index(method.lower()+'_1991_2020')
            counts=(values[:,ix,provinces]<values[:,base,provinces]).sum(1)
            expected=summary['province_counts'][context_name+' '+method]
            assert counts.tolist()==[expected[str(s)] for s in main.season.values]
    record={'date':'2026-11-01','provinces':38,'residual_categories':int((~provinces).sum()),
            'native_points':len(label),'unassigned_points':int((label==38).sum()),'overlap_points':int((label==39).sum()),
            'unassigned_country_weight_percent':float(100*native_w[label==38].sum()/native_w.sum()),
            'native_weight_reconstruction':'PASS <=1e-12','province_plus_residual_recombination':'PASS <=1e-8mm',
            'independent_main_score_max_gap':gaps,'annual_region_variant_season_comparisons':int(12*4*7*len(mass)),
            'all_seasons_all_years_all_variants_checked':True,'pooled_mse_before_sqrt_checked':True,
            'original_tutorial_netcdfs_unchanged':len(baseline),'regional_source_files_hash_verified':len(info['source_files']),
            'minimum_province_contributing_coarse_cells':int(weights.contributing_cells.values[provinces].min()),
            'maximum_province_single_cell_share_percent':float(100*weights.largest_cell_weight_fraction.values[provinces].max()),
            'code_sha256':{name:sha(ROOT/name) for name in ['scripts/prepare_regional_verification.py','scripts/verify_regional_verification.py','pycpt_tutorial/regions.py']}}
    (ROOT/'research/audits/regional-2023/verification.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))


if __name__=='__main__': main()
