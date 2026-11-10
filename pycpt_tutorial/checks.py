"""Preflight checks for a PyCPT case, collected from problems met in Learn PyCPT.

Each check corresponds to a failure that actually occurred in chapters 1-6 with
PyCPT 2.10.4, cptio 1.4.0 and CPT 17.8.3. The checks only look at the inputs; they
do not fit models or download data.

    from pycpt_tutorial import checks
    checks.remember_question(download_args, domain_dir)            # after the first download
    table = checks.check_case(download_args, predictand_name, Y,
                              hindcast_data, forecast_data, predictor_names, domain_dir)
"""
from pathlib import Path
import datetime as dt
import json

import numpy as np
import pandas as pd

QUESTION_FILE = "case-question.json"
# Coordinates cptio 1.4.0 accepts on a CPTv10 array (cptio/utilities/verify.py).
CPT_COORDS = {"T", "Ti", "Tf", "S", "X", "Y", "Mode", "index", "C", "M", "station", "elev", "Name"}


def _row(check, status, detail, chapter):
    return {"check": check, "status": status, "detail": detail, "chapter": chapter}


def _question(download_args):
    """A JSON-safe copy of download_args."""
    out = {}
    for key, value in download_args.items():
        out[key] = value.isoformat() if isinstance(value, (dt.date, dt.datetime)) else value
    return out


def remember_question(download_args, domain_dir):
    """Store the forecast question next to the downloaded files."""
    path = Path(domain_dir) / QUESTION_FILE
    path.write_text(json.dumps(_question(download_args), indent=2, sort_keys=True) + "\n")
    return path


def check_question(download_args, domain_dir):
    """Compare download_args with the question stored in the case folder."""
    path = Path(domain_dir) / QUESTION_FILE
    if not path.exists():
        return _row("case folder question", "warn",
                    f"No {QUESTION_FILE} yet; call remember_question after the first download.", 1)
    saved = json.loads(path.read_text())
    current = _question(download_args)
    changed = sorted(k for k in set(saved) | set(current) if saved.get(k) != current.get(k))
    if changed:
        return _row("case folder question", "fail",
                    "This folder's files were downloaded for a different question (changed: "
                    + ", ".join(changed) + "). Use a new case folder or force_download=True.", 1)
    return _row("case folder question", "ok", "download_args match the question stored in this folder.", 1)


def _years(a):
    return sorted(int(y) for y in a["T"].dt.year.values[a.notnull().any([d for d in a.dims if d != "T"]).values])


def check_predictand(Y, predictand_name):
    rows = []
    missing = Y.attrs.get("missing")
    try:
        numeric = missing is not None and not np.isnan(float(missing))
    except (TypeError, ValueError):
        numeric = False
    if "units" in Y.attrs and numeric:
        rows.append(_row("predictand attributes", "ok", f"units={Y.attrs['units']!r}, missing={missing!r}", 3))
    else:
        rows.append(_row("predictand attributes", "fail",
                         "cptio needs a 'units' attribute and a numeric 'missing' attribute; "
                         f"found units={Y.attrs.get('units')!r}, missing={missing!r}.", 3))
    extra = sorted(set(Y.coords) - CPT_COORDS)
    rows.append(_row("predictand coordinates", "fail" if extra else "ok",
                     f"coordinates cptio does not accept: {extra}" if extra else f"{sorted(Y.coords)}", 3))
    if "S" in Y.coords:
        rows.append(_row("predictand has no initialization date", "fail",
                         "Observations carry an 'S' coordinate. With CPT 17.8.3 and cptio 1.4.0 the fit then "
                         "fails reading CPT output ('Timestamp missing T'). Drop S from the observations.", 4))
    else:
        rows.append(_row("predictand has no initialization date", "ok", "no 'S' coordinate", 4))
    complete = Y.notnull().all("T")
    partial = Y.notnull().any("T") & ~complete
    rows.append(_row("predictand coverage", "warn" if int(partial.sum()) else "ok",
                     f"{int(complete.sum())} locations complete in every season; "
                     f"{int(partial.sum())} locations missing some seasons (not tested in this tutorial).", 3))
    if "PRCP" not in predictand_name.upper():
        rows.append(_row("predictand name", "warn",
                         f"{predictand_name!r} lacks 'PRCP'; plot_forecasts in PyCPT 2.10.4 then fails "
                         "(UnboundLocalError). Rainfall names should contain PRCP.", 4))
    else:
        rows.append(_row("predictand name", "ok", predictand_name, 4))
    return rows


def check_case(download_args, predictand_name, Y, hindcast_data, forecast_data, predictor_names, domain_dir=None):
    """Return a table of checks for one case."""
    rows = []
    if domain_dir is not None:
        rows.append(check_question(download_args, domain_dir))
    rows += check_predictand(Y, predictand_name)
    wanted = list(range(download_args["target_first_year"], download_args["target_final_year"] + 1))
    y_years = _years(Y)
    missing_obs = sorted(set(wanted) - set(y_years))
    rows.append(_row("observation years", "fail" if missing_obs else "ok",
                     f"missing target years: {missing_obs}" if missing_obs else f"{wanted[0]}-{wanted[-1]} all present", 2))
    for name, hindcast, forecast in zip(predictor_names, hindcast_data, forecast_data):
        missing = sorted(set(wanted) - set(_years(hindcast)))
        rows.append(_row(f"{name}: hindcast years", "fail" if missing else "ok",
                         f"missing target years: {missing}" if missing else "all training years present", 2))
        same_t = hindcast.sizes["T"] == Y.sizes["T"] and bool((hindcast["T"].values == Y["T"].values).all())
        rows.append(_row(f"{name}: dates match observations", "ok" if same_t else "fail",
                         "hindcast T equals observation T" if same_t else "hindcast and observation T differ", 3))
        if forecast is None or not bool(forecast.notnull().any()):
            rows.append(_row(f"{name}: forecast", "fail", "no forecast for this initialization", 6))
        else:
            start = str(forecast["S"].values[0])[:10] if "S" in forecast.coords else "unknown"
            expected = download_args["fdate"].date().isoformat()
            rows.append(_row(f"{name}: forecast", "ok" if start == expected else "fail",
                             f"initialized {start} (expected {expected})", 2))
        units = str(hindcast.attrs.get("units", ""))
        if "/day" in units or "day-1" in units:
            rows.append(_row(f"{name}: units label", "warn",
                             f"units attribute is {units!r}, a rate; the catalog requests examined in chapter 1 "
                             "multiply by the season length, so confirm whether the values are rates or seasonal totals.", 2))
    return pd.DataFrame(rows)


def summary(table):
    """Count the outcomes of check_case."""
    return table["status"].value_counts().reindex(["ok", "warn", "fail"], fill_value=0).to_dict()
