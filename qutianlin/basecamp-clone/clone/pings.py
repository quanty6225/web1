"""Participant-only account conversations, separate from project activity."""
import asyncio
import html as escape
import json
import secrets
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from lxml import html, etree
from local_render import safe_rich_text


def initialize(db):
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS bc_pings(id TEXT PRIMARY KEY,workspace TEXT NOT NULL,title TEXT NOT NULL DEFAULT '',created REAL NOT NULL,updated REAL NOT NULL,archived INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS bc_ping_members(ping TEXT,account TEXT,read_at REAL NOT NULL DEFAULT 0,PRIMARY KEY(ping,account));
        CREATE TABLE IF NOT EXISTS bc_ping_lines(id TEXT PRIMARY KEY,ping TEXT,author TEXT,body TEXT,created REAL,updated REAL,reply TEXT);
        CREATE INDEX IF NOT EXISTS bc_ping_lines_room ON bc_ping_lines(ping,created,id);
        ''')
    from ping_files import initialize as initialize_files
    initialize_files(db)
    from ping_covers import initialize as initialize_covers
    initialize_covers(db)
    from ping_actions import initialize as initialize_actions
    initialize_actions(db)


def participants(c, account, identifier):
    return [dict(row) for row in c.execute('SELECT m.account,a.display_name AS name FROM bc_ping_members m JOIN bc_members w ON w.account=m.account AND w.workspace=? JOIN local_auth_accounts a ON a.account_id=m.account WHERE m.ping=? ORDER BY a.display_name,m.account', (account['workspace_id'],identifier))]


def can_ping(c, account, target):
    members={r['account']:r for r in c.execute('SELECT * FROM bc_members WHERE workspace=?',(account['workspace_id'],))}
    actor=members.get(account['account_id']);other=members.get(target)
    if not actor or not other:return False
    if target==account['account_id'] or actor['role'] in ('owner','admin') or other['role'] in ('owner','admin'):return True
    one=None if actor['access']=='all' else {r['project'] for r in c.execute('SELECT project FROM bc_project_members WHERE workspace=? AND account=?',(account['workspace_id'],account['account_id']))}
    two=None if other['access']=='all' else {r['project'] for r in c.execute('SELECT project FROM bc_project_members WHERE workspace=? AND account=?',(account['workspace_id'],target))}
    return bool(one is None and two is None or one is None and two or two is None and one or one is not None and two is not None and one&two)


def choices(c, account):
    rows=[]
    for person in c.execute('SELECT m.account,a.display_name FROM bc_members m JOIN local_auth_accounts a ON a.account_id=m.account WHERE m.workspace=? ORDER BY a.display_name',(account['workspace_id'],)).fetchall():
        if can_ping(c,account,person['account']):
            rows.append({'value':person['account'],'name':person['display_name'],'type':'person','avatar_url':'/api/avatar.svg?person='+person['account']})
    return rows


def permitted(c, account, identifier):
    if not account or account.get('closed'):return None
    return c.execute('SELECT p.* FROM bc_pings p JOIN bc_ping_members m ON m.ping=p.id AND m.account=? JOIN bc_members w ON w.account=m.account AND w.workspace=p.workspace WHERE p.id=? AND p.workspace=? AND p.archived=0',(account['account_id'],identifier,account['workspace_id'])).fetchone()


def require_ping(c, account, identifier):
    row=permitted(c,account,identifier)
    if not row:raise HTTPException(404,'Ping not found')
    return dict(row)


def title_for(c, account, row):
    if row['title']:return row['title']
    names=[r['name'] for r in participants(c,account,row['id']) if r['account']!=account['account_id']]
    return ', '.join(names) or account['display_name']


def listing(c, account):
    from ping_covers import cover_url
    result=[]
    for row in c.execute('SELECT p.*,m.read_at FROM bc_pings p JOIN bc_ping_members m ON m.ping=p.id AND m.account=? WHERE p.workspace=? AND p.archived=0 ORDER BY p.updated DESC,p.id',(account['account_id'],account['workspace_id'])).fetchall():
        unread=bool(c.execute('SELECT 1 FROM bc_ping_lines WHERE ping=? AND author!=? AND created>? LIMIT 1',(row['id'],account['account_id'],row['read_at'])).fetchone())
        result.append({**dict(row),'title':title_for(c,account,row),'members':participants(c,account,row['id']),'unread':unread,'cover_url':cover_url(c,row['id'])})
    return result


def unreads(c, account):
    return [{'section':'circles','readable':'local-ping-'+row['id'],'identifier':'local-ping:'+account['workspace_id']+':'+row['id']} for row in listing(c,account) if row['unread']]


def render_sidebar(tree, c, account):
    rows=listing(c,account)
    if not rows:return
    for target in tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," sidebar__circles-avatars ")]'):
        for row in rows:
            link=etree.SubElement(target,'a',{'href':'/6302022/my/sidebar/circles/'+row['id'],'class':'sidebar__circle','data-turbo-frame':'sidebar_frame','data-local-ping-link':row['id'],'data-list-navigation-target':'focusable','data-roving-tabindex-target':'focusable'})
            others=[person for person in row['members'] if person['account']!=account['account_id']]
            avatar=(others or row['members'])[0]
            link.set('data-local-ping-avatar',avatar['account'])
            etree.SubElement(link,'img',{'class':'avatar','src':row['cover_url'] or '/api/avatar.svg?person='+avatar['account'],'alt':'','width':'40','height':'40'})
            etree.SubElement(link,'span',{'class':'sidebar__circle-name'}).text=row['title']
            if row['unread']:etree.SubElement(link,'span',{'class':'unread-badge','aria-label':'Unread Ping'}).text='•'
    for node in tree.xpath('//*[contains(@class,"blank-slate--pings")]'):node.getparent().remove(node)
    for node in tree.xpath('//*[@id="sidebar_pings_heading"]'):
        node.text='Pings '
        etree.SubElement(node,'a',{'href':'/6302022/my/sidebar/circles','data-turbo-frame':'sidebar_frame','class':'text-small'}).text='View all'


def line_markup(c, account, row):
    person=c.execute('SELECT display_name FROM local_auth_accounts WHERE account_id=?',(row['author'],)).fetchone()
    name=person['display_name'] if person else 'Member';own=row['author']==account['account_id'];identifier=escape.escape(row['id'],quote=True)
    timestamp=datetime.fromtimestamp(row['created'],timezone.utc)
    quote=json.loads(row['reply']) if row['reply'] else None
    quoted=''
    if quote:quoted='<blockquote data-ping-original="'+escape.escape(quote['id'],quote=True)+'"><strong>'+escape.escape(quote['name'])+'</strong>'+safe_rich_text(quote['body'])+'</blockquote>'
    controls='<button type="button" class="btn btn--sm btn--ghost" data-local-ping-reply="'+identifier+'">Reply</button>'
    if own:controls+='<button type="button" class="btn btn--sm btn--ghost" data-local-chat-edit="'+identifier+'">Edit</button><button type="button" class="btn btn--sm btn--ghost" data-local-chat-delete="'+identifier+'">Delete</button>'
    from ping_actions import markup as action_markup
    menu, reactions = action_markup(c, account, row)
    controls += menu
    from ping_files import markup as attachments
    return '<article id="local_chat_'+identifier+'" tabindex="-1" class="chat-line chat-line--rich-text recording '+('chat-line--me' if own else '')+'" data-recording-id="'+identifier+'" data-local-chat-id="'+identifier+'" data-datetime="'+timestamp.isoformat()+'"><div class="chat-line__avatar"><img class="avatar" src="/api/pings/'+escape.escape(row['ping'],quote=True)+'/people/'+escape.escape(row['author'],quote=True)+'/avatar.svg" alt="'+escape.escape(name,quote=True)+'" width="40" height="40"></div><div class="chat-line__bubble"><span class="chat-line__meta"><strong class="chat-line__author">'+escape.escape(name)+'</strong> <time datetime="'+timestamp.isoformat()+'">'+timestamp.strftime('%H:%M')+'</time>'+controls+'</span><div class="chat-line__body formatted_content">'+quoted+safe_rich_text(row['body'])+attachments(c,row['ping'],row['id'])+'</div>'+reactions+'</div></article>'


def install(app, db, require_user, user, csrf_check, shell, data_root, csrf_token):
    initialize(db);router=APIRouter();peers={}
    async def publish(identifier,event):
        for socket in tuple(peers.get(identifier,set())):
            try:
                account=user(socket)
                with db() as c:
                    if not permitted(c,account,identifier):await socket.close(code=1008);peers.get(identifier,set()).discard(socket);continue
                    output={k:v for k,v in event.items() if k!='row'}
                    if event.get('row'):output['html']=line_markup(c,account,event['row'])
                    if event['type']=='metadata':
                        from ping_covers import cover_url
                        record=require_ping(c,account,identifier)
                        output.update(title=title_for(c,account,record),members=participants(c,account,identifier),cover_url=cover_url(c,identifier))
                await socket.send_json(output)
            except (RuntimeError,WebSocketDisconnect):peers.get(identifier,set()).discard(socket)

    @router.get('/api/pings')
    def index(request:Request):
        account=require_user(request)
        with db() as c:return {'pings':listing(c,account)}

    def page_response(fragment,request,title):
        if request.headers.get('turbo-frame'):
            frame=etree.Element('turbo-frame',id='sidebar_frame');frame.append(fragment)
            return HTMLResponse(html.tostring(frame,encoding='unicode'))
        response=shell(request);tree=html.document_fromstring(response.body.decode());main=tree.xpath('//main')[0]
        for child in list(main):main.remove(child)
        if 'sidebar__chat' in fragment.get('class',''):main.set('class','main-content perma perma--chat perma--circle')
        main.text='';main.append(fragment)
        for node in tree.xpath('//title'):node.text=title
        return HTMLResponse(html.tostring(tree,encoding='unicode'))

    @router.get('/6302022/my/sidebar/circles')
    def all_pings(request:Request):
        account=require_user(request);section=etree.Element('section',{'class':'padding-24'})
        etree.SubElement(section,'a',{'href':'/6302022/my/sidebar/inbox','data-turbo-frame':'sidebar_frame'}).text='Back'
        etree.SubElement(section,'h3').text='Pings'
        with db() as c:
            for row in listing(c,account):
                entry=etree.SubElement(section,'p')
                etree.SubElement(entry,'a',{'href':'/6302022/my/sidebar/circles/'+row['id'],'data-turbo-frame':'sidebar_frame'}).text=row['title']
                if row['unread']:etree.SubElement(entry,'span',{'aria-label':'Unread Ping'}).text=' •'
        return page_response(section,request,'Pings')

    @router.get('/6302022/my/sidebar/circles/{identifier}/edit')
    def edit(identifier:str,request:Request):
        account=require_user(request)
        from ping_view import settings
        from ping_covers import cover_url
        with db() as c:
            record=require_ping(c,account,identifier)
            fragment=settings(identifier,record,participants(c,account,identifier),cover_url(c,identifier))
        return page_response(fragment,request,'Ping settings')

    @router.patch('/api/pings/{identifier}')
    async def update(identifier:str,request:Request):
        account=require_user(request);data=await request.json();csrf_check(request,data)
        title=str(data.get('title','')).strip();selected=data.get('members')
        if len(title)>200:raise HTTPException(422,'Keep the Ping name under 200 characters.')
        if not isinstance(selected,list) or not selected or any(not isinstance(p,str) for p in selected):raise HTTPException(422,'Keep at least one person in this Ping.')
        selected=set(selected)
        with db() as c:
            c.execute('BEGIN IMMEDIATE');require_ping(c,account,identifier)
            existing={p['account'] for p in participants(c,account,identifier)}
            if any(not can_ping(c,account,person) for person in selected-existing):raise HTTPException(422,'Choose someone you can Ping in this account.')
            for person in existing-selected:c.execute('DELETE FROM bc_ping_members WHERE ping=? AND account=?',(identifier,person))
            for person in selected-existing:c.execute('INSERT OR REPLACE INTO bc_ping_members VALUES(?,?,0)',(identifier,person))
            c.execute('UPDATE bc_pings SET title=?,updated=? WHERE id=?',(title,time.time(),identifier))
        await publish(identifier,{'type':'metadata'})
        return {'redirect':'/6302022/my/sidebar/circles/'+identifier if account['account_id'] in selected else '/6302022/my/sidebar/inbox'}

    @router.delete('/api/pings/{identifier}')
    async def archive(identifier:str,request:Request):
        account=require_user(request);csrf_check(request,{})
        with db() as c:
            c.execute('BEGIN IMMEDIATE');require_ping(c,account,identifier)
            c.execute('UPDATE bc_pings SET archived=1,updated=? WHERE id=?',(time.time(),identifier))
        await publish(identifier,{'type':'archived'})
        return {'redirect':'/6302022/my/sidebar/inbox'}

    @router.post('/6302022/my/sidebar/circles')
    async def create(request:Request):
        account=require_user(request);data=await request.json() if 'application/json' in request.headers.get('content-type','') else await request.form();csrf_check(request,data)
        values=data.get('circle[users]','');values=values if isinstance(values,list) else str(values).split(',')
        selected=set(str(value).strip() for value in values if str(value).strip())
        if not selected:raise HTTPException(422,'Choose someone to Ping.')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if any(not can_ping(c,account,person) for person in selected):raise HTTPException(422,'Choose someone you can Ping in this account.')
            selected.add(account['account_id']);identifier=None
            if not data.get('new_group'):
                for row in listing(c,account):
                    if {p['account'] for p in row['members']}==selected:identifier=row['id'];break
            if not identifier:
                identifier=str(800000000000+secrets.randbelow(99999999999));now=time.time()
                c.execute('INSERT INTO bc_pings VALUES(?,?,"",?,?,0)',(identifier,account['workspace_id'],now,now))
                for person in selected:c.execute('INSERT INTO bc_ping_members VALUES(?,?,0)',(identifier,person))
        path='/6302022/my/sidebar/circles/'+identifier
        if 'application/json' in request.headers.get('accept',''):return {'id':identifier,'redirect':path}
        return RedirectResponse(path,303)

    @router.get('/6302022/my/sidebar/circles/group_matches')
    def matches(request:Request):
        account=require_user(request);selected=set(request.query_params.getlist('person_ids[]'));frame=etree.Element('turbo-frame',id='group_ping_matches');target=etree.SubElement(frame,'div',{'data-person-ids':','.join(sorted(selected))})
        with db() as c:
            if any(not can_ping(c,account,person) for person in selected):raise HTTPException(422,'Choose someone you can Ping.')
            for row in listing(c,account):
                if {p['account'] for p in row['members']}==selected|{account['account_id']}:
                    item=etree.SubElement(target,'div',{'class':'sidebar__group-match'});etree.SubElement(item,'a',{'href':'/6302022/my/sidebar/circles/'+row['id'],'data-turbo-frame':'sidebar_frame'}).text=row['title']
        return HTMLResponse(html.tostring(frame,encoding='unicode'))

    @router.get('/api/pings/{identifier}/lines')
    def lines(identifier:str,request:Request):
        account=require_user(request)
        with db() as c:
            require_ping(c,account,identifier)
            return {'lines':[{'id':r['id'],'body':r['body'],'html':line_markup(c,account,r)} for r in c.execute('SELECT * FROM bc_ping_lines WHERE ping=? ORDER BY created,id',(identifier,))]}

    @router.get('/api/pings/{identifier}/people/{person}/avatar.svg')
    def historical_avatar(identifier:str,person:str,request:Request):
        account=require_user(request)
        with db() as c:
            require_ping(c,account,identifier)
            known=c.execute('SELECT 1 FROM bc_ping_members WHERE ping=? AND account=? UNION SELECT 1 FROM bc_ping_lines WHERE ping=? AND author=?',(identifier,person,identifier,person)).fetchone()
            row=c.execute('SELECT display_name FROM local_auth_accounts WHERE account_id=?',(person,)).fetchone()
            if not known or not row:raise HTTPException(404,'Person not found')
        letter=escape.escape(row['display_name'][:1].upper())
        return Response('<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 80 80"><circle cx="40" cy="40" r="40" fill="#4d4d4d"/><text x="40" y="54" text-anchor="middle" font-family="Arial,sans-serif" font-size="43" fill="white">'+letter+'</text></svg>',media_type='image/svg+xml')

    @router.post('/api/pings/{identifier}/read')
    async def read(identifier:str,request:Request):
        account=require_user(request);data=await request.json();csrf_check(request,data)
        with db() as c:
            require_ping(c,account,identifier);c.execute('UPDATE bc_ping_members SET read_at=? WHERE ping=? AND account=?',(time.time(),identifier,account['account_id']))
        return {'read':True}

    @router.post('/api/pings/{identifier}/lines')
    async def send(identifier:str,request:Request):
        account=require_user(request);data=await request.json();csrf_check(request,data)
        from comment_operations import content
        from ping_files import validate,attach,for_line
        files=data.get('files',[])
        body=safe_rich_text(str(data.get('content',''))) if files else content(data.get('content',''))
        if len(body)>100000:raise HTTPException(413,'This message is too long.')
        now=time.time();row={'id':secrets.token_hex(12),'ping':identifier,'author':account['account_id'],'body':body,'created':now,'updated':now,'reply':None}
        with db() as c:
            c.execute('BEGIN IMMEDIATE');require_ping(c,account,identifier)
            files=validate(c,account,identifier,files)
            if data.get('reply_to'):
                original=c.execute('SELECT l.*,a.display_name FROM bc_ping_lines l JOIN local_auth_accounts a ON a.account_id=l.author WHERE l.id=? AND l.ping=?',(data['reply_to'],identifier)).fetchone()
                if not original:raise HTTPException(404,'The original message was not found in this Ping.')
                file_names=''.join('<p>'+escape.escape(f['filename'])+'</p>' for f in for_line(c,identifier,original['id']))
                row['reply']=json.dumps({'id':original['id'],'name':original['display_name'],'body':original['body']+file_names})
            c.execute('INSERT INTO bc_ping_lines VALUES(:id,:ping,:author,:body,:created,:updated,:reply)',row)
            attach(c,files,row['id'])
            c.execute('UPDATE bc_pings SET updated=? WHERE id=?',(now,identifier))
            c.execute('UPDATE bc_ping_members SET read_at=? WHERE ping=? AND account=?',(now,identifier,account['account_id']))
            rendered=line_markup(c,account,row)
        await publish(identifier,{'type':'created','id':row['id'],'row':row})
        return {'type':'created','id':row['id'],'html':rendered}

    @router.api_route('/api/pings/{identifier}/lines/{line}',methods=['PATCH','DELETE'])
    async def change(identifier:str,line:str,request:Request):
        account=require_user(request);data=await request.json() if request.method=='PATCH' else {};csrf_check(request,data)
        with db() as c:
            c.execute('BEGIN IMMEDIATE');require_ping(c,account,identifier)
            record=c.execute('SELECT * FROM bc_ping_lines WHERE id=? AND ping=?',(line,identifier)).fetchone()
            if not record:raise HTTPException(404,'Message not found')
            if record['author']!=account['account_id']:raise HTTPException(403,'You can only change your own messages.')
            if request.method=='DELETE':
                from ping_actions import forget_line
                forget_line(c,identifier,line)
                c.execute('DELETE FROM bc_ping_lines WHERE id=?',(line,));event={'type':'deleted','id':line}
            else:
                from comment_operations import content
                from ping_files import for_line
                body=safe_rich_text(str(data.get('content',''))) if for_line(c,identifier,line) else content(data.get('content',''))
                if len(body)>100000:raise HTTPException(413,'This message is too long.')
                now=time.time();c.execute('UPDATE bc_ping_lines SET body=?,updated=? WHERE id=?',(body,now,line));event={'type':'updated','id':line,'row':{**dict(record),'body':body,'updated':now}}
            c.execute('UPDATE bc_pings SET updated=? WHERE id=?',(time.time(),identifier))
            output={k:v for k,v in event.items() if k!='row'}
            if event.get('row'):output['html']=line_markup(c,account,event['row'])
        await publish(identifier,event);return output

    @router.websocket('/api/pings/{identifier}/live')
    async def live(identifier:str,socket:WebSocket):
        account=user(socket);origin=str(socket.url.replace(path='',query='')).replace('ws:','http:').replace('wss:','https:').rstrip('/')
        with db() as c:allowed=permitted(c,account,identifier)
        if not allowed or socket.headers.get('origin')!=origin:await socket.close(code=1008);return
        await socket.accept();peers.setdefault(identifier,set()).add(socket)
        try:
            while True:
                try:await asyncio.wait_for(socket.receive_text(),timeout=1)
                except asyncio.TimeoutError:pass
                with db() as c:allowed=permitted(c,user(socket),identifier)
                if not allowed:await socket.close(code=1008);break
        except WebSocketDisconnect:pass
        finally:
            peers.get(identifier,set()).discard(socket)
            if not peers.get(identifier):peers.pop(identifier,None)

    @router.get('/6302022/my/sidebar/circles/{identifier}')
    @router.get('/6302022/circles/{identifier}')
    def show(identifier:str,request:Request):
        account=require_user(request)
        from ping_covers import cover_url
        with db() as c:record=require_ping(c,account,identifier);title=title_for(c,account,record);members=participants(c,account,identifier);cover=cover_url(c,identifier)
        from ping_view import conversation
        fragment=conversation(identifier,title,members,account['account_id'],cover)
        return page_response(fragment,request,title)
    from ping_files import install as install_files
    install_files(router,db,require_user,csrf_check,data_root,page_response)
    from ping_covers import install as install_covers
    install_covers(router,db,require_user,csrf_check,data_root,publish)
    from ping_actions import install as install_actions
    install_actions(router,db,require_user,csrf_check,csrf_token,publish)
    app.include_router(router)
