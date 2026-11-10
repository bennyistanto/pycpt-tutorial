"""Export verified notebook results for browser presentation; never recalculate fits."""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
import pandas as pd
import xarray as xr
from matplotlib import colormaps
from matplotlib.colors import to_hex

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'docs/assets/story'
AUDIT=ROOT/'temp/audits/interactive-story'
VARIANTS=['raw_cfsv2','climatology_1983_2010','climatology_1991_2020','cca_1983_2010','cca_1991_2020','pcr_1983_2010','pcr_1991_2020']
SEASONS='DJF JFM FMA MAM AMJ MJJ JJA JAS ASO SON OND NDJ'.split()


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    with xr.open_dataset(p) as ds: return ds.load()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-baseline',action='store_true',help='After re-verifying an intentional notebook/science update, preserve the prior baseline and start a new snapshot.')
    args=parser.parse_args()
    DEST.mkdir(parents=True,exist_ok=True); AUDIT.mkdir(parents=True,exist_ok=True)
    protected=[ROOT/'docs/notebooks/indonesia-seasons-2023.ipynb',
               *sorted((ROOT/'docs/data').rglob('*.nc')),
               *sorted((ROOT/'docs/assets/seasonal-2023').glob('*'))]
    baseline_path=AUDIT/'baseline.json'
    if baseline_path.exists() and args.refresh_baseline:
        previous=baseline_path.read_bytes()
        (AUDIT/f'baseline-{hashlib.sha256(previous).hexdigest()[:12]}.json').write_bytes(previous)
        baseline_path.unlink()
    if baseline_path.exists():
        baseline=json.loads(baseline_path.read_text())
        assert all(sha(ROOT/p)==h for p,h in baseline.items()),'A protected notebook/scientific artifact changed'
    else:
        baseline={str(p.relative_to(ROOT)):sha(p) for p in protected if p.is_file()}
        baseline_path.write_text(json.dumps(baseline,indent=2)+'\n')
    sources={}
    def load(name):
        p=ROOT/name; sources[name]=sha(p); return read(p)
    fields=load('docs/data/indonesia-seasons-2023.nc')
    scores=load('docs/assets/seasonal-2023/verification-2023.nc')
    context=load('docs/data/verification-context-2021-2024.nc')
    regions=load('docs/data/regions/province-weights.nc')
    regional=load('docs/assets/seasonal-2023/province-verification-2023.nc')
    pooled=load('docs/data/regions/province-context-pooled.nc')
    def records(ds,regional=False,context=False):
        result=[]
        for season in SEASONS:
            for region in (list(ds.region.values) if regional else [None]):
                selected=ds.sel(season=season,**({'region':region} if regional else {}))
                for variant in VARIANTS:
                    row={'season':season,'variant':variant}
                    if regional: row['region']=str(region)
                    for metric in ['rmse','mae','bias']:
                        key='pooled_'+metric if context else metric
                        a=selected[key].sel(forecast_variant=variant)
                        if 'evaluation_set' in a.dims: a=a.sel(evaluation_set='all_four_years')
                        row[metric]=float(a)
                    if variant.startswith(('cca','pcr')):
                        period=variant[4:]
                        for label,reference in [('Climatology','climatology_'+period),('Raw','raw_cfsv2')]:
                            base=selected['pooled_rmse' if context else 'rmse'].sel(forecast_variant=reference)
                            if 'evaluation_set' in base.dims: base=base.sel(evaluation_set='all_four_years')
                            row['gain'+label]=100*(1-row['rmse']/float(base))
                    result.append(row)
        return result
    support=[{'name':str(name),'isProvince':bool(regions.is_province.sel(region=name)),
              'cells':int(regions.contributing_cells.sel(region=name)),
              'weightPercent':100*float(regions.region_mass_fraction.sel(region=name)),
              'largestCellPercent':100*float(regions.largest_cell_weight_fraction.sel(region=name))}
             for name in regions.region.values]
    calendar=[{'season':s,'start':pd.Timestamp(fields.target_start.sel(season=s).item()).strftime('%Y-%m-%d'),
               'end':pd.Timestamp(fields.target_end.sel(season=s).item()).strftime('%Y-%m-%d'),
               'issue':pd.Timestamp(fields.initialization.sel(season=s).item()).strftime('%Y-%m-%d'),
               'sourceYear':int(fields.source_season_year.sel(season=s))} for s in SEASONS]
    data={'seasons':SEASONS,'variants':VARIANTS,'national':records(scores),'context':records(context,context=True),
          'regional':records(regional,regional=True),'regionalContext':records(pooled,regional=True),
          'support':support,'calendar':calendar,
          'palettes':{name:[to_hex(colormaps[name](i/256)) for i in range(257)] for name in ['YlGnBu','BrBG']},
          'note':'Unrounded verified scores. Browser presentation only; province counts/weights are not independent validation samples.'}
    (DEST/'metrics.json').write_text(json.dumps(data,separators=(',',':'),allow_nan=False)+'\n')
    mask=fields.evaluation_mask.values.astype(bool)
    rows,cols=np.nonzero(mask)
    cells=[]
    for r,c in zip(rows,cols):
        w=regions.region_weight.values[:,r,c]; total=w.sum()
        shares=[[str(regions.region.values[i]),float(w[i]/total)] for i in np.flatnonzero(w)]
        cells.append({'lon':float(fields.X[c]),'lat':float(fields.Y[r]),'row':int(r),'col':int(c),'shares':shares})
    map_fields={}; limits={}
    for season in SEASONS:
        ds=fields.sel(season=season)
        map_fields[season]={'observed':ds.observed_rainfall.values[mask].tolist()}
        for variant in VARIANTS: map_fields[season][variant]=ds.forecast_rainfall.sel(forecast_variant=variant).values[mask].tolist()
        limits[season]={}
        for period in ['1983_2010','1991_2020']:
            shown=['observed','raw_cfsv2','climatology_'+period,'cca_'+period,'pcr_'+period]
            limits[season][period]=float(np.quantile(np.concatenate([map_fields[season][k] for k in shown]),.99))
    (DEST/'fields.json').write_text(json.dumps({'cells':cells,'fields':map_fields,'rainLimits':limits,
            'extent':[94,-12,142,7],'grid':[76,192],'note':'Exact saved0.25degree values; display colours saturate, hover values do not.'},separators=(',',':'),allow_nan=False)+'\n')
    outputs={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in [DEST/'metrics.json',DEST/'fields.json']}
    record={'date':'2026-11-01','sources':sources,'outputs':outputs,'preserved_artifacts':len(baseline),
            'map_cells':len(cells),'numeric_rounding':'None in JSON; labels round for readability only.',
            'method':'Serialize existing metrics and fields; gain percentages use stored RMSE; no new fits or spatial weights.'}
    (DEST/'provenance.json').write_text(json.dumps(record,indent=2)+'\n')
    (AUDIT/'export.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))


if __name__=='__main__': main()
