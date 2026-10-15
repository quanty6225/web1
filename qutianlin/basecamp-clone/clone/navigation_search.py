"""Native navigation search fragments, using the captured menu row structure."""
from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import HTMLResponse
from lxml import html
from task_reports import project_names
from trash import erased
from workspaces import allows, members

MENU = html.parse(str(Path(__file__).parent / 'frontend/components/6e808a01f0b43ad6.html'))
PROJECT = MENU.xpath('//li[@data-bucket-id]')[0]
PERSON = MENU.xpath('//li[@data-person-id]')[0]


def person_row(person):
    row = deepcopy(PERSON)
    identifier, name = person['account'], person['name']
    row.set('id', 'navigation_menu_person_' + identifier)
    row.set('data-person-id', identifier)
    button = row.xpath('.//button')[0]
    button.set('data-rich-avatar-url', '/6302022/people/53382586/rich_avatar?' + urlencode({'person_id': identifier}))
    for image in row.xpath('.//img'):
        image.set('src', '/api/avatar.svg?' + urlencode({'person': identifier}))
        image.set('alt', name); image.set('title', name)
        image.set('data-avatar-for-person-id', identifier)
    spans = button.xpath('./span')
    spans[0].text = name
    spans[1].text = person['email']
    return row


def project_row(identifier, name):
    row = deepcopy(PROJECT)
    for node in row.iter():
        for key, value in list(node.attrib.items()):
            node.set(key, value.replace('49234165', identifier).replace('My Project', name))
        if node.text:
            node.text = node.text.replace('My Project', name)
    row.xpath('.//a')[0].set('href', '/6302022/projects/' + identifier)
    return row


def render(tree, account, connection):
    # The captured initial row is the signed-in person, not the source owner.
    person = next((p for p in members(connection, account['workspace_id']) if p['account'] == account['account_id']), None)
    if person:
        for row in tree.xpath('//li[@data-person-id and starts-with(@id,"navigation_menu_person_")]'):
            row.getparent().replace(row, person_row(person))
    for row in tree.xpath('//li[@data-bucket-id and starts-with(@id,"my_navigation_menu_bucket_")]'):
        identifier = row.get('data-bucket-id')
        saved = connection.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="project"', (account['workspace_id'], '/6302022/projects/' + identifier)).fetchone()
        fields = json.loads(saved['payload']) if saved else {}
        name = fields.get('project[name]', project_names().get(identifier))
        if name:
            row.getparent().replace(row, project_row(identifier, name))


def install(router, db, require_user):
    @router.get('/6302022/my/navigation/menu/search/projects')
    def projects(request: Request):
        account = require_user(request)
        query = request.query_params.get('q', '').strip().casefold()
        result = []
        with db() as connection:
            for identifier, source_name in project_names().items():
                route = '/6302022/projects/' + identifier
                if not allows(account, route) or erased(connection, account['workspace_id'], identifier):
                    continue
                saved = connection.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="project"', (account['workspace_id'], route)).fetchone()
                fields = json.loads(saved['payload']) if saved else {}
                if fields.get('_status') == 'trashed':
                    continue
                if fields.get('_status') == 'archived' and request.query_params.get('include_archived') != '1':
                    continue
                name = fields.get('project[name]', source_name)
                if not query or query not in name.casefold():
                    continue
                row = project_row(identifier, name)
                result.append(html.tostring(row, encoding='unicode'))
        return HTMLResponse(''.join(result), headers={'Cache-Control': 'private, no-store'})

    @router.get('/6302022/my/navigation/menu/search/people')
    def people(request: Request):
        account = require_user(request)
        query = request.query_params.get('q', '').strip().casefold()
        with db() as connection:
            rows = [person_row(person) for person in members(connection, account['workspace_id'])
                    if query and query in (person['name'] + ' ' + person['email']).casefold()]
        return HTMLResponse(''.join(html.tostring(row, encoding='unicode') for row in rows), headers={'Cache-Control': 'private, no-store'})
