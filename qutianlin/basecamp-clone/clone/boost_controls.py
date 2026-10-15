"""Native Boost controls bound to local recordings and their comments."""
import base64
import copy
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode
from lxml import html, etree
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).parent


def gid(identifier):
    return 'gid://bc3/Recording/' + identifier


def reference(identifier):
    return base64.urlsafe_b64encode(gid(identifier).encode()).decode().rstrip('=')


def identifier(value):
    if not value.startswith('gid://'):
        try:
            value = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True).decode()
        except (ValueError, UnicodeError):
            raise HTTPException(422, 'Choose an item to boost.')
    match = re.fullmatch(r'gid://bc3/Recording/(\d+|local-[a-f0-9]+)', value)
    if not match:
        raise HTTPException(422, 'Choose an item to boost.')
    return match[1]


@lru_cache(maxsize=1)
def source_comment_parents():
    from card_table import DATA
    from comment_replies import source_comments
    routes = {record['url'] for record in DATA['records'].values()}
    routes.update(column['board'].split('/card_tables/')[0] + '/card_tables/columns/' + key for key, column in DATA['columns'].items())
    return {identifier: route for route in sorted(routes) for identifier in source_comments(route)}


def resolve(c, account, bucket, target, referer=''):
    from record_operations import metadata, fields_for
    from thread_notifications import accessible_member
    record = metadata(c, account['workspace_id'], target)
    comment = None
    if not record:
        local = c.execute('SELECT route FROM bc_comments WHERE owner=? AND id=?', (account['workspace_id'], target)).fetchone()
        route = local['route'] if local else source_comment_parents().get(target, '')
        record = metadata(c, account['workspace_id'], route.rsplit('/', 1)[-1])
        if not record or record['url'] != route:
            raise HTTPException(404, 'Item not found')
        from comment_replies import original
        comment = original(c, account, record, target)
    if record['bucket'] != bucket or fields_for(c, account['workspace_id'], record).get('_record_status', 'active') != 'active':
        raise HTTPException(404, 'Item not found')
    if not accessible_member(c, account['workspace_id'], account['account_id'], record['url']):
        raise HTTPException(403, 'You cannot access this project.')
    return record, comment


@lru_cache(maxsize=1)
def posted_template():
    path = ROOT / 'frontend/pages/6302022/buckets/49234166/messages/10398823423/index.html'
    return html.fromstring(path.read_text()).xpath('//*[@data-boost-id]')[0]


@lru_cache(maxsize=1)
def new_button_template():
    tree = html.fromstring((ROOT / 'frontend/pages/6302022/buckets/49234166/messages/10398823423/index.html').read_text())
    return tree.xpath('//a[@aria-label="New boost"]')[0]


def comment_bar(record, target):
    button = copy.deepcopy(new_button_template())
    button.set('href', '/6302022/buckets/' + record['bucket'] + '/boosts/new?' + urlencode({'boost[boostable_gid]': reference(target)}))
    wrapper = etree.Element('div', {'class': 'boosts', 'data-controller': 'boosts', 'data-boosts-deleting-class': 'boost--deleting'})
    etree.SubElement(wrapper, 'turbo-frame', {'class': 'contents', 'id': 'boosts_recording_' + target})
    new = etree.SubElement(wrapper, 'turbo-frame', {'class': 'contents', 'id': 'new_boost_recording_' + target})
    new.append(button)
    return wrapper


def posted(row, account):
    node = copy.deepcopy(posted_template())
    old = node.get('data-boost-id')
    node = html.fromstring(html.tostring(node, encoding='unicode').replace(old, row['id']))
    node.set('data-local-boost', row['id'])
    node.set('data-creator-id', row['author'])
    name = row['display_name'] or 'Member'
    from record_attribution import avatar_url
    for avatar in node.xpath('.//img'):
        avatar.set('src', avatar_url(row['author'], row['route'].rsplit('/', 1)[-1]))
        avatar.set('data-avatar-for-person-id', row['author'])
        avatar.set('alt', name); avatar.set('title', name)
        avatar.attrib.pop('srcset', None)
    for part in node.xpath('.//*[@data-visible-to-creator-or-admin]'):
        part.attrib.pop('data-visible-to-creator-or-admin', None)
    for link in node.xpath('.//a[@data-turbo-method="delete"]'):
        if row['author'] != account['account_id']:
            link.getparent().remove(link)
        else:
            link.set('href', '/6302022/buckets/' + row['route'].split('/')[3] + '/boosts/' + row['id'])
            link.set('data-turbo-frame', '_top')
    content = node.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," boost__content ")]')[0]
    for child in list(content):
        content.remove(child)
    content.attrib.pop('class', None)
    content.set('class', 'boost__content text-nowrap')
    etree.SubElement(content, 'span', {'aria-hidden': 'true'}).text = row['content']
    etree.SubElement(content, 'span', {'class': 'sr-only', 'id': 'content_label_boost_' + row['id']}).text = name + ' boosted this with ‘' + row['content'] + '’'
    return node


