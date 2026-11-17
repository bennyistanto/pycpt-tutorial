"""Which subseasonal models add skill over Indonesia, and at which lead? A scan at 0.25 degree before any 0.05 degree fit.

Five SubX models on the IRI Data Library have hindcasts and 2023 runs (temp/audits/subseasonal-value-check):
GEFSv12_CPC, CFSv2, GEOS_V2p1, CCSM4 and FIMr1p1. They do not start on the same days, so a multi-model
forecast needs a rule for which run of each model answers a given issue date. This script applies one rule,
records what it implies for every model, and measures the cross-validated skill of each model and of their
equal-weight mean for the weekly targets of the single-model case (research/scripts/download_gefs_weeks.py).

Design
  * Issue dates are Wednesdays; targets are the 7-day windows starting on a Thursday in October-December,
    week 1 = days 1-7 after the issue, week 2 = 8-14, week 3 = 15-21, week 4 = 22-28, weeks 3-4 = 15-28.
  * Training years 2000-2016: the years all five hindcast sets cover and the local daily CHIRPS v3.0 has.
  * Start rule: the model's latest run on or before the issue date, at most 6 days earlier. The target
    days are the same calendar days for every model, so a model that started earlier is used at a
    longer lead. The lag is recorded per sample.
      GEFSv12_CPC, FIMr1p1  Wednesday runs: lag 0.
      GEOS_V2p1             a run every 5 days: lag 0-4 days.
      CCSM4                 runs on two fixed neighbouring calendar days a week (the weekday moves from
                            year to year): lag 0-6 days.
      CFSv2                 one run every 6 hours, one member each: the four runs from 06 UTC the day
                            before to 00 UTC on the issue date, averaged. A run that does not start at
                            00 UTC has 24-hour slots that do not match calendar days; the slot whose
                            centre is nearest the target day's centre is used (shift at most 6 hours).
  * Predictor: ensemble-mean total over the target days, 85-155E, 20S-20N. Predictand: CHIRPS v3.0
    window totals averaged over the Indonesian 0.05 degree pixels (supplied province boundary, every
    pixel a province touches) of each 0.25 degree block.
  * Both as anomalies from a mean over the training years (one target per year, nearest in season day),
    as in the weekly case. CCA through cptcore, 3 X EOFs, 3 Y EOFs, 2 CCA modes, cross-validation
    window 27 (a year holds 13 or 14 targets). Nothing is tuned.
  * Kept per fit: the cross-validated hindcasts, so the multi-model mean, the raw-model correlation,
    the no-model baseline and a cross-validated RPSS are computed afterwards on one footing.

Stages (each resumable):
    python research/scripts/subseasonal_skill_scan.py --stage download [--threads 4]
    python research/scripts/subseasonal_skill_scan.py --stage totals
    python research/scripts/subseasonal_skill_scan.py --stage fit [--workers 25]
    python research/scripts/subseasonal_skill_scan.py --stage summary
    python research/scripts/subseasonal_skill_scan.py --stage all

Raw model files go to --data (default ~/PyCPT/indonesia-subseasonal-scan), records and tables to --out.
Uses the IRI Data Library key PyCPT already reads (never printed); anonymous if none is configured.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import math
import multiprocessing
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

os.environ.setdefault("CPT_BIN_DIR", str(Path(sys.prefix) / "opt" / "cpt" / "bin"))
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import download_gefs_dekads as gefs_source  # noqa: E402
import download_gefs_weeks as weeks  # noqa: E402
from skill_calendar_scan import corr  # noqa: E402

BASE = "https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX"
# model: (dataset, hindcast branch, factor to mm per day)
MODELS = {
    "GEFSv12_CPC": ("/.EMC/.GEFSv12_CPC", "/.hindcast/.weekly/.pr", 1.0),
    "CFSv2": ("/.NCEP/.CFSv2", "/.hindcast/.pr", 86400.0),
    "GEOS_V2p1": ("/.GMAO/.GEOS_V2p1", "/.hindcast/.pr", 86400.0),
    "CCSM4": ("/.RSMAS/.CCSM4", "/.hindcast/.pr", 86400.0),
    "FIMr1p1": ("/.ESRL/.FIMr1p1", "/.hindcast/.pr", 86400.0),
}
UNITS = {"GEFSv12_CPC": "kg m-2"}
YEARS = list(range(2000, 2017))
LEADS = weeks.LEADS                      # name -> (first day after the issue, number of days)
BOX = gefs_source.BOX
MAX_LAG_DAYS = 6
CFSV2_HOURS_BEFORE = (18, 12, 6, 0)
SETTINGS = {"transform_predictand": None, "tailoring": None, "validation": "crossvalidation", "drymask_threshold": None,
            "skillmask_threshold": None, "crossvalidation_window": 27, "synchronous_predictors": True,
            "cca_modes": (2, 2), "x_eof_modes": (3, 3), "y_eof_modes": (3, 3)}
DAILY = Path("/mnt/e/temp/chirps/daily-idn")
PROVINCES = Path(os.environ.get("IDN_PROVINCE_FILE", "/mnt/f/temp/hybrid-bias-correction/data/subset/bnd/idn_bnd_adm1"))
GEFS_CACHE = Path.home() / "PyCPT" / "indonesia-ond-2023-dekads" / "gefs"
EPOCH = dt.datetime(1960, 1, 1)


def design():
    """Training rows of the weekly case, 2000-2016: target, lead, issue date (a Wednesday), first day and days."""
    return [r for r in weeks.design() if r["kind"] == "hindcast" and r["year"] in YEARS]


def catalog(folder):
    """{model: sorted starts that hold values}, from the value check's records."""
    out = {}
    for model in MODELS:
        rows = json.loads((Path(folder) / f"{model}.json").read_text())["rows"]
        starts = [dt.datetime.fromisoformat(s) for r in rows if r["kind"] == "hindcast" and r.get("ok") for s in r["starts"]]
        out[model] = sorted(set(starts))
    return out


