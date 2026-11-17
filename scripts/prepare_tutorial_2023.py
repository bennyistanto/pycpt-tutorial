"""Package the 0.05 degree twelve-season results for the offline teaching notebook; never refit.

Reads the finished research run (research/scripts/run_indonesia_all_seasons_005.py, working folder
~/CPT/cases/indonesia-all-seasons-2021-2024-005deg) and writes the teaching copies to docs/data:

  indonesia-seasons-2023.nc            forecasts and observations for the twelve windows centred on 2023,
                                       the shared pixel mask and weights, and each pixel's province
  verification-context-2021-2024.nc    national scores for the four ending years
  regions/province-context-annual.nc   province scores for every ending year, season and forecast
  regions/province-context-pooled.nc   the same, pooled over the four years
  ond-*.nc                             the OND 1991-2020 fitting inputs, for the optional rerun
  provenance.json, regions/provenance.json
"""
from pathlib import Path
import hashlib
import json
import sys

import numpy as np
import pandas as pd
import xarray as xr

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from pycpt_tutorial.export import save_netcdf
from pycpt_tutorial.regions import score_pixels_by_region
from pycpt_tutorial.seasons import SEASONS, season_window

CASE = Path.home() / "CPT/cases/indonesia-all-seasons-2021-2024-005deg"
SOURCE_CASE = Path.home() / "CPT/cases/indonesia-all-seasons-2021-2024-025deg"
DEST = REPO / "docs/data"
ENCODING = {"zlib": True, "complevel": 5, "dtype": "float32"}


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    with xr.open_dataset(path) as ds:
        return ds.load()


def write(ds, path, **metadata):
    ds = ds.copy()
    ds.attrs = {k: str(v) for k, v in metadata.items()}
    encoding = {}
    for name in ds.data_vars:
        kind = ds[name].dtype.kind
        encoding[name] = ENCODING if kind == "f" and name in ("forecast_rainfall", "observed_rainfall", "precipitation", "evaluation_weight") else {"zlib": True, "complevel": 5}
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(path, encoding=encoding)


