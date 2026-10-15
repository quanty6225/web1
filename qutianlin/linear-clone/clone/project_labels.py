"""Workspace project labels and mutually exclusive label groups."""
import json
import re
from fastapi import HTTPException


def records(c, wid):
    return {row['id']: json.loads(row['document']) for row in c.execute(
        "SELECT id,document FROM linear_records WHERE workspace_id=? AND kind='project-labels'", (wid,))}


def prepare_project_label(c, wid, value, previous, provided, now):
    title = value.get('title')
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 80:
        raise HTTPException(422, 'Enter a label name of at most 80 characters.')
    value['title'] = title.strip()
    if not isinstance(value.get('description', ''), str):
        raise HTTPException(422, 'Invalid label description.')
    for key in ('is_group', 'archived', 'favorite'):
        if not isinstance(value.get(key, False), bool):
            raise HTTPException(422, 'Invalid label state.')
        value.setdefault(key, False)
    value.setdefault('description', '')
    color = value.get('color', '#4cb782')
    if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        raise HTTPException(422, 'Select a label color.')
    value['color'] = color.lower()
    parent = value.get('parent_id')
    labels = records(c, wid)
    if parent is not None:
        if not isinstance(parent, str) or parent == value['id'] or parent not in labels or not labels[parent].get('is_group'):
            raise HTTPException(422, 'Select a label group from this workspace.')
        if value['is_group']:
            raise HTTPException(422, 'Label groups cannot be nested.')
        if labels[parent].get('archived') and parent != (previous or {}).get('parent_id'):
            raise HTTPException(422, 'Select an active label group.')
    value['parent_id'] = parent
    if parent and labels[parent].get('archived') and provided.get('archived') is False:
        raise HTTPException(422, 'Restore the label group first.')
    if value['archived']:
        if not (previous or {}).get('archived'):
            value['archived_at'] = now
        elif previous and previous.get('archived_at'):
            value['archived_at'] = previous['archived_at']
        else:
            value.pop('archived_at', None)
    else:
        value.pop('archived_at', None)
    conflict = next((item for item in labels.values() if item['id'] != value['id']
                     and item['title'].lower() == value['title'].lower()), None)
    if conflict:
        article = 'an archived' if conflict.get('archived') or labels.get(conflict.get('parent_id'), {}).get('archived') else 'a'
        kind = 'label group' if conflict.get('is_group') else 'label'
        raise HTTPException(409, f'There’s already {article} {kind} with this name in the workspace.')
    if not value['is_group'] and any(item.get('parent_id') == value['id'] for item in labels.values()):
        raise HTTPException(409, 'Move labels out of this group before converting it.')
    labels[value['id']] = value
    for row in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='projects'", (wid,)):
        assigned = json.loads(row['document']).get('labels', [])
        if value['id'] not in assigned:
            continue
        if value['is_group']:
            raise HTTPException(409, 'Remove this label from projects before converting it to a group.')
        if parent and any(ref != value['id'] and labels.get(ref, {}).get('parent_id') == parent for ref in assigned):
            raise HTTPException(409, 'A project already has another label from this group.')
    # These fields are derived by the server, never accepted from a client.
    if previous and 'last_applied_at' in previous:
        value['last_applied_at'] = previous['last_applied_at']
    else:
        value.pop('last_applied_at', None)


def prepare_project_labels(c, wid, value, previous, provided, now):
    labels = records(c, wid)
    refs = value.get('labels', [])
    if not isinstance(refs, list) or len(refs) > 100 or any(not isinstance(ref, str) for ref in refs) or len(set(refs)) != len(refs):
        raise HTTPException(422, 'Invalid project labels.')
    old = set((previous or {}).get('labels', []))
    groups = set()
    for ref in refs:
        label = labels.get(ref)
        if not label or label.get('is_group'):
            raise HTTPException(422, 'Select labels from this workspace.')
        parent = label.get('parent_id')
        if parent:
            if parent not in labels or not labels[parent].get('is_group'):
                raise HTTPException(422, 'Select labels from this workspace.')
            if parent in groups:
                raise HTTPException(422, 'Select only one label from each group.')
            groups.add(parent)
        if ref not in old:
            if label.get('archived') or labels.get(parent, {}).get('archived'):
                raise HTTPException(422, 'Archived labels cannot be applied to projects.')
            label['last_applied_at'] = now
            c.execute("UPDATE linear_records SET document=?,revision=revision+1,updated_at=? WHERE workspace_id=? AND kind='project-labels' AND id=?",
                      (json.dumps(label), now, wid, ref))


def delete_project_label(store, c, wid, record, now):
    labels = records(c, wid)
    removed = {record['id']}
    if record.get('is_group'):
        removed.update(item['id'] for item in labels.values() if item.get('parent_id') == record['id'])
    for row in c.execute("SELECT id,document FROM linear_records WHERE workspace_id=? AND kind='projects'", (wid,)).fetchall():
        project = json.loads(row['document'])
        if not removed.intersection(project.get('labels', [])):
            continue
        previous = dict(project)
        project['labels'] = [ref for ref in project['labels'] if ref not in removed]
        c.execute("UPDATE linear_records SET document=?,revision=revision+1,updated_at=? WHERE workspace_id=? AND kind='projects' AND id=?",
                  (json.dumps(project), now, wid, row['id']))
        store.collect_record_event(c, wid, 'projects', 'update', project, previous)
    for ref in removed - {record['id']}:
        c.execute("DELETE FROM linear_records WHERE workspace_id=? AND kind='project-labels' AND id=?", (wid, ref))
        store.collect_record_event(c, wid, 'project-labels', 'remove', labels[ref])


