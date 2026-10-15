"""Explicit task assignment and completion recipients, with current project access."""
import json
import re
import time
from fastapi import HTTPException
from record_operations import PREFIX, TITLE, fields_for, metadata


def identifiers(value, account):
    values = value if isinstance(value, list) else str(value or '').split(',')
    result = []
    for person in values:
        person = str(person).strip()
        if person == 'me':
            person = account['account_id']
        elif person == '53382586':
            person = account['workspace_id']
        if person and person not in result:
            result.append(person)
    return result


def validate_people(c, account, route, values):
    from task_fields import people, PEOPLE
    from thread_notifications import accessible_member
    catalog = people(c, account)
    for person in values:
        if person not in catalog:
            raise HTTPException(422, 'Choose someone who belongs to this project.')
        if person in PEOPLE and person != '53382586':
            if not route.startswith('/6302022/buckets/49234166/'):
                raise HTTPException(422, 'Choose someone who belongs to this project.')
        elif not accessible_member(c, account['workspace_id'], person, route):
            raise HTTPException(422, 'Choose someone who can access this project.')


def validate_completion_people(c, account, kind, state, payload, route):
    key = PREFIX[kind] + '[completion_subscribers]'
    if not account or key not in payload:
        return
    selected = identifiers(state.get(key, ''), account)
    validate_people(c, account, route, selected)
    state[key] = ','.join(selected)


def assignment_changed(c, account, record, previous, action='assigned', additional_recipients=()):
    if not account or record['kind'] not in ('todos', 'subtasks', 'card_tables/cards'):
        return False
    fields = fields_for(c, account['workspace_id'], record)
    key = PREFIX[record['kind']] + '[assignees]'
    assigned = set(identifiers(fields.get(key, ''), account))
    added = assigned - set(identifiers(previous.get(key, ''), account))
    if not added:
        return False
    # Assignment follows the discussion for both assigner and new assignees.
    for person in added | {account['account_id']}:
        c.execute('INSERT OR REPLACE INTO bc_thread_subscriptions VALUES(?,?,?,1)', (account['workspace_id'], record['id'], person))
    from activity_search import emit
    title = fields.get(PREFIX[record['kind']] + '[' + TITLE[record['kind']] + ']', record['title'])
    emit(c, account, record['url'], title, action, added | set(additional_recipients))
    return True


def complete(c, account, path, method):
    match = re.fullmatch(r'/6302022/buckets/(\d+)/(todos|subtasks)/(\d+)/completion', path)
    if not match:
        return None
    if method not in ('POST', 'DELETE'):
        raise HTTPException(405, 'Use the task completion checkbox to change this state.')
    c.execute('BEGIN IMMEDIATE')
    record = metadata(c, account['workspace_id'], match[3])
    if not record or record['url'] + '/completion' != path:
        raise HTTPException(404, 'Task not found')
    state = fields_for(c, account['workspace_id'], record)
    if state.get('_record_status', 'active') != 'active':
        raise HTTPException(404, 'Task not found')
    from task_reports import source_completed
    previous = c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="completion"', (account['workspace_id'], path)).fetchone()
    was_done = bool(json.loads(previous['payload']).get('active')) if previous else not record.get('is_new') and source_completed(record['template'])
    done = method != 'DELETE'
    c.execute('INSERT OR REPLACE INTO bc_mutations VALUES(?,?,"completion",?,?)', (account['workspace_id'], path, json.dumps({'active': done}), int(time.time())))
    if done != was_done:
        from activity_search import emit
        key = PREFIX[record['kind']] + '[completion_subscribers]'
        recipients = set(identifiers(state.get(key, ''), account)) | set(state.get('_assignment_authors', {}).values()) if done else set()
        emit(c, account, record['url'], state.get(PREFIX[record['kind']] + '[' + TITLE[record['kind']] + ']', record['title']), 'completed' if done else 'reopened', recipients)
    return {'redirect': record['url'], 'no_content': True, 'activity_handled': True}
