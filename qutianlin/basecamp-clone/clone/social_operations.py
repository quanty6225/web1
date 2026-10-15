"""Personal boosts and subscriptions attached to local workspace records."""
import re,secrets,time
from fastapi import HTTPException
from record_operations import fields_for

def initialize(db):
 with db() as c:c.execute('CREATE TABLE IF NOT EXISTS bc_boosts(id TEXT PRIMARY KEY,workspace TEXT,author TEXT,recording TEXT,route TEXT,content TEXT,created INTEGER)')
 from thread_notifications import initialize as initialize_threads
 initialize_threads(db)
def mutate(c,account,path,payload,method,referer):
 from column_watching import mutate as mutate_column_subscription
 column_change=mutate_column_subscription(c,account,path,payload,method,referer)
 if column_change:return column_change
 match=re.fullmatch(r'/6302022/buckets/(\d+)/boosts(?:/([a-z0-9]+))?',path)
 if match:
  if match[2]:
   if method!='DELETE':raise HTTPException(405,'Use DELETE to remove a boost.')
   row=c.execute('SELECT * FROM bc_boosts WHERE id=? AND workspace=?',(match[2],account['workspace_id'])).fetchone()
   if not row:raise HTTPException(404,'Boost not found')
   from boost_controls import resolve
   resolve(c,account,match[1],row['recording'],row['route'])
   if row['author']!=account['account_id']:raise HTTPException(403,'You can only remove your own boosts.')
   c.execute('DELETE FROM bc_boost_deliveries WHERE boost=?',(match[2],))
   c.execute('DELETE FROM bc_boosts WHERE id=?',(match[2],));return {'redirect':row['route']}
  content=str(payload.get('boost[content]','')).strip()
  if not content or len(content)>16:raise HTTPException(422,'Write a boost of up to 16 characters.')
  if method!='POST':raise HTTPException(405,'Use POST to add a boost.')
  from boost_controls import identifier as decode_identifier,resolve
  identifier=decode_identifier(str(payload.get('boost[boostable_gid]','')))
  record,comment=resolve(c,account,match[1],identifier,referer);route=record['url']
  if fields_for(c,account['workspace_id'],record).get('_comments_closed'):raise HTTPException(409,'Comments and Boosts are closed on this item.')
  boost=secrets.token_hex(12);now=int(time.time())
  c.execute('INSERT INTO bc_boosts VALUES(?,?,?,?,?,?,?)',(boost,account['workspace_id'],account['account_id'],identifier,route,content,now))
  from boost_reports import enqueue
  enqueue(c,account,record,comment,boost,now)
  return {'redirect':route}
 from thread_notifications import mutate as mutate_subscription
 return mutate_subscription(c,account,path,payload,method)

def render(tree,path,account,c):
 from thread_notifications import render as render_subscriptions
 render_subscriptions(tree,path,account,c)
 from column_watching import render as render_column_subscriptions
 render_column_subscriptions(tree,path,c,account)
 from boost_controls import render as render_boosts
 render_boosts(tree,path,c,account)
