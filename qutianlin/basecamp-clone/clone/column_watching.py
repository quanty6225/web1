"""Card-column subscriptions shared by the board and the column discussion."""
import re
from lxml import etree


def record(c, owner, identifier, columns=None):
    from card_table import columns_for
    from card_render import column_label
    columns = columns_for(c, owner) if columns is None else columns
    column = columns.get(identifier)
    if not column or column.get('deleted'):
        return None
    bucket = column['board'].split('/')[3]
    url = '/6302022/buckets/' + bucket + '/card_tables/columns/' + identifier
    return {'id': identifier, 'kind': 'card_tables/columns', 'bucket': bucket,
            'url': url, 'parent': column['board'], 'title': column_label(column, columns),
            'body': column.get('description', ''), 'is_new': bool(column.get('new')),
            'fields': {'kanban_column[name]': column_label(column, columns),
                       'kanban_column[description]': column.get('description', '')},
            'template': url.lstrip('/') + '/index.html'}


def audience(c, account, identifier, previous=None):
    from thread_notifications import subscribers
    from card_table import columns_for, parent_columns, column_lineage
    parents = parent_columns(columns_for(c, account['workspace_id']))
    # On hold is a region inside its parent column. Notify watchers when a
    # card enters that logical column, not when it pauses/resumes within it.
    already_in = set(column_lineage(previous, parents)) if previous else set()
    selected = set()
    for destination in column_lineage(identifier, parents):
        if destination in already_in:
            continue
        column = record(c, account['workspace_id'], destination)
        if column:
            selected.update(subscribers(c, account, column))
    return selected


def mutate(c, account, path, payload, method, referer):
    match = re.fullmatch(r'/6302022/buckets/(\d+)/card_tables/lists/(\d+)/subscription', path)
    if not match:
        return None
    from thread_notifications import mutate as subscribe, resolve
    column = resolve(c, account, match[1], match[2])
    if column['kind'] != 'card_tables/columns':
        from fastapi import HTTPException
        raise HTTPException(404, 'Column not found')
    result = subscribe(c, account, '/6302022/buckets/' + match[1] + '/recordings/' + match[2] + '/subscription', payload, method)
    # The board button returns to the board; the detail button stays on its column.
    result['redirect'] = column['parent'] if referer == column['parent'] else column['url']
    return result


def render(tree, path, c, account):
    if not account:
        return
    from thread_notifications import subscribers, people
    catalog = {}
    for form in tree.xpath('//form[contains(@action,"/recordings/") and contains(@action,"/subscription")]'):
        match = re.fullmatch(r'/6302022/buckets/(\d+)/recordings/(\d+)/subscription', form.get('action', ''))
        if not match:
            continue
        column = record(c, account['workspace_id'], match[2])
        if not column or column['bucket'] != match[1]:
            continue
        # Both the column header and its discussion show subscription state.
        form.set('data-turbo-frame', '_top')
        if path.endswith('/subscription/edit'):
            for nav in tree.xpath('//nav[@aria-label="Breadcrumb"]'):
                links = nav.xpath('.//a')
                if len(links) >= 3:
                    for link, href, label in ((links[-2], column['parent'], 'Card Table'),
                                              (links[-1], column['url'], column['title'])):
                        for child in list(link):
                            link.remove(child)
                        link.set('href', href)
                        link.text = label
    for form in tree.xpath('//form[contains(@action,"/card_tables/lists/") and contains(@action,"/subscription")]'):
        match = re.fullmatch(r'/6302022/buckets/(\d+)/card_tables/lists/(\d+)/subscription', form.get('action', ''))
        if not match:
            continue
        column = record(c, account['workspace_id'], match[2])
        if not column or column['bucket'] != match[1]:
            continue
        selected = subscribers(c, account, column) & set(people(c, account, column))
        catalog[match[2]] = (column, selected)
        active = account['account_id'] in selected
        wrappers = form.xpath('ancestor::li[@data-controller="people-visibility"]')
        if wrappers:
            wrapper = wrappers[0]
            is_remove = bool(form.xpath('./input[@name="_method" and @value="delete"]'))
            wrapper.attrib.pop('data-controller', None)
            wrapper.attrib.pop('data-people-visibility-show-value', None)
            wrapper.attrib.pop('data-people-visibility-hide-value', None)
            wrapper.set('class', ' '.join(name for name in wrapper.get('class', '').split() if name != 'hidden'))
            if is_remove != active:
                wrapper.set('hidden', '')
            else:
                wrapper.attrib.pop('hidden', None)
        else:
            for method_field in form.xpath('./input[@name="_method"]'):
                form.remove(method_field)
            if active:
                etree.SubElement(form, 'input', {'type': 'hidden', 'name': '_method', 'value': 'delete'})
            for button in form.xpath('./button'):
                icons = button.xpath('./svg')
                text = ' Stop watching' if active else ' Watch column'
                if icons:
                    icons[0].tail = text
                else:
                    button.text = text.strip()
                button.set('data-bridge-action-type', 'unsubscribe' if active else 'subscribe')
        form.set('data-turbo-frame', '_top')
    for identifier, (column, selected) in catalog.items():
        targets = tree.xpath('//*[@id="recording_' + identifier + '"]//*[contains(concat(" ",normalize-space(@class)," ")," kanban-people ")]')
        if path == column['url']:
            targets = tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," kanban-people ")]')
        for target in targets:
            for child in list(target):
                target.remove(child)
            target.text = ''
            choices = people(c, account, column)
            if not selected:
                etree.SubElement(target, 'span', {'class': 'kanban-people--notwatching'}).text = "Nobody's watching"
            for identifier in sorted(selected):
                person = choices[identifier]
                etree.SubElement(target, 'img', {'class': 'avatar avatar--xs', 'src': person['avatar_url'], 'alt': person['name'], 'title': person['name'], 'data-local-column-watcher': identifier})
