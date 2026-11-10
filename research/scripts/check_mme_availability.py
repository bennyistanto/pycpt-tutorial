"""Download candidate models for the Learn PyCPT MME chapter and record what arrives.

For each model, PyCPT's own download_data is called for the chapter's exact question
(1 September initialization, OND target, training target years 1991-2020, 2023
forecast, the same predictor and predictand boxes). The record notes whether the
download succeeded, which training years contain data, and whether the 2023
forecast arrived. No model is fitted.

    python research/scripts/check_mme_availability.py --models CanSIPSIC4.PRCP SPEAR.PRCP
    python research/scripts/check_mme_availability.py --merge

Each run writes docs/data/learn/mme-availability/<model>.json;
--merge combines them into docs/data/learn/mme-availability.json.
"""
from pathlib import Path
import argparse
import datetime as dt
import json
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/data/learn/mme-availability"
DOWNLOAD_ARGS = {
    "fdate": dt.datetime(2023, 9, 1),
    "target": "Oct-Dec",
    "target_first_year": 1991,
    "target_final_year": 2020,
    "predictor_extent": {"west": 85, "east": 155, "south": -20, "north": 20},
    "predictand_extent": {"west": 94, "east": 142, "south": -12, "north": 7},
}


def check(model):
    import pycpt

    case_dir = Path.home() / "PyCPT" / "indonesia-ond-2023-sep-init"
    domain_dir = pycpt.setup(case_dir, DOWNLOAD_ARGS["predictor_extent"])
    local = domain_dir / "data" / "local-CHIRPS3-OND-1991-2020.nc"
    record = {"model": model, "checked": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    start = time.monotonic()
    try:
        _, hindcasts, forecasts = pycpt.download_data("CHIRPS3.PRCP", local, [model], DOWNLOAD_ARGS, domain_dir, True)
        h, f = hindcasts[0], forecasts[0]
        years_with_data = sorted(int(y) for y in h["T"].dt.year.values[h.notnull().any(("Y", "X")).values])
        record.update({
            "downloaded": True,
            "hindcast_shape": dict(h.sizes),
            "hindcast_years_with_data": years_with_data,
            "missing_training_years": sorted(set(range(1991, 2021)) - set(years_with_data)),
            "initialization_months": sorted({int(m) for m in h["S"].dt.month.values}) if "S" in h.coords else None,
            "forecast_present": f is not None and bool(f.notnull().any()),
            "forecast_start": str(f["S"].values[0])[:10] if f is not None and "S" in f.coords else None,
            "grid_spacing_degrees": float(abs(h["X"].diff("X")).mean()),
        })
    except Exception as error:  # record and continue with the next model
        record.update({"downloaded": False, "error": f"{type(error).__name__}: {str(error)[:400]}",
                       "traceback_tail": traceback.format_exc().splitlines()[-3:]})
    record["elapsed_seconds"] = round(time.monotonic() - start, 1)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", nargs="*", default=[])
    parser.add_argument("--merge", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for model in args.models:
        record = check(model)
        (OUT / f"{model}.json").write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps({k: record.get(k) for k in ("model", "downloaded", "missing_training_years",
                                                     "forecast_present", "elapsed_seconds", "error")}), flush=True)
    if args.merge:
        records = [json.loads(p.read_text()) for p in sorted(OUT.glob("*.json"))]
        (OUT.parent / "mme-availability.json").write_text(json.dumps(records, indent=2) + "\n")
        print(f"merged {len(records)} records")


if __name__ == "__main__":
    main()
