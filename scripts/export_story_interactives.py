"""Export the twelve-season notebook results for the story page's interactive views; never recalculate fits.

Scores go to docs/assets/story/metrics.json. The maps are at 0.05 degree, so their values are
written as small binary files that the page loads one season at a time:

  fields.json            grid, pixel count, field order, province names, colour limits
  pixels.bin             int32, the grid position (row * nx + column, row 0 = north) of every scored pixel
  provinces.bin          uint8, each pixel's province (index into the names in fields.json)
  fields/<SEASON>.bin.gz uint16 whole millimetres: observed, then the seven forecasts, one value per pixel
  fields/<SEASON>-products.bin.gz uint16: the 1991-2020 normal and the two tercile boundaries (whole mm), the CCA
                         and PCR tercile probabilities (tenths of a percent), the observed category (0, 1, 2), and the
                         scales of the flexible forecast's climatology and forecast distributions (tenths of a mm)
"""
from pathlib import Path
import gzip
import hashlib
import json

import numpy as np
import pandas as pd
import xarray as xr
from matplotlib import colormaps
from matplotlib.colors import to_hex

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "docs/assets/story"
VARIANTS = ["raw_cfsv2", "climatology_1983_2010", "climatology_1991_2020", "cca_1983_2010", "cca_1991_2020", "pcr_1983_2010", "pcr_1991_2020"]
SEASONS = "DJF JFM FMA MAM AMJ MJJ JJA JAS ASO SON OND NDJ".split()


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    with xr.open_dataset(p) as ds:
        return ds.load()


