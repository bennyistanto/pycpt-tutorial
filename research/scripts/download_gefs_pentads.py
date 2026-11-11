"""Download GEFSv12 daily precipitation for the pentad lead-time case (subseasonal, pentads +1 to +6).

Design (shared with the notebook through `design()`):
  * Pentads follow CHIRPS: days 1-5, 6-10, 11-15, 16-20, 21-25 and 26 to the end of each month
    (CHC's CHIRPS v3.0 readme), so they are 5 days long except the sixth (3 to 6 days).
  * Real time: a forecast is issued on the last day of a pentad, from the GEFSv12 run started at
    00 UTC that day (GEFSv12 runs daily), for the next six pentads. Pentad +1 starts on day 1
    after the issue date, pentad +k on day 1 + the lengths of the k-1 pentads before it.
  * Training: GEFSv12 hindcasts (2000-2018) start on Wednesdays only. For each October-December
    target pentad and lead, the training sample uses the one Wednesday whose start-to-target offset
    falls in a 7-day window around the real-time offsets of that lead (WINDOWS). Every 7-day window
    holds exactly one Wednesday, so all leads are trained on the same targets. `check_design()`
    asserts that every 2023 real-time offset lies inside its lead's window and that no target
    needs a model day beyond 34.
  * Missing runs: IRI's GEFSv12_CPC real-time forecast started 5 December 2023 holds only missing
    values (every member and day; checked 11 November 2026, also after a fresh download). As a
    forecaster would, that issue date uses the latest complete run, 4 December 00 UTC
    (RUN_FOR_ISSUE); its offsets are one day longer and still inside every training window.

Uses the request, check and download helpers of `download_gefs_dekads.py` (same IRI branch, box
and raw cache), so files already downloaded for the dekad and weekly cases are reused.

    python research/scripts/download_gefs_pentads.py --out ~/PyCPT/indonesia-ond-2023-dekads/gefs --dry-run
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import download_gefs_dekads as base  # noqa: E402

WINDOWS = {1: (1, 7), 2: (3, 9), 3: (8, 14), 4: (13, 19), 5: (18, 24), 6: (23, 29)}   # start-to-target offset, days
TRAINING_YEARS = range(2000, 2019)
FORECAST_YEAR = 2023
TARGET_MONTHS = (10, 11, 12)
LATEST_MODEL_DAY = 34
RUN_FOR_ISSUE = {dt.date(2023, 12, 5): dt.date(2023, 12, 4)}   # issue date -> run used (see docstring)


def month_pentads(year, month):
    last = calendar.monthrange(year, month)[1]
    firsts = [1, 6, 11, 16, 21, 26]
    return [(dt.date(year, month, f), dt.date(year, month, firsts[i + 1]) if i < 5 else dt.date(year, month, last) + dt.timedelta(days=1))
            for i, f in enumerate(firsts)]


def pentads_between(first_month, last_month):
    """All pentads from the first of first_month (year, month) to the end of last_month, in order."""
    out, (y, m) = [], first_month
    while (y, m) <= last_month:
        out += month_pentads(y, m)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def design():
    """One row per (target pentad, lead): the start used, its offset and the model days needed."""
    rows = []
    for year in TRAINING_YEARS:
        for first, end in pentads_between((year, 10), (year, 12)):
            for lead, (a, b) in WINDOWS.items():
                starts = [first - dt.timedelta(days=o) for o in range(a, b + 1) if (first - dt.timedelta(days=o)).weekday() == 2]
                assert len(starts) == 1
                offset = (first - starts[0]).days
                rows.append({"kind": "hindcast", "year": year, "pentad": first, "end": end, "lead": lead, "issued": starts[0], "start": starts[0],
                             "first_day": offset, "days": (end - first).days, "last_day": offset + (end - first).days - 1})
    sequence = pentads_between((FORECAST_YEAR, 8), (FORECAST_YEAR, 12))
    for i, (first, end) in enumerate(sequence):
        if first.month not in TARGET_MONTHS:
            continue
        for lead in WINDOWS:
            issue = sequence[i - lead][1] - dt.timedelta(days=1)          # last day of the pentad `lead` before
            run = RUN_FOR_ISSUE.get(issue, issue)
            offset = (first - run).days
            rows.append({"kind": "forecast", "year": FORECAST_YEAR, "pentad": first, "end": end, "lead": lead, "issued": issue, "start": run,
                         "first_day": offset, "days": (end - first).days, "last_day": offset + (end - first).days - 1})
    return rows


def check_design(rows=None):
    rows = design() if rows is None else rows
    for r in rows:
        a, b = WINDOWS[r["lead"]]
        if r["kind"] == "forecast":
            assert a <= r["first_day"] <= b, f"2023 offset {r['first_day']} outside window {a}-{b} for lead {r['lead']}"
        assert r["last_day"] <= LATEST_MODEL_DAY, r
    return True


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
    check_design()
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
