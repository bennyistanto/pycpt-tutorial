"""Execute only the new fitting notebook; keep case-one sources/results unchanged."""
from pathlib import Path
import argparse,hashlib,json,time
import nbformat
from nbclient import NotebookClient
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--record',type=Path)
    args=parser.parse_args();root=args.root.resolve();path=root/'docs/notebooks/fit-diagnose-2023.ipynb'
    nb=nbformat.read(path,4);start=time.monotonic()
    try:
        NotebookClient(nb,timeout=300,kernel_name='pycpt-tutorial',resources={'metadata':{'path':str(root)}}).execute()
    except Exception:
        (root/'temp').mkdir(exist_ok=True);nbformat.write(nb,root/'temp/fitting-notebook-failed.ipynb');raise
    assert all(not any(o.output_type=='error' for o in c.get('outputs',[])) for c in nb.cells)
    nbformat.write(nb,path)
    manifest=json.loads((root/'docs/assets/fitting-2023/execution-manifest.json').read_text())
    assert len(manifest['fits'])==4 and manifest['offline_guard']=={'credential_reads':0,'remote_connections':0}
    record={'date':'2026-11-02','notebook':str(path),'elapsed_seconds':round(time.monotonic()-start,1),
        'code_cells_executed':sum(c.cell_type=='code' for c in nb.cells),'errors':0,'actual_fits':4,
        'notebook_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'native_directories':[r['native_directory'] for r in manifest['fits']],
        'netcdf_outputs':len(manifest['netcdf_outputs']),'offline_guard':manifest['offline_guard']}
    dest=args.record or ROOT/'temp/audits/fitting-tutorial-2023/execution.json';dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))

if __name__=='__main__':main()
