# Repository layout and relocation record

Reorganized 2026-11-01. The root retains entry-point documentation, project
instructions and continuity files. Tutorial content, durable research evidence
and temporary work have distinct homes.

```text
pycpt-tutorial/
├── README.md
├── AGENTS.md
├── HANDOFF.md
├── PLANS.md
├── LICENSE
├── docs/
│   ├── AUTHORING.md
│   ├── chapters/           # Reader-facing scientific stories
│   ├── notebooks/          # Executed teaching notebooks
│   └── guides/             # Installation, compatibility and tools
├── research/
│   ├── cases/              # Completed cases and frozen output artifacts
│   ├── audits/             # Scientific checks, manifests and source evidence
│   ├── reports/            # Research reviews and this relocation record
│   ├── plans/              # Detailed experiment designs
│   └── scripts/            # Reproducible preparation/run/verify/report pipelines
├── pycpt_tutorial/          # Reusable Python functions
├── environment/            # Tested environment locks
├── examples/               # Small synthetic demonstration files
├── scripts/                # Runtime smoke checker
├── tests/
└── temp/                   # Ignored scratch work, downloads, caches and previews
```

## Original paths and current locations

| Original | Current |
| --- | --- |
| `cases/` | `research/cases/` |
| `audits/` | `research/audits/` |
| Research pipeline files in `scripts/` | `research/scripts/` |
| `scripts/check_cpt.py` | Unchanged |
| `INSTALLATION.md` | `docs/guides/INSTALLATION.md` |
| `CPT_COMPATIBILITY.md` | `docs/guides/CPT_COMPATIBILITY.md` |
| `TOOLS.md` | `docs/guides/TOOLS.md` |
| `METHODOLOGY_AUDIT.md` | `research/reports/METHODOLOGY_AUDIT.md` |
| `NOTEBOOK_REFERENCE_REVIEW.md` | `research/reports/NOTEBOOK_REFERENCE_REVIEW.md` |
| `SEASONAL_BENCHMARK_PLAN.md` | `research/plans/SEASONAL_BENCHMARK_PLAN.md` |
| Root `cache/` | `temp/cache/` |

The publishing framework remains open; `docs/` is prepared for either Quarto or
Jupyter Book. The [authoring recommendation](../../docs/AUTHORING.md) is a story
plus an executed notebook sharing computed outputs. No placeholder is presented
as a completed teaching notebook, and no book deployment was configured.

## Scientific evidence and reproducibility

Before moving files, a path/hash snapshot covered364files. Data, figures,
environment locks, JSON manifests and audit evidence are protected against byte
changes. Documentation links and Python repository-root paths are intentionally
updated. Native Debian data/run paths and the installed environment are unchanged.

Historical JSON manifests retain their original execution paths and script hashes.
Those identify earlier runs; they are not rewritten to imply that relocated or
edited scripts were the versions originally executed. Use this path map to locate
the current code. New provenance records should use the new layout.

Research scripts assume the repository root as their working directory and locate
the shared Python tools from their new depth. The report generator supports a
scratch preview:

```bash
python research/scripts/document_indonesia_all_seasons.py --output-dir temp/report-preview
```

The snapshot, machine-readable path map and final validation are stored in
[repository-restructure-2026-11-01](../audits/repository-restructure-2026-11-01/).
The migration helpers and preview stay in ignored `temp/`.
