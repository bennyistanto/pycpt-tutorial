"""Partition frozen country weights with unsimplified provinces; no model fits."""
from pathlib import Path
import hashlib
import json
import sys

import numpy as np
import shapefile
import shapely
from shapely.geometry import shape
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pycpt_tutorial.export import save_netcdf
from pycpt_tutorial.regions import score_regions, pool_years

CASE = ROOT / "research/cases/indonesia-all-seasons-2021-2024-025deg"
DEST = ROOT / "docs/data/regions"
AUDIT = ROOT / "research/audits/regional-2023"
SOURCE = Path("/mnt/e/temp/chirps/rolling_dekad/wld_cli_chirps3_month3_bydekad_1981_2025.nc")
BOUNDARY = Path("/mnt/f/temp/hybrid-bias-correction/data/subset/bnd/idn_bnd_adm1")
COUNTRY = Path.home() / "CPT/cases/indonesia-ond-2023/inputs/indonesia_boundary.geojson"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024*1024), b""): h.update(b)
    return h.hexdigest()


def read(path):
    with xr.open_dataset(path) as ds: return ds.load()


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    AUDIT.mkdir(parents=True, exist_ok=True)
    baseline = {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT / "docs/data").glob("*.nc"))}
    (AUDIT / "baseline.json").write_text(json.dumps(baseline, indent=2)+"\n")
    manifest = json.loads((CASE / "case_manifest.json").read_text())
    sources = {}
    def frozen(name):
        p = CASE / "outputs" / name
        assert sha(p) == manifest["outputs"][name]["sha256"], name
        sources[str(p.relative_to(ROOT))] = sha(p)
        return read(p)
    footprint = frozen("evaluation_footprint.nc")
    country = shape(json.loads(COUNTRY.read_text()))
    shapely.prepare(country)
    with xr.open_dataset(SOURCE) as source:
        native = source.precip.sel(lon=slice(94,142), lat=slice(-12,7))
        lon, lat = np.meshgrid(native.lon.values, native.lat.values)
    assert lon.shape == (380,960)
    inside = shapely.contains_xy(country, lon, lat)
    w = inside * np.cos(np.deg2rad(lat))
    block = lambda a: a.reshape(76,5,192,5).sum(axis=(1,3))[::-1]
    np.testing.assert_allclose(block(w), footprint.country_land_weight, atol=1e-12, rtol=0)
    active = np.repeat(np.repeat(footprint.evaluation_mask.values[::-1].astype(bool),5,0),5,1) & inside
    row, col = np.nonzero(active)
    px, py = lon[active], lat[active]
    hits = np.zeros(len(px), dtype=np.uint8)
    labels = np.full(len(px), -1, dtype=np.int16)
    names = []
    boundary_prov = json.loads((ROOT / "docs/data/boundaries/provenance.json").read_text())
    for ext in (".shp", ".shx", ".dbf", ".prj"):
        path = BOUNDARY.with_suffix(ext)
        assert sha(path) == boundary_prov["sources"]["idn_bnd_adm1"]["files"][path.name]
        sources[str(path)] = sha(path)
    reader = shapefile.Reader(str(BOUNDARY), encoding="utf-8")
    for i, sr in enumerate(reader.iterShapeRecords()):
        name = sr.record.as_dict()["a1name"]
        geom = shape(sr.shape.__geo_interface__)
        assert geom.is_valid, name  # analysis uses original geometry, no simplification/repair
        shapely.prepare(geom)
        match = shapely.contains_xy(geom, px, py)
        hits += match
        labels[match] = i
        names.append(name)
        print(f"Province {i+1}: {name}, {int(match.sum())} native points", flush=True)
    reader.close()
    assert len(names) == len(set(names)) == 38
    labels[hits == 0] = 38
    labels[hits > 1] = 39
    all_names = names + ["Unassigned country pixels", "Overlapping province pixels"]
    fine_weight = np.cos(np.deg2rad(py))
    coarse_row, coarse_col = 75-row//5, col//5
    weights = np.zeros((40,76,192))
    np.add.at(weights, (labels,coarse_row,coarse_col), fine_weight)
    np.testing.assert_allclose(weights.sum(0), footprint.evaluation_weight, atol=1e-12, rtol=0)
    keep = weights.sum((1,2)) > 0
    assert keep[:38].all(), "A province has no support; do not silently score it as zero"
    index = np.flatnonzero(keep)
    region_weight = xr.DataArray(weights[index], dims=("region","Y","X"),
                                coords={"region": np.array(all_names)[index], "Y":footprint.Y, "X":footprint.X}, name="region_weight")
    region_weight.attrs = {"units":"relative native-pixel area", "definition":"Sum cosine(latitude) of original country-native pixels assigned to each province in each existing0.25degree cell"}
    data = xr.Dataset({"region_weight":region_weight,
                       "region_mass_fraction":region_weight.sum(("Y","X"))/region_weight.sum(),
                       "contributing_cells":(region_weight>0).sum(("Y","X")),
                       "largest_cell_weight_fraction":region_weight.max(("Y","X"))/region_weight.sum(("Y","X"))},
                      coords={"is_province":("region", index<38)})
    save_netcdf(data, DEST / "province-weights.nc", overwrite=True, metadata={"method":"Native0.05degree centre assignment to unsimplified supplied province polygons; original country mask authoritative",
                 "limitation":"Partition of existing0.25degree cell errors, not a new province rainfall product; neighbouring provinces may share a coarse cell",
                 "boundary_vintage":"Supplied38-feature file; metadata describes2022; not a current-boundary certification"})
    native_audit = xr.Dataset({"longitude":("point",px), "latitude":("point",py), "original_province_index":("point",labels),
                               "membership_count":("point",hits), "coarse_row":("point",coarse_row.astype("int16")),
                               "coarse_col":("point",coarse_col.astype("int16")), "native_weight":("point",fine_weight)})
    save_netcdf(native_audit, DEST / "native-membership.nc", overwrite=True)
    annuals = []
    for season in "DJF JFM FMA MAM AMJ MJJ JJA JAS ASO SON OND NDJ".split():
        ds = frozen(f"{season}_forecast_comparison.nc")
        score = score_regions(ds.forecast_rainfall, ds.observed_rainfall, region_weight)
        score = score.swap_dims({"T":"season_year"}).drop_vars([c for c in score.coords if c not in ("season_year","forecast_variant","region")])
        annuals.append(score.expand_dims(season=[season]))
    annual = xr.concat(annuals, dim="season", join="exact")
    pooled = pool_years(annual)
    save_netcdf(annual, DEST / "province-context-annual.nc", overwrite=True,
                metadata={"year_convention":"Original ending-year2021–2024, includingNDJ; not four complete midpoint-year collections"})
    save_netcdf(pooled, DEST / "province-context-pooled.nc", overwrite=True,
                metadata={"pooling":"Equal years: square root of mean annual regionalMSE; not meanRMSE"})
    national = frozen("verification_scores.nc")
    share = data.region_mass_fraction
    for key in ("rmse","mae","bias"):
        recombined = np.sqrt((annual.mse*share).sum("region")) if key=="rmse" else (annual[key]*share).sum("region")
        np.testing.assert_allclose(recombined.transpose("season","season_year","forecast_variant"), national[key].transpose("season","season_year","forecast_variant"), atol=1e-8, rtol=0)
    sources[str(COUNTRY)] = sha(COUNTRY)
    outputs = {p.name:{"sha256":sha(p),"bytes":p.stat().st_size} for p in sorted(DEST.glob("*.nc"))}
    total = fine_weight.sum()
    summary = {"source_files":sources, "outputs":outputs, "province_names":names,
               "region_order_original_indices":index.tolist(), "native_points":len(px),
               "unassigned_points":int((hits==0).sum()), "overlap_points":int((hits>1).sum()),
               "unassigned_weight_fraction":float(fine_weight[hits==0].sum()/total),
               "overlap_weight_fraction":float(fine_weight[hits>1].sum()/total),
               "country_weight_reconstruction":"PASS <=1e-12", "national_score_recombination":"PASS <=1e-8mm",
               "native_coordinate_source":str(SOURCE), "boundary_display_files_used_for_analysis":False,
               "method":"Original native country-pixel centre assignment to unsimplified province polygons; explicit unmatched/overlap categories; coarse errors retained"}
    (DEST / "provenance.json").write_text(json.dumps(summary,indent=2)+"\n")
    (AUDIT / "preparation.json").write_text(json.dumps(summary,indent=2)+"\n")
    assert all(sha(ROOT/p)==h for p,h in baseline.items())
    print(json.dumps({k:v for k,v in summary.items() if k not in ("source_files","outputs","province_names")},indent=2))


if __name__ == "__main__": main()
