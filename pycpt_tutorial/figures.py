"""Shared figure style for the Learn PyCPT chapters.

The tutorial draws its own figures from the data PyCPT returns, so every map and
chart shares one quiet style: white plate, ink text, hairline frames, coastlines
from Natural Earth, and colour scales chosen per quantity. Nothing here computes
scientific results; the functions only draw arrays they are given.
"""
from contextlib import contextmanager

import numpy as np

INK = "#1b1d22"
INK_2 = "#3c4049"
MUTED = "#6b6e75"
LINE = "#d9d3c7"
GRID = "#ece8e0"
LAND = "#f3f0ea"
ACCENT = "#1f4fa3"
MARK = "#c8462b"
GREEN = "#4f8a5a"
GOLD = "#c48a1d"
CYCLE = [ACCENT, MARK, GREEN, GOLD, "#7a5aa6", "#3a8fa3"]


def use_style():
    """Apply the tutorial's matplotlib defaults."""
    import matplotlib as mpl
    from cycler import cycler

    mpl.rcParams.update({
        "figure.dpi": 110,
        "savefig.dpi": 160,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.bbox": "tight",
        "savefig.pad_inches": .12,
        "font.family": "DejaVu Sans",
        "font.size": 9.5,
        "text.color": INK,
        "axes.edgecolor": LINE,
        "axes.linewidth": .8,
        "axes.labelcolor": INK_2,
        "axes.labelsize": 9,
        "axes.titlesize": 10.5,
        "axes.titleweight": "bold",
        "axes.titlecolor": INK,
        "axes.titlelocation": "left",
        "axes.titlepad": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "axes.prop_cycle": cycler(color=CYCLE),
        "grid.color": GRID,
        "grid.linewidth": .7,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "legend.frameon": False,
        "legend.fontsize": 8.5,
        "lines.linewidth": 1.7,
        "lines.solid_capstyle": "round",
    })


def map_axes(fig, spec, extent, *, left_labels=True, bottom_labels=True, land=False):
    """A PlateCarree map axis with coastlines, borders and light degree labels."""
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    from cartopy.mpl.ticker import LatitudeFormatter, LongitudeFormatter

    ax = fig.add_subplot(spec, projection=ccrs.PlateCarree())
    west, east, south, north = extent
    ax.set_extent([west, east, south, north], crs=ccrs.PlateCarree())
    if land:
        ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor=LAND, edgecolor="none", zorder=0)
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"), linewidth=.45, edgecolor=INK_2, zorder=3)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), linewidth=.3, edgecolor=MUTED, linestyle=(0, (2, 2)), zorder=3)
    ax.spines["geo"].set_edgecolor(LINE)
    ax.spines["geo"].set_linewidth(.8)
    ax.grid(False)
    step = 10 if (east - west) <= 60 else 20
    ax.set_xticks(np.arange(np.ceil(west / step) * step, east + .1, step), crs=ccrs.PlateCarree())
    ax.set_yticks(np.arange(np.ceil(south / 5) * 5, north + .1, 5 if (north - south) <= 25 else 10), crs=ccrs.PlateCarree())
    ax.xaxis.set_major_formatter(LongitudeFormatter(degree_symbol="°"))
    ax.yaxis.set_major_formatter(LatitudeFormatter(degree_symbol="°"))
    ax.tick_params(labelsize=7.5, colors=MUTED, labelleft=left_labels, labelbottom=bottom_labels)
    return ax


def draw_field(ax, field, **kwargs):
    """Draw a (Y, X) DataArray on a map axis without interpolation."""
    import cartopy.crs as ccrs

    a = field.transpose("Y", "X")
    options = dict(shading="nearest", rasterized=True, transform=ccrs.PlateCarree(), zorder=1)
    options.update(kwargs)
    return ax.pcolormesh(a["X"], a["Y"], a.values, **options)


def colorbar(fig, mappable, axes, label, *, orientation="vertical", extend="neither", ticks=None,
             fraction=.035, pad=.02, aspect=22):
    """A thin colour bar beside (vertical) or under (horizontal) one or more axes."""
    bar = fig.colorbar(mappable, ax=axes, orientation=orientation, fraction=fraction, pad=pad,
                       aspect=aspect, extend=extend, ticks=ticks)
    bar.outline.set_visible(False)
    bar.ax.tick_params(labelsize=7.5, colors=MUTED, length=0)
    bar.set_label(label, fontsize=8, color=INK_2, labelpad=6)
    return bar


MAP_WIDTH = 9.5  # inches; figures are stacked in one column at full page width


def map_height(extent, width=MAP_WIDTH):
    """Height in inches of a PlateCarree map of this extent drawn at the given width."""
    west, east, south, north = extent
    return width * (north - south) / (east - west)


