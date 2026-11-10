"""Run an extracted tutorial kit using the current analysis-only interpreter.

Requires preparation.json from the fresh-install audit. Never executes or writes
the canonical notebook. The kernel spec explicitly selects this interpreter;
user kernels and the full PyCPT environment are not used.
"""
from pathlib import Path
from datetime import date
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import sys
import time

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager
import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'research/audits/analysis-environment'
BLOCKED = ['pycpt', 'cptcore', 'cptio', 'cptdl', 'cptextras', 'cptbin']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    prep = json.loads((AUDIT / 'preparation.json').read_text())
    work = Path(prep['work'])
    prefix = Path(prep['environment_prefix'])
    assert Path(sys.prefix).resolve() == prefix.resolve()
    assert sys.flags.no_user_site, 'Run this verifier with python -s.'
    assert all(importlib.util.find_spec(name) is None for name in BLOCKED)
    packages = [json.loads(p.read_text()) for p in sorted((prefix / 'conda-meta').glob('*.json'))]
    forbidden = [p['name'] for p in packages if p['name'] in BLOCKED or p['name'].startswith('cpt')]
    assert not forbidden, forbidden
    assert not any(p.name.lower() in ('cpt', 'cpt.x', 'cpt.exe') for p in (prefix / 'bin').iterdir())
    kit = ROOT / 'docs/downloads/indonesia-seasons-2023-kit.zip'
    assert sha(kit) == prep['kit_sha256']
    canonical = ROOT / 'docs/notebooks/indonesia-seasons-2023.ipynb'
    assert sha(canonical) == prep['canonical_notebook_sha256']
    source = work / 'docs/notebooks/indonesia-seasons-2023.ipynb'
    assert sha(source) == sha(canonical)
    inputs_before = {str(p.relative_to(work)): sha(p) for p in sorted((work / 'docs/data').rglob('*')) if p.is_file()}
    nb = nbformat.read(source, as_version=4)
    original_code = [c for c in nb.cells if c.cell_type == 'code']
    assert len(original_code) == 22
    assert 'RERUN_CPT = False' in next(c.source for c in original_code if c.id == 'optional-rerun')

    guard = r'''
import sys, os, json, importlib.util, importlib.abc, shutil
from pathlib import Path
_blocked = {'pycpt','cptcore','cptio','cptdl','cptextras','cptbin'}
_availability = {name: importlib.util.find_spec(name) is not None for name in sorted(_blocked)}
assert not any(_availability.values()), _availability
assert sys.flags.no_user_site
assert os.environ.get('CPT_BIN_DIR') is None
assert not any(shutil.which(name) for name in ['CPT','cpt','CPT.x','cpt.x'])
_attempts = {'subprocess':0,'credential_read':0,'remote_network':0}
_system_queries = []
class _NoPyCPT(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in _blocked:
            raise ModuleNotFoundError('PyCPT packages absent/disabled during analysis-only verification')
sys.meta_path.insert(0, _NoPyCPT())
def _offline_audit(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes)):
        name = str(args[0]).lower()
        if 'dlauth' in name or '.iridlauth' in name or Path(name).name == '.env':
            _attempts['credential_read'] += 1
            raise RuntimeError('Credential access disabled')
    if event in ('socket.connect', 'socket.getaddrinfo'):
        address = args[1] if event == 'socket.connect' else args[0]
        host = address[0] if isinstance(address, tuple) else address
        if str(host) not in ('127.0.0.1', '::1', 'localhost'):
            _attempts['remote_network'] += 1
            raise RuntimeError('Remote network disabled')
    if event == 'subprocess.Popen':
        command = Path(str(args[0])).name
        # Matplotlib queries fonts; NumPy.testing queries local CPU capabilities.
        if command in ('fc-list', 'fc-match') or (command == 'lscpu' and args[1] == ['lscpu']):
            _system_queries.append(command)
        else:
            _attempts['subprocess'] += 1
            raise RuntimeError('External processes disabled')
    if event in ('os.system', 'os.posix_spawn'):
        _attempts['subprocess'] += 1
        raise RuntimeError('External processes disabled')
sys.addaudithook(_offline_audit)
try:
    __import__('cptcore')
except ModuleNotFoundError:
    _import_guard_tested = True
else:
    raise AssertionError('Import guard ineffective')
print('Fresh analysis-only interpreter; credentials and remote access disabled.')
'''
    result_cell = '''
assert not any(n.split('.')[0] in _blocked for n in sys.modules)
assert all(v == 0 for v in _attempts.values()), _attempts
print(json.dumps({'interpreter':sys.executable,'prefix':sys.prefix,
 'pycpt_modules_available':_availability,'loaded_pycpt_modules':[],
 'attempts':_attempts,'permitted_local_system_queries':_system_queries,
 'import_guard_negative_control':_import_guard_tested}))
'''
    nb.cells.insert(0, nbformat.v4.new_code_cell(guard, id='analysis-only-guard'))
    nb.cells.append(nbformat.v4.new_code_cell(result_cell, id='analysis-only-result'))
    kernels = work / '.analysis-kernels'
    spec = kernels / 'fresh-analysis'
    spec.mkdir(parents=True, exist_ok=True)
    (spec / 'kernel.json').write_text(json.dumps({
        'argv': [sys.executable, '-s', '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
        'display_name': 'Fresh tutorial analysis audit', 'language': 'python'}))
    km = KernelManager(kernel_name='fresh-analysis', kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(kernels)]))
    env = {k: v for k, v in os.environ.items() if not any(t in k.upper() for t in ('CPT', 'IRIDL', 'DLAUTH'))}
    env.pop('PYTHONPATH', None)
    env.update(PYTHONNOUSERSITE='1', PATH=f'{prefix}/bin:/usr/bin:/bin',
               MPLCONFIGDIR=str(work / '.matplotlib-cache'), IPYTHONDIR=str(work / '.ipython'))
    started = time.monotonic()
    try:
        NotebookClient(nb, km=km, timeout=240, resources={'metadata': {'path': str(work)}}).execute(env=env)
    finally:
        if km.has_kernel:
            km.shutdown_kernel(now=True)
    assert not any(o.output_type == 'error' for c in nb.cells if c.cell_type == 'code' for o in c.outputs)
    nbformat.write(nb, work / 'executed-analysis-only.ipynb')
    payload = json.loads(''.join(o.text for o in nb.cells[-1].outputs if o.output_type == 'stream'))
    assert Path(payload['prefix']).resolve() == prefix.resolve()

    checks = {'netcdf': [], 'csv': [], 'findings': [], 'include': []}
    for actual in sorted((work / 'docs/assets/seasonal-2023').iterdir()):
        expected = ROOT / actual.relative_to(work)
        assert expected.exists(), actual.name
        if actual.suffix == '.nc':
            with xr.open_dataset(actual) as opened: got = opened.load()
            with xr.open_dataset(expected) as opened: want = opened.load()
            xr.testing.assert_allclose(got, want, rtol=1e-12, atol=1e-8)
            assert got.attrs == want.attrs
            assert all(got[n].attrs == want[n].attrs for n in got.variables)
            checks['netcdf'].append(actual.name)
        elif actual.suffix == '.csv':
            pd.testing.assert_frame_equal(pd.read_csv(actual), pd.read_csv(expected), check_exact=False, rtol=1e-12, atol=1e-8)
            checks['csv'].append(actual.name)
        elif actual.suffix == '.json':
            assert json.loads(actual.read_text()) == json.loads(expected.read_text())
            checks['findings'].append(actual.name)
    for actual in sorted((work / 'docs/_includes').glob('*')):
        assert actual.read_bytes() == (ROOT / actual.relative_to(work)).read_bytes(), actual.name
        checks['include'].append(actual.name)
    assert checks['netcdf'] and checks['csv'] and checks['findings'] and checks['include']
    assert all(sha(work / path) == value for path, value in inputs_before.items())
    assert sha(canonical) == prep['canonical_notebook_sha256']
    record = {'date': date.today().isoformat(), 'result': 'PASS', **prep,
              'elapsed_execution_seconds': round(time.monotonic() - started, 1),
              'python': platform.python_version(), 'platform': platform.platform(),
              'original_code_cells_executed': 22, 'guard_cells': 2,
              'package_count': len(packages), 'forbidden_conda_packages': forbidden,
              'input_files_unchanged': len(inputs_before), 'canonical_notebook_unchanged': True,
              'numerical_tolerances': {'atol': 1e-8, 'rtol': 1e-12},
              'output_checks': checks, 'kernel_evidence': payload,
              'scope': 'Fresh Debian/Linux x86-64 conda environment from kit YAML; existing WSL distribution. No CPT fit or new data download. Guarded execution permits loopback kernel traffic, font and CPU queries only.'}
    (AUDIT / 'execution.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
