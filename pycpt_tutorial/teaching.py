"""Presentation helpers for the executed seasonal tutorial.

Metrics and scientific comparisons remain visible in the notebook. These helpers
only verify input hashes, style plots and save their display artifacts.
"""
from pathlib import Path
from functools import lru_cache
import hashlib
import json

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import TwoSlopeNorm
from matplotlib.collections import LineCollection
from matplotlib.patches import PathPatch
from matplotlib.path import Path as PlotPath

SEASONS="DJF JFM FMA MAM AMJ MJJ JJA JAS ASO SON OND NDJ".split()
MAIN=["raw_cfsv2","climatology_1991_2020","cca_1991_2020","pcr_1991_2020"]
LABELS={"raw_cfsv2":"Raw CFSv2","climatology_1991_2020":"Climatology","cca_1991_2020":"CCA","pcr_1991_2020":"PCR",
        "climatology_1983_2010":"Climatology · older","cca_1983_2010":"CCA · older","pcr_1983_2010":"PCR · older"}
COLORS={"Raw CFSv2":"#9b7164","Climatology":"#6b7280","CCA":"#147d92","PCR":"#c08325"}

def style():
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.titlesize":11,"axes.labelcolor":"#374151","text.color":"#182b35",
                         "axes.edgecolor":"#b8c1c6","axes.spines.top":False,"axes.spines.right":False,"figure.facecolor":"white",
                         "savefig.facecolor":"white","axes.titlelocation":"left","figure.dpi":110,"savefig.dpi":180})

def verify_bundle(folder):
    record=json.loads((folder/"provenance.json").read_text())
    for name,info in record["outputs"].items():
        assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==info["sha256"],name
    return record

def save_figure(fig,folder,name):
    folder.mkdir(parents=True,exist_ok=True)
    fig.savefig(folder/f"{name}.png",bbox_inches="tight")
    return fig

def rmse_overview(frame):
    table=frame.reindex(SEASONS)[list(COLORS)]
    fig,ax=plt.subplots(figsize=(10,5.2),layout="constrained")
    data=table.to_numpy()
    image=ax.imshow(data.T,aspect="auto",cmap="YlGnBu",vmin=0,vmax=float(data.max())*1.03)
    ax.set_xticks(range(12),SEASONS); ax.set_yticks(range(4),table.columns)
    for s in range(12):
        for m in range(4):
            ax.text(s,m,f"{data[s,m]:.0f}",ha="center",va="center",fontsize=10,color="white" if data[s,m]>data.max()*.53 else "#102a35",
                    fontweight="bold" if m==np.argmin(data[s]) else "normal")
    ax.set_title("Seasonal forecast error across Indonesia",fontweight="bold",pad=16)
    ax.set_xlabel("Target season centred on 2023 · bold numbers mark the lowest error")
    fig.colorbar(image,ax=ax,shrink=.62,pad=.02,label="Area-weighted spatial RMSE (mm)")
    return fig

def gain_bars(gains):
    fig,ax=plt.subplots(figsize=(10,3.8),layout="constrained")
    x=np.arange(12)
    for offset,method in ((-.18,"CCA"),(.18,"PCR")):
        ax.bar(x+offset,gains[method],width=.34,color=COLORS[method],label=method)
    ax.axhline(0,color="#182b35",linewidth=.8)
    ax.set_xticks(x,SEASONS); ax.set_ylabel("RMSE reduction relative to climatology (%)")
    ax.set_title("Does calibration improve on a simple rainfall average?",fontweight="bold",pad=12)
    ax.legend(frameon=False,ncols=2); ax.grid(axis="y",alpha=.15); ax.set_axisbelow(True)
    return fig

@lru_cache(maxsize=1)
def boundary_layers():
    folder = Path(__file__).resolve().parents[1] / "docs/data/boundaries"
    provenance = json.loads((folder / "provenance.json").read_text())
    layers = {}
    for name, info in provenance["outputs"].items():
        path = folder / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == info["sha256"], name
        layers[path.stem] = json.loads(path.read_text())["features"]
    return layers


