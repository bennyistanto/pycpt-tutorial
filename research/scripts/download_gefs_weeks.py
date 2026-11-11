"""Download GEFSv12 daily precipitation for the weekly lead-time case (subseasonal, issue-relative weeks).

Design (shared with the notebook through `design()`):
  * A forecast is issued on a Wednesday, from the GEFSv12 run started at 00 UTC that day. GEFSv12
    hindcasts start on Wednesdays too, so training and real time use exactly the same leads.
  * Targets are counted from the start: week 1 = days 1-7, week 2 = 8-14, week 3 = 15-21,
    week 4 = 22-28, and weeks 3-4 = days 15-28 (NOAA CPC's week 3-4 outlook). Day 0 is skipped
    because the forecast branch starts at day 1; a week 5 would need day 35, beyond the model.
  * Training targets: every 7-day (or 14-day) window that starts on a Thursday in
    October-December 2000-2018; each target gets exactly one start per lead, so all leads are
    scored on the same targets. 2023: the same rule with the forecast branch.

Uses the request, check and download helpers of `download_gefs_dekads.py` (same IRI branch, box
and raw cache), so files already downloaded for the dekad case are reused.

    python research/scripts/download_gefs_weeks.py --out ~/PyCPT/indonesia-ond-2023-dekads/gefs --dry-run
    python research/scripts/download_gefs_weeks.py --out ~/PyCPT/indonesia-ond-2023-dekads/gefs
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import download_gefs_dekads as base  # noqa: E402

LEADS = {"week1": (1, 7), "week2": (8, 7), "week3": (15, 7), "week4": (22, 7), "week34": (15, 14)}  # first day, length
LEAD_NAMES = {"week1": "Week 1", "week2": "Week 2", "week3": "Week 3", "week4": "Week 4", "week34": "Weeks 3-4"}
TRAINING_YEARS = range(2000, 2019)
FORECAST_YEAR = 2023
TARGET_MONTHS = (10, 11, 12)


def target_starts(year):
    """Thursdays in October-December of the year."""
    d = dt.date(year, 10, 1)
    while d.weekday() != 3:
        d += dt.timedelta(days=1)
    out = []
    while d.year == year:
        out.append(d)
        d += dt.timedelta(days=7)
    return out


def design():
    """One row per (target window, lead): the Wednesday start, offsets and model days used."""
    rows = []
    for kind, years in [("hindcast", TRAINING_YEARS), ("forecast", [FORECAST_YEAR])]:
        for year in years:
            for first in target_starts(year):
                for lead, (offset, length) in LEADS.items():
                    start = first - dt.timedelta(days=offset)
                    assert start.weekday() == 2
                    rows.append({"kind": kind, "year": year, "target": first, "end": first + dt.timedelta(days=length),
                                 "lead": lead, "start": start, "first_day": offset, "days": length,
                                 "last_day": offset + length - 1})
    return rows


def needed_starts():
    need = {}
    for r in design():
        key = (r["kind"], r["start"])
        need[key] = max(need.get(key, 0), r["last_day"])
    return dict(sorted(need.items(), key=lambda kv: (kv[0][0] != "hindcast", kv[0][1])))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    out = args.out.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    need = needed_starts()
    todo = [(k, s, d) for (k, s), d in need.items()
            if not (base.path_for(out, k, s).exists() and base.check(base.path_for(out, k, s), k, s, d) is None)]
    n_h = sum(k == "hindcast" for k, _ in need)
    print(f"{len(need)} starts ({n_h} hindcasts, {len(need) - n_h} forecasts); to download: {len(todo)}")
    if args.dry_run:
        return
    for n, (kind, start, last_day) in enumerate(todo, 1):
        t0 = time.monotonic()
        size = base.ensure(out, kind, start, last_day)
        print(f"[{n}/{len(todo)}] {kind} {start}: {size / 1e6:.1f} MB in {time.monotonic() - t0:.0f} s", flush=True)
    print(f"complete and checked: {len(need)} starts")


if __name__ == "__main__":
    main()
