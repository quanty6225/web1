"""Discussion subscriptions and the explicit audience of comment notifications."""
import json
import re
from functools import lru_cache
from pathlib import Path
from lxml import html, etree
from fastapi import HTTPException
from record_operations import metadata, fields_for, PREFIX, TITLE

ROOT = Path(__file__).parent


def initialize(db):
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS bc_thread_subscriptions(workspace TEXT,recording TEXT,person TEXT,active INTEGER,PRIMARY KEY(workspace,recording,person))')
        # Earlier versions saved a personal toggle without applying its audience.
        for row in c.execute('SELECT owner,name,value FROM bc_settings WHERE name LIKE "subscription:%"'):
            _, workspace, recording = row['name'].split(':', 2)
            value = json.loads(row['value'])
            c.execute('INSERT OR IGNORE INTO bc_thread_subscriptions VALUES(?,?,?,?)', (workspace, recording, row['owner'], int(value.get('active', False))))


def accessible_member(c, workspace, person, route):
    member = c.execute('SELECT * FROM bc_members WHERE workspace=? AND account=?', (workspace, person)).fetchone()
    if not member:
        return False
    if member['role'] == 'owner' or member['access'] == 'all':
        return True
    project = re.search(r'/6302022/(?:buckets|projects)/(\d+)', route)
    return bool(project and c.execute('SELECT 1 FROM bc_project_members WHERE workspace=? AND project=? AND account=?', (workspace, project[1], person)).fetchone())


@lru_cache(maxsize=256)
def source_subscribers(route):
    path = ROOT / 'frontend/pages' / route.lstrip('/') / 'index.html'
    if not path.exists():
        return ()
    tree = html.parse(path)
    return tuple(dict.fromkeys(tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," thread__subscribers ")]//img/@data-avatar-for-person-id')))


def subscribers(c, account, record):
    selected = set() if record.get('is_new') else set(source_subscribers(record['url']))
    if '53382586' in selected:
        selected.remove('53382586')
        selected.add(account['workspace_id'])
    for row in c.execute('SELECT person,active FROM bc_thread_subscriptions WHERE workspace=? AND recording=?', (account['workspace_id'], record['id'])):
        if row['active']:
            selected.add(row['person'])
        else:
            selected.discard(row['person'])
    return selected


def people(c, account, record):
    from task_fields import people as catalog
    result = catalog(c, account)
    result.pop('53382586', None)
    actual = {r['account'] for r in c.execute('SELECT account FROM bc_members WHERE workspace=?', (account['workspace_id'],))}
    for person in list(result):
        if person in actual and not accessible_member(c, account['workspace_id'], person, record['url']):
            result.pop(person)
        # A removed account is no longer in either the fixture or member catalog.
    return result


def resolve(c, account, bucket, identifier):
    record = metadata(c, account['workspace_id'], identifier)
    if not record or record['bucket'] != bucket or fields_for(c, account['workspace_id'], record).get('_record_status', 'active') != 'active':
        raise HTTPException(404, 'Record not found')
    return record


def mutate(c, account, path, payload, method):
    match = re.fullmatch(r'/6302022/buckets/(\d+)/recordings/(\d+)/subscription', path)
    if not match:
        return None
    record = resolve(c, account, match[1], match[2])
    before = subscribers(c, account, record)
    if method in ('POST', 'DELETE'):
        person = account['account_id']
        c.execute('INSERT OR REPLACE INTO bc_thread_subscriptions VALUES(?,?,?,?)', (account['workspace_id'], record['id'], person, int(method == 'POST')))
    elif method in ('PATCH', 'PUT'):
        from workspaces import writable
        writable(account)
        selected = payload.get('person_ids[]', [])
        if isinstance(selected, str):
            selected = [selected] if selected else []
        catalog = people(c, account, record)
        if not isinstance(selected, list) or any(not isinstance(person, str) or person not in catalog for person in selected):
            raise HTTPException(422, 'Choose people who can access this project.')
        selected = set(selected)
        for person in before | set(catalog):
            c.execute('INSERT OR REPLACE INTO bc_thread_subscriptions VALUES(?,?,?,?)', (account['workspace_id'], record['id'], person, int(person in selected)))
        if payload.get('notify') == 'true' and selected - before:
            from activity_search import emit
            fields = fields_for(c, account['workspace_id'], record)
            emit(c, account, record['url'], fields.get(PREFIX[record['kind']] + '[' + TITLE[record['kind']] + ']', record['title']), 'shared', selected - before)
    else:
        raise HTTPException(405, 'Unsupported subscription action')
    return {'redirect': record['url']}


