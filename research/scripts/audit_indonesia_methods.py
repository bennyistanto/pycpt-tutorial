"""Audit frozen CPT sessions; run isolated withholding checks, never edit cases.

Run using the Debian pycpt-tutorial Python. Large evidence remains in Debian;
the compact JSON evidence is copied into research/audits/methodology-2026-11-01/.
"""
from pathlib import Path
import hashlib
import calendar
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys

import numpy as np
from scipy.stats import t

REPO = Path(__file__).resolve().parents[2]
BASE = Path.home()/"CPT/cases"
ALL = BASE/"indonesia-all-seasons-2021-2024-025deg"
AUDIT = Path.home()/"CPT/audits/reference-2026-11-01"
DEST = REPO/"research/audits/methodology-2026-11-01"
ENGINE = Path.home()/"miniforge3/envs/pycpt-tutorial/opt/cpt/bin/CPT.x"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def blocks(path):
    lines = path.read_text().splitlines()
    result = []; i = 0
    tags = {}
    while i < len(lines):
        line = lines[i]
        if line.startswith("cpt:") and any(key in line for key in ("cpt:nrow=", "cpt:T=", "cpt:C=")):
            tags.update(dict(re.findall(r"cpt:([\w]+)=([^,]+)", line)))
            nr = int(tags["nrow"])
            a = np.array([[float(v) for v in row.split()[1:]] for row in lines[i+2:i+2+nr]])
            a[a == float(tags.get("missing", -999))] = np.nan
            result.append((dict(tags), a))
            i += nr+2
        else:
            i += 1
    return result


def values(path):
    return np.stack([a for _, a in blocks(path)])


def perturb(src, dst, year):
    lines = src.read_text().splitlines(); active = False; skip = False; changed = 0
    for i, line in enumerate(lines):
        if line.startswith("cpt:") and any(key in line for key in ("cpt:nrow=", "cpt:T=")):
            active = f"cpt:T={year}-" in line
            skip = active
        elif active and skip:
            skip = False  # longitude heading
        elif active and line and not line.startswith("cpt:"):
            row = line.split()
            # Change one retained grid cell. Its training variance and pattern
            # change substantially, but no mask membership changes.
            for j in range(1, len(row)):
                if float(row[j]) != -999:
                    row[j] = str(float(row[j])+100000)
                    lines[i] = "\t".join(row); changed += 1; active = False
                    break
    assert changed == 1, (src, year, changed)
    dst.write_text("\n".join(lines)+"\n")


def replay(old, dest, command_file, change):
    """Replay only into a distinct audit directory, retaining stdin and stdout."""
    assert old != dest and AUDIT in dest.parents
    dest.mkdir(exist_ok=True)
    for name in ("original_predictor", "original_predictand", "original_forecast_predictor"):
        change(old/name, dest/name)
    commands = command_file.read_text().replace(str(old), str(dest))
    (dest/"commands.txt").write_text(commands)
    fingerprints = {name:sha(dest/name) for name in ("commands.txt", "original_predictor", "original_predictand", "original_forecast_predictor")}
    marker=dest/"completed.json"
    if marker.exists(): assert json.loads(marker.read_text()) == fingerprints
    else:
        env=dict(os.environ); env["CPT_BIN_DIR"]=str(ENGINE.parent)
        with (dest/"session.log").open("w") as log:
            proc=subprocess.run([str(ENGINE)],input=commands+"\n0\n0\n",text=True,stdout=log,stderr=subprocess.STDOUT,cwd=dest,env=env,timeout=120)
        assert proc.returncode==0,(dest,proc.returncode)
        marker.write_text(json.dumps(fingerprints,indent=2)+"\n")


