"""Received project Boosts and a durable, local-SMTP three-hour digest."""
import json
import smtplib
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException, Request
from lxml import html, etree

PERIOD = 3 * 3600
SUBSCRIPTION = '/6302022/my/boost_reports/subscription.js'


def initialize(db):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS bc_boost_deliveries(
            boost TEXT PRIMARY KEY, account TEXT, workspace TEXT, due REAL,
            sent_at REAL, retry_at REAL NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0, error TEXT)''')


@lru_cache(maxsize=512)
def source_author(route):
    path = Path(__file__).parent / 'frontend/pages' / route.lstrip('/') / 'index.html'
    if not path.is_file():
        return None
    tree = html.parse(path)
    values = tree.xpath('//*[@id="recording_' + route.rsplit('/', 1)[-1] + '"]/@data-creator-id')
    if not values:
        values = tree.xpath('//header[contains(@class,"perma-header")]//img/@data-avatar-for-person-id')
    return values[0] if values else None


def recipient(c, account, record, comment):
    if comment:
        person = comment['author']
    elif record.get('is_new'):
        from record_attribution import creator
        person = creator(c, account['workspace_id'], record)['id']
    else:
        person = source_author(record['url'])
    return account['workspace_id'] if person == '53382586' else person


def enabled(c, account):
    preference = c.execute('SELECT value FROM bc_settings WHERE owner=? AND name="boosts_subscribed"', (account,)).fetchone()
    return not preference or bool(json.loads(preference['value']))


def enqueue(c, account, record, comment, boost, now):
    from thread_notifications import accessible_member
    person = recipient(c, account, record, comment)
    if not person or person == account['account_id'] or not enabled(c, person):
        return
    if not accessible_member(c, account['workspace_id'], person, record['url']):
        return
    pending = c.execute('SELECT MIN(due) FROM bc_boost_deliveries WHERE account=? AND workspace=? AND sent_at IS NULL', (person, account['workspace_id'])).fetchone()[0]
    c.execute('INSERT INTO bc_boost_deliveries(boost,account,workspace,due) VALUES(?,?,?,?)',
              (boost, person, account['workspace_id'], pending if pending is not None else now + PERIOD))


def received(c, account):
    from boost_controls import resolve
    from record_operations import fields_for, PREFIX, TITLE
    result = []
    for row in c.execute('SELECT b.*,a.display_name FROM bc_boosts b LEFT JOIN local_auth_accounts a ON a.account_id=b.author WHERE workspace=? ORDER BY created DESC,id', (account['workspace_id'],)):
        try:
            record, comment = resolve(c, account, row['route'].split('/')[3], row['recording'])
        except HTTPException:
            continue
        from column_lifecycle import record_status
        if record_status(c, account['workspace_id'], record) != 'active':
            continue
        project = c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="project"',
                            (account['workspace_id'], '/6302022/projects/' + record['bucket'])).fetchone()
        if project and json.loads(project['payload']).get('_status') == 'trashed':
            continue
        if recipient(c, account, record, comment) != account['account_id']:
            continue
        fields = fields_for(c, account['workspace_id'], record)
        title = fields.get(PREFIX[record['kind']] + '[' + TITLE[record['kind']] + ']', record['title'])
        result.append((dict(row), record, comment, title))
    return result


def render(tree, path, c, account):
    if path != '/6302022/my/boosts':
        return
    active = enabled(c, account['account_id'])
    for button in tree.xpath('//button[@data-url="' + SUBSCRIPTION + '"]'):
        for child in list(button):
            button.remove(child)
        button.text = 'Notifying you of new boosts every 3 hours' if active else 'Notify me of new boosts every 3 hours'
        button.set('data-behavior', 'unsubscribe_from_report' if active else 'subscribe_to_report')
    rows = received(c, account)
    if not rows:
        return
    for empty in tree.xpath('//main//*[contains(concat(" ",normalize-space(@class)," ")," blank-slate ")]'):
        empty.getparent().remove(empty)
    targets = tree.xpath('//main//div[@data-readable-identifier]/section') or tree.xpath('//main')
    if not targets:
        return
    from boost_controls import posted
    groups = {}
    for row, record, comment, title in rows:
        key = (datetime.fromtimestamp(row['created'], timezone.utc).date().isoformat(), row['recording'])
        if key not in groups:
            section = etree.SubElement(targets[0], 'section', {'class': 'boosts-report__item margin-block-16', 'data-local-received-boosts': row['recording']})
            etree.SubElement(section, 'time', {'class': 'boosts-report__date', 'datetime': key[0]}).text = key[0]
            heading = etree.SubElement(section, 'h3')
            etree.SubElement(heading, 'a', {'href': comment['url'] if comment else record['url']}).text = title
            groups[key] = etree.SubElement(section, 'div', {'class': 'boosts'})
        groups[key].append(posted(row, account))


def deliver(db, send_mail, origin, now):
    from scheduled_jobs import workspace_link
    with db() as c:
        c.execute('DELETE FROM bc_boost_deliveries WHERE boost NOT IN (SELECT id FROM bc_boosts)')
        jobs = c.execute('SELECT DISTINCT account,workspace FROM bc_boost_deliveries WHERE sent_at IS NULL AND due<=? AND retry_at<=?', (now, now)).fetchall()
    for job in jobs:
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            member = c.execute('SELECT m.*,a.email_normalized,a.email_verified FROM bc_members m JOIN local_auth_accounts a ON a.account_id=m.account WHERE m.account=? AND m.workspace=?', (job['account'], job['workspace'])).fetchone()
            closed = c.execute('SELECT 1 FROM bc_settings WHERE owner=? AND name="cancelled_at"', (job['workspace'],)).fetchone()
            key = (job['account'], job['workspace'])
            if not member or closed or not member['email_verified'] or not enabled(c, job['account']):
                c.execute('DELETE FROM bc_boost_deliveries WHERE account=? AND workspace=? AND sent_at IS NULL', key)
                continue
            from notification_preferences import enabled as notifications_enabled
            if not notifications_enabled(c, job['account'], now, 'email'):
                continue
            account = {'account_id': job['account'], 'workspace_id': job['workspace']}
            valid = {row['id']: (row, record, comment, title) for row, record, comment, title in received(c, account)}
            pending = c.execute('SELECT * FROM bc_boost_deliveries WHERE account=? AND workspace=? AND sent_at IS NULL AND due<=? AND retry_at<=?', (*key, now, now)).fetchall()
            selected = []
            for row in pending:
                if row['boost'] in valid:
                    selected.append(valid[row['boost']])
                else:
                    c.execute('DELETE FROM bc_boost_deliveries WHERE boost=?', (row['boost'],))
            if not selected:
                continue
            body = 'Your new Basecamp Boosts\n\n' + '\n\n'.join(
                (row['display_name'] or 'Member') + ': ' + row['content'] + '\n' + title + '\n' + workspace_link(origin, job['workspace'], comment['url'] if comment else record['url'])
                for row, record, comment, title in selected)
            body += '\n\nManage Boost notifications: ' + workspace_link(origin, job['workspace'], '/6302022/my/boosts') + '\n'
            try:
                send_mail(member['email_normalized'], 'Your new Basecamp Boosts', body)
            except (OSError, smtplib.SMTPException):
                for row, *_ in selected:
                    c.execute('UPDATE bc_boost_deliveries SET attempts=attempts+1,retry_at=?,error=? WHERE boost=?', (now + 300, 'Local SMTP delivery failed', row['id']))
            else:
                for row, *_ in selected:
                    c.execute('UPDATE bc_boost_deliveries SET sent_at=?,retry_at=0,attempts=0,error=NULL WHERE boost=?', (now, row['id']))


def install(app, db, require_user, csrf_check):
    initialize(db)

    @app.api_route(SUBSCRIPTION, methods=['POST', 'PUT', 'PATCH', 'DELETE'])
    async def subscribe(request: Request):
        account = require_user(request)
        csrf_check(request, {})
        active = request.method != 'DELETE'
        with db() as c:
            c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,"boosts_subscribed",?)', (account['account_id'], json.dumps(active)))
            if not active:
                c.execute('DELETE FROM bc_boost_deliveries WHERE account=? AND sent_at IS NULL', (account['account_id'],))
        return {'subscribed': active}
