# Fresh analysis-only Debian environment

Verified 2026-11-02. The complete tutorial kit runs its default saved-results
workflow without installing PyCPT/CPT or using IRI Data Library authentication.

## Installation and scope

- Created a **new conda environment**, not a clone of the full fitting environment,
  from the YAML extracted from the distributed kit. Existing Debian WSL2 was used;
  this was not a new OS installation.
- Prefix: `/home/bennyistanto/miniforge3/envs/pycpt-tutorial-analysis`.
- Conda-forge solve/install succeeded in106.8seconds,268packages including
  dependencies. No additional packages were installed to make the notebook work.
- All eight direct versions match the YAML: Python3.12.5, NumPy2.1.0,
  pandas2.2.2, xarray2024.10.0, Matplotlib3.9.2, netCDF4 1.7.1,
  ipykernel6.29.5 and notebook7.2.2.
- Package/build/hash inventory and an explicit Linux package export are retained
  in the audit folder. Other platforms and future fresh solves are not certified.

## Complete-kit execution

The verifier used the fresh interpreter with user-site packages disabled and an
isolated kernel specification pointing to that exact interpreter. It did not use
the canonical notebook's stored kernel name. PyCPT, cptcore, cptio, cptdl, cptextras
and cptbin were absent by module discovery and installed-package inventory. No
CPT executable was found on the restricted execution PATH or in the environment.

All22original code cells, unchanged, ran in52.1seconds. Two extra audit cells
were inserted in the scratch copy only. Guards rejected credential-file access,
remote connections and external processes except local font/CPU queries.
Results: zero credential-read, remote-network or disallowed-subprocess attempts;
no PyCPT modules loaded and no CPT fits. Loopback kernel traffic was allowed.
Inherited CPT/IRIDL authentication variables were removed without inspecting
credential values; private credential files were never read.

The first audit attempt stopped because the guard blocked NumPy.testing's local
`lscpu` query. A trace confirmed the exact command; the guard was narrowed to
allow it. No environment package or original notebook code changed to pass.
See [harness correction](../audits/analysis-environment/harness-correction.json).

## Output and preservation checks

- Three generated NetCDF datasets match the saved datasets: variables and
  coordinates checked with absolute tolerance1e-8 and relative tolerance1e-12;
  dataset and variable attributes also match.
- Eleven CSV tables match with the same numeric tolerances.
- Two findings JSON files and four generated story fragments match exactly.
- All nine generated PNGs are valid images. Pixel or compressed-byte equality
  is not claimed across the newly solved graphics stack.
- All17packaged input/provenance/boundary files remain byte-identical;22original
  code-cell sources match the canonical notebook. No published scientific files,
  canonical notebook outputs or kit bytes were replaced by this run.
- This verifies execution/reproduction, not new scientific forecast skill.

Kit SHA256: `66131d92f2d30c37fc1ab3d930a9036c13cdc2254ff03c281ec4c4d5df97b096`.
The environment and executed scratch copy are retained for further local review.

Evidence: [installation](../audits/analysis-environment/installation.json),
[packages](../audits/analysis-environment/packages.json),
[execution](../audits/analysis-environment/execution.json),
[supplement](../audits/analysis-environment/supplement.json),
[explicit package export](../audits/analysis-environment/conda-linux-64.explicit).
Verifier: `scripts/verify_analysis_environment.py`; preparation and installation
drivers remain under ignored `temp/`.
