"""Native template UI, owned import, preserved contents and account isolation."""
import asyncio,json,httpx
from pathlib import Path
from playwright.async_api import async_playwright
from local_helpers import actor,BASE
R=Path(__file__).resolve().parents[1];templates=json.loads(((R/'clone' if (R/'clone').is_dir() else R)/'seed/public-templates.json').read_text());checks=[]
async def main():
 c,email,password=actor();other,_,_=actor();uid=c.get('/api/v2/user/status').json()['userId'];anonymous=httpx.Client(base_url=BASE)
 for ident,t in templates.items():
  endpoint='/api/v2/templates/project/'+ident+'/apply';assert anonymous.post(endpoint).status_code==401
  res=c.post(endpoint);assert res.status_code==200,res.text;pid=res.json()['projectId'];batch=c.get('/api/v3/batch/check/0').json();tasks=[x for x in batch['syncTaskBean']['update'] if x['projectId']==pid]
  assert len(tasks)==len(t['metaData']['tasks']);source_ids={x['id'] for x in t['metaData']['tasks']};assert not source_ids&{x['id'] for x in tasks};assert all(x['creator']==uid for x in tasks)
  assert [(x['title'],x.get('content','')) for x in sorted(tasks,key=lambda x:x['sortOrder'])]==[(x['title'],x.get('content') or '') for x in t['metaData']['tasks']]
  assert pid not in {x['id'] for x in other.get('/api/v3/batch/check/0').json()['projectProfiles']};checks.append({'template':ident,'tasks':len(tasks),'owned':True,'isolated':True})
 async with async_playwright() as pw:
  b=await pw.chromium.launch(args=['--no-sandbox']);ctx=await b.new_context();p=await ctx.new_page();errors=[];remote=[]
  p.on('console',lambda e:errors.append(e.text) if e.type=='error' else None);p.on('pageerror',lambda e:errors.append(str(e)));p.on('requestfailed',lambda r:errors.append(r.url+':'+str(r.failure)));p.on('request',lambda r:remote.append(r.url) if r.url.startswith('http') and not r.url.startswith(BASE) else None)
  route='/pub/templates/project/63ff37e4e4b04f30d69e2dcf';await p.goto(BASE+route);await p.get_by_text('保存到我的清单',exact=True).click();await p.wait_for_url('**/signin?dest=**');assert '/templates/project/' in __import__('urllib.parse',fromlist=['unquote']).unquote(p.url)
  await p.get_by_role('textbox',name='Email',exact=True).fill(email);await p.get_by_label('Password',exact=True).fill(password);await p.get_by_role('button',name='Sign In',exact=True).click()
  pending='/templates/project/63ff37e4e4b04f30d69e2dcf/apply';await p.wait_for_url('**/webapp/#p/**',timeout=10000);await p.get_by_text('观后感模板',exact=True).first.wait_for()
  await p.wait_for_load_state('networkidle')
  count=len(c.get('/api/v3/batch/check/0').json()['projectProfiles']);await p.goto(BASE+pending);await p.wait_for_url('**/pub/templates/project/**');assert len(c.get('/api/v3/batch/check/0').json()['projectProfiles'])==count;checks.append({'signin_continuation':'pass','plain_get_does_not_import':'pass'})
  await p.get_by_text('保存到我的清单',exact=True).click();await p.wait_for_url('**/webapp/#p/**');await p.get_by_text('观后感模板',exact=True).first.wait_for();assert not errors,errors;assert not remote,remote;checks.append({'native_save':'pass','anonymous_signin':'pass','runtime_remote_requests':0});await b.close()
 (R/'artifacts/public-templates.json').write_text(json.dumps({'checks':checks,'passed':len(checks)},ensure_ascii=False,indent=2));print('PASS',len(checks),'public template checks')
asyncio.run(main())