def stacked(heights, width=MAP_WIDTH + 1.3):
    """A one-column figure whose rows have the given heights in inches."""
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(width, sum(heights) + .5 * len(heights)), layout="constrained")
    return fig, fig.add_gridspec(len(heights), 1, height_ratios=heights)


def box(ax, extent, color, label=None, linewidth=1.6):
    """Outline a west/east/south/north box and optionally label it in its corner."""
    import cartopy.crs as ccrs

    west, east, south, north = extent
    ax.plot([west, east, east, west, west], [south, south, north, north, south],
            color=color, linewidth=linewidth, transform=ccrs.PlateCarree(), zorder=4)
    if label is None:
        return
    ax.text(west + .8, north - .8, label, color=color, fontsize=8.5, fontweight="bold",
            va="top", ha="left", transform=ccrs.PlateCarree(), zorder=5,
            bbox=dict(boxstyle="round,pad=.25", facecolor="white", edgecolor="none", alpha=.85))


def extent_of(d):
    """Convert PyCPT's {'west','east','south','north'} dictionary to a tuple."""
    return (d["west"], d["east"], d["south"], d["north"])


@contextmanager
def quiet_pycpt_plots():
    """Run a PyCPT plotting function without drawing its figures inline.

    PyCPT's plot functions save PNG files to the case's figures/ folder and call
    plt.show(). Inside this block plt.show() does nothing and every new figure is
    closed afterwards, so the saved files are kept but nothing is displayed.
    """
    import matplotlib.pyplot as plt

    before = set(plt.get_fignums())
    original_show = plt.show
    plt.show = lambda *args, **kwargs: None
    try:
        yield
    finally:
        plt.show = original_show
        for number in set(plt.get_fignums()) - before:
            plt.close(number)


# ---------------------------------------------------------------------------
# Figures for evaluate_models results (chapter 4)
# ---------------------------------------------------------------------------

# Colour ranges follow PyCPT 2.10.4's SKILL_METRICS table (pycpt/notebook.py).
SKILL_SCALES = {
    "pearson": ("Pearson correlation", "RdBu_r", -1, 1, [-1, -.5, 0, .5, 1]),
    "spearman": ("Spearman correlation", "RdBu_r", -1, 1, [-1, -.5, 0, .5, 1]),
    "two_alternative_forced_choice": ("2AFC (%)", "RdBu_r", 0, 100, [0, 25, 50, 75, 100]),
    "roc_area_below_normal": ("ROC area, below normal", "RdBu_r", 0, 1, [0, .25, .5, .75, 1]),
    "roc_area_above_normal": ("ROC area, above normal", "RdBu_r", 0, 1, [0, .25, .5, .75, 1]),
    "root_mean_squared_error": ("RMSE (mm)", "YlOrRd", 0, 300, [0, 100, 200, 300]),
}


def skill_figure(skill, extent, metrics):
    """CPT's skill maps stacked in one column, each with its own colour bar."""
    fig, grid = stacked([map_height(extent)] * len(metrics))
    for i, metric in enumerate(metrics):
        title, cmap, vmin, vmax, ticks = SKILL_SCALES[metric]
        ax = map_axes(fig, grid[i, 0], extent, bottom_labels=i == len(metrics) - 1)
        image = draw_field(ax, skill[metric], cmap=cmap, vmin=vmin, vmax=vmax)
        ax.set_title(title)
        colorbar(fig, image, ax, "", ticks=ticks,
                 extend="max" if metric == "root_mean_squared_error" else "neither")
    return fig


def pattern_figure(pxs, pys, kind, mode, x_extent, y_extent):
    """One mode in one column: predictor loadings, predictand loadings, then both score series."""
    prefix = {"eof": "eof", "cca": "cca"}[kind]
    fig, grid = stacked([map_height(x_extent), map_height(y_extent), 2.6])
    for row, (patterns, extent, side, letter) in enumerate([(pxs, x_extent, "predictor", "x"), (pys, y_extent, "predictand", "y")]):
        load = patterns[f"{letter}_{prefix}_loadings"].sel(Mode=mode)
        load = load.where(load > -999)  # CPT writes -999 where a location was not used
        limit = float(np.nanmax(np.abs(load.values)))
        ax = map_axes(fig, grid[row, 0], extent)
        image = draw_field(ax, load, cmap="RdBu_r", vmin=-limit, vmax=limit)
        label = f"{kind.upper()} {mode} · {side} loadings"
        if kind == "eof":
            label += f" · {float(patterns[f'{letter}_explained_variance'].sel(Mode=mode)):.1f}% of variance"
        ax.set_title(label)
        colorbar(fig, image, ax, "loading")
    ax = fig.add_subplot(grid[2, 0])
    x_score = pxs[f"x_{prefix}_scores"].sel(Mode=mode)
    y_score = pys[f"y_{prefix}_scores"].sel(Mode=mode)
    x_score, y_score = x_score.where(x_score > -999), y_score.where(y_score > -999)
    years = x_score["T"].dt.year.values
    ax.axhline(0, color=LINE, linewidth=.8)
    ax.plot(years, x_score, color=ACCENT, marker="o", markersize=3, label="predictor")
    ax.plot(years, y_score, color=MARK, marker="o", markersize=3, label="predictand")
    title = f"{kind.upper()} {mode} · scores by training year"
    if kind == "cca":
        title += f" · r = {np.corrcoef(x_score, y_score)[0, 1]:.2f}"
    ax.set_title(title)
    ax.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0), frameon=False)
    return fig


