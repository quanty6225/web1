"""Current role holders in the evidenced Adminland overview and profile sheet."""
from copy import deepcopy
from urllib.parse import urlencode
from fastapi import HTTPException
from workspaces import members


def render(tree, path, account, connection, query):
    if path.rstrip('/') == '/6302022/account':
        people = members(connection, account['workspace_id'])
        for section in tree.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," superpowers ")]'):
            owners = 'superpowers--owner' in section.get('class', '').split()
            groups = section.xpath('./header//*[contains(@class,"avatar-group")]')
            if not groups or not len(groups[0]):
                continue
            group = groups[0]; prototype = deepcopy(group[0])
            for child in list(group):
                group.remove(child)
            for person in people:
                if person['role'] not in (('owner',) if owners else ('owner', 'admin')):
                    continue
                holder = deepcopy(prototype)
                holder.set('data-role-holder', person['account'])
                button = holder.xpath('.//button')[0]
                button.set('aria-label', person['name'])
                button.set('data-rich-avatar-url', '/6302022/people/53382586/rich_avatar?' + urlencode({'person_id': person['account']}))
                button.tail = ' ' + person['name']
                for avatar in button.xpath('.//img'):
                    avatar.set('src', '/api/avatar.svg?person=' + person['account'])
                    avatar.set('data-avatar-for-person-id', person['account'])
                    avatar.set('alt', person['name']); avatar.set('title', person['name'])
                group.append(holder)
    if path != '/6302022/people/53382586/rich_avatar' or not query or not query.get('person_id'):
        return
    identifier = query['person_id']
    person = next((person for person in members(connection, account['workspace_id']) if person['account'] == identifier), None)
    if not person:
        raise HTTPException(404, 'Person not found')
    for sheet in tree.xpath('//*[@data-modal-label]'):
        sheet.set('data-modal-label', person['name'])
    for name in tree.xpath('//*[contains(@class,"rich-avatar__name")]'):
        name.text = person['name']
    for avatar in tree.xpath('//img[@data-avatar-for-person-id]'):
        avatar.set('src', '/api/avatar.svg?person=' + identifier)
        avatar.set('data-avatar-for-person-id', identifier)
        avatar.set('alt', person['name']); avatar.set('title', person['name'])
    for badge in tree.xpath('//*[contains(@class,"rich-avatar-badge")]'):
        if person['role'] == 'owner':
            badge.text = 'Owner'
        elif person['role'] == 'admin':
            badge.text = 'Admin'
        else:
            badge.getparent().remove(badge)
    if identifier != account['account_id']:
        # The captured self-profile's personal edit links, job title and timezone
        # must not be attributed to another local person.
        for node in tree.xpath('//*[contains(@class,"rich-avatar__actions") or contains(@class,"rich-avatar__title") or contains(@class,"rich-avatar__time")]'):
            node.getparent().remove(node)
