"""Prepare and fit the subseasonal multi-model ensemble: five SubX models, each calibrated the same way at 0.05 degree.

The weekly case (`prepare_weeks`): one issue date, a Wednesday, and the targets of the single-model weekly case
(week 1 to week 4 and weeks 3-4). The models, the training years 2000-2016 and the rule for which run of each
model answers an issue date are those of `subseasonal_skill_scan.py`, which measured them at 0.25 degree first.

    prepare_weeks(case_root, issue)   writes CPT-ready anomalies: Y per lead, X and F per lead and model, and meta.json
    run(jobs, workers)                one process per (lead, model, method): CCA or PCR through cptcore, the layer
                                      PyCPT's evaluate_models calls; keeps a compact result at the Indonesian pixels

A compact result holds the cross-validated hindcasts, the forecast (deterministic, tercile probabilities, prediction
error variance), CPT's Pearson and 2AFC maps and the EOF and CCA patterns. A finished fit is reused when its input
values and settings are unchanged (SHA-256 stored in the result).

The ensemble itself is built by the notebook from these files, as PyCPT's construct_mme does: the equal-weight
mean of the members' deterministic values, prediction error variances and probabilities.

    python research/scripts/subseasonal_mme_fits.py --prepare-weeks [--issue 2023-11-01] [--workers 25] [--fit]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ.setdefault("CPT_BIN_DIR", str(Path(sys.prefix) / "opt" / "cpt" / "bin"))
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import subseasonal_skill_scan as scan  # noqa: E402

MODELS = list(scan.MODELS)
YEARS = scan.YEARS
FORECAST_BRANCH = {"GEFSv12_CPC": "/.forecast/.pr", "CFSv2": "/.forecast/.pr", "GEOS_V2p1": "/.forecast/.pr",
                   "CCSM4": "/.forecast/.pr", "FIMr1p1": "/.forecast_weekly/.pr"}
SCAN_DATA = Path.home() / "PyCPT" / "indonesia-subseasonal-scan"
CATALOG = ROOT / "temp/audits/subseasonal-value-check"
SETTINGS = {"x_eof_modes": (3, 3), "validation": "CROSSVALIDATION", "crossvalidation_window": 27, "synchronous_predictors": True,
            "transform_predictand": None, "tailoring": None, "drymask_threshold": None, "skillmask_threshold": None}
CCA_SETTINGS = dict(SETTINGS, y_eof_modes=(3, 3), cca_modes=(2, 2))
ENCODING = {"zlib": True, "complevel": 4}


def forecast_catalog():
    """{model: sorted 2023 forecast starts that hold values}; CFSv2's check timed out, so its runs are tried directly."""
    out = {}
    for model in MODELS:
        rows = json.loads((CATALOG / f"{model}.json").read_text())["rows"]
        out[model] = sorted({dt.datetime.fromisoformat(s) for r in rows if r["kind"] == "forecast" and r.get("ok") for s in r["starts"]})
    return out


def forecast_file(model, issue, cat):
    """Download (once) the 2023 run or runs of a model that answer an issue date; returns the path and the starts."""
    import requests
    at = dt.datetime.combine(issue, dt.time())
    if model == "CFSv2":
        starts = [at - dt.timedelta(hours=h) for h in scan.CFSV2_HOURS_BEFORE]
    else:
        starts = scan.selected_starts(model, issue, cat[model])
    if not starts:
        raise ValueError(f"{model}: no 2023 run within {scan.MAX_LAG_DAYS} days before {issue}")
    path = SCAN_DATA / "raw-forecast" / f"{model}-{issue}.nc"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        sel = f"/S/({scan.label(starts[0])})/({scan.label(starts[-1])})/RANGE" if len(starts) > 1 else f"/S/({scan.label(starts[0])})/VALUES"
        url = scan.BASE + scan.MODELS[model][0] + FORECAST_BRANCH[model] + sel + f"/X/{scan.BOX['west']}/{scan.BOX['east']}/RANGE/Y/{scan.BOX['south']}/{scan.BOX['north']}/RANGE/data.nc"
        try:
            from cptdl.utilities import read_dlauth
            key = read_dlauth() or ""
        except Exception:
            key = ""
        r = requests.get(url, cookies={"__dlauth_id": key} if key else None, timeout=900, headers={"User-Agent": "python-requests subseasonal case"})
        if r.status_code != 200 or not (r.content.startswith(b"CDF") or r.content.startswith(b"\x89HDF")):
            raise ValueError(f"{model}: HTTP {r.status_code}, not NetCDF")
        path.write_bytes(r.content)
    return path, starts


