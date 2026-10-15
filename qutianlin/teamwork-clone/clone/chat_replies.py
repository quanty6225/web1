"""Reply to local Chat notification emails using scoped, expiring capabilities."""
import json,re,secrets,time
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from urllib.parse import urlencode
from urllib.request import build_opener,ProxyHandler
from fastapi import HTTPException
DOMAIN='reply.teamwork.clone.test'
SCHEMA='''
CREATE TABLE IF NOT EXISTS tw_chat_reply_tokens(token TEXT PRIMARY KEY,owner TEXT NOT NULL,message TEXT NOT NULL,actor TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,email TEXT NOT NULL,expires REAL NOT NULL,UNIQUE(owner,message,actor),FOREIGN KEY(owner,message) REFERENCES tw_chat_messages(owner,id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tw_chat_reply_mail(token TEXT NOT NULL REFERENCES tw_chat_reply_tokens(token) ON DELETE CASCADE,mail TEXT NOT NULL,state TEXT NOT NULL,message TEXT,PRIMARY KEY(token,mail));
'''
def address(c,owner,message,actor,email):
 row=c.execute('SELECT token FROM tw_chat_reply_tokens WHERE owner=? AND message=? AND actor=?',(owner,message,actor)).fetchone()
 if row:return row['token']+'@'+DOMAIN
 token=secrets.token_urlsafe(32);c.execute('INSERT INTO tw_chat_reply_tokens VALUES(?,?,?,?,?,?)',(token,owner,message,actor,email,time.time()+30*86400));return token+'@'+DOMAIN

def reply_text(parsed):
 part=parsed.get_body(preferencelist=('plain',)) if parsed.is_multipart() else parsed
 if not part or part.get_content_type()!='text/plain' or part.get_content_disposition()=='attachment':return ''
 text=part.get_content()
 if not isinstance(text,str):return ''
 text=re.split(r'(?im)(?<!\S)#end\b',text,maxsplit=1)[0]
 text=re.split(r'(?im)^On .{1,1000}wrote:\s*$',text,maxsplit=1)[0]
 return text.strip()

def install(db):
 with db() as c:c.executescript(SCHEMA)
 def ingest():
  from chat_local import channel,add_message
  from chat_conversations import cutoff
  with db() as c:tokens=[dict(r) for r in c.execute('SELECT * FROM tw_chat_reply_tokens WHERE expires>?',(time.time(),))]
  http=build_opener(ProxyHandler({}));delivered=0
  def fetch(path):
   with http.open('http://127.0.0.1:8025'+path,timeout=10) as response:return response.read()
  for token in tokens:
   start=0;target=token['token']+'@'+DOMAIN
   while True:
    items=json.loads(fetch('/api/v1/search?'+urlencode({'query':'to:'+target,'start':start,'limit':100})))['messages']
    for item in items:
     with db() as c:
      if c.execute('SELECT 1 FROM tw_chat_reply_mail WHERE token=? AND mail=?',(token['token'],item['ID'])).fetchone():continue
     raw=fetch('/api/v1/message/'+item['ID']+'/raw');parsed=BytesParser(policy=policy.default).parsebytes(raw);text=reply_text(parsed)
     with db() as c:
      c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM tw_chat_reply_tokens WHERE token=? AND expires>?',(token['token'],time.time())).fetchone()
      if not row:continue
      if not c.execute('INSERT OR IGNORE INTO tw_chat_reply_mail VALUES(?,?,?,NULL)',(row['token'],item['ID'],'received')).rowcount:continue
      def reject(reason):c.execute('UPDATE tw_chat_reply_mail SET state=? WHERE token=? AND mail=?',(reason,row['token'],item['ID']))
      senders=[email.casefold() for _,email in getaddresses(parsed.get_all('From',[]))];recipients=[email.casefold() for _,email in getaddresses(parsed.get_all('To',[])+parsed.get_all('Cc',[]))]
      account=c.execute('SELECT email_normalized FROM local_auth_accounts WHERE account_id=?',(row['actor'],)).fetchone()
      if senders!=[row['email'].casefold()] or target.casefold() not in recipients or not account or account['email_normalized'].casefold()!=row['email'].casefold():reject('sender-mismatch');continue
      if str(parsed.get('Auto-Submitted','no')).casefold()!='no' or str(parsed.get('Precedence','')).casefold() in ['bulk','list','junk']:reject('automatic-message');continue
      if len(raw)>100000 or not text or len(text)>20000:reject('invalid-plain-body');continue
      if row['actor']!=row['owner'] and not c.execute('SELECT 1 FROM tw_memberships WHERE workspace_owner=? AND account=?',(row['owner'],row['actor'])).fetchone():reject('access-revoked');continue
      original=c.execute('SELECT * FROM tw_chat_messages WHERE owner=? AND id=?',(row['owner'],row['message'])).fetchone()
      if not original:reject('message-removed');continue
      try:channel(c,row['owner'],row['actor'],original['channel'],member=True)
      except HTTPException:reject('access-revoked');continue
      if original['created']<=cutoff(c,row['owner'],original['channel'],row['actor']):reject('history-cleared');continue
      mid=add_message(c,row['owner'],original['channel'],row['actor'],text)
      c.execute("UPDATE tw_chat_reply_mail SET state='sent',message=? WHERE token=? AND mail=?",(mid,row['token'],item['ID']));delivered+=1
    if len(items)<100:break
    start+=len(items)
  return delivered
 return ingest
