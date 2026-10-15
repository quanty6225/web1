"""Account-bound Notes collaboration. Links alone never grant content access."""
import hashlib,json,secrets
from backend.file_lifecycle import records,descendants
from backend.login_identifiers import resolve as resolve_phone
from websitebench.local_clone_auth.store import _normalize_email,AuthError

PREFIX='shared:'


def migrate(db):
    from backend import note_personal
    note_personal.migrate(db)
    db.execute('''CREATE TABLE IF NOT EXISTS icloud_note_shares (
        id TEXT PRIMARY KEY, owner TEXT NOT NULL, kind TEXT NOT NULL,
        target TEXT NOT NULL, active INTEGER NOT NULL, created_at INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS icloud_note_participants (
        share_id TEXT NOT NULL, email TEXT NOT NULL, account_id TEXT,
        permission TEXT NOT NULL, can_invite INTEGER NOT NULL, accepted INTEGER NOT NULL,
        PRIMARY KEY(share_id,email))''')
    db.execute('''CREATE TABLE IF NOT EXISTS icloud_note_hidden (
        share_id TEXT NOT NULL, account_id TEXT NOT NULL, note_id TEXT NOT NULL,
        PRIMARY KEY(share_id,account_id,note_id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS icloud_note_pins (
        account_id TEXT NOT NULL, resource_owner TEXT NOT NULL,
        note_id TEXT NOT NULL, pinned INTEGER NOT NULL,
        PRIMARY KEY(account_id,resource_owner,note_id))''')


def revision(item):
    return hashlib.sha256(json.dumps({k:item.get(k) for k in ('title','body','html')},sort_keys=True).encode()).hexdigest()


def entity(db,owner,kind,key):
    row=db.execute('SELECT payload FROM icloud_entities WHERE owner=? AND kind=? AND id=?',(owner,kind,key)).fetchone()
    return json.loads(row[0]) if row else None


def content(db,share):
    target=entity(db,share['owner'],share['kind'],share['target'])
    if not target or target.get('deleted') or target.get('locked'):raise LookupError('Shared item is no longer available.')
    if share['kind']=='notes':return [],[target]
    folders=records(db,share['owner'],'folders');keys=descendants(folders,[share['target']])
    notes=[n for n in records(db,share['owner'],'notes').values() if n.get('folder') in keys and not n.get('deleted') and not n.get('locked')]
    return [folders[key] for key in keys],notes


def share_row(db,key):
    row=db.execute('SELECT * FROM icloud_note_shares WHERE id=? AND active=1',(key,)).fetchone()
    if not row:raise LookupError('Shared item is no longer available.')
    content(db,row)
    return row


def participant(db,share,account):
    return db.execute('''SELECT * FROM icloud_note_participants WHERE share_id=?
        AND (account_id=? OR (account_id IS NULL AND email=?))''',
        (share['id'],account['account_id'],account['email_normalized'])).fetchone()


def access(db,key,account,*,accepted=True):
    share=share_row(db,key)
    if share['owner']==account['account_id']:return share,None
    person=participant(db,share,account)
    if not person or accepted and not person['accepted']:raise PermissionError('You do not have access to this shared item.')
    return share,person


def inherited(db,owner,kind,key):
    item=entity(db,owner,kind,key)
    if not item:return None
    folder=key if kind=='folders' else item.get('folder');ancestors=[]
    while folder and folder not in ancestors:
        ancestors.append(folder);parent=entity(db,owner,'folders',folder)
        folder=parent.get('parent') if parent else None
    shares=db.execute('SELECT * FROM icloud_note_shares WHERE owner=? AND active=1 ORDER BY created_at,id',(owner,)).fetchall()
    # A folder grant governs every contained note; individual grants cannot
    # override its participant permissions.
    for ancestor in reversed(ancestors):
        for share in shares:
            if share['kind']=='folders' and share['target']==ancestor:return share
    return next((s for s in shares if s['kind']==kind and s['target']==key),None)


def decorate(item,share=None,person=None,*,kind='notes'):
    result=dict(item)
    if kind=='notes':result['_revision']=revision(item)
    if not share:return result
    result['_share']={'id':share['id'],'kind':share['kind'],'owner':person is None,'root':kind==share['kind'] and item['id']==share['target'],
        'permission':person['permission'] if person else 'write','can_invite':bool(person['can_invite']) if person else True}
    if person:
        result['_original_id']=item['id'];result['id']=PREFIX+share['id']+':'+item['id']
        result['folder']=PREFIX+share['id']+':'+item.get('folder','notes') if share['kind']=='folders' else 'notes'
        if kind=='folders':result['parent']=PREFIX+share['id']+':'+item['parent'] if item.get('parent') and item['id']!=share['target'] else None
    return result


