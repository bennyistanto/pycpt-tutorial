"""Check every interactive number against immutable scientific outputs."""
from pathlib import Path
from datetime import date
import hashlib
import json
import sys
import numpy as np
import xarray as xr

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from verify_tutorial import Page


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    with xr.open_dataset(p) as ds:return ds.load()


def main():
    folder=ROOT/'docs/assets/story'; audit=ROOT/'research/audits/interactive-story'
    record=json.loads((folder/'provenance.json').read_text())
    baseline=json.loads((audit/'baseline.json').read_text())
    assert all(sha(ROOT/p)==h for p,h in baseline.items())
    assert all(sha(ROOT/p)==h for p,h in record['sources'].items())
    assert all(sha(folder/p)==r['sha256'] for p,r in record['outputs'].items())
    for name in ['story.js','metrics.json','fields.json','provenance.json']:
        assert sha(folder/name)==sha(ROOT/'docs/_book/assets/story'/name),name
    for name in ['indonesia','provinces','neighbours']:
        assert sha(ROOT/f'docs/data/boundaries/{name}.geojson')==sha(ROOT/f'docs/_book/data/boundaries/{name}.geojson')
    data=json.loads((folder/'metrics.json').read_text()); fields=json.loads((folder/'fields.json').read_text())
    paths={'national':'docs/assets/seasonal-2023/verification-2023.nc',
           'context':'docs/data/verification-context-2021-2024.nc',
           'regional':'docs/assets/seasonal-2023/province-verification-2023.nc',
           'regionalContext':'docs/data/regions/province-context-pooled.nc'}
    numbers=0
    for key,path in paths.items():
        source=read(ROOT/path)
        expected_rows=12*7*(source.sizes['region'] if 'region' in source.dims else 1)
        assert len(data[key])==expected_rows
        for r in data[key]:
            selection={'season':r['season'],'forecast_variant':r['variant']}
            if 'region' in r:selection['region']=r['region']
            ds=source.sel(**selection)
            if key=='context':ds=ds.sel(evaluation_set='all_four_years')
            for metric in ['rmse','mae','bias']:
                assert r[metric]==float(ds[('pooled_' if key=='context' else '')+metric]);numbers+=1
            if 'gainClimatology' in r:
                period=r['variant'][4:]
                base=source.sel(season=r['season'],forecast_variant='climatology_'+period,**({'region':r['region']} if 'region'in r else {}))
                if key=='context':base=base.sel(evaluation_set='all_four_years')
                rmse=float(base['pooled_rmse' if key=='context' else 'rmse'])
                assert r['gainClimatology']==100*(1-r['rmse']/rmse)
    source=read(ROOT/'docs/data/indonesia-seasons-2023.nc'); mask=source.evaluation_mask.values.astype(bool)
    assert len(fields['cells'])==3240
    rows,cols=np.nonzero(mask)
    np.testing.assert_array_equal([c['row'] for c in fields['cells']],rows)
    np.testing.assert_array_equal([c['col'] for c in fields['cells']],cols)
    np.testing.assert_array_equal([c['lon'] for c in fields['cells']],source.X.values[cols])
    np.testing.assert_array_equal([c['lat'] for c in fields['cells']],source.Y.values[rows])
    map_numbers=0
    for s in data['seasons']:
        ds=source.sel(season=s)
        np.testing.assert_array_equal(fields['fields'][s]['observed'],ds.observed_rainfall.values[mask]);map_numbers+=3240
        for v in data['variants']:
            np.testing.assert_array_equal(fields['fields'][s][v],ds.forecast_rainfall.sel(forecast_variant=v).values[mask]);map_numbers+=3240
    regions=read(ROOT/'docs/data/regions/province-weights.nc')
    for c in fields['cells']:
        w=regions.region_weight.values[:,c['row'],c['col']]; total=w.sum()
        expected=[[str(regions.region.values[i]),float(w[i]/total)] for i in np.flatnonzero(w)]
        assert c['shares']==expected
    html=(ROOT/'docs/_book/chapters/indonesia-seasons-2023.html').read_text()
    page=Page();page.feed(html)
    ids=[f'interactive-{key}' for key in ['national','gains','rainfall','error-maps','province','province-context','sensitivity','context']]
    assert all(i in page.ids for i in ids)
    assert 'quarto-ojs' in html
    assert all(not link.startswith(('https://','http://')) for link in page.scripts)
    assert len([im for im in page.images if 'story-fallback'in im.get('class','')])==8
    assert 'quarto-embed-nb-cell' not in html
    result={'date':date.today().isoformat(),'score_values_exactly_matched':numbers,'map_values_exactly_matched':map_numbers,
            'map_weight_shares_verified':3240,'protected_notebook_scientific_artifacts_unchanged':len(baseline),
            'interactive_story_panels':len(ids),'static_fallback_images':8,'published_runtime_assets_match_source':7,'required_external_scripts':[],
            'notebook_execution':'No canonical execution performed by this verifier; current preservation baseline matched.',
            'code_sha256':{p:sha(ROOT/p) for p in ['docs/assets/story/story.js','scripts/export_story_interactives.py','scripts/render_tutorial.py']}}
    (audit/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
