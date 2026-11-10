"""Package verified results for the first offline teaching notebook; never refit."""
from pathlib import Path
import hashlib
import json
import sys

import numpy as np
import pandas as pd
import xarray as xr
from cptio import open_cptdataset

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from pycpt_tutorial.export import save_netcdf
from pycpt_tutorial.seasons import SEASONS,season_window

CASE=REPO/"research/cases/indonesia-all-seasons-2021-2024-025deg"
DEST=REPO/"docs/data"

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    with xr.open_dataset(p) as ds: return ds.load()

def main():
    DEST.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((CASE/"case_manifest.json").read_text())
    sources={}
    def verified(name):
        p=CASE/"outputs"/name
        assert sha(p)==manifest["outputs"][name]["sha256"],name
        sources[str(p.relative_to(REPO))]=sha(p)
        return read(p)
    footprint=verified("evaluation_footprint.nc")
    score=verified("verification_scores.nc")
    fields=[]; starts=[]; ends=[]; issues=[]; source_years=[]; midpoints=[]
    for season in SEASONS:
        ending_year=2024 if season=="NDJ" else 2023
        ds=verified(f"{season}_forecast_comparison.nc")
        chosen=ds.sel(T=ds.season_year==ending_year).squeeze("T",drop=False)
        window=season_window(season,ending_year)
        assert pd.Timestamp(chosen.Ti.item())==window.start
        assert pd.Timestamp(chosen.Tf.item())==window.end
        assert pd.Timestamp(chosen.S.item())==window.initialization
        assert pd.Timestamp(chosen.T.item()).year==2023
        fields.append(chosen[["forecast_rainfall","observed_rainfall"]].drop_vars([c for c in chosen.coords if c not in ("X","Y","forecast_variant")]).expand_dims(season=[season]))
        starts.append(window.start); ends.append(window.end); issues.append(window.initialization)
        source_years.append(ending_year); midpoints.append(pd.Timestamp(chosen.T.item()))
    bundle=xr.concat(fields,dim="season",join="exact",combine_attrs="drop_conflicts")
    bundle=bundle.assign_coords(target_start=("season",pd.to_datetime(starts)),target_end=("season",pd.to_datetime(ends)),initialization=("season",pd.to_datetime(issues)),
                                target_midpoint=("season",pd.to_datetime(midpoints)),source_season_year=("season",source_years))
    bundle["evaluation_mask"]=footprint.evaluation_mask
    bundle["evaluation_weight"]=footprint.evaluation_weight
    mask=bundle.evaluation_mask.astype(bool)
    assert int(mask.sum())==3240
    assert int(bundle.forecast_rainfall.count())==12*7*3240
    metadata={"title":"Indonesia rainfall forecasts: twelve seasons centred on2023","source_case":CASE.name,"main_training_period":"1991–2020",
              "sensitivity_training_period":"1983–2010","calendar_note":"NDJ uses source ending-year2024; actual target November2023–January2024",
              "units_note":"Seasonal rainfall totals in mm; fields on0.25degree country-land grid; raw predictor supplied at1degree",
              "validation_note":"Retrospective current-vintage holdouts; overlapping seasons are not independent years; no probabilistic skill claim"}
    save_netcdf(bundle,DEST/"indonesia-seasons-2023.nc",metadata=metadata,overwrite=True)
    save_netcdf(score,DEST/"verification-context-2021-2024.nc",metadata={**metadata,"calendar_note":"Original ending-year2021–2024 context; not four complete midpoint-year collections"},overwrite=True)
    native=Path.home()/"CPT/cases"/CASE.name/"cpt-OND_cca_1991_2020"
    for filename,label in (("original_predictor","ond-training-predictor"),("original_predictand","ond-training-observations"),("original_forecast_predictor","ond-forecast-predictor")):
        source=native/filename
        ds=open_cptdataset(str(source)).load()
        if filename=="original_forecast_predictor": ds=ds.sel(T=ds.S.dt.year==2023)
        save_netcdf(ds,DEST/f"{label}.nc",metadata={"source_file":str(source),"source_sha256":sha(source),"purpose":"Exact native text inputs packaged for the optional OND calibration rerun"},overwrite=True)
        sources[str(source)]=sha(source)
    outputs={p.name:{"sha256":sha(p),"bytes":p.stat().st_size} for p in sorted(DEST.glob("*.nc"))}
    record={"case":CASE.name,"source_manifest_sha256":sha(CASE/"case_manifest.json"),"source_files":sources,"outputs":outputs,
            "calendar_selection":dict(zip(SEASONS,source_years)),"main_selection_midpoint_year":2023,"retained_cells":3240,
            "note":"Derived teaching copy; source case files unchanged. Only deterministic comparisons are bundled; native probabilities remain in research archive."}
    (DEST/"provenance.json").write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps({"files":len(outputs),"bytes":sum(x["bytes"] for x in outputs.values()),"cells":3240,"calendar_selection":record["calendar_selection"]},indent=2))

if __name__=="__main__": main()