def polygon_parts(geometry):
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPolygon":
        return geometry["coordinates"]
    if geometry["type"] == "GeometryCollection":
        return [p for g in geometry["geometries"] for p in polygon_parts(g)]
    return []


@lru_cache(maxsize=1)
def boundary_paths():
    layers = boundary_layers()
    rings = []
    for feature in layers["neighbours"]:
        for polygon in polygon_parts(feature["geometry"]):
            for ring in polygon:
                codes = np.full(len(ring), PlotPath.LINETO, dtype=np.uint8)
                codes[0], codes[-1] = PlotPath.MOVETO, PlotPath.CLOSEPOLY
                rings.append(PlotPath(np.asarray(ring), codes))
    outlines = {layer: [np.asarray(ring) for f in layers[layer] for polygon in polygon_parts(f["geometry"]) for ring in polygon]
                for layer in ("provinces", "indonesia")}
    return PlotPath.make_compound_path(*rings), outlines


def draw_boundaries(ax):
    """Cartographic overlays only; forecast masks and values are untouched."""
    neighbours, outlines = boundary_paths()
    ax.add_patch(PathPatch(neighbours, facecolor="#d6d8da", edgecolor="#9ca3a8", linewidth=.35, zorder=1))
    for layer, color, width, order in [("provinces", "#52616b", .30, 4), ("indonesia", "#263943", .55, 5)]:
        ax.add_collection(LineCollection(outlines[layer], colors=color, linewidths=width, zorder=order))


def map_axis(ax,field,title,*,cmap="YlGnBu",vmin=0,vmax=None,norm=None):
    image=ax.pcolormesh(field.X,field.Y,field.values,shading="auto",cmap=cmap,vmin=vmin if norm is None else None,vmax=vmax if norm is None else None,norm=norm,rasterized=True,zorder=2)
    draw_boundaries(ax)
    ax.set(xlim=(94,142),ylim=(-12,7),title=title)
    ax.set_aspect(1/np.cos(np.deg2rad(-2.5)))
    ax.set_xticks([100,120,140],["100°E","120°E","140°E"])
    ax.set_yticks([-10,0],["10°S","0°"])
    ax.tick_params(labelsize=8,length=2); ax.grid(alpha=.12)
    ax.set_facecolor("#f1f5f7")
    return image

def ond_maps(bundle):
    ds=bundle.sel(season="OND")
    observed=ds.observed_rainfall
    fig,axes=plt.subplots(3,2,figsize=(11,7),layout="constrained")
    fields=[("Observed · CHIRPS3",observed)]+[(LABELS[m],ds.forecast_rainfall.sel(forecast_variant=m)) for m in MAIN]
    limit=float(np.nanquantile(np.concatenate([a.values.ravel() for _,a in fields]),.99))
    for ax,(name,field) in zip(axes.flat,fields): im=map_axis(ax,field,name,vmax=limit)
    axes.flat[-1].axis("off")
    axes.flat[-1].text(.02,.85,"OND 2023\n1 October–31 December\n\nIssued 1 September\nCalibration: 1991–2020\nCountry-land cells: 3,240\n\nGrey land: other countries\nDark outline: Indonesia\nThin lines: provinces",transform=axes.flat[-1].transAxes,va="top",fontsize=10)
    fig.colorbar(im,ax=list(axes.flat[:5]),shrink=.65,pad=.015,label="Seasonal rainfall (mm) · common colour scale; top 1% saturated",extend="max")
    return fig

def error_atlas(bundle):
    fig,axes=plt.subplots(6,4,figsize=(15,12),layout="constrained")
    truth=bundle.observed_rainfall
    base=abs(bundle.forecast_rainfall.sel(forecast_variant="climatology_1991_2020")-truth)
    norm=TwoSlopeNorm(vmin=-300,vcenter=0,vmax=300)
    for index,season in enumerate(SEASONS):
        row,col=divmod(index,2)
        for j,method in enumerate(("cca","pcr")):
            field=(base-abs(bundle.forecast_rainfall.sel(forecast_variant=f"{method}_1991_2020")-truth)).sel(season=season)
            im=map_axis(axes[row,col*2+j],field,f"{season} · {method.upper()}",cmap="BrBG",norm=norm)
    fig.colorbar(im,ax=list(axes.flat),location="bottom",shrink=.52,pad=.02,aspect=55,label="Climatology absolute error − calibrated absolute error (mm) · positive = calibration helps",extend="both")
    return fig

