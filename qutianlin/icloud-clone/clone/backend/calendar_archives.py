"""Atomic local Calendar/legacy Reminders archives, with restore generations."""
import hashlib,json,uuid

KINDS=('calendars','events','lists','reminders')
SQL_KINDS="('calendars','events','lists','reminders')"


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS icloud_calendar_archives (
      owner TEXT NOT NULL,id TEXT NOT NULL,created_at INTEGER NOT NULL,
      digest TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(owner,id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS icloud_calendar_generations (
      owner TEXT PRIMARY KEY,generation INTEGER NOT NULL)''')


def generation(db,owner):
    row=db.execute('SELECT generation FROM icloud_calendar_generations WHERE owner=?',(owner,)).fetchone()
    return row[0] if row else 0


def check_generation(db,owner,expected):
    current=generation(db,owner)
    if (expected is None and current>0) or (expected is not None and str(current)!=str(expected)):
        raise FileExistsError('Calendars and reminders were restored in another window. Reload before making changes.')


def snapshot(db,owner,now,force=False):
    entries=[{'kind':r['kind'],'id':r['id'],'payload':json.loads(r['payload'])} for r in db.execute(
        f'SELECT kind,id,payload FROM icloud_entities WHERE owner=? AND kind IN {SQL_KINDS} ORDER BY kind,id',(owner,))]
    encoded=json.dumps(entries,sort_keys=True);digest=hashlib.sha256(encoded.encode()).hexdigest()
    last=db.execute('SELECT id,digest,created_at FROM icloud_calendar_archives WHERE owner=? ORDER BY rowid DESC LIMIT 1',(owner,)).fetchone()
    if not force and last and last['digest']==digest:return last['id']
    # Keep chronological order even when a caller or system clock moves back.
    if last:now=max(now,last['created_at'])
    identifier=uuid.uuid4().hex
    db.execute('INSERT INTO icloud_calendar_archives VALUES (?,?,?,?,?)',(owner,identifier,now,digest,encoded))
    return identifier


def versions(db,owner):
    return [{'id':r['id'],'created_at':r['created_at']} for r in db.execute(
        'SELECT id,created_at FROM icloud_calendar_archives WHERE owner=? ORDER BY created_at DESC,rowid DESC',(owner,))]


def restore(db,actor,identifier,expected,now):
    owner=actor['account_id'];check_generation(db,owner,expected)
    row=db.execute('SELECT payload FROM icloud_calendar_archives WHERE owner=? AND id=?',(owner,identifier)).fetchone()
    if not row:raise LookupError('Calendar archive not found.')
    entries=json.loads(row[0]);undo=snapshot(db,owner,now,force=True)
    from backend.event_invitations import revoke as revoke_events
    revoke_events(db,owner)
    from backend.calendar_sharing import revoke
    revoke(db,actor)
    # Invalidate both directions of sharing. Archives never contain grants.
    db.execute('DELETE FROM icloud_reminder_members WHERE share_id IN (SELECT id FROM icloud_reminder_shares WHERE owner=?)',(owner,))
    db.execute('UPDATE icloud_reminder_shares SET active=0 WHERE owner=?',(owner,))
    db.execute('DELETE FROM icloud_reminder_members WHERE account_id=? OR (account_id IS NULL AND email=?)',(owner,actor['email_normalized']))
    db.execute('UPDATE icloud_reminder_shares SET active=0 WHERE NOT EXISTS (SELECT 1 FROM icloud_reminder_members WHERE share_id=icloud_reminder_shares.id)')
    current=db.execute(f'SELECT kind,id FROM icloud_entities WHERE owner=? AND kind IN {SQL_KINDS}',(owner,)).fetchall()
    for entry in current:
        db.execute('INSERT OR IGNORE INTO icloud_entity_tombstones VALUES (?,?,?,?)',(owner,entry['kind'],entry['id'],now//1000))
    db.execute(f'DELETE FROM icloud_entities WHERE owner=? AND kind IN {SQL_KINDS}',(owner,))
    for entry in entries:
        data={k:v for k,v in entry['payload'].items() if k not in ('_sharing','_original_id')}
        db.execute('INSERT INTO icloud_entities VALUES (?,?,?,?,?)',(owner,entry['kind'],entry['id'],json.dumps(data),now//1000))
        db.execute('DELETE FROM icloud_entity_tombstones WHERE owner=? AND kind=? AND id=?',(owner,entry['kind'],entry['id']))
    db.execute('INSERT INTO icloud_calendar_generations VALUES (?,1) ON CONFLICT(owner) DO UPDATE SET generation=generation+1',(owner,))
    return {'undo_id':undo,'generation':generation(db,owner)}
