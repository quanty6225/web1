"""Show the creator of a local recording, never its captured prototype's creator."""
from datetime import datetime, timezone


def avatar_url(person, recording):
    return '/api/avatar.svg?person=' + person + '&recording=' + recording


def historical_person(connection, account, person, recording):
    """A departed author stays visible only through an accessible recording."""
    if not recording or account.get('closed'):
        return None
    from record_operations import metadata
    from workspaces import allows
    record = metadata(connection, account['workspace_id'], recording)
    if not record or not allows(account, record['url']):
        return None
    authored = record.get('is_new') and creator(connection, account['workspace_id'], record)['id'] == person
    if not authored:
        authored = connection.execute('SELECT 1 FROM bc_comments WHERE owner=? AND route=? AND author=? UNION ALL SELECT 1 FROM bc_boosts WHERE workspace=? AND route=? AND author=? LIMIT 1',
                                      (account['workspace_id'], record['url'], person, account['workspace_id'], record['url'], person)).fetchone()
    if authored:
        return connection.execute('SELECT display_name FROM local_auth_accounts WHERE account_id=?', (person,)).fetchone()
    return None


def creator(connection, owner, record):
    identifier = record.get('author')
    if not identifier and record['kind'] == 'uploads':
        from record_operations import fields_for
        file_id = fields_for(connection, owner, record).get('_file_id')
        file = connection.execute('SELECT uploader FROM bc_files WHERE id=? AND owner=?', (file_id, owner)).fetchone()
        identifier = file['uploader'] if file else None
    if not identifier:
        event = connection.execute('SELECT author FROM bc_events WHERE workspace=? AND route=? AND action="posted" ORDER BY created,id LIMIT 1', (owner, record['url'])).fetchone()
        identifier = event['author'] if event else None
    person = connection.execute('SELECT display_name FROM local_auth_accounts WHERE account_id=?', (identifier,)).fetchone() if identifier else None
    return {'id': identifier, 'name': person['display_name'] if person else 'Member'}


def card_summary(tree, connection, owner, record):
    person = creator(connection, owner, record)
    created = datetime.fromtimestamp(record['created'], timezone.utc)
    for byline in tree.xpath('.//span[contains(concat(" ",normalize-space(@class)," ")," task-details__assignee ")]'):
        byline.text = 'By ' + person['name'] + ' '
        for stamp in byline.xpath('./time'):
            stamp.set('datetime', created.isoformat())
            stamp.set('title', created.strftime('%B %d, %Y at %H:%M UTC'))
            for key in ('data-turbo-permanent', 'data-processed-at', 'data-localized'):
                stamp.attrib.pop(key, None)
            stamp.text = created.strftime('on %b %d, %Y')


def render(tree, connection, owner, record):
    person = creator(connection, owner, record)
    created = datetime.fromtimestamp(record['created'], timezone.utc)
    # Message authors also have a portrait beside the document body, outside
    # the header used by the other recording templates.
    for avatar in tree.xpath('//article[@id="recording_' + record['id'] + '"]/section[contains(concat(" ",normalize-space(@class)," ")," document-style-content ")]/img[@data-avatar-for-person-id]'):
        avatar.set('alt', person['name']); avatar.set('title', person['name'])
        if person['id']:
            avatar.set('src', avatar_url(person['id'], record['id']))
            avatar.set('data-avatar-for-person-id', person['id'])
        else:
            avatar.getparent().remove(avatar)
        avatar.attrib.pop('srcset', None)
    headers = tree.xpath('//main//*[contains(concat(" ",normalize-space(@class)," ")," perma-header ")]')
    for header in headers:
        for avatar in header.xpath('.//img[@data-avatar-for-person-id]'):
            avatar.set('alt', person['name']); avatar.set('title', person['name'])
            if person['id']:
                avatar.set('src', avatar_url(person['id'], record['id']))
                avatar.set('data-avatar-for-person-id', person['id'])
            else:
                avatar.attrib.pop('src', None)
                avatar.attrib.pop('data-avatar-for-person-id', None)
            avatar.attrib.pop('srcset', None)
            if (avatar.tail or '').strip():
                avatar.tail = ' ' + person['name'] + ' '
            else:
                sibling = avatar.getnext()
                if sibling is not None and sibling.tag == 'span' and not sibling.xpath('.//time'):
                    for child in list(sibling): sibling.remove(child)
                    sibling.text = person['name']
            if not person['id']: avatar.drop_tag()
        for stamp in header.xpath('.//time'):
            stamp.set('datetime', created.isoformat())
            stamp.set('title', created.strftime('%B %d, %Y at %H:%M UTC'))
            stamp.attrib.pop('data-processed-at', None)
            stamp.attrib.pop('data-localized', None)
            stamp.text = created.strftime('%b %d, %Y')
        for link in header.xpath('.//a[contains(@href,"/notified_recipients")]'):
            # A prototype's historical notification count does not describe a
            # new local recording. Its actual discussion audience is below.
            parent = link.getparent()
            if parent is not None: parent.remove(link)
    for node in tree.xpath('//*[@data-recording-id="' + record['id'] + '" and @data-creator-id]'):
        if person['id']: node.set('data-creator-id', person['id'])
        else: node.attrib.pop('data-creator-id', None)
    return person
