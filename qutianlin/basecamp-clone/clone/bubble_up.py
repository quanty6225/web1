"""Personal, durable Bubble Up scheduling using the captured native forms."""
import json
import copy
import hashlib
import re
import time
from datetime import datetime, timedelta, time as day_time
from pathlib import Path
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from lxml import html, etree
from record_operations import metadata, fields_for, PREFIX, TITLE
from workspaces import allows

ROOT = Path(__file__).parent / 'frontend'
ROUTES = json.loads((ROOT / 'routes.json').read_text())
INBOX = '/6302022/my/sidebar/inbox'
OVERVIEW = '/6302022/my/sidebar/bubble_ups'
EDIT = next(key for key in ROUTES if '/recordings/' in key and key.endswith('/bubble_up/edit'))
TIMEZONES = json.loads((ROOT / 'rails-timezones.json').read_text())['mapping']


def source_tree(path):
    info = ROUTES[path]
    return html.fromstring((ROOT / 'pages' / info.get('component_file', info['file'])).read_text())


WELCOME = {}
for _row in source_tree(INBOX).xpath('//article[@data-reading]'):
    _link = _row.xpath('.//a')[0]
    WELCOME[_row.get('id').removeprefix('reading_')] = {
        'id': _link.get('href').rsplit('/', 1)[-1], 'url': _link.get('href'),
        'title': ' '.join(_row.xpath('.//h4')[0].text_content().split()).removeprefix('A message from Basecamp, '),
    }


