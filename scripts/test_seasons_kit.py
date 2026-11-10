"""Extract the Indonesia seasons kit, run its notebook in the analysis-only environment, compare outputs.

Run with the analysis environment's interpreter (no PyCPT or CPT installed):

    ~/miniforge3/envs/pycpt-tutorial-analysis/bin/python -s scripts/test_seasons_kit.py

Checks:
1. every file in the kit is byte-identical to its source in the repository,
   and the kit contains no credential files;
2. the extracted notebook runs from top to bottom without errors, with PyCPT and
   CPT absent (the default saved-results path, RERUN_CPT = False);
3. every NetCDF, CSV and JSON the notebook writes under docs/assets/seasonal-2023
   matches the published version (NetCDF numerically, CSV/JSON exactly).

Writes research/audits/tutorial-2023/kit-test.json.
"""
from pathlib import Path
import datetime as dt
import hashlib
import importlib.util
import json
import tempfile
import time
import zipfile

import nbformat
import numpy as np
import xarray as xr
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "docs/downloads/indonesia-seasons-2023-kit.zip"
ASSETS = "docs/assets/seasonal-2023"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    assert all(importlib.util.find_spec(name) is None for name in ("pycpt", "cptcore", "cptio")), \
        "Run with the analysis-only environment, where PyCPT is not installed."
    work = Path(tempfile.mkdtemp(prefix="seasons-kit-"))
    with zipfile.ZipFile(KIT) as archive:
        names = archive.namelist()
        assert not any("dlauth" in Path(n).name.lower() or Path(n).name.startswith(".env") for n in names)
        archive.extractall(work)
    files = [n for n in names if n != "README.md"]
    mismatched = [n for n in files if sha(work / n) != sha(ROOT / n)]
    assert not mismatched, mismatched

    notebook_path = work / "docs/notebooks/indonesia-seasons-2023.ipynb"
    nb = nbformat.read(notebook_path, as_version=4)
    start = time.monotonic()
    NotebookClient(nb, timeout=1200, kernel_name="python3",
                   resources={"metadata": {"path": str(notebook_path.parent)}}).execute()
    errors = [i for i, c in enumerate(nb.cells)
              if any(o.get("output_type") == "error" for o in c.get("outputs", []))]
    assert not errors, errors

    produced = sorted(p for p in (work / ASSETS).rglob("*") if p.suffix in (".nc", ".csv", ".json"))
    compared = {}
    for path in produced:
        relative = path.relative_to(work)
        published = ROOT / relative
        if not published.exists():
            compared[str(relative)] = "new file (no published counterpart)"
            continue
        if path.suffix == ".nc":
            with xr.open_dataset(path) as a, xr.open_dataset(published) as b:
                a, b = a.load(), b.load()
            assert sorted(a.data_vars) == sorted(b.data_vars), relative
            for var in a.data_vars:
                if np.issubdtype(a[var].dtype, np.number):
                    np.testing.assert_allclose(a[var].values, b[var].values, rtol=1e-12, atol=1e-8, equal_nan=True)
                else:
                    assert (a[var].values == b[var].values).all(), (relative, var)
            compared[str(relative)] = "numerically equal"
        else:
            same = sha(path) == sha(published)
            if not same and path.suffix == ".json":
                same = json.loads(path.read_text()) == json.loads(published.read_text())
            assert same, relative
            compared[str(relative)] = "identical"

    record = {
        "tested": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "kit": str(KIT.relative_to(ROOT)), "kit_sha256": sha(KIT),
        "files_in_kit": len(names), "files_identical_to_repository": len(files),
        "notebook_cells_with_errors": 0,
        "execution_seconds": round(time.monotonic() - start, 1),
        "pycpt_installed": False,
        "outputs_compared": compared,
    }
    out = ROOT / "research/audits/tutorial-2023/kit-test.json"
    out.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({k: v for k, v in record.items() if k != "outputs_compared"}, indent=2))
    print(f"{len(compared)} outputs compared:", sorted(set(compared.values())))


if __name__ == "__main__":
    main()
