# Tutorial source

This is the Quarto book source. The first full-Indonesia story and executed
companion notebook cover twelve seasons centred on 2023, with OND as a worked
example, both training periods and original 2021–2024 context.

The second pair, [fitting story](chapters/fit-diagnose-2023.qmd) and
[executed fitting notebook](notebooks/fit-diagnose-2023.ipynb), runs four actual
OND/JJA 2023 PyCPT fits and inspects their diagnostics. Executing it requires the
full fitting environment; the first case's default execution remains analysis-only.

Ten more pairs follow one issue date through its lead times at five time scales
(seasonal, monthly, dekad, weekly, pentad), each with one model and with a
multi-model ensemble. [chapters/](chapters/README.md) and
[notebooks/](notebooks/README.md) list them, and `learn/` holds the seven Learn
PyCPT chapters.

Start at [the home page](index.qmd) or [reader guide](guides/start.qmd), then explore [the story](chapters/indonesia-seasons-2023.qmd), the
[executed notebook](notebooks/indonesia-seasons-2023.ipynb), and the
[reproduction guide](guides/reproduce.qmd). Rendered HTML is in `_book/`.

```bash
conda activate pycpt-tutorial
python scripts/render_tutorial.py
```

Run from the repository root. Rendering uses saved notebook outputs without
re-execution. The tested renderer is Quarto 1.8.27. The optional calibration path
is documented in the notebook and tested separately.
To refresh scientific outputs, re-execute the notebook (each folder's README names
the command) before packaging; layout edits need only rendering and verification.

| Location | Purpose |
| --- | --- |
| [chapters/](chapters/README.md) | Reader-facing stories, scientific context, findings and limitations |
| [notebooks/](notebooks/README.md) | Executed companion notebooks with reproducible steps and labelled outputs |
| [guides/](guides/README.md) | Installation, compatibility and reusable-tool guidance |

Completed experimental evidence lives in [research/](../research/README.md).
Reusable Python functions live in [pycpt_tutorial/](../pycpt_tutorial/).
Do not copy the entire research archive into the published book. Select the
figures, tables and downloadable artifacts needed by a specific chapter.
