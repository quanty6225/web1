"""Personal due-assignment and event reminders over current, accessible records.

Date-only tasks are evaluated at 09:00 in the recipient's time zone. Event
windows are one calendar day and one hour before each occurrence. These local
clock choices and plain-text SMTP templates are documented implementation choices.
"""
import json
import smtplib
from datetime import datetime, timedelta, time as clock, timezone

SYSTEM = 'system:reminder'


def initialize(db):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS bc_due_reminders(
            account TEXT, workspace TEXT, route TEXT, occurrence TEXT,
            event INTEGER, sent_at REAL, retry_at REAL DEFAULT 0,
            attempts INTEGER DEFAULT 0, error TEXT,
            PRIMARY KEY(account,workspace,route,occurrence))''')


def context(c, member):
    projects = None if member['role'] == 'owner' or member['access'] == 'all' else {
        row['project'] for row in c.execute('SELECT project FROM bc_project_members WHERE workspace=? AND account=?', (member['workspace'], member['account']))}
    return {'account_id': member['account'], 'workspace_id': member['workspace'], 'projects': projects}


def occurrences(c, account, now):
    from bubble_up import zone
    from notification_preferences import preferences
    from task_reports import open_tasks
    from calendar_view import records, starts_on, timestamp
    from column_lifecycle import record_status
    from workspaces import allows
    from record_operations import metadata
    settings = preferences(c, account['account_id'])
    tz = zone(c, account)
    local = datetime.fromtimestamp(now, tz)
    today = local.date()
    result = {}
    if 'due_assignments' in settings['reminders[]'] and local.hour >= 9:
        for task in open_tasks(c, account):
            if not task['due']:
                continue
            due = datetime.fromisoformat(task['due']).date()
            if due > today + timedelta(days=1):
                continue
            label = 'Due tomorrow' if due > today else 'Due today' if due == today else 'Overdue'
            occurrence = 'assignment:' + task['due'] + ':' + today.isoformat()
            result[(task['url'], occurrence)] = {'title': task['title'], 'label': label, 'date': task['due']}
    if 'schedule_entries' not in settings['reminders[]']:
        return result
    for record, fields in records(c, account['workspace_id']):
        if not allows(account, record['url']) or not metadata(c, account['workspace_id'], record['id']):
            continue
        if record_status(c, account['workspace_id'], record, fields) != 'active':
            continue
        project = c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="project"',
                            (account['workspace_id'], '/6302022/projects/' + record['bucket'])).fetchone()
        if project and json.loads(project['payload']).get('_status') == 'trashed':
            continue
        participants = fields.get('participants', '')
        participants = participants if isinstance(participants, list) else str(participants).split(',')
        participants = {account['workspace_id'] if value == '53382586' else value for value in participants}
        if account['account_id'] not in participants or not fields.get('schedule_entry[starts_at]'):
            continue
        original = timestamp(fields['schedule_entry[starts_at]'])
        all_day = str(fields.get('schedule_entry[all_day]', '')).lower() in ('1', 'true')
        # The stored recurrence calendar is based on the UTC date of its start.
        # Consider adjacent dates so recipient zones cannot skip an occurrence.
        utc_today = datetime.fromtimestamp(now, timezone.utc).date()
        for offset in range(-1, 3):
            day = utc_today + timedelta(days=offset)
            if not starts_on(fields, day):
                continue
            start = datetime.combine(day, clock(), tz) if all_day else datetime.combine(day, original.timetz()).astimezone(tz)
            start_at = start.timestamp()
            if now >= start_at:
                continue
            one_hour = start_at - 3600
            day_before = (start - timedelta(days=1)).timestamp()
            for kind, begin, end, label in [('day', day_before, one_hour, 'Event tomorrow'), ('hour', one_hour, start_at, 'Event in one hour')]:
                if begin <= now < end:
                    occurrence = 'event:' + start.isoformat() + ':' + kind
                    result[(record['url'], occurrence)] = {'title': fields.get('schedule_entry[summary]', record['title']), 'label': label, 'date': start.isoformat()}
    return result


def deliver(db, send_mail, origin, now):
    from notification_preferences import enabled
    from scheduled_jobs import workspace_link
    with db() as c:
        members = [dict(row) for row in c.execute('SELECT m.*,a.email_normalized,a.email_verified FROM bc_members m JOIN local_auth_accounts a ON a.account_id=m.account WHERE a.email_verified=1')]
    for member in members:
        with db() as c:
            # Serialize the eligibility check, durable occurrence and SMTP send
            # with edits, opt-outs, membership changes and another worker.
            c.execute('BEGIN IMMEDIATE')
            current = c.execute('SELECT m.*,a.email_normalized,a.email_verified FROM bc_members m JOIN local_auth_accounts a ON a.account_id=m.account WHERE m.account=? AND m.workspace=?', (member['account'], member['workspace'])).fetchone()
            if not current or not current['email_verified'] or c.execute('SELECT 1 FROM bc_settings WHERE owner=? AND name="cancelled_at"', (member['workspace'],)).fetchone():
                continue
            account = context(c, current)
            for (route, occurrence), item in occurrences(c, account, now).items():
                key = (member['account'], member['workspace'], route, occurrence)
                row = c.execute('SELECT * FROM bc_due_reminders WHERE account=? AND workspace=? AND route=? AND occurrence=?', key).fetchone()
                if not row:
                    event = c.execute('INSERT INTO bc_events(workspace,author,route,title,action,created) VALUES(?,?,?,?,?,?)',
                                      (member['workspace'], SYSTEM, route, item['title'], item['label'], now)).lastrowid
                    c.execute('INSERT INTO bc_event_recipients VALUES(?,?)', (event, member['account']))
                    c.execute('INSERT INTO bc_due_reminders(account,workspace,route,occurrence,event) VALUES(?,?,?,?,?)', (*key, event))
                    row = c.execute('SELECT * FROM bc_due_reminders WHERE account=? AND workspace=? AND route=? AND occurrence=?', key).fetchone()
                if row['sent_at'] is not None or row['retry_at'] > now or not enabled(c, member['account'], now, 'email'):
                    continue
                body = item['label'] + ': ' + item['title'] + '\n' + item['date'] + '\n\n' + workspace_link(origin, member['workspace'], route)
                body += '\n\nNotification settings: ' + workspace_link(origin, member['workspace'], '/6302022/my/notifications/settings') + '\n'
                try:
                    send_mail(current['email_normalized'], 'Basecamp reminder: ' + item['title'], body)
                except (OSError, smtplib.SMTPException):
                    c.execute('UPDATE bc_due_reminders SET attempts=attempts+1,retry_at=?,error=? WHERE account=? AND workspace=? AND route=? AND occurrence=?', (now + 300, 'Local SMTP delivery failed', *key))
                else:
                    c.execute('UPDATE bc_due_reminders SET sent_at=?,retry_at=0,error=NULL WHERE account=? AND workspace=? AND route=? AND occurrence=?', (now, *key))
