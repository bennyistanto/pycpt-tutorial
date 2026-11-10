# Reader requirements clarification

Verified 2026-11-02. This revision clarifies the PyCPT teaching scope and setup;
it does not introduce new forecasts or revise scientific conclusions.

## Reader paths

| Activity | Requirements |
| --- | --- |
| Read story or executed notebook | Browser |
| Execute default saved-results notebook | Complete kit, writable folder, scientific Python/Jupyter |
| Enable optional OND calibration | Compatible PyCPT and CPT engine, supplied local fitting inputs |
| Download new protected inputs | Network, dataset permission and source-specific authentication |
| Build Quarto website | Repository and Quarto; saved notebook outputs are rendered without execution |

PyCPT's fitting functions use CPT as their calculation engine, as described by
the [official project](https://iri-pycpt.github.io/). Standalone CPT compilation
and unused engine experiments are outside learner setup. The historical reports
are retained as [runtime development notes](RUNTIME_DEVELOPMENT_NOTES.md) and
[compatibility findings](CPT_COMPATIBILITY.md), outside the rendered book.

The [official authentication guide](https://iri-pycpt.github.io/authentication/)
distinguishes public from protected datasets. Authentication is not exclusively
an S2S requirement. Neither the default notebook nor the optional local-input OND
refit downloads new inputs or requires IRIDL credentials.

## Execution evidence

The newly packaged kit was extracted and its 22 original code cells executed in
a scratch copy. Import guards blocked PyCPT, cptcore, cptio, cptdl, cptextras and
cptbin; a negative-control import confirmed the guard worked. Additional guards
blocked credential-file reads, CPT subprocess launches and non-loopback network
connections. The run passed, loaded none of the blocked modules and recorded zero
launch/read/connection attempts. National and regional findings match saved ones.

That initial test used the existing kernel with those imports blocked. A subsequent
[fresh Debian environment test](ANALYSIS_ENVIRONMENT_VALIDATION.md) created the
analysis-only environment from the complete kit's YAML and passed all22original
cells with PyCPT/CPT packages actually absent. The eight direct package versions
matched the specification. The earlier test record remains preserved; the new
evidence is in `research/audits/analysis-environment/`. This is not a
cross-platform environment lock or certification of untested platforms.

## Preservation and presentation

- Three notebook Markdown cells changed. All code cells, their metadata,
  execution counts and saved outputs are identical; the canonical notebook was
  not executed during this revision.
- All 34 protected scientific files and 328 frozen research artifacts are unchanged.
  Interactive runtime code is unchanged; 20,160 score values and 311,040 map
  values still match their sources exactly.
- The notebook download and kit match the updated canonical notebook. The old
  baseline and kit manifest were archived before the documentation hash changed.
- Seven pages rendered; 716 local HTML links checked, none broken. No unused
  engine version mentions remain in published pages. New requirements tables
  checked at desktop and 390px mobile widths; no horizontal page overflow.

Evidence: [scope verification](../audits/reader-requirements/verification.json),
[guarded execution](../audits/reader-requirements/offline-execution.json),
[notebook preservation](../audits/reader-requirements/notebook-documentation.json),
[browser checks](../audits/reader-requirements/browser-validation.json) and
[book verification](../audits/tutorial-2023/verification.json).
