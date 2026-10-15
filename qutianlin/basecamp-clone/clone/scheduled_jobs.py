"""Durable weekly reports and cancelled-workspace retention, run by the app lifespan.

Schedules use UTC Mondays. SMTP retries are at least once: a process crash after
SMTP acceptance but before the SQLite commit can cause a duplicate delivery.
"""
import asyncio
import json
import logging
import smtplib
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

LOG = logging.getLogger(__name__)
RETENTION = 30 * 86400


def workspace_link(origin, workspace, path):
    return origin + '/workspaces/' + quote(workspace, safe='') + '/open?path=' + quote(path, safe='/')


def next_monday(now):
    date = datetime.fromtimestamp(now, timezone.utc)
    days = (7 - date.weekday()) % 7 or 7
    return int((date + timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def initialize(db):
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS bc_weekly_reports(
            account TEXT, workspace TEXT, next_run INTEGER NOT NULL,
            retry_at INTEGER NOT NULL DEFAULT 0, sent_at INTEGER,
            attempts INTEGER NOT NULL DEFAULT 0, error TEXT,
            PRIMARY KEY(account,workspace));
        CREATE TABLE IF NOT EXISTS bc_workspace_cleanup(
            workspace TEXT PRIMARY KEY, cleaned_at INTEGER NOT NULL);
        ''')


def set_subscription(c, account, enabled, now=None):
    c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,"assignments_subscribed",?)',
              (account, json.dumps(enabled)))
    if not enabled:
        c.execute('DELETE FROM bc_weekly_reports WHERE account=?', (account,))
    else:
        schedule(c, time.time() if now is None else now, account)


def schedule(c, now, only_account=None):
    members = c.execute('SELECT m.account,m.workspace FROM bc_members m JOIN local_auth_accounts a '
                        'ON a.account_id=m.account WHERE a.email_verified=1').fetchall()
    for member in members:
        account, workspace = member['account'], member['workspace']
        if only_account and account != only_account:
            continue
        preference = c.execute('SELECT value FROM bc_settings WHERE owner=? AND name="assignments_subscribed"', (account,)).fetchone()
        closed = c.execute('SELECT 1 FROM bc_settings WHERE owner=? AND name="cancelled_at"', (workspace,)).fetchone()
        if closed or preference and not json.loads(preference['value']):
            c.execute('DELETE FROM bc_weekly_reports WHERE account=? AND workspace=?', (account, workspace))
            continue
        c.execute('INSERT OR IGNORE INTO bc_weekly_reports(account,workspace,next_run) VALUES(?,?,?)',
                  (account, workspace, next_monday(now)))
    c.execute('DELETE FROM bc_weekly_reports WHERE NOT EXISTS '
              '(SELECT 1 FROM bc_members m WHERE m.account=bc_weekly_reports.account AND m.workspace=bc_weekly_reports.workspace)')


def task_lines(c, member, origin):
    from task_reports import open_tasks
    account, workspace = member['account'], member['workspace']
    projects = None if member['role'] == 'owner' or member['access'] == 'all' else {
        r['project'] for r in c.execute('SELECT project FROM bc_project_members WHERE workspace=? AND account=?', (workspace, account))}
    context = {'account_id': account, 'workspace_id': workspace, 'projects': projects}
    return ['- ' + task['title'] + (' — Due ' + task['due'] if task['due'] else '') + '\n  ' + workspace_link(origin, workspace, task['url'])
            for task in open_tasks(c, context)]


def deliver_reports(db, send_mail, origin, now):
    with db() as c:
        schedule(c, now)
        due = [dict(row) for row in c.execute('SELECT account,workspace FROM bc_weekly_reports WHERE next_run<=? AND retry_at<=?', (now, now))]
    for job in due:
        # Serialize a send with unsubscribe/cancel and other workers. SMTP has an
        # eight-second timeout; failures retain the same due occurrence for retry.
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            schedule(c, now, job['account'])
            row = c.execute('SELECT * FROM bc_weekly_reports WHERE account=? AND workspace=? AND next_run<=? AND retry_at<=?',
                            (job['account'], job['workspace'], now, now)).fetchone()
            if not row:
                continue
            member = c.execute('SELECT m.*,a.email_normalized,a.email_verified FROM bc_members m '
                               'JOIN local_auth_accounts a ON a.account_id=m.account WHERE m.account=? AND m.workspace=?',
                               (job['account'], job['workspace'])).fetchone()
            if not member or not member['email_verified']:
                c.execute('DELETE FROM bc_weekly_reports WHERE account=? AND workspace=?', (job['account'], job['workspace']))
                continue
            from notification_preferences import enabled
            if not enabled(c, job['account'], now, 'email'):
                continue
            lines = task_lines(c, member, origin)
            body = 'Your weekly Basecamp tasks\n\n' + ('\n\n'.join(lines) if lines else 'You have no outstanding assigned tasks.')
            body += '\n\nManage your task email subscription: ' + workspace_link(origin, job['workspace'], '/6302022/my/assignments') + '\n'
            try:
                send_mail(member['email_normalized'], 'Your weekly Basecamp tasks', body)
            except (OSError, smtplib.SMTPException):
                c.execute('UPDATE bc_weekly_reports SET attempts=attempts+1,retry_at=?,error=? WHERE account=? AND workspace=?',
                          (int(now) + 300, 'Local SMTP delivery failed', job['account'], job['workspace']))
            else:
                c.execute('UPDATE bc_weekly_reports SET next_run=?,sent_at=?,retry_at=0,attempts=0,error=NULL WHERE account=? AND workspace=?',
                          (next_monday(now), int(now), job['account'], job['workspace']))


def cleanup_workspaces(db, data_root, now):
    with db() as c:
        cancelled = c.execute('SELECT owner,value FROM bc_settings WHERE name="cancelled_at"').fetchall()
    for row in cancelled:
        if float(json.loads(row['value'])) + RETENTION > now:
            continue
        workspace = row['owner']
        with db() as c:
            c.execute('PRAGMA secure_delete=ON')
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT 1 FROM bc_workspace_cleanup WHERE workspace=?', (workspace,)).fetchone():
                continue
            for file in c.execute('SELECT id FROM bc_files WHERE owner=?', (workspace,)):
                identifier = file['id']
                if Path(identifier).name != identifier or identifier in ('.', '..'):
                    raise ValueError('Invalid stored upload identifier')
                c.execute('INSERT OR IGNORE INTO bc_file_cleanup(id) VALUES(?)', (identifier,))
            c.execute('DELETE FROM bc_event_reads WHERE event IN (SELECT id FROM bc_events WHERE workspace=?)', (workspace,))
            c.execute('DELETE FROM bc_event_recipients WHERE event IN (SELECT id FROM bc_events WHERE workspace=?)', (workspace,))
            for file in c.execute('SELECT f.id FROM bc_ping_files f JOIN bc_pings p ON p.id=f.ping WHERE p.workspace=?',(workspace,)):
                identifier=file['id']
                if Path(identifier).name!=identifier or identifier in ('.','..'):raise ValueError('Invalid stored private upload identifier')
                c.execute('INSERT OR IGNORE INTO bc_file_cleanup(id,storage) VALUES(?,"private-ping-files")', (identifier,))
            for cover in c.execute('SELECT f.file FROM bc_ping_covers f JOIN bc_pings p ON p.id=f.ping WHERE p.workspace=?',(workspace,)):
                c.execute('INSERT OR IGNORE INTO bc_file_cleanup(id,storage) VALUES(?,"private-ping-covers")',(cover['file'],))
            for table in ('bc_ping_files','bc_ping_covers','bc_ping_reactions','bc_ping_bookmarks','bc_ping_lines','bc_ping_members'):
                c.execute(f'DELETE FROM {table} WHERE ping IN (SELECT id FROM bc_pings WHERE workspace=?)',(workspace,))
            c.execute('DELETE FROM bc_pings WHERE workspace=?',(workspace,))
            for table in ('bc_records', 'bc_mutations', 'bc_comments', 'bc_files', 'bc_chat_lines', 'bc_tools', 'bc_exports', 'bc_payment_results'):
                c.execute(f'DELETE FROM {table} WHERE owner=?', (workspace,))
            for table in ('bc_events', 'bc_boosts', 'bc_boost_deliveries', 'bc_due_reminders', 'bc_invites', 'bc_project_members', 'bc_members', 'bc_weekly_reports', 'bc_bubble_ups', 'bc_thread_subscriptions', 'bc_column_views', 'bc_erased'):
                c.execute(f'DELETE FROM {table} WHERE workspace=?', (workspace,))
            for table in ('bc_wormholes', 'bc_card_relocations'):
                c.execute(f'DELETE FROM {table} WHERE workspace=?', (workspace,))
            c.execute('DELETE FROM bc_settings WHERE name LIKE ?', ('subscription:' + workspace + ':%',))
            for prefix in ('project-color:', 'project-star:'):
                c.execute('DELETE FROM bc_settings WHERE name LIKE ?', (prefix + workspace + ':%',))
            # Identity preferences and the cancellation tombstone survive; this
            # person may still use other workspaces. Sandbox payment audit events
            # are immutable and are not presented as project content.
            c.execute('DELETE FROM bc_settings WHERE owner=? AND name NOT IN '
                      '("cancelled_at","selected_workspace","assignments_subscribed","theme","grid","notifications")', (workspace,))
            c.execute('INSERT INTO bc_workspace_cleanup VALUES(?,?)', (workspace, int(now)))
    from trash import cleanup_files
    cleanup_files(db, data_root)


def tick(db, send_mail, origin, data_root, now=None):
    now = time.time() if now is None else now
    cleanup_workspaces(db, data_root, now)
    from trash import cleanup
    cleanup(db, data_root, now)
    from bubble_up import deliver
    with db() as c:
        deliver(c, now)
    deliver_reports(db, send_mail, origin, now)
    from boost_reports import deliver as deliver_boosts
    deliver_boosts(db, send_mail, origin, now)
    from due_reminders import deliver as deliver_reminders
    deliver_reminders(db, send_mail, origin, now)


def lifespan(db, send_mail, origin, data_root):
    @asynccontextmanager
    async def run(app):
        stop = asyncio.Event()

        async def worker():
            while not stop.is_set():
                try:
                    await asyncio.to_thread(tick, db, send_mail, origin, data_root)
                except Exception:
                    LOG.exception('Local scheduled maintenance failed; will retry')
                try:
                    await asyncio.wait_for(stop.wait(), timeout=60)
                except TimeoutError:
                    pass

        task = asyncio.create_task(worker())
        try:
            yield
        finally:
            stop.set()
            await task
    return run
