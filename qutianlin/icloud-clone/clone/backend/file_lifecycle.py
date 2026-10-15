"""Account-scoped Drive/iWork trash with server-owned recovery deadlines."""
import json

RETENTION_SECONDS = 30 * 24 * 60 * 60


def records(db, owner, kind):
    return {row['id']: json.loads(row['payload']) for row in db.execute(
        'SELECT id,payload FROM icloud_entities WHERE owner=? AND kind=?', (owner, kind))}


def descendants(data, roots):
    selected = set(roots)
    while True:
        added = {key for key, item in data.items() if item.get('parent') in selected} - selected
        if not added:
            return selected
        selected.update(added)


def ancestors(data, identifier):
    result = set()
    parent = data[identifier].get('parent')
    while parent in data and parent not in result:
        result.add(parent)
        parent = data[parent].get('parent')
    return result


def save(db, owner, kind, item, now):
    db.execute('UPDATE icloud_entities SET payload=?,updated_at=? WHERE owner=? AND kind=? AND id=?',
               (json.dumps(item), now, owner, kind, item['id']))


def apply(db, owner, kind, identifiers, action, now):
    """All validation precedes mutation; the caller owns one write transaction."""
    if kind not in ('files', 'documents') or action not in ('trash', 'recover', 'delete'):
        raise ValueError('Choose a valid file action.')
    if not isinstance(identifiers, list) or not identifiers or len(identifiers) > 5000 or any(not isinstance(i, str) for i in identifiers):
        raise ValueError('Select files to continue.')
    data = records(db, owner, kind)
    selected = set(identifiers)
    if not selected <= data.keys():
        raise LookupError('File not found.')
    if action != 'trash' and any(not data[key].get('deleted') for key in selected):
        raise ValueError('Select files from Recently Deleted.')
    removed = []
    if action == 'trash':
        for root in sorted(selected, key=lambda key: len(ancestors(data, key))):
            for key in descendants(data, [root]):
                item = data[key]
                if item.get('deleted'):
                    continue  # A second delete must not extend its recovery period.
                item.update(deleted=True, deleted_at=now, deleted_group=root)
                save(db, owner, kind, item, now)
    elif action == 'recover':
        for root in list(selected):
            if data[root].get('folder'):
                selected.update(key for key in descendants(data, [root])
                                if data[key].get('deleted_group') == root)
        # Restore parent folders too, retaining each recovered file's location.
        for root in list(selected):
            parent = data[root].get('parent')
            visited = {root}
            while parent in data and parent not in visited:
                visited.add(parent)
                if data[parent].get('deleted'):
                    selected.add(parent)
                parent = data[parent].get('parent')
        for key in selected:
            item = data[key]
            item['deleted'] = False
            item.pop('deleted_at', None)
            item.pop('deleted_group', None)
            save(db, owner, kind, item, now)
    else:
        for key in descendants(data, selected):
            removed.append(data[key])
            db.execute('DELETE FROM icloud_entities WHERE owner=? AND kind=? AND id=?', (owner, kind, key))
    return removed


def expire(db, owner, now):
    removed = []
    db.execute('BEGIN IMMEDIATE')
    for kind in ('files', 'documents'):
        data = records(db, owner, kind)
        expired = [key for key, item in data.items() if item.get('deleted')
                   and isinstance(item.get('deleted_at'), (int, float))
                   and item['deleted_at'] <= now - RETENTION_SECONDS]
        if expired:
            removed.extend(apply(db, owner, kind, expired, 'delete', now))
    db.commit()
    return removed


def validate_parent(data, identifier, parent):
    visited = {identifier}
    while parent:
        if not isinstance(parent, str) or parent in visited:
            raise ValueError('A folder cannot contain itself.')
        folder = data.get(parent)
        if not folder or not folder.get('folder') or folder.get('deleted'):
            raise ValueError('Folder not found.')
        visited.add(parent)
        parent = folder.get('parent')
