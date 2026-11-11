"""Convert the Earth Engine CHIRPS v3.0 pentad exports (one 72-band GeoTIFF per year) into one NetCDF per year.

Input  H:/temp/chirps/pentad/chirps3_pentad_idn_bbox_<YYYY>.tif   (bands pYYYYMMDD)
       H:/temp/chirps/pentad/chirps3_pentad_idn_bbox_<YYYY>_manifest.csv
       (written by research/scripts/gee/chirps3_pentad_to_drive.js)
Output E:/temp/chirps/pentad-idn/chirps3_pentad_idn_<YYYY>.nc
       precip(time, lat, lon) in mm per pentad, float32, NaN for no data; time = first day of the pentad,
       time_bnds = [first day, day after the last day), native 0.05 degree grid (pixel centres).

Checks per year, so the calendar is measured, not assumed:
  * 72 bands, named by the pentad's first day, in date order;
  * the manifest has one row per band with the same first day, and its month/pentad properties
    agree with CHIRPS pentads (days 1-5, 6-10, 11-15, 16-20, 21-25, 26 to the end of the month);
  * the manifest's end dates are reported: whether Earth Engine stores the day after the pentad
    or its last day is printed, not guessed;
  * the grid equals the daily export's grid (same transform and size), and no value is negative.

Runs with any Python that has rasterio, xarray and netCDF4 (the Windows miniforge here):

    python research/scripts/gee_pentad_to_netcdf.py --years 2000-2018,2023
"""
from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
from collections import Counter
from pathlib import Path

import numpy as np
import rasterio
import xarray as xr

SOURCE = Path("H:/temp/chirps/pentad")
DAILY = Path("H:/temp/chirps/daily/pycpt_CHIRPS3_IDN_rnl")
TARGET = Path("E:/temp/chirps/pentad-idn")
FIRSTS = [1, 6, 11, 16, 21, 26]


def parse_years(text):
    out = set()
    for part in text.split(","):
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return sorted(out)


def pentad_bounds(first):
    k = FIRSTS.index(first.day)
    if k < 5:
        return first, first.replace(day=FIRSTS[k + 1])
    return first, dt.date(first.year, first.month, calendar.monthrange(first.year, first.month)[1]) + dt.timedelta(days=1)


def daily_grid():
    path = next(DAILY.glob("*.tif"))
    with rasterio.open(path) as src:
        return tuple(round(v, 6) for v in src.transform[:6]), src.width, src.height


def convert(year, ends):
    tif = SOURCE / f"chirps3_pentad_idn_bbox_{year}.tif"
    manifest = SOURCE / f"chirps3_pentad_idn_bbox_{year}_manifest.csv"
    if not tif.exists() or not manifest.exists():
        return None
    with rasterio.open(tif) as src:
        names = list(src.descriptions)
        grid = (tuple(round(v, 6) for v in src.transform[:6]), src.width, src.height)
        if grid != daily_grid():
            raise SystemExit(f"{year}: pentad grid {grid} differs from the daily grid {daily_grid()}")
        data = src.read().astype("float32")
        nodata, transform, width, height = src.nodata, src.transform, src.width, src.height
    firsts = [dt.datetime.strptime(n, "p%Y%m%d").date() for n in names]
    expected = [dt.date(year, m, d) for m in range(1, 13) for d in FIRSTS]
    if firsts != expected:
        raise SystemExit(f"{year}: band dates are not the 72 CHIRPS pentads in order")
    with open(manifest, newline="") as f:
        rows = list(csv.DictReader(f))
    if [dt.date.fromisoformat(r["start"]) for r in rows] != firsts:
        raise SystemExit(f"{year}: manifest start dates differ from the band names")
    for r, first in zip(rows, firsts):
        in_month = FIRSTS.index(first.day) + 1
        number = int(float(r["pentad"]))
        if int(float(r["month"])) != first.month or number not in (in_month, (first.month - 1) * 6 + in_month):
            raise SystemExit(f"{year}: manifest month/pentad properties disagree at {first}")
        if first.month > 1:                       # January cannot tell the two numberings apart
            ends["pentad property numbered within the " + ("month" if number == in_month else "year")] += 1
        lo, hi = pentad_bounds(first)
        end = dt.date.fromisoformat(r["end"])
        ends[("day after the pentad" if end == hi else "last day of the pentad" if end == hi - dt.timedelta(days=1)
              else f"other ({end - lo})")] += 1
    data = np.where(data == nodata, np.nan, data)
    if np.nanmin(data) < 0:
        raise SystemExit(f"{year}: negative rainfall")
    lon = np.round(transform.c + transform.a * (np.arange(width) + .5), 3)
    lat = np.round(transform.f + transform.e * (np.arange(height) + .5), 3)
    bounds = np.array([pentad_bounds(f) for f in firsts], dtype="datetime64[ns]")
    ds = xr.Dataset({"precip": (("time", "lat", "lon"), data), "time_bnds": (("time", "nv"), bounds)},
                    coords={"time": np.array(firsts, dtype="datetime64[ns]"), "lat": lat, "lon": lon})
    ds.time.attrs["bounds"] = "time_bnds"
    ds.precip.attrs = {"units": "mm", "cell_methods": "time: sum", "long_name": "CHIRPS v3.0 pentad precipitation total",
                       "comment": "CHIRPS pentads: days 1-5, 6-10, 11-15, 16-20, 21-25, 26-end of month. NaN = no data."}
    ds.attrs = {"source": "Earth Engine UCSB-CHC/CHIRPS/V3/PENTAD, exported by research/scripts/gee/chirps3_pentad_to_drive.js",
                "converted_by": "research/scripts/gee_pentad_to_netcdf.py", "created": dt.date.today().isoformat()}
    TARGET.mkdir(parents=True, exist_ok=True)
    out = TARGET / f"chirps3_pentad_idn_{year}.nc"
    tmp = out.with_suffix(".part.nc")
    units = {"units": "days since 1970-01-01", "calendar": "proleptic_gregorian"}      # same units for time and its bounds (CF)
    ds.to_netcdf(tmp, encoding={"precip": {"zlib": True, "complevel": 4, "dtype": "float32", "chunksizes": (1, height, width)},
                                "time": units, "time_bnds": units})
    tmp.replace(out)
    return out, out.stat().st_size


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--years", default="2000-2018,2023")
    args = parser.parse_args()
    ends = Counter()
    for year in parse_years(args.years):
        result = convert(year, ends)
        if result is None:
            print(f"{year}: files not found in {SOURCE}")
            continue
        print(f"{result[0].name}: 72 pentads, {result[1] / 1e6:.0f} MB", flush=True)
    print("Manifest checks (pentad counts):", dict(ends))


if __name__ == "__main__":
    main()
