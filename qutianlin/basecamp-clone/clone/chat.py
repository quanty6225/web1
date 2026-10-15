"""Local chat persistence and account-scoped live delivery."""
import asyncio, html, json, secrets, time
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from local_render import safe_rich_text


def line_markup(row, name, editable=True):
    timestamp=datetime.fromtimestamp(row['created'],timezone.utc)
    identifier=html.escape(row['id'],quote=True)
    controls=f'<button type="button" class="btn btn--sm btn--ghost" data-local-chat-edit="{identifier}">Edit</button><button type="button" class="btn btn--sm btn--ghost" data-local-chat-delete="{identifier}">Delete</button>' if editable else ''
    return f'''<article id="local_chat_{identifier}" class="chat-line chat-line--rich-text chat-line--editable recording" data-local-chat-id="{identifier}"><div class="chat-line__avatar"><img class="avatar" src="/api/avatar.svg" width="40" height="40" alt="{html.escape(name,quote=True)}"></div><div class="chat-line__bubble"><span class="chat-line__meta"><strong class="chat-line__author">{html.escape(name)}</strong> <time datetime="{timestamp.isoformat()}">{timestamp:%H:%M}</time>{controls}</span><div class="chat-line__body formatted_content">{safe_rich_text(row['body'])}</div></div></article>'''


