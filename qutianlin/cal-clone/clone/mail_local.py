"""Local SMTP delivery with durable failure status and explicit retries."""
import os,smtplib,time,secrets
from email.message import EmailMessage

CLAIM_SECONDS=60

def mail_status(store,booking_id):
 with store.db() as c:
  return [{'id':r['id'],'status':'failed' if r['status']=='sending' and (r['claimed_at'] is None or r['claimed_at']<int(time.time())-CLAIM_SECONDS) else r['status'],'retryable':r['attempts']<3} for r in c.execute('SELECT id,status,attempts,claimed_at FROM cal_mail WHERE booking_id=?',(booking_id,))]

def deliver(store,booking_id=None,retry_failed=False):
 delivered=[]
 with store.db(True) as c:
  # An expired claim is an uncertain delivery, never a successful send. Retry
  # only when requested; retain the same Message-ID across attempts.
  c.execute("UPDATE cal_mail SET status='failed',claim_token=NULL,claimed_at=NULL,error='delivery-interrupted' WHERE status='sending' AND (claimed_at IS NULL OR claimed_at<?)",(int(time.time())-CLAIM_SECONDS,))
  rows=c.execute("SELECT * FROM cal_mail WHERE status IN ('pending'"+(",'failed'" if retry_failed else '')+") AND attempts<3"+(' AND booking_id=?' if booking_id else ''),(booking_id,) if booking_id else ()).fetchall()
 for r in rows:
  claim=secrets.token_urlsafe(24)
  with store.db(True) as c:
   changed=c.execute("UPDATE cal_mail SET status='sending',attempts=attempts+1,error=NULL,claim_token=?,claimed_at=? WHERE id=? AND status IN ('pending'"+(",'failed'" if retry_failed else '')+") AND attempts<3",(claim,int(time.time()),r['id'])).rowcount
  if not changed:continue
  message=EmailMessage();message['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@cal.clone.test');message['To']=r['recipient'];message['Subject']=r['subject'];message['Message-ID']='<'+r['id']+'@cal.clone.test>';message.set_content(r['body']);error=None
  try:
   with smtplib.SMTP(os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1'),int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025')),timeout=5) as smtp:smtp.send_message(message)
  except (OSError,smtplib.SMTPException) as exc:error=type(exc).__name__
  with store.db(True) as c:c.execute('UPDATE cal_mail SET status=?,error=?,claim_token=NULL,claimed_at=NULL WHERE id=? AND claim_token=?',('failed' if error else 'sent',error,r['id'],claim))
  delivered.append({'id':r['id'],'status':'failed' if error else 'sent'})
 return delivered