# Category colour ranges follow cptextras.view_probabilistic in PyCPT 2.10.4:
# below and above normal 35-85 %, near normal 35-55 %.
CATEGORIES = [("Below normal", "Oranges", 35, 85, [40, 60, 80]),
              ("Near normal", "Greys", 35, 55, [35, 45, 55]),
              ("Above normal", "Blues", 35, 85, [40, 60, 80])]


def _inset_bar(fig, image, ax, rect, label, ticks=None):
    cax = ax.inset_axes(rect)
    bar = fig.colorbar(image, cax=cax, orientation="horizontal", ticks=ticks)
    bar.outline.set_visible(False)
    bar.ax.tick_params(labelsize=7.5, colors=MUTED, length=0)
    bar.set_label(label, fontsize=8, color=INK_2, labelpad=4)
    return bar


def most_likely_map(fig, spec, probability, extent, title="Most likely category and its probability"):
    """Map of the leading tercile category coloured by its probability (PyCPT's view_probabilistic rule)."""
    most_likely = probability.fillna(-1).argmax("C").where(probability.notnull().all("C"))
    top = probability.max("C")
    ax = map_axes(fig, spec, extent)
    for index, (name, cmap, vmin, vmax, ticks) in enumerate(CATEGORIES):
        image = draw_field(ax, top.where(most_likely == index), cmap=cmap, vmin=vmin, vmax=vmax)
        _inset_bar(fig, image, ax, [index * .35, -.2, .3, .035], f"{name} (%)", ticks)
    ax.set_title(title)
    return ax


def forecast_figure(forecast, extent):
    """The most likely tercile category with its probability, above the deterministic forecast."""
    fig, grid = stacked([map_height(extent) + .7, map_height(extent) + .7])
    most_likely_map(fig, grid[0, 0], forecast.probabilistic.isel(T=0), extent)
    ax = map_axes(fig, grid[1, 0], extent)
    image = draw_field(ax, forecast.deterministic.isel(T=0), cmap="YlGnBu", vmin=0)
    ax.set_title("Deterministic forecast")
    _inset_bar(fig, image, ax, [.2, -.2, .6, .035], "OND rainfall total (mm)")
    return fig


# ---------------------------------------------------------------------------
# Figures for probabilistic forecasts (chapter 5)
# ---------------------------------------------------------------------------

CATEGORY_COLOURS = ["#e07b39", "#9a9a94", "#2f6fb5"]  # below, near, above normal


def tercile_maps(probability, extent, titles=("Below normal", "Near normal", "Above normal")):
    """One map per category probability (C order: below, near, above), stacked in one column."""
    cmaps = ["Oranges", "Greys", "Blues"]
    fig, grid = stacked([map_height(extent)] * 3)
    for i in range(3):
        ax = map_axes(fig, grid[i, 0], extent, bottom_labels=i == 2)
        image = draw_field(ax, probability.isel(C=i), cmap=cmaps[i], vmin=0, vmax=100)
        ax.set_title(f"{titles[i]} (%)")
        colorbar(fig, image, ax, "", ticks=[0, 33, 67, 100])
    return fig


def category_map(ax, category, extent=None):
    """Draw an integer category field (0 below, 1 near, 2 above normal) in fixed colours."""
    from matplotlib.colors import ListedColormap

    return draw_field(ax, category, cmap=ListedColormap(CATEGORY_COLOURS), vmin=-.5, vmax=2.5)


def category_legend(ax, labels=("Below normal", "Near normal", "Above normal"), **kwargs):
    from matplotlib.patches import Patch

    handles = [Patch(facecolor=c, edgecolor="none", label=l) for c, l in zip(CATEGORY_COLOURS, labels)]
    options = dict(loc="lower left", ncols=3, frameon=True, facecolor="white", edgecolor="none", framealpha=.9)
    options.update(kwargs)
    return ax.legend(handles=handles, **options)
