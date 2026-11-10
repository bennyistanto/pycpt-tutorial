# Offline teaching data

These five NetCDF files are derived teaching copies of verified research inputs
and results. `provenance.json` inventories their hashes and exact source files.
The notebook checks every input hash before and after its analysis.

The [boundary overlays](boundaries/README.md) add grey neighbouring countries
and unfilled Indonesia country/province outlines to the maps. Their separate
provenance record inventories the supplied shapefiles and compact display derivatives.
Separate [province analysis inputs](regions/README.md) partition native country
weights with unsimplified boundaries and preserve unassigned pixels explicitly.

- `indonesia-seasons-2023.nc`: deterministic forecasts, observations, common mask,
  weights and actual target/issue dates for twelve midpoints in2023.
- `verification-context-2021-2024.nc`: original ending-year context scores.
- `ond-training-predictor.nc`, `ond-training-observations.nc` and
  `ond-forecast-predictor.nc`: native CPT text inputs converted for the optional
  isolated OND rerun. Forecast input selects September2023 initialization only.

Generate from the full research archive with `python scripts/prepare_tutorial_2023.py`
in the pinned Debian environment. This does not fit models. It reads additional
native text inputs from the existing Debian case root; readers do not need those
external source paths because the teaching copies are included here.

Observation attribution: CHIRPS3, Climate Hazards Center, UC Santa Barbara,
[data repository DOI](https://doi.org/10.15780/G2JQ0P) and
[product documentation](https://www.chc.ucsb.edu/data/chirps3).
Model source: NCEP CFSv2 through the IRI Data Library; exact source hashes and
URLs are retained in the research case's availability/provenance records.
