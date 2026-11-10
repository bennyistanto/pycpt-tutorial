"""Write the reference list shown at the bottom of each page.

Every source is defined once in SOURCES; PAGES says which sources each page
cites. The script writes docs/_includes/references/<page>.qmd, which each .qmd
page pulls in under its "References" heading with an include shortcode. Quarto
does not run include shortcodes inside .ipynb files, so for notebooks the script
writes the list directly into the notebook's "## References" markdown cell.
Run it again after regenerating or re-executing a notebook.

Sources were checked with scripts/verify_references.py (links resolve; PyCPT
modules identical to the cited commit) and, for DOIs, against Crossref metadata.

    python scripts/build_references.py
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/_includes/references"
CHECKED = "10 November 2026"
PYCPT = "https://github.com/iri-pycpt/pycpt/blob/084bb5c380c200b5f65f11ba224a965547b91da1/"
NOTEBOOKS = "https://github.com/iri-pycpt/notebooks/blob/1c975316910b9e047ce685d9b8cdefb2c4b73551/"
DL_NOTE = f" Browsing Data Library pages requires signing in (checked {CHECKED}); PyCPT's data requests in this tutorial succeeded without a key."
CPTHELP_NOTE = f" Same page name as on the former cpthelp.iri.columbia.edu, which did not resolve when checked on {CHECKED}."

SOURCES = {
    # Software and workflow sources
    "pycpt_notebook": f"IRI. *PyCPT 2.10.4 source: `pycpt/src/pycpt/notebook.py`* (`setup`, `download_data`, `summarize_available_years`, `evaluate_models` and the plotting functions). Tag pycpt-2.10.4, commit 084bb5c. <{PYCPT}pycpt/src/pycpt/notebook.py>",
    "cptdl": f"IRI. *PyCPT 2.10.4 source: `cptdl`* (data catalog, `leads_from_target`, `evaluate_url`, `download`, `simple_download`). Tag pycpt-2.10.4, commit 084bb5c. <{PYCPT.replace('/blob/', '/tree/')}pycpt/src/cptdl>",
    "cptcore_cca": f"IRI. *PyCPT 2.10.4 source: `pycpt/src/cptcore/functional/cca.py`* (`canonical_correlation_analysis`). Tag pycpt-2.10.4, commit 084bb5c. <{PYCPT}pycpt/src/cptcore/functional/cca.py>",
    "cptextras_view": f"IRI. *PyCPT 2.10.4 source: `pycpt/src/cptextras/view.py`* (`view_probabilistic`) and `dlcolors.py` (`prepare_canvas`). Tag pycpt-2.10.4, commit 084bb5c. <{PYCPT}pycpt/src/cptextras/view.py>",
    "cptextras_redate": f"IRI. *PyCPT 2.10.4 source: `pycpt/src/cptextras/redate.py`* (`redate`). Tag pycpt-2.10.4, commit 084bb5c. <{PYCPT}pycpt/src/cptextras/redate.py>",
    "cptio_verify": f"IRI. *PyCPT 2.10.4 source: `cpt-io/src/cptio/utilities/verify.py`* (`is_valid_cptv10_xyt`). Tag pycpt-2.10.4, commit 084bb5c. <{PYCPT}cpt-io/src/cptio/utilities/verify.py>",
    "operational": f"IRI. *PyCPT operational seasonal notebook* (`Operations/pycpt-operational.ipynb`). iri-pycpt/notebooks, commit 1c97531. <{NOTEBOOKS}Operations/pycpt-operational.ipynb>",
    "cptcore_demo": f"IRI. *CPT-Core demonstration notebook* (`Demo/cptcore_demo.ipynb`). iri-pycpt/notebooks, commit 1c97531. <{NOTEBOOKS}Demo/cptcore_demo.ipynb>",
    "notebooks_repo": "IRI. *PyCPT example notebooks*. GitHub repository iri-pycpt/notebooks. <https://github.com/iri-pycpt/notebooks>",
    "pycpt_docs": "IRI. *PyCPT documentation: About*. <https://iri-pycpt.github.io/>",
    "pycpt_auth": "IRI. *PyCPT documentation: Authentication: downloading protected data*. <https://iri-pycpt.github.io/authentication/>",
    "pycpt_install": "IRI. *PyCPT documentation: Installing PyCPT 2.10.2* (the page title when checked; this tutorial uses 2.10.4). <https://iri-pycpt.github.io/installation/>",
    "teaching_cpt": "IRI. *Guide to PyCPT 2 for Seasonal Climate Forecasts* (Jupyter Book, 2 September 2023 build): The Climate Predictability Tool (CPT). <https://iri.columbia.edu/~awr/pycpt/seasonal-jupyterbook/html_2sep2023/cpt.html>",
    "teaching_config": "IRI. *Guide to PyCPT 2 for Seasonal Climate Forecasts* (Jupyter Book, 2 September 2023 build): Configuring PyCPT 2.5. <https://iri.columbia.edu/~awr/pycpt/seasonal-jupyterbook/html_2sep2023/configuration.html>",
    "cpt_product": "IRI. *CPT+: Climate Predictability Tool*. <https://iri.columbia.edu/our-expertise/climate/tools/cpt/>",
"cpthelp_cca": "CPT+. *444: CCA Maps* (CPT help). <https://cptplus.org/Help/Tools_Models_CCA.html>" + CPTHELP_NOTE,
    "cpthelp_scree": "CPT+. *441: Scree Plots* (CPT help). <https://cptplus.org/Help/Tools_Models_Scree.html>" + CPTHELP_NOTE,
    "cpthelp_yeof": "CPT+. *443: Y Loadings and Scores* (CPT help). <https://cptplus.org/Help/Tools_Models_YEOF.html>" + CPTHELP_NOTE,
    "cpthelp_probs": "CPT+. *Forecast Probabilities* (CPT help). <https://cptplus.org/Help/Tools_Forecast_Probs.html>" + CPTHELP_NOTE,
    "cpthelp_verify": "CPT+. *430: Verification* (CPT help). <https://cptplus.org/Help/Tools_Verify.html>" + CPTHELP_NOTE,
    "cpt_custom": "CPT+. *Customising the Results* (CPT help). <https://cptplus.org/Help/CPT_use_custom.html>",
    "cpt_whatsnew": "CPT+. *What's New* (CPT release history). <https://cptplus.org/whatsnew.html>",
    "cpt_source_1783": "IRI. *CPT 17.8.3 source code archive*. Columbia University Academic Commons. <https://doi.org/10.7916/fdp6-v391>",
    "methodology_audit": "PyCPT Tutorial. *Audit of the Indonesia experiments against CPT references* (research/reports/METHODOLOGY_AUDIT.md). <https://github.com/bennyistanto/pycpt-tutorial/blob/main/research/reports/METHODOLOGY_AUDIT.md>",
    "scipy_t": "SciPy. *scipy.stats.t* (SciPy manual). <https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.t.html>",
    "numpy_quantile": "NumPy. *numpy.quantile* (NumPy manual). <https://numpy.org/doc/stable/reference/generated/numpy.quantile.html>",
    "xarray_quantile": "xarray. *xarray.DataArray.quantile* (API reference). <https://docs.xarray.dev/en/stable/generated/xarray.DataArray.quantile.html>",
    # Data
    "iridl_cfsv2": "IRI Data Library. *NMME NCEP-CFSv2 hindcasts, PENTAD_SAMPLES_FULL, precipitation*. <https://iridl.ldeo.columbia.edu/SOURCES/.Models/.NMME/.NCEP-CFSv2/.HINDCAST/.PENTAD_SAMPLES_FULL/.prec/>" + DL_NOTE,
    "iridl_chirps2": "IRI Data Library. *UCSB CHIRPS version 2.0*. <https://iridl.ldeo.columbia.edu/SOURCES/.UCSB/.CHIRPS/.v2p0/>" + DL_NOTE,
    "iridl_nmme": "IRI Data Library. *North American Multi-Model Ensemble (NMME)* collection. <https://iridl.ldeo.columbia.edu/SOURCES/.Models/.NMME/>" + DL_NOTE,
    "iridl_seas51": "IRI Data Library. *Copernicus C3S ECMWF SEAS5.1* (catalog entry SEAS51c). <https://iridl.ldeo.columbia.edu/SOURCES/.EU/.Copernicus/.CDS/.C3S/.ECMWF/.SEAS51_iri2/>" + DL_NOTE,
    "johnson2019": "Johnson, S., Stockdale, T., Ferranti, L., et al. (2019). SEAS5: the new ECMWF seasonal forecast system. *Geoscientific Model Development*, 12, 1087-1117. <https://doi.org/10.5194/gmd-12-1087-2019>",
    "availability_script": "PyCPT Tutorial. *Model availability check* (research/scripts/check_mme_availability.py) and its record (research/audits/learn-pycpt/mme-availability.json). <https://github.com/bennyistanto/pycpt-tutorial/blob/main/research/scripts/check_mme_availability.py>",
    "chirps3": "Climate Hazards Center, UC Santa Barbara. *CHIRPS: Rainfall Estimates from Rain Gauge and Satellite Observations* (CHIRPS version 3.0 page). <https://www.chc.ucsb.edu/data/chirps3>",
    "saha2014": "Saha, S., Moorthi, S., Wu, X., et al. (2014). The NCEP Climate Forecast System Version 2. *Journal of Climate*, 27(6), 2185-2208. <https://doi.org/10.1175/JCLI-D-12-00823.1>",
    "kirtman2014": "Kirtman, B., Min, D., Infanti, J., et al. (2014). The North American Multimodel Ensemble: Phase-1 seasonal-to-interannual prediction; Phase-2 toward developing intraseasonal prediction. *Bulletin of the American Meteorological Society*, 95(4), 585-601. <https://doi.org/10.1175/BAMS-D-12-00050.1>",
    "funk2015": "Funk, C., Peterson, P., Landsfeld, M., et al. (2015). The climate hazards infrared precipitation with stations: a new environmental record for monitoring extremes. *Scientific Data*, 2, 150066. <https://doi.org/10.1038/sdata.2015.66>",
    "funk2014": "Funk, C., Peterson, P., Landsfeld, M., et al. (2014). *A quasi-global precipitation time series for drought monitoring*. U.S. Geological Survey Data Series 832. <https://doi.org/10.3133/ds832>",
    "naturalearth": "Natural Earth. *Admin 0: Countries*, 1:10m cultural vectors. <https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-admin-0-countries/>",
    "epstein1969": "Epstein, E. S. (1969). A scoring system for probability forecasts of ranked categories. *Journal of Applied Meteorology*, 8(6), 985-987. <https://doi.org/10.1175/1520-0450(1969)008%3C0985:ASSFPF%3E2.0.CO;2>",
    "mason2009": "Mason, S. J., and Weigel, A. P. (2009). A generic forecast verification framework for administrative purposes. *Monthly Weather Review*, 137(1), 331-349. <https://doi.org/10.1175/2008MWR2553.1>",
    "barnston1993": "Barnston, A. G., and van den Dool, H. M. (1993). A degeneracy in cross-validated skill in regression-based forecasts. *Journal of Climate*, 6(5), 963-977. <https://doi.org/10.1175/1520-0442(1993)006%3C0963:ADICVS%3E2.0.CO;2>",
    "guan2022": "Guan, H., Zhu, Y., Sinsky, E., et al. (2022). GEFSv12 reforecast dataset for supporting subseasonal and hydrometeorological applications. *Monthly Weather Review*, 150(3), 647-665. <https://doi.org/10.1175/MWR-D-21-0245.1>",
    "iridl_gefs": "IRI Data Library. *SubX EMC GEFSv12_CPC* (hindcast and forecast precipitation). <https://iridl.ldeo.columbia.edu/SOURCES/.Models/.SubX/.EMC/.GEFSv12_CPC/>" + DL_NOTE,
    "chc_daily_readme": "Climate Hazards Center. *Information about CHIRPS Daily Precipitation* (CHIRPS v3.0 daily readme). <https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/readme.txt>",
    "bmkg_dasarian": f"BMKG. *Peringatan Dini Curah Hujan Dasarian* (dekadal rainfall early warnings by regency and city; showed dasarian I November 2026 when checked on {CHECKED}). <https://www.bmkg.go.id/iklim/peringatan-dini-hujan-tinggi>",
    "gefs_audit": "PyCPT Tutorial. *GEFSv12 input adapter audit* (research/reports/GEFSV12_INPUT_ADAPTER.md). <https://github.com/bennyistanto/pycpt-tutorial/blob/main/research/reports/GEFSV12_INPUT_ADAPTER.md>",
    # Tools
    "cartopy": "SciTools. *Cartopy* (documentation). <https://scitools.org.uk/cartopy/docs/latest/>",
    "shapely": "Shapely. *shapely.contains_xy*. <https://shapely.readthedocs.io/en/stable/reference/shapely.contains_xy.html>",
    "xarray_weighted": "xarray. *Compare weighted and unweighted mean temperature* (example gallery). <https://docs.xarray.dev/en/stable/examples/area_weighted_temperature.html>",
}

PAGES = {
    "learn-01": ["operational", "pycpt_notebook", "cptdl", "iridl_cfsv2", "saha2014", "kirtman2014",
                 "iridl_chirps2", "funk2015", "naturalearth", "cartopy"],
    "learn-02": ["pycpt_auth", "pycpt_notebook", "cptdl", "operational", "iridl_cfsv2", "saha2014",
                 "kirtman2014", "iridl_chirps2", "funk2015", "naturalearth", "cartopy"],
    "learn-03": ["operational", "pycpt_notebook", "cptio_verify", "chirps3", "funk2014", "iridl_chirps2",
                 "funk2015", "naturalearth", "shapely", "cartopy"],
    "learn-04": ["pycpt_notebook", "cptcore_cca", "cptextras_redate", "cptextras_view", "operational",
                 "cptcore_demo", "cpthelp_verify", "saha2014", "chirps3", "funk2014", "naturalearth", "cartopy"],
    "case-seasons": ["teaching_cpt", "cpt_product", "iridl_cfsv2", "saha2014", "kirtman2014", "chirps3", "funk2014"],
    "case-fitting": ["teaching_cpt", "cptcore_demo", "cpthelp_cca", "cpthelp_scree", "cpthelp_yeof", "cpt_product",
                     "iridl_cfsv2", "saha2014", "kirtman2014", "chirps3", "funk2014"],
    "notebook-seasons": ["teaching_cpt", "notebooks_repo", "xarray_weighted", "shapely", "iridl_cfsv2",
                         "saha2014", "kirtman2014", "chirps3", "funk2014"],
    "notebook-fitting": ["teaching_cpt", "teaching_config", "cptcore_demo", "cpthelp_cca", "cpthelp_yeof",
                         "iridl_cfsv2", "saha2014", "chirps3", "funk2014"],
    "methods": ["teaching_cpt", "operational", "cpthelp_probs", "cpthelp_verify", "iridl_cfsv2", "saha2014",
                "kirtman2014", "chirps3", "funk2014", "shapely"],
    "learn-05": ["methodology_audit", "pycpt_notebook", "cptcore_cca", "operational", "cpthelp_probs", "cpt_custom",
                 "cpt_whatsnew", "cpt_source_1783", "scipy_t", "numpy_quantile", "xarray_quantile", "chirps3", "funk2014"],
    "learn-06": ["operational", "pycpt_notebook", "cptcore_cca", "availability_script", "iridl_nmme", "kirtman2014",
                 "saha2014", "iridl_seas51", "johnson2019", "chirps3", "funk2014", "naturalearth", "cartopy"],
    "learn-07": ["operational", "pycpt_notebook", "cptdl", "cptio_verify", "pycpt_auth", "pycpt_docs",
                 "availability_script", "methodology_audit", "iridl_chirps2", "funk2015", "chirps3", "funk2014"],
    "case-monthly": ["pycpt_notebook", "cptdl", "methodology_audit", "iridl_cfsv2", "saha2014", "kirtman2014",
                     "chirps3", "funk2014", "mason2009", "epstein1969", "barnston1993"],
    "notebook-monthly": ["pycpt_notebook", "cptdl", "methodology_audit", "iridl_cfsv2", "saha2014", "chirps3",
                         "funk2014", "naturalearth", "shapely", "numpy_quantile", "mason2009", "epstein1969", "barnston1993", "cartopy"],
    "case-seasonal-leads": ["pycpt_notebook", "cptdl", "methodology_audit", "iridl_cfsv2", "saha2014", "kirtman2014",
                            "chirps3", "funk2014", "mason2009", "epstein1969", "barnston1993"],
    "notebook-seasonal-leads": ["pycpt_notebook", "cptdl", "methodology_audit", "iridl_cfsv2", "saha2014", "chirps3",
                                "funk2014", "naturalearth", "shapely", "numpy_quantile", "mason2009", "epstein1969",
                                "barnston1993", "cartopy"],
    "case-dekad-leads": ["iridl_gefs", "guan2022", "bmkg_dasarian", "chirps3", "funk2014", "chc_daily_readme",
                         "pycpt_notebook", "cptcore_cca", "cptextras_redate", "gefs_audit", "mason2009", "epstein1969",
                         "barnston1993"],
    "notebook-dekad-leads": ["iridl_gefs", "guan2022", "bmkg_dasarian", "chirps3", "funk2014", "cptcore_cca",
                             "cptextras_redate", "gefs_audit", "naturalearth", "shapely", "numpy_quantile", "mason2009",
                             "epstein1969", "cartopy"],
    "start": ["pycpt_docs", "pycpt_auth", "pycpt_install", "cpt_product"],
    "reproduce": ["pycpt_install", "pycpt_auth", "pycpt_docs"],
}


NOTEBOOKS = {
    "learn-01": "docs/learn/01-first-case.ipynb",
    "learn-02": "docs/learn/02-getting-data.ipynb",
    "learn-03": "docs/learn/03-local-observations.ipynb",
    "learn-04": "docs/learn/04-evaluate-models.ipynb",
    "learn-05": "docs/learn/05-probabilistic-forecasts.ipynb",
    "learn-06": "docs/learn/06-multi-model-ensemble.ipynb",
    "learn-07": "docs/learn/07-adapt-your-region.ipynb",
    "notebook-seasons": "docs/notebooks/indonesia-seasons-2023.ipynb",
    "notebook-fitting": "docs/notebooks/fit-diagnose-2023.ipynb",
    "notebook-monthly": "docs/notebooks/monthly-leads-2023.ipynb",
    "notebook-seasonal-leads": "docs/notebooks/seasonal-leads-2023.ipynb",
    "notebook-dekad-leads": "docs/notebooks/dekad-leads-2023.ipynb",
}
HEADING = "## References {.unnumbered .reference-section}"


def fill_notebook(path, body):
    """Replace the content of the notebook's References cell; outputs are untouched."""
    nb = json.loads(path.read_text(encoding="utf-8"))
    cells = [c for c in nb["cells"] if c["cell_type"] == "markdown"
             and HEADING in ("".join(c["source"]) if isinstance(c["source"], list) else c["source"])]
    if len(cells) != 1:
        raise SystemExit(f"{path}: expected one References cell, found {len(cells)}")
    text = (HEADING + "\n\n" + body).strip("\n")
    # nbformat's on-disk form: a list of lines, each ending in a newline except the last.
    cells[0]["source"] = text.splitlines(keepends=True)
    path.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for page, keys in PAGES.items():
        lines = [f"{number}. {SOURCES[key]}" for number, key in enumerate(keys, start=1)]
        body = "::: {.reference-list}\n" + "\n".join(lines) + "\n:::\n"
        (OUT / f"{page}.qmd").write_text(body, encoding="utf-8", newline="\n")
        if page in NOTEBOOKS:
            # A fenced div inside a notebook markdown cell triggers Quarto 1.8 warnings,
            # so notebooks get the plain list; styling targets the heading's section.
            fill_notebook(ROOT / NOTEBOOKS[page], "\n".join(lines) + "\n")
        print(f"{page}: {len(keys)} sources{' (written into notebook)' if page in NOTEBOOKS else ''}")
    unused = sorted(set(SOURCES) - {k for keys in PAGES.values() for k in keys})
    if unused:
        print("Defined but unused:", unused)


if __name__ == "__main__":
    main()