def climatology(target_dates, train_dates, train_values):
    """For each target, the mean over the training years of the one training sample nearest in season day."""
    import numpy as np
    by_year = {}
    for j, t in enumerate(train_dates):
        by_year.setdefault(t.year, []).append(j)
    W = np.zeros((len(target_dates), len(train_dates)))
    for i, t in enumerate(target_dates):
        for idx in by_year.values():
            W[i, idx[int(np.argmin([abs(scan.season_day(train_dates[j]) - scan.season_day(t)) for j in idx]))]] = 1 / len(by_year)
    flat = train_values.reshape(len(train_dates), -1)
    return (W @ np.nan_to_num(flat)).reshape((len(target_dates),) + train_values.shape[1:]).astype("float32")


def cpt_ready(values, like, first_year):
    """(T, Y, X) values on `like`'s grid, re-dated to consecutive placeholder years: CPT cannot read irregular dates."""
    import numpy as np
    import pandas as pd
    import xarray as xr
    years = first_year + np.arange(values.shape[0])
    a = xr.DataArray(values.astype("float32"), dims=("T", "Y", "X"),
                     coords={"T": pd.to_datetime([f"{y}-10-04" for y in years]), "Y": like["Y"].values, "X": like["X"].values}, name="anomaly")
    a = a.assign_coords(Ti=("T", pd.to_datetime([f"{y}-10-01" for y in years])), Tf=("T", pd.to_datetime([f"{y}-10-07" for y in years])))
    a.attrs = {"units": "mm", "missing": -999.0}
    return a


