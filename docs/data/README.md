# Tutorial data

The six NetCDF files in this folder belong to the twelve-season case. They are
derived teaching copies of research inputs and results; `provenance.json` and
`products-provenance.json` inventory their hashes and exact source files.
The notebook checks every input hash before and after its analysis.

The [boundary overlays](boundaries/README.md) add grey neighbouring countries
and unfilled Indonesia country/province outlines to the maps. Their separate
provenance record inventories the supplied shapefiles and compact display derivatives.
Separate [province analysis inputs](regions/README.md) hold province scores of the
0.05° pixel errors; every scored pixel belongs to one province.

- `indonesia-seasons-2023.nc`: deterministic forecasts, observations, common mask,
  weights and actual target/issue dates for twelve midpoints in 2023.
- `verification-context-2021-2024.nc`: original ending-year context scores.
- `ond-training-predictor.nc`, `ond-training-observations.nc` and
  `ond-forecast-predictor.nc`: native CPT text inputs converted for the optional
  isolated OND rerun. Forecast input selects September 2023 initialization only.
- `indonesia-seasons-2023-products.nc`: tercile probabilities, normals, tercile
  boundaries and flexible-forecast scales for the same twelve seasons, written by
  `python scripts/prepare_forecast_products_2023.py`.

The other folders hold what each case's executed notebook wrote:

- `fitting-2023/`: inputs and frozen controls of Fit & diagnose.
- `seasonal-leads-2023/`, `monthly-2023/`, `dekad-leads-2023/`, `week-leads-2023/`,
  `pentad-leads-2023/`: tables and NetCDF maps of the single-model lead-time cases.
- `seasonal-mme-2023/`, `monthly-mme-2023/`, `dekad-mme-2023/`, `week-mme-2023/`,
  `pentad-mme-2023/`: the same for the multi-model ensemble cases.
- `learn/`: model availability records used by Learn PyCPT chapters 6 and 7.

Generate from the full research archive with `python scripts/prepare_tutorial_2023.py`
in the pinned Debian environment. This does not fit models. It reads additional
native text inputs from the existing Debian case root; readers do not need those
external source paths because the teaching copies are included here.

Observation attribution: CHIRPS3, Climate Hazards Center, UC Santa Barbara,
[data repository DOI](https://doi.org/10.15780/G2JQ0P) and
[product documentation](https://www.chc.ucsb.edu/data/chirps3).
Model source for the twelve-season case: NCEP CFSv2 through the IRI Data Library; exact source hashes and
URLs are retained in the research case's availability/provenance records.
