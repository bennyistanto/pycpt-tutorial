"""Run the weekly lead-time CPT fits in parallel, one process per (lead, method).

Each job reads its prepared inputs (X, Y and F anomalies, one NetCDF each, written by the notebook),
fits CCA or PCR through cptcore (the layer PyCPT's evaluate_models calls), and saves only what
the case uses: the forecast (deterministic and tercile probabilities) and the skill maps. At
0.05 degree the full cross-validated hindcasts are several GB per fit, so they stay in CPT's
own output folder and are not passed between processes.

A result is reused only when it was made from identical input values and the same settings
(SHA-256 of both is stored in the result file).

Each fit runs as a separate Python process (`python weekly_fits.py job.json`), so the caller can
be a notebook kernel or a script without multiprocessing start-method issues.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _digest(inputs: dict, settings: dict) -> str:
    # Hash of the input values and coordinates (not the file bytes, which can differ between writes)
    import xarray as xr
    h = hashlib.sha256()
    for key in ("X", "Y", "F"):
        with xr.open_dataarray(inputs[key]) as a:
            for part in (a.values, a["T"].values, a["Y"].values, a["X"].values):
                h.update(part.tobytes())
    h.update(json.dumps(settings, sort_keys=True, default=str).encode())
    return h.hexdigest()


def fit_one(job: dict) -> dict:
    import xarray as xr
    from cptcore import canonical_correlation_analysis, principal_components_regression

    inputs, folder, method, settings = job["inputs"], Path(job["folder"]), job["method"], job["settings"]
    result_file = folder / "result.nc"
    digest = _digest(inputs, dict(settings, method=method))
    if result_file.exists():
        with xr.open_dataset(result_file) as old:
            if old.attrs.get("inputs_sha256") == digest:
                return dict(job, path=str(result_file), seconds=float(old.attrs["fit_seconds"]), reused=True)
    cpt_dir = folder / "cpt"
    shutil.rmtree(cpt_dir, ignore_errors=True)
    cpt_dir.mkdir(parents=True)
    X, Y, F = (xr.open_dataarray(inputs[k]).load() for k in ("X", "Y", "F"))
    for a in (X, Y, F):
        a.name = "anomaly"
        a.attrs = {"units": "mm", "missing": -999.0}
    function = canonical_correlation_analysis if method == "CCA" else principal_components_regression
    start = time.monotonic()
    out = function(X, Y, F=F, **settings, cpt_kwargs={"outputdir": cpt_dir})
    seconds = time.monotonic() - start
    hindcast, forecast, skill = out[0], out[1], out[2]
    # Check: CPT's correlation map against one recomputed from its own cross-validated hindcasts
    import numpy as np
    h = hindcast.deterministic.transpose("T", "Y", "X").values.astype("float64")
    h[h <= -999] = np.nan
    y = Y.transpose("T", "Y", "X").values.astype("float64")
    ha, ya = h - np.nanmean(h, axis=0), y - np.nanmean(y, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        recomputed = (ha * ya).sum(0) / np.sqrt((ha * ha).sum(0) * (ya * ya).sum(0))
    cpt_r = skill.pearson.transpose("Y", "X").values.astype("float64")
    cpt_r[cpt_r <= -999] = np.nan
    gap = float(np.nanmax(np.abs(cpt_r - recomputed)))
    below_zero = float(np.nansum(h < 0) / np.isfinite(h).sum() * 100)
    keep = xr.Dataset({"deterministic": forecast.deterministic, "probabilistic": forecast.probabilistic})
    keep = keep.drop_vars([c for c in keep.coords if c not in ("T", "C", "Y", "X")])
    for name in skill.data_vars:
        keep[f"skill_{name}"] = skill[name].drop_vars([c for c in skill[name].coords if c not in ("Y", "X")])
    keep.attrs = {"inputs_sha256": digest, "fit_seconds": seconds, "method": method, "lead": job["lead"],
                  "largest_gap_cpt_vs_recomputed_pearson": gap, "hindcast_values_below_zero_percent": below_zero}
    tmp = folder / "result.part.nc"
    keep.to_netcdf(tmp, encoding={v: {"zlib": True, "complevel": 4} for v in keep.data_vars})
    tmp.replace(result_file)
    return dict(job, path=str(result_file), seconds=seconds, reused=False)


def run_all(jobs: list[dict], workers: int) -> list[dict]:
    """Run every job, `workers` at a time, each in its own Python process."""
    def launch(job):
        folder = Path(job["folder"])
        folder.mkdir(parents=True, exist_ok=True)
        spec, answer, log = folder / "job.json", folder / "done.json", folder / "fit.log"
        spec.write_text(json.dumps(job, default=str))
        answer.unlink(missing_ok=True)
        with open(log, "w") as out:
            code = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(spec)], stdout=out, stderr=subprocess.STDOUT).returncode
        if code != 0 or not answer.exists():
            raise RuntimeError(f"fit {job['lead']} {job['method']} failed (exit {code}); see {log}: " + log.read_text()[-3000:])
        return json.loads(answer.read_text())

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(launch, jobs))


if __name__ == "__main__":
    spec = Path(sys.argv[1])
    job = json.loads(spec.read_text())
    job["settings"] = {k: tuple(v) if isinstance(v, list) else v for k, v in job["settings"].items()}
    result = fit_one(job)
    (spec.parent / "done.json").write_text(json.dumps(result, default=str))
