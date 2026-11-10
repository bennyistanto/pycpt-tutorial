"""Download GEFSv12 daily precipitation for the dekad lead-time case (subseasonal, dekads 1-3 ahead).

Source: IRI Data Library, SubX EMC GEFSv12_CPC, the branch PyCPT's subseasonal catalog uses.
  hindcasts  .hindcast/.weekly/.pr   Wednesday starts, 11 members, kg m-2 per day
  forecasts  .forecast/.pr           daily starts, 31 members, kg m-2 s-1
Request: predictor box 85-155E, 20S-20N (as the seasonal cases), all members, daily
lead slots L = 1.5 .. 31.5 (days [1, 32)), which covers every target dekad of the
lead rule in temp/subseasonal-plan.md (latest day used: 31).

Starts: every Wednesday whose start falls 1-21 days before an October-December dekad,
2000-2018 (hindcasts) and 2023 (forecasts): 278 + 15.

One raw NetCDF per start in --out. Resumable: a start is skipped when its file exists,
opens, and has the expected members, lead slots and grid. Anonymous access; no key.

    python research/scripts/download_gefs_dekads.py --out ~/PyCPT/indonesia-ond-2023-dekads/gefs --dry-run
    python research/scripts/download_gefs_dekads.py --out ~/PyCPT/indonesia-ond-2023-dekads/gefs --limit 2
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
LEADS = np.arange(1.5, 32.0, 1.0)          # daily midpoints, days [1, 32)
USER_AGENT = "gefs-dekad-downloader/1.0 (python urllib)"


def dekads(year):
    out = []
    for m in range(1, 13):
        nxt = dt.date(year + (m == 12), m % 12 + 1, 1)
        out += [(dt.date(year, m, 1), dt.date(year, m, 11)), (dt.date(year, m, 11), dt.date(year, m, 21)),
                (dt.date(year, m, 21), nxt)]
    return out


def needed_starts(years):
    """Wednesdays 1-21 days before the start of an OND dekad of the given years."""
    starts = set()
    for year in years:
        for first, _ in dekads(year):
            if first.month in (10, 11, 12):
                starts.update(first - dt.timedelta(days=d) for d in range(1, 22)
                              if (first - dt.timedelta(days=d)).weekday() == 2)
    return sorted(starts)


def url_for(kind, start):
    label = f"0000 {start.day} {start:%b} {start.year}".replace(" ", "%20")
    return (BASE + BRANCH[kind] + f"/S/({label})/VALUES/X/{BOX['west']}/{BOX['east']}/RANGE"
            f"/Y/{BOX['south']}/{BOX['north']}/RANGE/L/{LEADS[0]}/{LEADS[-1]}/RANGE/data.nc")


def check(path, kind, start):
    """Return None if the file is a complete, expected GEFS request, else the reason."""
    try:
        with xr.open_dataset(path, decode_timedelta=False) as ds:
            pr = ds["pr"]
            if pr.attrs.get("units") != UNITS[kind]:
                return f"units {pr.attrs.get('units')!r}"
            if ds.sizes.get("M") != MEMBERS[kind]:
                return f"{ds.sizes.get('M')} members"
            if not np.array_equal(ds["L"].values, LEADS):
                return f"lead slots {ds['L'].values.min()}..{ds['L'].values.max()} ({ds.sizes['L']})"
            if np.datetime64(ds["S"].values[0], "D") != np.datetime64(start, "D"):
                return f"start {ds['S'].values[0]}"
            if ds.sizes.get("X") != BOX["east"] - BOX["west"] + 1 or ds.sizes.get("Y") != BOX["north"] - BOX["south"] + 1:
                return f"grid {ds.sizes.get('Y')} x {ds.sizes.get('X')}"
    except Exception as e:  # unreadable or truncated file
        return f"unreadable ({type(e).__name__})"
    return None


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


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, help="download at most this many new starts (for testing)")
    parser.add_argument("--kind", choices=["hindcast", "forecast"], help="only this branch (default both)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    out = args.out.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    jobs = [("hindcast", s) for s in needed_starts(range(2000, 2019))] + [("forecast", s) for s in needed_starts([2023])]
    if args.kind:
        jobs = [j for j in jobs if j[0] == args.kind]
    print(f"{len(jobs)} starts: {sum(k == 'hindcast' for k, _ in jobs)} hindcasts "
          f"({jobs[0][1]} .. {jobs[-1][1]}), "
          f"{sum(k == 'forecast' for k, _ in jobs)} forecasts")
    if args.dry_run:
        print("example URL:", url_for(*jobs[0]))
        return
    log = out / "download-log.csv"
    new = not log.exists()
    done = fetched = 0
    with open(log, "a", newline="") as handle:
        writer = csv.writer(handle)
        if new:
            writer.writerow(["finished_utc", "kind", "start", "bytes", "seconds", "url"])
        for kind, start in jobs:
            path = out / f"gefs-{kind}-{start.isoformat()}.nc"
            if path.exists() and check(path, kind, start) is None:
                done += 1
                continue
            if args.limit is not None and fetched >= args.limit:
                break
            url = url_for(kind, start)
            t0 = time.monotonic()
            size = fetch(url, path)
            problem = check(path, kind, start)
            if problem:
                raise SystemExit(f"{path.name}: downloaded but {problem}; stopping so it can be investigated")
            seconds = time.monotonic() - t0
            fetched += 1
            writer.writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), kind, start, size,
                             round(seconds, 1), url])
            handle.flush()
            print(f"{path.name}: {size / 1e6:.1f} MB in {seconds:.0f} s ({done + fetched}/{len(jobs)})", flush=True)
    print(f"complete and checked: {done + fetched} of {len(jobs)} starts")


if __name__ == "__main__":
    main()