def main():
    manifest = json.loads((CASE / "case_manifest.json").read_text())
    sources = {}

    def verified(name):
        path = CASE / "outputs" / name
        assert sha(path) == manifest["outputs"][name]["sha256"], name
        sources[f"{CASE.name}/outputs/{name}"] = sha(path)
        return read(path)

    footprint = verified("evaluation_footprint.nc")
    score = verified("verification_scores.nc")
    mask = footprint.evaluation_mask.astype(bool)
    pixels = int(mask.sum())
    province_names = [str(v) for v in footprint.province.values]
    labels = footprint.province_index.where(mask, -1).astype("int16")
    assert int((labels.values[mask.values] < 0).sum()) == 0, "every scored pixel touches a province"

    fields, annual = [], []
    starts, ends, issues, source_years, midpoints = [], [], [], [], []
    for season in SEASONS:
        ending_year = 2024 if season == "NDJ" else 2023
        ds = verified(f"{season}_forecast_comparison.nc")
        chosen = ds.sel(T=ds.season_year == ending_year).squeeze("T", drop=False)
        window = season_window(season, ending_year)
        assert pd.Timestamp(chosen.Ti.item()) == window.start and pd.Timestamp(chosen.Tf.item()) == window.end
        assert pd.Timestamp(chosen.S.item()) == window.initialization and pd.Timestamp(chosen["T"].item()).year == 2023
        keep = chosen[["forecast_rainfall", "observed_rainfall"]]
        fields.append(keep.drop_vars([c for c in keep.coords if c not in ("X", "Y", "forecast_variant")]).expand_dims(season=[season]))
        starts.append(window.start); ends.append(window.end); issues.append(window.initialization)
        source_years.append(ending_year); midpoints.append(pd.Timestamp(chosen["T"].item()))
        # province scores for all four ending years, from the same pixel errors
        error = (ds.forecast_rainfall - ds.observed_rainfall).transpose("forecast_variant", "T", "Y", "X")
        regional = score_pixels_by_region(error.values[:, :, mask.values], labels.values[mask.values], footprint.evaluation_weight.values[mask.values], len(province_names))
        annual.append(xr.Dataset({name: (("forecast_variant", "season_year", "region"), values) for name, values in regional.items()},
                                 coords={"forecast_variant": ds.forecast_variant.values, "season_year": ds.season_year.values, "region": province_names}).expand_dims(season=[season]))
        print("packaged", season, flush=True)

    bundle = xr.concat(fields, dim="season", join="exact", combine_attrs="drop_conflicts")
    bundle = bundle.assign_coords(target_start=("season", pd.to_datetime(starts)), target_end=("season", pd.to_datetime(ends)),
                                  initialization=("season", pd.to_datetime(issues)), target_midpoint=("season", pd.to_datetime(midpoints)),
                                  source_season_year=("season", source_years))
    bundle["evaluation_mask"] = footprint.evaluation_mask
    bundle["evaluation_weight"] = footprint.evaluation_weight
    bundle["province_index"] = labels
    bundle = bundle.assign_coords(province=province_names)
    assert int(bundle.forecast_rainfall.count()) == 12 * 7 * pixels and int(bundle.observed_rainfall.count()) == 12 * pixels
    metadata = {"title": "Indonesia rainfall forecasts: twelve seasons centred on 2023, native 0.05 degree",
                "source_case": CASE.name, "main_training_period": "1991-2020", "sensitivity_training_period": "1983-2010",
                "calendar_note": "NDJ uses the source ending year 2024; its target is November 2023 to January 2024",
                "units_note": "Seasonal rainfall totals in mm at every 0.05 degree pixel that touches Indonesia; the raw predictor is supplied at 1 degree",
                "pixel_rule": "Any overlap with the supplied 38-province boundary (unsimplified); province_index is the province covering most of the pixel",
                "validation_note": "Retrospective current-vintage holdouts; overlapping seasons are not independent years; no probabilistic skill claim"}
    for old in ("province-weights.nc", "native-membership.nc"):
        (DEST / "regions" / old).unlink(missing_ok=True)
    write(bundle, DEST / "indonesia-seasons-2023.nc", **metadata)
    write(score, DEST / "verification-context-2021-2024.nc", **{**metadata, "calendar_note": "Ending-year 2021-2024 context; not four complete midpoint-year collections"})

    annual = xr.concat(annual, dim="season", join="exact")
    for name in annual:
        annual[name].attrs["units"] = "mm2" if name == "mse" else "mm"
    pooled = annual[["mse", "mae", "bias"]].mean("season_year", keep_attrs=True)
    pooled["rmse"] = np.sqrt(pooled.mse)
    pooled.rmse.attrs["units"] = "mm"
    share = xr.DataArray(np.bincount(labels.values[mask.values], weights=footprint.evaluation_weight.values[mask.values], minlength=len(province_names)),
                         dims="region", coords={"region": province_names})
    share = share / share.sum()
    for key in ("rmse", "mae", "bias"):          # provinces recombine to the national scores
        combined = np.sqrt((annual.mse * share).sum("region")) if key == "rmse" else (annual[key] * share).sum("region")
        np.testing.assert_allclose(combined.transpose("season", "forecast_variant", "season_year"), score[key].transpose("season", "forecast_variant", "season_year"), atol=1e-6, rtol=1e-9)
    write(annual, DEST / "regions/province-context-annual.nc", year_convention="Ending-year 2021-2024, including NDJ; not four complete midpoint-year collections")
    write(pooled, DEST / "regions/province-context-pooled.nc", pooling="Equal years: square root of the mean annual province MSE, not the mean RMSE")

    # The OND 1991-2020 fitting inputs, for the optional rerun in the notebook
    observed = read(CASE / "OND" / "observations.nc")
    years = list(range(1991, 2021))
    train_mask = observed.analysis_mask.sel(training_period="1991_2020", drop=True).astype(bool)
    y = observed.precipitation.sel(T=observed.season_year.isin(years)).where(train_mask).drop_vars("season_year")
    y.attrs = {"units": "mm", "missing": -999.0}
    model = read(SOURCE_CASE / "OND" / "predictors.nc").precipitation
    x = model.sel(T=model.season_year.isin(years)).drop_vars("season_year")
    f = model.sel(T=model.season_year == 2023).drop_vars("season_year")
    for a in (x, f):
        a.attrs = {"units": "mm", "missing": -999.0}
    for name, array in (("ond-training-predictor", x), ("ond-training-observations", y), ("ond-forecast-predictor", f)):
        save_netcdf(array.to_dataset(name="precipitation"), DEST / f"{name}.nc", overwrite=True,
                    metadata={"purpose": "OND 1991-2020 fitting inputs of the 0.05 degree run, packaged for the optional rerun"})
    sources[f"{SOURCE_CASE.name}/OND/predictors.nc"] = sha(SOURCE_CASE / "OND" / "predictors.nc")

    outputs = {p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in sorted(DEST.glob("*.nc"))}
    record = {"case": CASE.name, "source_files": sources, "outputs": outputs, "calendar_selection": dict(zip(SEASONS, source_years)),
              "main_selection_midpoint_year": 2023, "retained_pixels": pixels, "grid": "native 0.05 degree, pixels touching Indonesia",
              "note": "Derived teaching copy. Only deterministic comparisons are bundled; native probabilities remain in the research run."}
    (DEST / "provenance.json").write_text(json.dumps(record, indent=2) + "\n")
    region_outputs = {p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in sorted((DEST / "regions").glob("*.nc"))}
    counts = np.bincount(labels.values[mask.values], minlength=len(province_names))
    region_record = {"outputs": region_outputs, "province_names": province_names, "pixels": pixels,
                     "pixels_by_province": dict(zip(province_names, counts.tolist())), "weight_share_by_province": dict(zip(province_names, share.values.tolist())),
                     "method": "Each 0.05 degree pixel belongs to the province covering most of it (unsimplified supplied boundary); every scored pixel touches a province",
                     "national_score_recombination": "PASS", "boundary_vintage": "Supplied 38-feature file; metadata describes 2022; not a current-boundary certification"}
    (DEST / "regions/provenance.json").write_text(json.dumps(region_record, indent=2) + "\n")
    print(json.dumps({"files": len(outputs), "MB": round(sum(x["bytes"] for x in outputs.values()) / 1e6, 1), "pixels": pixels,
                      "smallest_province": min(zip(counts.tolist(), province_names))}, indent=2))


if __name__ == "__main__":
    main()