def list_items(db,account,kind):
    owner=account['account_id'];result=[]
    for item in records(db,owner,kind).values():result.append(decorate(item,inherited(db,owner,kind,item['id']),kind=kind))
    for share in db.execute('SELECT * FROM icloud_note_shares WHERE active=1 AND owner!=?',(owner,)).fetchall():
        person=participant(db,share,account)
        if not person or not person['accepted']:continue
        try:folders,notes=content(db,share)
        except LookupError:continue
        hidden={r[0] for r in db.execute('SELECT note_id FROM icloud_note_hidden WHERE share_id=? AND account_id=?',(share['id'],owner))}
        for item in folders if kind=='folders' else notes:
            # Existing direct note grants are suspended while a containing
            # folder controls the note, including for recipients not in it.
            controlling=inherited(db,share['owner'],kind,item['id'])
            if not controlling or controlling['id']!=share['id']:continue
            if kind=='notes' and item['id'] in hidden:continue
            result.append(decorate(item,share,person,kind=kind))
    from backend.note_personal import overlay
    for item in result:
        overlay(db,account,item,kind)
        if kind=='notes':
            share_id=item.get('_share',{}).get('id')
            resource_owner=db.execute('SELECT owner FROM icloud_note_shares WHERE id=?',(share_id,)).fetchone()[0] if item.get('_original_id') else owner
            row=db.execute("SELECT updated_at FROM icloud_entities WHERE owner=? AND kind='notes' AND id=?",(resource_owner,item.get('_original_id',item['id']))).fetchone()
            item['_modified']=row[0] if row else None
            personalize_pin(db,owner,resource_owner,item)
    return result


def personalize_pin(db,account_id,resource_owner,item):
    identifier=item.get('_original_id',item['id'])
    row=db.execute('SELECT pinned FROM icloud_note_pins WHERE account_id=? AND resource_owner=? AND note_id=?',
        (account_id,resource_owner,identifier)).fetchone()
    # Preserve existing owned-note pins, but never inherit another person's pin.
    item['pinned']=bool(row[0]) if row else bool(item.get('pinned')) if account_id==resource_owner else False
    return item


def set_pin(db,account,identifier,pinned):
    if type(pinned) is not bool:raise ValueError('Choose a pin state.')
    item=next((n for n in list_items(db,account,'notes') if n['id']==identifier),None)
    if not item:raise LookupError('Note not found.')
    if item.get('deleted'):raise FileExistsError('Recover this note before pinning it.')
    resource_owner=account['account_id']
    if item.get('_original_id'):
        share,_,_=shared_item(db,account,'notes',identifier)
        resource_owner=share['owner']
    db.execute('''INSERT INTO icloud_note_pins VALUES (?,?,?,?)
        ON CONFLICT(account_id,resource_owner,note_id) DO UPDATE SET pinned=excluded.pinned''',
        (account['account_id'],resource_owner,item.get('_original_id',identifier),int(pinned)))
    item['pinned']=pinned
    return item


def clear_pin(db,account_id,resource_owner,identifier):
    # An explicit false also suppresses the owned legacy payload fallback.
    db.execute('''INSERT INTO icloud_note_pins VALUES (?,?,?,0)
        ON CONFLICT(account_id,resource_owner,note_id) DO UPDATE SET pinned=0''',
        (account_id,resource_owner,identifier))


def summary(db,key,account):
    share,person=access(db,key,account,accepted=False)
    target=entity(db,share['owner'],share['kind'],share['target'])
    owner=db.execute('SELECT display_name FROM local_auth_accounts WHERE account_id=?',(share['owner'],)).fetchone()
    result={'id':key,'kind':share['kind'],'title':target.get('title') or target.get('name'),
        'target':share['target'],'owner':person is None,'owner_name':owner[0],'accepted':person is None or bool(person['accepted']),
        'permission':person['permission'] if person else 'write','can_invite':bool(person['can_invite']) if person else True}
    if result['accepted']:
        result['participants']=[{'email':p['email'],'permission':p['permission'],'can_invite':bool(p['can_invite']),
            'accepted':bool(p['accepted']),'self':p['account_id']==account['account_id']}
            for p in db.execute('SELECT * FROM icloud_note_participants WHERE share_id=? ORDER BY email',(key,))]
    return result


