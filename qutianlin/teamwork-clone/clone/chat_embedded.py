"""Authorized Embedded Chat summary and bulk read state for the Projects host."""
import time
from fastapi import HTTPException, Query, Request
import chat_settings,chat_users,chat_conversations,chat_delivery,chat_hooks
from chat_markdown import render as markdown


def install(app,db,owner,account):
    from chat_local import channels,project_access
    def identity(req,c):
        who=owner(req);actor=account(req)['account_id']
        if not chat_users.enabled(c,who,actor):raise HTTPException(403,'Your access to Teamwork Chat has been removed.')
        return who,actor
    @app.get('/api/chat/embedded')
    def summary(req:Request,project:str=Query('',max_length=100)):
        with db() as c:
            who,actor=identity(req,c);rooms=channels(c,who,actor);result=[]
            for room in rooms:
                if not room['joined']:continue
                last_read=c.execute('SELECT last_read FROM tw_chat_members WHERE owner=? AND channel=? AND actor=?',(who,room['id'],actor)).fetchone()[0]
                cutoff=chat_conversations.cutoff(c,who,room['id'],actor)
                unread=c.execute("SELECT * FROM tw_chat_messages WHERE owner=? AND channel=? AND created>? AND author!=? AND kind!='system' ORDER BY created,id",(who,room['id'],max(last_read,cutoff),actor)).fetchall()
                important=sum(room['kind']=='pair' or chat_delivery.important(c,who,room['id'],actor,m['id']) for m in unread)
                newest=c.execute('SELECT * FROM tw_chat_messages WHERE owner=? AND channel=? AND created>? ORDER BY created DESC,id DESC LIMIT 1',(who,room['id'],cutoff)).fetchone()
                latest=None
                if newest:
                    user=c.execute('SELECT display_name FROM local_auth_accounts WHERE account_id=?',(newest['author'],)).fetchone()
                    latest={'id':newest['id'],'body_html':markdown(newest['body']),'created':newest['created'],'author':newest['author'],'name':chat_hooks.author(c,who,newest['id']) or (user[0] if user else 'Former member')}
                result.append({**room,'unread_count':len(unread),'important_count':important,'latest':latest})
            context=None
            if project and project_access(c,who,actor,project):
                record=c.execute('SELECT name FROM tw_projects WHERE owner=? AND id=?',(who,project)).fetchone()
                linked=next((r for r in rooms if r['kind']=='project' and r['project_id']==project),None)
                context={'id':project,'name':record['name'],'channel':linked}
            return {'owner':who,'actor':actor,'enabled':chat_settings.settings(c,who,actor)['embeddedChat']=='enabled','channels':result,'unread_count':sum(r['unread_count'] for r in result),'important_count':sum(r['important_count'] for r in result),'project':context}
    @app.put('/api/chat/embedded/read')
    def read_all(req:Request):
        with db() as c:
            c.execute('BEGIN IMMEDIATE');who,actor=identity(req,c);now=time.time();ids=[]
            for room in channels(c,who,actor):
                if room['joined']:
                    c.execute('UPDATE tw_chat_members SET last_read=? WHERE owner=? AND channel=? AND actor=?',(now,who,room['id'],actor));ids.append(room['id'])
            return {'read':ids}
