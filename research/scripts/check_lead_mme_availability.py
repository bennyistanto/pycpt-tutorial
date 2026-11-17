"""Record which seasonal models deliver data for a lead-time case, before any skill is computed.

For one model and one issue date, PyCPT's own download functions are called for every
question the seasonal and monthly lead-time cases ask: six 3-month targets and six 1-month
targets at leads of 1 to 6 months, the training target years, and the cases' predictor
box. The record notes, per target, whether the download succeeded, which training years
hold data, whether the forecast arrived with values and whether the returned target
months are the ones requested. No model is fitted and no observations are needed.

    python research/scripts/check_lead_mme_availability.py --issue 2023-06-01 --model SEAS51c.PRCP --out <folder>
    python research/scripts/check_lead_mme_availability.py --issue 2023-06-01 --merge --out <folder>

Each run writes <folder>/<model>.json; --merge combines them into <folder>/summary.json.
Downloads go to ~/PyCPT/availability-<issue>/, apart from the case folders.
"""
from pathlib import Path
import argparse
import contextlib
import datetime as dt
import io
import json
import time
import traceback

LEADS = [1, 2, 3, 4, 5, 6]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PREDICTOR_EXTENT = {"west": 85, "east": 155, "south": -20, "north": 20}
PREDICTAND_EXTENT = {"west": 94, "east": 142, "south": -12, "north": 7}
LENGTH = {"seasons": 3, "months": 1}


def target_name(issue, lead, length):
    return f"{MONTHS[(issue.month - 1 + lead) % 12]}-{MONTHS[(issue.month - 2 + lead + length) % 12]}"


def check_target(model, issue, training, case, lead):
    import pycpt
    from pycpt import notebook as pycpt_notebook

    target = target_name(issue, lead, LENGTH[case])
    folder = Path.home() / "PyCPT" / f"availability-{issue:%Y-%m-%d}" / case / f"lead-{lead}"
    args = dict(fdate=issue, target=target, target_first_year=training[0], target_final_year=training[1],
                predictor_extent=PREDICTOR_EXTENT, predictand_extent=PREDICTAND_EXTENT)
    record = {"case": case, "lead": lead, "target": target}
    start = time.monotonic()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            domain_dir = pycpt.setup(folder, PREDICTOR_EXTENT)
            h = pycpt_notebook.download_hindcasts([model], domain_dir, False, args)[0]
        h = h.where(h > -999)
        years = [int(y) for y in h["T"].dt.year.values]
        with_data = sorted(y for y, ok in zip(years, h.notnull().any(("Y", "X")).values) if ok)
        wanted = set(range(training[0], training[1] + 1))
        # A lead beyond the model's range does not always fail: for a single month the Data Library
        # returns the last lead it has, labelled with that lead's own target dates. Compare with the request.
        first, last = (MONTHS.index(m) + 1 for m in target.split("-"))
        months = lambda a: [int(a["Ti"].dt.month.values[0]), int(a["Tf"].dt.month.values[0])]
        record.update({
            "downloaded": True,
            "missing_training_years": sorted(wanted - set(with_data)),
            "hindcast_first_start": str(h["S"].values[0])[:10] if "S" in h.coords else None,
            "grid_spacing_degrees": float(abs(h["X"].diff("X")).mean()),
        })
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                f = pycpt_notebook.download_forecasts([model], domain_dir, False, args)[0]
        except Exception as error:
            f = None
            record["forecast_error"] = f"{type(error).__name__}: {str(error).splitlines()[0][:160]}"
        if f is not None:
            f = f.where(f > -999)
        record.update({
            "forecast_present": f is not None and bool(f.notnull().any()),
            "forecast_start": str(f["S"].values[0])[:10] if f is not None and "S" in f.coords else None,
            "returned_target_months": {"hindcast": months(h), "forecast": months(f) if f is not None else None},
            "target_matches": bool(months(h) == [first, last] and (f is None or months(f) == [first, last])),
        })
    except Exception as error:  # record and continue with the next target
        record.update({"downloaded": False, "error": f"{type(error).__name__}: {str(error).splitlines()[0][:160]}",
                       "traceback_tail": traceback.format_exc().splitlines()[-2:]})
    record["elapsed_seconds"] = round(time.monotonic() - start, 1)
    record["qualifies"] = bool(record.get("downloaded") and not record.get("missing_training_years")
                               and record.get("forecast_present") and record.get("target_matches"))
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--issue", required=True, help="issue date, YYYY-MM-DD")
    parser.add_argument("--training", nargs=2, type=int, default=[1992, 2020], help="first and last training target year")
    parser.add_argument("--cases", nargs="*", default=["seasons", "months"])
    parser.add_argument("--model")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--merge", action="store_true")
    args = parser.parse_args()
    issue = dt.datetime.fromisoformat(args.issue)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.model:
        record = {"model": args.model, "issue": issue.date().isoformat(), "training_target_years": args.training,
                  "checked": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "targets": []}
        for case in args.cases:
            for lead in LEADS:
                row = check_target(args.model, issue, args.training, case, lead)
                record["targets"].append(row)
                print(json.dumps({"model": args.model, **{k: row.get(k) for k in (
                    "case", "lead", "target", "downloaded", "missing_training_years", "forecast_present",
                    "target_matches", "qualifies", "elapsed_seconds", "error")}}), flush=True)
                (args.out / f"{args.model}.json").write_text(json.dumps(record, indent=1) + "\n")
    if args.merge:
        records = [json.loads(p.read_text()) for p in sorted(args.out.glob("*.PRCP.json"))]
        (args.out / "summary.json").write_text(json.dumps(records, indent=1) + "\n")
        print(f"merged {len(records)} records")


if __name__ == "__main__":
    main()