def invite(db,account,data,now):
    permission=data.get('permission','write')
    if permission not in ('read','write'):raise ValueError('Choose a permission level.')
    addresses=data.get('recipients')
    if not isinstance(addresses,list) or not 1<=len(addresses)<=30:raise ValueError('Enter people to invite.')
    emails=set()
    for address in addresses:
        try:email=_normalize_email(address) if isinstance(address,str) and '@' in address else resolve_phone(db,address)
        except AuthError:raise ValueError('Enter a valid email address or account phone number.')
        if not email:raise ValueError('Use an email address or a phone number associated with a local account.')
        emails.add(email)
    if data.get('share_id'):
        share,person=access(db,data['share_id'],account)
        if person and not person['can_invite']:raise PermissionError('You cannot add people to this item.')
    else:
        kind=data.get('kind');key=data.get('target');owner=account['account_id']
        if kind not in ('notes','folders') or not isinstance(key,str):raise ValueError('Choose a note or folder.')
        item=entity(db,owner,kind,key)
        if not item or item.get('deleted'):raise LookupError('Item not found.')
        if item.get('locked'):raise ValueError('Locked notes cannot be shared.')
        if kind=='folders':
            folders=records(db,owner,'folders');keys=descendants(folders,[key])
            if any(n.get('locked') and n.get('folder') in keys for n in records(db,owner,'notes').values()):raise ValueError('This folder contains a locked note.')
        share=inherited(db,owner,kind,key)
        if share and (share['kind']!=kind or share['target']!=key):raise ValueError('Manage sharing at the shared folder level.')
        if not share:
            key_id=secrets.token_hex(16)
            db.execute('INSERT INTO icloud_note_shares VALUES (?,?,?,?,1,?)',(key_id,owner,kind,key,now))
            share=share_row(db,key_id)
            if kind=='folders':
                for old in db.execute('SELECT * FROM icloud_note_shares WHERE owner=? AND active=1 AND id!=?',(owner,key_id)).fetchall():
                    if inherited(db,owner,old['kind'],old['target'])['id']==key_id:
                        db.execute('UPDATE icloud_note_shares SET active=0 WHERE id=?',(old['id'],))
        person=None
    owner_email=db.execute('SELECT email_normalized FROM local_auth_accounts WHERE account_id=?',(share['owner'],)).fetchone()[0]
    if owner_email in emails:raise ValueError('The owner already has access.')
    for email in emails:
        # Re-inviting cannot quietly change an existing participant's grant.
        db.execute('INSERT OR IGNORE INTO icloud_note_participants VALUES (?,?,NULL,?,?,0)',
            (share['id'],email,permission,int(bool(data.get('can_invite')))))
    return share['id'],sorted(emails)


def action(db,key,account,data):
    action=data.get('action');share,person=access(db,key,account,accepted=action!='accept')
    if action=='accept':
        if person:
            db.execute('UPDATE icloud_note_participants SET account_id=?,accepted=1 WHERE share_id=? AND email=?',
                (account['account_id'],key,person['email']))
            db.execute('DELETE FROM icloud_note_hidden WHERE share_id=? AND account_id=?',(key,account['account_id']))
        return
    if action=='stop':
        if person:raise PermissionError('Only the owner can stop sharing.')
        db.execute('UPDATE icloud_note_shares SET active=0 WHERE id=?',(key,));return
    if action in ('leave','hide'):
        if not person:raise ValueError('The owner cannot remove themselves.')
        from backend.note_personal import clear_share
        clear_share(db,account['account_id'],key)
        if action=='leave':db.execute('DELETE FROM icloud_note_participants WHERE share_id=? AND email=?',(key,person['email']))
        else:
            db.execute('UPDATE icloud_note_participants SET accepted=0 WHERE share_id=? AND email=?',(key,person['email']))
            if share['kind']=='notes':clear_pin(db,account['account_id'],share['owner'],share['target'])
        return
    if person and not person['can_invite']:raise PermissionError('You cannot manage participants.')
    email=data.get('email');target=db.execute('SELECT * FROM icloud_note_participants WHERE share_id=? AND email=?',(key,email)).fetchone()
    if not target:raise LookupError('Participant not found.')
    if action=='remove':db.execute('DELETE FROM icloud_note_participants WHERE share_id=? AND email=?',(key,email));return
    if action=='permission':
        if data.get('permission') not in ('read','write'):raise ValueError('Choose a permission level.')
        db.execute('UPDATE icloud_note_participants SET permission=?,can_invite=? WHERE share_id=? AND email=?',
            (data['permission'],int(bool(data.get('can_invite'))),key,email));return
    raise ValueError('Unknown sharing action.')


