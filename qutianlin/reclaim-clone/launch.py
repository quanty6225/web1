#!/usr/bin/env python3
"""Start this independent clone with a local data directory."""
import json,os,runpy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SITE=ROOT.name.removesuffix('-clone')
CLONE=ROOT/'clone'
os.chdir(CLONE)
sys.path[:0]=[str(CLONE/'vendor'),str(CLONE)]
runtime=CLONE/'backend/runtime.json'
if not runtime.exists():runtime=ROOT/'backend/runtime.json'
data=Path(os.environ.get('DATA_DIR',ROOT/'data')).resolve()
data.mkdir(parents=True,exist_ok=True)
os.environ.setdefault('WEBSITEBENCH_SITE_BACKEND_RUNTIME',str(runtime))
os.environ.setdefault('WEBSITEBENCH_SITE_BACKEND_DATABASE',str(data/json.loads(runtime.read_text())['database']['filename']))
os.environ.setdefault(SITE.upper()+'_DATA_DIR',str(data))
os.environ.setdefault('WEBSITEBENCH_SMTP_HOST','127.0.0.1')
os.environ.setdefault('WEBSITEBENCH_SMTP_PORT','1025')
os.environ.setdefault('WEBSITEBENCH_SMTP_FROM','no-reply@'+SITE+'.clone.test')
os.environ.setdefault('PORT',str(18200))
os.environ.setdefault('BASE_URL','http://127.0.0.1:'+os.environ['PORT'])
if SITE=='ifttt':runpy.run_path(str(CLONE/'app.py'),run_name='__main__')
else:
    import uvicorn
    module='server' if SITE in ('linear','reclaim') else 'app'
    uvicorn.run(module+':app',host=os.environ.get('HOST','127.0.0.1'),port=int(os.environ['PORT']),access_log=False)
