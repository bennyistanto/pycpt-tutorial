"""Create a small runnable kit containing no credentials or bulk research caches."""
from pathlib import Path
import hashlib
import json
import zipfile
import nbformat
import shutil

ROOT=Path(__file__).resolve().parents[1]

def main():
    notebook=ROOT/"docs/notebooks/indonesia-seasons-2023.ipynb"
    nb=nbformat.read(notebook,as_version=4)
    assert all(c.execution_count is not None for c in nb.cells if c.cell_type=="code")
    assert "RERUN_CPT = False" in next(c.source for c in nb.cells if c.get("id")=="optional-rerun")
    files=[notebook,*sorted((ROOT/"docs/data").glob("*.nc")),ROOT/"docs/data/provenance.json",
           *sorted((ROOT/"docs/data/boundaries").glob("*")),
           *sorted((ROOT/"docs/data/regions").glob("*")),
           *sorted((ROOT/"pycpt_tutorial").glob("*.py")),ROOT/"environment/conda-linux-64.lock",ROOT/"environment/offline-analysis.yml",ROOT/"LICENSE"]
    dest=ROOT/"docs/downloads/indonesia-seasons-2023-kit.zip"
    dest.parent.mkdir(exist_ok=True)
    shutil.copyfile(notebook,dest.parent/notebook.name)
    shutil.copyfile(ROOT/"environment/offline-analysis.yml",dest.parent/"offline-analysis.yml")
    with zipfile.ZipFile(dest,"w",zipfile.ZIP_DEFLATED) as z:
        for p in files: z.write(p,p.relative_to(ROOT))
        z.writestr("README.md","""# Indonesia seasonal tutorial kit

Extract this entire archive. Open docs/notebooks/indonesia-seasons-2023.ipynb
from this directory or a subdirectory. The notebook discovers this kit's root.
Its default saved-results execution needs scientific Python packages, not a
PyCPT installation, CPT executable or IRI Data Library credentials.

For offline analysis, create a NEW scientific-Python environment:

    conda env create -f environment/offline-analysis.yml
    conda activate pycpt-tutorial-analysis
    python -m ipykernel install --user --name pycpt-tutorial-analysis --display-name 'Python (Tutorial Analysis)'
    jupyter notebook docs/notebooks/indonesia-seasons-2023.ipynb

Choose Python (Tutorial Analysis), then run all cells. Creating the environment
requires package downloads; subsequent default notebook execution is offline.
The optional OND calibration through PyCPT requires the separate tested fitting
environment (PyCPT 2.10.4, cptio 1.4.0, CPT 17.8.3):

    conda create -n pycpt-tutorial --file environment/conda-linux-64.lock
    conda activate pycpt-tutorial

This explicit lock is for the tested Linux x86-64 runtime. The offline-analysis
YAML lists direct package versions matching that runtime and contains no PyCPT
or CPT dependency; it is not a complete cross-platform lock.
It writes a unique scratch directory under temp/ and preserves saved inputs.

Calendar: all target midpoints in 2023. NDJ ends in January 2024 and preserves the
research ending-year 2024 label. This is a retrospective deterministic case study,
not evidence of general or probabilistic forecast skill.

Data attribution: CHIRPS3, Climate Hazards Center, UC Santa Barbara,
https://doi.org/10.15780/G2JQ0P and https://www.chc.ucsb.edu/data/chirps3 .
Model source: NCEP CFSv2 through the IRI Data Library; exact source hashes and
calendar selections are in docs/data/provenance.json. Teaching fields are derived
country-land aggregations, not the native source products.

Boundary overlays: supplied Indonesia country/province and world shapefiles,
cropped and simplified for display. Indonesia metadata credits Badan Informasi
Geospasial, modified by Benny Istanto. See docs/data/boundaries/README.md and
provenance.json for source hashes and processing; overlays do not affect analysis.
Separate province analysis weights use native country-pixel centres and the
unsimplified supplied province file. See docs/data/regions/README.md; unassigned
country pixels remain an explicit category. The notebook exports province-weighted
coarse-cell errors, not a new fine-resolution provincial rainfall product.
""")
    record={"kit":str(dest.relative_to(ROOT)),"sha256":hashlib.sha256(dest.read_bytes()).hexdigest(),"bytes":dest.stat().st_size,
            "files":[str(p.relative_to(ROOT)) for p in files],"note":"Notebook plus offline inputs/helpers and Linux lock; no credentials, native logs or reference caches."}
    (ROOT/"research/audits/tutorial-2023/kit.json").write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps({k:v for k,v in record.items() if k!="files"},indent=2))

if __name__=="__main__": main()
