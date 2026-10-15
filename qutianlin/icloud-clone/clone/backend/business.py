"""Site-owned migrations and account-scoped business records."""
import json, sqlite3, time
from pathlib import Path

PHOTO_RETENTION_SECONDS = 30 * 24 * 60 * 60

def expire_notes(db, owner, now):
 db.execute('BEGIN IMMEDIATE')
 rows=db.execute("""SELECT id FROM icloud_entities WHERE owner=? AND kind='notes'
   AND json_extract(payload,'$.deleted')=1
   AND json_extract(payload,'$.deleted_at') IS NOT NULL
   AND json_extract(payload,'$.deleted_at')<=?""",(owner,now-PHOTO_RETENTION_SECONDS)).fetchall()
 for row in rows:
  db.execute('INSERT OR IGNORE INTO icloud_entity_tombstones VALUES (?,?,?,?)',(owner,'notes',row['id'],now))
  db.execute("DELETE FROM icloud_entities WHERE owner=? AND kind='notes' AND id=?",(owner,row['id']))
 db.commit()

def remove_photo_references(db, owner, photo_id):
 for row in db.execute("SELECT id,payload FROM icloud_entities WHERE owner=? AND kind='albums'",(owner,)).fetchall():
  album=json.loads(row['payload'])
  if photo_id in album.get('photos',[]):
   album['photos']=[identifier for identifier in album['photos'] if identifier!=photo_id]
   db.execute("UPDATE icloud_entities SET payload=?,updated_at=? WHERE owner=? AND kind='albums' AND id=?",(json.dumps(album),int(time.time()),owner,row['id']))

def expire_photos(db, owner, now):
 """Remove only this owner's photos after their 30-day recovery period."""
 db.execute('BEGIN IMMEDIATE')
 rows=db.execute("""SELECT id,payload FROM icloud_entities WHERE owner=? AND kind='photos'
   AND json_extract(payload,'$.deleted')=1
   AND json_extract(payload,'$.deleted_at') IS NOT NULL
   AND json_extract(payload,'$.deleted_at')<=?""",(owner,now-PHOTO_RETENTION_SECONDS)).fetchall()
 removed=[]
 for row in rows:
  remove_photo_references(db,owner,row['id'])
  db.execute("DELETE FROM icloud_entities WHERE owner=? AND kind='photos' AND id=?",(owner,row['id']))
  removed.append(json.loads(row['payload']))
 db.commit()
 return removed

def migrate(db):
 from backend.alarms import migrate as migrate_alarms
 migrate_alarms(db)
 from backend.event_attachments import migrate as migrate_event_attachments
 migrate_event_attachments(db)
 from backend.event_invitations import migrate as migrate_event_invitations
 migrate_event_invitations(db)
 from backend.calendar_sharing import migrate as migrate_calendar_sharing
 migrate_calendar_sharing(db)
 from backend.calendar_archives import migrate as migrate_calendar_archives
 migrate_calendar_archives(db)
 from backend.reminder_sharing import migrate as migrate_reminder_sharing
 migrate_reminder_sharing(db)
 from backend.note_sharing import migrate as migrate_note_sharing
 migrate_note_sharing(db)
 from backend.contact_archives import migrate as migrate_contact_archives
 migrate_contact_archives(db)
 db.execute('''CREATE TABLE IF NOT EXISTS icloud_entity_tombstones (
   owner TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL,
   deleted_at INTEGER NOT NULL, PRIMARY KEY(owner,kind,id))''')
 db.execute('''CREATE TABLE IF NOT EXISTS icloud_help_feedback (
   owner TEXT NOT NULL, page TEXT NOT NULL, helpful INTEGER NOT NULL,
   comment TEXT NOT NULL, updated_at INTEGER NOT NULL,
   PRIMARY KEY(owner,page))''')
 db.execute('''
 CREATE TABLE IF NOT EXISTS icloud_entities (
   owner TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL,
   payload TEXT NOT NULL, updated_at INTEGER NOT NULL,
   PRIMARY KEY(owner,kind,id))''')
 db.execute('''
 CREATE TABLE IF NOT EXISTS icloud_account_seed (
   owner TEXT PRIMARY KEY, seeded_at INTEGER NOT NULL)
 ''')
 from backend.note_sharing import repair_shadowed_shares
 repair_shadowed_shares(db)

