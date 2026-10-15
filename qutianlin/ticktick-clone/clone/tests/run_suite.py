"""Run independent local actors; requires local SMTP and an already running clone."""
from pathlib import Path
import subprocess,sys,json,time,os
R=Path(__file__).resolve().parents[1]
for name in ['artifacts','run']:(R/name).mkdir(exist_ok=True)
names=['auth_backend','auth_edges','email_link','account_data','payments_backend','collaboration_backend','files_calendar','gifts_and_shared_files','security_workflow','browser_workflow','settings_workflow','collaboration_browser','focus_browser','statistics_calendar','private_public_pages','homepage_media','transient_states','public_templates','blog_workflow']
results=[]
for name in names:
 started=time.time()
 with (R/'run'/(name+'-suite.log')).open('w') as f:
  result=subprocess.run([sys.executable,str(R/'tests'/(name+'.py'))],cwd=R,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},stdout=f,stderr=subprocess.STDOUT,timeout=180)
 results.append({'test':name,'exit_code':result.returncode,'elapsed_seconds':round(time.time()-started,2)});print(name,result.returncode,flush=True)
(R/'artifacts/regression-suite.json').write_text(json.dumps({'tests':results,'passed':sum(r['exit_code']==0 for r in results),'total':len(results)},indent=2))
assert all(r['exit_code']==0 for r in results),results
