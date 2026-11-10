# Examples

Small files for trying the tutorial's export tools without downloading data or
running CPT. **All of them are real data.** None are synthetic.

| File | What it is | Size |
| --- | --- | --- |
| `cpt/CFSv2.PRCP_f2023.tsv` | CPTv10 text returned by the IRI Data Library for the CFSv2 forecast initialized 1 September 2023, OND 2023, 85°E-155°E and 20°S-20°N on a 1° grid. Downloaded by PyCPT 2.10.4 `download_data` in [Learn PyCPT chapter 2](../docs/learn/02-getting-data.ipynb). | 41,710 bytes |
| `netcdf/cfsv2-ond-2023-forecast.nc` | The same forecast converted with `python -m pycpt_tutorial.export`. Values and coordinates are identical to the NetCDF copy PyCPT wrote during the download. | 36,399 bytes |

Request URL (from chapter 2's executed output):
`https://iridl.ldeo.columbia.edu/SOURCES/.Models/.NMME/.NCEP-CFSv2/.HINDCAST/.PENTAD_SAMPLES_FULL/.prec/S/%280000%201%20Sep%202023%29/VALUES/L/1.5/3.5/RANGEEDGES/%5BL%5D//keepgrids/average/Y/-20/20/RANGEEDGES/X/85/155/RANGEEDGES/%5BM%5D/average/92/mul/-999/setmissing_value/%5BX/Y%5D%5BL/S/add%5D/cptv10.tsv`

**Units.** The file's units attribute reads `mm/day`, but the values are OND
seasonal totals in mm: the request averages over leads and ensemble members and
multiplies by 92 days. Chapter 2 verifies this against independently saved monthly
rates (largest difference for this forecast 0.0050 mm). The NetCDF carries a `units_note` attribute
saying so.

A real PyCPT forecast with category probabilities and prediction-error variance is
published with the Fit & diagnose case: `docs/assets/fitting-2023/OND-cca-forecasts.nc`.

SHA-256, recorded 2026-11-10:

- `cpt/CFSv2.PRCP_f2023.tsv`: `88325f05bc00466a81088b0e50fd0125efaa8a8be15e2fef6d354ebef3bf1bf2`
- `netcdf/cfsv2-ond-2023-forecast.nc`: `1897aaa951a715cc056dbffd60952607c9e08afafed9de6a26310a27dd4bb1d7`
