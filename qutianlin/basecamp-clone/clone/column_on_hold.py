"""Persistent On hold regions using the captured native column structure."""
import json
import re
import secrets
from lxml import etree, html
from fastapi import HTTPException


def mutate(c, owner, column, method):
    from card_table import DATA, columns_for, parent_columns, cards_for, save_column
    columns = columns_for(c, owner)
    parents = parent_columns(columns)
    if column['id'] in parents:
        raise HTTPException(404, 'Column not found')
    children = [key for key, parent in parents.items() if parent == column['id'] and not columns[key].get('deleted')]
    if method == 'POST':
        if children:
            return {'redirect': column['board'], 'on_hold_id': children[0]}
        identifier = str(900000000000 + secrets.randbelow(99999999999))
        source = DATA['columns']['10398823195']
        markup = source['html'].replace(source['board'], column['board']).replace('/buckets/49234166/', '/buckets/' + column['board'].split('/')[3] + '/')
        tree = html.fromstring(markup.replace(source['id'], identifier))
        for card in tree.xpath('.//article'):
            card.getparent().remove(card)
        child = {'id': identifier, 'board': column['board'], 'count': 0, 'name': '',
                 'new': True, 'parent': column['id'], 'html': html.tostring(tree, encoding='unicode')}
        save_column(c, owner, child)
        return {'redirect': column['board'], 'on_hold_id': identifier}
    for identifier in children:
        for card_id, card in cards_for(c, owner).items():
            if card['board'] != column['board']:
                continue
            row = c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="moves"',
                            (owner, column['board'].split('/card_tables/')[0] + '/card_tables/cards/' + card_id + '/moves')).fetchone()
            current = json.loads(row['payload']).get('column_id') if row else card['column']
            if current == identifier:
                # The source evidence does not establish where occupied-region
                # removal puts cards. Never silently move or drop those records.
                raise HTTPException(501, 'Removing an occupied On hold area is not available yet.')
        save_column(c, owner, {**columns[identifier], 'deleted': True})
    return {'redirect': column['board']}


def render(tree, columns):
    from card_table import parent_columns
    parents = parent_columns(columns)
    active = {key: parent for key, parent in parents.items() if not columns[key].get('deleted') and not columns[parent].get('deleted')}
    for identifier, parent in active.items():
        if tree.xpath('//*[@id="recording_' + identifier + '"]'):
            continue
        containers = tree.xpath('//*[@id="recording_' + parent + '"]/div[contains(concat(" ",normalize-space(@class)," ")," kanban-column__content ")]')
        if containers:
            containers[0].append(html.fromstring(columns[identifier]['html']))
    for form in tree.xpath('//form[contains(@action,"/on_hold")]'):
        match = re.search(r'/card_tables/columns/(\d+)/on_hold(?:\?|$)', form.get('action', ''))
        if not match or match[1] not in columns:
            continue
        enabled = match[1] in active.values()
        for field in form.xpath('./input[@name="_method"]'):
            form.remove(field)
        if enabled:
            etree.SubElement(form, 'input', {'type': 'hidden', 'name': '_method', 'value': 'delete'})
        for button in form.xpath('./input[@type="submit"]'):
            button.set('value', ("Disable" if enabled else "Enable") + " 'On hold'")
        form.set('data-turbo-frame', '_top')
