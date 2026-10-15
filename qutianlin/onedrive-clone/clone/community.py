"""Local Q&A voting; no source tokens, remote writes or fabricated seed votes."""
import json
from pathlib import Path
from fastapi import Request,HTTPException

def register(app,db,session,auth):
    catalog=json.loads((Path(__file__).parent/'content/community-votes.json').read_text())
    follow_targets=json.loads((Path(__file__).parent/'content/community-follows.json').read_text())
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS community_votes(thread TEXT NOT NULL,target TEXT NOT NULL,actor TEXT NOT NULL,value TEXT NOT NULL,PRIMARY KEY(thread,target,actor))')
        c.execute('CREATE TABLE IF NOT EXISTS community_follows(actor TEXT NOT NULL,target TEXT NOT NULL,PRIMARY KEY(actor,target))')
    def actor(request):
        token,state=session(request,False)
        if not state:raise HTTPException(401,'请刷新页面后重试')
        logged=bool(state['authenticated'])
        return ('account:'+state['account']['account_id'] if logged else 'anonymous:'+auth.session_owner_digest(token)),logged
    def member(request):
        who,logged=actor(request)
        if not logged:raise HTTPException(401,'请先登录')
        return who
    def following(who):
        with db() as c:rows=c.execute('SELECT target FROM community_follows WHERE actor=? ORDER BY target',(who,)).fetchall()
        return {'following':[row['target'] for row in rows]}
    @app.get('/api/community/follows')
    def get_follows(request:Request):
        return following(member(request))
    @app.post('/api/community/follows')
    async def set_follow(request:Request):
        who=member(request);body=await request.json()
        if not isinstance(body,dict) or set(body)!={'target','following'} or not isinstance(body['target'],str) or type(body['following']) is not bool:raise HTTPException(400,'Invalid follow request')
        if body['target'] not in follow_targets:raise HTTPException(404,'Follow target not found')
        with db() as c:
            if body['following']:c.execute('INSERT OR IGNORE INTO community_follows VALUES(?,?)',(who,body['target']))
            else:c.execute('DELETE FROM community_follows WHERE actor=? AND target=?',(who,body['target']))
        return following(who)
    def thread(qid):
        if qid not in catalog:raise HTTPException(404,'Question not found')
        return catalog[qid]
    def result(qid,who):
        source=thread(qid)
        with db() as c:
            rows=c.execute('SELECT target,actor,value FROM community_votes WHERE thread=?',(qid,)).fetchall()
        votes={key:{**target,'count':target['source_count'],'selected':None} for key,target in source['targets'].items()}
        for row in rows:
            if row['target'] not in votes:continue
            target=votes[row['target']]
            if row['value']=='yes':target['count']+=1
            if row['actor']==who:target['selected']=row['value']
        return {'question':qid,'votes':votes}
    @app.get('/api/community/{qid}/votes')
    def votes(qid:str,request:Request):
        who,_=actor(request);return result(qid,who)
    @app.post('/api/community/{qid}/votes')
    async def vote(qid:str,request:Request):
        source=thread(qid);who,logged=actor(request);body=await request.json()
        if not isinstance(body,dict):raise HTTPException(400,'Invalid vote')
        target=body.get('target');value=body.get('value')
        if not isinstance(target,str) or target not in source['targets']:raise HTTPException(404,'Vote target not found')
        allowed=['yes','no',None] if source['targets'][target]['kind']=='answer' else ['yes',None]
        if value not in allowed:raise HTTPException(400,'Invalid vote')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');prior=c.execute('SELECT value FROM community_votes WHERE thread=? AND target=? AND actor=?',(qid,target,who)).fetchone()
            repeated=bool(prior and not logged)
            if not repeated:
                if value is None:c.execute('DELETE FROM community_votes WHERE thread=? AND target=? AND actor=?',(qid,target,who))
                else:c.execute('INSERT INTO community_votes VALUES(?,?,?,?) ON CONFLICT(thread,target,actor) DO UPDATE SET value=excluded.value',(qid,target,who,value))
        return {**result(qid,who),'repeated_anonymous_vote':repeated}
