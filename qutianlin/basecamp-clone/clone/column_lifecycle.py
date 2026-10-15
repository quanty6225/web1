"""Column status and inherited visibility, without rewriting individual cards."""
import json
import re
from datetime import datetime, timezone
from lxml import etree
from fastapi import HTTPException


def load_status(c, owner, columns):
    for row in c.execute('SELECT route,payload FROM bc_mutations WHERE owner=? AND kind="record"', (owner,)):
        match = re.fullmatch(r'/6302022/buckets/\d+/card_tables/columns/(\d+)', row['route'])
        if match and match[1] in columns:
            columns[match[1]]['_record_status'] = json.loads(row['payload']).get('_record_status', 'active')
    for row in c.execute('SELECT recording FROM bc_erased WHERE workspace=?', (owner,)):
        if row['recording'] in columns:
            columns[row['recording']]['deleted'] = True


def status(columns, identifier, parents=None):
    from card_table import parent_columns, column_lineage
    parents = parent_columns(columns) if parents is None else parents
    result = 'active'
    for key in column_lineage(identifier, parents):
        column = columns.get(key, {})
        value = 'trashed' if column.get('deleted') else column.get('_record_status', 'active')
        if value == 'trashed':
            return value
        if value != 'active':
            result = value
    return result


def require_active(columns, identifier):
    if status(columns, identifier) != 'active':
        raise HTTPException(409, 'Restore this column before adding or moving cards into it.')


def record_status(c, owner, record, fields=None):
    from record_operations import fields_for
    from card_table import columns_for, source_cards
    fields = fields_for(c, owner, record) if fields is None else fields
    own = fields.get('_record_status', 'active')
    if record['kind'] not in ('card_tables/cards', 'card_tables/columns'):
        return own
    columns = columns_for(c, owner)
    if record['kind'] == 'card_tables/columns':
        inherited = status(columns, record['id'])
    else:
        column = fields.get('_column_id') or source_cards().get(record['id'], {}).get('column')
        moved = c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="moves"',
                          (owner, record['url'] + '/moves')).fetchone()
        if moved:
            column = json.loads(moved['payload']).get('column_id', column)
        inherited = status(columns, column) if column else 'active'
    if 'trashed' in (own, inherited):
        return 'trashed'
    return inherited if inherited != 'active' else own


def validate_change(c, owner, record):
    from card_table import columns_for, parent_columns, is_special
    columns = columns_for(c, owner); column = columns.get(record['id'])
    if not column or column.get('deleted'):
        raise HTTPException(404, 'Column not found')
    if is_special(column) or record['id'] in parent_columns(columns):
        raise HTTPException(409, 'Only workflow columns can be archived or put in the trash.')


def transition_order(c, owner, record, before, after):
    from card_table import columns_for, save_column
    from column_order import workflow
    columns = columns_for(c, owner); column = columns[record['id']]
    if before == 'active' and after != 'active':
        for index, item in enumerate(workflow(columns, column['board']), 1):
            save_column(c, owner, {**item, 'position': index})
    elif before != 'active' and after == 'active':
        ordered = workflow(columns, column['board'])
        position = column.get('position', len(ordered) + 1)
        ordered.insert(min(position - 1, len(ordered)), column)
        for index, item in enumerate(ordered, 1):
            save_column(c, owner, {**item, 'position': index})


def action(container, record, value, label):
    link = etree.SubElement(container, 'a', {'href': '/6302022/buckets/' + record['bucket'] + '/recordings/' + record['id'] + '/status/' + value,
                                           'class': 'decorated', 'data-method': 'PUT', 'data-remote': 'true', 'rel': 'nofollow'})
    link.text = label
    return link


def render_notice(tree, c, account, record, fields):
    value = fields.get('_record_status', 'active'); targets = tree.xpath('//main')
    if value == 'active' or not targets:
        return
    column = record['kind'] == 'card_tables/columns'
    notice = etree.Element('div', {'role': 'status', 'class': 'recording-status-notice margin-block-16 padding-16', 'data-column-status-notice' if column else 'data-record-status-notice': value})
    author = fields.get('_status_by')
    person = c.execute('SELECT display_name FROM local_auth_accounts WHERE account_id=?', (author,)).fetchone() if author else None
    who = 'You' if author == account['account_id'] else person['display_name'] if person else 'A member'
    notice.text = who + (' archived this ' if value == 'archived' else ' put this ' + ('column' if column else 'item') + ' in the trash ')
    stamp = fields.get('_status_at')
    if stamp:
        when = datetime.fromtimestamp(stamp, timezone.utc)
        node = etree.SubElement(notice, 'time', {'datetime': when.isoformat(), 'data-local': 'time-ago'})
        node.text = when.strftime('%b %d, %Y at %H:%M UTC'); node.tail = '. You can '
    else:
        notice.text += '. You can '
    link = action(notice, record, 'active', 'unarchive it' if value == 'archived' else 'restore it')
    if value == 'archived':
        link.tail = ' or '; link = action(notice, record, 'trashed', 'put it in the trash')
    link.tail = '.'
    targets[0].insert(0, notice)


def render(tree, path, c, account, query):
    if path != '/6302022/account/trash' and not re.fullmatch(r'/6302022/buckets/\d+/card_tables/(?:\d+|columns/\d+)', path):
        return
    from card_table import columns_for, parent_columns
    from column_watching import record as column_record
    from record_operations import fields_for
    from workspaces import allows
    columns = columns_for(c, account['workspace_id']); parents = parent_columns(columns); records = []
    for identifier, column in columns.items():
        if column.get('deleted') or identifier in parents or not allows(account, column['board']):
            continue
        record = column_record(c, account['workspace_id'], identifier, columns=columns)
        fields = fields_for(c, account['workspace_id'], record)
        records.append((column, record, fields))
        if path == record['url']:
            render_notice(tree, c, account, record, fields)
    archived = [(column, record) for column, record, fields in records if column['board'] == path and fields.get('_record_status') == 'archived']
    if archived:
        menus = tree.xpath('//a[contains(@data-action,"copy-to-clipboard#copy")]/ancestor::div[contains(@class,"action-sheet__content")][1]')
        if menus:
            link = etree.SubElement(menus[0], 'a', {'href': path + '?status=archived', 'class': 'action-sheet__action', 'data-local-archived-columns': 'true'})
            link.text = 'View ' + str(len(archived)) + ' archived ' + ('column' if len(archived) == 1 else 'columns')
    if (query or {}).get('status') == 'archived' and any(column['board'] == path for column in columns.values()):
        grids = tree.xpath('//*[@id="kanban-workflow"]/ancestor::*[contains(concat(" ",normalize-space(@class)," ")," kanban-grid ")][1]')
        grids = grids or tree.xpath('//*[@id="kanban-workflow"]/parent::*')
        if grids:
            listing = etree.Element('section', {'data-local-column-archive': 'true', 'class': 'margin-block-24'})
            etree.SubElement(listing, 'h2').text = 'Archived columns'
            etree.SubElement(listing, 'a', {'href': path, 'class': 'decorated'}).text = 'Card Table'
            for column, record in archived:
                row = etree.SubElement(listing, 'article', {'class': 'margin-block-16', 'data-archived-column': record['id']})
                title = etree.SubElement(row, 'a', {'href': record['url']}); title.text = record['title']; title.tail = ' '
                action(row, record, 'active', 'Unarchive')
            if not archived:
                etree.SubElement(listing, 'p').text = 'No archived columns.'
            grids[0].getparent().replace(grids[0], listing)