def main():
    AUDIT.mkdir(parents=True, exist_ok=True); DEST.mkdir(parents=True, exist_ok=True)
    roots = [BASE/name for name in (
        "indonesia-ond-2023", "indonesia-ond-2023-025deg",
        "indonesia-ond-2023-025deg-1991-2020", "indonesia-ond-2021-2024-025deg",
        ALL.name)]
    inventory = []
    for root in roots:
        for p in sorted(root.rglob("*commands.txt")):
            lines = [s.strip() for s in p.read_text().splitlines()]
            if "534" not in lines: continue
            folder = Path(next(s for s in lines if s.endswith("/original_predictor"))).parent
            if not (folder/"forecast_probabilities.txt").exists(): continue
            candidates = [p.with_name(p.name.replace("-commands.txt", suffix)) for suffix in (".log", "-session.log")]
            log_path = next(q for q in candidates if q.exists())
            log_text=log_path.read_text()
            periods = re.findall(r"^ Climatological Period: (.+)$",log_text,re.M)
            assert len(set(periods)) == 1, (log_path, periods)
            climate = periods[0].strip()
            bound_labels = re.findall(r"542\.\s+Zero-Bound \(turn (on|off)\)",log_text)
            entry = {"commands": str(p), "sha256": sha(p), "folder": str(folder),
                     "method": "CCA" if "611" in lines[:6] else "PCR", "session_log":str(log_path),
                     "actual_climatological_period":climate,
                     "zero_bound_enabled_after_loading_rainfall":bool(bound_labels and bound_labels[-1]=="off"),
                     "execution_log_confirms_cv":"Cross-validating model ..." in log_text,
                     "execution_log_confirms_full_training_fit":"Constructing model using full training period" in log_text,
                     "window": int(lines[lines.index("534")+1]),
                     "crossvalidation_command": "311" in lines,
                     "forecast_settings_override": "552" in lines,
                     "forecast_values_requested": any(lines[i:i+2] == ["111", "511"] for i in range(len(lines)-1)),
                     "forecast_variance_requested": any(lines[i:i+2] == ["111", "514"] for i in range(len(lines)-1)),
                     "forecast_probabilities_requested": any(lines[i:i+2] == ["111", "501"] for i in range(len(lines)-1))}
            inventory.append(entry)
    (DEST/"session_inventory.json").write_text(json.dumps(inventory, indent=2)+"\n")
    assert len(inventory) == 66, len(inventory)
    assert all(e["execution_log_confirms_cv"] and e["execution_log_confirms_full_training_fit"] and e["zero_bound_enabled_after_loading_rainfall"] for e in inventory)
    assert all(e["window"] == 5 and e["crossvalidation_command"] and not e["forecast_settings_override"] and all(e[k] for k in ("forecast_values_requested", "forecast_variance_requested", "forecast_probabilities_requested")) for e in inventory)
    print("SESSIONS", len(inventory), flush=True)

    checks = []
    for e in inventory:
        folder = Path(e["folder"])
        y = values(folder/"original_predictand")
        h = values(folder/"hindcast_values.txt")
        f = values(folder/"forecast_values.txt")
        v = values(folder/"forecast_prediction_error_variance.txt")
        n = len(y); mask = np.isfinite(y).all(axis=0)
        assert not np.any(np.isfinite(y).any(axis=0) & ~mask)
        assert np.isfinite(values(folder/"original_predictor")).all()
        assert np.isfinite(values(folder/"original_forecast_predictor")).all()
        # The source passes the retained X EOF count, three, even for CCA.
        df = n-3-1
        assert int(blocks(folder/"forecast_prediction_error_variance.txt")[0][0]["dof"]) == df
        training_tags = [tags for tags,_ in blocks(folder/"original_predictand")]
        forecast_tags = [tags for tags,_ in blocks(folder/"original_forecast_predictor")]
        train_dates = {tags["T"] for tags in training_tags}
        forecast_dates = {tags["T"] for tags in forecast_tags}
        assert not train_dates.intersection(forecast_dates)
        def target_end(tags):
            start,*ends=tags["T"].split("/")
            end=ends[-1] if ends else start
            if re.fullmatch(r"\d{1,2}",end): end=start[:4]+"-"+end
            if re.fullmatch(r"\d{4}-\d{1,2}",end):
                year,month=map(int,end.split("-"))
                return dt.datetime(year,month,calendar.monthrange(year,month)[1],23,59,59)
            return dt.datetime.fromisoformat(end)
        assert max(map(target_end,training_tags)) < min(dt.datetime.fromisoformat(tags["S"]) for tags in forecast_tags),(folder,"training target must end before forecast initialization")
        base = np.sum((y[:,mask]-h[:,mask])**2, axis=0)/df
        ratios = v[:,mask]/base
        spread = np.max(ratios, axis=1)-np.min(ratios, axis=1)
        # CPT's default climatological period is clipped to the data. It is
        # NOT generally identical to the training interval. Use actual logs.
        first,last = map(int,re.findall(r"\d{4}",e["actual_climatological_period"]))
        input_years = np.array([int(tags["T"][:4]) for tags,_ in blocks(folder/"original_predictand")])
        cy = y[(input_years>=first)&(input_years<=last)]
        thresholds = np.quantile(cy[:,mask], [.33, .67], axis=0, method="hazen")
        low = t.cdf((thresholds[0]-f[:,mask])/np.sqrt(v[:,mask]), df)*100
        high = t.sf((thresholds[1]-f[:,mask])/np.sqrt(v[:,mask]), df)*100
        expected = np.stack([low, 100-low-high, high], axis=1)
        pb = blocks(folder/"forecast_probabilities.txt")
        # Match explicit target/category tags, independent of block ordering.
        indexed = {(tags["T"],int(tags["C"])):a for tags,a in pb}
        targets = [tags["T"] for tags,_ in blocks(folder/"forecast_values.txt")]
        actual = np.stack([indexed[(target,category)] for target in targets for category in (1,2,3)]).reshape(len(f),3,*mask.shape)[:,:,mask]
        all_difference = float(np.max(abs(actual-expected)))
        positive = f[:,mask] > 0
        if np.any(~positive):
            # Disable the automatic rainfall-name guess in an isolated replay.
            # Fixed-mode full-training regression is unchanged by this label;
            # CV error variances can change. Use ONLY the replay's unbounded
            # full-model location, with the ORIGINAL saved probability scale.
            dest=AUDIT/f"unbounded-{folder.name}"
            def rename_label(src,dst):
                data=src.read_text()
                if src.name=="original_predictand": data=data.replace("cpt:field=precipitation", "cpt:field=audit_unbounded")
                dst.write_text(data)
            replay(folder,dest,Path(e["commands"]),rename_label)
            unbounded=values(dest/"forecast_values.txt")[:,mask]
            np.testing.assert_allclose(unbounded[positive],f[:,mask][positive],atol=.00002,rtol=1e-6)
            assert np.all(unbounded[~positive] <= 0)
            low=t.cdf((thresholds[0]-unbounded)/np.sqrt(v[:,mask]),df)*100
            high=t.sf((thresholds[1]-unbounded)/np.sqrt(v[:,mask]),df)*100
            expected=np.stack([low,100-low-high,high],axis=1)
            print("UNBOUNDED_LOCATION_CHECK",folder.name,int(np.sum(~positive)),flush=True)
        difference = float(np.max(abs(actual-expected)))
        check = {"case": folder.name, "samples": n, "complete_retained_cells": int(mask.sum()),
                 "folder":str(folder), "all_season_case":folder.parent==ALL,
                 "forecast_target_intersects_training":False,
                 "actual_climatological_period":e["actual_climatological_period"], "category_climatology_samples":len(cy),
                 "degrees_of_freedom": df,
                 "variance_to_cv_sse_over_df_ratio_by_forecast": np.median(ratios, axis=1).tolist(),
                 "max_spatial_range_of_ratio": float(np.max(spread)),
                 "zero_bounded_forecast_cells":int(np.sum(~positive)),
                 "probability_max_difference_using_bounded_mean_percentage_points":all_difference,
                 "student_t_probability_max_difference_percentage_points": difference}
        checks.append(check)
        assert np.max(spread) < .0002, check
        assert np.min(ratios) >= 1, check
        # CPT uses AS27 approximation; input/output are printed to six figures.
        if difference >= .002:
            pos = np.unravel_index(np.argmax(abs(actual-expected)),actual.shape)
            k,c,j=pos
            print("PROBABILITY_MISMATCH",check,"position",pos,"actual",actual[pos],"scipy",expected[pos],"forecast",f[:,mask][k,j],"variance",v[:,mask][k,j],"thresholds",thresholds[:,j],flush=True)
        assert difference < .002, check
    assert len(checks) == 66
    (DEST/"probability_reconstruction.json").write_text(json.dumps(checks, indent=2)+"\n")
    print("PROBABILITY_RECONSTRUCTIONS", len(checks), "max_difference_pp", max(c["student_t_probability_max_difference_percentage_points"] for c in checks), flush=True)

    experiments = []
    for method in ("cca", "pcr"):
        old = ALL/f"cpt-OND_{method}_1991_2020"
        command_file = ALL/f"{old.name}-commands.txt"
        original_h = values(old/"hindcast_values.txt")
        for field, year in (("predictand",1991), ("predictand",2005), ("predictand",2020), ("predictor",2005)):
            dest = AUDIT/f"perturb-{method}-{field}-{year}"
            def modify(src,target):
                if src.name==f"original_{field}": perturb(src,target,year)
                else: shutil.copyfile(src,target)
            replay(old,dest,command_file,modify)
            changed_h = values(dest/"hindcast_values.txt")
            changed_index = year-1991
            indices = sorted({(changed_index+offset)%30 for offset in range(-2,3)})
            if field == "predictor": indices.remove(changed_index)
            difference = np.abs(changed_h-original_h)
            excluded_change = float(np.nanmax(difference[indices]))
            other = [i for i in range(30) if i not in indices and (field != "predictor" or i != changed_index)]
            included_change = float(np.nanmax(difference[other]))
            record = {"method": method, "perturbed": field, "perturbed_year": year,
                      "hindcast_years_required_unchanged": [1991+i for i in indices],
                      "max_change_with_perturbed_sample_withheld_mm": excluded_change,
                      "max_change_when_sample_included_mm": included_change,
                      "commands": str(dest/"commands.txt"), "log": str(dest/"session.log")}
            experiments.append(record)
            (DEST/"withholding_experiments.json").write_text(json.dumps(experiments, indent=2)+"\n")
            assert excluded_change == 0 and included_change > .001, record
            print("WITHHOLDING_PASS", method, field, year, flush=True)
    assert all(sha(Path(e["commands"]))==e["sha256"] for e in inventory)
    manifest=json.loads((ALL/"case_manifest.json").read_text())
    integrity={"all_season_output_files":0,"prior_output_files":0,"repo_all_season_output_files":0}
    for name,info in manifest["outputs"].items():
        assert sha(ALL/"outputs"/name)==info["sha256"]
        assert sha(REPO/"research/cases"/ALL.name/"outputs"/name)==info["sha256"]
        integrity["all_season_output_files"]+=1; integrity["repo_all_season_output_files"]+=1
    for name,checksum in manifest["unchanged_benchmark_artifacts_sha256"].items():
        assert sha(Path(name))==checksum
        integrity["prior_output_files"]+=1
    (DEST/"artifact_integrity.json").write_text(json.dumps(integrity,indent=2)+"\n")
    result = {"date":"2026-11-01", "successful_real_case_sessions": len(inventory),
              "probability_reconstructions": len(checks),
              "all_season_probability_reconstructions": sum(c["all_season_case"] for c in checks),
              "zero_bounded_forecast_cells":sum(c["zero_bounded_forecast_cells"] for c in checks),
              "unbounded_location_replays":sum(c["zero_bounded_forecast_cells"]>0 for c in checks),
              "max_probability_difference_percentage_points": max(c["student_t_probability_max_difference_percentage_points"] for c in checks),
              "withholding_experiments": len(experiments), "engine_sha256":sha(ENGINE), "artifact_integrity":integrity,
              "scope_limit":"Numeric consistency and exclusion behavior, not empirical probability reliability or operational forecast certification."}
    (DEST/"summary.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