def batch_project_labels(store, wid, data):
    """Apply selection actions atomically, including explicit conflict resolution."""
    import time
    if not isinstance(data, dict):
        raise HTTPException(422, 'Expected an object.')
    ids = data.get('ids')
    action = data.get('action')
    if not isinstance(ids, list) or not ids or len(ids) > 100 or any(not isinstance(id, str) for id in ids) or len(set(ids)) != len(ids):
        raise HTTPException(422, 'Select labels from this workspace.')
    if action not in ('move', 'merge', 'archive', 'restore', 'favorite', 'unfavorite', 'delete'):
        raise HTTPException(422, 'Invalid label action.')
    now = int(time.time())
    with store.auth.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        labels = records(c, wid)
        if any(id not in labels for id in ids):
            raise HTTPException(404, 'Item not found.')
        selected = [labels[id] for id in ids]
        if action in ('archive', 'restore'):
            selected = [item for item in selected if item.get('parent_id') not in ids]
        project_rows = c.execute("SELECT id,document FROM linear_records WHERE workspace_id=? AND kind='projects'", (wid,)).fetchall()
        projects = {row['id']: json.loads(row['document']) for row in project_rows}
        def save_project(project, refs):
            if project.get('labels', []) == refs:
                return
            previous = dict(project)
            project['labels'] = refs
            c.execute("UPDATE linear_records SET document=?,revision=revision+1,updated_at=? WHERE workspace_id=? AND kind='projects' AND id=?", (json.dumps(project), now, wid, project['id']))
            store.collect_record_event(c, wid, 'projects', 'update', project, previous)
        def delete_label(item):
            if not c.execute("SELECT 1 FROM linear_records WHERE workspace_id=? AND kind='project-labels' AND id=?", (wid, item['id'])).fetchone():
                return
            delete_project_label(store, c, wid, item, now)
            c.execute("DELETE FROM linear_records WHERE workspace_id=? AND kind='project-labels' AND id=?", (wid, item['id']))
            store.collect_record_event(c, wid, 'project-labels', 'remove', item)
        if action == 'delete':
            for item in selected:
                delete_label(item)
        elif action == 'merge':
            if len(selected) < 2 or any(item.get('is_group') or item.get('parent_id') != selected[0].get('parent_id') for item in selected):
                raise HTTPException(422, 'Select labels in the same group to merge.')
            usage = lambda item: sum(item['id'] in p.get('labels', []) for p in projects.values())
            target = sorted(selected, key=lambda item: (-usage(item), -item.get('last_applied_at', 0), item['title'].casefold()))[0]
            if data.get('target_id') != target['id']:
                raise HTTPException(409, 'The merge destination changed. Refresh and try again.')
            for project in projects.values():
                refs = project.get('labels', [])
                if set(ids).intersection(refs):
                    save_project(project, list(dict.fromkeys(target['id'] if ref in ids else ref for ref in refs)))
            for item in selected:
                if item['id'] != target['id']:
                    delete_label(item)
        else:
            parent = data.get('parent_id')
            patch = {'parent_id': parent} if action == 'move' else {'archived': action == 'archive'} if action in ('archive', 'restore') else {'favorite': action == 'favorite'}
            if action == 'move':
                if any(item.get('is_group') for item in selected):
                    raise HTTPException(422, 'Select labels to move into a group.')
                if parent is not None and (not isinstance(parent, str) or parent not in labels or not labels[parent].get('is_group') or labels[parent].get('archived')):
                    raise HTTPException(422, 'Select an active label group from this workspace.')
                if parent:
                    for project in projects.values():
                        refs = project.get('labels', [])
                        moving = [id for id in ids if id in refs]
                        existing = [ref for ref in refs if ref not in ids and labels.get(ref, {}).get('parent_id') == parent]
                        removed = moving if existing else moving[1:]
                        if removed:
                            if data.get('resolve_conflicts') is not True:
                                raise HTTPException(409, 'A project already has another label from this group.')
                            save_project(project, [ref for ref in refs if ref not in removed])
            for item in selected:
                if action == 'restore' and labels.get(item.get('parent_id'), {}).get('archived') and item.get('parent_id') not in ids:
                    raise HTTPException(422, 'Restore the label group first.')
                value = {**item, **patch}
                if action == 'move' and parent:
                    children = [label for label in records(c, wid).values() if label.get('parent_id') == parent]
                    colors = {label.get('color') for label in children}
                    if len(children) > 1 and len(colors) == 1:
                        value['color'] = children[0]['color']
                prepare_project_label(c, wid, value, item, patch, now)
                c.execute("UPDATE linear_records SET document=?,revision=revision+1,updated_at=? WHERE workspace_id=? AND kind='project-labels' AND id=?", (json.dumps(value), now, wid, item['id']))
                labels[item['id']] = value
                store.collect_record_event(c, wid, 'project-labels', 'update', value, item)
        c.commit()
    return {'saved': True, 'labels': store.list(wid, 'project-labels')}