def render(tree, path, c, account):
    if path == '/6302022/my/boosts':
        from boost_reports import render as render_report
        render_report(tree, path, c, account)
        return
    from record_operations import metadata, fields_for
    record = metadata(c, account['workspace_id'], path.rsplit('/', 1)[-1])
    if record and record['url'] == path and record.get('is_new'):
        for old in tree.xpath('//*[@data-boost-id]'):
            old.getparent().remove(old)
        for link in tree.xpath('//a[@aria-label="New boost"]'):
            link.set('href', '/6302022/buckets/' + record['bucket'] + '/boosts/new?' + urlencode({'boost[boostable_gid]': reference(record['id'])}))
    if record and record['url'] == path:
        for comment in tree.xpath('//*[@data-local-comment]'):
            bar = comment_bar(record, comment.get('data-local-comment'))
            if fields_for(c, account['workspace_id'], record).get('_comments_closed'):
                for link in bar.xpath('.//a[@aria-label="New boost"]'):
                    link.getparent().remove(link)
            footers = comment.xpath('./footer')
            (footers[0] if footers else comment).append(bar)
    for row in c.execute('SELECT b.*,a.display_name FROM bc_boosts b LEFT JOIN local_auth_accounts a ON a.account_id=b.author WHERE workspace=? ORDER BY created,id', (account['workspace_id'],)):
        if path != row['route']:
            continue
        from thread_notifications import accessible_member
        if not accessible_member(c, account['workspace_id'], account['account_id'], row['route']):
            continue
        try:
            resolve(c, account, row['route'].split('/')[3], row['recording'], row['route'])
        except HTTPException:
            continue
        targets = tree.xpath('//turbo-frame[@id="boosts_recording_' + row['recording'] + '"]')
        if not targets:
            targets = tree.xpath('//main')
        if targets:
            targets[0].insert(0, posted(row, account))


def install(app, db, require_user, csrf_for, session, routes):
    source = next(info for route, info in routes.items() if '/boosts/new?' in route)
    template = (ROOT / 'frontend/pages' / source['file']).read_text()

    @app.get('/6302022/buckets/{bucket}/boosts/new')
    def new_boost(bucket: str, request: Request):
        account = require_user(request)
        target = identifier(request.query_params.get('boost[boostable_gid]', ''))
        with db() as c:
            record, comment = resolve(c, account, bucket, target, request.headers.get('referer', ''))
            from record_operations import fields_for
            if fields_for(c, account['workspace_id'], record).get('_comments_closed'):
                raise HTTPException(409, 'Comments and Boosts are closed on this item.')
            from record_attribution import creator
            name = comment['name'] if comment else creator(c, account['workspace_id'], record)['name'] if record.get('is_new') else ''
            if not name:
                path = ROOT / 'frontend/pages' / record['url'].lstrip('/') / 'index.html'
                if path.is_file():
                    names = html.fromstring(path.read_text()).xpath('//header[contains(@class,"perma-header")]//img[@data-avatar-for-person-id]/@alt')
                    name = names[0] if names else ''
        tree = html.fromstring(template)
        frame = tree.xpath('//turbo-frame[starts-with(@id,"new_boost_recording_")]')[0]
        frame.set('id', 'new_boost_recording_' + target)
        for form in frame.xpath('.//form'):
            form.set('action', '/6302022/buckets/' + bucket + '/boosts')
            form.set('data-turbo-frame', 'boosts_recording_' + target)
            for field in form.xpath('.//input[@name="authenticity_token" or @name="_csrf"]'):
                field.getparent().remove(field)
            etree.SubElement(form, 'input', {'type': 'hidden', 'name': '_csrf', 'value': csrf_for(session(request))})
            for field in form.xpath('.//input[@name="boost[boostable_gid]"]'):
                field.set('value', gid(target))
            for field in form.xpath('.//input[@type="text"]'):
                field.set('placeholder', 'Boost ' + name.split()[0] + '…' if name else 'Boost…')
        return HTMLResponse(html.tostring(frame, encoding='unicode'))
