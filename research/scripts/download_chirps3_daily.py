"""Download CHIRPS v3.0 daily Final rainfall (NetCDF, 0.05 degree, global) from the Climate Hazards Center.

Files come from https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/<variant>/netcdf/<layout>/
  variant  rnl: daily timing from ERA5 (1981 onwards); sat: daily timing from IMERG (1998 onwards)
  layout   byYear: one file per year (about 3-4 GiB); byMonth: one file per month (about 300-360 MiB)

Both variants split the same CHIRPS v3.0 pentad totals into days; see CHC's daily readme:
https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/readme.txt

The CHC server limits request rates (it answers HTTP 429 "Too Many Requests"), so this
script is deliberately gentle:
  * one directory listing per folder gives the file names and approximate sizes; there is
    no separate size request per file
  * one download at a time by default, with a pause between files
  * on HTTP 429 or 503 it waits as long as the server's Retry-After header asks, or
    1, 2, 4 ... up to 15 minutes, then continues
Downloads resume from <name>.part with an HTTP Range request. A file is complete only when
its size equals the total the server reports for it and it starts with the HDF5 signature
of NetCDF-4 files; it is then renamed from .part and recorded in download-log.csv.

Standard library only (Python 3.9+). Examples:
    python download_chirps3_daily.py --out F:/chirps3/daily --variant rnl sat --years 1981-2026 --dry-run
    python download_chirps3_daily.py --out F:/chirps3/daily --variant rnl sat --years 1981-2026
    python download_chirps3_daily.py --out F:/chirps3/daily --variant rnl --layout byMonth --years 2023 --months 9-12

Re-running the same command skips finished files and resumes partial ones.
Space needed (server listing, 10 November 2026): rnl 1981-2026 by year 172.3 GiB;
sat 1998-2026 by year 92.8 GiB.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import email.utils
import html
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final"
USER_AGENT = "chirps3-daily-downloader/1.1 (python urllib)"
HDF5_SIGNATURE = b"\x89HDF\r\n\x1a\n"
CHUNK = 4 * 2**20
UNITS = {"B": 1, "KiB": 2**10, "MiB": 2**20, "GiB": 2**30, "TiB": 2**40}
ROW = re.compile(r'<a href="([^"/?]+\.nc)"[^>]*>.*?</a></td><td class="size">\s*([\d.]+)\s*([KMGT]?i?B)\s*</td>')


def say(*parts):
    print(dt.datetime.now().strftime("%H:%M:%S"), *parts, flush=True)


class RateLimited(Exception):
    def __init__(self, wait):
        super().__init__(f"server asked to wait {wait:.0f} s")
        self.wait = wait


def open_url(url, headers=None, timeout=120):
    """urlopen that turns HTTP 429/503 into RateLimited with the server's Retry-After, if any."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code in (429, 503):
            raise RateLimited(retry_after(e.headers.get("Retry-After"))) from e
        raise


