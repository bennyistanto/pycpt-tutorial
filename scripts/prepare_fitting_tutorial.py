"""Package the OND/JJA fitting inputs and controls at 0.05 degree for the Fit & diagnose notebook; never refit.

Inputs and controls come from the finished twelve-season run at native resolution
(research/scripts/run_indonesia_all_seasons_005.py, working folder
~/CPT/cases/indonesia-all-seasons-2021-2024-005deg):

  <SEASON>-X.nc, -Y.nc, -F.nc      training predictor, training observations, 2023 predictor
  comparison-context.nc            the 2023 observation and the raw and climatology forecasts
  controls/<SEASON>-<method>-*     that run's 2023 forecast, cross-validated hindcasts, native skill and
                                   EOF/CCA diagnostics, which the notebook's own fits must reproduce
  predictor-boundaries.geojson     country outlines over the predictor box, for display only
"""
from pathlib import Path
import hashlib
import json
import sys

import numpy as np
import shapefile
import xarray as xr
from shapely import make_valid
from shapely.geometry import box, mapping, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pycpt_tutorial import fitting as fit

CASE = Path.home() / "CPT/cases/indonesia-all-seasons-2021-2024-005deg"
SOURCE_CASE = Path.home() / "CPT/cases/indonesia-all-seasons-2021-2024-025deg"
DATA = ROOT / "docs/data/fitting-2023"
AUDIT = ROOT / "temp/audits/fitting-tutorial-2023"
FLOAT = {"zlib": True, "complevel": 5, "dtype": "float32"}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read(p):
    with xr.open_dataset(p) as ds:
        return ds.load()