def selected_starts(model, issue, have):
    """The run or runs of the model that answer an issue date; [] when the rule finds none."""
    at = dt.datetime.combine(issue, dt.time())
    if model == "CFSv2":
        want = [at - dt.timedelta(hours=h) for h in CFSV2_HOURS_BEFORE]
        return want if all(w in have for w in want) else []
    near = [s for s in have if at - dt.timedelta(days=MAX_LAG_DAYS) <= s <= at]
    return [max(near)] if near else []


def raw_path(data, model, issue):
    if model == "GEFSv12_CPC":
        return gefs_source.path_for(GEFS_CACHE, "hindcast", issue)
    return Path(data) / "raw" / model / f"{model}-{issue.isoformat()}.nc"


def label(s):
    return f"{s:%H%M} {s.day} {s:%b} {s.year}".replace(" ", "%20")


def url_for(model, starts):
    dataset, branch, _ = MODELS[model]
    s = f"/S/({label(starts[0])})/({label(starts[-1])})/RANGE" if len(starts) > 1 else f"/S/({label(starts[0])})/VALUES"
    return BASE + dataset + branch + s + f"/X/{BOX['west']}/{BOX['east']}/RANGE/Y/{BOX['south']}/{BOX['north']}/RANGE/data.nc"


def slots(start, first_day, days):
    """Lead slot (L, in days) of each target day for a run started at `start`; the issue is start's date plus the lag."""
    return [math.floor((first_day - start).total_seconds() / 86400 + k + 0.5) + 0.5 for k in range(days)]


def open_raw(path):
    import numpy as np
    import xarray as xr
    with xr.open_dataset(path, decode_times=False) as ds:
        pr = ds["pr"].load()
        starts = [EPOCH + dt.timedelta(days=float(s)) for s in np.atleast_1d(ds["S"].values)]
    return pr, starts


