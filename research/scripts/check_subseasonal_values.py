"""Check that subseasonal model runs on the IRI Data Library hold values, not only grid entries.

A start listed on a dataset's S grid can still be empty (IRI's GEFSv12 run of 5 Dec 2023 is).
For each candidate model this script downloads daily precipitation at one grid point
(120E, 0N, inside the cases' predictor box) for every start between 25 August and
31 December of each year, all leads and all members, and records which starts hold
finite values, how many members and how many lead days. 25 August is 37 days before
1 October, so the range covers every start the October-December dekad, week and pentad
targets can use.

This is a presence check at one point. It does not show that the whole field is complete;
the full downloads check that per file.

    python research/scripts/check_subseasonal_values.py --out <folder>
    python research/scripts/check_subseasonal_values.py --out <folder> --models CCSM4 FIMr1p1

Writes <folder>/<model>.json and <folder>/summary.csv. Uses the IRI Data Library key
PyCPT already reads (never printed); anonymous if none is configured.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests
import xarray as xr

BASE = "https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX"
POINT = {"X": 120, "Y": 0}
# model: (centre/dataset, hindcast branch, forecast branches tried in order, hindcast years)
MODELS = {
    "GEFSv12_CPC": ("/.EMC/.GEFSv12_CPC", "/.hindcast/.weekly/.pr", ["/.forecast/.pr"], (1999, 2018)),
    "CFSv2": ("/.NCEP/.CFSv2", "/.hindcast/.pr", ["/.forecast/.pr"], (1999, 2016)),
    "GEOS_V2p1": ("/.GMAO/.GEOS_V2p1", "/.hindcast/.pr", ["/.forecast/.pr"], (1999, 2016)),
    "CCSM4": ("/.RSMAS/.CCSM4", "/.hindcast/.pr", ["/.forecast/.pr"], (1999, 2016)),
    "FIMr1p1": ("/.ESRL/.FIMr1p1", "/.hindcast/.pr", ["/.forecast_weekly/.pr", "/.forecast/.pr"], (1999, 2016)),
}
FORECAST_YEAR = 2023
EPOCH = dt.datetime(1960, 1, 1)
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _key():
    try:
        from cptdl.utilities import read_dlauth
        return read_dlauth() or ""
    except Exception:
        return ""


KEY = _key()


def url_for(dataset, branch, year):
    first, last = f"0000 25 Aug {year}", f"2300 31 Dec {year}"
    return (BASE + dataset + branch + f"/S/({first})/({last})/RANGE/X/{POINT['X']}/VALUE/Y/{POINT['Y']}/VALUE/data.nc"
            ).replace(" ", "%20")


def fetch(url, attempts=4):
    for attempt in range(1, attempts + 1):
        try:
            r = requests.get(url, cookies={"__dlauth_id": KEY} if KEY else None, timeout=600,
                             headers={"User-Agent": "python-requests availability check"})
            if "/auth/login" in r.url:
                raise PermissionError("sign-in required")
            if r.status_code != 200 or not (r.content.startswith(b"CDF") or r.content.startswith(b"\x89HDF")):
                raise ValueError(f"HTTP {r.status_code}, not NetCDF")
            return r.content
        except PermissionError:
            raise
        except Exception:
            if attempt == attempts:
                raise
            time.sleep(15 * attempt)


def check_year(model, kind, branch, year):
    dataset = MODELS[model][0]
    url = url_for(dataset, branch, year)
    row = {"model": model, "kind": kind, "branch": branch, "year": year, "url": url}
    t0 = time.monotonic()
    try:
        with xr.open_dataset(io.BytesIO(fetch(url)), decode_times=False) as ds:
            pr = ds["pr"].squeeze(drop=True).load()
            other = [d for d in pr.dims if d != "S"]
            starts = [EPOCH + dt.timedelta(days=float(s)) for s in np.atleast_1d(ds["S"].values)]
            finite = np.isfinite(pr)
            has = np.atleast_1d(finite.any(other).values)
            good = [s for s, ok in zip(starts, has) if ok]
            ond_span = [s for s in good if s.month >= 10 or (s.month == 9 and s.day >= 1) or s.month == 8]
            row.update({
                "ok": True,
                "units": pr.attrs.get("units"),
                "dims": {d: int(n) for d, n in pr.sizes.items()},
                "starts_on_grid": len(starts),
                "starts_with_values": len(good),
                "starts_empty": len(starts) - len(good),
                "first_with_values": good[0].isoformat(timespec="minutes") if good else None,
                "last_with_values": good[-1].isoformat(timespec="minutes") if good else None,
                "weekdays_with_values": {WEEKDAYS[i]: sum(s.weekday() == i for s in good) for i in range(7)
                                         if any(s.weekday() == i for s in good)},
                "hours_with_values": sorted({s.hour for s in good}),
                "starts": [s.isoformat(timespec="minutes") for s in ond_span],
            })
            if good and "L" in pr.dims:
                per_lead = finite.sel(S=ds["S"].values[has]) if pr["S"].size > 1 else finite
                lead_ok = per_lead.any([d for d in per_lead.dims if d != "L"]).values
                row["lead_days_with_values"] = [float(ds["L"].values[lead_ok].min()), float(ds["L"].values[lead_ok].max()),
                                                int(lead_ok.sum())]
                row["lead_grid"] = [float(ds["L"].values.min()), float(ds["L"].values.max()), int(ds["L"].size)]
            if good and "M" in pr.dims:
                sel = finite.sel(S=ds["S"].values[has]) if pr["S"].size > 1 else finite
                members = sel.any("L").sum("M").values if "L" in sel.dims else sel.sum("M").values
                row["members_with_values"] = [int(np.min(members)), int(np.max(members))]
            if good:
                gaps = np.diff([s.timestamp() for s in good]) / 86400
                row["start_spacing_days"] = [float(gaps.min()), float(np.median(gaps)), float(gaps.max())] if len(gaps) else None
    except Exception as error:
        row.update({"ok": False, "error": f"{type(error).__name__}: {str(error)[:200]}"})
    row["seconds"] = round(time.monotonic() - t0, 1)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--models", nargs="*", default=list(MODELS))
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    jobs = []
    for model in args.models:                                   # forecasts first: they decide the issue dates
        jobs += [(model, "forecast", b, FORECAST_YEAR) for b in MODELS[model][2]]
    for model in args.models:
        _, hind, _, (y0, y1) = MODELS[model]
        jobs += [(model, "hindcast", hind, y) for y in range(y0, y1 + 1)]
    done_file = args.out / "rows.jsonl"                         # one line per finished request, so a rerun resumes
    rows = [json.loads(line) for line in done_file.read_text().splitlines()] if done_file.exists() else []
    rows = [r for r in rows if r.get("ok")]
    have = {(r["model"], r["kind"], r["branch"], r["year"]) for r in rows}
    jobs = [j for j in jobs if j not in have]
    print(f"{len(have)} requests already done, {len(jobs)} to run", flush=True)

    def run(job):
        row = check_year(*job)
        with lock:
            if row.get("ok"):
                with open(done_file, "a") as handle:
                    handle.write(json.dumps(row) + "\n")
            print(json.dumps({k: row.get(k) for k in ("model", "kind", "branch", "year", "ok", "starts_on_grid",
                                                      "starts_with_values", "members_with_values",
                                                      "lead_days_with_values", "seconds", "error")}), flush=True)
        return row

    lock = threading.Lock()
    with ThreadPoolExecutor(args.workers) as pool:
        rows += list(pool.map(run, jobs))
    rows = [r for r in rows if r["model"] in args.models]
    for model in args.models:
        mine = [r for r in rows if r["model"] == model]
        record = {"model": model, "point": POINT, "checked": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                  "rows": mine}
        (args.out / f"{model}.json").write_text(json.dumps(record, indent=2) + "\n")
    fields = ["model", "kind", "branch", "year", "ok", "units", "starts_on_grid", "starts_with_values", "starts_empty",
              "first_with_values", "last_with_values", "weekdays_with_values", "hours_with_values",
              "members_with_values", "lead_days_with_values", "start_spacing_days", "error"]
    all_rows = []
    for path in sorted(args.out.glob("*.json")):
        all_rows += json.loads(path.read_text())["rows"]
    with open(args.out / "summary.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"wrote {len(all_rows)} rows")


if __name__ == "__main__":
    main()