def initialize(db):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS bc_bubble_ups(
            account TEXT, workspace TEXT, target TEXT, route TEXT, title TEXT,
            due REAL NOT NULL, delivered REAL, read_at REAL,
            PRIMARY KEY(account, workspace, target))''')


def preferences(c, account):
    row = c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route="/6302022/my/preferences" ORDER BY updated DESC LIMIT 1', (account['account_id'],)).fetchone()
    return json.loads(row['payload']) if row else {}


def zone(c, account):
    name = preferences(c, account).get('person[time_zone_name]', 'Beijing')
    try:
        return ZoneInfo(TIMEZONES.get(name, name))
    except ZoneInfoNotFoundError:
        raise HTTPException(422, 'Choose a supported time zone in My preferences.')


def due_at(value, tz, now):
    if value == 'now':
        return now
    today = datetime.fromtimestamp(now, tz).date()
    if value == 'today':
        due = datetime.combine(today, day_time(16), tz).timestamp()
        if due <= now:
            raise HTTPException(422, 'Choose a future time for Bubble Up.')
        return due
    if value == 'tomorrow':
        date = today + timedelta(days=1)
    elif value in ('weekend', 'next_week'):
        weekday = 5 if value == 'weekend' else 0
        date = today + timedelta(days=(weekday - today.weekday()) % 7 or 7)
    else:
        try:
            date = datetime.strptime(value, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            raise HTTPException(422, 'Choose a date for Bubble Up.')
        if not today < date <= today + timedelta(days=365):
            raise HTTPException(422, 'Choose a date between tomorrow and one year from today.')
    return datetime.combine(date, day_time(8), tz).timestamp()


@lru_cache(maxsize=1)
def source_chats():
    items = {}
    for path in ROUTES:
        match = re.fullmatch(r'/6302022/buckets/(\d+)/chats/(\d+)', path)
        if not match:
            continue
        tree = source_tree(path)
        items[match[2]] = {'id': match[2], 'bucket': match[1], 'url': path, 'title': ROUTES[path]['title']}
        for line in tree.xpath('//*[@data-behavior="chat_line"][@data-recording-id]'):
            identifier = line.get('data-recording-id')
            body = line.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " chat-line__body ")]')
            title = ' '.join((body[0] if body else line).text_content().split())
            items[identifier] = {'id': identifier, 'bucket': match[1], 'url': path + '#recording_' + identifier, 'title': title}
    return items


def target(c, account, kind, identifier, bucket=None):
    if kind == 'ping':
        from ping_actions import reminder_target
        return reminder_target(c, account, identifier)
    if kind == 'reading':
        welcome = WELCOME.get(identifier)
        if welcome:
            return welcome
        raise HTTPException(404, 'Notification not found')
    record = metadata(c, account['workspace_id'], identifier)
    if not record:
        item = source_chats().get(identifier)
        if item and (not bucket or item['bucket'] == bucket) and allows(account, item['url']):
            project = c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="project"',
                                (account['workspace_id'], '/6302022/projects/' + item['bucket'])).fetchone()
            if not project or json.loads(project['payload']).get('_status') != 'trashed':
                return item
    if not record or bucket and record['bucket'] != bucket or not allows(account, record['url']):
        raise HTTPException(404, 'Item not found')
    fields = fields_for(c, account['workspace_id'], record)
    from column_lifecycle import record_status
    if record_status(c, account['workspace_id'], record, fields) != 'active':
        raise HTTPException(404, 'Item not found')
    deleted = c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="project"',
                        (account['workspace_id'], '/6302022/projects/' + record['bucket'])).fetchone()
    if deleted and json.loads(deleted['payload']).get('_status') == 'trashed':
        raise HTTPException(404, 'Item not found')
    return {**record, 'title': fields.get(PREFIX[record['kind']] + '[' + TITLE[record['kind']] + ']', record['title'])}


def active(c, account, row):
    try:
        kind, identifier = row['target'].split(':', 1)
        return target(c, account, kind, identifier)
    except HTTPException:
        return None


def deliver(c, now):
    # Membership and current project permissions are checked at delivery and
    # again when rendering; old reminders cannot bypass later revocation.
    for row in c.execute('SELECT * FROM bc_bubble_ups WHERE due<=? AND delivered IS NULL', (now,)).fetchall():
        member = c.execute('SELECT * FROM bc_members WHERE account=? AND workspace=?', (row['account'], row['workspace'])).fetchone()
        closed = c.execute('SELECT 1 FROM bc_settings WHERE owner=? AND name="cancelled_at"', (row['workspace'],)).fetchone()
        projects = None if member and (member['role'] == 'owner' or member['access'] == 'all') else [p['project'] for p in c.execute('SELECT project FROM bc_project_members WHERE account=? AND workspace=?', (row['account'], row['workspace']))]
        account = {'account_id': row['account'], 'workspace_id': row['workspace'], 'projects': projects}
        key = (row['account'], row['workspace'], row['target'])
        if not member or closed or not active(c, account, row):
            c.execute('DELETE FROM bc_bubble_ups WHERE account=? AND workspace=? AND target=?', key)
        else:
            c.execute('UPDATE bc_bubble_ups SET delivered=? WHERE account=? AND workspace=? AND target=? AND delivered IS NULL', (now, *key))


def pending(c, account, include_future=False):
    rows = c.execute('SELECT * FROM bc_bubble_ups WHERE account=? AND workspace=? AND read_at IS NULL ORDER BY due DESC',
                     (account['account_id'], account['workspace_id'])).fetchall()
    if not include_future:
        rows = [row for row in rows if row['due'] <= time.time()]
    return [(row, item) for row in rows if (item := active(c, account, row))]


def edit_markup(c, account, kind, identifier, path, csrf, full_view=False):
    frame = html.fromstring((ROOT / 'bubble-up-edit.html').read_text())
    frame.set('id', 'bubble_up_actions_' + kind + '_' + identifier)
    tz = zone(c, account)
    now = time.time()
    today = datetime.fromtimestamp(now, tz).date()
    existing = c.execute('SELECT due FROM bc_bubble_ups WHERE account=? AND workspace=? AND target=? AND read_at IS NULL',
                         (account['account_id'], account['workspace_id'], kind + ':' + identifier)).fetchone()
    for form in frame.xpath('.//form'):
        form.set('action', path)
        etree.SubElement(form, 'input', {'type': 'hidden', 'name': '_csrf', 'value': csrf})
        if full_view:
            etree.SubElement(form, 'input', {'type': 'hidden', 'name': 'return_to', 'value': OVERVIEW})
    for button in frame.xpath('.//button[@data-key]'):
        key = button.get('data-key')
        if key == 'now' and existing:
            pop = button
            if existing['due'] > now:
                form = copy.deepcopy(button.getparent())
                button.getparent().addprevious(form)
                pop = form.xpath('./button')[0]
            pop.set('data-key', 'pop')
            pop.xpath('./span')[0].text = 'Pop'
            pop.xpath('./small')[0].text = 'Remove from Bubble Up'
            etree.SubElement(pop.getparent(), 'input', {'type': 'hidden', 'name': '_method', 'value': 'delete'})
        if key != 'now':
            try:
                when = datetime.fromtimestamp(due_at(key, tz, now), tz)
            except HTTPException:
                button.getparent().getparent().remove(button.getparent())
                continue
            clock = when.strftime('%H:%M') if preferences(c, account).get('person[time_format]') == 'twenty_four_hour' else when.strftime('%-I:%M%p').lower()
            button.xpath('.//small')[0].text = when.strftime('%a, ') + clock
    for picker in frame.xpath('.//bc-date-picker'):
        picker.set('value', str(today + timedelta(days=1)))
        picker.set('data-min-date', str(today + timedelta(days=1)))
        picker.set('data-max-date', str(today + timedelta(days=365)))
    return html.tostring(frame, encoding='unicode')


def bubble_menu(kind, identifier, path, full_view=False):
    prototype = source_tree(INBOX).xpath('//article[@data-reading]')[0]
    menu = copy.deepcopy(prototype.xpath('.//span[@data-deferred-action-sheet]')[0])
    menu.set('data-local-bubble-menu', kind + ':' + identifier)
    # The overview form returns to the overview; the inbox form returns to
    # the inbox. Do not retain the previous view's form across navigation.
    menu.set('id', 'local_bubble_menu_' + kind + '_' + identifier + ('_all' if full_view else '_inbox'))
    menu.set('data-turbo-permanent', '')
    for node in menu.iter():
        for attribute, value in list(node.attrib.items()):
            node.set(attribute, value.replace('reading_5068406178', kind + '_' + identifier))
    for frame in menu.xpath('.//turbo-frame'):
        frame.set('src', path + '/edit' + ('?view=all' if full_view else ''))
    for icon in menu.xpath('.//*[contains(@class,"bubble-trigger__icon--unscheduled")]'):
        icon.getparent().remove(icon)
    for icon in menu.xpath('.//*[contains(@class,"bubble-trigger__icon--bubbled")]'):
        icon.set('class', 'svg-icon svg-icon--bubble text-blue')
    return menu


def render(tree, path, c, account):
    rows = pending(c, account)
    for badge in tree.xpath('//*[@id="sidebar_badge"]//*[contains(concat(" ",normalize-space(@class)," ")," unread-badge ")]'):
        if (badge.text or '').isdigit():
            badge.text = str(int(badge.text) + len(rows))
    for container in tree.xpath('//*[@data-bridge--bubble-up-url-value]'):
        match = re.search(r'/recordings/(\d+)/bubble_up', container.get('data-bridge--bubble-up-url-value', ''))
        if not match:
            continue
        row = c.execute('SELECT * FROM bc_bubble_ups WHERE account=? AND workspace=? AND target=? AND read_at IS NULL',
                        (account['account_id'], account['workspace_id'], 'recording:' + match[1])).fetchone()
        if row:
            container.set('data-bridge--bubble-up-bubbled-value', str(row['due'] <= time.time()).lower())
            container.set('data-bridge--bubble-up-scheduled-at-value', datetime.fromtimestamp(row['due'], zone(c, account)).isoformat())
    if path not in (INBOX, OVERVIEW):
        return
    full_view = path == OVERVIEW
    all_rows = pending(c, account, include_future=True)
    if full_view:
        for sidebar in tree.xpath('//*[@id="sidebar"]'):
            # The native controller closes a sidebar whose URL is also the
            # main document URL. A direct overview link is intentionally that
            # case; keep its panel open and replace this node on the next visit.
            tree.set('data-sidebar-open', '')
            tree.set('data-sidebar-subpage', '')
            sidebar.attrib.pop('data-turbo-permanent', None)
            sidebar.set('data-action', sidebar.get('data-action', '').replace('turbo:load@document->sidebar#closeOnConflictingVisit', ''))
            for pane in sidebar.xpath('.//*[@data-sidebar-target="pane"]'):
                pane.attrib.pop('inert', None)
    if full_view and not tree.xpath('//*[contains(@class,"readings--bubbled-ups")]'):
        frames = tree.xpath('//*[@id="sidebar_frame"]')
        if frames:
            content = source_tree(INBOX).xpath('//*[@id="sidebar_frame"]')[0]
            for child in list(frames[0]):
                frames[0].remove(child)
            frames[0].set('data-prefetched-frame-url-value', OVERVIEW)
            for child in content:
                frames[0].append(child)
    sections = tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," readings--bubbled-ups ")]')
    if not sections or not all_rows:
        return
    section = sections[0]
    if full_view:
        scrollable = section.getparent().getparent()
        for child in list(scrollable):
            if child is not section.getparent():
                scrollable.remove(child)
        for sibling in list(section.getparent()):
            if sibling is not section:
                section.getparent().remove(sibling)
        rows = sorted(all_rows, key=lambda entry: entry[0]['due'])
    else:
        rows = rows[:2]
    # A future-only section still needs its link to the scheduled-item panel.
    section.set('class', 'readings--bubbled-ups')
    section.attrib.pop('data-sidebar--readings-target', None)
    header = etree.SubElement(section, 'header', {'class': 'sidebar__list-header'})
    etree.SubElement(header, 'h3', {'id': 'sidebar_bubbled_up_heading', 'class': 'sidebar__list-heading'}).text = 'Bubble Up' if full_view else 'Recently Bubbled Up'
    more = len(all_rows) - len(rows)
    if full_view:
        etree.SubElement(header, 'a', {'href': INBOX, 'data-turbo-frame': 'sidebar_frame', 'class': 'decorated'}).text = 'New for you'
    elif more:
        etree.SubElement(header, 'a', {'href': OVERVIEW, 'data-turbo-frame': 'sidebar_frame', 'class': 'decorated', 'data-local-bubble-overview': 'true'}).text = 'View ' + str(more) + ' more'
    for row, item in rows:
        kind, identifier = row['target'].split(':', 1)
        article = etree.SubElement(section, 'article', {'class': 'reading list-grid', 'data-reading': 'true',
            'id': 'reading_bubble_' + kind + '_' + identifier,
            'data-local-bubble': row['target'], 'data-sidebar--readings-target': 'reading', 'data-section': 'inbox'})
        if kind == 'reading':
            # A resurfaced notification retains its actual avatar, excerpt and
            # original metadata instead of becoming a title-only placeholder.
            original = source_tree(INBOX).xpath('//*[@id="reading_' + identifier + '"]')[0]
            article.append(copy.deepcopy(original.xpath('./a')[0]))
        else:
            link = etree.SubElement(article, 'a', {'href': item['url'], 'class': 'reading__link list-grid',
                'data-roving-tabindex-target': 'focusable', 'data-sidebar--readings-target': 'control'})
            content = etree.SubElement(link, 'div', {'class': 'reading__content', 'data-quick-find-target': 'searchable'})
            etree.SubElement(content, 'h4', {'class': 'reading__description margin-block-0'}).text = item['title']
        if kind == 'ping':
            bubble_path = item['bubble_path']
        else:
            path = '/6302022/my/readings/' + identifier if kind == 'reading' else '/6302022/buckets/' + item['bucket'] + '/recordings/' + identifier
            bubble_path = path + '/bubble_up'
        extras = etree.SubElement(article, 'div', {'class': 'reading__extras'})
        extras.append(bubble_menu(kind, identifier, bubble_path, full_view))
        if full_view:
            stamp = datetime.fromtimestamp(row['due'], zone(c, account))
            etree.SubElement(article, 'time', {'class': 'reading__metadata text-subtle', 'datetime': stamp.isoformat(), 'data-local-bubble-due': 'true'}).text = stamp.strftime('%a, %b %d, %H:%M')
        # The native morph-version controller preserves unchanged reading rows,
        # including their lazy-loaded action sheet and keyboard focus. Include
        # the actual due instant even when the compact view hides its date.
        version = json.dumps([row['due'], row['due'] <= time.time()]).encode() + html.tostring(article)
        article.set('data-morph-version', hashlib.sha256(version).hexdigest())


def sidebar_streams(db, account, csrf, full_view=False):
    from local_render import render as render_local
    result = []
    for path, frame_id in ((OVERVIEW if full_view else INBOX, 'sidebar_frame'), ('/6302022/my/sidebar/badge', 'sidebar_badge')):
        markup = html.tostring(source_tree(INBOX if path == OVERVIEW else path), encoding='unicode')
        with db() as c:
            markup = render_local(markup, path, account['workspace_id'], c, account['display_name'], account=account)
        tree = html.fromstring(markup)
        for form in tree.xpath('//form'):
            etree.SubElement(form, 'input', {'type': 'hidden', 'name': '_csrf', 'value': csrf})
        frame = tree.xpath('//*[@id="' + frame_id + '"]')[0]
        content = ''.join(html.tostring(child, encoding='unicode') for child in frame)
        result.append('<turbo-stream action="update" target="' + frame_id + '"><template>' + content + '</template></turbo-stream>')
    return ''.join(result)


def install(app, db, require_user, csrf_check, csrf_token):
    router = APIRouter()

    def resolve(request, c, bucket, identifier):
        account = require_user(request)
        kind = 'recording' if bucket else 'reading'
        item = target(c, account, kind, identifier, bucket)
        return account, kind, item

    @router.get('/6302022/buckets/{bucket}/recordings/{identifier}/bubble_up/edit')
    @router.get('/6302022/my/readings/{identifier}/bubble_up/edit')
    def edit(identifier: str, request: Request, bucket: str = None):
        with db() as c:
            account, kind, item = resolve(request, c, bucket, identifier)
            return HTMLResponse(edit_markup(c, account, kind, identifier, request.url.path.removesuffix('/edit'), csrf_token(request), request.query_params.get('view') == 'all'))

    @router.api_route('/6302022/buckets/{bucket}/recordings/{identifier}/bubble_up', methods=['POST', 'PUT', 'PATCH', 'DELETE'])
    @router.api_route('/6302022/my/readings/{identifier}/bubble_up', methods=['POST', 'PUT', 'PATCH', 'DELETE'])
    async def save(identifier: str, request: Request, bucket: str = None):
        data = await request.json() if 'application/json' in request.headers.get('content-type', '') else await request.form()
        csrf_check(request, data)
        with db() as c:
            account, kind, item = resolve(request, c, bucket, identifier)
            key = (account['account_id'], account['workspace_id'], kind + ':' + identifier)
            method = str(data.get('_method', request.method)).upper()
            if method == 'DELETE':
                c.execute('DELETE FROM bc_bubble_ups WHERE account=? AND workspace=? AND target=?', key)
                due = None
            else:
                now = time.time()
                due = due_at(data.get('at'), zone(c, account), now)
                c.execute('INSERT OR REPLACE INTO bc_bubble_ups VALUES(?,?,?,?,?,?,?,NULL)', (*key, item['url'], item['title'], due, now if due <= now else None))
                if kind == 'reading':
                    c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,?,"true")', (account['account_id'], 'welcome-read-' + item['id']))
        if 'application/json' in request.headers.get('accept', ''):
            return {'saved': True, 'due': due, 'redirect': item['url']}
        if 'turbo-stream' in request.headers.get('accept', ''):
            with db() as c:
                full_view = data.get('return_to') == OVERVIEW and bool(pending(c, account, include_future=True))
            return Response(sidebar_streams(db, account, csrf_token(request), full_view), media_type='text/vnd.turbo-stream.html')
        return RedirectResponse(item['url'], 303)

    app.include_router(router)