def comment_posted(c, account, record, identifier, reply_author=None):
    from activity_search import emit
    # Posting a comment follows the discussion again, including after a prior
    # opt-out. The author never receives a notification for their own comment.
    c.execute('INSERT OR REPLACE INTO bc_thread_subscriptions VALUES(?,?,?,1)', (account['workspace_id'], record['id'], account['account_id']))
    fields = fields_for(c, account['workspace_id'], record)
    title = fields.get(PREFIX[record['kind']] + '[' + TITLE[record['kind']] + ']', record['title'])
    audience = subscribers(c, account, record)
    if reply_author:
        audience.add(reply_author)
    return emit(c, account, record['url'] + '#comment-' + identifier, title, 'commented on', audience)


def render(tree, path, account, c):
    for form in tree.xpath('//form[contains(@action,"/subscription")]'):
        match = re.fullmatch(r'/6302022/buckets/(\d+)/recordings/(\d+)/subscription', form.get('action', ''))
        if not match:
            continue
        record = metadata(c, account['workspace_id'], match[2])
        if not record:
            continue
        catalog = people(c, account, record)
        selected = subscribers(c, account, record) & set(catalog)
        picker = form.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," list-picker ")]')
        if picker:
            for child in list(picker[0]):
                picker[0].remove(child)
            for person, info in catalog.items():
                label = etree.SubElement(picker[0], 'label', {'class': 'checkbox-field margin-block-8', 'data-local-subscriber': person})
                attributes = {'type': 'checkbox', 'name': 'person_ids[]', 'value': person, 'data-checkbox-group-target': 'checkbox'}
                if person in selected:
                    attributes['checked'] = 'checked'
                etree.SubElement(label, 'input', attributes)
                etree.SubElement(label, 'img', {'class': 'avatar', 'src': info['avatar_url'], 'alt': '', 'width': '32', 'height': '32'})
                etree.SubElement(label, 'span').text = info['name']
            continue
        active = account['account_id'] in selected
        for field in form.xpath('.//input[@name="_method"]'):
            field.getparent().remove(field)
        if active:
            etree.SubElement(form, 'input', {'type': 'hidden', 'name': '_method', 'value': 'delete'})
        for button in form.xpath('.//button[@type="submit"]'):
            icons = button.xpath('.//svg')
            if icons:
                icons[0].tail = ' Don’t notify me' if active else ' Notify me'
            else:
                button.text = 'Don’t notify me' if active else 'Notify me'
        sections = form.xpath('ancestor::div[contains(concat(" ",normalize-space(@class)," ")," thread__subscribers ")]')
        if not sections:
            continue
        section = sections[0]
        count_nodes = section.xpath('./div[not(@class)]')
        if count_nodes:
            text = count_nodes[0].text_content()
            suffix = text[text.find('will be notified'):].strip()
            count_nodes[0].text = str(len(selected)) + (' person ' if len(selected) == 1 else ' people ') + suffix
        groups = section.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," avatar-group ")]')
        if groups:
            for avatar in groups[0].xpath('./img'):
                groups[0].remove(avatar)
            source_order = [account['workspace_id'] if person == '53382586' else person for person in source_subscribers(record['url'])]
            ordered = list(dict.fromkeys([person for person in source_order if person in selected] + [person for person in catalog if person in selected]))
            for index, person in enumerate(ordered):
                info = catalog[person]
                groups[0].insert(index, etree.Element('img', {'class': 'avatar', 'src': info['avatar_url'], 'alt': info['name'], 'title': info['name'], 'data-avatar-for-person-id': person, 'width': '32', 'height': '32'}))
