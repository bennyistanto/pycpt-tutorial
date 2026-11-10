# Debian WSL runtime

See [CPT installation findings and compatibility](CPT_COMPATIBILITY.md) for the
diagnostic evidence, changed menu meanings, and a proposed PyCPT migration scope.

The runtime lives in Debian's Linux filesystem. The tutorial repository remains at
`C:\Users\benny\OneDrive\Documents\Github\pycpt-tutorial`, mounted in Debian at
`/mnt/c/Users/benny/OneDrive/Documents/Github/pycpt-tutorial`.

## Environments

| Purpose | Location | Versions |
| --- | --- | --- |
| Tutorial runtime | `/home/bennyistanto/miniforge3/envs/pycpt-tutorial` | Python 3.12.5, PyCPT 2.10.4, cptio 1.4.0, packaged CPT 17.8.3 |
| CPT source-build tools | `/home/bennyistanto/miniforge3/envs/cpt-build` | gfortran 16.2.0 and make |

The runtime was created from the Linux lock file accompanying the official
[PyCPT v2.10.4 release](https://github.com/iri-pycpt/notebooks/releases/tag/v2.10.4).
No runtime package upgrades were applied. A proposed cptbin 17.8.9 update was
unavailable from the stable channel; it was not installed.

Exact installed package snapshots are saved in `environment/conda-linux-64.lock`
and `environment/cpt-build-linux-64.lock`. These describe Linux x86-64 environments.
They are not Windows environment specifications.

## Start working

In a Debian terminal:

```bash
source /home/bennyistanto/miniforge3/etc/profile.d/conda.sh
conda activate pycpt-tutorial
cd /mnt/c/Users/benny/OneDrive/Documents/Github/pycpt-tutorial
printf '%s\n' "$CONDA_PREFIX" "$CPT_BIN_DIR"
```

Activation sets `CPT_BIN_DIR` to the environment's packaged engine at
`/home/bennyistanto/miniforge3/envs/pycpt-tutorial/opt/cpt/bin`.
The existing `.zshrc` custom-CPT exports were left unchanged. Check the effective
variable after activation rather than assuming the shell startup value remains active.

The Jupyter kernel is registered inside this environment as
**Python (PyCPT Tutorial)**. Start `jupyter notebook` from the activated environment.
The original seasonal and subseasonal release notebooks are saved under
`/home/bennyistanto/CPT/pycpt-2.10.4-release`.

## IRI Data Library authentication

The supplied key is configured at `/home/bennyistanto/.pycpt_dlauth` in Debian,
outside the repository and its OneDrive directory. The file is owned by the Debian
user and has mode `0600` (owner read/write only). Installed PyCPT successfully reads
the expected key. This verifies local configuration, not remote dataset permission
or token validity.

PyCPT 2.10.4 reads a JSON object containing a `key` field from this native location.
It does not load an IRI credential from the project's `.env`. The current `.env`
contains comments only, and `.env.example` documents the convention without secrets.
Credential files and `.env` variants are ignored by Git.

For a fresh setup on another machine, use the documented interactive flow in the
[official PyCPT authentication guide](https://iri-pycpt.github.io/authentication/):

```bash
conda activate pycpt-tutorial
python -c 'from cptdl.utilities import setup_dlauth; setup_dlauth("you@example.com")'
chmod 600 ~/.pycpt_dlauth
```

The password is requested interactively. Do not put it or the key in a shell command,
notebook, or project file. The setup function keeps an existing credential file.

To check local configuration without displaying the key:

```bash
python -c 'from cptdl.utilities import read_dlauth; print("Credential configured:", bool(read_dlauth()))'
```

In notebooks, do not leave `read_dlauth()` as a cell's final expression, because
Jupyter would display its return value. Protected downloads must explicitly use
the workflow's authentication setting (`use_dlauth=True`) and the account must
have access to the requested dataset.

## Offline execution check

```bash
python scripts/check_cpt.py --method cca --initialization-coordinates \
  --output /home/bennyistanto/CPT/verification/packaged-cca-with-init
python scripts/check_cpt.py --method pcr --initialization-coordinates \
  --output /home/bennyistanto/CPT/verification/packaged-pcr-with-init
```

Each check uses a deterministic synthetic 2-by-3 grid, 31 training years, and one
forecast year. It checks finite forecasts, correct year alignment, probability
totals, output parsing, and NetCDF writing. It saves a `summary.json`, NetCDF
outputs, and the CPT command/output log under the requested output directory.

Both packaged-engine checks passed on 2026-10-31. They establish a working
CCA/PCR execution path; they do not establish regional forecast skill, complete
CPT feature compatibility, or the full subseasonal workflow.

Initialization coordinate `S` belongs on the predictors in this example. Putting
it on synthetic observations caused an output-date parsing failure during test
development. Explicit seasonal `Ti`/`Tf` coordinates and synchronous predictors
also prevent ambiguous point-date parsing and unintended one-year offsets.

## Building CPT 19.2.6 from the supplied source

The source is at `/home/bennyistanto/CPT/19.2.6`.

Two issues were identified:

1. `sfmakedepend` had CRLF line endings. Its shebang referred to `/usr/bin/perl`
   followed by a carriage return. A backup, `sfmakedepend.crlf-original`, was
   preserved before converting the helper to LF. Dependency regeneration then worked.
2. gfortran 14.2.0 and 13.4.0 crashed while compiling `cpt_file.F95` during
   overloaded-operator resolution. Disabling optimization and increasing the stack
   did not help. gfortran 16.2.0 passed that compilation step.

A third issue was a stale install rule: it requested nonexistent `data/labels.txt`,
while this engine reads `data/labels.toml`. The failed tar command was masked by a
pipeline, so `make install` returned success despite missing required data. The
Makefile was backed up as `Makefile.original` and its install file list was fixed
to include `labels.toml` and `download_CPTDM.txt`.

The relevant build commands are:

```bash
source /home/bennyistanto/miniforge3/etc/profile.d/conda.sh
conda activate cpt-build
cd /home/bennyistanto/CPT/19.2.6
# One-time repair; preserve the original backup if it already exists.
test -e sfmakedepend.crlf-original || cp -p sfmakedepend sfmakedepend.crlf-original
sed -i 's/\r$//' sfmakedepend
test -e Makefile.original || cp -p Makefile Makefile.original
sed -i 's|cpt.ini data/labels.txt data/download_IRIDL.txt CPT.x|cpt.ini data/labels.toml data/download_CPTDM.txt data/download_IRIDL.txt CPT.x|' Makefile
make -B srcdeps
test -e lapack/lapack/make.inc || cp lapack/lapack/make.inc.example lapack/lapack/make.inc
make -C lapack/lapack FC="$FC" lapacklib blaslib
make -o lapack/lapack/liblapack.a -o lapack/lapack/librefblas.a \
  FC="$FC" INSTALL_DIR=/home/bennyistanto/CPT/19.2.6 install
```

When switching compiler versions, clear generated objects/modules with `make clean`
from this exact source directory before rebuilding. Initial compilation includes
the bundled BLAS/LAPACK libraries and takes longer than subsequent builds.

The compiler environment can be recreated from its saved lock file. The installed
`FC` variable supplies the complete compiler path; Debian's system gfortran is
unchanged.

The library-only targets avoid the bundled LAPACK default target's full upstream
test suite. During this installation, that extra test build was stopped after the
required archives had been produced. The archives were reused for linking CPT.
The full LAPACK test suite was not completed.

CPT startup and its About menu confirm version **19.2.6**. Shared libraries resolve
to the `cpt-build` environment, so retain that environment while using this binary.

```bash
conda deactivate
export CPT_BIN_DIR=/home/bennyistanto/CPT/19.2.6/bin
/home/bennyistanto/CPT/19.2.6/bin/CPT.x
```

Enter `711` for About, or `0` to exit. Startup may print benign directory-already-exists
messages from this CPT version.

## CPT 19 is not a drop-in PyCPT engine

Unmodified PyCPT 2.10.4 failed both CCA and PCR when pointed at CPT 19.2.6:

- CPT 19 changed the skill menu. For example, PyCPT sends 15 for below-normal ROC,
  but CPT 19 offers 13 and has no option 15 there. Other changed IDs include 2AFC,
  RMSE, and above-normal ROC.
- After adapting score IDs diagnostically, predictor initialization metadata caused
  another parser mismatch: CPT 19 wrote `cpt:S=2012-09`, while cptio expects a
  complete midnight timestamp.

The standalone engine completed synthetic CCA/PCR forecasts with an in-memory
score-menu adapter and initialization metadata omitted. Those checks establish
working native calculations and output, **not unmodified PyCPT compatibility**.
The diagnostic adapter is in `temp/cpt19-menu-check.py`; it does not patch installed
packages and is not a general CPT 19 integration.

Keep the tutorial environment's default packaged CPT 17.8.3. An official or
separately validated CPT 19 adapter remains future work.

Changing only the crashing menu IDs is insufficient: some older IDs remain valid
in CPT 19 but select different statistics. The [compatibility report](CPT_COMPATIBILITY.md)
records the observed mappings and required checks.

## Verification record

See `environment/verification-2026-10-31.json` for the result matrix and binary
hashes. Detailed outputs remain under `/home/bennyistanto/CPT/verification`.

## Recreate the tutorial environment

Choose an unused environment name rather than overwriting an existing one:

```bash
conda create -n pycpt-tutorial-recreated --file environment/conda-linux-64.lock
```

Creating an environment does not by itself verify data access, credentials, or
scientific workflow behavior. Run the offline checks before trying full notebooks.
