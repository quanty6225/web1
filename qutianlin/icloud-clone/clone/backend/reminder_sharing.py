"""Legacy reminder-list membership; only owners manage invitations."""
import json,secrets,time
from backend import reminders,calendar_archives
from websitebench.local_clone_auth.store import _normalize_email,AuthError
PREFIX='rshared:'


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS icloud_reminder_shares (
        id TEXT PRIMARY KEY, owner TEXT NOT NULL, target TEXT NOT NULL, active INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS icloud_reminder_members (
        share_id TEXT NOT NULL, email TEXT NOT NULL, account_id TEXT, status TEXT NOT NULL,
        PRIMARY KEY(share_id,email))''')


def read(db,owner,kind,key):
    row=db.execute('SELECT payload FROM icloud_entities WHERE owner=? AND kind=? AND id=?',(owner,kind,key)).fetchone()
    return json.loads(row[0]) if row else None


def get_share(db,key):
    share=db.execute('SELECT * FROM icloud_reminder_shares WHERE id=? AND active=1',(key,)).fetchone()
    if not share or not read(db,share['owner'],'lists',share['target']):raise LookupError('This shared list is no longer available.')
    return share


def membership(db,share,actor):
    return db.execute('''SELECT * FROM icloud_reminder_members WHERE share_id=?
        AND (account_id=? OR (account_id IS NULL AND email=?))''',
        (share['id'],actor['account_id'],actor['email_normalized'])).fetchone()


def access(db,key,actor,*,pending=False):
    share=get_share(db,key)
    if share['owner']==actor['account_id']:return share,None
    member=membership(db,share,actor)
    if not member or member['status']=='declined' or not pending and member['status']!='accepted':raise PermissionError('You do not have access to this reminder list.')
    return share,member


def owned_share(db,owner,list_id):
    return db.execute('SELECT * FROM icloud_reminder_shares WHERE owner=? AND target=? AND active=1',(owner,list_id)).fetchone()


def decorate(item,share=None,member=None,kind='reminders'):
    value={k:v for k,v in item.items() if k not in ('_sharing','_original_id')}
    if share:
        value['_sharing']={'id':share['id'],'owner':member is None,'accepted':member is None or member['status']=='accepted'}
        if member:
            value['_original_id']=item['id'];value['id']=PREFIX+share['id']+':'+item['id']
            if kind=='reminders':value['list']=PREFIX+share['id']+':'+share['target']
    return value


def visible(db,actor,kind):
    owner=actor['account_id'];result=[]
    for item in reminders.rows(db,owner,kind).values():
        share=owned_share(db,owner,item['id'] if kind=='lists' else item.get('list'))
        result.append(decorate(item,share,kind=kind))
    for share in db.execute('SELECT * FROM icloud_reminder_shares WHERE active=1 AND owner!=?',(owner,)).fetchall():
        member=membership(db,share,actor)
        target=read(db,share['owner'],'lists',share['target'])
        if not target or not member or member['status']=='declined':continue
        if kind=='lists':result.append(decorate(target,share,member,kind))
        elif member['status']=='accepted':
            result.extend(decorate(item,share,member) for item in reminders.rows(db,share['owner'],'reminders').values() if item.get('list')==share['target'])
    return result


def locate_list(db,actor,key):
    if not isinstance(key,str):raise ValueError('Choose a reminder list.')
    if key.startswith(PREFIX):
        try:_,sid,original=key.split(':',2)
        except ValueError:raise LookupError('List not found.')
        share,member=access(db,sid,actor)
        if share['target']!=original:raise LookupError('List not found.')
        return share['owner'],original,share,member
    if not read(db,actor['account_id'],'lists',key):raise LookupError('List not found.')
    return actor['account_id'],key,owned_share(db,actor['account_id'],key),None


def summary(db,key,actor):
    share,member=access(db,key,actor,pending=True);target=read(db,share['owner'],'lists',share['target'])
    owner=db.execute('SELECT display_name,email_normalized FROM local_auth_accounts WHERE account_id=?',(share['owner'],)).fetchone()
    result={'id':key,'target':share['target'],'name':target['name'],'owner':member is None,'owner_name':owner[0],
        'accepted':member is None or member['status']=='accepted'}
    if result['accepted']:
        result['owner_email']=owner[1]
        result['participants']=[{'email':p['email'],'status':p['status'],'self':p['account_id']==actor['account_id']} for p in db.execute('SELECT * FROM icloud_reminder_members WHERE share_id=? ORDER BY email',(key,))]
    return result


def invite(db,actor,data):
    addresses=data.get('recipients')
    if not isinstance(addresses,list) or not 1<=len(addresses)<=30:raise ValueError('Enter email addresses for the people you want to invite.')
    try:emails=sorted({_normalize_email(v) for v in addresses})
    except AuthError:raise ValueError('Enter valid email addresses.')
    if data.get('share_id'):
        share,member=access(db,data['share_id'],actor)
        if member:raise PermissionError('Only the owner can invite people.')
    else:
        key=data.get('list')
        if not isinstance(key,str) or key.startswith(PREFIX):raise PermissionError('Only the owner can invite people.')
        if not read(db,actor['account_id'],'lists',key):raise LookupError('List not found.')
        share=owned_share(db,actor['account_id'],key)
        if not share:
            sid=secrets.token_hex(16);db.execute('INSERT INTO icloud_reminder_shares VALUES (?,?,?,1)',(sid,actor['account_id'],key));share=get_share(db,sid)
    if actor['email_normalized'] in emails:raise ValueError('The owner already has access.')
    for email in emails:
        old=db.execute('SELECT status FROM icloud_reminder_members WHERE share_id=? AND email=?',(share['id'],email)).fetchone()
        if not old:db.execute("INSERT INTO icloud_reminder_members VALUES (?,?,NULL,'invited')",(share['id'],email))
        elif old[0]=='declined':db.execute("UPDATE icloud_reminder_members SET account_id=NULL,status='invited' WHERE share_id=? AND email=?",(share['id'],email))
    return share['id'],emails


def action(db,key,actor,data):
    action=data.get('action');share,member=access(db,key,actor,pending=action in ('join','decline'))
    if action in ('join','decline','leave'):
        if not member:raise ValueError('The owner cannot leave their own list.')
        if action=='leave':db.execute('DELETE FROM icloud_reminder_members WHERE share_id=? AND email=?',(key,member['email']))
        else:db.execute('UPDATE icloud_reminder_members SET account_id=?,status=? WHERE share_id=? AND email=?',
            (actor['account_id'],'accepted' if action=='join' else 'declined',key,member['email']))
    elif action=='remove':
        if member:raise PermissionError('Only the owner can remove people.')
        cursor=db.execute('DELETE FROM icloud_reminder_members WHERE share_id=? AND email=?',(key,data.get('email')))
        if not cursor.rowcount:raise LookupError('Participant not found.')
    elif action=='resend':
        if member:raise PermissionError('Only the owner can resend invitations.')
        email=data.get('email')
        if not db.execute('SELECT 1 FROM icloud_reminder_members WHERE share_id=? AND email=?',(key,email)).fetchone():raise LookupError('Participant not found.')
        db.execute("UPDATE icloud_reminder_members SET status='invited' WHERE share_id=? AND email=? AND status='declined'",(key,email))
        return email
    else:raise ValueError('Choose a sharing action.')
    if not db.execute('SELECT 1 FROM icloud_reminder_members WHERE share_id=?',(key,)).fetchone():db.execute('UPDATE icloud_reminder_shares SET active=0 WHERE id=?',(key,))


def write(db,actor,identifier,data,now,*,delete=False):
    source_owner=actor['account_id'];source_share=None;source_member=None;original=identifier
    if identifier.startswith(PREFIX):
        try:_,sid,original=identifier.split(':',2)
        except ValueError:raise LookupError('Reminder not found.')
        source_share,source_member=access(db,sid,actor);source_owner=source_share['owner']
    previous=read(db,source_owner,'reminders',original)
    if source_share and (not previous or previous.get('list')!=source_share['target']):raise LookupError('Reminder not found.')
    if db.execute("SELECT 1 FROM icloud_entity_tombstones WHERE owner=? AND kind='reminders' AND id=?",(source_owner,original)).fetchone():
        if delete:raise LookupError('Reminder not found.')
        raise FileNotFoundError('This reminder was permanently deleted.')
    if delete:
        if not previous:raise LookupError('Reminder not found.')
        calendar_archives.snapshot(db,source_owner,time.time_ns()//1000000)
        reminders.delete(db,source_owner,'reminders',original,now);return None
    selected=data.get('list') or (decorate(previous,source_share,source_member)['list'] if previous else None)
    try:target_owner,target,target_share,target_member=locate_list(db,actor,selected)
    except LookupError:raise ValueError('Choose one of your reminder lists.')
    if not previous and target_owner!=source_owner and read(db,target_owner,'reminders',original):raise ValueError('A reminder with this identifier already exists in the destination.')
    if not previous and db.execute("SELECT 1 FROM icloud_entity_tombstones WHERE owner=? AND kind='reminders' AND id=?",(target_owner,original)).fetchone():raise FileNotFoundError('This reminder was permanently deleted.')
    target_id=secrets.token_hex(16) if previous and target_owner!=source_owner else original
    clean={k:v for k,v in data.items() if k not in ('_sharing','_original_id')};clean.update(id=target_id,list=target)
    prior=dict(previous or {})
    if target_owner!=source_owner:prior.pop('_next_id',None);prior.pop('order',None)
    after=clean.get('after')
    if isinstance(after,str) and after.startswith(PREFIX):
        try:_,after_share,after_key=after.split(':',2)
        except ValueError:raise ValueError('Choose an insertion position in this list.')
        if not target_share or target_share['id']!=after_share:raise ValueError('Choose an insertion position in this list.')
        clean['after']=after_key
    for changed_owner in {source_owner,target_owner}:calendar_archives.snapshot(db,changed_owner,time.time_ns()//1000000)
    reminders.validate(db,target_owner,clean,prior,now)
    reminders.repeat_after_completion(db,target_owner,clean,prior,now)
    if previous and target_owner!=source_owner:reminders.delete(db,source_owner,'reminders',original,now)
    reminders.save(db,target_owner,'reminders',clean,now)
    return decorate(clean,target_share,target_member)
