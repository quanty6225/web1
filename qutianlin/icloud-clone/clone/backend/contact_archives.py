"""Local contact snapshots; restore atomically preserves an undo version."""
import hashlib,json,uuid


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS icloud_contact_archives (
      owner TEXT NOT NULL,id TEXT NOT NULL,created_at INTEGER NOT NULL,
      digest TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(owner,id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS icloud_contact_generations (
      owner TEXT PRIMARY KEY,generation INTEGER NOT NULL)''')


def generation(db,owner):
    row=db.execute('SELECT generation FROM icloud_contact_generations WHERE owner=?',(owner,)).fetchone()
    return row[0] if row else 0


def check_generation(db,owner,expected):
    current=generation(db,owner)
    if (expected is None and current>0) or (expected is not None and str(current)!=str(expected)):
        raise ValueError('Contacts were restored in another window. Reload before making changes.')


def snapshot(db,owner,now,force=False):
    entries=[{'kind':row['kind'],'id':row['id'],'payload':json.loads(row['payload'])} for row in db.execute(
        "SELECT kind,id,payload FROM icloud_entities WHERE owner=? AND kind IN ('contacts','contact_lists') ORDER BY kind,id",(owner,))]
    settings=db.execute("SELECT payload FROM icloud_entities WHERE owner=? AND kind='settings' AND id='contacts'",(owner,)).fetchone()
    payload={'entries':entries,'my_card':json.loads(settings[0]).get('my_card') if settings else None}
    encoded=json.dumps(payload,sort_keys=True);digest=hashlib.sha256(encoded.encode()).hexdigest()
    last=db.execute('SELECT id,digest FROM icloud_contact_archives WHERE owner=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(owner,)).fetchone()
    if not force and last and last['digest']==digest:return last['id']
    identifier=uuid.uuid4().hex
    db.execute('INSERT INTO icloud_contact_archives VALUES (?,?,?,?,?)',(owner,identifier,now,digest,encoded))
    return identifier


def versions(db,owner):
    return [{'id':row['id'],'created_at':row['created_at']} for row in db.execute(
        'SELECT id,created_at FROM icloud_contact_archives WHERE owner=? ORDER BY created_at DESC,rowid DESC',(owner,))]


def restore(db,owner,identifier,expected,now):
    check_generation(db,owner,expected)
    row=db.execute('SELECT payload FROM icloud_contact_archives WHERE owner=? AND id=?',(owner,identifier)).fetchone()
    if not row:raise LookupError('Contact archive not found.')
    payload=json.loads(row[0]);undo=snapshot(db,owner,now,force=True)
    db.execute("DELETE FROM icloud_entities WHERE owner=? AND kind IN ('contacts','contact_lists')",(owner,))
    for entry in payload['entries']:
        db.execute('INSERT INTO icloud_entities VALUES (?,?,?,?,?)',(owner,entry['kind'],entry['id'],json.dumps(entry['payload']),now//1000))
    setting=db.execute("SELECT payload FROM icloud_entities WHERE owner=? AND kind='settings' AND id='contacts'",(owner,)).fetchone()
    preferences=json.loads(setting[0]) if setting else {'id':'contacts'}
    preferences.pop('my_card',None)
    if payload.get('my_card'):preferences['my_card']=payload['my_card']
    db.execute('INSERT INTO icloud_entities VALUES (?,?,?,?,?) ON CONFLICT(owner,kind,id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',(owner,'settings','contacts',json.dumps(preferences),now//1000))
    db.execute('INSERT INTO icloud_contact_generations VALUES (?,1) ON CONFLICT(owner) DO UPDATE SET generation=generation+1',(owner,))
    return {'undo_id':undo,'generation':generation(db,owner)}
