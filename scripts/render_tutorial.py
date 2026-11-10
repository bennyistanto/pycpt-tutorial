"""Render in an isolated Linux scratch copy, avoiding locked OneDrive Quarto caches."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import re


def strip_unused_static_widget_bootstrap(source,book):
    """Quarto1.8.27 treats any text/html output as a JS widget, even plain tables.

    Static PNG/table notebooks do not need its CDN jQuery/RequireJS bootstrap.
    Leave unknown/interactive MIME types, widget metadata and scripted HTML alone.
    Only the generated HTML changes; notebooks and their saved outputs stay intact.
    """
    removed={}
    for path in [p for folder in ('notebooks','learn') for p in (source/folder).glob('*.ipynb')]:
        nb=json.loads(path.read_text());safe=not nb.get('metadata',{}).get('widgets')
        for cell in nb['cells']:
            for output in cell.get('outputs',[]):
                data=output.get('data',{})
                if set(data)-{'text/plain','text/html','image/png'}:safe=False
                html=data.get('text/html','');html=''.join(html) if isinstance(html,list) else html
                if re.search(r'<script\b|<iframe\b|<object\b|<embed\b|\bon\w+\s*=|javascript:',html,re.I):safe=False
        if not safe:continue
        rendered=book/path.parent.name/path.with_suffix('.html').name
        if not rendered.exists():continue
        text=rendered.read_text()
        text,n=re.subn(r'<script\b[^>]*\bsrc="https://cdn\.jsdelivr\.net/npm/(?:jquery@3\.5\.1/dist/jquery\.min\.js|requirejs@2\.3\.6/require\.min\.js)"[^>]*></script>','',text)
        text,m=re.subn(r'<script type="application/javascript">define\(\x27jquery\x27, \[\],function\(\) \{return window\.jQuery;\}\)</script>','',text)
        if n or m:rendered.write_text(text);removed[str(rendered.relative_to(book))]=n+m
    return removed

ROOT=Path(__file__).resolve().parents[1]


def main():
    stage=Path(tempfile.mkdtemp(prefix='pycpt-quarto-'))
    source=ROOT/'docs'
    # A concurrent preview can create/remove generated *_files directories while
    # the source is copied. They are rebuilt in the isolated render, not inputs.
    shutil.copytree(source,stage/'docs',ignore=shutil.ignore_patterns('_book','.quarto','.jupyter_cache','__pycache__','*_files'))
    env=os.environ.copy();env['QUARTO_PYTHON']=sys.executable
    subprocess.run(['quarto','render',str(stage/'docs')],check=True,env=env)
    static_removed=strip_unused_static_widget_bootstrap(stage/'docs',stage/'docs/_book')
    shutil.copytree(stage/'docs/_book',source/'_book',dirs_exist_ok=True)
    record={'scratch_directory':str(stage),'output':'docs/_book','renderer':subprocess.check_output(['quarto','--version'],text=True).strip(),
            'reason':'Isolate generated Quarto cache from OneDrive/Windows file locks; source data and executed notebook are read-only copies.',
            'story_sha256':hashlib.sha256((source/'_book/chapters/indonesia-seasons-2023.html').read_bytes()).hexdigest(),
            'unused_static_widget_bootstrap_removed':static_removed}
    audit=ROOT/'temp/audits/interactive-story';audit.mkdir(parents=True,exist_ok=True)
    (audit/'render.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))


if __name__=='__main__':main()