def main():
    (DEST / "fields").mkdir(parents=True, exist_ok=True)
    sources = {}

    def load(name):
        p = ROOT / name
        sources[name] = sha(p)
        return read(p)

    fields = load("docs/data/indonesia-seasons-2023.nc")
    scores = load("docs/assets/seasonal-2023/verification-2023.nc")
    context = load("docs/data/verification-context-2021-2024.nc")
    regional = load("docs/assets/seasonal-2023/province-verification-2023.nc")
    pooled = load("docs/data/regions/province-context-pooled.nc")
    regions = json.loads((ROOT / "docs/data/regions/provenance.json").read_text())

    def records(ds, by_region=False, pooled_context=False):
        result = []
        for season in SEASONS:
            for region in (list(ds.region.values) if by_region else [None]):
                selected = ds.sel(season=season, **({"region": region} if by_region else {}))
                for variant in VARIANTS:
                    row = {"season": season, "variant": variant}
                    if by_region:
                        row["region"] = str(region)
                    for metric in ["rmse", "mae", "bias"]:
                        a = selected["pooled_" + metric if pooled_context else metric].sel(forecast_variant=variant)
                        if "evaluation_set" in a.dims:
                            a = a.sel(evaluation_set="all_four_years")
                        row[metric] = float(a)
                    if variant.startswith(("cca", "pcr")):
                        period = variant[4:]
                        for label, reference in [("Climatology", "climatology_" + period), ("Raw", "raw_cfsv2")]:
                            base = selected["pooled_rmse" if pooled_context else "rmse"].sel(forecast_variant=reference)
                            if "evaluation_set" in base.dims:
                                base = base.sel(evaluation_set="all_four_years")
                            row["gain" + label] = 100 * (1 - row["rmse"] / float(base))
                    result.append(row)
        return result

    names = regions["province_names"]
    support = [{"name": name, "isProvince": True, "cells": int(regions["pixels_by_province"][name]),
                "weightPercent": 100 * float(regions["weight_share_by_province"][name])} for name in names]
    calendar = [{"season": s, "start": pd.Timestamp(fields.target_start.sel(season=s).item()).strftime("%Y-%m-%d"),
                 "end": pd.Timestamp(fields.target_end.sel(season=s).item()).strftime("%Y-%m-%d"),
                 "issue": pd.Timestamp(fields.initialization.sel(season=s).item()).strftime("%Y-%m-%d"),
                 "sourceYear": int(fields.source_season_year.sel(season=s))} for s in SEASONS]
    data = {"seasons": SEASONS, "variants": VARIANTS, "national": records(scores), "context": records(context, pooled_context=True),
            "regional": records(regional, by_region=True), "regionalContext": records(pooled, by_region=True),
            "support": support, "calendar": calendar, "pixels": int(fields.evaluation_mask.sum()),
            "palettes": {name: [to_hex(colormaps[name](i / 256)) for i in range(257)] for name in ["YlGnBu", "BrBG"]},
            "note": "Unrounded verified scores. Browser presentation only; province counts and weights are not independent validation samples."}
    (DEST / "metrics.json").write_text(json.dumps(data, separators=(",", ":"), allow_nan=False) + "\n")

    mask = fields.evaluation_mask.transpose("Y", "X").values.astype(bool)
    assert float(fields.Y[0]) > float(fields.Y[-1]), "rows run north to south"
    flat = np.flatnonzero(mask.ravel())
    (DEST / "pixels.bin").write_bytes(flat.astype("<i4").tobytes())
    (DEST / "provinces.bin").write_bytes(fields.province_index.transpose("Y", "X").values.ravel()[flat].astype("u1").tobytes())
    order = ["observed"] + VARIANTS
    limits = {}
    for old in (DEST / "fields").glob("*"):
        old.unlink()
    for season in SEASONS:
        ds = fields.sel(season=season)
        values = {"observed": ds.observed_rainfall.transpose("Y", "X").values.ravel()[flat]}
        for variant in VARIANTS:
            values[variant] = ds.forecast_rainfall.sel(forecast_variant=variant).transpose("Y", "X").values.ravel()[flat]
        assert all(np.isfinite(v).all() and v.min() >= 0 and v.max() < 65535 for v in values.values()), season
        blob = b"".join(np.round(values[k]).astype("<u2").tobytes() for k in order)
        (DEST / "fields" / f"{season}.bin.gz").write_bytes(gzip.compress(blob, 9, mtime=0))
        limits[season] = {period: float(np.quantile(np.concatenate([values[k] for k in ["observed", "raw_cfsv2", "climatology_" + period, "cca_" + period, "pcr_" + period]]), .99))
                          for period in ["1983_2010", "1991_2020"]}
    # Forecast products: what the anomaly, percent-of-normal and probability views need
    products = load("docs/data/indonesia-seasons-2023-products.nc")
    assert bool((products.evaluation_mask == fields.evaluation_mask).all())
    product_order = ["normal", "tercile_lower", "tercile_upper"] + [f"{m}_{c}" for m in ("cca", "pcr") for c in ("below", "near", "above")] + ["observed_category", "climatology_scale", "cca_scale", "pcr_scale"]
    anomaly_limits = {}
    for season in SEASONS:
        ds = products.sel(season=season)
        take = lambda a: a.transpose("Y", "X").values.ravel()[flat]
        values = {name: np.round(take(ds[name])) for name in ("normal", "tercile_lower", "tercile_upper")}
        for m in ("cca", "pcr"):
            for c in ("below", "near", "above"):
                values[f"{m}_{c}"] = np.round(10 * take(ds.probability.sel({"method": m, "category": c})))
        values["observed_category"] = take(ds.observed_category)
        # ingredients of the flexible forecast, in tenths of a millimetre
        values["climatology_scale"] = np.round(10 * take(ds.climatology_scale))
        for m in ("cca", "pcr"):
            values[f"{m}_scale"] = np.round(10 * take(ds.forecast_scale.sel({"method": m})))
        assert all(np.isfinite(v).all() and v.min() >= 0 and v.max() < 65535 for v in values.values()), season
        (DEST / "fields" / f"{season}-products.bin.gz").write_bytes(gzip.compress(b"".join(values[k].astype("<u2").tobytes() for k in product_order), 9, mtime=0))
        normal = take(ds.normal)
        rain = fields.sel(season=season)
        anomalies = np.concatenate([take(rain.observed_rainfall) - normal] + [take(rain.forecast_rainfall.sel(forecast_variant=f"{m}_1991_2020")) - normal for m in ("cca", "pcr")])
        anomaly_limits[season] = float(np.quantile(np.abs(anomalies), .99))
    step = float(abs(fields.X[1] - fields.X[0]))
    manifest = {"grid": {"west": round(float(fields.X.min()) - step / 2, 3), "north": round(float(fields.Y.max()) + step / 2, 3), "step": round(step, 3),
                         "nx": int(fields.sizes["X"]), "ny": int(fields.sizes["Y"]), "pixels": int(len(flat))},
                "order": order, "provinces": names, "rainLimits": limits,
                "productOrder": product_order, "anomalyLimits": anomaly_limits,
                "flexible": {"degreesOfFreedom": int(products.forecast_scale.attrs["degrees_of_freedom"]), "scaleUnit": 0.1,
                             "note": "PyCPT construct_flex_fcst: Student's t centred on the forecast with scale sqrt((N-2)/N x prediction error variance) and N degrees of freedom; climatology normal with the training mean and sqrt((N-2)/N) x the training standard deviation"},
                "note": "Values in whole millimetres at 0.05 degree; display colours saturate, hover values do not."}
    (DEST / "fields.json").write_text(json.dumps(manifest, separators=(",", ":"), allow_nan=False) + "\n")
    outputs = {str(p.relative_to(DEST)).replace("\\", "/"): {"sha256": sha(p), "bytes": p.stat().st_size}
               for p in [DEST / "metrics.json", DEST / "fields.json", DEST / "pixels.bin", DEST / "provinces.bin", *sorted((DEST / "fields").glob("*.bin.gz"))]}
    record = {"sources": sources, "outputs": outputs, "map_pixels": int(len(flat)),
              "numeric_rounding": "Scores unrounded in JSON; map values rounded to whole millimetres.",
              "method": "Serialize existing metrics and fields; gain percentages use stored RMSE; no new fits or weights."}
    (DEST / "provenance.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"pixels": int(len(flat)), "files": len(outputs), "MB": round(sum(o["bytes"] for o in outputs.values()) / 1e6, 1)}, indent=2))


if __name__ == "__main__":
    main()