def sensitivity_plot(frame):
    fig,axes=plt.subplots(1,2,figsize=(11,3.7),sharey=True,layout="constrained")
    x=np.arange(12)
    for ax,method in zip(axes,("cca","pcr")):
        old=frame[f"{method}_1983_2010"]; recent=frame[f"{method}_1991_2020"]
        ax.plot(x,old,"o--",color="#798491",label="1983–2010",markersize=4)
        ax.plot(x,recent,"o-",color=COLORS[method.upper()],label="1991–2020",markersize=4)
        ax.set_xticks(x,SEASONS,rotation=45); ax.set_title(method.upper(),fontweight="bold"); ax.grid(axis="y",alpha=.15)
    axes[0].set_ylabel("Spatial RMSE (mm)"); axes[1].legend(frameon=False)
    return fig

def context_plot(frame):
    fig,ax=plt.subplots(figsize=(10,4),layout="constrained")
    for name in COLORS:
        ax.plot(range(12),frame[name],"o-",color=COLORS[name],label=name,markersize=4)
    ax.set_xticks(range(12),SEASONS); ax.set_ylabel("Pooled spatial RMSE (mm)")
    ax.set_title("A broader context: original ending-year 2021–2024 windows",fontweight="bold",pad=12)
    ax.legend(frameon=False,ncols=4); ax.grid(axis="y",alpha=.15)
    return fig


def province_heatmap(scores, title):
    """Show all supplied provinces, using one fixed relative-error colour scale."""
    names = sorted(str(v) for v in scores.region.values)
    base = scores.rmse.sel(forecast_variant="climatology_1991_2020")
    assert bool((base > 0).all())
    fig, axes = plt.subplots(1, 2, figsize=(14, 11), sharey=True, layout="constrained")
    for ax, method in zip(axes, ("cca", "pcr")):
        gain = 100*(1-scores.rmse.sel(forecast_variant=f"{method}_1991_2020")/base)
        values = gain.sel(region=names, season=SEASONS).transpose("region", "season").values
        im = ax.imshow(values, cmap="BrBG", norm=TwoSlopeNorm(vmin=-100, vcenter=0, vmax=100), aspect="auto")
        ax.set_xticks(range(12), SEASONS, rotation=45)
        ax.set_yticks(range(len(names)), names, fontsize=8)
        ax.set_title(method.upper(), fontweight="bold")
        ax.tick_params(length=0)
    fig.suptitle(title, fontsize=14, fontweight="bold")
    fig.colorbar(im, ax=list(axes), location="bottom", shrink=.65, aspect=50, pad=.015,
                 label="RMSE reduction relative to matched climatology (%) · green helps; brown worsens", extend="min")
    return fig


def province_support_map(native, unassigned_fraction):
    fig, ax = plt.subplots(figsize=(11, 4.8), layout="constrained")
    draw_boundaries(ax)
    assigned = native.membership_count.values == 1
    ax.scatter(native.longitude.values[assigned], native.latitude.values[assigned], s=.15, color="#71a8b0", linewidths=0, zorder=2, label="Assigned native country pixels")
    ax.scatter(native.longitude.values[~assigned], native.latitude.values[~assigned], s=3, color="#b34430", linewidths=0, zorder=6, label="Unassigned/overlap pixels")
    ax.set(xlim=(94,142), ylim=(-12,7), xlabel="Longitude (°E)", ylabel="Latitude (°N)")
    ax.set_aspect(1/np.cos(np.deg2rad(-2.5))); ax.set_facecolor("#f1f5f7")
    ax.set_title(f"Province assignment audit · {100*unassigned_fraction:.2f}% of country weight unassigned", fontweight="bold")
    ax.legend(frameon=False, loc="lower left", markerscale=3)
    return fig
