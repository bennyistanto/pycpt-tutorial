# PyCPT tutorial requirements and setup

This tutorial teaches PyCPT use. CPT is its calculation engine when models are
fitted; standalone CPT source builds and application operation are outside scope.

- Read the story or executed notebook: a browser only.
- Run case-one saved-results cells: scientific Python/Jupyter and its complete kit; no
  PyCPT, CPT executable, Quarto or IRIDL credentials.
- Optional OND refit: the tested PyCPT environment with its compatible CPT engine
  and supplied local inputs; no IRIDL credentials.
- Execute case-two OND/JJA fitting: the full tested PyCPT environment, compatible
  engine and complete fitting kit; four actual fits, no IRIDL credentials.
- Optional new data downloads: network access, permissions, and authentication
  only for protected datasets.

Use the [reader requirements guide](start.qmd) and
[separate execution/fitting setup instructions](reproduce.qmd).
The case-one kit includes `environment/offline-analysis.yml` for analysis. The
fitting kit includes `environment/conda-linux-64.lock` for the full environment.
Initial package installation may require internet access; both notebooks use local inputs.
