"""Permanent deletion for the observed Free and sample project flows."""
import json
import re
import time
from functools import lru_cache
from pathlib import Path
from fastapi import HTTPException
from trash import erased


@lru_cache(maxsize=1)
def source_projects():
    from task_reports import project_names
    return project_names()


@lru_cache(maxsize=8)
def source_tools(bucket):
    routes = json.loads((Path(__file__).parent / 'frontend/routes.json').read_text())
    result = {}
    for path in routes:
        match = re.fullmatch(r'/6302022/buckets/' + re.escape(bucket) + r'/(message_boards|todosets|vaults|schedules|chats|card_tables)/(\d+)', path)
        if match:
            result[match[2]] = {'id': match[2], 'url': path, 'kind': match[1]}
    return result


def is_project_path(path, bucket):
    return any(path == prefix or path.startswith(prefix + '/') for prefix in ('/6302022/projects/' + bucket, '/6302022/buckets/' + bucket))


def authorize(c, account, bucket):
    owner = account['workspace_id']
    if bucket not in source_projects() or erased(c, owner, bucket):
        raise HTTPException(404, 'Project not found')
    member = c.execute('SELECT role,access FROM bc_members WHERE workspace=? AND account=?', (owner, account['account_id'])).fetchone()
    if not member or member['role'] == 'viewer':
        raise HTTPException(403, 'You cannot delete this project.')
    if member['role'] != 'owner' and member['access'] != 'all' and not c.execute('SELECT 1 FROM bc_project_members WHERE workspace=? AND project=? AND account=?', (owner, bucket, account['account_id'])).fetchone():
        raise HTTPException(403, 'You do not have access to this project.')
    # The two seeded projects belong to the original local workspace creator.
    # Ownership transfers must not silently change that creator identity.
    if member['role'] not in ('owner', 'admin') and account['account_id'] != owner:
        raise HTTPException(403, 'Only the project creator, an administrator, or an account owner can delete this project.')


def erase_project(c, owner, bucket):
    from trash import records, erase_records, queue_unused_files
    from tool_operations import TYPES
    now = time.time(); catalog = records(c, owner)
    selected = {key for key, record in catalog.items() if record['bucket'] == bucket}
    tools = dict(source_tools(bucket))
    for row in c.execute('SELECT * FROM bc_tools WHERE owner=? AND bucket=?', (owner, bucket)):
        kind = TYPES[row['kind']][0]
        tools[row['id']] = {'id': row['id'], 'kind': kind, 'url': '/6302022/buckets/' + bucket + '/' + kind + '/' + row['id']}
    rooms = [key for key, tool in tools.items() if tool['kind'] == 'chats']
    possible_files = set()
    for room in rooms:
        for row in c.execute('SELECT body FROM bc_chat_lines WHERE owner=? AND room=?', (owner, room)):
            possible_files.update(re.findall(r'/files/([^/"\\\s]+)', row['body']))
        c.execute('DELETE FROM bc_chat_lines WHERE owner=? AND room=?', (owner, room))
    erase_records(c, owner, catalog, selected, now)
    for row in c.execute('SELECT id,parent,data,body FROM bc_records WHERE owner=?', (owner,)).fetchall():
        if is_project_path(row['parent'], bucket) or is_project_path(json.loads(row['data']).get('url', ''), bucket):
            possible_files.update(re.findall(r'/files/([^/"\\\s]+)', row['body'] + row['data']))
            c.execute('DELETE FROM bc_records WHERE owner=? AND id=?', (owner, row['id']))
    for table in ('bc_mutations', 'bc_comments'):
        for row in c.execute(f'SELECT DISTINCT route FROM {table} WHERE owner=?', (owner,)).fetchall():
            if is_project_path(row['route'], bucket):
                c.execute(f'DELETE FROM {table} WHERE owner=? AND route=?', (owner, row['route']))
    # Events/reminders may target tools rather than individual recordings.
    for table in ('bc_events', 'bc_bubble_ups', 'bc_boosts'):
        for row in c.execute(f'SELECT DISTINCT route FROM {table} WHERE workspace=?', (owner,)).fetchall():
            if is_project_path(row['route'], bucket) or any(row['route'].endswith('/chats/' + room) for room in rooms):
                if table == 'bc_events':
                    for relation in ('bc_event_reads', 'bc_event_recipients'):
                        c.execute(f'DELETE FROM {relation} WHERE event IN (SELECT id FROM bc_events WHERE workspace=? AND route=?)', (owner, row['route']))
                c.execute(f'DELETE FROM {table} WHERE workspace=? AND route=?', (owner, row['route']))
    for tool in tools.values():
        c.execute('INSERT OR IGNORE INTO bc_erased VALUES(?,?,?,?)', (owner, tool['id'], tool['url'], now))
    c.execute('DELETE FROM bc_tools WHERE owner=? AND bucket=?', (owner, bucket))
    c.execute('DELETE FROM bc_project_members WHERE workspace=? AND project=?', (owner, bucket))
    c.execute('DELETE FROM bc_invites WHERE workspace=? AND project=?', (owner, bucket))
    for name in ('project-color:', 'project-star:'):
        c.execute('DELETE FROM bc_settings WHERE name=?', (name + owner + ':' + bucket,))
    for row in c.execute('SELECT id,buckets FROM bc_exports WHERE owner=?', (owner,)).fetchall():
        remaining = [key for key in json.loads(row['buckets']) if key != bucket]
        if remaining:
            c.execute('UPDATE bc_exports SET buckets=? WHERE id=?', (json.dumps(remaining), row['id']))
        else:
            c.execute('DELETE FROM bc_exports WHERE id=?', (row['id'],))
    c.execute('INSERT INTO bc_erased VALUES(?,?,?,?)', (owner, bucket, '/6302022/projects/' + bucket, now))
    queue_unused_files(c, owner, possible_files)
    return rooms


def mutate(c, account, path, method):
    match = re.fullmatch(r'/6302022/projects/(\d+)/status/(\w+)', path)
    legacy = re.fullmatch(r'/6302022/projects/(\d+)', path) if method == 'DELETE' else None
    if not match and not legacy:
        return None
    bucket = (match or legacy)[1]
    c.execute('PRAGMA secure_delete=ON'); c.execute('BEGIN IMMEDIATE')
    authorize(c, account, bucket)
    if match and method != 'PUT':
        raise HTTPException(405, 'Use PUT to change this project status.')
    if match and match[2] != 'deleted':
        raise HTTPException(409, 'Archiving is not available for this Free or sample project.')
    rooms = erase_project(c, account['workspace_id'], bucket)
    return {'redirect': '/6302022/', 'chat_rooms': rooms, 'activity_handled': True}


def render(tree, c, account):
    removed = {row['recording'] for row in c.execute('SELECT recording FROM bc_erased WHERE workspace=? AND route="/6302022/projects/" || recording', (account['workspace_id'],))}
    if not removed:
        return
    from workspaces import filter_tree
    allowed = [key for key in source_projects() if key not in removed and (account.get('projects') is None or key in account['projects'])]
    filter_tree(tree, {**account, 'projects': allowed})
    for field in tree.xpath('//input[@name="bucket_ids[]"]|//option[@value]'):
        if field.get('value') not in removed:
            continue
        wrapper = next((p for p in field.iterancestors() if p.tag == 'label'), field)
        if wrapper.getparent() is not None:
            wrapper.getparent().remove(wrapper)
