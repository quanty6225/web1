"""Per-person Card Table views synchronized with the native preference cookie."""
from urllib.parse import quote
from fastapi import APIRouter,HTTPException,Request
import workspaces
from card_table import columns_for,is_special,parent_columns

COOKIE='kanban_collapsed_columns_6302022'

def available(c,account):
 columns=columns_for(c,account['workspace_id']);parents=parent_columns(columns)
 return {identifier:column for identifier,column in columns.items() if not column.get('deleted') and not is_special(column) and identifier not in parents and workspaces.allows(account,column['board'])}

def apply_cookie(response,c,account,secure=False):
 visible=available(c,account)
 collapsed=[row['column_id'] for row in c.execute('SELECT column_id FROM bc_column_views WHERE workspace=? AND account=? AND collapsed=1 ORDER BY column_id',(account['workspace_id'],account['account_id'])) if row['column_id'] in visible]
 # The captured native controller reads decodeURIComponent(document.cookie).
 response.set_cookie(COOKIE,quote(','.join(collapsed),safe=''),path='/',samesite='lax',secure=secure,max_age=30*86400)

def install(app,db,require_user,csrf_check):
 with db() as c:c.execute('CREATE TABLE IF NOT EXISTS bc_column_views(workspace TEXT NOT NULL,account TEXT NOT NULL,column_id TEXT NOT NULL,collapsed INTEGER NOT NULL CHECK(collapsed IN (0,1)),PRIMARY KEY(workspace,account,column_id))')
 router=APIRouter()
 def resolve(c,account,identifier):
  if account.get('closed'):raise HTTPException(403,'This account has closed.')
  columns=columns_for(c,account['workspace_id']);column=columns.get(identifier)
  if not column or column.get('deleted'):raise HTTPException(404,'Column not found.')
  if not workspaces.allows(account,column['board']):raise HTTPException(403,'You do not have access to this project.')
  if is_special(column) or identifier in parent_columns(columns):raise HTTPException(409,'This column cannot be collapsed.')
  return column
 @router.get('/api/card-columns/{identifier}/view')
 def view(identifier:str,request:Request):
  account=require_user(request)
  with db() as c:
   resolve(c,account,identifier);row=c.execute('SELECT collapsed FROM bc_column_views WHERE workspace=? AND account=? AND column_id=?',(account['workspace_id'],account['account_id'],identifier)).fetchone()
  return {'column_id':identifier,'collapsed':bool(row['collapsed']) if row else False}
 @router.post('/api/card-columns/{identifier}/view')
 async def change(identifier:str,request:Request):
  account=require_user(request);data=await request.json();csrf_check(request,data)
  if not isinstance(data.get('collapsed'),bool):raise HTTPException(422,'Choose a collapsed or expanded view.')
  with db() as c:
   resolve(c,account,identifier)
   # Viewers may change their own view; no shared project data is changed.
   c.execute('INSERT INTO bc_column_views VALUES(?,?,?,?) ON CONFLICT(workspace,account,column_id) DO UPDATE SET collapsed=excluded.collapsed',(account['workspace_id'],account['account_id'],identifier,int(data['collapsed'])))
  return {'column_id':identifier,'collapsed':data['collapsed']}
 app.include_router(router)
