"""When is Indonesian seasonal rainfall predictable, and how far ahead? A scan of start months and leads.

For every start month (the 1st of each month), every lead of 1 to 6 months and every model, this
script downloads the model's hindcasts with PyCPT, builds the matching CHIRPS v3.0 three-month
totals on a 0.25 degree grid (5 x 5 native pixels, Indonesian land only, the grid of the
twelve-season benchmark) and fits CCA through cptcore, the layer PyCPT's evaluate_models calls.
At 0.25 degree a fit takes seconds, so the whole calendar can be measured before choosing
which case to run at 0.05 degree.

Variants:
  base        model rainfall over 85-155E, 20S-20N; 3 X EOFs, 3 Y EOFs, 2 CCA modes (the cases' settings)
  search      the same data; CPT chooses the modes within X 1-8, Y 1-6, CCA 1-3
  sst         model sea surface temperature over 40E-280E, 30S-30N; fixed modes as in base
  sst-search  the SST predictor with the mode search

Per job it keeps the cross-validated deterministic hindcasts, so the multi-model mean, the
no-model baseline and the cross-validated RPSS are computed afterwards on one footing.
Training target years 1992-2020. Nothing is tuned on a verification year.

    python research/scripts/skill_calendar_scan.py --out temp/audits/skill-calendar [--workers 24] [--variants base search]
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import multiprocessing
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

os.environ.setdefault("CPT_BIN_DIR", str(Path(sys.prefix) / "opt" / "cpt" / "bin"))
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MODELS = ["CFSv2", "GEOSS2S", "CanSIPSIC3", "CCSM4", "CESM1", "SPEAR", "SEAS51c"]
TRAINING = (1992, 2020)
LEADS = [1, 2, 3, 4, 5, 6]
PREDICTAND_BOX = {"west": 94, "east": 142, "south": -12, "north": 7}
FIXED = {"cca_modes": (2, 2), "x_eof_modes": (3, 3), "y_eof_modes": (3, 3)}
SEARCH = {"cca_modes": (1, 3), "x_eof_modes": (1, 8), "y_eof_modes": (1, 6)}
VARIANTS = {
    "base": ("PRCP", {"west": 85, "east": 155, "south": -20, "north": 20}, FIXED),
    "search": ("PRCP", {"west": 85, "east": 155, "south": -20, "north": 20}, SEARCH),
    "sst": ("SST", {"west": 40, "east": 280, "south": -30, "north": 30}, FIXED),
    "sst-search": ("SST", {"west": 40, "east": 280, "south": -30, "north": 30}, SEARCH),
}
COMMON = {"transform_predictand": None, "tailoring": None, "validation": "crossvalidation", "drymask_threshold": None,
          "skillmask_threshold": None, "crossvalidation_window": 5, "synchronous_predictors": True}
CHIRPS = Path("/mnt/e/temp/chirps/dekad/wld_cli_chirps3_dekad_1981_2025.nc")
CASE_ROOT = Path.home() / "PyCPT" / "indonesia-skill-calendar"
TOTALS = {}          # (year, month of the first day) -> 0.25 degree three-month total; filled in the parent, shared by fork


def target_name(start_month, lead):
    first = (start_month - 1 + lead) % 12
    return f"{MONTHS[first]}-{MONTHS[(first + 2) % 12]}"


def build_totals():
    """Three-month CHIRPS v3.0 totals on the 0.25 degree Indonesian land grid, for every season start 1991-2021."""
    import numpy as np
    import pandas as pd
    import shapely
    import xarray as xr
    import cartopy.io.shapereader as shapereader
    from pycpt_tutorial.country_grid import aggregate_country_rainfall

    source = xr.open_dataset(CHIRPS)
    bounds = pd.DatetimeIndex(source.time_bnds.values.ravel()).values.reshape(-1, 2)
    first_days, end_days = pd.DatetimeIndex(bounds[:, 0]), pd.DatetimeIndex(bounds[:, 1])
    box = PREDICTAND_BOX
    region = source.precip.sel(lon=slice(box["west"], box["east"]), lat=slice(box["south"], box["north"]))
    region = region.isel(lat=slice(0, region.sizes["lat"] // 5 * 5), lon=slice(0, region.sizes["lon"] // 5 * 5))
    records = shapereader.Reader(shapereader.natural_earth("10m", "cultural", "admin_0_countries")).records()
    indonesia = next(r.geometry for r in records if r.attributes["ADM0_A3"] == "IDN")
    shapely.prepare(indonesia)
    lon2d, lat2d = np.meshgrid(region.lon, region.lat)
    country = xr.DataArray(shapely.contains_xy(indonesia, lon2d, lat2d), dims=("lat", "lon"), coords={"lat": region.lat, "lon": region.lon})
    for year in range(TRAINING[0] - 2, TRAINING[1] + 2):
        for month in range(1, 13):
            first = pd.Timestamp(year, month, 1)
            end = first + pd.DateOffset(months=3)
            index = np.flatnonzero((first_days >= first) & (end_days <= end))
            assert len(index) == 9 and first_days[index[0]] == first and end_days[index[-1]] == end, (year, month)
            total = region.isel(time=index).sum("time", skipna=False).load()
            block = aggregate_country_rainfall(total, country, 5, minimum_coverage=.99).precipitation
            block = block.rename({"lat": "Y", "lon": "X"})
            block = block.assign_coords(Y=np.round(block["Y"].values.astype(float), 3), X=np.round(block["X"].values.astype(float), 3))
            TOTALS[year, month] = block.sortby("Y", ascending=False).astype("float32")


def fit(job):
    """One (start month, lead, model, variant). Returns a status record; never raises."""
    out, start_month, lead, model, variant = job
    record = {"start_month": start_month, "lead": lead, "model": model, "variant": variant, "target": target_name(start_month, lead)}
    result = Path(out) / "fits" / f"{variant}-start{start_month:02d}-lead{lead}-{model}.npz"
    t0 = time.monotonic()
    try:
        import numpy as np
        import pandas as pd
        import xarray as xr
        import pycpt
        from pycpt import notebook as pycpt_notebook
        from cptcore import canonical_correlation_analysis

        if result.exists():
            with np.load(result, allow_pickle=False) as z:
                return dict(record, status="reused", **json.loads(str(z["record"])))
        variable, extent, modes = VARIANTS[variant]
        name = f"{model}.{variable}"
        args = dict(fdate=dt.datetime(2023, start_month, 1), target=record["target"], target_first_year=TRAINING[0],
                    target_final_year=TRAINING[1], predictor_extent=extent, predictand_extent=PREDICTAND_BOX)
        with contextlib.redirect_stdout(io.StringIO()):
            domain_dir = pycpt.setup(CASE_ROOT / f"start-{start_month:02d}" / f"lead-{lead}", extent)
            X = pycpt_notebook.download_hindcasts([name], domain_dir, False, args)[0]
        first, last = (MONTHS.index(m) + 1 for m in record["target"].split("-"))
        years = [int(y) for y in X["T"].dt.year.values]
        problems = []
        if years != list(range(TRAINING[0], TRAINING[1] + 1)) or not X.where(X > -999).notnull().any(("Y", "X")).values.all():
            problems.append("training years missing")
        if [int(X["Ti"].dt.month.values[0]), int(X["Tf"].dt.month.values[0])] != [first, last]:
            problems.append(f"returned months {int(X['Ti'].dt.month.values[0])}-{int(X['Tf'].dt.month.values[0])}")
        if problems:
            return dict(record, status="unavailable", reason="; ".join(problems), seconds=round(time.monotonic() - t0, 1))

        Y = xr.concat([TOTALS[pd.Timestamp(a).year, pd.Timestamp(a).month] for a in X["Ti"].values], dim=pd.Index(X["T"].values, name="T"))
        assert all(pd.Timestamp(b) + pd.Timedelta(days=1) == pd.Timestamp(a) + pd.DateOffset(months=3) for a, b in zip(X["Ti"].values, X["Tf"].values))
        cells = Y.notnull().all("T")
        Y = Y.where(cells).assign_coords(Ti=("T", X["Ti"].values), Tf=("T", X["Tf"].values)).transpose("T", "Y", "X").rename("precipitation")
        Y.attrs = {"units": "mm", "missing": -999.0}
        t1 = time.monotonic()
        with contextlib.redirect_stdout(io.StringIO()):
            hindcast, _, skill, px, py = canonical_correlation_analysis(X, Y, F=None, **COMMON, **modes)
        fit_seconds = time.monotonic() - t1
        flat = np.flatnonzero(cells.values.ravel())
        pix = lambda a: a.reindex(Y=Y["Y"], X=Y["X"], method="nearest", tolerance=1e-3).transpose(..., "Y", "X").values.reshape(a.shape[:-2] + (-1,))[..., flat]
        h = pix(hindcast.deterministic.where(hindcast.deterministic > -999)).astype("float32")
        o = pix(Y).astype("float32")
        raw = None
        if variable == "PRCP":
            raw = X.where(X > -999).interp(Y=Y["Y"], X=Y["X"], method="linear").transpose("T", "Y", "X").values.reshape(len(years), -1)[:, flat].astype("float32")
        weight = np.cos(np.deg2rad(np.repeat(Y["Y"].values, Y.sizes["X"])[flat]))
        mean = lambda v: float(np.nansum(v * weight) / weight[np.isfinite(v)].sum())
        retained = lambda scores: int(np.isfinite(scores.where(scores > -999).values).any(axis=0).sum())
        summary = {"cells": int(len(flat)), "fit_seconds": round(fit_seconds, 1),
                   "pearson": mean(pix(skill.pearson.where(skill.pearson > -999))),
                   "afc": mean(pix(skill.two_alternative_forced_choice.where(skill.two_alternative_forced_choice > -999))),
                   "x_eof_modes": retained(px.x_eof_scores), "y_eof_modes": retained(py.y_eof_scores), "cca_modes": retained(px.x_cca_scores),
                   "first_start": str(X["S"].values[0])[:10], "grid_degrees": float(abs(X["X"].diff("X")).mean())}
        result.parent.mkdir(parents=True, exist_ok=True)
        tmp = result.with_suffix(".part.npz")
        arrays = dict(h=h, o=o, weight=weight.astype("float32"), flat=flat.astype("int32"), record=json.dumps(summary))
        if raw is not None:
            arrays["raw"] = raw
        np.savez_compressed(tmp, **arrays)
        tmp.replace(result)
        return dict(record, status="fitted", seconds=round(time.monotonic() - t0, 1), **summary)
    except Exception as error:
        if "Expected data with a" in str(error):          # PyCPT's message when a model has no forecast that far ahead
            return dict(record, status="unavailable", reason="lead beyond the model's range", seconds=round(time.monotonic() - t0, 1))
        return dict(record, status="failed", seconds=round(time.monotonic() - t0, 1), error=f"{type(error).__name__}: {str(error)[:300]}",
                    traceback=traceback.format_exc().splitlines()[-8:])


def corr(a, b):
    import numpy as np
    a, b = a - a.mean(0), b - b.mean(0)
    return (a * b).sum(0) / np.sqrt((a * a).sum(0) * (b * b).sum(0))


def cv_rps(hindcast, observed, window=5):
    """Ranked probability score of leave-window-out tercile probabilities, summed over years, per cell (as the MME notebook)."""
    import numpy as np
    from scipy.stats import t as student_t
    T, half = observed.shape[0], window // 2
    error, rps = hindcast - observed, np.zeros(observed.shape[1])
    for i in range(T):
        keep = np.setdiff1d(np.arange(T), [(i + k) % T for k in range(-half, half + 1)])
        lower, upper = np.quantile(observed[keep], [0.33, 0.67], axis=0, method="hazen")
        scale = np.sqrt((error[keep] ** 2).mean(0))
        below = student_t.cdf((lower - hindcast[i]) / scale, len(keep) - 1)
        not_above = student_t.cdf((upper - hindcast[i]) / scale, len(keep) - 1)
        rps += (below - (observed[i] < lower)) ** 2 + (not_above - (observed[i] <= upper)) ** 2
    return rps


def climatology_hindcast(observed, window=5):
    import numpy as np
    T, half = observed.shape[0], window // 2
    return np.stack([observed[np.setdiff1d(np.arange(T), [(i + k) % T for k in range(-half, half + 1)])].mean(0) for i in range(T)])


def summarise(out, records):
    """Per (variant, start, lead): every member, the multi-model mean, the raw mean and the no-model baseline."""
    import numpy as np
    import pandas as pd
    rows = []
    good = [r for r in records if r["status"] in ("fitted", "reused")]
    for variant in sorted({r["variant"] for r in good}):
        for start_month in range(1, 13):
            for lead in LEADS:
                mine = [r for r in good if (r["variant"], r["start_month"], r["lead"]) == (variant, start_month, lead)]
                if not mine:
                    continue
                data = {r["model"]: np.load(Path(out) / "fits" / f"{variant}-start{start_month:02d}-lead{lead}-{r['model']}.npz") for r in mine}
                first = next(iter(data.values()))
                o, w = first["o"].astype("float64"), first["weight"].astype("float64")
                mean = lambda v: float(np.nansum(v * w) / w[np.isfinite(v)].sum())
                reference = cv_rps(climatology_hindcast(o), o)
                base = {"variant": variant, "start_month": start_month, "start": MONTHS[start_month - 1], "lead": lead,
                        "target": mine[0]["target"], "members": len(mine)}
                for r in mine:
                    h = data[r["model"]]["h"].astype("float64")
                    rows.append(dict(base, forecast=r["model"], pearson=r["pearson"], afc=r["afc"], cv_rpss=mean(1 - cv_rps(h, o) / reference),
                                     raw_pearson=mean(corr(data[r["model"]]["raw"].astype("float64"), o)) if "raw" in data[r["model"]] else np.nan,
                                     x_eof_modes=r["x_eof_modes"], y_eof_modes=r["y_eof_modes"], cca_modes=r["cca_modes"]))
                mme = np.mean([data[m]["h"].astype("float64") for m in data], axis=0)
                raw_mean = np.mean([data[m]["raw"].astype("float64") for m in data], axis=0) if "raw" in first else None
                rows.append(dict(base, forecast="MME", pearson=mean(corr(mme, o)), cv_rpss=mean(1 - cv_rps(mme, o) / reference),
                                 raw_pearson=mean(corr(raw_mean, o)) if raw_mean is not None else np.nan))
                rows.append(dict(base, forecast="no model", pearson=mean(corr(climatology_hindcast(o), o)), cv_rpss=0.0))
    table = pd.DataFrame(rows)
    table.round(4).to_csv(Path(out) / "skill-calendar.csv", index=False)
    return table


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--variants", nargs="*", default=["base"])
    parser.add_argument("--starts", nargs="*", type=int, default=list(range(1, 13)))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    build_totals()
    print(f"observations: {len(TOTALS)} three-month totals in {time.monotonic() - t0:.0f} s", flush=True)
    jobs = [(str(args.out), s, lead, model, variant) for variant in args.variants for s in args.starts for lead in LEADS
            for model in MODELS if not (VARIANTS[variant][0] == "SST" and model == "CESM1")]      # the catalog has no CESM1.SST
    records = []
    log = args.out / "records.jsonl"
    old = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context("fork")) as pool, open(log, "a") as handle:
        for n, record in enumerate(pool.map(fit, jobs), 1):
            records.append(record)
            handle.write(json.dumps(record) + "\n")
            handle.flush()
            if record["status"] != "reused" and (n % 20 == 0 or record["status"] == "failed"):
                print(n, len(jobs), json.dumps({k: record.get(k) for k in ("variant", "start_month", "lead", "model", "status", "pearson", "seconds", "reason", "error")}), flush=True)
    done = {(r["variant"], r["start_month"], r["lead"], r["model"]) for r in records}
    records += [r for r in old if (r["variant"], r["start_month"], r["lead"], r["model"]) not in done and r["status"] in ("fitted", "reused")
                and (Path(args.out) / "fits" / f"{r['variant']}-start{r['start_month']:02d}-lead{r['lead']}-{r['model']}.npz").exists()]
    counts = {}
    for r in records:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("status:", counts, f"| {(time.monotonic() - t0) / 60:.1f} min", flush=True)
    table = summarise(args.out, records)
    print("wrote", args.out / "skill-calendar.csv", len(table), "rows")


if __name__ == "__main__":
    main()
