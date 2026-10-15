"""Event-linked attachment bytes, retained for archived event restoration."""
import base64,binascii,secrets,time
from pathlib import PurePosixPath
from backend.reminder_sharing import read
MAX_BYTES=20*1024*1024


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS icloud_event_attachments (
      id TEXT PRIMARY KEY,uploader TEXT NOT NULL,name TEXT NOT NULL,
      size INTEGER NOT NULL,content BLOB NOT NULL,created_at INTEGER NOT NULL)''')


def metadata(row):return {'id':row['id'],'name':row['name'],'size':row['size']}


def upload(db,actor,data):
    name=data.get('name');encoded=data.get('content')
    if not isinstance(name,str) or not name.strip() or not isinstance(encoded,str):raise ValueError('Choose an attachment.')
    if len(encoded)>((MAX_BYTES+2)//3)*4:raise ValueError('Choose a file smaller than 20 MB.')
    try:content=base64.b64decode(encoded,validate=True)
    except (ValueError,binascii.Error):raise ValueError('Invalid attachment contents.')
    if len(content)>MAX_BYTES:raise ValueError('Choose a file smaller than 20 MB.')
    if any(c in name for c in '\\/:*?"<>|'):raise ValueError('This filename contains characters that cannot be used in Calendar.')
    name=PurePosixPath(name).name
    name=''.join(c for c in name if ord(c)>=32 and ord(c)!=127)[:255].strip()
    if not name or name in ('.','..'):raise ValueError('Choose a file name.')
    identifier=secrets.token_hex(16)
    db.execute('INSERT INTO icloud_event_attachments VALUES (?,?,?,?,?,?)',(identifier,actor['account_id'],name,len(content),content,int(time.time())))
    return {'id':identifier,'name':name,'size':len(content)}


def validate(db,actor,attachments,previous):
    if not isinstance(attachments,list) or len(attachments)>20:raise ValueError('Choose at most 20 attachments.')
    previous_ids={a['id'] for a in previous.get('attachments',[])};result=[];seen=set()
    for attachment in attachments:
        identifier=attachment.get('id') if isinstance(attachment,dict) else None
        if not isinstance(identifier,str):raise ValueError('Invalid attachment.')
        if identifier in seen:continue
        seen.add(identifier)
        row=db.execute('SELECT id,uploader,name,size FROM icloud_event_attachments WHERE id=?',(identifier,)).fetchone()
        if not row or identifier not in previous_ids and row['uploader']!=actor['account_id']:raise PermissionError('This attachment is not available to this event.')
        result.append(metadata(row))
    return result


def resolve_event(db,actor,key):
    from backend import calendar_sharing,event_invitations
    if key.startswith(event_invitations.PREFIX):return event_invitations.access(db,key[len(event_invitations.PREFIX):],actor)[1]
    if key.startswith(calendar_sharing.PREFIX):
        try:_,sid,original=key.split(':',2)
        except ValueError:raise LookupError('Event not found.')
        share,_=calendar_sharing.access(db,sid,actor);event=read(db,share['owner'],'events',original)
        if not event or event.get('calendar')!=share['target']:raise LookupError('Event not found.')
        return event
    event=read(db,actor['account_id'],'events',key)
    if not event:raise LookupError('Event not found.')
    return event


def download(db,actor,identifier,event_id=None):
    row=db.execute('SELECT * FROM icloud_event_attachments WHERE id=?',(identifier,)).fetchone()
    if not row:raise LookupError('Attachment not found.')
    if event_id:
        event=resolve_event(db,actor,event_id)
        if not any(a['id']==identifier for a in event.get('attachments',[])):raise LookupError('Attachment is no longer part of this event.')
    elif row['uploader']!=actor['account_id']:raise PermissionError('You do not have access to this attachment.')
    return row


def public_download(db,token,event_id,identifier):
    share=db.execute('SELECT * FROM icloud_calendar_shares WHERE active=1 AND public_token=?',(token,)).fetchone()
    if not share:raise LookupError('Public calendar not found.')
    event=read(db,share['owner'],'events',event_id)
    if not event or event.get('calendar')!=share['target'] or not any(a['id']==identifier for a in event.get('attachments',[])):raise LookupError('Attachment not found.')
    row=db.execute('SELECT * FROM icloud_event_attachments WHERE id=?',(identifier,)).fetchone()
    if not row:raise LookupError('Attachment not found.')
    return row
