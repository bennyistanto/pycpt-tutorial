<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo/logo-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/logo/logo-light.png">
    <img alt="PyCPT Tutorial logo: a stick figure points at a board where a rainfall time series fans out into rain, sun and wind" src="docs/assets/logo/logo-light.png" width="440">
  </picture>
</p>

# PyCPT Tutorial

A practical, evidence-first tutorial on calibrating seasonal rainfall forecasts with
[PyCPT](https://iri-pycpt.github.io/), worked through with real data over Indonesia.

**Read it online: <https://bennyistanto.github.io/pycpt-tutorial>**

The chapters and case studies are executed notebooks, or stories built from them,
using real model and observation data. Numbers in the text come from the executed
outputs, and the chapter, case and methods pages end with their references.

A casual weekend project by [Benny Istanto](https://github.com/bennyistanto).
It is not an official PyCPT tutorial and is not affiliated with, endorsed by or
maintained by the International Research Institute for Climate and Society (IRI)
or the developers of PyCPT and CPT.

## What is inside

**Learn PyCPT**: seven chapters on the PyCPT 2.10 workflow, one forecast question
throughout (CFSv2, 1 September 2023 start, OND 2023 rainfall over Indonesia,
1991-2020 training).

| Chapter | Notebook |
| --- | --- |
| 1. Your first PyCPT case | [01-first-case.ipynb](docs/learn/01-first-case.ipynb) |
| 2. Getting the data | [02-getting-data.ipynb](docs/learn/02-getting-data.ipynb) |
| 3. Bring your own observations | [03-local-observations.ipynb](docs/learn/03-local-observations.ipynb) |
| 4. Evaluate a model | [04-evaluate-models.ipynb](docs/learn/04-evaluate-models.ipynb) |
| 5. Reading probabilistic forecasts | [05-probabilistic-forecasts.ipynb](docs/learn/05-probabilistic-forecasts.ipynb) |
| 6. Combining models | [06-multi-model-ensemble.ipynb](docs/learn/06-multi-model-ensemble.ipynb) |
| 7. Adapt it to your region | [07-adapt-your-region.ipynb](docs/learn/07-adapt-your-region.ipynb) |

**Case studies: Indonesia Seasons 2023**

- [Story](docs/chapters/indonesia-seasons-2023.qmd) with its
  [executed notebook](docs/notebooks/indonesia-seasons-2023.ipynb): CCA, PCR, the raw
  model and climatology compared across twelve seasons centred on 2023, nationally and
  for 38 provinces.
- [Fit & diagnose](docs/chapters/fit-diagnose-2023.qmd) with its
  [executed notebook](docs/notebooks/fit-diagnose-2023.ipynb): four PyCPT fits for OND
  and JJA 2023, model patterns and cross-validated residuals.

Setup, downloads, methods and credits are in [docs/guides/](docs/guides/README.md).

## Where to find the outputs

All outputs are real results from the executed notebooks and research pipelines,
stored as NetCDF4 (open with `xarray.open_dataset`), CSV, JSON or PNG.

| What | Where | Contents |
| --- | --- | --- |
| Case study outputs | [docs/assets/seasonal-2023/](docs/assets/seasonal-2023/), [docs/assets/fitting-2023/](docs/assets/fitting-2023/) | Scores, comparisons, figures and 33 NetCDF files behind the two case studies |
| Downloadable kits | [docs/downloads/](docs/downloads/) | Each case study's notebook with its inputs and helper code, ready to run; all 30 fitted NetCDF outputs of Fit & diagnose as one zip |
| Research benchmarks | [research/cases/](research/cases/) | Frozen experiments, 276 NetCDF files in total: each case's `outputs/` folder, a README describing it and JSON manifests with every file's SHA-256 hash |
| Small examples | [examples/](examples/README.md) | A real CFSv2 forecast as CPT text and as NetCDF, for trying the export tool |

The research benchmarks:

| Case | NetCDF files | Question |
| --- | --- | --- |
| [indonesia-all-seasons-2021-2024-025deg](research/cases/indonesia-all-seasons-2021-2024-025deg/README.md) | 209 | All twelve seasons, 2021-2024, at 0.25° (source of the Story case study) |
| [indonesia-ond-2021-2024-025deg](research/cases/indonesia-ond-2021-2024-025deg/README.md) | 13 | Does the training-period improvement persist across OND 2021-2024? |
| [indonesia-ond-2023-025deg-1991-2020](research/cases/indonesia-ond-2023-025deg-1991-2020/README.md) | 19 | OND 2023 at 0.25°, 1991-2020 training sensitivity |
| [indonesia-ond-2023-025deg](research/cases/indonesia-ond-2023-025deg/README.md) | 18 | OND 2023, CCA and PCR refitted at 0.25° |
| [indonesia-ond-2023](research/cases/indonesia-ond-2023/README.md) | 17 | The first full-Indonesia OND 2023 replay at 1° |

The [research README](research/README.md) explains how these relate, and the
[methodology audit](research/reports/METHODOLOGY_AUDIT.md) records what was checked
against CPT's source and outputs.

## Running it yourself

Reading needs only a browser. The [setup guide](docs/guides/reproduce.qmd) separates
three levels: re-running the saved-results analysis (scientific Python only), fitting
models (the tested PyCPT 2.10.4 environment in `environment/`), and downloading new
data. The Learn PyCPT chapters use the full PyCPT environment; chapter 7 adds a
preflight checker (`pycpt_tutorial.checks`) for your own cases.

## Repository layout

| Folder | Purpose |
| --- | --- |
| [docs/](docs/README.md) | The Quarto book: Learn PyCPT chapters, case studies, notebooks, guides, data and downloads |
| [research/](research/README.md) | Frozen experiments with their outputs, audits, reports and research pipelines |
| [pycpt_tutorial/](pycpt_tutorial/) | Helper code: figures, preflight checks, calendars, aggregation and NetCDF export |
| [scripts/](scripts/) | Notebook execution, data preparation, kit packaging, reference and render tools |
| [environment/](environment/) | Pinned Debian environment locks and runtime verification |
| [examples/](examples/README.md) | Small real-data files for trying the export tools |
| [tests/](tests/) | Unit tests, run with `python -m pytest` |
| [.github/workflows/](.github/workflows/publish.yml) | Builds the book and publishes it to GitHub Pages |

## License

Code is released under the [Mozilla Public License 2.0](LICENSE). Data and boundaries
keep the terms of their sources; see [About & credits](docs/guides/about.qmd).

## Contact

Benny Istanto, [benny.istan.to](https://benny.istan.to). Questions and problems:
[issue tracker](https://github.com/bennyistanto/pycpt-tutorial/issues).
