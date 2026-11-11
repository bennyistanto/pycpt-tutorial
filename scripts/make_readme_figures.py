"""Figures for the repository README, drawn only from saved case outputs (no fitting, no downloads).

    python scripts/make_readme_figures.py

1. skill-across-time-scales.png: area-mean cross-validated CCA correlation (and the raw model's)
   against days from issue to target, one panel per model family.
2. week1-skill-005deg.png: week-1 CCA correlation at the native 0.05° grid, with a zoom on Java.
3. weekly-skill-ridgelines.png: distribution of the 61,190 pixel correlations at each weekly lead.

Inputs: docs/data/*/skill-by-lead.csv, */summary.json, */lead-design.csv,
docs/data/week-leads-2023/week-leads-2023-skill-maps.nc, docs/data/boundaries/*.geojson.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from matplotlib.collections import PatchCollection
from matplotlib.patches import Polygon, Rectangle
from scipy.stats import gaussian_kde

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pycpt_tutorial import figures  # noqa: E402

OUT = ROOT / "docs/assets/readme"
DATA = ROOT / "docs/data"
INK, MUTED, LINE = "#1b1d22", figures.MUTED, figures.LINE
COLOURS = {"Monthly": figures.ACCENT, "Seasonal": "#7a5aa6", "Dekad": figures.GOLD, "Weekly": figures.MARK,
           "Weeks 3-4": figures.MARK, "Pentad": figures.GREEN}


def subtitle(ax, title, note):
    ax.set_title(title, loc="left", fontsize=13, color=INK, pad=26, fontweight="bold")
    ax.text(0, 1.02, note, transform=ax.transAxes, fontsize=8.5, color=MUTED, va="bottom")


def cases():
    """One row per (case, lead): days from issue to the first day of the target, its length, CCA and raw r."""
    rows = []
    issue = dt.date(2023, 11, 1)
    for case, folder in [("Monthly", "monthly-2023"), ("Seasonal", "seasonal-leads-2023")]:
        s = pd.read_csv(DATA / folder / "skill-by-lead.csv").set_index(["lead", "method"])
        for lead, t in json.loads((DATA / folder / "summary.json").read_text())["targets"].items():
            first, last = dt.date.fromisoformat(t["first_day"]), dt.date.fromisoformat(t["last_day"])
            rows.append({"family": "CFSv2", "case": case, "label": t["label"], "offset": (first - issue).days,
                         "length": (last - first).days + 1, "cca": s.loc[(int(lead), "CCA"), "Pearson"],
                         "raw": s.loc[(int(lead), "raw CFSv2"), "Pearson"]})
    for case, folder in [("Dekad", "dekad-leads-2023"), ("Weekly", "week-leads-2023"), ("Pentad", "pentad-leads-2023")]:
        if not (DATA / folder / "skill-by-lead.csv").exists():
            continue                                      # a case not yet run is left out
        s = pd.read_csv(DATA / folder / "skill-by-lead.csv")
        s["lead"] = s["lead"].astype(str)
        s = s.set_index(["lead", "method"])
        design = pd.read_csv(DATA / folder / "lead-design.csv")
        design["lead"] = design["lead"].astype(str)
        live = design[design.kind == "forecast"].groupby("lead").agg(offset=("first_day", "mean"), length=("days", "mean"))
        for lead, r in live.iterrows():
            rows.append({"family": "GEFSv12", "case": "Weeks 3-4" if lead == "week34" else case, "label": lead,
                         "offset": r.offset, "length": r.length,
                         "cca": s.loc[(lead, "CCA"), "Pearson"], "raw": s.loc[(lead, "raw GEFS"), "Pearson"]})
    return pd.DataFrame(rows)


def skill_across_time_scales():
    d = cases()
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.9), layout="constrained", sharey=True,
                             gridspec_kw={"width_ratios": [1, 1.25]})
    panels = [("GEFSv12", "Subseasonal: GEFSv12, October-December", (0, 30), [1, 7, 14, 21, 28]),
              ("CFSv2", "Monthly and seasonal: CFSv2 issued 1 Nov 2023", (18, 196), [30, 61, 92, 121, 152, 182])]
    for ax, (family, title, xlim, ticks) in zip(axes, panels):
        ax.axhline(0, color=INK, linewidth=.7, alpha=.4)
        sub = d[d.family == family]
        for case, g in sub.groupby("case", sort=False):
            g = g.sort_values("offset")
            c = COLOURS[case]
            if case != "Weeks 3-4":
                ax.plot(g.offset, g.cca, color=c, linewidth=2.2, zorder=3)
                ax.plot(g.offset, g.raw, color=c, linewidth=1, linestyle=(0, (2, 2)), alpha=.75, zorder=2)
            ax.scatter(g.offset, g.cca, s=18 + 2.2 * g.length, color=c, edgecolor="white", linewidth=1, zorder=4)
            ax.scatter(g.offset, g.raw, s=18 + 2.2 * g.length, facecolor="white", edgecolor=c, linewidth=1.3, zorder=4)
        ax.set_xlim(*xlim)
        ax.set_xticks(ticks)
        ax.set_title(title, loc="left", fontsize=10, color=INK)
        ax.grid(axis="x", visible=False)
        ax.set_xlabel("Days from issue to the first day of the target")
    axes[0].set_ylabel("Area-mean correlation over Indonesia")
    # labels placed by hand where lines end, clear of each other
    first = axes[0]
    for case, dy in [("Dekad", .02), ("Weekly", -.045), ("Pentad", 0), ("Weeks 3-4", .015)]:
        g = d[d.case == case].sort_values("offset")
        if g.empty:
            continue
        last = g.iloc[-1] if case != "Weeks 3-4" else g.iloc[0]
        first.annotate(case, (last.offset, last.cca), xytext=(7, dy * 400), textcoords="offset points", fontsize=9,
                       color=COLOURS[case], fontweight="bold", va="center")
    for case in ["Monthly", "Seasonal"]:
        g = d[d.case == case].sort_values("offset")
        axes[1].annotate(case, (g.iloc[0].offset, g.iloc[0].cca), xytext=(-8, 10 if case == "Seasonal" else -12),
                         textcoords="offset points", fontsize=9, color=COLOURS[case], fontweight="bold", ha="right")
    fig.suptitle("How much skill is left, from one week to six months ahead", x=.01, ha="left", fontsize=13,
                 fontweight="bold", color=INK)
    fig.text(.01, .925, "Filled, solid: calibrated (CCA, cross-validated) · open, dotted: raw model · marker size: length of the target period",
             fontsize=8.5, color=MUTED)
    fig.get_layout_engine().set(rect=(0, 0, 1, .91))
    fig.savefig(OUT / "skill-across-time-scales.png", dpi=170, facecolor="white")
    plt.close(fig)
    return d


def rings(g):
    if g["type"] == "Polygon":
        return g["coordinates"]
    if g["type"] == "MultiPolygon":
        return [r for p in g["coordinates"] for r in p]
    return []


LAYERS = {name: json.loads((DATA / "boundaries" / f"{name}.geojson").read_text()) for name in ("neighbours", "indonesia", "provinces")}


def draw_boundaries(ax, provinces=True):
    for name, face, width, z in [("neighbours", "#eceae4", .4, 1), ("indonesia", "#eceae4", .5, 1), ("provinces", "none", .25, 4)]:
        if name == "provinces" and not provinces:
            continue
        patches = [Polygon(np.asarray(r)[:, :2], closed=True) for f in LAYERS[name]["features"] for r in rings(f["geometry"])]
        ax.add_collection(PatchCollection(patches, facecolor=face, edgecolor="#7d8580", linewidth=width, zorder=z))


def week1_map():
    m = xr.open_dataset(DATA / "week-leads-2023/week-leads-2023-skill-maps.nc")
    r = m.cca_pearson_week1
    lat = r.Y.values
    step = .05
    extent = [float(r.X.min()) - step / 2, float(r.X.max()) + step / 2, float(r.Y.min()) - step / 2, float(r.Y.max()) + step / 2]
    origin = "upper" if lat[0] > lat[-1] else "lower"
    show = dict(extent=extent, origin=origin, cmap="RdBu_r", vmin=-.8, vmax=.8, interpolation="nearest", zorder=2)
    view = [94.5, 141.5, -11.2, 6.2]
    lens = [106.2, 111.8, -8.0, -6.0]                         # western and central Java
    W = 10.4
    main_h = W * .96 * (view[3] - view[2]) / (view[1] - view[0])
    zoom_w = W * .62
    zoom_h = zoom_w * (lens[3] - lens[2]) / (lens[1] - lens[0])
    H = main_h + zoom_h + 1.5
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([.02, (zoom_h + .55) / H, .96, main_h / H])
    draw_boundaries(ax)
    image = ax.imshow(r.values, **show)
    ax.set_xlim(view[0], view[1]); ax.set_ylim(view[2], view[3]); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_edgecolor(LINE)
    fig.text(.02, 1 - .32 / H, "Week 1 at 0.05°: 61,190 pixels, each with its own skill", fontsize=13, fontweight="bold", color=INK, va="top")
    fig.text(.02, 1 - .62 / H, "Cross-validated correlation of calibrated (CCA) GEFSv12 week-1 rainfall with CHIRPS v3.0, "
             "October-December 2000-2018", fontsize=8.5, color=MUTED, va="top")
    ax.add_patch(Rectangle((lens[0], lens[2]), lens[1] - lens[0], lens[3] - lens[2], fill=False, edgecolor=INK, linewidth=1.2, zorder=5))
    zoom = fig.add_axes([.02, .3 / H, .62, zoom_h / H])
    draw_boundaries(zoom)
    zoom.imshow(r.values, **show)
    zoom.set_xlim(lens[0], lens[1]); zoom.set_ylim(lens[2], lens[3]); zoom.set_aspect("equal")
    zoom.set_xticks([]); zoom.set_yticks([])
    for s in zoom.spines.values():
        s.set_edgecolor(INK); s.set_linewidth(1.2)
    zoom.text(.01, .03, "Western and central Java: every square is one 0.05° pixel, about 5.5 km",
              transform=zoom.transAxes, fontsize=8, color=INK, bbox=dict(facecolor="white", edgecolor="none", alpha=.85, pad=2))
    from matplotlib.patches import ConnectionPatch
    for xy_main, xy_zoom in [((lens[0], lens[2]), (0, 1)), ((lens[1], lens[2]), (1, 1))]:
        fig.add_artist(ConnectionPatch(xyA=xy_main, coordsA=ax.transData, xyB=xy_zoom, coordsB=zoom.transAxes,
                                       color=INK, linewidth=.7, alpha=.55))
    cax = fig.add_axes([.68, (zoom_h * .35 + .3) / H, .29, .14 / H])
    bar = fig.colorbar(image, cax=cax, orientation="horizontal", ticks=[-.8, -.4, 0, .4, .8])
    bar.outline.set_visible(False); bar.ax.tick_params(labelsize=8, colors=MUTED, length=0)
    bar.set_label("Pearson correlation (0 = no linear relationship)", fontsize=8.5, color=MUTED)
    w = (np.cos(np.deg2rad(r.Y)) * r.notnull()).fillna(0)
    fig.text(.68, (zoom_h * .35 + .3) / H + .5 / H,
             f"Area-mean {float(r.weighted(w).mean()):.2f}\nhalf of all pixels between "
             f"{np.nanpercentile(r.values, 25):.2f} and {np.nanpercentile(r.values, 75):.2f}", fontsize=9, color=INK, va="bottom")
    fig.savefig(OUT / "week1-skill-005deg.png", dpi=170, facecolor="white")
    plt.close(fig)


def ridgelines():
    m = xr.open_dataset(DATA / "week-leads-2023/week-leads-2023-skill-maps.nc")
    leads = [("week1", "Week 1"), ("week2", "Week 2"), ("week3", "Week 3"), ("week4", "Week 4"), ("week34", "Weeks 3-4")]
    grid = np.linspace(-.5, .9, 500)
    fig, ax = plt.subplots(figsize=(9.6, 5.4), layout="constrained")
    height, rng = .92, np.random.default_rng(0)
    for i, (key, name) in enumerate(leads):
        base = (len(leads) - 1 - i) * 1.0
        z = 2 * i + 10                                        # lower rows drawn in front
        out = {}
        for var in (f"cca_pearson_{key}", f"raw_pearson_{key}"):
            v = m[var].values.ravel()
            v = v[np.isfinite(v)]
            dens = gaussian_kde(v[rng.choice(len(v), size=min(len(v), 25000), replace=False)], bw_method=.07)(grid)
            out[var] = (v, dens)
        top = max(d.max() for _, d in out.values())
        v, dens = out[f"cca_pearson_{key}"]
        y = base + dens / top * height
        ax.fill_between(grid, base, y, color=figures.ACCENT, alpha=.88, linewidth=0, zorder=z)
        ax.plot(grid, y, color="white", linewidth=1.2, zorder=z)
        ax.plot([grid[0], grid[-1]], [base, base], color=LINE, linewidth=.8, zorder=z)
        med = np.median(v)
        ax.plot([med, med], [base, base + np.interp(med, grid, dens) / top * height], color="white", linewidth=1.6, zorder=z + 1)
        raw_v, raw_d = out[f"raw_pearson_{key}"]
        keep = raw_d / top > .01
        ax.plot(np.where(keep, grid, np.nan), base + raw_d / top * height, color=INK, linewidth=1.1,
                linestyle=(0, (2.5, 1.8)), zorder=z + 1)
        ax.text(-.52, base + .36, name, ha="right", va="bottom", fontsize=10.5, color=INK, fontweight="bold")
        share = float((v > 0).mean() * 100)
        ax.text(-.52, base + .02, f"median {med:.2f}\n{share:.1f}% of pixels > 0", ha="right", va="bottom",
                fontsize=8, color=MUTED, zorder=30)
    ax.axvline(0, color=INK, linewidth=.8, alpha=.45, zorder=40)
    ax.set_yticks([]); ax.set_xlim(-.5, .9); ax.set_ylim(-.15, len(leads) - 1 + height + .1)
    for s in ["left", "top", "right"]:
        ax.spines[s].set_visible(False)
    ax.set_xlabel("Cross-validated correlation at each 0.05° pixel")
    subtitle(ax, "Skill is a distribution, not a number: 61,190 pixels at each lead",
             "Blue: calibrated (CCA), white line at the median · dashed: raw GEFSv12 · weekly rainfall over Indonesia, October-December 2000-2018")
    ax.grid(False)
    fig.savefig(OUT / "weekly-skill-ridgelines.png", dpi=170, facecolor="white")
    plt.close(fig)


def main():
    figures.use_style()
    OUT.mkdir(parents=True, exist_ok=True)
    d = skill_across_time_scales()
    print(d.round(3).to_string())
    week1_map()
    ridgelines()
    for p in sorted(OUT.glob("*.png")):
        print(f"{p.relative_to(ROOT)}  ({p.stat().st_size / 1000:.0f} kB)")


if __name__ == "__main__":
    main()
