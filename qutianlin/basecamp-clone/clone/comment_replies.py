"""Source-shaped comment quotes, tied to an original in the same discussion."""
import copy
import json
import re
from functools import lru_cache
from pathlib import Path
from datetime import datetime, timezone
from lxml import html, etree
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from record_operations import metadata, fields_for
from local_render import safe_rich_text

ROOT = Path(__file__).parent
TEMPLATE = (ROOT / 'frontend/comment-reply-bubble.html').read_text()


def initialize(db):
    with db() as c:
        if 'reply' not in {r['name'] for r in c.execute('PRAGMA table_info(bc_comments)')}:
            c.execute('ALTER TABLE bc_comments ADD COLUMN reply TEXT')


@lru_cache(maxsize=128)
def source_comments(route):
    path = ROOT / 'frontend/pages' / route.lstrip('/') / 'index.html'
    if not path.exists():
        return {}
    tree = html.fromstring(path.read_text())
    result = {}
    for node in tree.xpath('//article[@data-comment and @data-recording-id]'):
        body = node.xpath('./div[contains(concat(" ",normalize-space(@class)," ")," formatted_content ")]')
        author = node.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," thread-entry__author ")]')
        timestamp = node.xpath('./header//time/@datetime')
        avatars = node.xpath('./header//img/@src')
        if not body or not author:
            continue
        identifier = node.get('data-recording-id')
        result[identifier] = {'id': identifier, 'author': node.get('data-creator-id'), 'name': author[0].text_content().strip(),
                              'body': safe_rich_text(html.tostring(body[0], encoding='unicode')), 'timestamp': timestamp[0] if timestamp else '',
                              'url': route + '#__recording_' + identifier, 'avatar': avatars[0] if avatars else ''}
    return result


def original(c, account, record, identifier):
    row = c.execute('SELECT m.*,a.display_name FROM bc_comments m LEFT JOIN local_auth_accounts a ON a.account_id=m.author WHERE m.owner=? AND m.route=? AND m.id=?',
                    (account['workspace_id'], record['url'], identifier)).fetchone()
    if row:
        return {'id': row['id'], 'author': row['author'], 'name': row['display_name'] or 'Member', 'body': safe_rich_text(row['body']),
                'timestamp': datetime.fromtimestamp(row['created'], timezone.utc).isoformat(), 'url': record['url'] + '#comment-' + row['id']}
    source = None if record.get('is_new') else source_comments(record['url']).get(identifier)
    if not source:
        raise HTTPException(404, 'The original comment was not found in this discussion.')
    result = dict(source)
    if result['author'] == '53382586':
        result['author'] = account['workspace_id']
        author = c.execute('SELECT display_name FROM local_auth_accounts WHERE account_id=?', (result['author'],)).fetchone()
        if author:
            result['name'] = author['display_name']
    return result


def snapshot(c, account, record, payload):
    identifier = str(payload.get('comment[original_id]', '')).strip()
    if not identifier:
        return None
    result = original(c, account, record, identifier)
    excerpt = str(payload.get('comment[excerpt]', '')).strip()
    if excerpt:
        normalize = lambda value: re.sub(r'\s+', ' ', value).strip()
        body_text = html.fragment_fromstring(result['body'], create_parent='div').text_content()
        if normalize(excerpt) not in normalize(body_text):
            raise HTTPException(422, 'The selected quote must come from the original comment.')
        result['excerpt'] = excerpt
    return result


def bubble(quote, preview=False):
    frame = html.fromstring(TEMPLATE)
    link = frame.xpath('//*[contains(@class,"thread-reply-bubble__author")]/a')[0]
    link.text = quote['name']
    for anchor in frame.xpath('.//a'):
        anchor.set('href', quote['url'])
    for node in frame.xpath('.//time'):
        node.set('datetime', quote['timestamp'])
        node.text = quote['timestamp']
    content = frame.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," clamp__content ")]')[0]
    for child in list(content):
        content.remove(child)
    content.text = ''
    if quote.get('excerpt'):
        etree.SubElement(content, 'div', {'class': 'thread-reply-bubble__excerpt'}).text = quote['excerpt']
    else:
        body = html.fragment_fromstring(safe_rich_text(quote['body']), create_parent='div')
        content.text = body.text
        for child in list(body):
            content.append(child)
    if preview:
        return frame
    block = frame.xpath('./div[contains(@class,"thread-reply-bubble")]')[0]
    for node in block.xpath('.//*[@inert]'):
        node.attrib.pop('inert', None)
    for node in block.xpath('.//button[@aria-label="Remove reply"]'):
        node.getparent().remove(node)
    block.set('data-local-reply-original', quote['id'])
    return block


@lru_cache(maxsize=1)
def reply_button():
    page = ROOT / 'frontend/pages/6302022/buckets/49234166/messages/10398823423/index.html'
    tree = html.fromstring(page.read_text())
    return tree.xpath('//button[@aria-label="Reply to this comment"]')[0]


def append_button(node, record, identifier):
    footer = etree.SubElement(node, 'footer', {'class': 'thread-entry__footer'})
    button = copy.deepcopy(reply_button())
    button.set('data-thread--reply-original-id-param', identifier)
    button.set('data-thread--reply-url-param', '/6302022/buckets/' + record['bucket'] + '/recordings/' + record['id'] + '/comments/' + identifier + '/replies/new')
    footer.append(button)


def install(app, db, require_user):
    router = APIRouter()

    @router.get('/6302022/buckets/{bucket}/recordings/{recording}/comments/{identifier}/replies/new')
    def preview(bucket: str, recording: str, identifier: str, request: Request):
        account = require_user(request)
        with db() as c:
            record = metadata(c, account['workspace_id'], recording)
            if not record or record['bucket'] != bucket:
                raise HTTPException(404, 'Record not found')
            state = fields_for(c, account['workspace_id'], record)
            if state.get('_record_status', 'active') != 'active':
                raise HTTPException(404, 'Record not found')
            if state.get('_comments_closed'):
                raise HTTPException(409, 'Comments are closed on this item.')
            quote = original(c, account, record, identifier)
        return HTMLResponse(html.tostring(bubble(quote, preview=True), encoding='unicode'))

    app.include_router(router)