def check_raw(path, model, starts, need_slots):
    """None when the file holds every run and lead slot the targets need, with finite values; else the reason."""
    import numpy as np
    try:
        pr, got = open_raw(path)
        if got != starts:
            return f"starts {got}"
        if pr.attrs.get("units") != UNITS.get(model, "kg m-2 s-1"):
            return f"units {pr.attrs.get('units')!r}"
        if pr.sizes.get("X") != BOX["east"] - BOX["west"] + 1 or pr.sizes.get("Y") != BOX["north"] - BOX["south"] + 1:
            return f"grid {pr.sizes.get('Y')} x {pr.sizes.get('X')}"
        for i, s in enumerate(starts):
            want = sorted(need_slots[s])
            if not np.isin(want, pr["L"].values).all():
                return f"lead slots end at {float(pr['L'].max())}, need {want[-1]}"
            if not np.isfinite(pr.isel(S=i).sel(L=want).values).all():
                return "missing values in the needed days"
    except Exception as e:
        return f"unreadable ({type(e).__name__}: {str(e)[:80]})"
    return None


def plan(cat):
    """{(model, issue): {"starts": [...], "slots": {start: set of L}, "rows": [design rows served]}} and the rows the rule cannot serve."""
    jobs, unserved = {}, []
    for r in design():
        issue = r["start"]
        first = dt.datetime.combine(r["target"], dt.time())
        for model in MODELS:
            starts = selected_starts(model, issue, cat[model])
            if not starts:
                unserved.append({"model": model, "lead": r["lead"], "target": r["target"].isoformat(), "reason": "no run within the lag window"})
                continue
            job = jobs.setdefault((model, issue), {"starts": starts, "slots": {s: set() for s in starts}, "rows": []})
            for s in starts:
                job["slots"][s].update(slots(s, first, r["days"]))
            job["rows"].append(r)
    return jobs, unserved


def download(args, jobs):
    import requests
    try:
        from cptdl.utilities import read_dlauth
        key = read_dlauth() or ""
    except Exception:
        key = ""
    todo = [(k, j) for k, j in jobs.items() if k[0] != "GEFSv12_CPC"
            and not (raw_path(args.data, *k).exists() and check_raw(raw_path(args.data, *k), k[0], j["starts"], j["slots"]) is None)]
    print(f"download: {len(jobs)} files planned, {len(todo)} to fetch", flush=True)
    log = args.out / "download-log.jsonl"

    def one(item):
        (model, issue), job = item
        path = raw_path(args.data, model, issue)
        path.parent.mkdir(parents=True, exist_ok=True)
        url, t0, problem = url_for(model, job["starts"]), time.monotonic(), None
        for attempt in range(1, 6):
            try:
                r = requests.get(url, cookies={"__dlauth_id": key} if key else None, timeout=600,
                                 headers={"User-Agent": "python-requests subseasonal scan"})
                if "/auth/login" in r.url:
                    return {"model": model, "issue": issue.isoformat(), "ok": False, "problem": "sign-in required"}
                if r.status_code != 200 or not (r.content.startswith(b"CDF") or r.content.startswith(b"\x89HDF")):
                    raise ValueError(f"HTTP {r.status_code}, not NetCDF")
                tmp = path.with_suffix(".part")
                tmp.write_bytes(r.content)
                tmp.replace(path)
                problem = check_raw(path, model, job["starts"], job["slots"])
                break
            except Exception as e:
                problem = f"{type(e).__name__}: {str(e)[:120]}"
                time.sleep(15 * attempt)
        return {"model": model, "issue": issue.isoformat(), "ok": problem is None, "problem": problem,
                "bytes": path.stat().st_size if path.exists() else 0, "seconds": round(time.monotonic() - t0, 1), "url": url}

    bad = 0
    with ThreadPoolExecutor(args.threads) as pool, open(log, "a") as handle:
        for n, rec in enumerate(pool.map(one, todo), 1):
            handle.write(json.dumps(rec) + "\n")
            handle.flush()
            bad += not rec["ok"]
            if not rec["ok"] or n % 50 == 0:
                print(n, len(todo), json.dumps({k: rec[k] for k in ("model", "issue", "ok", "problem", "seconds")}), flush=True)
    print(f"download: fetched {len(todo) - bad}, failed {bad}", flush=True)


