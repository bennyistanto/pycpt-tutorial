"""Fit every model of a multi-model lead-time case through PyCPT, in parallel, and build the ensemble.

One job per (lead, model, method). A job downloads the model's hindcasts and forecast with
PyCPT's `download_data` into the lead's case folder, checks that the returned target dates
are the requested ones (a lead beyond a model's range comes back as the last lead it has),
fits CCA or PCR with PyCPT's `evaluate_models`, and saves a compact result file holding what
the case uses: the cross-validated deterministic hindcasts, the forecast, the skill maps and
the EOF and CCA patterns. PyCPT's own (much larger) files stay in the folder's `output/`.

After the fits, one job per lead builds the ensemble with PyCPT's `construct_mme` for the CCA
members and again for the PCR members, and PyCPT's `construct_flex_fcst` for the CCA ensemble.

A result is reused when its settings, model data and observations are unchanged (SHA-256 of
the input values is stored in the file).

    python research/scripts/seasonal_mme_fits.py config.json [--workers 26] [--only-mme]

config.json: {"case_root": ..., "issue": "2023-11-01", "training": [1992, 2020],
  "predictor_extent": {...}, "predictand_extent": {...}, "cpt_args": {...},
  "leads": {"1": {"target": "Dec-Feb", "local_file": ..., "models": [...]}, ...}}
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import multiprocessing
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

# The CPT engine is found through CPT_BIN_DIR, which activating the conda environment sets.
# When this script is started with the environment's python directly, set the same default.
os.environ.setdefault("CPT_BIN_DIR", str(Path(sys.prefix) / "opt" / "cpt" / "bin"))

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PREDICTAND = "CHIRPS3.PRCP"
ENCODING = {"zlib": True, "complevel": 4, "dtype": "float32"}


def _args(config, lead):
    return dict(fdate=dt.datetime.fromisoformat(config["issue"]), target=config["leads"][lead]["target"],
                target_first_year=config["training"][0], target_final_year=config["training"][1],
                predictor_extent=config["predictor_extent"], predictand_extent=config["predictand_extent"])


def _cpt_args(config):
    return {k: tuple(v) if isinstance(v, list) else v for k, v in config["cpt_args"].items()}


def _digest(config, arrays):
    h = hashlib.sha256()
    for a in arrays:
        h.update(a.values.tobytes())
        for c in ("T", "Y", "X"):
            if c in a.coords:
                h.update(a[c].values.tobytes())
    h.update(json.dumps([config["cpt_args"], config["training"], config["issue"]], sort_keys=True).encode())
    return h.hexdigest()


def _save(ds, path):
    tmp = path.with_suffix(".part")
    ds.to_netcdf(tmp, encoding={v: ENCODING for v in ds.data_vars if ds[v].dtype.kind == "f"})
    tmp.replace(path)


def fit(job):
    """One (lead, model, method) fit. Returns a small status record; never raises."""
    config, lead, model, method = job
    record = {"lead": lead, "model": model, "method": method}
    start = time.monotonic()
    try:
        import numpy as np
        import pandas as pd
        import xarray as xr
        import pycpt

        info = config["leads"][lead]
        args = _args(config, lead)
        domain_dir = pycpt.setup(Path(config["case_root"]) / f"lead-{lead}", config["predictor_extent"])
        out_dir = domain_dir / "compact"
        out_dir.mkdir(exist_ok=True)
        result = out_dir / f"{model}_{method}.nc"
        Y, X, F = pycpt.download_data(PREDICTAND, Path(info["local_file"]), [model], args, domain_dir, False)

        # The data must answer the question asked: every training year, the forecast, and the requested months.
        first, last = (MONTHS.index(m) + 1 for m in info["target"].split("-"))
        years = [int(y) for y in X[0]["T"].dt.year.values]
        wanted = list(range(config["training"][0], config["training"][1] + 1))
        has_data = X[0].where(X[0] > -999).notnull().any(("Y", "X")).values
        problems = []
        if years != wanted or not has_data.all():
            problems.append(f"training years {sorted(set(wanted) - {y for y, ok in zip(years, has_data) if ok})} missing")
        if F[0] is None or not bool(F[0].where(F[0] > -999).notnull().any()):
            problems.append("no forecast")
        for name, a in (("hindcast", X[0]), ("forecast", F[0])):
            if a is not None and [int(a["Ti"].dt.month.values[0]), int(a["Tf"].dt.month.values[0])] != [first, last]:
                problems.append(f"{name} target months {int(a['Ti'].dt.month.values[0])}-{int(a['Tf'].dt.month.values[0])}, asked {first}-{last}")
        if not ((X[0]["T"].values == Y["T"].values).all()):
            problems.append("hindcast T axis differs from the observations")
        if problems:
            raise ValueError("; ".join(problems))

        digest = _digest(config, [Y, X[0], F[0]])
        if result.exists():
            with xr.open_dataset(result) as old:
                if old.attrs.get("inputs_sha256") == digest:
                    return dict(record, status="reused", seconds=float(old.attrs["fit_seconds"]), path=str(result))

        t0 = time.monotonic()
        hcsts, fcsts, skill, pxs, pys = pycpt.evaluate_models(X, method, Y, F, _cpt_args(config), domain_dir, [model])
        seconds = time.monotonic() - t0
        clean = lambda a: a.where(a > -999)
        ds = xr.Dataset()
        ds["cv_hindcast"] = clean(hcsts[0].deterministic).reset_coords(drop=True)
        ds["forecast"] = clean(fcsts[0].deterministic).isel(T=0, drop=True).reset_coords(drop=True)
        ds["forecast_probability"] = clean(fcsts[0].probabilistic).isel(T=0, drop=True).reset_coords(drop=True)
        ds["forecast_pev"] = clean(fcsts[0].prediction_error_variance).isel(T=0, drop=True).reset_coords(drop=True)
        for name in skill[0].data_vars:
            ds[f"skill_{name}"] = skill[0][name].reset_coords(drop=True)
        modes = max(config["cpt_args"]["x_eof_modes"][1], config["cpt_args"]["y_eof_modes"][1])
        px = pxs[0].isel(Mode=slice(0, modes)).rename({"Y": "Yx", "X": "Xx"})
        for name in px.data_vars:
            ds[name] = clean(px[name]).reset_coords(drop=True)
        if method == "CCA":
            py = pys[0].isel(Mode=slice(0, modes))
            for name in py.data_vars:
                ds[name] = clean(py[name]).reset_coords(drop=True)
        ds.attrs = {"inputs_sha256": digest, "fit_seconds": round(seconds, 1), "model": model, "method": method,
                    "target": info["target"], "issue": config["issue"],
                    "forecast_start": str(F[0]["S"].values[0])[:10],
                    "forecast_target": f"{str(F[0]['Ti'].values[0])[:10]} to {str(F[0]['Tf'].values[0])[:10]}",
                    "hindcast_starts": f"{str(X[0]['S'].values[0])[:10]} to {str(X[0]['S'].values[-1])[:10]}",
                    "predictor_grid_degrees": float(abs(X[0]["X"].diff("X")).mean()),
                    "settings": json.dumps(config["cpt_args"], sort_keys=True)}
        _save(ds, result)
        return dict(record, status="fitted", seconds=round(seconds, 1), path=str(result))
    except Exception as error:
        return dict(record, status="failed", seconds=round(time.monotonic() - start, 1),
                    error=f"{type(error).__name__}: {str(error)[:300]}", traceback=traceback.format_exc().splitlines()[-12:])


def ensemble(job):
    """construct_mme for the CCA members, then the PCR members, and construct_flex_fcst for the CCA ensemble."""
    config, lead, members = job
    record = {"lead": lead, "members": members}
    start = time.monotonic()
    try:
        import numpy as np
        import xarray as xr
        import pycpt

        info = config["leads"][lead]
        domain_dir = pycpt.setup(Path(config["case_root"]) / f"lead-{lead}", config["predictor_extent"])
        out_dir, output = domain_dir / "compact", domain_dir / "output"
        Y, _, _ = pycpt.download_data(PREDICTAND, Path(info["local_file"]), members[:1], _args(config, lead), domain_dir, False)
        cpt_args = _cpt_args(config)
        clean = lambda a: a.where(a > -999)
        for method in ("CCA", "PCR"):
            m = method.lower()
            digest = hashlib.sha256(b"".join(xr.open_dataset(out_dir / f"{name}_{method}.nc").attrs["inputs_sha256"].encode()
                                              for name in members)).hexdigest()
            result = out_dir / f"MME_{method}.nc"
            if result.exists():
                with xr.open_dataset(result) as old:
                    if old.attrs.get("inputs_sha256") == digest:
                        continue
            hcsts = [xr.open_dataset(output / f"{name}_crossvalidated_{m}_hindcasts.nc").load() for name in members]
            fcsts = [xr.open_dataset(output / f"{name}_realtime_{m}_forecasts.nc").load() for name in members]
            det, prob, pev, skill = pycpt.construct_mme(fcsts, hcsts, Y, members, members, cpt_args, domain_dir)
            mme_hindcast = xr.open_dataset(output / "MME_deterministic_hindcasts.nc").load()
            for old in output.glob("MME_*.nc"):                                  # keep both methods' PyCPT files
                old.replace(output / old.name.replace("MME_", f"MME-{method}_", 1))
            ds = xr.Dataset()
            ds["cv_hindcast"] = clean(mme_hindcast.deterministic).reset_coords(drop=True)
            ds["forecast"] = clean(det).isel(T=0, drop=True).reset_coords(drop=True)
            ds["forecast_probability"] = clean(prob).isel(T=0, drop=True).reset_coords(drop=True)
            ds["forecast_pev"] = clean(pev).isel(T=0, drop=True).reset_coords(drop=True)
            skill = skill.where(skill > -999)
            for name in skill.data_vars:
                ds[f"skill_{name}"] = skill[name].reset_coords(drop=True)
            # equal-weight mean of the members, computed here independently of construct_mme
            ds["members_mean_forecast"] = xr.concat([clean(f.deterministic).isel(T=0, drop=True).reset_coords(drop=True)
                                                     for f in fcsts], "model").mean("model")
            # PyCPT's flexible forecast: probability of exceeding the training median, and its ingredients
            exceed, fcst_scale, climo_scale, fcst_mu, climo_mu, _, ntrain, threshold = pycpt.construct_flex_fcst(
                method, cpt_args, ds["forecast"], 0.5, True, Y, ds["forecast_pev"])
            ds["flex_exceed_median"] = exceed.reset_coords(drop=True)
            ds["flex_forecast_scale"] = fcst_scale.reset_coords(drop=True)
            ds["flex_climatology_scale"] = climo_scale.reset_coords(drop=True)
            ds["flex_forecast_mean"] = fcst_mu.reset_coords(drop=True)
            ds["flex_climatology_mean"] = climo_mu.reset_coords(drop=True)
            ds["flex_threshold_median"] = threshold.reset_coords(drop=True)
            ds.attrs = {"inputs_sha256": digest, "members": ", ".join(members), "method": method,
                        "flex_degrees_of_freedom": int(ntrain), "target": info["target"], "issue": config["issue"]}
            _save(ds, result)
        return dict(record, status="done", seconds=round(time.monotonic() - start, 1))
    except Exception as error:
        return dict(record, status="failed", seconds=round(time.monotonic() - start, 1),
                    error=f"{type(error).__name__}: {str(error)[:300]}", traceback=traceback.format_exc().splitlines()[-4:])


def download(job):
    """Download one (lead, model) pair's hindcasts and forecast, so that its two fits only read them."""
    config, lead, model = job
    try:
        import pycpt
        info = config["leads"][lead]
        domain_dir = pycpt.setup(Path(config["case_root"]) / f"lead-{lead}", config["predictor_extent"])
        pycpt.download_data(PREDICTAND, Path(info["local_file"]), [model], _args(config, lead), domain_dir, False)
        return None
    except Exception as error:
        return f"lead {lead} {model}: {type(error).__name__}: {str(error)[:200]}"


