# Story and companion notebook

## Agreed format

Use a readable scientific story plus an executed companion notebook for each
substantial case. This suits readers who want to understand the forecast evidence
and practitioners who want to reproduce it. A notebook alone is sufficient for
a focused coding exercise, but the Indonesia tutorial also needs space to explain
the scientific question, baselines, regional context and limitations.

The story should establish the question, identify the data and forecast target,
explain the main maps and comparisons, and state what the evidence supports.
It should link to the notebook and scientific references. Keep detailed code and
setup logs in the companion material.

The notebook should retain concise Markdown explaining the purpose of each step,
input units and dates, training/validation design, meaningful checks and output
interpretation. Its visible cells should teach the workflow. Longer reusable
preparation, export and plotting functions can live in `pycpt_tutorial/` with
clear links to their implementation.

## One computation, two presentations

The story and notebook must share one set of computed results. The notebook
generates the figures, maps, tables and machine-readable metrics. The story uses
browser-readable exports of those outputs; do not maintain a second calculation in its prose.
Every figure needs a stable label, caption and accessible description. Match the
story's numerical claims to saved metrics and record the producing configuration.

The notebook remains a static, executed chapter with downloadable figures. The
story uses Quarto's [Observable JS support](https://quarto.org/docs/interactive/ojs/)
and [local JavaScript modules](https://quarto.org/docs/interactive/ojs/code-reuse.html)
for reactive views. `docs/assets/story/story.js` provides SVG charts, canvas maps,
keyboard/touch details and sortable tables without third-party library requests.
Values come from `scripts/export_story_interactives.py`, using the saved NetCDF
outputs. Browser code filters and presents data; it does not fit models or
recalculate spatial scores. Local-error maps subtract stored cell errors only.

An example reactive view is:

```text
viewof nationalMetric = selectControl("National score", options, "rmse")
nationalHeatmap(storyData, nationalMetric)
```

The tested renderer is Quarto1.8.27. Activate the pinned Debian environment,
export story inputs with `python scripts/export_story_interactives.py`, then
`python scripts/render_tutorial.py` from the repository root. The render helper
uses an isolated Debian scratch copy to avoid locked OneDrive Quarto caches and
copies only the successful book output back. Quarto1.8.27 requires the local
module to use `.js`, not `.mjs`. Ordinary rendering does not execute notebook cells. The
notebook exports generated findings includes, figures and metrics; do not edit
those outputs manually. For an intentional scientific notebook change: execute,
verify the scientific outputs, package the notebook kit, then export with
`--refresh-baseline` and render. That explicit flag preserves the old hash snapshot.
Presentation-only edits need no notebook execution or kit rebuild.

If a reader clarification changes notebook Markdown, compare all code cells,
their metadata and outputs before/after; preserve them exactly. Refresh the raw
notebook download and kit, archive the prior baseline, then update only the
intentional notebook-document hash after verifying unchanged scientific artifacts.
Do not recalculate results or re-export browser data for a prose-only correction.
Reader requirements must distinguish browser reading, scientific-Python offline
analysis, optional PyCPT/CPT fitting and conditional protected-data authentication.
The guarded extracted-kit check in research/audits/reader-requirements/ records
offline execution with PyCPT imports, credentials, CPT launches and remote access blocked.

Verify data and assets with `python scripts/verify_story_interactives.py` and
`python scripts/verify_tutorial.py`, then exercise the page in a browser. Reload
after rendering to avoid cached CSS/modules. Check defaults, controls, pointer
details, keyboard focus, maps, tables and narrow/wide layouts. Every interactive
view retains a labelled notebook-reference PNG link and a noscript image.
The **Download current view (PNG)** button saves the selected metric, method,
period, season or province with its legend and relevant dates/support notes.
It exports complete SVG extents and redraws maps at a fixed resolution, so a
narrow or scrolled viewport never crops the download. Hover markers, tooltips
and table filters are excluded; CSV downloads follow table filtering separately.
These browser-generated snapshots use the standard Canvas
[`toBlob()` API](https://developer.mozilla.org/en-US/docs/Web/API/HTMLCanvasElement/toBlob)
and local graphics only. Keep original executed notebook PNGs unchanged; they
remain reference figures and need not cover every dropdown combination.

The six SVG-based chart panels also offer **Download current view (SVG)**.
These standalone files include the complete chart, current metadata, editable
text and vector legends, with local styles and no embedded raster images or
external resources. The canvas map panels continue to export PNG. Verify actual
SVG downloads in a standalone viewer as well as the page, including changed
metrics/periods and the full province matrix.

## Execution and publishing workflow

The collection home is `docs/index.qmd`; `guides/start.qmd` explains reader
paths and `guides/about.qmd` holds credits, provenance and reuse information.
Group stories under Case studies and executed notebooks under Computational
notebooks in `docs/_quarto.yml`. Use matching case labels in both groups so
readers can find each companion easily. Add future cases to those groups and
the home overview only when their reader-facing material is ready; preserve
existing URLs.

Use `docs/styles/theme.scss` and `docs/styles/theme-dark.scss` for light/dark theme variables
and local system fonts, and
`docs/styles/styles.css` for shared layout/components and responsive/print rules.
Native Quarto themes provide the appearance toggle and remember the reader's
choice; `respect-user-color-scheme` follows the browser preference initially.
`docs/_brand.yml` supplies the transparent light/dark sidebar logos from
`docs/assets/logo/`. Keep both logo canvases proportionally aligned to avoid
layout movement when switching. Do not invert scientific rasters or palettes;
saved figures and PNG/SVG exports retain their original report-ready colours.
Keep chart palette definitions and scientific exports separate from site styling.
The shared footer is configured in `_quarto.yml`; link to actual source/license
information rather than assigning new terms to existing data or boundaries.
For a layout-only pass, render and check links, desktop/mobile navigation,
keyboard focus, interactive views/downloads and preserved input/output hashes.
There is no need to execute or repackage the verified notebook for those edits.

1. Run saved-results analysis in the verified Debian analysis-only environment;
   use the separate pinned PyCPT environment for optional fitting. Use explicit
   project/data paths and a documented working directory. Fresh-environment kit
   evidence is in `research/audits/analysis-environment/`; its verifier is
   `scripts/verify_analysis_environment.py` (requires the prepared scratch-kit record).
2. Default to verified saved inputs/results for a lightweight reader reproduction.
   Provide a separately documented path to rerun calibration in a new output directory.
   Do not overwrite the frozen research benchmarks.
3. Verify dates, units, masks, validation provenance, output metrics and figures;
   save successful executed notebook outputs and a small provenance record.
4. Build the story from those verified outputs. An ordinary book render should not
   trigger new source downloads or expensive CPT fitting.
5. Recheck story/notebook agreement when results change. Keep execution errors and
   exploratory cells in ignored `temp/`, outside the published notebook.

Raw data, CPT logs, caches and bulk model results stay in Debian or the research
archive. Select only the artifacts needed for the reader-facing source. Existing
research JSON manifests preserve their historical paths and hashes; relocation is
documented separately rather than rewriting those records.

Before teaching probabilities, consult the
[methodology audit](../research/reports/METHODOLOGY_AUDIT.md) and
[official notebook review](../research/reports/NOTEBOOK_REFERENCE_REVIEW.md).
Native and flexible probabilities, independent and in-sample scores, and training
and category-reference periods must remain distinct.

## Fitting and diagnostics case

`fit-diagnose-2023.ipynb` deliberately executes four local-input PyCPT calls.
It needs the full fitting environment, while reading the executed pages needs
only a browser. Keep its data/assets under `fitting-2023/`; do not repackage or
execute the first notebook when updating this case. `prepare_fitting_tutorial.py`
packages inputs/controls, `execute_fitting_tutorial.py` executes the new notebook,
and `package_fitting_tutorial.py` builds its separate kit/output archive.

The notebook exports `interactive-data.json`; `assets/fitting-2023/fitting.js`
only presents these Python values. Preserve old `assets/story/` bytes. Pattern
PNG exports contain both maps and score series; their SVG export is explicitly
the score chart only. Use separate EOF/CCA/spectrum axes and verified original
input masks to decode missing native weights. Retain every returned dataset,
independent score/control checks and the full execution manifest. Do not label
full-training canonical correlations or spectra as forecast skill.

The pinned Quarto renderer treats `text/html` tables as possible widgets and
injects legacy CDN jQuery/RequireJS support. The render helper removes only those
unused bootstrap tags from generated notebook HTML when all saved MIME outputs
are plain text, script-free HTML or PNG and there is no widget metadata. It leaves
interactive/unknown output types alone. This avoids an observed AMD conflict and
keeps these static notebook pages independent of CDN widget scripts, without
changing either canonical notebook. Recheck browser logs/navigation after renderer changes.

Dark-mode page surfaces use neutral charcoal/black with grey/white accents in
`styles/theme-dark.scss` and the `.quarto-dark` overrides in `styles/styles.css`.
Keep scientific chart/map palettes and PNG/SVG export backgrounds unchanged.
The input-only subseasonal work remains research evidence, not a third published
case: consult `research/reports/GEFSV12_INPUT_ADAPTER.md` before authoring it.
