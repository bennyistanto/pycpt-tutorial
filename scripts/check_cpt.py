"""Offline CPT/PyCPT runtime check using a reproducible synthetic seasonal case.

Run this with the project's PyCPT environment. It verifies execution and parsing,
not regional forecast skill or complete CPT/PyCPT feature compatibility.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from cptcore import canonical_correlation_analysis, principal_components_regression


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=["cca", "pcr"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--initialization-coordinates", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7619)
    times = pd.to_datetime([f"{year}-11-15" for year in range(1981, 2013)])
    signal = rng.normal(size=(32, 1, 1))
    pattern = np.array([[1.0, 0.7, 1.2], [0.8, 1.1, 0.6]])[None, :, :]
    x_values = 200 + 35 * signal * pattern + rng.normal(0, 8, (32, 2, 3))
    y_values = 240 + 28 * signal * pattern + rng.normal(0, 10, (32, 2, 3))
    coords = {
        "T": times,
        "Ti": ("T", pd.to_datetime([f"{year}-10-01" for year in range(1981, 2013)])),
        "Tf": ("T", pd.to_datetime([f"{year}-12-31" for year in range(1981, 2013)])),
        "Y": [-7.0, -8.0],
        "X": [111.0, 112.0, 113.0],
    }
    attrs = {"missing": -999.0, "units": "mm"}
    x = xr.DataArray(x_values, coords=coords, dims=("T", "Y", "X"), name="rain", attrs=attrs)
    y = xr.DataArray(y_values, coords=coords, dims=("T", "Y", "X"), name="rain", attrs=attrs)
    if args.initialization_coordinates:
        x = x.assign_coords(S=("T", pd.to_datetime([f"{year}-09-01" for year in range(1981, 2013)])))
    x_train, y_train = x.isel(T=slice(None, -1)), y.isel(T=slice(None, -1))
    forecast_input = x.isel(T=slice(-1, None))
    kwargs = dict(
        F=forecast_input,
        x_eof_modes=(1, 2),
        crossvalidation_window=3,
        synchronous_predictors=True,
        cpt_kwargs={"outputdir": args.output / "cpt-output", "log": args.output / "commands.log"},
    )
    if args.method == "cca":
        result = canonical_correlation_analysis(
            x_train, y_train, y_eof_modes=(1, 2), cca_modes=(1, 1), **kwargs
        )
    else:
        result = principal_components_regression(x_train, y_train, **kwargs)
    hindcasts, forecasts, skill = result[:3]
    print("Returned sizes:", dict(hindcasts.sizes), dict(forecasts.sizes), flush=True)
    assert hindcasts.deterministic.sizes["T"] == 31
    assert np.isfinite(hindcasts.deterministic).any()
    assert forecasts.deterministic.sizes["T"] == 1
    assert np.isfinite(forecasts.deterministic).all()
    np.testing.assert_array_equal(hindcasts.T.dt.year, range(1981, 2012))
    np.testing.assert_array_equal(forecasts.T.dt.year, [2012])
    probabilities = forecasts.probabilistic
    assert np.isfinite(probabilities).all()
    category_dim = next(d for d in probabilities.dims if d not in ("T", "X", "Y"))
    np.testing.assert_allclose(probabilities.sum(category_dim), 100, atol=0.1)
    for name, dataset in (("hindcasts", hindcasts), ("forecasts", forecasts), ("skill", skill)):
        dataset.to_netcdf(args.output / f"{name}.nc")
    summary = {
        "method": args.method,
        "includes_initialization_coordinates": args.initialization_coordinates,
        "diagnostic_adapter": os.environ.get("CPT_DIAGNOSTIC_ADAPTER"),
        "executable": str(Path(os.environ["CPT_BIN_DIR"]) / "CPT.x"),
        "hindcast_samples": 31,
        "forecast_samples": 1,
        "forecast_variables": list(forecasts.data_vars),
        "skill_variables": list(skill.data_vars),
        "probability_sum": "100 percent within 0.1",
        "status": "PASS",
        "scope": "Synthetic offline runtime check only; not full compatibility or scientific validation",
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
