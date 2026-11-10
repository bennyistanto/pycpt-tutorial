"""Record upstream notebook configurations and check installed helper semantics."""
from pathlib import Path
import ast
import hashlib
import importlib.util
import json
import sys

import numpy as np
import pycpt
import xarray as xr
from scipy.stats import t

REPO=Path(__file__).resolve().parents[2]
CACHE=REPO/"temp/official-notebooks"
DEST=REPO/"research/audits/methodology-2026-11-01/notebooks"
DEST.mkdir(parents=True,exist_ok=True)
manifest=json.loads((CACHE/"manifest.json").read_text())
assert manifest["commit"]=="1c975316910b9e047ce685d9b8cdefb2c4b73551"
for item in manifest["files"]:
    raw=(CACHE/"raw"/item["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==item["sha256"],item["path"]
    if not item["path"].endswith(".ipynb"): continue
    nb=json.loads((CACHE/"raw"/item["path"]).read_text())
    settings=[]
    for i,cell in enumerate(nb["cells"]):
        if cell["cell_type"]!="code": continue
        source="".join(cell["source"])
        try: tree=ast.parse(source)
        except SyntaxError: continue
        for node in ast.walk(tree):
            if isinstance(node,ast.Assign):
                for target in node.targets:
                    if isinstance(target,ast.Name) and target.id in ("cpt_args","MOS","min_version"):
                        if isinstance(node.value,ast.Dict):
                            value={}
                            for key,val in zip(node.value.keys,node.value.values):
                                try: value[ast.literal_eval(key)]=ast.literal_eval(val)
                                except (ValueError,TypeError): pass
                        else:
                            try: value=ast.literal_eval(node.value)
                            except (ValueError,TypeError): continue
                        settings.append({"cell_index_zero_based":i,"variable":target.id,"value":value})
    item["literal_settings"]=settings
manifest["review_scope"]="Configuration/workflow-source survey of all18notebooks; focused comparison of seasonal examples, Operations, Station, Subseasonal and flex debug cells. Notebooks not executed."
(DEST/"source_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")

# Use the already-audited independent CPT text reader. No CPT invocation.
spec=importlib.util.spec_from_file_location("audit",REPO/"research/scripts/audit_indonesia_methods.py")
audit=importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
folder=Path.home()/"CPT/cases/indonesia-all-seasons-2021-2024-025deg/cpt-OND_cca_1991_2020"
y=audit.values(folder/"original_predictand")
mask=np.isfinite(y).all(axis=0)
f=audit.values(folder/"forecast_values.txt")[2][mask]
assert np.all(f>0),"This controlled helper comparison requires no zero-bounded forecast locations."
variance=audit.values(folder/"forecast_prediction_error_variance.txt")[2][mask]
threshold=np.quantile(y[:,mask],.67,axis=0,method="hazen")
Y=xr.DataArray(y[:,mask],dims=("T","station"))
F=xr.DataArray(f,dims="station")
V=xr.DataArray(variance,dims="station")
Q=xr.DataArray(threshold,dims="station")
result=pycpt.construct_flex_fcst("CCA",{"transform_predictand":None,"tailoring":None},F,Q,False,Y,V)
flex=result[0].values
n=len(y)
expected_flex=t.sf((threshold-f)/np.sqrt((n-2)/n*variance),n)
native_formula=t.sf((threshold-f)/np.sqrt(variance),n-4)
np.testing.assert_allclose(flex,expected_flex,atol=1e-14,rtol=1e-14)
native_blocks=audit.blocks(folder/"forecast_probabilities.txt")
native_above=next(a[mask] for tags,a in native_blocks if tags["T"].startswith("2023-") and tags["C"]=="3")/100
native_gap=float(np.max(abs(native_above-native_formula)))*100
assert native_gap < .002
diff=abs(flex-native_above)*100
pick=int(np.argmax(diff))
ys,xs=np.where(mask)
point={"row_index":int(ys[pick]),"column_index":int(xs[pick]),"threshold_mm":float(threshold[pick]),"deterministic_mm":float(f[pick]),"native_squared_scale_mm2":float(variance[pick]),"native_above_probability_percent":float(native_above[pick]*100),"flex_above_probability_percent":float(flex[pick]*100)}
library=Path(pycpt.__file__).parent/"notebook.py"
source=library.read_text(); tree=ast.parse(source)
function_ranges={node.name:[node.lineno,node.end_lineno] for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in ("evaluate_models","construct_mme_new","evaluate_mme","construct_mme","construct_flex_fcst")}
record={"installed_pycpt_version":pycpt.__version__,"installed_module":str(library),"installed_module_sha256":hashlib.sha256(library.read_bytes()).hexdigest(),"function_line_ranges":function_ranges,"case":"OND2023_CCA_1991_2020","training_samples":n,"comparison_scope":"Same native67th-percentile physical thresholds, same positive forecast means and squared scales. Only helper versus native distribution parameters differ. No fitting or data downloads.","retained_cells":int(mask.sum()),"helper_degrees_of_freedom":n,"native_degrees_of_freedom":n-4,"helper_scale2_factor":(n-2)/n,"native_reconstruction_max_difference_percentage_points":native_gap,"max_native_vs_helper_difference_percentage_points":float(np.max(diff)),"mean_absolute_native_vs_helper_difference_percentage_points":float(np.mean(diff)),"example_max_difference_cell":point}
(DEST/"installed_workflow_check.json").write_text(json.dumps(record,indent=2)+"\n")
print(json.dumps(record,indent=2))
for item in manifest["files"]:
    if "literal_settings" in item:
        cfg=[x for x in item["literal_settings"] if x["variable"]=="cpt_args"]
        print(item["path"],json.dumps([{k:x["value"].get(k) for k in ("validation","crossvalidation_window","transform_predictand","x_eof_modes","y_eof_modes","cca_modes")} for x in cfg]))
