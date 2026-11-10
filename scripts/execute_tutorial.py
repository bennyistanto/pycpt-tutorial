"""Execute the teaching notebook; optionally test the OND rerun in a scratch copy."""
from pathlib import Path
import argparse
import hashlib
import json
import platform
import subprocess
import nbformat
from nbclient import NotebookClient

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-rerun",action="store_true",help="Execute a scratch copy with the gated OND rerun enabled.")
    args=parser.parse_args()
    path=ROOT/"docs/notebooks/indonesia-seasons-2023.ipynb"
    nb=nbformat.read(path,as_version=4)
    if args.test_rerun:
        cell=next(c for c in nb.cells if c.get("id")=="optional-rerun")
        cell.source=cell.source.replace("RERUN_CPT = False","RERUN_CPT = True")
    client=NotebookClient(nb,timeout=240,kernel_name="pycpt-tutorial",resources={"metadata":{"path":str(ROOT)}})
    client.execute()
    assert all(not any(o.output_type=="error" for o in c.get("outputs",[])) for c in nb.cells)
    output=ROOT/"temp/indonesia-seasons-2023-rerun.ipynb" if args.test_rerun else path
    nbformat.write(nb,output)
    record={"notebook":str(output.relative_to(ROOT)),"python":platform.python_version(),"quarto":subprocess.check_output(["quarto","--version"],text=True).strip(),
            "code_cells_executed":sum(c.cell_type=="code" for c in nb.cells),"errors":0,"optional_cpt_rerun":args.test_rerun,
            "notebook_sha256":hashlib.sha256(output.read_bytes()).hexdigest()}
    dest=ROOT/"temp/audits/tutorial-2023"
    dest.mkdir(parents=True,exist_ok=True)
    (dest/("optional-rerun.json" if args.test_rerun else "execution.json")).write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps(record,indent=2))

if __name__=="__main__": main()
