"""Personal project colors and stars, with native Turbo card replacement."""
import json
import re
from lxml import html, etree
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

COLORS = {'white', 'yellow', 'orange', 'red', 'pink', 'purple', 'blue', 'green', 'brown', 'gray'}


def key(account, bucket, name):
    return 'project-' + name + ':' + account['workspace_id'] + ':' + bucket


def preference(c, account, bucket, name):
    row = c.execute('SELECT value FROM bc_settings WHERE owner=? AND name=?',
                    (account['account_id'], key(account, bucket, name))).fetchone()
    return json.loads(row['value']) if row else None


def render(tree, c, account):
    for picker in tree.xpath('//details[@data-color-picker-path]'):
        match = re.fullmatch(r'/6302022/buckets/(\d+)/user_customizations', picker.get('data-color-picker-path'))
        if not match:
            continue
        bucket = match[1]
        color = preference(c, account, bucket, 'color')
        if color not in COLORS:
            continue
        picker.set('data-color-picker-selected', color)
        cards = picker.xpath('ancestor::article[contains(concat(" ",normalize-space(@class)," ")," card ")]')
        for card in cards:
            style = re.sub(r'--recording-color\s*:[^;]*;?', '', card.get('style', '')).strip()
            card.set('style', style + (';' if style and not style.endswith(';') else '') + '--recording-color: var(--recording-color-' + ('canvas' if color == 'white' else color) + ');')
    for form in tree.xpath('//form[contains(@action,"/stars")]'):
        match = re.fullmatch(r'/6302022/buckets/(\d+)/stars', form.get('action', ''))
        if not match:
            continue
        active = preference(c, account, match[1], 'star')
        if active is None:
            continue
        for button in form.xpath('.//button'):
            classes = [v for v in button.get('class', '').split() if v not in ('star-button--starred', 'star-button--unstarred')]
            button.set('class', ' '.join(classes + ['star-button--starred' if active else 'star-button--unstarred']))
            button.set('aria-pressed', str(active).lower())
        methods = form.xpath('.//input[@name="_method"]')
        field = methods[0] if methods else etree.SubElement(form, 'input', {'type': 'hidden', 'name': '_method'})
        field.set('value', 'delete' if active else 'post')


def install(app, db, require_user, csrf_check, render_home):
    router = APIRouter()

    def card(request, account, bucket):
        tree = html.fromstring(render_home(request, account))
        cards = tree.xpath('//article[.//a[@href="/6302022/projects/' + bucket + '"]]')
        if not cards:
            raise HTTPException(404, 'Project not found')
        return cards[0]

    async def change(request, bucket, name):
        account = require_user(request)
        data = await request.json() if 'application/json' in request.headers.get('content-type', '') else await request.form()
        csrf_check(request, data)
        # Read the actual owned home card before persisting any preference.
        if not bucket.isdigit():
            raise HTTPException(404, 'Project not found')
        card(request, account, bucket)
        method = str(data.get('_method', request.method)).upper()
        value = str(data.get('user_customization[color]', '')) if name == 'color' else method != 'DELETE'
        if name == 'color' and value not in COLORS:
            raise HTTPException(422, 'Choose one of the available project colors.')
        with db() as c:
            c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,?,?)',
                      (account['account_id'], key(account, bucket, name), json.dumps(value)))
        if 'application/json' in request.headers.get('accept', ''):
            return {'saved': True, name: value}
        if 'text/vnd.turbo-stream.html' in request.headers.get('accept', ''):
            replacement = card(request, account, bucket)
            stream = etree.Element('turbo-stream', {'action': 'replace', 'target': replacement.get('id')})
            etree.SubElement(stream, 'template').append(replacement)
            return HTMLResponse(html.tostring(stream, encoding='unicode'), media_type='text/vnd.turbo-stream.html')
        return RedirectResponse('/6302022/', 303)

    @router.api_route('/6302022/buckets/{bucket}/user_customizations', methods=['POST', 'PATCH', 'PUT'])
    async def color(bucket: str, request: Request):
        return await change(request, bucket, 'color')

    @router.api_route('/6302022/buckets/{bucket}/stars', methods=['POST', 'PATCH', 'PUT', 'DELETE'])
    async def star(bucket: str, request: Request):
        return await change(request, bucket, 'star')

    app.include_router(router)
