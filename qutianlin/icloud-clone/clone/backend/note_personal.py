"""Private placement/title overlays for received Notes share roots."""
import json


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS icloud_note_personal (
        account_id TEXT NOT NULL, share_id TEXT NOT NULL, kind TEXT NOT NULL,
        item_id TEXT NOT NULL, name TEXT, parent TEXT,
        PRIMARY KEY(account_id,share_id,kind,item_id))''')


def overlay(db,account,item,kind):
    share=item.get('_share')
    if not share or share['owner'] or not share['root']:return item
    row=db.execute('SELECT name,parent FROM icloud_note_personal WHERE account_id=? AND share_id=? AND kind=? AND item_id=?',
        (account['account_id'],share['id'],kind,item['_original_id'])).fetchone()
    if not row:return item
    from backend.note_sharing import entity,inherited
    parent=row['parent']
    # A stale personal reference must never make a received item disappear.
    if parent and (not entity(db,account['account_id'],'folders',parent) or inherited(db,account['account_id'],'folders',parent)):
        parent=None
    if kind=='folders':
        if row['name'] is not None:item['name']=row['name']
        item['parent']=parent
    else:item['folder']=parent or 'notes'
    return item


def tree(db,owner):
    from backend.note_sharing import list_items
    account=db.execute('SELECT * FROM local_auth_accounts WHERE account_id=?',(owner,)).fetchone()
    return {f['id']:f for f in list_items(db,account,'folders')}


def received_root(db,account,kind,alias):
    from backend.note_sharing import shared_item,list_items
    share,person,item=shared_item(db,account,kind,alias)
    if not person or share['kind']!=kind or share['target']!=item['id']:
        raise PermissionError('Only a received shared root has a personal location.')
    if not any(v['id']==alias for v in list_items(db,account,kind)):
        raise LookupError('Item not found.')
    return share,item


def move(db,account,kind,alias,parent):
    if kind not in ('notes','folders'):raise ValueError('Choose a note or folder.')
    share,item=received_root(db,account,kind,alias)
    from backend.note_sharing import entity,inherited,list_items
    owner=account['account_id']
    if parent is not None and (not isinstance(parent,str) or not parent):raise ValueError('Folder not found.')
    if parent:
        if not entity(db,owner,'folders',parent):raise LookupError('Folder not found.')
        if inherited(db,owner,'folders',parent):raise PermissionError('Items cannot be moved into a shared folder.')
    if kind=='notes' and not parent:raise ValueError('Notes cannot be moved to All iCloud.')
    if kind=='folders':
        if parent=='notes':raise ValueError('Folders cannot be moved into Notes.')
        from backend.note_folders import validate_hierarchy
        validate_hierarchy(tree(db,owner),alias,parent)
    db.execute('''INSERT INTO icloud_note_personal VALUES (?,?,?,?,NULL,?)
        ON CONFLICT(account_id,share_id,kind,item_id) DO UPDATE SET parent=excluded.parent''',
        (owner,share['id'],kind,item['id'],parent))
    return next(v for v in list_items(db,account,kind) if v['id']==alias)


def rename_folder(db,account,alias,data,now):
    from backend.note_sharing import shared_item,decorate,list_items
    share,person,item=shared_item(db,account,'folders',alias)
    if not person:raise ValueError('Use the original item.')
    current=next((f for f in list_items(db,account,'folders') if f['id']==alias),None)
    if not current:raise LookupError('Folder not found.')
    name=data.get('name')
    if not isinstance(name,str) or not name.strip():raise ValueError('Enter a folder name.')
    if item['id']==share['target']:
        if 'parent' in data and data['parent']!=current.get('parent'):
            move(db,account,'folders',alias,data['parent'])
        db.execute('''INSERT INTO icloud_note_personal VALUES (?,?,?,?,?,NULL)
            ON CONFLICT(account_id,share_id,kind,item_id) DO UPDATE SET name=excluded.name''',
            (account['account_id'],share['id'],'folders',item['id'],name.strip()))
        return next(f for f in list_items(db,account,'folders') if f['id']==alias)
    if person['permission']!='write':raise PermissionError('You can only view this folder.')
    if 'parent' in data and data['parent']!=current.get('parent'):
        raise PermissionError('A subfolder inside a shared folder cannot be moved.')
    item['name']=name.strip()
    db.execute("UPDATE icloud_entities SET payload=?,updated_at=? WHERE owner=? AND kind='folders' AND id=?",
        (json.dumps(item),now,share['owner'],item['id']))
    return decorate(item,share,person,kind='folders')


def clear_share(db,account_id,share_id):
    db.execute('DELETE FROM icloud_note_personal WHERE account_id=? AND share_id=?',(account_id,share_id))


def delete_container(db,owner,folders):
    """Removing a private containing folder removes received roots only for its owner."""
    from backend.note_sharing import action
    account=db.execute('SELECT * FROM local_auth_accounts WHERE account_id=?',(owner,)).fetchone()
    rows=db.execute('SELECT * FROM icloud_note_personal WHERE account_id=?',(owner,)).fetchall()
    for row in rows:
        if row['parent'] not in folders:continue
        try:action(db,row['share_id'],account,{'action':'hide'})
        except (LookupError,PermissionError):clear_share(db,owner,row['share_id'])
