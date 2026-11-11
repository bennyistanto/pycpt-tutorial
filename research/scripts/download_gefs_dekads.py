"""Download GEFSv12 daily precipitation for the dekad lead-time case: forecasts of the next 1, 2 and 3 dekads.

Design (shared with the notebook through `design()`):
  * A forecast is issued on the last day of a dekad (model start 00 UTC that day) and covers
    dekad +1, +2 and +3. In real time these begin 1, 11-12 and 21-22 days after the start.
  * GEFSv12 forecasts start every day, so the 2023 forecasts use exactly those issue dates.
  * GEFSv12 hindcasts start only on Wednesdays, so training uses, for each October-December
    target dekad of 2000-2018 and each lead, the one Wednesday whose start falls inside a
    7-day window around the real-time offset: 1-7 days (lead 1), 8-14 (lead 2), 18-24 (lead 3).
    Every window holds exactly one Wednesday; the latest model day used is 34.

Source: IRI Data Library, SubX EMC GEFSv12_CPC, the branch PyCPT's subseasonal catalog uses.
  hindcasts  .hindcast/.weekly/.pr   Wednesday starts, 11 members, kg m-2 per day
  forecasts  .forecast/.pr           daily starts, 31 members, kg m-2 s-1
Request: predictor box 85-155E, 20S-20N (as the seasonal cases), all members, daily lead
slots L = 1.5 .. 34.5 (days [1, 35)). Files from an earlier run that stop at L = 31.5 are
kept when every target they serve ends by day 31.

One raw NetCDF per start in --out. Resumable: a start is skipped when its file opens and has
the expected members, units, grid and every lead slot its targets need. Anonymous access.

    python research/scripts/download_gefs_dekads.py --out ~/PyCPT/indonesia-ond-2023-dekads/gefs --dry-run
    python research/scripts/download_gefs_dekads.py --out ~/PyCPT/indonesia-ond-2023-dekads/gefs
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import xarray as xr

BASE = "https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX/.EMC/.GEFSv12_CPC"
BRANCH = {"hindcast": "/.hindcast/.weekly/.pr", "forecast": "/.forecast/.pr"}
MEMBERS = {"hindcast": 11, "forecast": 31}
UNITS = {"hindcast": "kg m-2", "forecast": "kg m-2 s-1"}
BOX = dict(west=85, east=155, south=-20, north=20)
REQUEST_LEADS = np.arange(1.5, 35.0, 1.0)            # daily midpoints, days [1, 35)
WINDOWS = {1: (1, 7), 2: (8, 14), 3: (18, 24)}       # start-to-target offsets (days) for hindcast training
TRAINING_YEARS = range(2000, 2019)
FORECAST_YEAR = 2023
TARGET_MONTHS = (10, 11, 12)
USER_AGENT = "gefs-dekad-downloader/2.0 (python urllib)"


def dekads(year):
    out = []
    for m in range(1, 13):
        nxt = dt.date(year + (m == 12), m % 12 + 1, 1)
        out += [(dt.date(year, m, 1), dt.date(year, m, 11)), (dt.date(year, m, 11), dt.date(year, m, 21)),
                (dt.date(year, m, 21), nxt)]
    return out


def design():
    """One row per (target dekad, lead): the start that forecasts it, its offset and the model days used."""
    rows = []
    all_dekads = sorted(d for y in range(min(TRAINING_YEARS) - 1, FORECAST_YEAR + 2) for d in dekads(y))
    for year in list(TRAINING_YEARS):
        for first, end in dekads(year):
            if first.month not in TARGET_MONTHS:
                continue
            for lead, (lo, hi) in WINDOWS.items():
                starts = [first - dt.timedelta(days=d) for d in range(lo, hi + 1)
                          if (first - dt.timedelta(days=d)).weekday() == 2]
                assert len(starts) == 1
                rows.append(_row("hindcast", year, first, end, lead, starts[0]))
    for i, (first, end) in enumerate(all_dekads):
        if first.year != FORECAST_YEAR or first.month not in TARGET_MONTHS:
            continue
        for lead in WINDOWS:
            issue_dekad = all_dekads[i - lead + 1]          # dekad +1 of the issue
            rows.append(_row("forecast", FORECAST_YEAR, first, end, lead, issue_dekad[0] - dt.timedelta(days=1)))
    return rows


def _row(kind, year, first, end, lead, start):
    offset, days = (first - start).days, (end - first).days
    return {"kind": kind, "year": year, "dekad": first, "end": end, "lead": lead, "start": start,
            "first_day": offset, "days": days, "last_day": offset + days - 1}


def needed_starts():
    """{(kind, start): latest model day that start must cover}."""
    need = {}
    for r in design():
        key = (r["kind"], r["start"])
        need[key] = max(need.get(key, 0), r["last_day"])
    return dict(sorted(need.items(), key=lambda kv: (kv[0][0] != "hindcast", kv[0][1])))


def url_for(kind, start):
    label = f"0000 {start.day} {start:%b} {start.year}".replace(" ", "%20")
    return (BASE + BRANCH[kind] + f"/S/({label})/VALUES/X/{BOX['west']}/{BOX['east']}/RANGE"
            f"/Y/{BOX['south']}/{BOX['north']}/RANGE/L/{REQUEST_LEADS[0]}/{REQUEST_LEADS[-1]}/RANGE/data.nc")


def check(path, kind, start, last_day=31):
    """Return None if the file is a complete GEFS request covering days 1..last_day, else the reason."""
    try:
        with xr.open_dataset(path, decode_timedelta=False) as ds:
            pr = ds["pr"]
            if pr.attrs.get("units") != UNITS[kind]:
                return f"units {pr.attrs.get('units')!r}"
            if ds.sizes.get("M") != MEMBERS[kind]:
                return f"{ds.sizes.get('M')} members"
            needed = np.arange(1.5, last_day + 1.0, 1.0)
            if not np.isin(needed, ds["L"].values).all():
                return f"lead slots end at {ds['L'].values.max()}, need {needed[-1]}"
            if np.datetime64(ds["S"].values[0], "D") != np.datetime64(start, "D"):
                return f"start {ds['S'].values[0]}"
            if ds.sizes.get("X") != BOX["east"] - BOX["west"] + 1 or ds.sizes.get("Y") != BOX["north"] - BOX["south"] + 1:
                return f"grid {ds.sizes.get('Y')} x {ds.sizes.get('X')}"
    except Exception as e:  # unreadable or truncated file
        return f"unreadable ({type(e).__name__})"
    return None


def path_for(out, kind, start):
    return Path(out) / f"gefs-{kind}-{start.isoformat()}.nc"


def fetch(url, path, attempts=5):
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=300) as r:
                body = r.read()
            if not (body.startswith(b"CDF") or body.startswith(b"\x89HDF")):
                raise ValueError("response is not NetCDF")
            tmp = path.with_suffix(".part")
            tmp.write_bytes(body)
            tmp.replace(path)
            return len(body)
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError, OSError) as e:
            if attempt == attempts:
                raise
            wait = 20 * attempt
            print(f"  attempt {attempt} failed ({type(e).__name__}: {str(e)[:80]}); waiting {wait} s", flush=True)
            time.sleep(wait)


def ensure(out, kind, start, last_day):
    """Download the start if its file is missing or does not cover last_day; return bytes fetched (0 if kept)."""
    path = path_for(out, kind, start)
    if path.exists() and check(path, kind, start, last_day) is None:
        return 0
    size = fetch(url_for(kind, start), path)
    problem = check(path, kind, start, last_day)
    if problem:
        raise SystemExit(f"{path.name}: downloaded but {problem}; stopping so it can be investigated")
    return size


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    out = args.out.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    need = needed_starts()
    todo = [(k, s, d) for (k, s), d in need.items()
            if not (path_for(out, k, s).exists() and check(path_for(out, k, s), k, s, d) is None)]
    n_h = sum(k == "hindcast" for k, _ in need)
    print(f"{len(need)} starts ({n_h} hindcasts, {len(need) - n_h} forecasts); to download: {len(todo)}")
    if args.dry_run:
        for k, s, d in todo[:10]:
            print(f"  {k} {s} (needs day {d})")
        return
    log = out / "download-log.csv"
    new = not log.exists() or log.stat().st_size == 0
    with open(log, "a", newline="") as handle:
        writer = csv.writer(handle)
        if new:
            writer.writerow(["finished_utc", "kind", "start", "bytes", "seconds", "url"])
        for n, (kind, start, last_day) in enumerate(todo, 1):
            t0 = time.monotonic()
            size = ensure(out, kind, start, last_day)
            writer.writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), kind, start, size,
                             round(time.monotonic() - t0, 1), url_for(kind, start)])
            handle.flush()
            print(f"[{n}/{len(todo)}] {kind} {start}: {size / 1e6:.1f} MB", flush=True)
    print(f"complete and checked: {len(need)} starts")


if __name__ == "__main__":
    main()
