"""Prepare real CHIRPS3/CFSv2 inputs for a full-Indonesia OND 2023 replay.

Run from the repository root in Debian's pycpt-tutorial environment. The original
CHIRPS files are read only. Credentials are used only for IRI HTTP requests.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys

import cartopy.io.shapereader as shpreader
import cptdl
from cptdl.utilities import read_dlauth
from cptio import open_cptdataset
import numpy as np
import pandas as pd
import requests
import shapely
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pycpt_tutorial.export import save_netcdf

ROOT = Path.home() / "CPT/cases/indonesia-ond-2023"
CHIRPS = Path("/mnt/e/temp/chirps/rolling_dekad/wld_cli_chirps3_month3_bydekad_1981_2025.nc")
YEARS = list(range(1982, 2011)) + [2023]
BOUNDS = dict(west=94, east=142, south=-12, north=7)
PREDICTOR_BOUNDS = dict(west=85, east=155, south=-20, north=20)


def write(data, name, metadata=None):
    path = ROOT / "inputs" / name
    if not path.exists():
        save_netcdf(data, path, metadata=metadata)
    return path


def prepare_observations():
    cached = ROOT / "inputs/observations_chirps3_ond.nc"
    if cached.exists():
        print("USING_CACHED_OBSERVATIONS", cached, flush=True)
        return
    boundary_path = shpreader.natural_earth(resolution="10m", category="cultural", name="admin_0_countries")
    record = next(r for r in shpreader.Reader(boundary_path).records() if r.attributes.get("ADM0_A3") == "IDN")
    geometry = record.geometry
    shapely.prepare(geometry)
    (ROOT / "inputs").mkdir(parents=True, exist_ok=True)
    (ROOT / "inputs/indonesia_boundary.geojson").write_text(json.dumps(shapely.geometry.mapping(geometry)))
    records = []
    with xr.open_dataset(CHIRPS) as source:
        times = pd.DatetimeIndex(source.time.values)
        selected = [int(np.flatnonzero((times.year == year) & (times.month == 12) & (times.day == 21))[0]) for year in YEARS]
        bounds = source.time_bnds.isel(time=selected).values
        for year, bound in zip(YEARS, bounds):
            assert pd.Timestamp(bound[0]) == pd.Timestamp(year=year, month=10, day=1)
            assert pd.Timestamp(bound[1]) == pd.Timestamp(year=year+1, month=1, day=1)
        domain = source.precip.sel(lon=slice(BOUNDS["west"], BOUNDS["east"]), lat=slice(BOUNDS["south"], BOUNDS["north"]))
        assert domain.sizes == {"time": source.sizes["time"], "lat": 380, "lon": 960}
        lon, lat = np.meshgrid(domain.lon.values, domain.lat.values)
        mask = xr.DataArray(shapely.contains_xy(geometry, lon, lat), dims=("lat", "lon"), coords={"lat":domain.lat,"lon":domain.lon})
        weights = np.cos(np.deg2rad(domain.lat)) * mask
        land_fraction = mask.astype(float).coarsen(lat=20, lon=20, boundary="exact").mean()
        for year, index in zip(YEARS, selected):
            print("READING_CHIRPS", year, flush=True)
            values = domain.isel(time=index).load()
            assert not bool((values < 0).any()), "Unexpected negative valid rainfall"
            valid_weights = weights.where(values.notnull(), 0)
            numerator = (values.fillna(0) * weights).coarsen(lat=20, lon=20, boundary="exact").sum()
            denominator = valid_weights.coarsen(lat=20, lon=20, boundary="exact").sum()
            coverage = denominator / weights.coarsen(lat=20, lon=20, boundary="exact").sum()
            coarse = (numerator / denominator).where((land_fraction > 0) & (coverage >= 0.99))
            records.append(coarse.drop_vars("time", errors="ignore"))
    rain = xr.concat(records, dim=pd.Index(YEARS, name="year"))
    # Choose modelled country cells from training availability only, not 2023 values.
    complete = rain.sel(year=slice(1982,2010)).notnull().all("year")
    rain = rain.where(complete).rename({"year":"T", "lat":"Y", "lon":"X"})
    starts = pd.to_datetime([f"{year}-10-01" for year in YEARS])
    ends = pd.to_datetime([f"{year}-12-31" for year in YEARS])
    midpoints = starts + (ends - starts) / 2
    rain = rain.assign_coords(T=midpoints, Ti=("T", starts), Tf=("T", ends)).sortby("Y", ascending=False)
    rain.name = "precipitation"
    rain.attrs = {"units":"mm", "missing":-999.0, "standard_name":"precipitation_amount",
                  "long_name":"Indonesia land-only OND accumulated rainfall", "cell_methods":"time: sum area: mean"}
    fraction = land_fraction.rename({"lat":"Y","lon":"X"}).sortby("Y", ascending=False)
    fraction.attrs = {"units":"1", "long_name":"Fraction of native CHIRPS grid-cell centres inside Indonesia"}
    spatial_mask = complete.rename({"lat":"Y","lon":"X"}).sortby("Y", ascending=False).astype("int8")
    spatial_mask.attrs = {"long_name":"Indonesia country cells with complete selected-year observations", "flag_values":np.array([0,1],dtype="int8"),"flag_meanings":"excluded included"}
    write(rain.to_dataset(), "observations_chirps3_ond.nc", {
        "source":"Local CHIRPS v3 three-month rolling dekadal accumulation",
        "source_file":str(CHIRPS), "selection":"December 21 timestamp with exact October 1–January 1 bounds",
        "aggregation":"Area-weighted mean over Indonesian native 0.05-degree cells within 1-degree blocks",
        "boundary_source":"Natural Earth 1:10m admin_0_countries ADM0_A3=IDN",
        "coverage_rule":"At least 99 percent of country-cell weight valid in each training year; mask fitted on 1982–2010 only",
        "data_kind":"observed_reference"})
    write(xr.Dataset({"indonesia_fraction":fraction,"analysis_mask":spatial_mask}), "indonesia_analysis_mask.nc")
    print("OBSERVATIONS_READY", dict(rain.sizes), "valid_country_cells",int(spatial_mask.sum()), flush=True)


def prepare_model():
    key = read_dlauth()
    assert key, "IRI authentication is not configured"
    sources = {}
    args = dict(fdate=dt.datetime(2023,9,1), first_year=1982, final_year=2010,
                target="Oct-Dec", predictor_extent=PREDICTOR_BOUNDS,
                lead_low=1.5, lead_high=3.5, filetype="cptv10.tsv")
    for kind in ("hindcasts", "forecasts"):
        url = cptdl.evaluate_url(getattr(cptdl,kind)["CFSv2.PRCP"], **args)
        assert "%5BL%5D//keepgrids/average/" in url and "/92/mul/" in url
        # Request separate monthly mean rates, then use exact calendar-day weights.
        url = url.replace("%5BL%5D//keepgrids/average/", "").replace("/92/mul/", "/")
        target = ROOT / "inputs" / f"cfsv2_{kind}_monthly.tsv"
        if not target.exists():
            print("DOWNLOADING_MONTHLY_MODEL", kind, flush=True)
            with requests.get(url, cookies={"__dlauth_id":key}, timeout=180) as response:
                response.raise_for_status()
                if not response.content.startswith(b"xmlns:cpt"):
                    raise RuntimeError("IRI returned non-CPT content; credential value is not logged")
                target.write_bytes(response.content)
        raw_text = target.read_text()
        initialization_dates = re.findall(r"cpt:S=([^,\r\n]+)", raw_text)
        assert initialization_dates
        initializations = [pd.Timestamp(value.strip()) for value in initialization_dates]
        assert all(value.month == 9 and value.day == 1 and value.hour == 0 for value in initializations)
        # cptio 1.4.0 deduplicates repeated S values, conflicting with monthly T.
        # Preserve the raw file and remove only S from a parsing copy. Restore its
        # verified September initialization when the monthly data are aggregated.
        parsing_copy = target.with_suffix(".parsing.tsv")
        parsing_copy.write_text(re.sub(r",\s*cpt:S=[^,\r\n]+", "", raw_text))
        ds = open_cptdataset(str(parsing_copy))
        values = ds[list(ds.data_vars)[0]].sortby("T")
        print("MONTHLY_MODEL",kind,dict(values.sizes),values.attrs.get("units"), flush=True)
        assert values.attrs["units"] == "mm/day"
        expected_years = list(range(1982,2011)) if kind == "hindcasts" else [2023]
        assert sorted(set(value.year for value in initializations)) == expected_years
        totals = []
        for year in expected_years:
            monthly = values.sel(T=values["T"].dt.year == year)
            assert list(monthly["T"].dt.month.values) == [10,11,12]
            days = (monthly.Tf - monthly.Ti) / np.timedelta64(1,"D") + 1
            np.testing.assert_array_equal(days, [31,30,31])
            total = (monthly * days).sum("T", skipna=False).drop_vars(["Ti","Tf","S"],errors="ignore")
            totals.append(total)
        starts = pd.to_datetime([f"{year}-10-01" for year in expected_years])
        ends = pd.to_datetime([f"{year}-12-31" for year in expected_years])
        rain = xr.concat(totals, dim=pd.Index(starts+(ends-starts)/2,name="T"))
        rain = rain.assign_coords(Ti=("T",starts),Tf=("T",ends),S=("T",pd.to_datetime([f"{year}-09-01" for year in expected_years])))
        rain = rain.transpose("T","Y","X").rename("precipitation")
        rain.attrs = {"units":"mm", "missing":-999.0, "standard_name":"precipitation_amount", "cell_methods":"time: sum", "long_name":"CFSv2 ensemble-mean OND rainfall accumulation"}
        write(rain.to_dataset(),f"cfsv2_{kind}_ond.nc", {"source":"NCEP CFSv2 via IRI NMME", "aggregation":"Monthly mean rainfall rate multiplied by actual days per calendar month, then summed", "initialization_month":"September"})
        sources[kind] = {"url":url,"bytes":target.stat().st_size,"sha256":hashlib.sha256(target.read_bytes()).hexdigest(),"years":expected_years,"shape":dict(rain.sizes)}
        print("MODEL_READY",kind,dict(rain.sizes), "mean_mm",float(rain.mean()), flush=True)
    availability = {"case_id":"indonesia-ond-2023", "forecast_initialization":"2023-09-01", "target_start":"2023-10-01", "target_end":"2023-12-31", "training_years":[1982,2010], "forecast_year":2023,
                    "model":"CFSv2.PRCP", "model_sources":sources,"observations":{"product":"CHIRPS v3.0","available_years":[1981,2025],"local_source":str(CHIRPS),"original_source_size_bytes":CHIRPS.stat().st_size},
                    "country_bounds":BOUNDS,"predictor_bounds":PREDICTOR_BOUNDS,"output_resolution_degrees":1.0,"prepared_at":dt.datetime.now(dt.timezone.utc).isoformat(),
                    "interpretation":"Historical replay using retrospectively available model/observation products, not an as-issued 2023 operational record"}
    (ROOT/"availability.json").write_text(json.dumps(availability,indent=2)+"\n")


if __name__ == "__main__":
    (ROOT/"inputs").mkdir(parents=True,exist_ok=True)
    prepare_model()
    prepare_observations()
