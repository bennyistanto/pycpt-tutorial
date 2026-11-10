# Executed companion notebooks

The first [executed teaching notebook](indonesia-seasons-2023.ipynb) reproduces
the twelve-season2023 story. Default execution is offline; the optional OND
CCA/PCR rerun writes only to a new scratch directory.

Run `python scripts/execute_tutorial.py` from the repository root to refresh its
outputs and generated story findings. Read the [reproduction guide](../guides/reproduce.qmd).
Exploratory and downloaded reference notebooks stay in ignored `temp/`.

The second [executed fitting notebook](fit-diagnose-2023.ipynb) makes four actual
CCA/PCR calls for OND/JJA2023and saves every returned dataset plus checked
diagnostics. Executing it requires the full PyCPT fitting environment and its
compatible engine; local inputs need no credentials or source downloads.
Refresh this notebook separately with `python scripts/execute_fitting_tutorial.py`.
Package and verify its dedicated kit with `package_fitting_tutorial.py` and
`verify_fitting_tutorial.py`; keep the first case unchanged.
