"""Durable Wormholes and permission-checked relocation of complete card trees."""
import copy
import json
import re
import secrets
import time
from datetime import datetime
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from lxml import etree, html

COLORS = ('white', 'red', 'orange', 'yellow', 'green', 'blue', 'aqua', 'purple', 'gray', 'pink', 'brown')


def initialize(db):
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS bc_wormholes(
            id TEXT,workspace TEXT,board TEXT,column_id TEXT,color TEXT,
            PRIMARY KEY(workspace,id));
            CREATE TABLE IF NOT EXISTS bc_card_relocations(
            workspace TEXT,old_path TEXT,new_path TEXT,PRIMARY KEY(workspace,old_path));''')


def board_access(c, account, board):
    from workspaces import allows
    from card_table import columns_for
    from trash import erased
    if not allows(account, board):
        raise HTTPException(403, 'You cannot access the destination project.')
    bucket = board.split('/')[3]
    project = c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="project"', (account['workspace_id'], '/6302022/projects/' + bucket)).fetchone()
    if erased(c, account['workspace_id'], bucket) or project and json.loads(project['payload']).get('_status') == 'trashed':
        raise HTTPException(404, 'Project not found')
    if not any(column['board'] == board for column in columns_for(c, account['workspace_id']).values()):
        raise HTTPException(404, 'Card Table not found')
    tool = c.execute('SELECT active FROM bc_tools WHERE owner=? AND id=?', (account['workspace_id'], board.rsplit('/', 1)[-1])).fetchone()
    if tool and not tool['active']:
        raise HTTPException(404, 'Card Table not found')


def destination(c, account, board, column_id):
    from card_table import columns_for
    from column_lifecycle import require_active
    board_access(c, account, board)
    columns = columns_for(c, account['workspace_id'])
    column = columns.get(column_id)
    if not column or column.get('deleted'):
        raise HTTPException(404, 'Destination column not found')
    board_access(c, account, column['board'])
    if column['board'] == board:
        raise HTTPException(422, 'Choose another Card Table for this Wormhole.')
    require_active(columns, column_id)
    return column


def available(c, account, board):
    rows = c.execute('SELECT * FROM bc_wormholes WHERE workspace=? AND board=? ORDER BY rowid', (account['workspace_id'], board)).fetchall()
    result = []
    for row in rows:
        try:
            column = destination(c, account, board, row['column_id'])
        except HTTPException:
            continue
        result.append((dict(row), column))
    return result


def relocate(c, account, record, column):
    from record_operations import DATA, metadata, fields_for, PREFIX
    from card_table import is_done
    owner = account['workspace_id']
    old_bucket, new_bucket = record['bucket'], column['board'].split('/')[3]
    catalog = {key: metadata(c, owner, key) for key in DATA['records']}
    for row in c.execute('SELECT id FROM bc_records WHERE owner=?', (owner,)):
        catalog[row['id']] = metadata(c, owner, row['id'])
    selected = {record['id']: record}
    while True:
        children = {key: value for key, value in catalog.items() if value and key not in selected and value['parent'] in {r['url'] for r in selected.values()}}
        if not children:
            break
        selected.update(children)
    routes = {value['url']: value['url'].replace('/buckets/' + old_bucket + '/', '/buckets/' + new_bucket + '/', 1) for value in selected.values()}
    for item in selected.values():
        old, new = item['url'], routes[item['url']]
        state = fields_for(c, owner, item)
        parent = column['board'] if item['id'] == record['id'] else routes.get(item['parent'], item['parent'])
        if item['id'] == record['id']:
            state['_column_id'] = column['id']
        # Keep historical authorship, but never carry assignments to people who
        # cannot read the destination project.
        from thread_notifications import accessible_member
        for suffix in ('assignees', 'completion_subscribers'):
            key = PREFIX[item['kind']] + '[' + suffix + ']'
            if key in state:
                people = str(state[key]).split(',')
                state[key] = ','.join(person for person in people if accessible_member(c, owner, owner if person == '53382586' else person, new))
        provenance = {}
        if not item.get('is_new'):
            from card_table import source_cards
            source = source_cards().get(item['id'])
            if source:
                node = html.fromstring(source['html'])
                author = node.get('data-creator-id')
                if author:
                    provenance['author'] = owner if author == '53382586' else author
                stamps = node.xpath('.//time/@datetime')
                if stamps:
                    provenance['created'] = datetime.fromisoformat(stamps[0].replace('Z', '+00:00')).timestamp()
        data = {**item, **provenance, 'url': new, 'bucket': new_bucket, 'parent': parent, 'fields': state,
                'prototype': item.get('prototype', item['id']), 'created': item.get('created', 0),
                'relocated_source': item.get('relocated_source', not item.get('is_new', False)), 'is_new': True}
        data.update(provenance)
        c.execute('INSERT OR REPLACE INTO bc_records VALUES(?,?,?,?,?,?,?,?)', (item['id'], owner, parent, item['kind'], item['title'], item.get('body', ''), json.dumps(data), int(data['created'])))
        # Canonical recording URLs change with their project, while stable IDs,
        # comments, rich-text file URLs, subscriptions and Boosts are retained.
        if old != new:
            mutations = c.execute('SELECT * FROM bc_mutations WHERE owner=? AND (route=? OR route LIKE ?)', (owner, old, old + '/%')).fetchall()
            for row in mutations:
                target = new + row['route'][len(old):]
                c.execute('INSERT OR REPLACE INTO bc_mutations VALUES(?,?,?,?,?)', (owner, target, row['kind'], row['payload'], row['updated']))
                c.execute('DELETE FROM bc_mutations WHERE owner=? AND route=? AND kind=?', (owner, row['route'], row['kind']))
            c.execute('UPDATE bc_comments SET route=? WHERE owner=? AND route=?', (new, owner, old))
            for table in ('bc_events', 'bc_boosts', 'bc_bubble_ups'):
                c.execute(f'UPDATE {table} SET route=? || substr(route,?) WHERE workspace=? AND (route=? OR route LIKE ?)', (new, len(old) + 1, owner, old, old + '#%'))
            c.execute('DELETE FROM bc_card_relocations WHERE workspace=? AND old_path=?', (owner, new))
            c.execute('UPDATE bc_card_relocations SET new_path=? WHERE workspace=? AND new_path=?', (new, owner, old))
            c.execute('INSERT OR REPLACE INTO bc_card_relocations VALUES(?,?,?)', (owner, old, new))
        c.execute('INSERT OR REPLACE INTO bc_mutations VALUES(?,?,?,?,?)', (owner, new, 'record', json.dumps(state), int(time.time())))
    new = routes[record['url']]
    state = {'column_id': column['id'], 'position': 1}
    if is_done(column):
        state.update(completed_at=time.time(), completed_by=account['account_id'])
    c.execute('INSERT OR REPLACE INTO bc_mutations VALUES(?,?,?,?,?)', (owner, new + '/moves', 'moves', json.dumps(state), int(time.time())))
    from activity_search import emit
    from thread_notifications import subscribers
    from column_watching import audience
    moved = metadata(c, owner, record['id'])
    emit(c, account, new, fields_for(c, owner, moved).get('kanban_card[title]', record['title']), 'moved', subscribers(c, account, moved) | audience(c, account, column['id']))
    return {'redirect': new}


def move(c, account, record, wormhole_id):
    row = c.execute('SELECT * FROM bc_wormholes WHERE workspace=? AND id=?', (account['workspace_id'], wormhole_id)).fetchone()
    if not row:
        return None
    if record['parent'] != row['board']:
        raise HTTPException(404, 'Wormhole not found on this Card Table')
    column = destination(c, account, row['board'], row['column_id'])
    return relocate(c, account, record, column)


def install(app, db, require_user, csrf_check):
    @app.api_route('/6302022/buckets/{bucket}/card_tables/{board_id}/wormholes', methods=['POST'])
    @app.api_route('/6302022/buckets/{bucket}/card_tables/{board_id}/wormholes/{identifier}', methods=['POST', 'PATCH', 'PUT', 'DELETE'])
    async def save(bucket: str, board_id: str, request: Request, identifier: str = ''):
        from workspaces import writable
        account = require_user(request)
        writable(account)
        data = await request.json() if 'application/json' in request.headers.get('content-type', '') else await request.form()
        csrf_check(request, data)
        board = '/6302022/buckets/' + bucket + '/card_tables/' + board_id
        method = str(data.get('_method', request.method)).upper()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            board_access(c, account, board)
            row = c.execute('SELECT * FROM bc_wormholes WHERE workspace=? AND board=? AND id=?', (account['workspace_id'], board, identifier)).fetchone() if identifier else None
            if identifier and not row:
                raise HTTPException(404, 'Wormhole not found')
            if method == 'DELETE':
                c.execute('DELETE FROM bc_wormholes WHERE workspace=? AND id=?', (account['workspace_id'], identifier))
            else:
                column_id = str(data.get('column_id', row['column_id'] if row else ''))
                destination(c, account, board, column_id)
                color = str(data.get('color', row['color'] if row else 'purple'))
                if color not in COLORS:
                    raise HTTPException(422, 'Choose a supported color.')
                if not row and c.execute('SELECT COUNT(*) FROM bc_wormholes WHERE workspace=? AND board=?', (account['workspace_id'], board)).fetchone()[0] >= 4:
                    raise HTTPException(409, 'A Card Table can have up to four Wormholes.')
                identifier = identifier or 'wh-' + secrets.token_hex(8)
                c.execute('INSERT OR REPLACE INTO bc_wormholes VALUES(?,?,?,?,?)', (identifier, account['workspace_id'], board, column_id, color))
        request.state.activity_handled = True
        if 'application/json' in request.headers.get('accept', ''):
            return {'id': identifier, 'redirect': board}
        return RedirectResponse(board, 303)


def label(c, account, column):
    from card_render import column_label
    tool = c.execute('SELECT title FROM bc_tools WHERE owner=? AND id=?', (account['workspace_id'], column['board'].rsplit('/', 1)[-1])).fetchone()
    return (tool['title'] if tool else 'Card Table') + ' — ' + column_label(column)


def render(tree, path, c, account, query):
    from card_table import columns_for
    from record_operations import metadata
    columns = columns_for(c, account['workspace_id'])
    match = re.fullmatch(r'(/6302022/buckets/\d+/card_tables/\d+)(/wormholes/new)?', path)
    if match:
        board = match[1]
        if match[2]:
            forms = tree.xpath('//form[contains(@action,"/wormholes") and @method="post"]')
            if forms:
                form = forms[0]
                candidates = []
                for key, column in columns.items():
                    try:
                        destination(c, account, board, key)
                    except HTTPException:
                        continue
                    candidates.append(column)
                if candidates:
                    for child in list(form):
                        form.remove(child)
                    editing = c.execute('SELECT * FROM bc_wormholes WHERE workspace=? AND board=? AND id=?', (account['workspace_id'], board, str(query.get('edit', '')))).fetchone()
                    if editing:
                        destination(c, account, board, editing['column_id'])
                        form.set('action', board + '/wormholes/' + editing['id'])
                        etree.SubElement(form, 'input', {'type': 'hidden', 'name': '_method', 'value': 'patch'})
                    wrapper = etree.SubElement(form, 'div', {'class': 'modal-sheet__scroller'})
                    etree.SubElement(wrapper, 'h2').text = 'Edit wormhole' if editing else 'Add a wormhole'
                    field = etree.SubElement(wrapper, 'label', {'class': 'margin-block-16'}); field.text = 'Destination column'
                    select = etree.SubElement(field, 'select', {'name': 'column_id', 'class': 'input input--full-width'})
                    for column in candidates:
                        option = etree.SubElement(select, 'option', {'value': column['id']}); option.text = label(c, account, column)
                        if editing and editing['column_id'] == column['id']:
                            option.set('selected', 'selected')
                    field = etree.SubElement(wrapper, 'label'); field.text = 'Color'
                    select = etree.SubElement(field, 'select', {'name': 'color', 'class': 'input'})
                    for color in COLORS:
                        option = etree.SubElement(select, 'option', {'value': color}); option.text = color.title()
                        if color == (editing['color'] if editing else 'purple'):
                            option.set('selected', 'selected')
                    etree.SubElement(wrapper, 'button', {'type': 'submit', 'class': 'btn btn--primary btn--solid margin-block-16'}).text = 'Save wormhole' if editing else 'Add wormhole'
        else:
            containers = tree.xpath('//*[@id="kanban-wormholes"]')
            if containers:
                for row, column in available(c, account, board):
                    item = etree.SubElement(containers[0], 'div', {'class': 'kanban-wormhole margin-inline-8', 'data-local-wormhole': row['id'], 'style': '--recording-color:var(--recording-color-' + row['color'] + ');'})
                    etree.SubElement(item, 'a', {'href': column['board'], 'class': 'decorated'}).text = '🌀 ' + label(c, account, column)
                    menu = etree.SubElement(item, 'details'); etree.SubElement(menu, 'summary', {'aria-label': 'Wormhole options'}).text = '•••'
                    etree.SubElement(menu, 'a', {'href': board + '/wormholes/new?edit=' + row['id'], 'class': 'decorated'}).text = 'Edit wormhole'
                    form = etree.SubElement(menu, 'form', {'action': board + '/wormholes/' + row['id'], 'method': 'post'})
                    etree.SubElement(form, 'input', {'type': 'hidden', 'name': '_method', 'value': 'delete'})
                    etree.SubElement(form, 'button', {'type': 'submit', 'class': 'btn btn--negative'}).text = 'Delete wormhole'
    record = metadata(c, account['workspace_id'], path.rsplit('/', 1)[-1])
    menus = tree.xpath('//*[@id="move-card-columns"]')
    if record and record['kind'] == 'card_tables/cards' and menus:
        prototype = menus[0].xpath('./li')[0]
        for row, column in available(c, account, record['parent']):
            node = copy.deepcopy(prototype)
            node.set('id', 'move_option_' + row['id']); node.set('data-local-wormhole-move', row['id'])
            node.set('aria-selected', 'false')
            for form in node.xpath('.//form'):
                form.set('action', record['url'] + '/moves?column_id=' + row['id']); form.set('data-turbo-frame', '_top')
            for title in node.xpath('.//span[contains(@class,"truncate")]'):
                title.text = '🌀 ' + label(c, account, column)
            for button in node.xpath('.//button'):
                button.attrib.pop('data-hotkey', None)
            menus[0].append(node)
