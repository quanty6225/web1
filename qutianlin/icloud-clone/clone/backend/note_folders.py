"""Owned Notes folders and atomic moves; system folders remain protected."""
import json
from backend.file_lifecycle import records,descendants


def validate_folder(db,owner,identifier,data,previous):
    if identifier in ('all','recently-deleted'):
        raise ValueError('This is a system folder.')
    name=data.get('name','')
    if not isinstance(name,str) or not name.strip():
        raise ValueError('Enter a folder name.')
    data['name']=name.strip()
    data.setdefault('parent',previous.get('parent'))
    if data['parent'] is not None and (not isinstance(data['parent'],str) or not data['parent']):
        raise ValueError('Folder not found.')
    if identifier=='notes' and (data['name']!='Notes' or data.get('parent')):
        raise ValueError('The Notes folder cannot be renamed or moved.')
    # Parents of owned folders must remain owned; received roots are only personal overlays.
    folders=records(db,owner,'folders')
    if data.get('parent') and data['parent'] not in folders:raise ValueError('Folder not found.')
    from backend.note_personal import tree
    validate_hierarchy(tree(db,owner),identifier,data.get('parent'))


def validate_hierarchy(folders,identifier,parent):
    seen={identifier}
    while parent:
        if not isinstance(parent,str) or parent in seen:
            raise ValueError('A folder cannot contain itself.')
        if parent not in folders:raise ValueError('Folder not found.')
        seen.add(parent);parent=folders[parent].get('parent')
    children={}
    for key,folder in folders.items():
        children.setdefault(folder.get('parent'),[]).append(key)
    pending=[(identifier,len(seen))];visited=set()
    while pending:
        key,level=pending.pop()
        if key in visited:raise ValueError('A folder cannot contain itself.')
        visited.add(key)
        if level>5:raise ValueError('Notes is limited to 5 levels of folders.')
        pending.extend((child,level+1) for child in children.get(key,[]))


def validate_note(db,owner,data,previous):
    data.setdefault('folder',previous.get('folder') or 'notes')
    target=data['folder']
    if not isinstance(target,str) or not db.execute(
        "SELECT 1 FROM icloud_entities WHERE owner=? AND kind='folders' AND id=?",(owner,target)).fetchone():
        raise ValueError('Folder not found.')
    if previous and target!=previous.get('folder','notes'):
        raise ValueError('Use the move action to change the note folder.')


def delete_folder(db,owner,identifier,now):
    folders=records(db,owner,'folders')
    if identifier not in folders:raise LookupError('Folder not found.')
    affected=descendants(folders,[identifier])
    if 'notes' in affected:raise ValueError('The Notes folder cannot be deleted.')
    from backend.note_personal import delete_container
    delete_container(db,owner,affected)
    for note in records(db,owner,'notes').values():
        if note.get('folder') not in affected:continue
        from backend.note_sharing import clear_pin
        clear_pin(db,owner,owner,note['id'])
        deleted_at=note.get('deleted_at') if note.get('deleted') else None
        note.update(deleted=True,deleted_at=deleted_at or now,folder='notes')
        db.execute("UPDATE icloud_entities SET payload=?,updated_at=? WHERE owner=? AND kind='notes' AND id=?",
                   (json.dumps(note),now,owner,note['id']))
    for key in affected:
        db.execute('INSERT OR IGNORE INTO icloud_entity_tombstones VALUES (?,?,?,?)',(owner,'folders',key,now))
        db.execute("DELETE FROM icloud_entities WHERE owner=? AND kind='folders' AND id=?",(owner,key))


def move(db,owner,kind,identifier,target,now):
    if kind not in ('notes','folders') or not isinstance(identifier,str):
        raise ValueError('Choose a note or folder.')
    rows=records(db,owner,kind)
    if identifier not in rows:raise LookupError('Item not found.')
    item=dict(rows[identifier])
    if kind=='folders':
        item['parent']=target
        validate_folder(db,owner,identifier,item,rows[identifier])
    else:
        if not isinstance(target,str):raise ValueError('Notes cannot be moved to All iCloud.')
        folder=records(db,owner,'folders').get(target)
        if not folder:raise LookupError('Folder not found.')
        item.update(folder=target,deleted=False,shared=bool(folder.get('shared')))
        item.pop('deleted_at',None)
    from backend.note_sharing import revoke_moved
    revoke_moved(db,owner,kind,identifier,rows[identifier],target)
    db.execute('UPDATE icloud_entities SET payload=?,updated_at=? WHERE owner=? AND kind=? AND id=?',
               (json.dumps(item),now,owner,kind,identifier))
    return item