def main():
    AUDIT.mkdir(parents=True, exist_ok=True)
    controls = DATA / "controls"
    controls.mkdir(parents=True, exist_ok=True)
    for old in list(DATA.glob("*.nc")) + list(controls.glob("*.nc")):
        old.unlink()
    output, sources = {}, {}

    def save(ds, name, single=True):
        path = DATA / name
        encoding = {v: (FLOAT if single and ds[v].dtype.kind == "f" else {"zlib": True, "complevel": 5}) for v in ds.data_vars}
        ds.to_netcdf(path, encoding=encoding)
        output[name] = {"sha256": sha(path), "bytes": path.stat().st_size}

    context = read(ROOT / "docs/data/indonesia-seasons-2023.nc").sel(season=["OND", "JJA"])
    context = context.sel(forecast_variant=["raw_cfsv2", "climatology_1991_2020", "cca_1991_2020", "pcr_1991_2020"])
    save(context, "comparison-context.nc")
    pixels = int(context.evaluation_mask.sum())
    years = np.arange(1991, 2021)
    for season in ["OND", "JJA"]:
        observed = read(CASE / season / "observations.nc")
        model = read(SOURCE_CASE / season / "predictors.nc").precipitation
        sources[f"{SOURCE_CASE.name}/{season}/predictors.nc"] = sha(SOURCE_CASE / season / "predictors.nc")
        mask = observed.analysis_mask.sel(training_period="1991_2020", drop=True).astype(bool)
        np.testing.assert_array_equal(mask, context.evaluation_mask.astype(bool))
        X = model.sel(T=model.season_year.isin(years)).drop_vars("season_year")
        F = model.sel(T=model.season_year == 2023).drop_vars("season_year")
        Y = observed.precipitation.sel(T=observed.season_year.isin(years)).where(mask).drop_vars("season_year")
        assert X.sizes["T"] == Y.sizes["T"] == 30 and F.sizes["T"] == 1 and int(mask.sum()) == pixels
        np.testing.assert_array_equal(X["T"], Y["T"])
        for a in (X, Y, F):
            a.attrs = {"units": "mm", "missing": -999.0}
        # X and F stay in double precision (they are the model's values); Y is CHIRPS in single precision
        save(X.to_dataset(name="precipitation"), f"{season}-X.nc", single=False)
        save(F.to_dataset(name="precipitation"), f"{season}-F.nc", single=False)
        save(Y.astype("float32").to_dataset(name="precipitation"), f"{season}-Y.nc")
        for method in ["cca", "pcr"]:
            key = f"{season}_{method}_1991_2020"
            fitted = read(CASE / season / f"{method}_1991_2020.nc")
            sources[f"{CASE.name}/{season}/{method}_1991_2020.nc"] = sha(CASE / season / f"{method}_1991_2020.nc")
            chosen = fitted.sel(T=fitted["T"].dt.year == 2023)
            assert chosen.sizes["T"] == 1
            save(xr.Dataset({"deterministic": chosen.forecast, "probabilistic": chosen.forecast_probability,
                             "prediction_error_variance": chosen.forecast_pev}), f"controls/{season}-{method}-forecasts.nc", single=False)
            save(xr.Dataset({"deterministic": fitted.cv_hindcast.rename({"Th": "T"})}), f"controls/{season}-{method}-hindcasts.nc")
            save(xr.Dataset({name[6:]: fitted[name] for name in fitted.data_vars if name.startswith("skill_")}), f"controls/{season}-{method}-native_skill.nc", single=False)
            # EOF and CCA diagnostics of that run, cleaned exactly as the notebook cleans its own fits
            folder = Path(fitted.attrs["cpt_folder"])
            for side, prefix in [("predictor", "x")] + ([("predictand", "y")] if method == "cca" else []):
                raw = xr.Dataset({name: fitted[name] for name in fitted.data_vars if name.startswith(prefix + "_") and name != f"{prefix}_explained_variance"})
                raw = raw.rename({"Th": "T", **({"Yx": "Y", "Xx": "X"} if side == "predictor" else {})})
                diagnostics = fit.clean_diagnostics(raw, folder, side)
                save(diagnostics, f"controls/{season}-{method}-{side}-diagnostics.nc", single=False)
            print("packaged", key, flush=True)

    # Country outlines over the whole predictor box, for display only
    base = Path("/mnt/f/temp/hybrid-bias-correction/data/subset/bnd/wld_bnd_adm0")
    features, clip = [], box(85, -20, 155, 20)
    with shapefile.Reader(str(base), encoding="utf-8") as reader:
        for row in reader.iterShapeRecords():
            geom = shape(row.shape.__geo_interface__)
            if not geom.is_valid:
                geom = make_valid(geom)
            if not geom.intersects(clip):
                continue
            geom = geom.intersection(clip).simplify(.025, preserve_topology=True)
            if not geom.is_empty:
                features.append({"type": "Feature", "properties": {}, "geometry": mapping(geom)})
    path = DATA / "predictor-boundaries.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")) + "\n")
    output[path.name] = {"sha256": sha(path), "bytes": path.stat().st_size}
    record = {"case": "fit-diagnose-2023", "training_period": "1991-2020", "seasons": ["OND", "JJA"], "forecast_year": 2023, "pixels": pixels,
              "grid": "native 0.05 degree; every pixel that touches the supplied 38-province boundary",
              "data_note": "Prepared local seasonal fields from the audited archive; no source download.",
              "boundary_note": "Predictor-domain country outlines clipped and simplified from the supplied world shapefile, for display only.",
              "outputs": output, "source_hashes": sources,
              "attribution": "CHIRPS v3.0, Climate Hazards Center/UCSB (https://doi.org/10.15780/G2JQ0P); CFSv2, NCEP via IRI Data Library. Boundaries supplied by Benny Istanto; Indonesia boundaries credit BIG. See ../provenance.json and ../boundaries/provenance.json.",
              "controls": "Forecast, hindcast, skill and diagnostics from the 0.05 degree twelve-season run (four forecast years per fit); the notebook refits with one forecast year.",
              "method_note": "Fixed CCA 3X/3Y/2CCA; PCR 3X; cyclic CV5; no tuning or empirical probability reliability claim."}
    (DATA / "provenance.json").write_text(json.dumps(record, indent=2) + "\n")
    (AUDIT / "preparation.json").write_text(json.dumps({"files": len(output), "pixels": pixels, "provenance_sha256": sha(DATA / "provenance.json")}, indent=2) + "\n")
    print(json.dumps({"packaged_files": len(output), "pixels": pixels, "MB": round(sum(o["bytes"] for o in output.values()) / 1e6, 1)}, indent=2))


if __name__ == "__main__":
    main()
