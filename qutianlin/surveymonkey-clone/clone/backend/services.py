"""Site services: shared authentication, shared branded mail, local SMTP transport."""
import hmac,hashlib,json,os,secrets,smtplib,sqlite3
from contextlib import contextmanager,closing
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from fastapi import HTTPException
from backend.site_backend_integration import open_site_services
from backend.survey_model import seed_demo,seed_feedback
from websitebench.local_clone_auth import LocalAuthStore,MAIL_SMTP_PENDING
from backend.auth_service import SurveyAuthStore

ROOT=Path(__file__).resolve().parents[1]
backend,_=open_site_services()
WORKER=secrets.token_urlsafe(32)
auth=SurveyAuthStore(backend.lifecycle.database_path,site_id=backend.config.site_id,mail_mode=MAIL_SMTP_PENDING,mail_worker_token=WORKER)
auth.ensure_schema()
demo=auth.seed_account(subject_id='surveymonkey-demo',email='demo@surveymonkey.offline.invalid',display_name='Demo account',password='SurveyMonkey-Demo-2026!')
COOKIE=backend.config.cookie_name

@contextmanager
def db():
    with closing(sqlite3.connect(backend.lifecycle.database_path,timeout=20)) as connection:
        connection.row_factory=sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        with connection:yield connection

with db() as connection:
    seed_demo(connection,demo)
    seed_feedback(connection)

def account(request):
    session=auth.resolve_session(request.cookies.get(COOKIE))
    return session.get('account') if session else None

def require_account(request):
    value=account(request)
    if not value:raise HTTPException(401,'Please log in to SurveyMonkey.')
    return value

def csrf(token):return hmac.new(token.encode(),b'surveymonkey-local-form',hashlib.sha256).hexdigest()

def check_csrf(request):
    token=request.cookies.get(COOKIE)
    if not token or not hmac.compare_digest(csrf(token),request.headers.get('x-csrf-token','')):raise HTTPException(403,'This page has expired. Refresh it and try again.')
    origin=request.headers.get('origin')
    if origin and origin!=str(request.base_url).rstrip('/'):raise HTTPException(403,'The request origin does not match this site.')

def set_session(response,token):
    response.set_cookie(COOKIE,token,max_age=30*86400,**dict(backend.config.cookie_options));return response

def deliver_auth(token,purpose):
    claim=auth.claim_pending_mail_for_session(token,purpose=purpose,worker_token=WORKER)
    if not claim:return auth.session_mail_state(token,purpose=purpose)
    accepted=False;reserved=False
    try:
        mail=backend.mail.issue(purpose,claim['recipient'],{'code':claim['verification_code'],'minutes':10})
        host=os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1')
        if host not in ('127.0.0.1','localhost','::1','mailpit','smtp'):raise RuntimeError('SMTP must use the local mailbox.')
        sender=os.environ.get(mail['sender_address_env'],'no-reply@surveymonkey.clone.test')
        message=EmailMessage();message['From']=formataddr((mail['sender_display_name'],sender));message['To']=mail['recipient'];message['Subject']=mail['subject'];message['X-Clone-Site']='surveymonkey'
        link=os.environ.get('BASE_URL',backend.config.public_origin)+('/reset/verify' if purpose=='password-reset' else '/sign-up/verify')
        message.set_content(mail['text']+'\n\n'+link)
        message.add_alternative(mail['html']+'<p>'+link+'</p>',subtype='html')
        auth.reserve_mail_target_request(claim['mail_id'],claim['claim_token'],worker_token=WORKER);reserved=True
        with smtplib.SMTP(host,int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025')),timeout=8) as smtp:
            rejected=smtp.send_message(message)
            if rejected:raise RuntimeError('Local mailbox rejected the recipient.')
        accepted=True
    except (OSError,smtplib.SMTPException,RuntimeError):
        pass
    finally:
        auth.finish_mail_claim(claim['mail_id'],claim['claim_token'],sent=accepted,target_request_count=int(reserved),accepted_request_count=int(accepted),error=None if accepted else 'network',worker_token=WORKER)
    return auth.session_mail_state(token,purpose=purpose)

def survey_owned(connection,survey_id,owner,include_deleted=False):
    row=connection.execute('SELECT * FROM sm_surveys WHERE id=? AND owner=?'+('' if include_deleted else ' AND deleted=0'),(survey_id,owner)).fetchone()
    if not row:raise HTTPException(404,'Survey not found.')
    return row

def survey_data(connection,survey_id,public=False):
    row=connection.execute('SELECT * FROM sm_surveys WHERE id=? AND deleted=0',(survey_id,)).fetchone()
    if not row:raise HTTPException(404,'Survey not found.')
    result=dict(row)
    for key in ('theme','settings'):result[key]=json.loads(result[key])
    result['pages']=[]
    for page in connection.execute('SELECT * FROM sm_pages WHERE survey_id=? ORDER BY position',(survey_id,)):
        value=dict(page);value['logic']=json.loads(value['logic']);value['questions']=[]
        for q in connection.execute('SELECT * FROM sm_questions WHERE page_id=? ORDER BY position',(page['id'],)):
            question=dict(q);question['choices']=json.loads(question['choices']);question['options']=json.loads(question['options']);question['required']=bool(question['required']);value['questions'].append(question)
        result['pages'].append(value)
    if public:
        for key in ('owner','folder_id','created','updated','deleted','version'):result.pop(key,None)
    return result
