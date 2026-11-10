"""Isolated executable compatibility checks with all I/O and fitting stubbed."""
import ast
import datetime as dt
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
from unittest.mock import patch

import cptdl.utilities as utilities
import numpy as np
import xarray as xr

ROOT=Path(__file__).resolve().parents[2]
AUDIT=ROOT/'research/audits/subseasonal-readiness'
source_path=Path(metadata.distribution('pycpt').locate_file('pycpt/subseasonal.py'))
tree=ast.parse(source_path.read_text())
notes=json.loads((AUDIT/'source-inventory.json').read_text())
templates=notes['installed_sources']['pycpt/subseasonal.py']['templates']
calls=[]
def capture_download(*args,**kwargs):
    calls.append({'keyword_names':sorted(kwargs),'use_dlauth':kwargs.get('use_dlauth')})
    return utilities.download(*args,**kwargs)
def forbidden_fit(*args,**kwargs):
    raise AssertionError('A fit must not run during readiness checks')
environment={'dl':SimpleNamespace(download=capture_download),'hindcasts':templates['hindcasts'],
             'xr':xr,'np':np,'cc':SimpleNamespace(canonical_correlation_analysis=forbidden_fit,deterministic_skill=forbidden_fit)}
for name in ['download_hindcasts','evaluate_models']:
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(source_path),'exec'),environment)
result={'date':'2026-11-02','source_sha256':hashlib.sha256(source_path.read_bytes()).hexdigest(),
        'network_requests':0,'fits_run':0,'installed_packages_modified':False,'checks':{}}
with tempfile.TemporaryDirectory(dir=ROOT/'temp',prefix='subseasonal-driver-') as work:
    root=Path(work)
    args={'filetype':'cptv10.tsv','fdate':dt.datetime(2023,6,1),'training_season':'May-Jul',
          'leads':[('Week 2',8,14)],'predictor_extent':{'west':94,'east':143,'south':-12,'north':7}}
    with patch.object(utilities,'simple_download',return_value='no-file-needed'),patch.object(utilities.cio,'open_cptdataset',return_value=object()):
        try:environment['download_hindcasts'](['GEFSv12.PRCP'],args,root,True)
        except KeyError as exc:
            assert exc.args==('target',)
            result['checks']['fresh_download']={'exception':'KeyError','missing_keyword':'target','actual_download_call':calls[-1]}
        else:raise AssertionError('Expected missing seasonal target check')
    data=xr.Dataset(coords={'model':['GEFSv12.PRCP'],'lead_name':['Week 2']})
    for method,exception in [('PCR',Exception),('None',UnboundLocalError)]:
        try:environment['evaluate_models'](data,data,data,method,{},root)
        except exception as exc:
            if method=='PCR':assert str(exc)=='PCR not yet implemented for subseasonal'
            result['checks'][method]={'exception':type(exc).__name__,'message':str(exc)}
        else:raise AssertionError('Expected unsupported branch')
result['interpretation']='These exercise actual installed function bodies with network/parser/fitter boundaries stubbed. They do not validate fitted results or real data parsing.'
(AUDIT/'driver-checks.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
