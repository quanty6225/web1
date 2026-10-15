"""Captured Work Can Wait preferences and local delivery eligibility."""
import json
import time
from datetime import datetime, timedelta

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from lxml import html
from pathlib import Path

PATH = '/6302022/my/notifications/settings'
DEFAULTS = {'granularity': 'everything', 'reminders[]': ['schedule_entries', 'due_assignments'],
            'platforms[]': ['email', 'web'], 'show_badge_counts': False,
            'schedule_enabled': False, 'schedule[start_hour]': 9, 'schedule[end_hour]': 17,
            'schedule[work_days][]': ['1', '2', '3', '4', '5'], 'bundle_enabled': True}


def preferences(c, account):
    row = c.execute('SELECT value FROM bc_settings WHERE owner=? AND name="notification_preferences"', (account,)).fetchone()
    return {**DEFAULTS, **(json.loads(row['value']) if row else {})}


def work_time(c, account, now):
    from bubble_up import zone
    settings = preferences(c, account)
    if not settings['schedule_enabled']:
        return True
    local = datetime.fromtimestamp(now, zone(c, {'account_id': account}))
    start, end = settings['schedule[start_hour]'], settings['schedule[end_hour]']
    # A shift belongs to the day it starts, including an overnight shift.
    today = str(local.isoweekday() % 7) in settings['schedule[work_days][]']
    if end > start:
        return today and start <= local.hour < end
    previous = str((local - timedelta(days=1)).isoweekday() % 7) in settings['schedule[work_days][]']
    return today and local.hour >= start or previous and local.hour < end


def enabled(c, account, now=None, platform=None):
    now = time.time() if now is None else now
    snooze = c.execute('SELECT value FROM bc_settings WHERE owner=? AND name="notifications_snoozed_until"', (account,)).fetchone()
    if snooze and float(json.loads(snooze['value'])) > now:
        return False
    toggle = c.execute('SELECT value FROM bc_settings WHERE owner=? AND name="notifications"', (account,)).fetchone()
    if toggle and not json.loads(toggle['value']):
        return False
    settings = preferences(c, account)
    if platform and platform not in settings['platforms[]']:
        return False
    return work_time(c, account, now)


def state(c, account):
    snooze = c.execute('SELECT value FROM bc_settings WHERE owner=? AND name="notifications_snoozed_until"', (account,)).fetchone()
    if snooze and float(json.loads(snooze['value'])) > time.time():
        return 'snoozed'
    return 'on' if enabled(c, account) else 'off'


def render(tree, path, c, account):
    if path not in (PATH, PATH + '/edit'):
        return
    settings = preferences(c, account['account_id'])
    for field in tree.xpath('//form[@action="' + PATH + '"]//input[@name]|//form[@action="' + PATH + '"]//select[@name]'):
        name = field.get('name')
        if name not in settings:
            continue
        value = settings[name]
        if field.tag == 'select':
            selected = {str(v) for v in value} if isinstance(value, list) else {str(value)}
            for option in field.xpath('./option'):
                option.attrib.pop('selected', None)
                if option.get('value') in selected:
                    option.set('selected', 'selected')
        elif field.get('type') in ('checkbox', 'radio'):
            field.attrib.pop('checked', None)
            checked = field.get('value') in value if isinstance(value, list) else bool(value) if field.get('type') == 'checkbox' else field.get('value') == (str(value).lower() if isinstance(value, bool) else str(value))
            if checked:
                field.set('checked', 'checked')
    for container in tree.xpath('//*[@id="schedule_enabled_true"]/ancestor::*[contains(@data-behavior,"expandable")][1]'):
        classes = set(container.get('class', '').split())
        classes.discard('expanded')
        if settings['schedule_enabled']:
            classes.add('expanded')
        container.set('class', ' '.join(sorted(classes)))
    # Native settings controllers retain their existing enable/disable and day
    # picker behavior. The summary must reflect the durable settings as well.
    for node in tree.xpath('//*[@data-role="my_notifications"]//span'):
        if len(node):
            continue
        if (node.text or '').strip() == 'Notifications are on':
            node.text = 'Notifications are on' if enabled(c, account['account_id']) else 'Notifications are off'
    for node in tree.xpath('//*[@data-role="my_notifications"]/div'):
        if 'You’re set to receive' not in (node.text or ''):
            continue
        channels = ' and '.join('browser' if v == 'web' else v for v in settings['platforms[]'])
        about = 'everything' if settings['granularity'] == 'everything' else 'Pings and @mentions'
        when = 'during your work hours' if settings['schedule_enabled'] else 'all the time'
        node.text = 'You’re set to receive ' + (channels + ' notifications for ' + about + ' ' + when + '.' if channels else 'no email or browser notifications.')
    for link in tree.xpath('//*[@data-role="my_notifications"]//*[@data-behavior="toggle_notifications"]'):
        active = state(c, account['account_id']) == 'on'
        link.set('data-verb', 'PUT' if active else 'DELETE')
        link.text = 'Turn notifications off' if active else 'Turn notifications on'


