"""Plot explicitly derived training correlations beside existing holdout errors."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
import numpy as np
import xarray as xr

ROOT=Path(__file__).resolve().parents[2]
AUDIT=ROOT/'research/audits/fitting-diagnostics'


def main():
    record=json.loads((AUDIT/'verification.json').read_text());assert record['result']=='PASS'
    boundaries=ROOT/'docs/data/boundaries'
    layers={p.stem:json.loads(p.read_text()) for p in boundaries.glob('*.geojson')}
    def shapes(ax,layer,fill=False):
        for feature in layers[layer]['features']:
            g=feature['geometry'];polys=g['coordinates'] if g['type']=='MultiPolygon' else [g['coordinates']]
            for poly in polys:
                for ring in poly:
                    ax.add_patch(Polygon(ring,closed=True,facecolor='#e3e5e4' if fill else 'none',edgecolor='#5c6663',linewidth=.35,zorder=3 if fill else 5))
    fig,axes=plt.subplots(2,3,figsize=(15,6.8),gridspec_kw={'width_ratios':[1.2,1.2,.9]},layout='constrained')
    for row,season in enumerate(['OND','JJA']):
        path=AUDIT/'outputs'/f'{season}_cca_1991_2020_predictand_diagnostics.nc'
        with xr.open_dataset(path) as source:ds=source.load()
        for col,(name,dim,title) in enumerate([('eof_correlation','eof_mode','Y EOF 1'),('cca_correlation','cca_mode','Y CCA 1')]):
            ax=axes[row,col];a=ds[name].sel({dim:1})
            mesh=ax.pcolormesh(a.X,a.Y,a,vmin=-1,vmax=1,cmap='RdBu_r',shading='nearest',rasterized=True,zorder=2)
            shapes(ax,'neighbours',True)
            for layer in ['indonesia','provinces']:
                if layer in layers:shapes(ax,layer)
            ax.set(xlim=(94,142),ylim=(-12,8),title=f'{season}: {title} · training 1991–2020',xlabel='Longitude',ylabel='Latitude')
            ax.set_aspect(1/np.cos(np.deg2rad(-2)))
        ax=axes[row,2];values=record['comparison_2023_rmse_mm'][season]
        order=['raw_cfsv2','climatology_1991_2020','cca_1991_2020','pcr_1991_2020']
        bars=ax.barh(['Raw','Climatology','CCA','PCR'],[values[v] for v in order],color=['#9ca3a0','#ba9c6d','#32736e','#bb674f'])
        ax.invert_yaxis();ax.set(xlim=(0,440),xlabel='Spatial RMSE (mm)',title=f'{season} 2023 · saved forecast errors')
        for bar,v in zip(bars,[values[v] for v in order]):ax.text(v+5,bar.get_y()+bar.get_height()/2,f'{v:.2f}',va='center',fontsize=9)
        ax.spines[['top','right']].set_visible(False)
    fig.colorbar(mesh,ax=axes[:,:2].ravel().tolist(),orientation='horizontal',fraction=.045,pad=.08,label='Derived Pearson correlation with training diagnostic score (not forecast skill)')
    fig.suptitle('Training patterns and forecast errors answer different questions',fontsize=16)
    fig.savefig(AUDIT/'outputs/training-patterns-and-holdout-errors.png',dpi=160)
    plt.close(fig)
    print('Saved audit-only training-patterns-and-holdout-errors.png; no new fits.')


if __name__=='__main__':main()
