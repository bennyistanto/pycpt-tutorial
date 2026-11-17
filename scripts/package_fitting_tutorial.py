"""Create the case-two fitting kit and the two NetCDF output archives (one per season) only."""
from pathlib import Path
import hashlib,json,shutil,zipfile
import nbformat
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    nbpath=ROOT/'docs/notebooks/fit-diagnose-2023.ipynb';nb=nbformat.read(nbpath,4)
    assert all(c.execution_count is not None and not any(o.output_type=='error' for o in c.outputs) for c in nb.cells if c.cell_type=='code')
    manifest=json.loads((ROOT/'docs/assets/fitting-2023/execution-manifest.json').read_text())
    assert len(manifest['fits'])==4 and len(manifest['netcdf_outputs'])==30
    dest=ROOT/'docs/downloads';dest.mkdir(exist_ok=True)
    shutil.copyfile(nbpath,dest/nbpath.name)
    files=[nbpath,ROOT/'LICENSE',ROOT/'environment/conda-linux-64.lock',
      *sorted(p for p in (ROOT/'docs/data/fitting-2023').rglob('*') if p.is_file()),
      *sorted(p for p in (ROOT/'docs/data/boundaries').glob('*') if p.is_file()),
      *sorted((ROOT/'pycpt_tutorial').glob('*.py'))]
    kit=dest/'fit-diagnose-2023-kit.zip'
    with zipfile.ZipFile(kit,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files:z.write(p,p.relative_to(ROOT))
        z.writestr('README.md','''# Fit and diagnose rainfall forecasts: OND/JJA 2023

Extract this entire kit. The executed notebook is
docs/notebooks/fit-diagnose-2023.ipynb. Reading saved outputs requires only a
notebook viewer. Executing all cells makes four actual PyCPT fits and requires
the FULL tested Linux x86-64 PyCPT environment and its compatible CPT engine.
The analysis-only environment does not execute these fitting cells.

From this extracted directory with conda available:

    conda create -n pycpt-tutorial --file environment/conda-linux-64.lock
    conda activate pycpt-tutorial
    python -m ipykernel install --user --name pycpt-tutorial --display-name "Python (PyCPT Tutorial)"
    jupyter notebook docs/notebooks/fit-diagnose-2023.ipynb

If the fitting environment already exists, activate it instead of creating it
again. Choose Python (PyCPT Tutorial); run top to bottom. Every execution creates
a unique temp/ directory and writes new derived NetCDF/CSV/PNG outputs under
docs/assets/fitting-2023/. The notebook creates any missing output folders.
Initial conda installation can require package downloads. Notebook execution
uses the supplied local inputs and does not need an IRIDL key or new downloads.
Credentials and source preparation drives are not included or required.

The conda release is PyCPT 2.10.4; Python package metadata may report 2.10.4.dev0.
The notebook records both and verifies the audited engine/wrapper hashes. Native
fit logs and commands are retained with outputs. Do not build a standalone engine
or substitute an unverified runtime for this controlled replay.

Training 1991-2020; targets OND/JJA 2023; CCA with 3 X EOFs, 3 Y EOFs and 2 CCA modes,
and PCR with 3 X EOFs; cyclic cross-validation window of 5.
Patterns describe full-training relationships, not per-fold or independent skill.
Native weights and explicit field-score correlations are exported separately.
No model tuning, physical attribution or empirical probability reliability claim.
Native probability/variance fields are retained as outputs, not scored here.

Inputs/controls: docs/data/fitting-2023/provenance.json. Model source is NCEP CFSv2
through the IRI Data Library; observations are CHIRPS3, Climate Hazards Center/
UCSB (https://doi.org/10.15780/G2JQ0P). Supplied Indonesia boundaries credit BIG,
modified by Benny Istanto. Display boundaries do not change scoring support.
See docs/data/boundaries/README.md and provenance.json for attribution/hashes.
Code license: Mozilla Public License 2.0, see LICENSE; data retain source terms.
''')
    # One archive per season: at 0.05 degree a single archive is above GitHub's 100 MB limit per file.
    old=dest/'fit-diagnose-2023-outputs.zip'
    if old.exists():old.unlink()
    published=[p for p in (ROOT/'docs/assets/fitting-2023').rglob('*') if p.is_file() and p.suffix in ['.nc','.csv','.png','.json','.log','.txt'] and p.name!='interactive-data.json']
    archives=[]
    for season,other in [('OND','JJA'),('JJA','OND')]:
      outputs=dest/f'fit-diagnose-2023-outputs-{season}.zip';archives.append(outputs)
      chosen=[p for p in published if not p.name.upper().startswith(other+'-')]
      with zipfile.ZipFile(outputs,'w',zipfile.ZIP_DEFLATED) as z:
          for p in sorted(chosen):z.write(p,p.relative_to(ROOT/'docs/assets/fitting-2023'))
          z.write(ROOT/'LICENSE','LICENSE')
          z.writestr('README.md','''# OND/JJA 2023 fitted outputs

The NetCDFs of one season's two isolated local-input PyCPT fits (the other season is in
a second archive), with the summaries that cover both seasons. The execution manifest
records runtime, configuration, control comparisons and each file hash.
Forecast-comparison and deterministic-scores summarize the selected 2023 examples;
CV-yearly-scores and CV-residual-summary describe deterministic training cross-validation.
Per-fit files retain all returned datasets. Clean predictor/predictand diagnostics
use separate EOF/CCA/spectrum axes, explicitly decoded masks and separately named
native weights and field-score correlations. They describe full-training models.
Native probabilities/variance are preserved, not evidence of empirical reliability.
See the executed fitting notebook and tutorial story for interpretation.
Observations: CHIRPS3, Climate Hazards Center/UCSB, https://doi.org/10.15780/G2JQ0P.
Model: NCEP CFSv2 via IRI Data Library. Source data retain their original terms.
''')
    assert all(a.stat().st_size<95e6 for a in archives)
    for archive in [kit,*archives]:
        with zipfile.ZipFile(archive) as z:
            assert not any('dlauth' in Path(name).name.lower() or Path(name).name.startswith('.env') for name in z.namelist())
    record={'date':__import__('datetime').date.today().isoformat(),'notebook_sha256':sha(nbpath),'kit':{'file':str(kit.relative_to(ROOT)),'sha256':sha(kit),'bytes':kit.stat().st_size,'files':len(files)+1},
       'output_archives':[{'file':str(o.relative_to(ROOT)),'sha256':sha(o),'bytes':o.stat().st_size} for o in archives],
       'scope':'Only case-two downloads changed; no credentials or bulk native session inputs included.'}
    (ROOT/'temp/audits/fitting-tutorial-2023/kit.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))

if __name__=='__main__':main()
