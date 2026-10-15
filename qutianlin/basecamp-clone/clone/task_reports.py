"""Owned task reports rendered inside the captured My Tasks tray."""
import json
from collections import defaultdict
from datetime import date
from functools import lru_cache
from pathlib import Path
from lxml import html, etree
from card_table import columns_for
from record_operations import DATA, metadata, fields_for, PREFIX, TITLE, text_value
from workspaces import allows

ROOT = Path(__file__).parent


@lru_cache(maxsize=256)
def source_completed(template):
    tree = html.parse(str(ROOT / 'frontend/pages' / template))
    return bool(tree.xpath('//input[@name="todo_complete" and @checked]|//*[contains(@class,"card-perma-meta__done")]'))


def unfinished(c, owner, record, fields):
    from column_lifecycle import record_status
    if record_status(c, owner, record, fields) != 'active':
        return False
    project = c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="project"',
                        (owner, '/6302022/projects/' + record['bucket'])).fetchone()
    if project and json.loads(project['payload']).get('_status') == 'trashed':
        return False
    completion = c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="completion"',
                           (owner, record['url'] + '/completion')).fetchone()
    if completion and json.loads(completion['payload']).get('active', False):
        return False
    if record['kind'] == 'card_tables/cards':
        column = fields.get('_column_id') or DATA['cards'].get(record['id'], {}).get('column')
        move = c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="moves"',
                         (owner, record['url'] + '/moves')).fetchone()
        if move:
            column = json.loads(move['payload']).get('column_id')
        if column:
            return 'kanban-grid__done-column' not in columns_for(c, owner).get(column, {}).get('html', '')
    if not completion and not record.get('is_new') and source_completed(record['template']):
        return False
    return True


def open_tasks(c, account, mode='assignments'):
    owner = account['workspace_id']
    records = dict(DATA['records'])
    for row in c.execute('SELECT id FROM bc_records WHERE owner=?', (owner,)):
        record = metadata(c, owner, row['id'])
        if record:
            records[record['id']] = record
    own_ids = {account['account_id']}
    if owner == account['account_id']:
        own_ids.add('53382586')
    result = []
    for record in records.values():
        if record['kind'] not in ('todos', 'subtasks', 'card_tables/cards') or not allows(account, record['url']):
            continue
        fields = fields_for(c, owner, record)
        prefix = PREFIX[record['kind']]
        assignees = {v for v in str(fields.get(prefix + '[assignees]', '')).split(',') if v}
        if mode == 'assignings':
            authors = fields.get('_assignment_authors', {})
            if not any(identifier not in own_ids and authors.get(identifier) == account['account_id'] for identifier in assignees):
                continue
        elif not own_ids.intersection(assignees):
            continue
        if unfinished(c, owner, record, fields):
            result.append({**record, 'state': fields, 'assignees': sorted(assignees),
                           'title': text_value(fields.get(prefix + '[' + TITLE[record['kind']] + ']', record['title'])),
                           'due': fields.get(prefix + '[due_on]', '')})
    return sorted(result, key=lambda task: (task['bucket'], task['due'] or '9999-12-31', task['title'].casefold()))


@lru_cache(maxsize=1)
def project_names():
    tree = html.parse(str(ROOT / 'frontend/pages/6302022/index.html'))
    return {a.get('href').rsplit('/', 1)[-1]: ' '.join(a.xpath('.//h2')[0].text_content().split())
            for a in tree.xpath('//a[starts-with(@href,"/6302022/projects/") and .//h2]')}


def render(tree, path, c, account):
    if not account:
        return
    frames = tree.xpath('//turbo-frame[@id="my_navigation_assignments"]')
    if not frames:
        return
    frame = frames[0]
    targets = frame.xpath('./div[contains(@class,"schedule--coalesced")]')
    if not targets:
        return
    # Home has a lazy frame and no report contents until My Tasks is opened.
    mode = 'assignings' if path == '/6302022/my/assignings' or frame.get('src', '').split('?')[0].endswith('/assignings') else 'assignments'
    tasks = open_tasks(c, account, mode)
    if not tasks:
        return
    for blank in frame.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," blank-slate ")]'):
        blank.getparent().remove(blank)
    target = targets[0]
    groups = defaultdict(list)
    for task in tasks:
        groups[task['bucket']].append(task)
    from task_fields import people
    catalog = people(c, account)
    for bucket, entries in groups.items():
        section = etree.SubElement(target, 'section', {'class': 'todolist margin-block-24', 'data-quick-find-target': 'section', 'data-local-task-report': bucket})
        heading = etree.SubElement(section, 'h2', {'class': 'todolist__title'})
        etree.SubElement(heading, 'a', {'href': '/6302022/projects/' + bucket}).text = project_names().get(bucket, 'Project')
        listing = etree.SubElement(section, 'ul', {'class': 'todos todos--remaining'})
        for task in entries:
            row = etree.SubElement(listing, 'li', {'class': 'todo recording', 'data-recording-id': task['id'], 'data-quick-find-target': 'searchable', 'data-local-task-id': task['id'], 'data-role': 'completion_container'})
            wrapper = etree.SubElement(row, 'div', {'class': 'checkbox-field'})
            if task['kind'] in ('todos', 'subtasks'):
                label = etree.SubElement(wrapper, 'label', {'class': 'todo__checkbox checkbox'})
                etree.SubElement(label, 'input', {'type': 'checkbox', 'name': 'todo_complete', 'value': '1', 'autocomplete': 'off', 'aria-label': task['title'], 'data-behavior': 'todo_completion', 'data-url': task['url'] + '/completion'})
            content = etree.SubElement(wrapper, 'div', {'class': 'todo__content checkbox-field__content'})
            etree.SubElement(content, 'a', {'href': task['url'], 'dir': 'auto'}).text = task['title']
            details = etree.SubElement(content, 'span', {'class': 'task-details'})
            for identifier in task['assignees']:
                person = catalog.get(identifier)
                if not person:
                    continue
                assignee = etree.SubElement(details, 'span', {'class': 'task-details__assignee'})
                etree.SubElement(assignee, 'img', {'class': 'avatar', 'alt': person['name'], 'title': person['name'], 'src': person['avatar_url'], 'width': '24', 'height': '24'})
                etree.SubElement(assignee, 'a', {'href': task['url'] + '/edit', 'title': 'Reassign…'}).text = person['name']
            if task['due']:
                etree.SubElement(details, 'a', {'href': task['url'] + '/edit', 'class': 'task-details__date', 'title': 'Change the schedule…'}).text = date.fromisoformat(task['due']).strftime('%a, %b %d')
