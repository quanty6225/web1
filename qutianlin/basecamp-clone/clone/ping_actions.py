"""Private message reactions, bookmarks and reminders; never project records."""
import time

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from lxml import html, etree

REACTIONS = ('👍', '👏', '👋', '❤️', '😂', '😊', '🎉', '🚀')


def initialize(db):
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS bc_ping_reactions(
            ping TEXT, line TEXT, account TEXT, content TEXT, created REAL,
            PRIMARY KEY(ping,line,account,content));
        CREATE TABLE IF NOT EXISTS bc_ping_bookmarks(
            ping TEXT, line TEXT, account TEXT, created REAL,
            PRIMARY KEY(ping,line,account));
        ''')


def require_line(c, account, ping, line):
    from pings import require_ping
    require_ping(c, account, ping)
    row = c.execute('SELECT * FROM bc_ping_lines WHERE ping=? AND id=?', (ping, line)).fetchone()
    if not row:
        raise HTTPException(404, 'Message not found')
    return dict(row)


def reminder_target(c, account, line):
    row = c.execute('SELECT * FROM bc_ping_lines WHERE id=?', (line,)).fetchone()
    if not row:
        raise HTTPException(404, 'Message not found')
    row = require_line(c, account, row['ping'], line)
    text = ' '.join(html.fragment_fromstring(row['body'] or '', create_parent='div').text_content().split())
    if not text:
        files = c.execute('SELECT filename FROM bc_ping_files WHERE ping=? AND posted_line=?', (row['ping'], line)).fetchall()
        text = ', '.join(file['filename'] for file in files) or 'Ping'
    return {'id': line, 'url': permalink(row['ping'], line), 'title': text,
            'bubble_path': endpoint(row['ping'], line) + '/bubble_up'}


def endpoint(ping, line):
    return '/api/pings/' + ping + '/lines/' + line


def permalink(ping, line):
    return '/6302022/circles/' + ping + '#local_chat_' + line


def markup(c, account, row):
    line, ping = row['id'], row['ping']
    saved = bool(c.execute('SELECT 1 FROM bc_ping_bookmarks WHERE ping=? AND line=? AND account=?',
                          (ping, line, account['account_id'])).fetchone())
    menu = etree.Element('details', {'class': 'local-ping-actions', 'data-local-ping-actions': ''})
    etree.SubElement(menu, 'summary', {'class': 'btn btn--icon btn--sm btn--ghost', 'aria-label': 'Message options'}).text = '•••'
    panel = etree.SubElement(menu, 'div', {'class': 'local-ping-actions-panel', 'popover': 'manual'})
    reactions = etree.SubElement(panel, 'div', {'class': 'local-ping-reaction-picker', 'aria-label': 'Reactions'})
    own = {r['content'] for r in c.execute('SELECT content FROM bc_ping_reactions WHERE ping=? AND line=? AND account=?', (ping, line, account['account_id']))}
    for reaction in REACTIONS:
        etree.SubElement(reactions, 'button', {'type': 'button', 'class': 'btn btn--sm btn--ghost',
            'data-local-ping-reaction': reaction, 'aria-label': reaction, 'aria-pressed': str(reaction in own).lower()}).text = reaction
    etree.SubElement(panel, 'button', {'type': 'button', 'class': 'btn btn--sm btn--ghost',
        'data-local-ping-copy': permalink(ping, line)}).text = 'Copy link'
    etree.SubElement(panel, 'button', {'type': 'button', 'class': 'btn btn--sm btn--ghost',
        'data-local-ping-bubble': ''}).text = 'Bubble up'
    etree.SubElement(panel, 'button', {'type': 'button', 'class': 'btn btn--sm btn--ghost',
        'data-local-ping-bookmark': '', 'aria-pressed': str(saved).lower()}).text = 'Remove bookmark' if saved else 'Bookmark'
    etree.SubElement(panel, 'div', {'data-local-ping-bubble-editor': ''})
    bar = etree.Element('div', {'class': 'chat-line__boosts', 'data-local-ping-reactions': ''})
    grouped = {}
    for reaction in c.execute('SELECT r.*,a.display_name FROM bc_ping_reactions r LEFT JOIN local_auth_accounts a ON a.account_id=r.account WHERE r.ping=? AND r.line=? ORDER BY r.created,r.account', (ping, line)):
        grouped.setdefault(reaction['content'], []).append(reaction)
    for reaction, people in grouped.items():
        names = ', '.join(person['display_name'] or 'Member' for person in people)
        etree.SubElement(bar, 'button', {'type': 'button', 'class': 'btn btn--sm btn--ghost',
            'data-local-ping-reaction': reaction, 'aria-pressed': str(reaction in own).lower(),
            'aria-label': reaction + ': ' + names, 'title': names}).text = reaction + ' ' + str(len(people))
    return html.tostring(menu, encoding='unicode'), html.tostring(bar, encoding='unicode')


def render_bookmarks(tree, path, c, account):
    if path != '/6302022/my/navigation/bookmarks':
        return
    targets = tree.xpath('//*[@id="my_navigation_bookmarks"]')
    if not targets:
        return
    for row in c.execute('SELECT b.* FROM bc_ping_bookmarks b JOIN bc_pings p ON p.id=b.ping WHERE b.account=? AND p.workspace=? ORDER BY b.created DESC', (account['account_id'], account['workspace_id'])):
        try:
            item = reminder_target(c, account, row['line'])
        except HTTPException:
            continue
        entry = etree.SubElement(targets[0], 'div', {'class': 'local-new-item flex align-center gap-8', 'data-local-ping-bookmark-row': row['line']})
        etree.SubElement(entry, 'a', {'href': item['url'], 'data-quick-find-target': 'searchable',
            'data-list-navigation-target': 'focusable'}).text = item['title']
        etree.SubElement(entry, 'button', {'type': 'button', 'class': 'btn btn--sm btn--ghost',
            'aria-label': 'Remove bookmark', 'data-local-ping-bookmark-remove': endpoint(row['ping'], row['line']) + '/bookmark'}).text = '×'
        for empty in tree.xpath('//*[contains(@class,"blank-slate") or contains(@class,"empty-state") or contains(@class,"tray__empty")]'):
            if empty.getparent() is not None:
                empty.getparent().remove(empty)


def forget_line(c, ping, line):
    for table in ('bc_ping_reactions', 'bc_ping_bookmarks'):
        c.execute(f'DELETE FROM {table} WHERE ping=? AND line=?', (ping, line))
    c.execute('DELETE FROM bc_bubble_ups WHERE target=?', ('ping:' + line,))


def install(router, db, require_user, csrf_check, csrf_token, publish):
    async def update_line(ping, line, account):
        from pings import line_markup
        with db() as c:
            row = require_line(c, account, ping, line)
            rendered = line_markup(c, account, row)
        await publish(ping, {'type': 'updated', 'id': line, 'row': row})
        return {'type': 'updated', 'id': line, 'html': rendered}

    @router.api_route('/api/pings/{ping}/lines/{line}/reactions/{reaction}', methods=['PUT', 'DELETE'])
    async def react(ping: str, line: str, reaction: str, request: Request):
        account = require_user(request)
        csrf_check(request, {})
        if reaction not in REACTIONS:
            raise HTTPException(422, 'Choose a reaction.')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            require_line(c, account, ping, line)
            key = (ping, line, account['account_id'], reaction)
            if request.method == 'DELETE':
                c.execute('DELETE FROM bc_ping_reactions WHERE ping=? AND line=? AND account=? AND content=?', key)
            else:
                c.execute('INSERT OR IGNORE INTO bc_ping_reactions VALUES(?,?,?,?,?)', (*key, time.time()))
        return await update_line(ping, line, account)

    @router.api_route('/api/pings/{ping}/lines/{line}/bookmark', methods=['PUT', 'DELETE'])
    async def bookmark(ping: str, line: str, request: Request):
        account = require_user(request)
        csrf_check(request, {})
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            require_line(c, account, ping, line)
            key = (ping, line, account['account_id'])
            if request.method == 'DELETE':
                c.execute('DELETE FROM bc_ping_bookmarks WHERE ping=? AND line=? AND account=?', key)
            else:
                c.execute('INSERT OR IGNORE INTO bc_ping_bookmarks VALUES(?,?,?,?)', (*key, time.time()))
        return await update_line(ping, line, account)

    @router.get('/api/pings/{ping}/lines/{line}/bubble_up/edit')
    def bubble_edit(ping: str, line: str, request: Request):
        from bubble_up import edit_markup
        account = require_user(request)
        with db() as c:
            require_line(c, account, ping, line)
            return HTMLResponse(edit_markup(c, account, 'ping', line, request.url.path.removesuffix('/edit'), csrf_token(request), request.query_params.get('view') == 'all'))

    @router.api_route('/api/pings/{ping}/lines/{line}/bubble_up', methods=['POST', 'PUT', 'PATCH', 'DELETE'])
    async def bubble(ping: str, line: str, request: Request):
        from bubble_up import due_at, zone, sidebar_streams, pending, OVERVIEW
        account = require_user(request)
        data = await request.json() if 'application/json' in request.headers.get('content-type', '') else await request.form()
        csrf_check(request, data)
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            require_line(c, account, ping, line)
            item = reminder_target(c, account, line)
            key = (account['account_id'], account['workspace_id'], 'ping:' + line)
            if str(data.get('_method', request.method)).upper() == 'DELETE':
                c.execute('DELETE FROM bc_bubble_ups WHERE account=? AND workspace=? AND target=?', key)
                due = None
            else:
                now = time.time()
                due = due_at(data.get('at'), zone(c, account), now)
                c.execute('INSERT OR REPLACE INTO bc_bubble_ups VALUES(?,?,?,?,?,?,?,NULL)', (*key, item['url'], item['title'], due, now if due <= now else None))
        if 'application/json' in request.headers.get('accept', ''):
            return {'saved': True, 'due': due, 'redirect': item['url']}
        if 'turbo-stream' in request.headers.get('accept', ''):
            with db() as c:
                full_view = data.get('return_to') == OVERVIEW and bool(pending(c, account, include_future=True))
            return Response(sidebar_streams(db, account, csrf_token(request), full_view), media_type='text/vnd.turbo-stream.html')
        return RedirectResponse(item['url'], 303)
