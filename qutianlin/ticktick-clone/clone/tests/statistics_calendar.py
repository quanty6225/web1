"""Exercise real counters, ownership and calendar-file browser import."""
import asyncio,json,secrets,datetime
from pathlib import Path
from local_helpers import actor,BASE
from playwright.async_api import async_playwright
async def main():
 c,_,_=actor();other,_,_=actor();passed=[];today=datetime.datetime.now(datetime.timezone.utc);stamp=int(today.strftime('%Y%m%d'))
 ranking=c.get('/api/v3/user/ranking').json();assert ranking['taskCount']==0 and ranking['projectCount']==0
 pid=c.post('/api/v2/project',json={'name':'Statistics test'}).json()['id'];tid=secrets.token_hex(12)
 assert c.post('/api/v2/batch/task',json={'add':[{'id':tid,'projectId':pid,'title':'Completed local work','status':2,'completedTime':today.isoformat()}]}).is_success
 stats=c.get('/api/v2/statistics/general').json();assert stats['totalCompleted']==1 and stats['todayCompleted']==1;assert other.get('/api/v2/statistics/general').json()['totalCompleted']==0
 assert c.get('/api/v3/user/ranking').json()['taskCount']==1;passed.append('Owned task completion counters exclude starter creation counts')
 hid=secrets.token_hex(12);assert c.post('/api/v2/habits/batch',json={'add':[{'id':hid,'name':'Daily habit','goal':1}]}).is_success
 assert c.post('/api/v2/habitCheckins/batch',json={'add':[{'id':secrets.token_hex(12),'habitId':hid,'checkinStamp':stamp,'status':1}]}).is_success
 week=c.get('/api/v2/habits/statistics/week/current').json();assert len(week)==7 and week[str(stamp)]['completedHabitCount']==1;assert other.get('/api/v2/habits/statistics/week/current').json()[str(stamp)]['completedHabitCount']==0;passed.append('Weekly habit results use seven dated buckets with account isolation')
 async with async_playwright() as pw:
  b=await pw.chromium.launch(args=['--no-sandbox']);ctx=await b.new_context();await ctx.add_cookies([{'name':'ticktick_local_session','value':c.cookies.get('ticktick_local_session'),'url':BASE}]);p=await ctx.new_page();errors=[];external=[]
  p.on('pageerror',lambda e:errors.append(str(e)));p.on('response',lambda r:errors.append(str(r.status)+' '+r.url) if r.status>=400 else None);p.on('request',lambda r:external.append(r.url) if not r.url.startswith((BASE+'/','data:','blob:')) else None)
  await p.goto(BASE+'/webapp/#statistics');await p.wait_for_timeout(2000);body=await p.locator('body').inner_text();assert 'Total Completion' in body and 'Invalid date' not in body;passed.append('Statistics screen renders real task and dated habit data')
  await p.goto(BASE+'/local/calendar/google');ics=b'BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nSUMMARY:Imported appointment\r\nDTSTART:20261020T120000Z\r\nDTEND:20261020T123000Z\r\nDESCRIPTION:First line\\nSecond line\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n'
  await p.locator('input[type=file]').set_input_files({'name':'calendar.ics','mimeType':'text/calendar','buffer':ics});await p.get_by_role('button',name='Import',exact=True).click();await p.get_by_text('Imported 1 events into your local account.',exact=True).wait_for();await p.get_by_role('link',name='Open imported events').click();await p.get_by_text('Imported appointment',exact=True).wait_for()
  tasks=c.get('/api/v3/batch/check/0').json()['syncTaskBean']['update'];task=next(t for t in tasks if t['title']=='Imported appointment');assert task['startDate']=='2026-10-20T12:00:00+00:00' and task['content']=='First line\nSecond line';assert not any(t['title']=='Imported appointment' for t in other.get('/api/v3/batch/check/0').json()['syncTaskBean']['update']);passed.append('Calendar browser import preserves UTC dates and isolates imported events')
  await b.close()
 assert not errors and not external,(errors,external)
 Path('artifacts/statistics-calendar.json').write_text(json.dumps({'passed':passed,'errors':errors,'external':external},indent=2));print('PASS',len(passed),passed)
asyncio.run(main())
