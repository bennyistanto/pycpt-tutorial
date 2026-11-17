"""What does a forecast with no model score in cross-validation? The baseline for the lead-time cases.

For each lead of the single-model seasonal and monthly cases, this reads the case's own
training observations (the local CHIRPS v3.0 file the notebook wrote into its case folder)
and builds the forecast that uses no model at all: for each training year, the mean of the
observations outside that year's cross-validation window (the year and its two neighbours
on each side, wrapping at the ends, as CPT's window of 5 does). It then scores that forecast
exactly as the hindcasts are scored: Pearson correlation over the training years at each
pixel, averaged over Indonesia with cosine-latitude weights.

Leaving a wet year out lowers the mean of the rest, so this correlation is negative
(Barnston and van den Dool 1993, doi:10.1175/1520-0442(1993)006<0963:ADICVS>2.0.CO;2).
Zero is therefore not the no-skill level of a cross-validated correlation.

    python research/scripts/no_model_cv_baseline.py

Writes docs/data/seasonal-leads-2023/no-model-baseline.csv and docs/data/monthly-2023/no-model-baseline.csv.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[2]
CASES = {"seasonal-leads-2023": Path.home() / "PyCPT" / "indonesia-issued-2023-11-seasons",
         "monthly-2023": Path.home() / "PyCPT" / "indonesia-issued-2023-11-months"}
WINDOW = 5


def climatology_hindcast(observed):
    T, half = observed.shape[0], WINDOW // 2
    return np.stack([observed[np.setdiff1d(np.arange(T), [(i + k) % T for k in range(-half, half + 1)])].mean(0) for i in range(T)])


def corr(a, b):
    a, b = a - a.mean(0), b - b.mean(0)
    return (a * b).sum(0) / np.sqrt((a * a).sum(0) * (b * b).sum(0))


def main():
    for case, folder in CASES.items():
        rows = []
        for lead in range(1, 7):
            files = sorted((folder / f"lead-{lead}").glob("local-CHIRPS3-*-1991-2020.nc"))
            assert len(files) == 1, (case, lead, files)
            with xr.open_dataset(files[0]) as ds:
                y = ds.precipitation.load()
            y = y.where(y > -999)
            valid = y.notnull().all("T")
            r = xr.DataArray(corr(climatology_hindcast(y.values), y.values), dims=("Y", "X"), coords={"Y": y["Y"], "X": y["X"]})
            weights = np.cos(np.deg2rad(y["Y"])) * valid
            rows.append({"lead": lead, "target": files[0].name.split("-")[2] if case == "monthly-2023" else "-".join(files[0].name.split("-")[2:4]),
                         "training_years": int(y.sizes["T"]), "pixels": int(valid.sum()), "window": WINDOW,
                         "no_model_pearson": round(float(r.where(valid).weighted(weights).mean()), 4),
                         "pixel_minimum": round(float(r.where(valid).min()), 4), "pixel_maximum": round(float(r.where(valid).max()), 4)})
        table = pd.DataFrame(rows)
        out = ROOT / "docs" / "data" / case / "no-model-baseline.csv"
        table.to_csv(out, index=False, lineterminator="\n")
        print(case, "->", out.relative_to(ROOT))
        print(table.to_string(index=False))


if __name__ == "__main__":
    main()