def retry_after(value):
    if not value:
        return 0.0
    if value.strip().isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
        return max(0.0, (when - dt.datetime.now(dt.timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return 0.0


def patiently(action, what, attempts=12):
    """Run action(); wait out rate limits and transient network errors, with growing waits."""
    for attempt in range(1, attempts + 1):
        try:
            return action()
        except RateLimited as e:
            wait = max(e.wait, min(900, 60 * 2 ** (attempt - 1)))
            say(f"{what}: server is rate-limiting (HTTP 429/503); waiting {wait / 60:.1f} min")
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            wait = min(600, 20 * attempt)
            say(f"{what}: attempt {attempt} failed ({type(e).__name__}: {str(e)[:80]}); waiting {wait} s")
        if attempt == attempts:
            raise RuntimeError(f"{what}: gave up after {attempts} attempts; rerun later to continue")
        time.sleep(wait)


def list_files(variant, layout):
    """[(name, approximate bytes)] from one directory listing."""
    url = f"{BASE}/{variant}/netcdf/{layout}/"

    def get():
        with open_url(url, timeout=60) as r:
            return r.read().decode("utf-8", "replace")

    page = patiently(get, f"listing {variant}/{layout}")
    rows = [(html.unescape(n), float(v) * UNITS[u]) for n, v, u in ROW.findall(page)]
    if not rows:
        raise SystemExit(f"No .nc files found in {url}; the listing format may have changed.")
    return url, sorted(rows)


def file_period(name):
    m = re.search(r"\.(\d{4})(?:\.(\d{2}))?\.days_p05\.nc$", name)
    if not m:
        raise ValueError(f"Unexpected file name: {name}")
    return int(m.group(1)), int(m.group(2)) if m.group(2) else None


def parse_range(text, low, high):
    values = set()
    for part in text.split(","):
        a, _, b = part.strip().partition("-")
        values.update(range(int(a), int(b or a) + 1))
    bad = [v for v in values if not low <= v <= high]
    if bad:
        raise SystemExit(f"Out of range: {bad}")
    return sorted(values)


def is_hdf5(path):
    with open(path, "rb") as f:
        return f.read(8) == HDF5_SIGNATURE


LOG_HEADER = ["finished_utc", "variant", "file", "bytes", "seconds", "url"]


def logged_sizes(log):
    """{(variant, file): bytes} for every finished file in the log; tolerates a missing header line."""
    if not log.exists():
        return {}
    with open(log, newline="") as handle:
        rows = [r for r in csv.reader(handle) if len(r) == len(LOG_HEADER) and r[0] != LOG_HEADER[0]]
    return {(r[1], r[2]): int(r[3]) for r in rows}


def total_from(response, have):
    """Full file size from a 200 (Content-Length) or 206 (Content-Range: bytes a-b/total) response."""
    if response.status == 206:
        return int(response.headers["Content-Range"].rsplit("/", 1)[1])
    return int(response.headers["Content-Length"])


def download(url, target):
    """Download url into target via target.part, resuming; return (bytes, seconds)."""
    part = target.with_name(target.name + ".part")
    start = time.monotonic()
    state = {"total": None}

    def step():
        have = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            response = open_url(url, headers=headers)
        except urllib.error.HTTPError as e:
            if e.code == 416 and have:  # nothing left to send: the .part already holds the whole file
                state["total"] = have
                return
            raise
        with response:
            if have and response.status != 206:
                say(f"{target.name}: server ignored the resume request, starting again")
                have = 0
            state["total"] = total_from(response, have)
            with open(part, "ab" if have else "wb") as f:
                while True:
                    block = response.read(CHUNK)
                    if not block:
                        break
                    f.write(block)
        if part.stat().st_size < state["total"]:
            raise ConnectionError(f"stream ended at {part.stat().st_size:,} of {state['total']:,} bytes")

    patiently(step, target.name)
    size = part.stat().st_size
    if size != state["total"]:
        raise RuntimeError(f"{target.name}: {size:,} bytes on disk but the server reports {state['total']:,}")
    if not is_hdf5(part):
        part.unlink()
        raise RuntimeError(f"{target.name}: complete size but not an HDF5/NetCDF-4 file; removed")
    os.replace(part, target)
    return size, time.monotonic() - start


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n", 2)[2])
    parser.add_argument("--out", type=Path, required=True, help="output folder; files go in <out>/<variant>/<layout>/")
    parser.add_argument("--variant", nargs="+", choices=["rnl", "sat"], default=["rnl"])
    parser.add_argument("--layout", choices=["byYear", "byMonth"], default="byYear")
    parser.add_argument("--years", default="1981-2026", help="e.g. 2000-2025 or 2000,2023")
    parser.add_argument("--months", default="1-12", help="byMonth only, e.g. 9-12")
    parser.add_argument("--pause", type=float, default=10, help="seconds between files (default 10)")
    parser.add_argument("--dry-run", action="store_true", help="list files and approximate sizes, download nothing")
    args = parser.parse_args()

    years = set(parse_range(args.years, 1981, 2100))
    months = set(parse_range(args.months, 1, 12))
    out = args.out.expanduser()
    log = out / "download-log.csv"
    finished = logged_sizes(log)
    jobs = []
    for variant in args.variant:
        folder_url, rows = list_files(variant, args.layout)
        for name, approx in rows:
            year, month = file_period(name)
            if year in years and (month is None or month in months):
                path = out / variant / args.layout / name
                done = path.exists() and finished.get((variant, name)) == path.stat().st_size
                part = path.with_name(name + ".part")
                jobs.append(dict(variant=variant, url=folder_url + name, path=path, approx=approx, done=done,
                                 partial=part.stat().st_size if part.exists() else 0))
    if not jobs:
        raise SystemExit("No files on the server match those choices.")

    print(f"\n{'variant':8} {'file':40} {'~GiB':>6}  status")
    for j in jobs:
        status = "done" if j["done"] else f"partial ~{j['partial'] / j['approx']:.0%}" if j["partial"] else "to download"
        print(f"{j['variant']:8} {j['path'].name:40} {j['approx'] / 2**30:6.1f}  {status}")
    remaining = sum(j["approx"] - j["partial"] for j in jobs if not j["done"])
    print(f"\n{len(jobs)} files, about {sum(j['approx'] for j in jobs) / 2**30:.1f} GiB; "
          f"about {remaining / 2**30:.1f} GiB still to download (sizes from the server listing, rounded)")
    out.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(out).free
    print(f"Free space at {out}: {free / 2**30:.1f} GiB")
    if args.dry_run:
        return
    if remaining * 1.05 > free:
        raise SystemExit("Not enough free space for the remaining files; choose another --out or fewer years.")

    new_log = not log.exists() or log.stat().st_size == 0
    failures = []
    with open(log, "a", newline="") as handle:
        writer = csv.writer(handle)
        if new_log:
            writer.writerow(LOG_HEADER)
            handle.flush()
        todo = [j for j in jobs if not j["done"]]
        for number, j in enumerate(todo, 1):
            j["path"].parent.mkdir(parents=True, exist_ok=True)
            say(f"[{number}/{len(todo)}] {j['variant']} {j['path'].name}")
            try:
                size, seconds = download(j["url"], j["path"])
            except Exception as e:  # keep going with the other files; report at the end
                say(f"FAILED {j['path'].name}: {e}")
                failures.append(j["path"].name)
                continue
            say(f"done {j['path'].name} ({size / 2**30:.2f} GiB, {size / 2**20 / max(seconds, 1e-9):.1f} MiB/s)")
            writer.writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), j["variant"],
                             j["path"].name, size, round(seconds, 1), j["url"]])
            handle.flush()
            if number < len(todo):
                time.sleep(args.pause)
    say(f"Finished: {len(jobs) - len(failures)} of {len(jobs)} files complete; log {log}")
    if failures:
        say("Not complete (rerun the same command to resume): " + ", ".join(failures))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
