"""Check the sources cited in the Learn PyCPT reference lists.

1. Installed PyCPT modules must be byte-identical to the files at the cited
   upstream commit (tag pycpt-2.10.4), so a reference to that file describes the
   code that produced the tutorial's outputs.
2. Every cited URL must resolve (HTTP status below 400 after redirects).

Run in the pinned Debian environment:

    python scripts/verify_references.py

Writes research/audits/learn-pycpt/references.json.
"""
from pathlib import Path
import datetime as dt
import hashlib
import importlib
import json

import requests

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "084bb5c380c200b5f65f11ba224a965547b91da1"
RAW = f"https://raw.githubusercontent.com/iri-pycpt/pycpt/{COMMIT}/"
BLOB = f"https://github.com/iri-pycpt/pycpt/blob/{COMMIT}/"

MODULES = {
    "pycpt.notebook": "pycpt/src/pycpt/notebook.py",
    "cptcore.functional.cca": "pycpt/src/cptcore/functional/cca.py",
    "cptdl.utilities": "pycpt/src/cptdl/utilities.py",
    "cptextras.view": "pycpt/src/cptextras/view.py",
    "cptextras.redate": "pycpt/src/cptextras/redate.py",
    "cptextras.dlcolors": "pycpt/src/cptextras/dlcolors.py",
    "cptdl.catalog": "pycpt/src/cptdl/catalog.py",
    "cptdl.targetleadconv": "pycpt/src/cptdl/targetleadconv.py",
    "cptio.utilities.verify": "cpt-io/src/cptio/utilities/verify.py",
}

URLS = [
    BLOB + path for path in MODULES.values()
] + [
    "https://github.com/iri-pycpt/notebooks/blob/1c975316910b9e047ce685d9b8cdefb2c4b73551/Operations/pycpt-operational.ipynb",
    "https://github.com/iri-pycpt/notebooks/blob/1c975316910b9e047ce685d9b8cdefb2c4b73551/Demo/cptcore_demo.ipynb",
    "https://iri-pycpt.github.io/",
    "https://iri-pycpt.github.io/authentication/",
    "https://iri-pycpt.github.io/installation/",
    "https://iri.columbia.edu/~awr/pycpt/seasonal-jupyterbook/html_2sep2023/cpt.html",
    "https://iri.columbia.edu/~awr/pycpt/seasonal-jupyterbook/html_2sep2023/configuration.html",
    "https://iri.columbia.edu/our-expertise/climate/tools/cpt/",
    "https://cptplus.org/Help/CPT_use_contents.html",
    "https://cptplus.org/Help/Tools_Models_CCA.html",
    "https://cptplus.org/Help/Tools_Models_Scree.html",
    "https://cptplus.org/Help/Tools_Models_YEOF.html",
    "https://cptplus.org/Help/Tools_Forecast_Probs.html",
    "https://cptplus.org/Help/Tools_Verify.html",
    "https://cptplus.org/Help/CPT_use_input_gridded.html",
    "https://iridl.ldeo.columbia.edu/SOURCES/.Models/.NMME/.NCEP-CFSv2/.HINDCAST/.PENTAD_SAMPLES_FULL/.prec/",
    "https://iridl.ldeo.columbia.edu/SOURCES/.UCSB/.CHIRPS/.v2p0/",
    "https://www.chc.ucsb.edu/data/chirps3",
    "https://cptplus.org/Help/CPT_use_custom.html",
    "https://cptplus.org/whatsnew.html",
    "https://doi.org/10.7916/fdp6-v391",
    "https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.t.html",
    "https://numpy.org/doc/stable/reference/generated/numpy.quantile.html",
    "https://docs.xarray.dev/en/stable/generated/xarray.DataArray.quantile.html",
    "https://iridl.ldeo.columbia.edu/SOURCES/.Models/.NMME/",
    "https://iridl.ldeo.columbia.edu/SOURCES/.EU/.Copernicus/.CDS/.C3S/.ECMWF/.SEAS51_iri2/",
    "https://doi.org/10.5194/gmd-12-1087-2019",
    "https://doi.org/10.1175/JCLI-D-12-00823.1",
    "https://doi.org/10.1175/BAMS-D-12-00050.1",
    "https://doi.org/10.1038/sdata.2015.66",
    "https://doi.org/10.3133/ds832",
    "https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-admin-0-countries/",
    "https://scitools.org.uk/cartopy/docs/latest/",
    "https://shapely.readthedocs.io/en/stable/reference/shapely.contains_xy.html",
    "https://docs.xarray.dev/en/stable/examples/area_weighted_temperature.html",
]


def main():
    session = requests.Session()
    session.headers["User-Agent"] = "pycpt-tutorial-reference-check"
    modules = {}
    for name, path in MODULES.items():
        installed = Path(importlib.import_module(name).__file__).read_bytes()
        upstream = session.get(RAW + path, timeout=60).content
        modules[name] = {
            "upstream_path": path,
            "identical": hashlib.sha256(installed).hexdigest() == hashlib.sha256(upstream).hexdigest(),
            "sha256": hashlib.sha256(installed).hexdigest(),
        }
    urls = {}
    for url in URLS:
        try:
            response = session.get(url, timeout=60, allow_redirects=True)
            urls[url] = {"status": response.status_code, "final_url": response.url}
        except requests.RequestException as error:
            urls[url] = {"status": None, "error": type(error).__name__}
    record = {
        "checked": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "upstream_commit": COMMIT,
        "modules": modules,
        "urls": urls,
    }
    out = ROOT / "research/audits/learn-pycpt/references.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n")
    for name, info in modules.items():
        print(f"{'OK ' if info['identical'] else 'DIFF'} {name} == {info['upstream_path']}")
    for url, info in urls.items():
        print(info.get("status"), url)


if __name__ == "__main__":
    main()
