"""Keep explicit sharing of uploaded rich-text attachments tied to a record."""
from lxml import html
from urllib.parse import unquote, urlsplit


def track(c, account, kind, fields, previous):
    from record_operations import PREFIX, BODY
    key = PREFIX[kind] + '[' + BODY[kind] + ']'
    if not account or key not in fields:
        return
    tree = html.fragment_fromstring(str(fields[key] or ''), create_parent='div')
    previous_files = set(previous.get('_attachment_files', []))
    shared = set()
    for value in tree.xpath('.//@src|.//@href'):
        if not value.startswith('/files/'):
            continue
        parts = urlsplit(value).path.split('/')
        if len(parts) < 4:
            continue
        identifier = unquote(parts[2])
        row = c.execute('SELECT uploader FROM bc_files WHERE owner=? AND id=? AND uploaded=1', (account['workspace_id'], identifier)).fetchone()
        # Knowing another person's unshared file URL cannot grant access.
        if row and (row['uploader'] == account['account_id'] or identifier in previous_files):
            shared.add(identifier)
    fields['_attachment_files'] = sorted(shared)


def accessible(c, account, identifier):
    from record_operations import metadata, fields_for
    from column_lifecycle import record_status
    from workspaces import allows
    for row in c.execute('SELECT id FROM bc_records WHERE owner=?', (account['workspace_id'],)):
        record = metadata(c, account['workspace_id'], row['id'])
        if not record or not allows(account, record['url']):
            continue
        fields = fields_for(c, account['workspace_id'], record)
        if identifier in fields.get('_attachment_files', []) and record_status(c, account['workspace_id'], record, fields) != 'trashed':
            return True
    return False
