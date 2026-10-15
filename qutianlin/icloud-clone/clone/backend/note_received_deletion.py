"""Delete received shared content while preserving the deleting actor's trash copy."""
import json,secrets
from backend.file_lifecycle import records,descendants


def delete(db,account,kind,share,person,item,now):
    from backend import note_sharing
    if kind=='folders' and item['id']==share['target']:
        note_sharing.action(db,share['id'],account,{'action':'hide'})
        return
    if person['permission']!='write':raise PermissionError('You can only view this item.')
    if kind=='notes' and share['kind']=='notes':
        note_sharing.action(db,share['id'],account,{'action':'hide'})
        return
    owner=share['owner'];actor=account['account_id']
    folders=descendants(records(db,owner,'folders'),[item['id']]) if kind=='folders' else set()
    notes=[n for n in records(db,owner,'notes').values() if n.get('folder') in folders and not n.get('deleted')] if kind=='folders' else [item]
    # Validate every member before changing any resource or personal record.
    for note in notes:
        if note.get('locked'):raise ValueError('Unlock this note before deleting it.')
        attachments=note.get('attachments',[])
        if not isinstance(attachments,list) or any(not isinstance(a,dict) or not isinstance(a.get('typeUTI'),str) or not a['typeUTI'].startswith('com.apple.notes.inlinetextattachment') for a in attachments):
            raise ValueError('Cannot clone note with this attachment type')
    for note in notes:
        identifier=secrets.token_hex(16)
        copy={key:note[key] for key in ('title','body','html','attachments') if key in note}
        copy.update(id=identifier,folder='notes',deleted=True,deleted_at=now,pinned=False)
        db.execute('INSERT INTO icloud_entities VALUES (?,?,?,?,?)',(actor,'notes',identifier,json.dumps(copy),now))
        db.execute('INSERT OR IGNORE INTO icloud_entity_tombstones VALUES (?,?,?,?)',(owner,'notes',note['id'],now))
        db.execute("DELETE FROM icloud_entities WHERE owner=? AND kind='notes' AND id=?",(owner,note['id']))
        db.execute('DELETE FROM icloud_note_pins WHERE resource_owner=? AND note_id=?',(owner,note['id']))
        db.execute('''DELETE FROM icloud_note_hidden WHERE note_id=? AND share_id IN
            (SELECT id FROM icloud_note_shares WHERE owner=?)''',(note['id'],owner))
        db.execute('''DELETE FROM icloud_note_personal WHERE kind='notes' AND item_id=? AND share_id IN
            (SELECT id FROM icloud_note_shares WHERE owner=?)''',(note['id'],owner))
    for identifier in folders:
        db.execute('INSERT OR IGNORE INTO icloud_entity_tombstones VALUES (?,?,?,?)',(owner,'folders',identifier,now))
        db.execute("DELETE FROM icloud_entities WHERE owner=? AND kind='folders' AND id=?",(owner,identifier))
    note_sharing.revoke_deleted(db,owner)
