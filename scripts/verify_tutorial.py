"""Independently verify tutorial scores, frozen artifacts, book links and kit execution."""
from pathlib import Path
from datetime import date
from html.parser import HTMLParser
from urllib.parse import unquote,urlsplit
import argparse
import hashlib
import json
import tempfile
import zipfile

import nbformat
from nbclient import NotebookClient
import numpy as np
import xarray as xr

ROOT=Path(__file__).resolve().parents[1]

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    with xr.open_dataset(p) as ds: return ds.load()

class Page(HTMLParser):
    def __init__(self): super().__init__(); self.links=[]; self.ids=set(); self.images=[]; self.scripts=[]; self.interactive=[]
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if d.get("id"): self.ids.add(d["id"])
        for key in ("href","src"):
            if d.get(key): self.links.append(d[key])
        if tag=="img": self.images.append(d)
        if tag=="script" and d.get("src"): self.scripts.append(d["src"])
        if d.get("data-story-panel"): self.interactive.append(d["data-story-panel"])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-kit",action="store_true")
    args=parser.parse_args()
    data=read(ROOT/"docs/data/indonesia-seasons-2023.nc")
    scores=read(ROOT/"docs/assets/seasonal-2023/verification-2023.nc")
    info=json.loads((ROOT/"docs/data/provenance.json").read_text())
    assert list(data.season.values)=="DJF JFM FMA MAM AMJ MJJ JJA JAS ASO SON OND NDJ".split()
    assert np.all(data.target_midpoint.dt.year==2023)
    assert str(data.target_start.sel(season="NDJ").values).startswith("2023-11-01")
    assert str(data.target_end.sel(season="NDJ").values).startswith("2024-01-31")
    assert int(data.source_season_year.sel(season="NDJ"))==2024
    mask=data.evaluation_mask.values.astype(bool)
    weights=data.evaluation_weight.values[mask]; weights=weights/weights.sum()
    assert mask.sum()==3240 and np.isfinite(weights).all() and (weights>0).all()
    f=data.forecast_rainfall.transpose("season","forecast_variant","Y","X").values[:,:,mask]
    y=data.observed_rainfall.transpose("season","Y","X").values[:,mask]
    assert np.isfinite(f).all() and np.isfinite(y).all()
    e=f-y[:,None,:]
    independent={"rmse":np.sqrt(np.sum(e*e*weights,axis=-1)),"mae":np.sum(abs(e)*weights,axis=-1),"bias":np.sum(e*weights,axis=-1)}
    max_gap=0
    for name,array in independent.items():
        np.testing.assert_allclose(array,scores[name].transpose("season","forecast_variant"),atol=1e-8,rtol=0)
        max_gap=max(max_gap,float(np.max(abs(array-scores[name].values))))
    findings=json.loads((ROOT/"docs/assets/seasonal-2023/findings.json").read_text())
    variants=list(data.forecast_variant.values); ci=variants.index("climatology_1991_2020"); ri=variants.index("raw_cfsv2")
    for method in ("CCA","PCR"):
        ix=variants.index(method.lower()+"_1991_2020")
        assert int(np.sum(independent["rmse"][:,ix]<independent["rmse"][:,ci]))==findings["calibration_beats_climatology_seasons"][method]
        assert int(np.sum(independent["rmse"][:,ix]<independent["rmse"][:,ri]))==findings["calibration_beats_raw_seasons"][method]
    for name,expected in info["outputs"].items(): assert sha(ROOT/"docs/data"/name)==expected["sha256"]
    boundary_folder=ROOT/"docs/data/boundaries"
    boundary_info=json.loads((boundary_folder/"provenance.json").read_text())
    for name,expected in boundary_info["outputs"].items():
        assert sha(boundary_folder/name)==expected["sha256"],name
        layer=json.loads((boundary_folder/name).read_text())
        assert len(layer["features"])==expected["features"]
        if name=="neighbours.geojson":
            assert all(f["properties"]["iso3"]!="IDN" for f in layer["features"])
    for name,expected in info["source_files"].items():
        p=Path(name) if name.startswith("/") else ROOT/name
        assert sha(p)==expected,name
    # Preserve the complete pre-tutorial research evidence set, not just the inputs used here.
    snapshot=json.loads((ROOT/"research/audits/repository-restructure-2026-11-01/inventory_before.json").read_text())
    protected=[x for x in snapshot["files"] if Path(x["new"]).suffix not in (".md",".py")]
    for item in protected: assert sha(ROOT/item["new"])==item["sha256"],item["new"]
    nb=nbformat.read(ROOT/"docs/notebooks/indonesia-seasons-2023.ipynb",as_version=4)
    code=[c for c in nb.cells if c.cell_type=="code"]
    assert all(c.execution_count is not None for c in code)
    assert all(not any(o.output_type=="error" for o in c.outputs) for c in code)
    assert "RERUN_CPT = False" in next(c.source for c in code if c.id=="optional-rerun")
    book=ROOT/"docs/_book"
    pages={}
    for p in book.rglob("*.html"):
        page=Page(); page.feed(p.read_text()); pages[p.resolve()]=page
    expected_pages={'index.html','guides/start.html','guides/about.html','guides/reproduce.html','guides/methods.html',
                    'chapters/indonesia-seasons-2023.html','notebooks/indonesia-seasons-2023.html',
                    'chapters/fit-diagnose-2023.html','notebooks/fit-diagnose-2023.html'}
    assert {p.relative_to(book.resolve()).as_posix() for p in pages}==expected_pages
    broken=[]; checked=0
    for path,page in pages.items():
        for link in page.links:
            parts=urlsplit(link)
            if parts.scheme or parts.netloc or not parts.path and not parts.fragment: continue
            target=path if not parts.path else ((book/unquote(parts.path.lstrip("/"))) if parts.path.startswith("/") else path.parent/unquote(parts.path))
            target=target.resolve()
            if target.is_dir(): target=target/"index.html"
            if not target.exists(): broken.append([str(path.relative_to(book)),link])
            elif parts.fragment and target in pages and unquote(parts.fragment) not in pages[target].ids:
                broken.append([str(path.relative_to(book)),link,"missing fragment"])
            checked+=1
    assert not broken,broken
    story=(book/"chapters/indonesia-seasons-2023.html").resolve()
    figures=[im for im in pages[story].images if "story-fallback" in im.get("class","")]
    assert len(figures)==8 and all(im.get("alt") for im in figures)
    assert len(pages[story].interactive)==8
    assert (book/"notebooks/indonesia-seasons-2023.html").exists()
    assert sha(book/"downloads/indonesia-seasons-2023.ipynb")==sha(ROOT/"docs/notebooks/indonesia-seasons-2023.ipynb")
    kit=ROOT/"docs/downloads/indonesia-seasons-2023-kit.zip"
    prior_path=ROOT/"research/audits/tutorial-2023/verification.json"
    prior=json.loads(prior_path.read_text()) if prior_path.exists() else {}
    previous_kit=prior.get("kit_execution","").removeprefix("Not repeated; prior verified kit unchanged. ")
    while previous_kit.startswith("Not repeated; prior verified kit unchanged. "):
        previous_kit=previous_kit.removeprefix("Not repeated; prior verified kit unchanged. ")
    kit_result=("Not repeated; prior verified kit unchanged. "+previous_kit
                if not args.test_kit and prior.get("kit_sha256")==sha(kit) and "PASS" in prior.get("kit_execution","") else "Not requested")
    guarded_path=ROOT/'research/audits/reader-requirements/offline-execution.json'
    if not args.test_kit and guarded_path.exists():
        guarded=json.loads(guarded_path.read_text())
        if guarded.get('result')=='PASS' and guarded.get('kit_sha256')==sha(kit):
            kit_result='PASS: extracted kit executed with PyCPT/CPT/authentication/remote access blocked; findings identical. See research/audits/reader-requirements/offline-execution.json'
    fresh_path=ROOT/'research/audits/analysis-environment/execution.json'
    if not args.test_kit and fresh_path.exists():
        fresh=json.loads(fresh_path.read_text())
        if fresh.get('result')=='PASS' and fresh.get('kit_sha256')==sha(kit):
            kit_result='PASS: complete kit executed in fresh analysis-only Debian environment; PyCPT/CPT absent; numerical outputs and findings matched. See research/audits/analysis-environment/execution.json'
    if args.test_kit:
        work=Path(tempfile.mkdtemp(prefix="tutorial-kit-",dir=ROOT/"temp"))
        with zipfile.ZipFile(kit) as z:
            assert not any(Path(n).name.startswith(".env") or "dlauth" in n for n in z.namelist())
            for name in z.namelist(): assert (work/name).resolve().is_relative_to(work.resolve())
            z.extractall(work)
        kit_nb=nbformat.read(work/"docs/notebooks/indonesia-seasons-2023.ipynb",as_version=4)
        NotebookClient(kit_nb,timeout=240,kernel_name="pycpt-tutorial",resources={"metadata":{"path":str(work)}}).execute()
        assert not any(o.output_type=="error" for c in kit_nb.cells for o in c.get("outputs",[]))
        actual=json.loads((work/"docs/assets/seasonal-2023/findings.json").read_text())
        assert actual==findings
        assert json.loads((work/"docs/assets/seasonal-2023/regional-findings.json").read_text())==json.loads((ROOT/"docs/assets/seasonal-2023/regional-findings.json").read_text())
        kit_result=f"PASS: executed extracted kit offline; findings identical; scratch folder {work.relative_to(ROOT)}"
    record={"date":date.today().isoformat(),"independent_numpy_max_score_difference_mm":max_gap,"forecast_windows":12,"cells":3240,
            "calendar_ndj":"November2023–January2024; source ending-year2024","code_cells_executed":len(code),"notebook_errors":0,
            "protected_research_files_unchanged":len(protected),"source_files_hash_verified":len(info["source_files"]),"book_html_pages":len(pages),
            "local_html_links_checked":checked,"broken_html_links":broken,"static_story_fallbacks_with_alt":len(figures),"interactive_story_panels":len(pages[story].interactive),"kit_execution":kit_result,
            "boundary_layers_hash_verified":len(boundary_info["outputs"]),
            "kit_sha256":sha(kit),"book_story_sha256":sha(story),"findings":findings["calibration_beats_climatology_seasons"]}
    (ROOT/"research/audits/tutorial-2023/verification.json").write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps(record,indent=2))

if __name__=="__main__": main()
