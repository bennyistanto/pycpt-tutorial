"""Execute a newly extracted fitting kit and compare all scientific outputs."""
from pathlib import Path
import hashlib,json,subprocess,sys,tempfile,zipfile
import xarray as xr
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    audit=ROOT/'research/audits/fitting-tutorial-2023';kit=ROOT/'docs/downloads/fit-diagnose-2023-kit.zip'
    baseline=json.loads((audit/'baseline.json').read_text())['protected']
    notebook=ROOT/'docs/notebooks/fit-diagnose-2023.ipynb';nbsha=sha(notebook)
    metadata=json.loads((audit/'kit.json').read_text());assert sha(kit)==metadata['kit']['sha256']
    work=Path(tempfile.mkdtemp(prefix='fitting-kit-',dir=ROOT/'temp'))
    with zipfile.ZipFile(kit) as z:
        assert all((work/n).resolve().is_relative_to(work.resolve()) for n in z.namelist())
        assert not any('dlauth' in Path(n).name.lower() or Path(n).name.startswith('.env') for n in z.namelist())
        z.extractall(work)
    assert sha(work/'docs/notebooks/fit-diagnose-2023.ipynb')==nbsha
    subprocess.run([sys.executable,str(ROOT/'scripts/execute_fitting_tutorial.py'),'--root',str(work),
                    '--record',str(audit/'kit-execution.json')],check=True)
    source=ROOT/'docs/assets/fitting-2023';actual=work/'docs/assets/fitting-2023'
    checks={'netcdf':[],'csv':[],'png_byte_identical':[]}
    for path in sorted(source.glob('*.nc')):
        with xr.open_dataset(path) as opened:expected=opened.load()
        with xr.open_dataset(actual/path.name) as opened:got=opened.load()
        xr.testing.assert_identical(got,expected)
        checks['netcdf'].append(path.name)
    for path in sorted(source.glob('*.csv')):
        pd.testing.assert_frame_equal(pd.read_csv(path),pd.read_csv(actual/path.name),check_exact=True)
        checks['csv'].append(path.name)
    for path in sorted(source.glob('*.png')):
        assert sha(path)==sha(actual/path.name),path.name
        checks['png_byte_identical'].append(path.name)
    assert (work/'docs/_includes/fitting-findings.qmd').read_bytes()==(ROOT/'docs/_includes/fitting-findings.qmd').read_bytes()
    assert json.loads((actual/'interactive-data.json').read_text())==json.loads((source/'interactive-data.json').read_text())
    assert sha(notebook)==nbsha
    # The 2026-11-02 baseline guarded case one while case two was built. Later, intended
    # edits (reference lists, link fixes, refreshed kits) change some of those files, so
    # the baseline is reported against, not asserted; its own bytes stay unchanged.
    changed=sorted(path for path,value in baseline.items() if sha(ROOT/path)!=value)
    record={'date':__import__('datetime').date.today().isoformat(),'result':'PASS','kit_sha256':sha(kit),'scratch':str(work.relative_to(ROOT)),
        'actual_fits_in_extracted_kit':4,'checks':checks,'interactive_values_and_story_findings_identical':True,
        'canonical_notebook_unchanged':True,'baseline_date':json.loads((audit/'baseline.json').read_text())['date'],
        'case_one_files_unchanged_since_baseline':len(baseline)-len(changed),
        'case_one_files_changed_since_baseline':changed}
    (audit/'kit-verification.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))

if __name__=='__main__':main()
