# Tutorial tools: NetCDF export

The tutorial includes reusable Python tools as well as explanations and notebooks.
The first is `pycpt_tutorial.export.save_netcdf`. Exporting existing xarray data
requires NumPy, xarray and netCDF4; it does not require PyCPT or a CPT executable.
It uses xarray's [NetCDF writer](https://docs.xarray.dev/en/stable/generated/xarray.Dataset.to_netcdf.html).

PyCPT already returns xarray objects, and its higher-level workflows save several
outputs as NetCDF. This helper adds a consistent export step for custom results:

- Preserve variable names, values, dimensions, units, missing values, and coordinates.
- Apply lossless NetCDF4 compression, with a configurable level from 0 to 9.
- Add public experiment metadata as global attributes.
- Reopen the temporary file and check decoded data, coordinates, and attributes before publishing it.
- Refuse to replace existing files unless `overwrite=True` is explicitly requested.
- Convert CPTv10 text that the installed `cptio` reader supports.

It does not rename coordinates, change units, regrid data, combine model results,
or certify CF compliance. Date ranges, forecast initialization, probability
categories, and model/lead coordinates are kept as supplied. Unsupported CPT text
formats still require an appropriate reader. The optional CPT-text conversion
path additionally requires `cptio`.

## From a notebook

Use the analysis environment for existing xarray data, or the PyCPT environment
when also fitting models. Start Jupyter from the repository root. Given PyCPT's
returned `forecasts`, `hindcasts`, and `skill` datasets:

```python
from pycpt_tutorial.export import save_netcdf

save_netcdf(
    forecasts,
    "exports/forecasts.nc",
    metadata={"case_id": "my-case", "method": "CCA"},
)
save_netcdf(hindcasts, "exports/hindcasts.nc")
save_netcdf(skill, "exports/skill.nc")
```

To export probabilities separately:

```python
save_netcdf(
    forecasts[["probabilistic"]],
    "exports/probabilities.nc",
)
```

Use NetCDF-compatible metadata values such as strings or numbers. Record actual
model versions, observational products, issue dates, and validation methods when
known. The exporter does not infer these from filenames or establish whether a
result was independently validated. Never include account credentials in metadata.

## From the command line

Run from the repository root in Debian. This converts the real CFSv2 forecast
text file in `examples/cpt/` (see [the examples README](../../examples/README.md))
and writes to a folder in your Linux home directory:

```bash
conda activate pycpt-tutorial
python -m pycpt_tutorial.export \
  examples/cpt/CFSv2.PRCP_f2023.tsv \
  ~/exports/cfsv2-ond-2023-forecast.nc \
  --input-format cpt \
  --metadata "initialization=2023-09-01" --metadata "target=Oct-Dec 2023"
```

Existing `.nc` inputs can also be exported with new metadata or compression.
Add `--overwrite` only when replacement is intended. The helper writes a temporary
file beside the destination; default publishing requires hard-link support.
This is tested on Debian's Linux filesystem. Verification loads the full output,
so use this helper for tutorial-scale datasets.

## Example files and checks

All example files are **real data**; none are synthetic.

| File | Contents |
| --- | --- |
| `examples/cpt/CFSv2.PRCP_f2023.tsv` | CPTv10 text from the IRI Data Library: CFSv2 forecast initialized 1 September 2023 for OND 2023, downloaded by PyCPT in [Learn PyCPT chapter 2](../learn/02-getting-data.ipynb) |
| `examples/netcdf/cfsv2-ond-2023-forecast.nc` | The same forecast converted by the command above; values identical to PyCPT's own NetCDF copy |
| `docs/assets/fitting-2023/OND-cca-forecasts.nc` | A real PyCPT CCA forecast for OND 2023 over Indonesia: deterministic rainfall, category probabilities and prediction-error variance, from the [Fit & diagnose case](../chapters/fit-diagnose-2023.qmd) |

The CFSv2 files carry the units attribute `mm/day`, but their values are OND
seasonal totals in mm; chapter 2 shows the evidence. The converted NetCDF records
this in a `units_note` attribute. The exporter keeps units as supplied.

Open a file without rerunning CPT:

```python
import xarray as xr

with xr.open_dataset("docs/assets/fitting-2023/OND-cca-forecasts.nc") as dataset:
    print(dataset)
```

Tests cover round-trip data/metadata integrity, compression settings, extra
model/lead/category dimensions, named DataArrays, overwrite protection, and failed
exports leaving existing results intact:

```bash
python -m unittest discover -s tests -v
```

More tools can follow the scientific pilot: data checks, AOI summaries, and forecast
product preparation. A CF-oriented export profile needs a separate review of time
bounds, lead conventions, units, category definitions, and spatial metadata.