def seed_demo(db, owner):
 seed_defaults(db,owner)
 # Each fixture addition has its own migration marker: a restart must not
 # recreate unrelated records that the local account has deleted.
 add_fixtures(db,owner,'drive-v1',('files',))
 sync_media(db,owner)
 sync_find(db,owner)
 marker='v2:'+owner
 if db.execute('SELECT 1 FROM icloud_account_seed WHERE owner=?',(marker,)).fetchone():return
 folder=Path(__file__).resolve().parents[1]/'fixtures'
 for path in folder.glob('*.json'):
  for item in json.loads(path.read_text()):
   db.execute('INSERT OR IGNORE INTO icloud_entities VALUES (?,?,?,?,?)',(owner,path.stem,item['id'],json.dumps(item),int(time.time())))
   if path.stem=='photos':
    row=db.execute('SELECT payload FROM icloud_entities WHERE owner=? AND kind=? AND id=?',(owner,'photos',item['id'])).fetchone();old=json.loads(row[0]);old['portrait']=item.get('portrait',False)
    db.execute('UPDATE icloud_entities SET payload=? WHERE owner=? AND kind=? AND id=?',(json.dumps(old),owner,'photos',item['id']))
 db.execute('INSERT INTO icloud_account_seed VALUES (?,?)',(marker,int(time.time())))
 db.commit()

def add_fixtures(db,owner,version,kinds):
 marker=version+':'+owner
 if db.execute('SELECT 1 FROM icloud_account_seed WHERE owner=?',(marker,)).fetchone():return
 folder=Path(__file__).resolve().parents[1]/'fixtures'
 for kind in kinds:
  for item in json.loads((folder/(kind+'.json')).read_text()):
   db.execute('INSERT OR IGNORE INTO icloud_entities VALUES (?,?,?,?,?)',(owner,kind,item['id'],json.dumps(item),int(time.time())))
 db.execute('INSERT INTO icloud_account_seed VALUES (?,?)',(marker,int(time.time())))
 db.commit()

def seed_defaults(db,owner):
 add_fixtures(db,owner,'empty-defaults-v1',('calendars','lists','folders'))

def sync_find(db,owner):
 marker='find-device-identity-v2:'+owner
 if db.execute('SELECT 1 FROM icloud_account_seed WHERE owner=?',(marker,)).fetchone():return
 fixtures=json.loads((Path(__file__).resolve().parents[1]/'fixtures/devices.json').read_text())
 for device in fixtures:
  row=db.execute("SELECT payload FROM icloud_entities WHERE owner=? AND kind='devices' AND id=?",(owner,device['id'])).fetchone()
  if not row:continue
  data=json.loads(row[0]);data.update({key:device[key] for key in ('order','device_class','capabilities','activation_locked')})
  db.execute("UPDATE icloud_entities SET payload=? WHERE owner=? AND kind='devices' AND id=?",(json.dumps(data),owner,device['id']))
 db.execute('INSERT INTO icloud_account_seed VALUES (?,?)',(marker,int(time.time())))
 db.commit()

def sync_media(db,owner):
 marker='detail-media-v1:'+owner
 if db.execute('SELECT 1 FROM icloud_account_seed WHERE owner=?',(marker,)).fetchone():return
 path=Path(__file__).resolve().parents[1]/'fixtures/photos.json'
 photos=json.loads(path.read_text())
 if not any(p.get('detail_src') for p in photos):return
 for photo in photos:
  row=db.execute('SELECT payload FROM icloud_entities WHERE owner=? AND kind=? AND id=?',(owner,'photos',photo['id'])).fetchone()
  if not row:continue
  data=json.loads(row[0]);data.update({k:photo[k] for k in ('detail_src','video_src','live_src','duration') if k in photo})
  db.execute('UPDATE icloud_entities SET payload=? WHERE owner=? AND kind=? AND id=?',(json.dumps(data),owner,'photos',photo['id']))
 db.execute('INSERT INTO icloud_account_seed VALUES (?,?)',(marker,int(time.time())))
 db.commit()