def install(app, db, require_user, csrf_check):
    @app.api_route('/6302022/my/notifications/toggle', methods=['PUT', 'DELETE'])
    @app.put('/6302022/my/notifications/snooze')
    async def toggle(request: Request):
        account = require_user(request)
        csrf_check(request, {})
        with db() as c:
            if request.url.path.endswith('/snooze'):
                try:
                    duration = int(request.query_params.get('duration', 3600))
                except ValueError:
                    raise HTTPException(422, 'Choose a valid pause duration.')
                if not 1 <= duration <= 86400:
                    raise HTTPException(422, 'Pause notifications for up to one day.')
                c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,"notifications_snoozed_until",?)', (account['account_id'], json.dumps(time.time() + duration)))
            else:
                c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,"notifications",?)', (account['account_id'], json.dumps(request.method == 'DELETE')))
                c.execute('DELETE FROM bc_settings WHERE owner=? AND name="notifications_snoozed_until"', (account['account_id'],))
            tree = html.parse(str(Path(__file__).parent / 'frontend/pages/6302022/my/notifications/settings/index.html')).getroot()
            render(tree, PATH, c, account)
            return HTMLResponse(html.tostring(tree.xpath('//*[@data-role="my_notifications"]')[0], encoding='unicode'))

    @app.api_route(PATH, methods=['POST', 'PUT', 'PATCH'])
    async def save(request: Request):
        account = require_user(request)
        data = await request.json() if 'application/json' in request.headers.get('content-type', '') else await request.form()
        csrf_check(request, data)
        def many(name):
            value = data.getlist(name) if hasattr(data, 'getlist') else data.get(name, [])
            return list(dict.fromkeys(str(v) for v in (value if isinstance(value, list) else [value]) if str(v)))
        def flag(name):
            value = data.get(name, False)
            if value not in (True, False, 'true', 'false', '1', '0', 'on', ''):
                raise HTTPException(422, 'Choose a valid notification preference.')
            return value in (True, 'true', '1', 'on')
        settings = {'granularity': str(data.get('granularity', 'everything')),
                    'reminders[]': many('reminders[]'), 'platforms[]': many('platforms[]'),
                    'schedule[work_days][]': many('schedule[work_days][]')}
        if settings['granularity'] not in ('everything', 'pings_and_mentions'):
            raise HTTPException(422, 'Choose what to be notified about.')
        for key, valid in [('reminders[]', {'schedule_entries', 'due_assignments'}), ('platforms[]', {'email', 'web'}), ('schedule[work_days][]', set('0123456'))]:
            if not set(settings[key]) <= valid:
                raise HTTPException(422, 'Choose a valid notification preference.')
        for name in ('show_badge_counts', 'schedule_enabled', 'bundle_enabled'):
            settings[name] = flag(name)
        try:
            settings['schedule[start_hour]'] = int(data.get('schedule[start_hour]', 9))
            settings['schedule[end_hour]'] = int(data.get('schedule[end_hour]', 17))
        except (TypeError, ValueError):
            raise HTTPException(422, 'Choose valid working hours.')
        if not 0 <= settings['schedule[start_hour]'] <= 23 or not 1 <= settings['schedule[end_hour]'] <= 24:
            raise HTTPException(422, 'Choose valid working hours.')
        if settings['schedule_enabled'] and not settings['schedule[work_days][]']:
            raise HTTPException(422, 'Choose at least one working day.')
        with db() as c:
            c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,"notification_preferences",?)', (account['account_id'], json.dumps(settings)))
        if 'application/json' in request.headers.get('accept', ''):
            return {'saved': True, 'redirect': PATH}
        return RedirectResponse(PATH, 303)
