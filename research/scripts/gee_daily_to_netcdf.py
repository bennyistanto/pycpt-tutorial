"""Convert the Earth Engine daily CHIRPS v3.0 exports (monthly multi-band GeoTIFFs) into one NetCDF per year.

Input  H:/temp/chirps/daily/pycpt_CHIRPS3_IDN_<variant>/chirps3_<variant>_idn_bbox_<YYYYMMDD>_<YYYYMMDD>.tif
       (one band per UTC day, named dYYYYMMDD; see research/scripts/gee/README.md)
Output E:/temp/chirps/daily-idn/chirps3_<variant>_daily_idn_<YYYY>.nc
       precip(time, lat, lon), mm/day, float32, NaN for no data, native 0.05 degree grid (pixel centres).

Checks per year: every calendar day present exactly once (the pilot days exported twice are taken once,
after checking both copies are identical), one grid for all files, no negative values.

Runs with any Python that has rasterio, xarray and netCDF4 (the Windows miniforge here):

    python research/scripts/gee_daily_to_netcdf.py --variant rnl --years 2000-2023
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import re
from pathlib import Path

import numpy as np
import rasterio
import xarray as xr

SOURCE = Path("H:/temp/chirps/daily")
TARGET = Path("E:/temp/chirps/daily-idn")


def parse_years(text):
    out = set()
    for part in text.split(","):
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return sorted(out)


def files_for(variant, year):
    out = []
    for path in glob.glob(str(SOURCE / f"pycpt_CHIRPS3_IDN_{variant}" / "*.tif")):
        m = re.search(r"_(\d{8})_(\d{8})\.tif$", path)
        if m and m.group(1)[:4] == str(year):
            out.append(path)
    return sorted(out)


def convert(variant, year):
    days = {}
    grid = None
    for path in files_for(variant, year):
        with rasterio.open(path) as src:
            this = (str(src.crs), tuple(round(v, 6) for v in src.transform[:6]), src.width, src.height)
            if grid is None:
                grid, transform, width, height = this, src.transform, src.width, src.height
            elif this != grid:
                raise SystemExit(f"{path}: grid differs from the year's first file")
            data = src.read().astype("float32")
            nodata = src.nodata
            for name, band in zip(src.descriptions, data):
                day = dt.datetime.strptime(name, "d%Y%m%d").date()
                band = np.where(band == nodata, np.nan, band)
                if day in days:
                    if not np.array_equal(days[day], band, equal_nan=True):
                        raise SystemExit(f"{day}: two exported copies differ")
                    continue
                days[day] = band
    expected = [dt.date(year, 1, 1) + dt.timedelta(days=i) for i in range((dt.date(year + 1, 1, 1) - dt.date(year, 1, 1)).days)]
    present = [d for d in expected if d in days]
    if not present:
        return None
    missing = [d for d in expected if d not in days and d <= max(days)]
    if missing:
        raise SystemExit(f"{variant} {year}: missing days inside the record, first {missing[:3]}")
    stack = np.stack([days[d] for d in present])
    if np.nanmin(stack) < 0:
        raise SystemExit(f"{variant} {year}: negative rainfall")
    lon = np.round(transform.c + transform.a * (np.arange(width) + .5), 3)
    lat = np.round(transform.f + transform.e * (np.arange(height) + .5), 3)
    ds = xr.Dataset({"precip": (("time", "lat", "lon"), stack)},
                    coords={"time": np.array(present, dtype="datetime64[ns]"), "lat": lat, "lon": lon})
    ds.precip.attrs = {"units": "mm/day", "long_name": f"CHIRPS v3.0 daily precipitation ({variant})",
                       "comment": "Day D covers 00 UTC D to 00 UTC D+1 (CHC daily readme). NaN = no data."}
    ds.attrs = {"source": f"Earth Engine UCSB-CHC/CHIRPS/V3/DAILY_{variant.upper()}, exported by research/scripts/gee/chirps3_daily_to_drive.js",
                "converted_by": "research/scripts/gee_daily_to_netcdf.py", "created": dt.date.today().isoformat()}
    TARGET.mkdir(parents=True, exist_ok=True)
    out = TARGET / f"chirps3_{variant}_daily_idn_{year}.nc"
    tmp = out.with_suffix(".part.nc")
    ds.to_netcdf(tmp, encoding={"precip": {"zlib": True, "complevel": 4, "dtype": "float32",
                                           "chunksizes": (1, len(lat), len(lon))}})
    tmp.replace(out)
    return out, len(present), out.stat().st_size


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--variant", choices=["rnl", "sat"], default="rnl")
    parser.add_argument("--years", default="2000-2023")
    args = parser.parse_args()
    for year in parse_years(args.years):
        result = convert(args.variant, year)
        if result is None:
            print(f"{args.variant} {year}: no files")
            continue
        out, n, size = result
        print(f"{out.name}: {n} days, {size / 1e6:.0f} MB", flush=True)


if __name__ == "__main__":
    main()
