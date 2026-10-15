"""Local notification feed and durable daily SMTP summaries (basic plan)."""
import json,os,time,smtplib,asyncio,logging
from email.message import EmailMessage
from email.utils import formataddr
from fastapi import APIRouter,Request
from backend.services import db,require_account,check_csrf,backend

router=APIRouter()
log=logging.getLogger(__name__)

def preferences(connection,owner):
    row=connection.execute('SELECT preferences FROM sm_profiles WHERE owner=?',(owner,)).fetchone()
    return json.loads(row['preferences']) if row else {}

@router.get('/api/notifications')
def feed(request:Request):
    owner=require_account(request)['account_id'];now=int(time.time())
    with db() as c:
        prefs=preferences(c,owner);seen=int(prefs.get('notifications_seen',0))
        rows=c.execute('SELECT s.id,s.title,s.settings,COUNT(*) count,MAX(r.completed) completed FROM sm_responses r JOIN sm_surveys s ON s.id=r.survey_id WHERE s.owner=? AND s.deleted=0 AND r.status="complete" AND r.completed>=? GROUP BY s.id ORDER BY completed DESC LIMIT 50',(owner,now-30*86400)).fetchall()
        items=[{'survey_id':r['id'],'title':r['title'],'count':r['count'],'completed':r['completed'],'unread':r['completed']>seen} for r in rows if json.loads(r['settings']).get('response_alerts',True)]
    return {'items':items,'unread':sum(i['unread'] for i in items)}

@router.post('/api/notifications/read')
def mark_read(request:Request):
    check_csrf(request);owner=require_account(request)['account_id']
    with db() as c:
        c.execute('BEGIN IMMEDIATE');prefs=preferences(c,owner);prefs['notifications_seen']=int(time.time())
        c.execute('INSERT INTO sm_profiles(owner,preferences) VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET preferences=excluded.preferences',(owner,json.dumps(prefs)))
    return {'ok':True}

def enqueue_daily_digests(now=None):
    """One summary per owner/day, at or after 08:00 UTC; no marketing messages."""
    now=int(time.time()) if now is None else int(now)
    day=now//86400
    if now%86400<8*3600:return 0
    start=(day-1)*86400;end=day*86400;queued=0
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        rows=c.execute('SELECT s.owner,s.id,s.title,s.settings,a.email_normalized,COUNT(*) count FROM sm_responses r JOIN sm_surveys s ON s.id=r.survey_id JOIN local_auth_accounts a ON a.account_id=s.owner WHERE s.deleted=0 AND r.status="complete" AND r.completed>=? AND r.completed<? GROUP BY s.id ORDER BY s.owner,s.title',(start,end)).fetchall()
        groups={}
        for row in rows:
            if not json.loads(row['settings']).get('response_alerts',True):continue
            groups.setdefault(row['owner'],[]).append(row)
        for owner,items in groups.items():
            key=f'digest:{owner}:{day-1}'
            if c.execute('SELECT 1 FROM websitebench_mail_jobs WHERE site_id=? AND purpose=? AND idempotency_key=?',(backend.config.site_id,'response-digest',key)).fetchone():continue
            summary='\n'.join(f"{r['title']}: {r['count']} new responses" for r in items)
            backend.mail.enqueue('response-digest',items[0]['email_normalized'],{'summary':summary,'url':os.environ.get('BASE_URL','http://127.0.0.1:18190')+'/home/'},idempotency_key=key,simulation=False,connection=c)
            queued+=1
    return queued

def deliver_pending_digests(now=None):
    delivered=0
    current=int(time.time()) if now is None else int(now)
    backend.mail.release_stale_claims(older_than=300,now=current)
    for _ in range(50):
        claim=backend.mail.claim_pending(now=now)
        if not claim:break
        mail=claim['message'];accepted=False
        try:
            host=os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1')
            if host not in ('127.0.0.1','localhost','::1','mailpit','smtp'):raise RuntimeError('SMTP must use the local mailbox.')
            message=EmailMessage();message['From']=formataddr((mail['sender_display_name'],os.environ.get(mail['sender_address_env'],'no-reply@surveymonkey.clone.test')));message['To']=mail['recipient'];message['Subject']=mail['subject'];message['X-Clone-Site']='surveymonkey';message['Message-ID']='<'+claim['mail_id']+'@surveymonkey.clone.test>';message.set_content(mail['text']);message.add_alternative(mail['html'],subtype='html')
            with smtplib.SMTP(host,int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025')),timeout=8) as smtp:
                if smtp.send_message(message):raise RuntimeError('Local mailbox rejected the recipient.')
            accepted=True
        except (OSError,smtplib.SMTPException,RuntimeError):
            backend.mail.mark_failed(claim['mail_id'],category='network',claim_token=claim['claim_token'],retry_delay_seconds=60,now=now)
        if accepted:
            backend.mail.mark_sent(claim['mail_id'],claim_token=claim['claim_token']);delivered+=1
    return delivered

async def digest_worker():
    while True:
        try:
            await asyncio.to_thread(enqueue_daily_digests)
            await asyncio.to_thread(deliver_pending_digests)
        except Exception:
            log.exception('Local response digest processing failed')
        await asyncio.sleep(60)
