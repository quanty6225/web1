"""Workspace trash, irreversible erasure and durable file cleanup."""
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from fastapi import HTTPException
from lxml import etree

RETENTION = 25 * 86400
ROOT = '/6302022/account/trash'


def initialize(db):
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS bc_erased(workspace TEXT, recording TEXT, route TEXT,
            erased_at REAL, PRIMARY KEY(workspace,recording));
        CREATE TABLE IF NOT EXISTS bc_file_cleanup(id TEXT PRIMARY KEY, storage TEXT NOT NULL DEFAULT 'uploads');
        ''')
        if 'storage' not in {row['name'] for row in c.execute('PRAGMA table_info(bc_file_cleanup)')}:
            c.execute("ALTER TABLE bc_file_cleanup ADD COLUMN storage TEXT NOT NULL DEFAULT 'uploads'")


def erased(c, owner, identifier):
    return c.execute('SELECT 1 FROM bc_erased WHERE workspace=? AND recording=?', (owner, identifier)).fetchone() is not None


def records(c, owner):
    from record_operations import DATA, metadata
    from card_table import columns_for
    identifiers = set(DATA['records']) | set(columns_for(c, owner))
    identifiers.update(row['id'] for row in c.execute('SELECT id FROM bc_records WHERE owner=?', (owner,)))
    return {identifier: record for identifier in identifiers if (record := metadata(c, owner, identifier))}


def entries(c, owner):
    from record_operations import metadata, fields_for
    result = []
    for row in c.execute('SELECT route,payload,updated FROM bc_mutations WHERE owner=? AND kind="record"', (owner,)):
        state = json.loads(row['payload'])
        if state.get('_record_status') != 'trashed':
            continue
        record = metadata(c, owner, row['route'].rsplit('/', 1)[-1])
        if record:
            fields = fields_for(c, owner, record)
            # Older local DELETE writes did not store _status_at. Their persisted
            # update time is the only available retention anchor, not today's time.
            result.append((record, fields, fields.get('_status_at', row['updated'])))
    return sorted(result, key=lambda item: (item[2], item[0]['id']))


def preserve_stamp(c, owner, record, state):
    if state.get('_record_status') in ('trashed', 'archived') and '_status_at' not in state:
        row = c.execute('SELECT updated FROM bc_mutations WHERE owner=? AND route=? AND kind="record"', (owner, record['url'])).fetchone()
        if row:
            state['_status_at'] = row['updated']


def children(c, owner, catalog):
    from card_table import columns_for, parent_columns, source_cards
    from record_operations import fields_for
    parents = parent_columns(columns_for(c, owner)); result = {}
    for identifier, record in catalog.items():
        parent = record['parent'].rsplit('/', 1)[-1]
        if record['kind'] == 'card_tables/columns':
            parent = parents.get(identifier, parent)
        elif record['kind'] == 'card_tables/cards':
            fields = fields_for(c, owner, record)
            parent = fields.get('_column_id') or source_cards().get(identifier, {}).get('column') or parent
            moved = c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="moves"', (owner, record['url'] + '/moves')).fetchone()
            if moved:
                parent = json.loads(moved['payload']).get('column_id', parent)
        result.setdefault(parent, []).append(identifier)
    return result


def references(c, owner):
    """Surviving recordings, comments and Chat protect shared upload bytes."""
    values = [row['data'] + row['body'] for row in c.execute('SELECT data,body FROM bc_records WHERE owner=?', (owner,))]
    values.extend(row['payload'] for row in c.execute('SELECT payload FROM bc_mutations WHERE owner=?', (owner,)))
    values.extend(row['body'] for row in c.execute('SELECT body FROM bc_comments WHERE owner=?', (owner,)))
    values.extend(row['body'] for row in c.execute('SELECT body FROM bc_chat_lines WHERE owner=?', (owner,)))
    return '\n'.join(values)


def erase(c, owner, identifier, now):
    from record_operations import fields_for
    catalog = records(c, owner)
    if identifier not in catalog:
        raise HTTPException(404, 'Item not found')
    descendants = children(c, owner, catalog); pending = [identifier]; selected = set()
    while pending:
        key = pending.pop()
        if key in selected:
            continue
        selected.add(key); pending.extend(descendants.get(key, ()))
    return erase_records(c, owner, catalog, selected, now)


def erase_records(c, owner, catalog, selected, now):
    from record_operations import fields_for
    possible_files = set()
    for key in selected:
        record = catalog[key]; fields = fields_for(c, owner, record); route = record['url']
        possible_files.update(value for value in [fields.get('_file_id'), *fields.get('_versions', [])] if value)
        text = json.dumps(fields) + '\n'.join(row['body'] for row in c.execute('SELECT body FROM bc_comments WHERE owner=? AND route=?', (owner, route)))
        possible_files.update(re.findall(r'/files/([^/"\\\s]+)', text))
        c.execute('INSERT OR IGNORE INTO bc_erased VALUES(?,?,?,?)', (owner, key, route, now))
        c.execute('DELETE FROM bc_records WHERE owner=? AND id=?', (owner, key))
        c.execute('DELETE FROM bc_comments WHERE owner=? AND route=?', (owner, route))
        c.execute('DELETE FROM bc_mutations WHERE owner=? AND (route=? OR route LIKE ?)', (owner, route, route + '/%'))
        c.execute('DELETE FROM bc_boosts WHERE workspace=? AND route=?', (owner, route))
        c.execute('DELETE FROM bc_thread_subscriptions WHERE workspace=? AND recording=?', (owner, key))
        c.execute('DELETE FROM bc_settings WHERE name=?', ('subscription:' + owner + ':' + key,))
        c.execute('DELETE FROM bc_bubble_ups WHERE workspace=? AND route=?', (owner, route))
        c.execute('DELETE FROM bc_column_views WHERE workspace=? AND column_id=?', (owner, key))
        c.execute('DELETE FROM bc_event_reads WHERE event IN (SELECT id FROM bc_events WHERE workspace=? AND route=?)', (owner, route))
        c.execute('DELETE FROM bc_event_recipients WHERE event IN (SELECT id FROM bc_events WHERE workspace=? AND route=?)', (owner, route))
        c.execute('DELETE FROM bc_events WHERE workspace=? AND route=?', (owner, route))
        c.execute('DELETE FROM bc_settings WHERE owner=? AND name=?', (owner, 'card-column-' + key))
        # Personal bookmarks store a recording_path, including per-member owners.
        for row in c.execute('SELECT owner,route,payload FROM bc_mutations WHERE kind="bookmarks"').fetchall() if record.get('is_new') else ():
            if json.loads(row['payload']).get('recording_path') == route and c.execute('SELECT 1 FROM bc_members WHERE workspace=? AND account=?', (owner, row['owner'])).fetchone():
                c.execute('DELETE FROM bc_mutations WHERE owner=? AND route=? AND kind="bookmarks"', (row['owner'], row['route']))
    queue_unused_files(c, owner, possible_files)
    return len(selected)


def queue_unused_files(c, owner, possible_files):
    remaining = references(c, owner)
    for file_id in possible_files:
        if file_id in remaining:
            continue
        if c.execute('SELECT 1 FROM bc_files WHERE owner=? AND id=?', (owner, file_id)).fetchone():
            c.execute('INSERT OR IGNORE INTO bc_file_cleanup(id) VALUES(?)', (file_id,))
            c.execute('DELETE FROM bc_files WHERE owner=? AND id=?', (owner, file_id))


def cleanup_files(db, data_root):
    # Commit the erasure before touching bytes; interrupted unlinks remain queued.
    with db() as c:
        for row in c.execute('SELECT id,storage FROM bc_file_cleanup').fetchall():
            identifier = row['id']
            if Path(identifier).name != identifier or identifier in ('.', '..'):
                raise ValueError('Invalid stored upload identifier')
            if row['storage'] not in ('uploads', 'private-ping-files', 'private-ping-covers'):
                raise ValueError('Invalid stored upload directory')
            (Path(data_root) / row['storage'] / identifier).unlink(missing_ok=True)
            c.execute('DELETE FROM bc_file_cleanup WHERE id=?', (identifier,))


def cleanup(db, data_root, now):
    with db() as c:
        c.execute('PRAGMA secure_delete=ON'); c.execute('BEGIN IMMEDIATE')
        owners = [row['owner'] for row in c.execute('SELECT DISTINCT owner FROM bc_mutations WHERE kind="record"')]
        for owner in owners:
            for record, fields, stamp in entries(c, owner):
                if stamp + RETENTION <= now and not erased(c, owner, record['id']):
                    erase(c, owner, record['id'], now)
    cleanup_files(db, data_root)


def mutate(c, account, path, method):
    match = re.fullmatch(ROOT + r'/(\d+)', path)
    if not match and path != ROOT:
        return None
    from workspaces import manager
    manager(account, True)
    if method != 'DELETE':
        raise HTTPException(405, 'Use DELETE to empty the trash.')
    c.execute('PRAGMA secure_delete=ON'); c.execute('BEGIN IMMEDIATE')
    available = {record['id']: record for record, fields, stamp in entries(c, account['workspace_id'])}
    identifiers = [match[1]] if match else list(available)
    if match and match[1] not in available:
        raise HTTPException(404, 'Trashed item not found')
    count = 0
    for identifier in identifiers:
        if not erased(c, account['workspace_id'], identifier):
            count += erase(c, account['workspace_id'], identifier, time.time())
    return {'redirect': ROOT, 'erased': count, 'activity_handled': True}


def render(tree, path, c, account):
    from record_operations import metadata, fields_for, PREFIX, TITLE, BODY, text_value
    from column_lifecycle import action, render_notice
    owner = account['workspace_id']
    if account['role'] != 'owner':
        for link in tree.xpath('//a[@href="' + ROOT + '"]'):
            link.getparent().remove(link)
    if path != ROOT:
        record = metadata(c, owner, path.rsplit('/', 1)[-1])
        if record and record['url'] == path and record['kind'] != 'card_tables/columns':
            state = fields_for(c, owner, record)
            if state.get('_record_status') in ('archived', 'trashed'):
                render_notice(tree, c, account, record, state)
        return
    targets = tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," global-trash ")]')
    if not targets:
        return
    target = targets[0]
    for child in list(target):
        target.remove(child)
    items = entries(c, owner)
    if not items:
        etree.SubElement(target, 'p', {'class': 'break text-subtle'}).text = 'The trash is empty'
        return
    def delete_button(container, url, label):
        form = etree.SubElement(container, 'form', {'action': url, 'method': 'post', 'data-turbo-confirm': 'Permanently delete these items? This cannot be undone.'})
        etree.SubElement(form, 'input', {'type': 'hidden', 'name': '_method', 'value': 'delete'})
        etree.SubElement(form, 'button', {'type': 'submit', 'class': 'btn btn--negative btn--sm'}).text = label
    delete_button(target, ROOT, 'Empty the trash')
    grid = etree.SubElement(target, 'div', {'class': 'card-grid margin-block-24'})
    previous_date = None
    for record, fields, stamp in items:
        date = datetime.fromtimestamp(stamp, timezone.utc)
        if date.date() != previous_date:
            divider = etree.SubElement(grid, 'div', {'class': 'date-divider'})
            etree.SubElement(divider, 'h3').text = date.strftime('%B %d, %Y')
            previous_date = date.date()
        row = etree.SubElement(grid, 'article', {'class': 'card', 'data-trashed-record': record['id']})
        if record['kind'] == 'card_tables/columns':
            row.set('data-trashed-column', record['id'])
        title = fields.get(PREFIX[record['kind']] + '[' + TITLE[record['kind']] + ']', record['title'])
        heading = etree.SubElement(row, 'h2', {'class': 'text-md'})
        etree.SubElement(heading, 'a', {'href': record['url'], 'class': 'decorated'}).text = title
        excerpt = text_value(fields.get(PREFIX[record['kind']] + '[' + BODY[record['kind']] + ']', ''))
        if excerpt:
            etree.SubElement(row, 'p', {'class': 'text-sm margin-block-8'}).text = excerpt[:360]
        paragraph = etree.SubElement(row, 'p', {'class': 'text-subtle'})
        paragraph.text = 'Trashed '
        etree.SubElement(paragraph, 'time', {'datetime': date.isoformat(), 'data-local': 'time-ago'}).text = date.strftime('%b %d, %Y at %H:%M UTC')
        action(row, record, 'active', 'Restore')
        delete_button(row, ROOT + '/' + record['id'], 'Delete permanently')
