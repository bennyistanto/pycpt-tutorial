# Learn PyCPT

Step-by-step chapters on the high-level PyCPT 2.10 workflow, one executed notebook
each. The running example is CFSv2, September 2023 initialization, OND 2023
rainfall over Indonesia, trained on 1991-2020, matching the Fit & diagnose case.

| Chapter | Notebook | Status |
| --- | --- | --- |
| 1. Your first PyCPT case | `01-first-case.ipynb` | Executed |
| 2. Getting the data | `02-getting-data.ipynb` | Executed (downloads from the IRI Data Library) |
| 3. Bring your own observations | `03-local-observations.ipynb` | Executed (reads a local CHIRPS v3.0 archive) |
| 4. Evaluate a model | `04-evaluate-models.ipynb` | Executed (runs CPT through evaluate_models) |
| 5. Reading probabilistic forecasts | `05-probabilistic-forecasts.ipynb` | Executed (reads chapter 4 outputs; no refit) |
| 6. Combining models | `06-multi-model-ensemble.ipynb` | Executed (seven models; availability from `research/scripts/check_mme_availability.py`) |
| 7. Adapt it to your region | `07-adapt-your-region.ipynb` | Executed (preflight checks from `pycpt_tutorial/checks.py`) |

Execute a chapter inside the pinned Debian environment:

```
python scripts/execute_learn_chapter.py docs/learn/01-first-case.ipynb
```

The script records each run in `temp/audits/learn-pycpt/` (local, not published) and replaces the home
directory with `~` in text outputs. Quarto rendering never executes these notebooks.

After executing a chapter, refresh its reference list (written into the notebook's
"References" cell):

```
python scripts/build_references.py
```

Figures come from `pycpt_tutorial/figures.py`; use it for every new figure.
