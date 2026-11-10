"""Figures for the 0.05-degree trial: the OND 2023 CCA forecast at both resolutions.

    python research/scripts/plot_indonesia_005_trial.py
"""
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import xarray as xr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pycpt_tutorial import figures

CASE = ROOT / "research/cases/indonesia-ond-2023-005deg-trial"
BOX = (94, 142, -12, 7)


def main():
    figures.use_style()
    fine = xr.open_dataset(CASE / "forecast-2023-0p05.nc")
    common = xr.open_dataset(CASE / "forecast-2023-common-0p25.nc")
    panels = [
        (fine.cca_forecast_0p05, "CCA forecast, OND 2023 · predictand at 0.05°", "YlGnBu", 0, 2000, "mm"),
        (common.cca_forecast_0p25, "CCA forecast, OND 2023 · predictand at 0.25°", "YlGnBu", 0, 2000, "mm"),
        (common.cca_forecast_0p05_aggregated - common.cca_forecast_0p25,
         "0.05° forecast aggregated to 0.25°, minus the 0.25° forecast", "BrBG", -20, 20, "mm"),
        (fine.observed_2023_0p05, "Observed OND 2023 · CHIRPS v3.0 at 0.05°", "YlGnBu", 0, 2000, "mm"),
    ]
    fig, grid = figures.stacked([figures.map_height(BOX)] * len(panels))
    for row, (field, title, cmap, low, high, unit) in enumerate(panels):
        ax = figures.map_axes(fig, grid[row, 0], BOX, bottom_labels=row == len(panels) - 1)
        image = figures.draw_field(ax, field, cmap=cmap, vmin=low, vmax=high)
        ax.set_title(title)
        figures.colorbar(fig, image, ax, unit, extend="both" if cmap == "BrBG" else "max")
    fig.savefig(CASE / "cca-forecast-0p05-vs-0p25.png")
    print("saved", CASE / "cca-forecast-0p05-vs-0p25.png")


if __name__ == "__main__":
    main()