def shared_item(db,account,kind,alias):
    try:_,key,identifier=alias.split(':',2)
    except ValueError:raise LookupError('Item not found.')
    share,person=access(db,key,account)
    folders,notes=content(db,share);item=next((v for v in (folders if kind=='folders' else notes) if v['id']==identifier),None)
    governing=inherited(db,share['owner'],kind,identifier)
    if not item or not governing or governing['id']!=key:raise LookupError('Item not found.')
    return share,person,item


def update_shared(db,account,kind,alias,data,now,*,delete=False):
    share,person,item=shared_item(db,account,kind,alias)
    if not person:raise ValueError('Use the original item.')
    if delete:
        from backend.note_received_deletion import delete as delete_received
        delete_received(db,account,kind,share,person,item,now)
        return None
    if kind=='folders':
        from backend.note_personal import rename_folder
        return rename_folder(db,account,alias,data,now)
    if kind!='notes' or person['permission']!='write':raise PermissionError('You can only view this item.')
    if data.get('_revision')!=revision(item):raise FileExistsError('This note changed. Reload before saving your changes.')
    from backend.note_personal import overlay
    current=overlay(db,account,decorate(item,share,person),'notes')
    # A direct share's folder is personal projection, never part of a content save.
    for field in (('deleted',) if share['kind']=='notes' else ('deleted','folder')):
        if field in data and data[field]!=current.get(field):raise PermissionError('Use the corresponding note action.')
    for field in ('title','body','html'):
        if field in data:
            if not isinstance(data[field],str):raise ValueError('Invalid note content.')
            item[field]=data[field]
    db.execute("UPDATE icloud_entities SET payload=?,updated_at=? WHERE owner=? AND kind='notes' AND id=?",
        (json.dumps(item),now,share['owner'],item['id']))
    return personalize_pin(db,account['account_id'],share['owner'],overlay(db,account,decorate(item,share,person),'notes'))


def revoke_deleted(db,owner):
    for share in db.execute('SELECT * FROM icloud_note_shares WHERE owner=? AND active=1',(owner,)).fetchall():
        try:content(db,share)
        except LookupError:db.execute('UPDATE icloud_note_shares SET active=0 WHERE id=?',(share['id'],))


def revoke_moved(db,owner,kind,identifier,previous,target):
    """A containing share replaces direct grants; private moves retain them."""
    source=previous.get('folder','notes') if kind=='notes' else previous.get('parent')
    if not previous or source==target:return
    if not target or not inherited(db,owner,'folders',target):return
    folders=descendants(records(db,owner,'folders'),[identifier]) if kind=='folders' else set()
    notes={identifier} if kind=='notes' else {
        note['id'] for note in records(db,owner,'notes').values() if note.get('folder') in folders}
    for share in db.execute('SELECT * FROM icloud_note_shares WHERE owner=? AND active=1',(owner,)).fetchall():
        if share['target'] in (folders if share['kind']=='folders' else notes):
            db.execute('UPDATE icloud_note_shares SET active=0 WHERE id=?',(share['id'],))


def repair_shadowed_shares(db):
    """Retire grants left beneath a controlling folder by older local versions."""
    for share in db.execute('SELECT * FROM icloud_note_shares WHERE active=1').fetchall():
        governing=inherited(db,share['owner'],share['kind'],share['target'])
        if governing and governing['id']!=share['id']:
            db.execute('UPDATE icloud_note_shares SET active=0 WHERE id=?',(share['id'],))


def create_note(db,account,folder_alias,now):
    share,person,folder=shared_item(db,account,'folders',folder_alias)
    if not person or person['permission']!='write':raise PermissionError('You can only view this folder.')
    item={'id':secrets.token_hex(16),'folder':folder['id'],'title':'New Note','body':'','deleted':False,'pinned':False}
    db.execute('INSERT INTO icloud_entities VALUES (?,?,?,?,?)',(share['owner'],'notes',item['id'],json.dumps(item),now))
    return decorate(item,share,person)
