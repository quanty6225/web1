"""Read-only previews of authorized local entities and retained source URL metadata."""
import json,re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from fastapi import Request
from chat_markdown import render

CATALOG=json.loads((Path(__file__).parent/'static/chat-link-previews.json').read_text())

class Links(HTMLParser):
    def __init__(self, text):
        super().__init__();self.urls=[];self.feed(render(text))
    def handle_starttag(self, tag, attrs):
        if tag=='a':
            url=dict(attrs).get('href','')
            if url.startswith('/outbound?'):
                url=parse_qs(urlsplit(url).query).get('url',[''])[0]
            if url and url not in self.urls:self.urls.append(url)


def entity(url):
    try:parsed=urlsplit(url)
    except ValueError:return None
    if parsed.scheme and parsed.scheme not in ['http','https']:return None
    if parsed.hostname in ['localhost','127.0.0.1','::1']:
        try:
            if parsed.port not in range(18150,18160):return None
        except ValueError:return None
    if parsed.netloc and not (parsed.hostname in ['localhost','127.0.0.1','::1'] or parsed.hostname and parsed.hostname.endswith('.teamwork.com')):return None
    path=parsed.fragment if parsed.fragment.startswith('/') else parsed.path
    match=re.match(r'^/(?:app/)?(tasks|projects|tasklists|notebooks|milestones|files|comments|messages|people)/([^/?#]+)',path)
    if not match:return None
    kinds={'tasks':'task','projects':'project','tasklists':'list','notebooks':'notebook','milestones':'milestone','files':'file','comments':'comment','messages':'message','people':'person'}
    return kinds[match[1]],match[2]


def teamwork_card(ws, kind, ident):
    typ='tasklist' if kind=='list' else kind
    missing={'kind':'teamwork','type':typ,'status':'no-access'}
    if kind=='task':
        task=next((t for t in ws['tasks'] if t['id']==ident),None)
        if not task:return missing
        project=next((p for p in ws['projects'] if p['id']==task['project_id']),{})
        parent=next((t for t in ws['tasks'] if t['id']==task.get('parent_id')),None)
        assigned='You' if ws['account']['account_id'] in task.get('assignee_ids',[]) else task.get('assignee') or 'Anyone'
        fields=([('Parent task',parent['title'],'/app/tasks/'+parent['id'])] if parent else [])
        fields += [('Tasklist',task.get('list_name'),'/app/projects/'+task['project_id']+'/tasks/list'),('Priority',task.get('priority')),('Assigned',assigned),('Due date',task.get('due_date'))]
        return {'kind':'teamwork','type':typ,'status':'loaded','title':task['title'],'subtitle':project.get('name',''),'url':'/app/tasks/'+ident,'fields':[field for field in fields if field[1]],'completed':bool(task['completed']),'comments':sum(r['kind']=='comment' and r['parent']==ident for r in ws['records'])}
    if kind=='project':
        project=next((p for p in ws['projects'] if p['id']==ident),None)
        if not project:return missing
        fields=[('Description',project.get('description')),('Start date',project.get('start_date')),('End date',project.get('end_date'))]
        return {'kind':'teamwork','type':typ,'status':'loaded','title':project['name'],'subtitle':project.get('company',''),'url':'/app/projects/'+ident+'/tasks/list','fields':[(k,v) for k,v in fields if v]}
    if kind=='person':
        person=next((p for p in ws['people'] if p['id']==ident),None)
        if person:return {'kind':'teamwork','type':typ,'status':'loaded','title':person['name'],'subtitle':person['email'],'url':'/app/people','fields':[]}
    record=next((r for r in ws['records'] if r['kind']==kind and r['id']==ident),None)
    if not record:return missing
    data=record['data'];project=next((p for p in ws['projects'] if p['id']==record['parent']),{})
    title=data.get('title') or data.get('name') or data.get('text','')
    parent_task=next((t for t in ws['tasks'] if t['id']==record['parent']),None)
    pid=parent_task['project_id'] if parent_task else record['parent']
    section={'list':'tasks/list','notebook':'notebooks','milestone':'milestones','file':'files','comment':'comments','message':'messages','person':'people'}[kind]
    target='/app/tasks/'+parent_task['id'] if kind=='comment' and parent_task else '/app/projects/'+pid+'/'+section
    target=('/api/files/'+ident) if kind=='file' else target+'#record-'+ident
    return {'kind':'teamwork','type':typ,'status':'loaded','title':title,'subtitle':project.get('name',''),'url':target,'fields':[(k,v) for k,v in [('Description',data.get('description') or data.get('body') or data.get('text')),('Due date',data.get('due_date'))] if v]}


def install(app,db,identity,workspace):
    from chat_local import channel
    from fastapi import HTTPException
    @app.get('/api/chat/messages/{mid}/cards')
    def cards(mid:str,req:Request):
        with db() as c:
            who,actor=identity(req,c)
            message=c.execute('SELECT * FROM tw_chat_messages WHERE owner=? AND id=?',(who,mid)).fetchone()
            if not message:raise HTTPException(404,'Message not found.')
            channel(c,who,actor,message['channel'])
            import chat_conversations
            if message['created']<=chat_conversations.cutoff(c,who,message['channel'],actor):raise HTTPException(404,'Message not found.')
            urls=Links(message['body']).urls
        entities=[entity(url) for url in urls]
        target=next((row for row in entities if row),None)
        if target:return {'cards':[teamwork_card(workspace(req),*target)]}
        for url in urls:
            value=CATALOG.get(url.rstrip('/') or '/')
            if value:return {'cards':[{'kind':'url',**value}]}
        return {'cards':[]}