def run(config, workers=26, only_mme=False, log=print, ensemble_workers=2):
    """Run all fits, then the ensembles for leads whose members all succeeded. Returns the status records."""
    context = multiprocessing.get_context("fork")
    records = []
    if not only_mme:
        # Downloads first, one job per (lead, model). The CCA and PCR fits of a model read the same files;
        # when both downloaded them at once, one read a half-written file (10 of 78 fits failed that way).
        pairs = [(config, lead, model) for lead, info in config["leads"].items() for model in info["models"]]
        with ProcessPoolExecutor(max_workers=min(workers, 12), mp_context=context) as pool:
            for problem in pool.map(download, pairs):
                if problem:
                    log("download: " + problem)
        jobs = [(config, lead, model, method) for lead, info in config["leads"].items()
                for model in info["models"] for method in ("CCA", "PCR")]
        log(f"{len(jobs)} fits, {workers} at a time")
        with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
            for record in pool.map(fit, jobs):
                records.append(record)
                log(json.dumps(record))
    failed = {(r["lead"], r["model"]) for r in records if r["status"] == "failed"}
    jobs = [(config, lead, [m for m in info["models"] if (lead, m) not in failed]) for lead, info in config["leads"].items()]
    # Few ensembles at a time: at 0.05 degree one construct_mme needs about 60 GB of memory. With six at
    # once CPT died in three of them; three at once filled a 188 GB machine.
    with ProcessPoolExecutor(max_workers=min(ensemble_workers, len(jobs)), mp_context=context) as pool:
        for record in pool.map(ensemble, jobs):
            records.append(record)
            log(json.dumps(record))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config", type=Path)
    parser.add_argument("--workers", type=int, default=26)
    parser.add_argument("--only-mme", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    start = time.monotonic()
    records = run(config, args.workers, args.only_mme, log=lambda s: print(s, flush=True))
    (Path(config["case_root"]) / "fit-records.json").write_text(json.dumps(records, indent=2) + "\n")
    print(f"finished in {(time.monotonic() - start) / 60:.1f} min; failed: {sum(r['status'] == 'failed' for r in records)}")


if __name__ == "__main__":
    main()