def install(app, db, require_user, user, csrf_check, routes):
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS bc_chat_lines(id TEXT PRIMARY KEY, owner TEXT NOT NULL, room TEXT NOT NULL, body TEXT NOT NULL, created INTEGER NOT NULL, updated INTEGER NOT NULL)')
        if 'author' not in {r['name'] for r in c.execute('PRAGMA table_info(bc_chat_lines)')}:c.execute('ALTER TABLE bc_chat_lines ADD COLUMN author TEXT')
        c.execute('UPDATE bc_chat_lines SET author=owner WHERE author IS NULL')
        c.execute('CREATE INDEX IF NOT EXISTS bc_chat_room ON bc_chat_lines(owner,room,created)')
    router=APIRouter();peers={}
    rooms={p.split('/chats/')[1].split('/')[0].split('@')[0].split('?')[0] for p in routes if '/chats/' in p}
    from workspaces import allows
    room_paths={p.split('/chats/')[1].split('/')[0].split('@')[0].split('?')[0]:p for p in routes if '/chats/' in p}
    def permitted(account,room):
        if not account or account.get('closed'):return False
        from trash import erased
        with db() as c:
            if erased(c,account['workspace_id'],room):return False
        if room in rooms:return allows(account,room_paths[room])
        with db() as c:tool=c.execute('SELECT * FROM bc_tools WHERE id=? AND owner=? AND kind="Chat::Transcript" AND active=1',(room,account['workspace_id'])).fetchone()
        return bool(tool and allows(account,'/6302022/projects/'+tool['bucket']))
    def valid_room(room,account):
        if not permitted(account,room):raise HTTPException(403,'You do not have access to this project.')
    async def publish(owner,room,message):
        for socket in tuple(peers.get((owner,room),set())):
            try:
                viewer=user(socket)
                if not permitted(viewer,room) or viewer['workspace_id']!=owner:
                    await socket.close(code=1008);peers.get((owner,room),set()).discard(socket);continue
                outgoing=dict(message)
                if message.get('row'):outgoing['html']=line_markup(message['row'],message['name'],message['row']['author']==viewer['account_id']);outgoing.pop('row',None);outgoing.pop('name',None)
                await socket.send_json(outgoing)
            except (RuntimeError,WebSocketDisconnect):peers.get((owner,room),set()).discard(socket)
    async def revoke_chat_rooms(owner,rooms):
        for room in rooms:
            for socket in tuple(peers.get((owner,room),set())):
                try:await socket.close(code=1008)
                except (RuntimeError,WebSocketDisconnect):pass
    app.state.revoke_chat_rooms=revoke_chat_rooms
    @router.get('/api/chats/{room}/lines')
    async def lines(room:str,request:Request):
        account=require_user(request);valid_room(room,account)
        with db() as c:rows=c.execute('SELECT l.*,a.display_name AS author_name FROM bc_chat_lines l LEFT JOIN local_auth_accounts a ON a.account_id=l.author WHERE owner=? AND room=? ORDER BY created,id',(account['workspace_id'],room)).fetchall()
        return {'lines':[{'id':r['id'],'body':r['body'],'html':line_markup(r,r['author_name'] or 'Member',r['author']==account['account_id'])} for r in rows]}
    @router.post('/api/chats/{room}/lines')
    async def create(room:str,request:Request):
        account=require_user(request);valid_room(room,account);data=await request.json();csrf_check(request,data);body=safe_rich_text(str(data.get('content','')))
        from lxml import html as lhtml
        tree=lhtml.fragment_fromstring(body,create_parent='div')
        if not tree.text_content().strip() and not tree.xpath('.//img'):raise HTTPException(422,'Write a message first.')
        if len(body)>100000:raise HTTPException(413,'This message is too long.')
        row={'id':secrets.token_hex(12),'owner':account['workspace_id'],'author':account['account_id'],'room':room,'body':body,'created':time.time_ns()/1e9,'updated':time.time_ns()/1e9}
        with db() as c:c.execute('INSERT INTO bc_chat_lines(id,owner,room,body,created,updated,author) VALUES(:id,:owner,:room,:body,:created,:updated,:author)',row)
        event={'type':'created','id':row['id'],'html':line_markup(row,account['display_name']),'row':row,'name':account['display_name']};await publish(account['workspace_id'],room,event);return event
    @router.api_route('/api/chats/{room}/lines/{identifier}',methods=['PATCH','DELETE'])
    async def change(room:str,identifier:str,request:Request):
        account=require_user(request);valid_room(room,account);data=await request.json() if request.method=='PATCH' else {};csrf_check(request,data)
        with db() as c:
            row=c.execute('SELECT * FROM bc_chat_lines WHERE id=? AND owner=? AND room=?',(identifier,account['workspace_id'],room)).fetchone()
            if not row:raise HTTPException(404,'Message not found')
            row=dict(row)
            if row['author']!=account['account_id']:raise HTTPException(403,'You can only edit or delete your own messages.')
            if request.method=='DELETE':c.execute('DELETE FROM bc_chat_lines WHERE id=?',(identifier,));event={'type':'deleted','id':identifier}
            else:
                body=safe_rich_text(str(data.get('content','')))
                from lxml import html as lhtml
                if not lhtml.fragment_fromstring(body,create_parent='div').text_content().strip():raise HTTPException(422,'Write a message first.')
                c.execute('UPDATE bc_chat_lines SET body=?,updated=? WHERE id=?',(body,time.time(),identifier));row['body']=body;event={'type':'updated','id':identifier,'html':line_markup(row,account['display_name']),'row':row,'name':account['display_name']}
        await publish(account['workspace_id'],room,event);return event
    @router.websocket('/api/chats/{room}/live')
    async def live(room:str,socket:WebSocket):
        account=user(socket)
        if not permitted(account,room) or socket.headers.get('origin')!=str(socket.url.replace(path='',query='')).replace('ws:','http:').replace('wss:','https:').rstrip('/'):
            await socket.close(code=1008);return
        await socket.accept();key=(account['workspace_id'],room);peers.setdefault(key,set()).add(socket)
        try:
            while True:
                await socket.receive_text()
                viewer=user(socket)
                if not viewer or viewer['workspace_id']!=account['workspace_id'] or not permitted(viewer,room):await socket.close(code=1008);break
        except WebSocketDisconnect:pass
        finally:
            peers.get(key,set()).discard(socket)
            if not peers.get(key):peers.pop(key,None)
    app.include_router(router)