def prepare_weeks(case_root, issue=dt.date(2023, 11, 1), log=print):
    """Write the CPT inputs of the weekly five-model case and return its description (also saved as meta.json)."""
    import numpy as np
    import pandas as pd
    import xarray as xr
    from pycpt_tutorial.country_grid import read_provinces, touching_pixels

    case_root = Path(case_root)
    inputs = case_root / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    leads = scan.LEADS
    assert issue.weekday() == 2, "the weekly case issues on a Wednesday"
    rows = scan.design()
    stamp = lambda d: pd.Timestamp(d).to_pydatetime()

    # model totals for the training targets (written by subseasonal_skill_scan.py --stage totals), on the targets all models have
    x_train, common = {}, {}
    for lead in leads:
        per_model = {}
        for model in MODELS:
            with xr.open_dataset(SCAN_DATA / "totals" / f"{model}.nc") as ds:
                per_model[model] = ds[lead].load().rename({f"T_{lead}": "T"})
        shared = sorted(set.intersection(*[set(pd.DatetimeIndex(a["T"].values)) for a in per_model.values()]))
        assert sorted({t.year for t in shared}) == YEARS, lead
        common[lead] = [stamp(t) for t in shared]
        for model, a in per_model.items():
            x_train[lead, model] = a.sel(T=shared).transpose("T", "Y", "X")
    samples = pd.read_csv(ROOT / "temp/audits/subseasonal-skill-scan/samples.csv")

    # the 2023 runs that answer the issue date, and their totals over the same calendar days
    cat = forecast_catalog()
    targets_2023 = {lead: dt.datetime.combine(issue, dt.time()) + dt.timedelta(days=first) for lead, (first, _) in leads.items()}
    x_fc, runs = {}, {}
    for model in MODELS:
        path, starts = forecast_file(model, issue, cat)
        pr, got = scan.open_raw(path)
        assert got == starts, (model, got)
        assert pr.attrs.get("units") == "kg m-2 s-1", (model, pr.attrs.get("units"))
        runs[model] = {"starts": [s.isoformat(timespec="minutes") for s in starts], "members": int(pr.sizes.get("M", 1)) * len(starts),
                       "lag_days": (dt.datetime.combine(issue, dt.time()) - max(starts)).total_seconds() / 86400,
                       "training_members": int(samples[samples.model == model].members.max()),
                       "training_lag_days": [float(samples[samples.model == model].lag_days.min()), round(float(samples[samples.model == model].lag_days.mean()), 2),
                                             float(samples[samples.model == model].lag_days.max())]}
        for lead, (_, days) in leads.items():
            per_start = []
            for i, s in enumerate(starts):
                d = pr.isel(S=i).sel(L=scan.slots(s, targets_2023[lead], days))
                assert bool(np.isfinite(d).all()), (model, lead)
                d = d.sum("L") * 86400.0
                per_start.append(d.mean("M") if "M" in d.dims else d)
            x_fc[lead, model] = (sum(per_start) / len(per_start)).sortby("Y", ascending=False).transpose("Y", "X")
    log(f"2023 runs for the issue of {issue}: " + "; ".join(f"{m} {r['starts'][-1][:10]} ({r['members']} members, lag {r['lag_days']:.0f} d)" for m, r in runs.items()))

    # observations: daily CHIRPS v3.0 at 0.05 degree, summed over each target window
    t0 = time.monotonic()
    files = [scan.DAILY / f"chirps3_rnl_daily_idn_{y}.nc" for y in YEARS + [YEARS[-1] + 1, issue.year, issue.year + 1]]
    assert all(f.exists() for f in files), [f.name for f in files if not f.exists()]
    source = xr.open_mfdataset(files, combine="by_coords")
    daily = source.precip.sel(time=source.time.dt.month.isin([10, 11, 12, 1])).load()
    touching, _ = touching_pixels(daily.lon.values, daily.lat.values, read_provinces(scan.PROVINCES))
    country = xr.DataArray(touching, dims=("lat", "lon"), coords={"lat": daily.lat, "lon": daily.lon}).rename({"lat": "Y", "lon": "X"}).sortby("Y", ascending=False)

    def window(first, days):
        w = daily.sel(time=slice(pd.Timestamp(first), pd.Timestamp(first) + pd.Timedelta(days=days - 1)))
        assert w.sizes["time"] == days, (first, w.sizes["time"])
        return w.sum("time", skipna=False).rename({"lat": "Y", "lon": "X"}).sortby("Y", ascending=False).astype("float32")

    all_train = {days: sorted({stamp(r["target"]) for r in rows if r["days"] == days}) for days in (7, 14)}
    obs_train = {days: np.stack([window(t, days).values for t in all_train[days]]) for days in (7, 14)}
    grid = window(all_train[7][0], 7)
    mask = country.values & np.isfinite(obs_train[7]).all(0) & np.isfinite(obs_train[14]).all(0)
    log(f"observations: {len(all_train[7])} training targets per window length, read in {time.monotonic() - t0:.0f} s; "
        f"pixels touching Indonesia {int(country.values.sum()):,}, with data in every training target {int(mask.sum()):,}")

    meta = {"case": "weeks", "issue": issue.isoformat(), "training_years": [YEARS[0], YEARS[-1]], "models": MODELS, "runs": runs,
            "pixels": int(mask.sum()), "leads": {}, "settings": {k: str(v) for k, v in CCA_SETTINGS.items()}}
    xr.Dataset({"mask": (("Y", "X"), mask)}, coords={"Y": grid["Y"].values, "X": grid["X"].values}).to_netcdf(inputs / "mask.nc")
    extra = xr.Dataset(coords={"Y": grid["Y"].values, "X": grid["X"].values})
    for lead, (_, days) in leads.items():
        train_dates = all_train[days]
        clim_train = climatology(train_dates, train_dates, obs_train[days])
        keep = [train_dates.index(t) for t in common[lead]]
        y_anom = np.where(mask, obs_train[days][keep] - clim_train[keep], np.nan)
        cpt_ready(y_anom, grid, 1701).to_netcdf(inputs / f"Y-{lead}.nc", encoding={"anomaly": ENCODING})
        target = targets_2023[lead]
        observed = window(target, days).values
        clim_2023 = climatology([target], train_dates, obs_train[days])[0]
        extra[f"observed_{lead}"] = (("Y", "X"), np.where(mask, observed, np.nan).astype("float32"))
        extra[f"climatology_{lead}"] = (("Y", "X"), np.where(mask, clim_2023, np.nan).astype("float32"))
        for model in MODELS:
            x = x_train[lead, model]
            x_clim = climatology(common[lead] + [target], common[lead], x.values)
            cpt_ready(x.values - x_clim[:-1], x, 1701).to_netcdf(inputs / f"X-{lead}-{model}.nc")
            cpt_ready((x_fc[lead, model].values - x_clim[-1])[None], x, 1990).to_netcdf(inputs / f"F-{lead}-{model}.nc")
        meta["leads"][lead] = {"name": scan.weeks.LEAD_NAMES[lead], "first_day": leads[lead][0], "days": days,
                               "target_first_day": target.date().isoformat(), "target_last_day": (target + dt.timedelta(days=days - 1)).date().isoformat(),
                               "training_targets": [t.date().isoformat() for t in common[lead]]}
        log(f"{lead}: {len(common[lead])} training targets on all five models; 2023 target {target:%d %b} to {target + dt.timedelta(days=days - 1):%d %b}")
    extra.to_netcdf(inputs / "targets-2023.nc", encoding={v: ENCODING for v in extra.data_vars})
    (case_root / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


# ----------------------------------------------------------------------------------------------------------------
# Dekads and pentads: calendar targets. GEFSv12 hindcasts start on Wednesdays only, so the single-model cases train
# each target and lead on the one Wednesday whose offset falls in that lead's 7-day window. That Wednesday is the
# issue date of the training sample here too, and the other models answer it by the same start rule.
CALENDAR = {
    "dekads": {"module": "download_gefs_dekads", "target_key": "dekad", "issue_key": "start", "cv_window": 17, "unit": "Dekad",
               "root": "indonesia-issued-2023-10-31-dekads-mme"},
    "pentads": {"module": "download_gefs_pentads", "target_key": "pentad", "issue_key": "issued", "cv_window": 35, "unit": "Pentad",
                "root": "indonesia-issued-2023-10-31-pentads-mme"},
}
MIN_SHARE = 0.9          # a model is a member at a lead when it serves the 2023 target and at least this share of the training targets


def read_targets(case, firsts):
    """CHIRPS v3.0 totals of the target dekads or pentads at 0.05 degree, as (target, Y, X) with Y north to south."""
    import numpy as np
    import pandas as pd
    import xarray as xr
    times = pd.to_datetime(firsts)
    if case == "dekads":
        source = xr.open_dataset("/mnt/e/temp/chirps/dekad/wld_cli_chirps3_dekad_1981_2025.nc")
        a = source.precip.sel(time=times, lon=slice(93.95, 142.0), lat=slice(-12.0, 7.05)).load()
    else:
        years = sorted({t.year for t in times})
        source = xr.open_mfdataset([f"/mnt/e/temp/chirps/pentad-idn/chirps3_pentad_idn_{y}.nc" for y in years], combine="by_coords")
        a = source.precip.sel(time=times).load()
    bounds = pd.DatetimeIndex(source.time_bnds.sel(time=times).values.ravel()).values.reshape(-1, 2)
    a = a.rename({"time": "T", "lat": "Y", "lon": "X"})
    a = a.assign_coords(Y=np.round(a.Y.values.astype(float), 3), X=np.round(a.X.values.astype(float), 3)).sortby("Y", ascending=False)
    return a.astype("float32"), bounds


def fetch_hindcast(model, issue, starts):
    """Download (once) the hindcast run or runs of a model for an issue date into the scan's raw folder."""
    import requests
    path = scan.raw_path(SCAN_DATA, model, issue)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from cptdl.utilities import read_dlauth
        key = read_dlauth() or ""
    except Exception:
        key = ""
    for attempt in range(1, 6):
        try:
            r = requests.get(scan.url_for(model, starts), cookies={"__dlauth_id": key} if key else None, timeout=600,
                             headers={"User-Agent": "python-requests subseasonal case"})
            if r.status_code != 200 or not (r.content[:3] == b"CDF" or r.content[1:4] == b"HDF"):
                raise ValueError(f"HTTP {r.status_code}, not NetCDF")
            tmp = path.with_suffix(".part")
            tmp.write_bytes(r.content)
            tmp.replace(path)
            return path
        except Exception:
            if attempt == 5:
                raise
            time.sleep(15 * attempt)


def window_total(pr, starts, first, days, factor):
    """Ensemble-mean total over the target days from the given runs, or None when a needed lead slot is absent or empty."""
    import numpy as np
    per_start = []
    have = set(np.round(pr["L"].values, 3).tolist())
    for i, s in enumerate(starts):
        want = scan.slots(s, first, days)
        if not set(want) <= have:
            return None
        d = pr.isel(S=i).sel(L=want)
        if not bool(np.isfinite(d).all()):
            return None
        d = d.sum("L") * factor
        per_start.append(d.mean("M") if "M" in d.dims else d)
    return (sum(per_start) / len(per_start)).sortby("Y", ascending=False).transpose("Y", "X").astype("float32")


def prepare_calendar(case, case_root, issue=dt.date(2023, 10, 31), log=print):
    """Write the CPT inputs of the dekad or pentad five-model case and return its description (also saved as meta.json)."""
    import importlib
    import numpy as np
    import pandas as pd
    import xarray as xr
    from concurrent.futures import ThreadPoolExecutor as Pool
    from pycpt_tutorial.country_grid import read_provinces, touching_pixels

    spec = CALENDAR[case]
    module = importlib.import_module(spec["module"])
    case_root = Path(case_root)
    inputs = case_root / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    design = module.design()
    train_rows = [r for r in design if r["kind"] == "hindcast" and r["year"] in YEARS]
    issue_rows = [r for r in design if r["kind"] == "forecast" and r[spec["issue_key"]] == issue]
    leads = sorted({r["lead"] for r in train_rows})
    assert sorted(r["lead"] for r in issue_rows) == leads, "the issue date must forecast every lead"
    keys = {lead: f"lead{lead}" for lead in leads}
    midnight = lambda d: dt.datetime.combine(d, dt.time())

    # training totals of every model: the run that answers each sample's Wednesday, summed over the target's days
    cat = scan.catalog(CATALOG)
    need = {}
    for r in train_rows:
        for model in MODELS:
            starts = scan.selected_starts(model, r["start"], cat[model])
            if starts:
                need[model, r["start"]] = starts
    missing = [(m, i, s) for (m, i), s in need.items() if not scan.raw_path(SCAN_DATA, m, i).exists()]
    if missing:
        log(f"downloading {len(missing)} hindcast files not yet on disk")
        with Pool(4) as pool:
            list(pool.map(lambda item: fetch_hindcast(*item), missing))
    opened, totals, lags = {}, {}, {m: [] for m in MODELS}
    for r in train_rows:
        first = midnight(r[spec["target_key"]])
        for model in MODELS:
            starts = need.get((model, r["start"]))
            if not starts:
                continue
            if (model, r["start"]) not in opened:
                opened[model, r["start"]] = scan.open_raw(scan.raw_path(SCAN_DATA, model, r["start"]))
            pr, got = opened[model, r["start"]]
            assert got == starts, (model, r["start"], got)
            total = window_total(pr, starts, first, r["days"], scan.MODELS[model][2])
            if total is not None:
                totals[model, r["lead"], first] = total
                lags[model].append((midnight(r["start"]) - max(starts)).total_seconds() / 86400)
    del opened

    # the 2023 runs that answer the issue date
    fcat = forecast_catalog()
    x_fc, runs = {}, {}
    for model in MODELS:
        path, starts = forecast_file(model, issue, fcat)
        pr, got = scan.open_raw(path)
        assert got == starts and pr.attrs.get("units") == "kg m-2 s-1", (model, got, pr.attrs.get("units"))
        train_pr, _ = scan.open_raw(scan.raw_path(SCAN_DATA, model, train_rows[0]["start"]))
        runs[model] = {"starts": [s.isoformat(timespec="minutes") for s in starts], "members": int(pr.sizes.get("M", 1)) * len(starts),
                       "lag_days": (midnight(issue) - max(starts)).total_seconds() / 86400,
                       "training_members": int(train_pr.sizes.get("M", 1)) * len(need[model, train_rows[0]["start"]]),
                       "training_lag_days": [float(min(lags[model])), round(float(np.mean(lags[model])), 2), float(max(lags[model]))],
                       "last_lead_day": float(pr["L"].max())}
        for r in issue_rows:
            total = window_total(pr, starts, midnight(r[spec["target_key"]]), r["days"], 86400.0)
            if total is not None:
                x_fc[model, r["lead"]] = total
    log(f"2023 runs for the issue of {issue}: " + "; ".join(f"{m} {r['starts'][-1][:10]} ({r['members']} members, lag {r['lag_days']:.0f} d)" for m, r in runs.items()))

    # members and common training targets per lead
    all_train = sorted({midnight(r[spec["target_key"]]) for r in train_rows})
    members, common, why = {}, {}, {}
    for lead in leads:
        served = {m: {t for t in all_train if (m, lead, t) in totals} for m in MODELS}
        members[lead] = [m for m in MODELS if (m, lead) in x_fc and len(served[m]) >= MIN_SHARE * len(all_train)
                         and sorted({t.year for t in served[m]}) == YEARS]
        why[lead] = {m: ("no 2023 forecast this far ahead" if (m, lead) not in x_fc else f"serves {len(served[m])} of {len(all_train)} training targets")
                     for m in MODELS if m not in members[lead]}
        common[lead] = sorted(set.intersection(*[served[m] for m in members[lead]]))
        assert sorted({t.year for t in common[lead]}) == YEARS, lead

    # observations: CHIRPS v3.0's own dekad or pentad product
    t0 = time.monotonic()
    obs, bounds = read_targets(case, all_train)
    lengths = {t: r["days"] for r in train_rows for t in [midnight(r[spec["target_key"]])]}
    assert all((b[1] - b[0]) / np.timedelta64(1, "D") == lengths[t] for t, b in zip(all_train, bounds)), "stored bounds differ from the design"
    touching, _ = touching_pixels(obs.X.values, obs.Y.values, read_provinces(scan.PROVINCES))
    obs_train = obs.values
    mask = touching & np.isfinite(obs_train).all(0)
    targets_2023 = {r["lead"]: (midnight(r[spec["target_key"]]), r["days"]) for r in issue_rows}
    obs_2023, _ = read_targets(case, [targets_2023[lead][0] for lead in leads])
    obs_2023 = obs_2023.reindex(Y=obs.Y, X=obs.X, method="nearest", tolerance=1e-3)
    log(f"observations: {len(all_train)} training targets read in {time.monotonic() - t0:.0f} s; "
        f"pixels touching Indonesia {int(touching.sum()):,}, with data in every training target {int(mask.sum()):,}")

    meta = {"case": case, "issue": issue.isoformat(), "training_years": [YEARS[0], YEARS[-1]], "models": MODELS, "runs": runs,
            "pixels": int(mask.sum()), "leads": {}, "cv_window": spec["cv_window"], "all_training_targets": len(all_train),
            "settings": {k: str(v) for k, v in dict(CCA_SETTINGS, crossvalidation_window=spec["cv_window"]).items()}}
    grid = obs.isel(T=0)
    xr.Dataset({"mask": (("Y", "X"), mask)}, coords={"Y": grid["Y"].values, "X": grid["X"].values}).to_netcdf(inputs / "mask.nc")
    extra = xr.Dataset(coords={"Y": grid["Y"].values, "X": grid["X"].values})
    clim_train = climatology(all_train, all_train, obs_train)
    for k, lead in enumerate(leads):
        key = keys[lead]
        keep = [all_train.index(t) for t in common[lead]]
        y_anom = np.where(mask, obs_train[keep] - clim_train[keep], np.nan)
        cpt_ready(y_anom, grid, 1701).to_netcdf(inputs / f"Y-{key}.nc", encoding={"anomaly": ENCODING})
        target, days = targets_2023[lead]
        clim_2023 = climatology([target], all_train, obs_train)[0]
        extra[f"observed_{key}"] = (("Y", "X"), np.where(mask, obs_2023.isel(T=k).values, np.nan).astype("float32"))
        extra[f"climatology_{key}"] = (("Y", "X"), np.where(mask, clim_2023, np.nan).astype("float32"))
        for model in members[lead]:
            x = np.stack([totals[model, lead, t].values for t in common[lead]])
            like = totals[model, lead, common[lead][0]]
            x_clim = climatology(common[lead] + [target], common[lead], x)
            cpt_ready(x - x_clim[:-1], like, 1701).to_netcdf(inputs / f"X-{key}-{model}.nc")
            cpt_ready((x_fc[model, lead].values - x_clim[-1])[None], like, 1990).to_netcdf(inputs / f"F-{key}-{model}.nc")
        meta["leads"][key] = {"name": f"{spec['unit']} +{lead}", "lead": lead, "days": days, "first_day": (target - midnight(issue)).days,
                              "target_first_day": target.date().isoformat(), "target_last_day": (target + dt.timedelta(days=days - 1)).date().isoformat(),
                              "models": members[lead], "not_members": why[lead], "training_targets": [t.date().isoformat() for t in common[lead]]}
        log(f"{key}: {len(members[lead])} members ({', '.join(members[lead])}); {len(common[lead])} of {len(all_train)} training targets on all of them; "
            f"2023 target {target:%d %b} to {target + dt.timedelta(days=days - 1):%d %b}" + (f"; not members: {why[lead]}" if why[lead] else ""))
    extra.to_netcdf(inputs / "targets-2023.nc", encoding={v: ENCODING for v in extra.data_vars})
    (case_root / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def jobs_for(case_root, meta):
    case_root = Path(case_root)
    window = meta.get("cv_window", SETTINGS["crossvalidation_window"])
    return [dict(lead=lead, model=model, method=method, case_root=str(case_root),
                 settings=dict(CCA_SETTINGS if method == "CCA" else SETTINGS, crossvalidation_window=window))
            for lead in meta["leads"] for model in meta["leads"][lead].get("models", meta["models"]) for method in ("CCA", "PCR")]


def result_path(job):
    return Path(job["case_root"]) / "compact" / f"{job['lead']}-{job['model']}-{job['method']}.nc"


def _digest(arrays, settings):
    h = hashlib.sha256()
    for a in arrays:
        for part in (a.values, a["Y"].values, a["X"].values):
            h.update(part.tobytes())
    h.update(json.dumps(settings, sort_keys=True, default=str).encode())
    return h.hexdigest()


def fit_one(job):
    """One (lead, model, method). Returns a status record; never raises."""
    record = {k: job[k] for k in ("lead", "model", "method")}
    start = time.monotonic()
    try:
        import numpy as np
        import xarray as xr
        from cptcore import canonical_correlation_analysis, principal_components_regression

        root, lead, model, method = Path(job["case_root"]), job["lead"], job["model"], job["method"]
        inputs = root / "inputs"
        X, Y, F = (xr.open_dataarray(inputs / name).load() for name in (f"X-{lead}-{model}.nc", f"Y-{lead}.nc", f"F-{lead}-{model}.nc"))
        for a in (X, Y, F):
            a.name = "anomaly"
            a.attrs = {"units": "mm", "missing": -999.0}
        settings = {k: tuple(v) if isinstance(v, list) else v for k, v in job["settings"].items()}
        digest = _digest([X, Y, F], dict(settings, method=method))
        result = result_path(job)
        if result.exists():
            with xr.open_dataset(result) as old:
                if old.attrs.get("inputs_sha256") == digest:
                    return dict(record, status="reused", seconds=float(old.attrs["fit_seconds"]), path=str(result))
        cpt_dir = root / "cpt" / f"{lead}-{model}-{method}"
        shutil.rmtree(cpt_dir, ignore_errors=True)
        cpt_dir.mkdir(parents=True)
        function = canonical_correlation_analysis if method == "CCA" else principal_components_regression
        t0 = time.monotonic()
        out = function(X, Y, F=F, **settings, cpt_kwargs={"outputdir": cpt_dir})
        seconds = time.monotonic() - t0
        hindcast, forecast, skill, px = out[0], out[1], out[2], out[3]

        with xr.open_dataset(inputs / "mask.nc") as m:
            mask = m["mask"].load()
        flat = np.flatnonzero(mask.values.ravel())

        def pix(a):
            a = a.where(a > -999).reindex(Y=mask["Y"], X=mask["X"], method="nearest", tolerance=1e-4).transpose(..., "Y", "X")
            return a.values.reshape(a.shape[:-2] + (-1,))[..., flat].astype("float32")

        ds = xr.Dataset(coords={"pixel": flat.astype("int32")})
        ds["cv_hindcast"] = (("T", "pixel"), pix(hindcast.deterministic.transpose("T", "Y", "X")))
        ds["forecast"] = (("pixel",), pix(forecast.deterministic.isel(T=0, drop=True)))
        ds["forecast_probability"] = (("C", "pixel"), pix(forecast.probabilistic.isel(T=0, drop=True).transpose("C", "Y", "X")))
        ds["forecast_pev"] = (("pixel",), pix(forecast.prediction_error_variance.isel(T=0, drop=True)))
        ds["skill_pearson"] = (("pixel",), pix(skill.pearson))
        ds["skill_two_alternative_forced_choice"] = (("pixel",), pix(skill.two_alternative_forced_choice))
        clean = lambda a: a.where(a > -999)
        px = px.isel(Mode=slice(0, 3))
        ds = ds.assign_coords(Mode=px["Mode"].values.astype("int32"))
        for name in px.data_vars:                                  # predictor patterns stay on the model grid
            a = clean(px[name]).reset_coords(drop=True)
            if "Y" in a.dims:
                a = a.transpose("Mode", "Y", "X")
                ds = ds.assign_coords(Yx=a["Y"].values, Xx=a["X"].values)
                ds[name] = (("Mode", "Yx", "Xx"), a.values)
            else:
                ds[name] = (a.dims, a.values)
        if method == "CCA":
            py = out[4].isel(Mode=slice(0, 3))
            for name in py.data_vars:
                a = clean(py[name]).reset_coords(drop=True)
                ds[name] = (("Mode", "pixel"), pix(py[name].transpose("Mode", "Y", "X"))) if "Y" in a.dims else (a.dims, a.values)
        h, y = ds["cv_hindcast"].values.astype("float64"), pix(Y.transpose("T", "Y", "X")).astype("float64")
        ha, ya = h - h.mean(0), y - y.mean(0)
        with np.errstate(invalid="ignore", divide="ignore"):
            recomputed = (ha * ya).sum(0) / np.sqrt((ha * ha).sum(0) * (ya * ya).sum(0))
        ds.attrs = {"inputs_sha256": digest, "fit_seconds": round(seconds, 1), "model": model, "method": method, "lead": lead,
                    "training_targets": int(X.sizes["T"]),
                    "largest_gap_cpt_vs_recomputed_pearson": float(np.nanmax(np.abs(ds["skill_pearson"].values - recomputed))),
                    "hindcast_values_missing": int((~np.isfinite(h)).sum()),
                    "settings": json.dumps(settings, sort_keys=True, default=str)}
        result.parent.mkdir(parents=True, exist_ok=True)
        tmp = result.with_suffix(".part")
        ds.to_netcdf(tmp, encoding={v: ENCODING for v in ds.data_vars if ds[v].dtype.kind == "f"})
        tmp.replace(result)
        shutil.rmtree(cpt_dir, ignore_errors=True)                 # CPT's own files are several GB per fit
        return dict(record, status="fitted", seconds=round(seconds, 1), path=str(result))
    except Exception as error:
        return dict(record, status="failed", seconds=round(time.monotonic() - start, 1),
                    error=f"{type(error).__name__}: {str(error)[:300]}", traceback=traceback.format_exc().splitlines()[-12:])


def run(jobs, workers=25, log=print):
    """Each fit in its own Python process, `workers` at a time; returns the status records in job order."""
    def launch(job):
        folder = Path(job["case_root"]) / "jobs"
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{job['lead']}-{job['model']}-{job['method']}"
        (folder / f"{name}.json").write_text(json.dumps(job, default=list))
        done = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--job", str(folder / f"{name}.json")],
                              capture_output=True, text=True)
        out = folder / f"{name}.record.json"
        record = json.loads(out.read_text()) if done.returncode == 0 and out.exists() else dict(
            lead=job["lead"], model=job["model"], method=job["method"], status="failed", error=(done.stderr or done.stdout)[-400:])
        log(json.dumps({k: record.get(k) for k in ("lead", "model", "method", "status", "seconds", "error")}))
        return record
    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(launch, jobs))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--job", type=Path)
    parser.add_argument("--prepare-weeks", action="store_true")
    parser.add_argument("--prepare", choices=sorted(CALENDAR), help="prepare the dekad or pentad case (issue 2023-10-31 unless --issue is given)")
    parser.add_argument("--case-root", type=Path)
    parser.add_argument("--issue")
    parser.add_argument("--fit", action="store_true")
    parser.add_argument("--workers", type=int, default=25)
    parser.add_argument("--only", nargs="*", help="lead-model-method names to fit, e.g. week1-CFSv2-PCR")
    parser.add_argument("--leads", nargs="*", help="fit only these leads, e.g. lead1 lead2")
    args = parser.parse_args()
    if args.job:
        job = json.loads(args.job.read_text())
        record = fit_one(job)
        args.job.with_suffix("").with_suffix(".record.json").write_text(json.dumps(record))
        return
    flush = lambda *a: print(*a, flush=True)
    default_root = Path.home() / "PyCPT" / (CALENDAR[args.prepare]["root"] if args.prepare else "indonesia-issued-2023-11-weeks-mme")
    root = (args.case_root or default_root).expanduser()
    if args.prepare:
        meta = prepare_calendar(args.prepare, root, dt.date.fromisoformat(args.issue or "2023-10-31"), log=flush)
    elif args.prepare_weeks:
        meta = prepare_weeks(root, dt.date.fromisoformat(args.issue or "2023-11-01"), log=flush)
    else:
        meta = json.loads((root / "meta.json").read_text())
    if args.fit:
        jobs = jobs_for(root, meta)
        if args.leads:
            jobs = [j for j in jobs if j["lead"] in args.leads]
        if args.only:
            jobs = [j for j in jobs if f"{j['lead']}-{j['model']}-{j['method']}" in args.only]
        t0 = time.monotonic()
        records = run(jobs, args.workers, log=flush)
        counts = {}
        for r in records:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        flush(f"{len(records)} fits: {counts}; {(time.monotonic() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