def totals(args, jobs, unserved):
    """Per model: ensemble-mean window totals (mm) for every target and lead, with the lag of each sample."""
    import numpy as np
    import pandas as pd
    import xarray as xr
    rows, fields = [], {}
    for (model, issue), job in sorted(jobs.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        path = raw_path(args.data, model, issue)
        problem = check_raw(path, model, job["starts"], job["slots"]) if path.exists() else "file missing"
        if problem and model == "GEFSv12_CPC" and path.exists():       # the cached files start at day 1 and are checked by their own rule
            problem = gefs_source.check(path, "hindcast", issue, max(r["last_day"] for r in job["rows"]))
        if problem:
            unserved += [{"model": model, "lead": r["lead"], "target": r["target"].isoformat(), "reason": problem} for r in job["rows"]]
            continue
        pr, _ = open_raw(path)
        factor = MODELS[model][2]
        for r in job["rows"]:
            first = dt.datetime.combine(r["target"], dt.time())
            per_start = []
            for i, s in enumerate(job["starts"]):
                d = pr.isel(S=i).sel(L=slots(s, first, r["days"])).sum("L", skipna=False) * factor
                per_start.append(d.mean("M", skipna=False) if "M" in d.dims else d)
            field = sum(per_start) / len(per_start)
            fields[model, r["lead"], r["target"]] = field.sortby("Y", ascending=False).astype("float32")
            lag = (dt.datetime.combine(issue, dt.time()) - max(job["starts"])).total_seconds() / 86400
            rows.append({"model": model, "lead": r["lead"], "target": r["target"].isoformat(), "issue": issue.isoformat(),
                         "runs": len(job["starts"]), "members": int(pr.sizes.get("M", 1)) * len(job["starts"]), "lag_days": lag,
                         "last_slot": max(max(v) for v in job["slots"].values()), "negative_values": int((field < 0).sum())})
    folder = Path(args.data) / "totals"
    folder.mkdir(parents=True, exist_ok=True)
    for model in MODELS:
        ds = xr.Dataset()
        for lead in LEADS:
            targets = sorted(t for (m, l, t) in fields if (m, l) == (model, lead))
            if targets:
                ds[lead] = xr.concat([fields[model, lead, t].drop_vars([c for c in fields[model, lead, t].coords if c not in ("Y", "X")])
                                      for t in targets], pd.Index(pd.to_datetime(targets), name=f"T_{lead}"))
        ds.to_netcdf(folder / f"{model}.nc")
    table = pd.DataFrame(rows)
    table.to_csv(args.out / "samples.csv", index=False)
    pd.DataFrame(unserved).to_csv(args.out / "unserved.csv", index=False)
    lag = table.groupby("model").agg(samples=("target", "size"), runs=("runs", "max"), members=("members", "max"),
                                     lag_min=("lag_days", "min"), lag_mean=("lag_days", "mean"), lag_max=("lag_days", "max"),
                                     last_slot=("last_slot", "max"), negative_values=("negative_values", "sum"))
    lag.round(2).to_csv(args.out / "start-rule.csv")
    print(lag.round(2).to_string(), flush=True)
    print(f"totals: {len(table)} samples; not served: {len(unserved)}", flush=True)


def observations(args):
    """CHIRPS v3.0 7-day and 14-day totals on the 0.25 degree grid for every training target; cached."""
    import numpy as np
    import pandas as pd
    import xarray as xr
    from pycpt_tutorial.country_grid import aggregate_country_rainfall, read_provinces, touching_pixels
    cache = Path(args.data) / "observations-0p25.nc"
    if cache.exists():
        return xr.open_dataset(cache).load()
    files = [DAILY / f"chirps3_rnl_daily_idn_{y}.nc" for y in YEARS + [YEARS[-1] + 1]]
    assert all(f.exists() for f in files), [f.name for f in files if not f.exists()]
    source = xr.open_mfdataset(files, combine="by_coords")
    daily = source.precip.sel(time=source.time.dt.month.isin([10, 11, 12, 1])).load().sortby("lat")
    step = float(daily.lon[1] - daily.lon[0])

    def aligned(coord):                      # first index whose pixel edge lies on a 0.25 degree line, then whole blocks of 5
        edge = (coord.values - step / 2) / (5 * step)
        first = int(np.flatnonzero(np.abs(edge - np.round(edge)) < 1e-3)[0])
        return slice(first, first + (coord.size - first) // 5 * 5)

    daily = daily.isel(lat=aligned(daily.lat), lon=aligned(daily.lon))
    touching, _ = touching_pixels(daily.lon.values, daily.lat.values, read_provinces(PROVINCES))
    country = xr.DataArray(touching, dims=("lat", "lon"), coords={"lat": daily.lat, "lon": daily.lon})
    out = xr.Dataset()
    for days in (7, 14):
        targets = sorted({r["target"] for r in design() if r["days"] == days})
        blocks = []
        for t in targets:
            window = daily.sel(time=slice(pd.Timestamp(t), pd.Timestamp(t) + pd.Timedelta(days=days - 1)))
            assert window.sizes["time"] == days, (t, window.sizes["time"])
            block = aggregate_country_rainfall(window.sum("time", skipna=False), country, 5, minimum_coverage=.99).precipitation
            blocks.append(block.rename({"lat": "Y", "lon": "X"}))
        a = xr.concat(blocks, pd.Index(pd.to_datetime(targets), name=f"T_{days}"))
        out[f"total_{days}"] = a.assign_coords(Y=np.round(a["Y"].values.astype(float), 3), X=np.round(a["X"].values.astype(float), 3)).sortby("Y", ascending=False).astype("float32")
    out.attrs["country_pixels_005"] = int(touching.sum())
    out.to_netcdf(cache)
    return out


def season_day(t):
    return (t - dt.datetime(t.year, 10, 1)).days


def anomalies(field, dim):
    """Anomaly from the mean of one target per training year, the one nearest in season day (as the weekly case)."""
    import numpy as np
    import pandas as pd
    dates = [pd.Timestamp(t).to_pydatetime() for t in field[dim].values]
    by_year = {}
    for j, t in enumerate(dates):
        by_year.setdefault(t.year, []).append(j)
    W = np.zeros((len(dates), len(dates)))
    for i, t in enumerate(dates):
        for idx in by_year.values():
            W[i, idx[int(np.argmin([abs(season_day(dates[j]) - season_day(t)) for j in idx]))]] = 1 / len(by_year)
    a = field.transpose(dim, ...).values
    clim = (W @ np.nan_to_num(a.reshape(len(dates), -1))).reshape(a.shape)
    return field.transpose(dim, ...).copy(data=(a - clim).astype("float32"))


def cpt_ready(a, dim):
    import numpy as np
    import pandas as pd
    years = 1701 + np.arange(a.sizes[dim])
    a = a.rename({dim: "T"}).transpose("T", "Y", "X")
    a = a.assign_coords(T=pd.to_datetime([f"{y}-10-04" for y in years]), Ti=("T", pd.to_datetime([f"{y}-10-01" for y in years])),
                        Tf=("T", pd.to_datetime([f"{y}-10-07" for y in years]))).rename("anomaly")
    a.attrs = {"units": "mm", "missing": -999.0}
    return a


def fit(job):
    """One (model, lead). Returns a status record; never raises."""
    data, out, model, lead = job
    record = {"model": model, "lead": lead}
    result = Path(out) / "fits" / f"{lead}-{model}.npz"
    t0 = time.monotonic()
    try:
        import numpy as np
        import pandas as pd
        import xarray as xr
        from cptcore import canonical_correlation_analysis
        if result.exists():
            with np.load(result, allow_pickle=False) as z:
                return dict(record, status="reused", **json.loads(str(z["record"])))
        days = LEADS[lead][1]
        with xr.open_dataset(Path(data) / "totals" / f"{model}.nc") as ds:
            if lead not in ds:
                return dict(record, status="unavailable", reason="no samples")
            x = ds[lead].load()
        with xr.open_dataset(Path(data) / "observations-0p25.nc") as ds:
            y = ds[f"total_{days}"].load().rename({f"T_{days}": "T"})
        x = x.rename({f"T_{lead}": "T"})
        common = np.intersect1d(x["T"].values, y["T"].values)
        per_year = pd.Series(1, index=pd.DatetimeIndex(common)).groupby(lambda t: t.year).size()
        if sorted(per_year.index) != YEARS:
            return dict(record, status="unavailable", reason=f"training years with samples: {sorted(per_year.index)}")
        x, y = x.sel(T=common), y.sel(T=common)
        cells = y.notnull().all("T")
        xa, ya = anomalies(x, "T"), anomalies(y, "T").where(cells)
        X, Y = cpt_ready(xa, "T"), cpt_ready(ya, "T")
        t1 = time.monotonic()
        with contextlib.redirect_stdout(io.StringIO()):
            hindcast, _, skill, px, py = canonical_correlation_analysis(X, Y, F=None, **SETTINGS)
        fit_seconds = time.monotonic() - t1
        flat = np.flatnonzero(cells.values.ravel())
        pix = lambda a: a.reindex(Y=Y["Y"], X=Y["X"], method="nearest", tolerance=1e-3).transpose(..., "Y", "X").values.reshape(a.shape[:-2] + (-1,))[..., flat]
        h = pix(hindcast.deterministic.where(hindcast.deterministic > -999)).astype("float32")
        o = pix(Y).astype("float32")
        raw = X.interp(Y=Y["Y"], X=Y["X"], method="linear").transpose("T", "Y", "X").values.reshape(len(common), -1)[:, flat].astype("float32")
        weight = np.cos(np.deg2rad(np.repeat(Y["Y"].values, Y.sizes["X"])[flat]))
        mean = lambda v: float(np.nansum(v * weight) / weight[np.isfinite(v)].sum())
        cpt_r = pix(skill.pearson.where(skill.pearson > -999))
        summary = {"cells": int(len(flat)), "samples": int(len(common)), "samples_per_year": [int(per_year.min()), int(per_year.max())],
                   "fit_seconds": round(fit_seconds, 1), "pearson": mean(cpt_r),
                   "largest_gap_cpt_vs_recomputed_pearson": float(np.nanmax(np.abs(cpt_r - corr(h.astype("float64"), o.astype("float64"))))),
                   "afc": mean(pix(skill.two_alternative_forced_choice.where(skill.two_alternative_forced_choice > -999))),
                   "hindcast_values_missing": int((~np.isfinite(h)).sum())}
        result.parent.mkdir(parents=True, exist_ok=True)
        tmp = result.with_suffix(".part.npz")
        np.savez_compressed(tmp, h=h, o=o, raw=raw, weight=weight.astype("float32"), flat=flat.astype("int32"),
                            targets=np.array([str(t)[:10] for t in common]), record=json.dumps(summary))
        tmp.replace(result)
        return dict(record, status="fitted", seconds=round(time.monotonic() - t0, 1), **summary)
    except Exception as error:
        return dict(record, status="failed", seconds=round(time.monotonic() - t0, 1), error=f"{type(error).__name__}: {str(error)[:300]}",
                    traceback=traceback.format_exc().splitlines()[-8:])


def cv_rps(hindcast, observed, years):
    """Ranked probability score of leave-one-year-out tercile probabilities, summed over samples, per cell."""
    import numpy as np
    from scipy.stats import t as student_t
    error, rps = hindcast - observed, np.zeros(observed.shape[1])
    for year in np.unique(years):
        keep, out = years != year, np.flatnonzero(years == year)
        lower, upper = np.quantile(observed[keep], [0.33, 0.67], axis=0, method="hazen")
        scale = np.sqrt((error[keep] ** 2).mean(0))
        for i in out:
            below = student_t.cdf((lower - hindcast[i]) / scale, keep.sum() - 1)
            not_above = student_t.cdf((upper - hindcast[i]) / scale, keep.sum() - 1)
            rps += (below - (observed[i] < lower)) ** 2 + (not_above - (observed[i] <= upper)) ** 2
    return rps


def summarise(args, records):
    """Per lead: every model, their equal-weight mean on the targets all of them have, the raw means and the no-model baseline."""
    import numpy as np
    import pandas as pd
    rows = []
    good = [r for r in records if r["status"] in ("fitted", "reused")]
    for lead in LEADS:
        mine = [r for r in good if r["lead"] == lead]
        if not mine:
            continue
        data = {r["model"]: np.load(Path(args.out) / "fits" / f"{lead}-{r['model']}.npz") for r in mine}
        common = sorted(set.intersection(*[set(d["targets"].tolist()) for d in data.values()]))
        pick = {m: np.array([d["targets"].tolist().index(t) for t in common]) for m, d in data.items()}
        years = np.array([int(t[:4]) for t in common])
        first = next(iter(data))
        o, w = data[first]["o"][pick[first]].astype("float64"), data[first]["weight"].astype("float64")
        assert all(np.array_equal(d["flat"], data[first]["flat"]) for d in data.values())
        mean = lambda v: float(np.nansum(v * w) / w[np.isfinite(v)].sum())
        no_model = np.stack([o[years != y].mean(0) for y in years])
        reference = cv_rps(no_model, o, years)
        base = {"lead": lead, "name": weeks.LEAD_NAMES[lead], "members": len(mine), "common_targets": len(common)}
        H, RAW = {}, {}
        for r in mine:
            m = r["model"]
            H[m], RAW[m] = data[m]["h"][pick[m]].astype("float64"), data[m]["raw"][pick[m]].astype("float64")
            rows.append(dict(base, forecast=m, samples=r["samples"], pearson_all_samples=r["pearson"], pearson=mean(corr(H[m], o)),
                             afc=r["afc"], cv_rpss=mean(1 - cv_rps(H[m], o, years) / reference), raw_pearson=mean(corr(RAW[m], o))))
        mme, raw_mean = np.mean(list(H.values()), axis=0), np.mean(list(RAW.values()), axis=0)
        rows.append(dict(base, forecast="MME", pearson=mean(corr(mme, o)), cv_rpss=mean(1 - cv_rps(mme, o, years) / reference), raw_pearson=mean(corr(raw_mean, o))))
        for dropped in H:                                   # what each model contributes: the mean of the other four
            rest = np.mean([H[m] for m in H if m != dropped], axis=0)
            rows.append(dict(base, forecast=f"MME without {dropped}", members=len(H) - 1, pearson=mean(corr(rest, o)),
                             cv_rpss=mean(1 - cv_rps(rest, o, years) / reference)))
        rows.append(dict(base, forecast="no model", pearson=mean(corr(no_model, o)), cv_rpss=0.0))
    table = pd.DataFrame(rows)
    table.round(4).to_csv(args.out / "skill-by-lead.csv", index=False)
    return table


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "temp/audits/subseasonal-skill-scan")
    parser.add_argument("--data", type=Path, default=Path.home() / "PyCPT" / "indonesia-subseasonal-scan")
    parser.add_argument("--catalog", type=Path, default=ROOT / "temp/audits/subseasonal-value-check")
    parser.add_argument("--stage", choices=["plan", "download", "totals", "fit", "summary", "all"], default="all")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--workers", type=int, default=25)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    args.data = args.data.expanduser()
    args.data.mkdir(parents=True, exist_ok=True)
    stage = lambda name: args.stage in (name, "all")
    t0 = time.monotonic()
    jobs, unserved = plan(catalog(args.catalog))
    per_model = {m: sum(k[0] == m for k in jobs) for m in MODELS}
    print(f"plan: {len(design())} target-lead rows, files per model {per_model}, rows the rule cannot serve {len(unserved)}", flush=True)
    if stage("download"):
        download(args, jobs)
    if stage("totals"):
        totals(args, jobs, unserved)
    if stage("fit"):
        obs = observations(args)
        print(f"observations: {dict(obs.sizes)}, cells with data in every 7-day target {int(obs.total_7.notnull().all('T_7').sum())}", flush=True)
        todo = [(str(args.data), str(args.out), model, lead) for lead in LEADS for model in MODELS]
        with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context("spawn")) as pool, open(args.out / "records.jsonl", "w") as handle:
            for record in pool.map(fit, todo):
                handle.write(json.dumps(record) + "\n")
                handle.flush()
                print(json.dumps({k: record.get(k) for k in ("model", "lead", "status", "samples", "pearson", "seconds", "reason", "error")}), flush=True)
    if stage("summary"):
        records = [json.loads(line) for line in (args.out / "records.jsonl").read_text().splitlines()]
        table = summarise(args, records)
        print(table[table.forecast.isin(list(MODELS) + ["MME", "no model"])].pivot(index="forecast", columns="lead", values="pearson")[list(LEADS)].round(3).to_string(), flush=True)
    print(f"done in {(time.monotonic() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
