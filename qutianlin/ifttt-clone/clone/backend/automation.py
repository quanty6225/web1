"""Account-owned offline automations, using the site-bound SQLite lifecycle.

Third-party adapters write local effect records. They never call production
services. Event identity, quota checks and state changes share one transaction.
"""
import json
import hashlib
import re
import secrets
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, reset_tzpath, TZPATH
from .filter_code import evaluate as evaluate_filter, validate as validate_filter

ZONE_DATA = Path(__file__).resolve().parents[1] / 'vendor/tzdata/zoneinfo'
if ZONE_DATA.is_dir(): reset_tzpath([str(ZONE_DATA), *TZPATH])


BUILTINS = ('date_and_time', 'email', 'email_digest', 'ifttt', 'feed', 'space', 'weather')
LIMITS = {'free': 2, 'pro': 20, 'pro_plus': None}
PRICES = {('pro', 'monthly'): 499, ('pro', 'yearly'): 3588,
          ('pro_plus', 'monthly'): 1499, ('pro_plus', 'yearly'): 10788}


def migrate_v1(conn):
    statements = [
        """CREATE TABLE ifttt_profiles(owner TEXT PRIMARY KEY, settings TEXT NOT NULL DEFAULT '{}',
            plan TEXT NOT NULL DEFAULT 'free', created_at INTEGER NOT NULL)""",
        """CREATE TABLE ifttt_connections(owner TEXT NOT NULL, service TEXT NOT NULL,
            account TEXT NOT NULL DEFAULT 'default', label TEXT NOT NULL, settings TEXT NOT NULL DEFAULT '{}',
            connected INTEGER NOT NULL CHECK(connected IN (0,1)), updated_at INTEGER NOT NULL,
            PRIMARY KEY(owner,service,account))""",
        """CREATE TABLE ifttt_applets(id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL,
            definition TEXT NOT NULL, enabled INTEGER NOT NULL CHECK(enabled IN(0,1)),
            archived INTEGER NOT NULL CHECK(archived IN(0,1)), origin TEXT NOT NULL DEFAULT 'diy',
            revision INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)""",
        "CREATE INDEX ifttt_applets_owner ON ifttt_applets(owner,archived,created_at)",
        """CREATE TABLE ifttt_events(id TEXT PRIMARY KEY, owner TEXT NOT NULL, module TEXT NOT NULL,
            ingredients TEXT NOT NULL, event_key TEXT NOT NULL, created_at INTEGER NOT NULL,
            UNIQUE(owner,event_key))""",
        """CREATE TABLE ifttt_runs(id TEXT PRIMARY KEY, owner TEXT NOT NULL, applet_id TEXT NOT NULL,
            event_id TEXT NOT NULL, status TEXT NOT NULL, definition TEXT NOT NULL,
            due_at INTEGER NOT NULL, steps TEXT NOT NULL, created_at INTEGER NOT NULL,
            finished_at INTEGER, UNIQUE(applet_id,event_id))""",
        "CREATE INDEX ifttt_runs_due ON ifttt_runs(status,due_at)",
        """CREATE TABLE ifttt_effects(id TEXT PRIMARY KEY, owner TEXT NOT NULL, run_id TEXT NOT NULL,
            step_index INTEGER NOT NULL, service TEXT NOT NULL, module TEXT NOT NULL,
            payload TEXT NOT NULL, created_at INTEGER NOT NULL, UNIQUE(run_id,step_index))""",
        """CREATE TABLE ifttt_operations(owner TEXT NOT NULL, operation_key TEXT NOT NULL,
            request TEXT NOT NULL, response TEXT NOT NULL, PRIMARY KEY(owner,operation_key))""",
        """CREATE TABLE ifttt_preferences(owner TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
            PRIMARY KEY(owner,key))""",
    ]
    for statement in statements:
        conn.execute(statement)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def identifier(prefix):
    return prefix + secrets.token_hex(12)


class Automation:
    def __init__(self, backend, catalog, published=None, timezones=None):
        self.backend = backend
        self.modules = {m['route']: m for m in catalog['modules']}
        self.services = set(BUILTINS) | {m['service'] for m in self.modules.values()}
        self.published = published or {}
        self.timezones = timezones or {}

    @staticmethod
    def _clock(value):
        value = str(value).strip().upper()
        for pattern in ('%H:%M', '%I:%M %p', '%I %p'):
            try: return datetime.strptime(value, pattern).time()
            except ValueError: pass
        raise ValueError('Enter a time such as 07:00 or 7:00 AM')

    def _schedule_matches(self, trigger, moment):
        slug = trigger['module'].rsplit('/', 1)[-1]
        fields = trigger['fields']
        if slug == 'every_hour_at':
            try: minute = int(str(fields.get('time', '')).lstrip(':'))
            except ValueError: raise ValueError('Choose 00, 15, 30 or 45 minutes past the hour')
            if minute not in {0, 15, 30, 45}: raise ValueError('Choose 00, 15, 30 or 45 minutes past the hour')
            return moment.minute == minute
        if slug == 'every_year_on':
            try: chosen = datetime.fromisoformat(str(fields.get('datetime', '')))
            except ValueError: raise ValueError('Enter a date and time such as 2026-01-01T07:00')
            return (moment.month, moment.day, moment.hour, moment.minute) == (chosen.month, chosen.day, chosen.hour, chosen.minute)
        chosen = self._clock(fields.get('time'))
        matching_time = (moment.hour, moment.minute) == (chosen.hour, chosen.minute)
        if slug == 'every_weekday_at':
            days = fields.get('weekdays', [])
            if isinstance(days, str): days = [s.strip() for s in days.split(',')]
            aliases = {name.lower(): i for i, name in enumerate(('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'))}
            aliases.update({name[:3]: number for name, number in list(aliases.items())})
            selected = {aliases.get(str(day).lower()) for day in days}
            if not selected or None in selected: raise ValueError('Enter weekday names separated by commas')
            return matching_time and moment.weekday() in selected
        if slug == 'every_month_on_the':
            try: day = int(fields.get('month_day', ''))
            except ValueError: raise ValueError('Enter a day of the month from 1 to 31')
            if not 1 <= day <= 31: raise ValueError('Enter a day of the month from 1 to 31')
            return matching_time and moment.day == day
        return matching_time

    def ensure_owner(self, conn, owner):
        if not isinstance(owner, str) or not owner:
            raise PermissionError('Sign in to continue')
        created = conn.execute('INSERT OR IGNORE INTO ifttt_profiles(owner,created_at) VALUES (?,?)',
                               (owner, int(time.time()))).rowcount
        if created:
            for service in BUILTINS:
                conn.execute('INSERT INTO ifttt_connections(owner,service,label,connected,updated_at) VALUES (?,?,?,1,?)',
                             (owner, service, 'Local ' + service.replace('_', ' ').title(), int(time.time())))

    def _plan(self, conn, owner):
        return conn.execute('SELECT plan FROM ifttt_profiles WHERE owner=?', (owner,)).fetchone()['plan']

    def _quota(self, conn, owner):
        limit = LIMITS[self._plan(conn, owner)]
        count = conn.execute('SELECT count(*) FROM ifttt_applets WHERE owner=? AND archived=0', (owner,)).fetchone()[0]
        if limit is not None and count >= limit:
            raise ValueError(f'Your plan allows {limit} Applets. Archive an Applet or upgrade to continue.')

    def _applet(self, conn, owner, applet_id):
        row = conn.execute('SELECT * FROM ifttt_applets WHERE id=? AND owner=?', (applet_id, owner)).fetchone()
        if row is None:
            raise LookupError('Applet not found')
        return dict(row)

    def _step(self, step, kind):
        if not isinstance(step, dict): raise ValueError('Choose a ' + kind.rstrip('s'))
        module = self.modules.get(step.get('module'))
        if module is None or module['kind'] != kind: raise ValueError('Unknown ' + kind.rstrip('s'))
        fields = step.get('fields', {})
        if not isinstance(fields, dict): raise ValueError('Invalid fields')
        allowed = {f['Slug'] for f in module['fields']}
        if set(fields) - allowed: raise ValueError('Unknown module field')
        for field in module['fields']:
            value = fields.get(field['Slug'], '')
            if field.get('Required') == 'true' and not str(value).strip():
                raise ValueError(field.get('Label', field['Slug']) + ' is required')
            if not isinstance(value, (str, list)) or len(str(value)) > 8000:
                raise ValueError('Invalid field value')
            if isinstance(value, list) and not all(isinstance(v, str) for v in value):
                raise ValueError('Invalid field selection')
        account = step.get('account', 'default')
        if not isinstance(account, str) or len(account) > 120: raise ValueError('Invalid service account')
        return {'module': module['route'], 'fields': fields, 'account': account}

    def _definition(self, conn, owner, value):
        if not isinstance(value, dict): raise ValueError('Invalid Applet')
        trigger = self._step(value.get('trigger'), 'triggers')
        if self.modules[trigger['module']]['service'] == 'date_and_time':
            self._schedule_matches(trigger, datetime.now(timezone.utc))
        actions = value.get('actions', [])
        queries = value.get('queries', [])
        filter_code = value.get('filter_code', '')
        if not isinstance(filter_code, str) or len(filter_code) > 10000: raise ValueError('Filter code must contain at most 10,000 characters')
        if not isinstance(actions, list) or not 1 <= len(actions) <= 20: raise ValueError('Add an action')
        if not isinstance(queries, list) or len(queries) > 20: raise ValueError('Invalid queries')
        plan = self._plan(conn, owner)
        if len(actions) > 1 and plan == 'free': raise ValueError('Multiple actions require Pro')
        if queries and plan != 'pro_plus': raise ValueError('Queries require Pro+')
        if filter_code.strip() and plan != 'pro_plus': raise ValueError('Filter code requires Pro+')
        if filter_code.strip(): validate_filter(filter_code)
        delay = value.get('delay_seconds', 0)
        if type(delay) is not int or delay != 0 and not 15 <= delay <= 10800:
            raise ValueError('Delay must be between 15 seconds and 3 hours')
        if delay and plan != 'pro_plus': raise ValueError('Delay requires Pro+')
        description = value.get('description', '')
        if not isinstance(description, str) or len(description) > 500: raise ValueError('Description must contain at most 500 characters')
        card_service = value.get('card_service', '')
        if not isinstance(card_service, str): raise ValueError('Choose an Applet service')
        services = {self.modules[s.get('module', '')]['service'] for s in [trigger, *actions, *queries] if isinstance(s, dict) and s.get('module') in self.modules}
        if card_service and card_service not in services: raise ValueError('Choose a service used by this Applet')
        result = {'trigger': trigger, 'actions': [self._step(s, 'actions') for s in actions],
                  'queries': [self._step(s, 'queries') for s in queries], 'delay_seconds': delay, 'filter_code': filter_code,
                  'description': description, 'card_service': card_service}
        if any(s['account'] != 'default' for s in [trigger, *result['actions'], *result['queries']]) and plan != 'pro_plus':
            raise ValueError('Multiple service accounts require Pro+')
        return result

    def _connections(self, conn, owner, definition):
        for step in [definition['trigger'], *definition['actions'], *definition.get('queries', [])]:
            service = self.modules[step['module']]['service']
            row = conn.execute('SELECT connected FROM ifttt_connections WHERE owner=? AND service=? AND account=?',
                               (owner, service, step['account'])).fetchone()
            if not row or not row['connected']:
                raise ValueError('Connect ' + service.replace('_', ' ') + ' to continue')

    def snapshot(self, owner):
        with self.backend.lifecycle.connection(transaction=True) as conn:
            self.ensure_owner(conn, owner)
            profile = dict(conn.execute('SELECT * FROM ifttt_profiles WHERE owner=?', (owner,)).fetchone())
            result = {'plan': profile['plan'], 'limit': LIMITS[profile['plan']], 'settings': json.loads(profile['settings'])}
            billing = conn.execute("SELECT value FROM ifttt_preferences WHERE owner=? AND key='billing'", (owner,)).fetchone()
            result['billing'] = json.loads(billing['value']) if billing else None
            for name in ('connections', 'applets', 'runs', 'effects'):
                order = 'updated_at' if name == 'connections' else 'created_at'
                rows = conn.execute(f'SELECT * FROM ifttt_{name} WHERE owner=? ORDER BY {order} DESC', (owner,)).fetchall()
                result[name] = [dict(row) for row in rows]
                for item in result[name]:
                    item.pop('owner', None)
                    for key in ('definition', 'settings', 'steps', 'payload'):
                        if key in item: item[key] = json.loads(item[key])
            definitions = {run['id']:run['definition'] for run in result['runs']}
            for effect in result['effects']:
                effect['account'] = definitions[effect['run_id']]['actions'][effect['step_index']].get('account','default')
            return result

    def mutate(self, owner, action, body):
        with self.backend.lifecycle.connection(transaction=True) as conn:
            self.ensure_owner(conn, owner)
            key = body.get('operation_key')
            if not isinstance(key, str) or not 8 <= len(key) <= 150:
                raise ValueError('A unique operation key is required')
            request = encoded({'action': action, 'body': body})
            previous = conn.execute('SELECT request,response FROM ifttt_operations WHERE owner=? AND operation_key=?', (owner, key)).fetchone()
            if previous:
                if previous['request'] != request: raise ValueError('Operation key was already used for a different request')
                return json.loads(previous['response'])
            result = self._mutate(conn, owner, action, body)
            conn.execute('INSERT INTO ifttt_operations VALUES (?,?,?,?)', (owner, key, request, encoded(result)))
            return result

    def _mutate(self, conn, owner, action, body):
        now = int(time.time())
        if action == 'checkout':
            plan, interval = body.get('plan'), body.get('interval')
            if (plan, interval) not in PRICES: raise ValueError('Choose a valid plan and billing interval')
            amount = PRICES[plan, interval]
            facts = {'site_id': 'ifttt', 'owner': owner, 'plan': plan, 'interval': interval,
                     'amount_minor': amount, 'currency': 'USD', 'trial_days': 7}
            fingerprint = hashlib.sha256(encoded(facts).encode()).hexdigest()
            flow = self.backend.payments.create_intent(owner=owner, amount_minor=amount, currency='USD',
                fingerprint=fingerprint, idempotency_key=body['operation_key'], connection=conn)
            attempt = self.backend.payments.attempt(flow_id=flow['flow_id'], owner=owner, amount_minor=amount,
                currency='USD', fingerprint=fingerprint, scenario_id=body.get('scenario'),
                idempotency_key=body['operation_key'], connection=conn)
            if attempt['status'] != 'APPROVED':
                return {'status': attempt['status'].lower(), 'message': 'The local payment was ' + attempt['status'].lower() + '. No plan change was made.'}
            approval = self.backend.payments.consume_approval(conn, flow_id=flow['flow_id'], owner=owner,
                amount_minor=amount, currency='USD', fingerprint=fingerprint)
            billing = facts | {'status': 'trialing', 'trial_ends_at': now + 7 * 86400,
                               'started_at': now, 'flow_id': approval['flow_id'], 'simulation': True}
            conn.execute('UPDATE ifttt_profiles SET plan=? WHERE owner=?', (plan, owner))
            conn.execute("INSERT INTO ifttt_preferences VALUES (?,'billing',?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value", (owner, encoded(billing)))
            return {'status': 'approved', 'redirect': '/billing', 'billing': billing}
        if action == 'cancel-subscription':
            row = conn.execute("SELECT value FROM ifttt_preferences WHERE owner=? AND key='billing'", (owner,)).fetchone()
            if not row: raise ValueError('There is no subscription to cancel')
            billing = json.loads(row['value'])
            billing.update(status='cancelled', cancelled_at=now)
            # Local cancellation is immediate; keep the newest two Applets and
            # archive excess ones rather than leaving a free account over quota.
            rows = conn.execute('SELECT id FROM ifttt_applets WHERE owner=? AND archived=0 ORDER BY created_at DESC,id', (owner,)).fetchall()
            for row in rows[2:]: self._archive(conn, owner, row['id'], now)
            conn.execute("UPDATE ifttt_profiles SET plan='free' WHERE owner=?", (owner,))
            conn.execute("UPDATE ifttt_preferences SET value=? WHERE owner=? AND key='billing'", (encoded(billing), owner))
            return {'message': 'Local subscription cancelled', 'redirect': '/billing'}
        if action == 'service-settings':
            service, account = body.get('service'), body.get('account', 'default')
            row = conn.execute('SELECT settings FROM ifttt_connections WHERE owner=? AND service=? AND account=? AND connected=1',(owner, service, account)).fetchone()
            if not row: raise ValueError('Connect this service first')
            zone = body.get('timezone')
            if not isinstance(zone, str) or zone not in self.timezones: raise ValueError('Choose a valid time zone')
            settings = json.loads(row['settings']) | {'timezone': zone}
            conn.execute('UPDATE ifttt_connections SET settings=?,updated_at=? WHERE owner=? AND service=? AND account=?',(encoded(settings),now,owner,service,account))
            return {'message':'Service time zone saved'}
        if action in ('connect', 'disconnect'):
            service = body.get('service')
            account = body.get('account', 'default')
            if service not in self.services: raise ValueError('Unknown service')
            if not isinstance(account, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', account): raise ValueError('Invalid service account')
            if account != 'default' and self._plan(conn, owner) != 'pro_plus': raise ValueError('Multiple service accounts require Pro+')
            label = body.get('label', 'Local ' + service.replace('_', ' ').title())
            if not isinstance(label, str) or not 1 <= len(label) <= 160: raise ValueError('Enter an account label')
            conn.execute('''INSERT INTO ifttt_connections(owner,service,account,label,connected,updated_at)
                VALUES (?,?,?,?,?,?) ON CONFLICT(owner,service,account) DO UPDATE SET
                label=excluded.label,connected=excluded.connected,updated_at=excluded.updated_at''',
                         (owner, service, account, label, int(action == 'connect'), now))
            if action == 'disconnect':
                for row in conn.execute('SELECT id,definition FROM ifttt_applets WHERE owner=? AND archived=0', (owner,)).fetchall():
                    definition = json.loads(row['definition'])
                    steps = [definition['trigger'], *definition['actions'], *definition.get('queries', [])]
                    if any(self.modules[s['module']]['service'] == service and s['account'] == account for s in steps):
                        self._archive(conn, owner, row['id'], now)
            return {'connected': action == 'connect', 'service': service}
        if action in ('create', 'update'):
            title = body.get('title', '')
            if not isinstance(title, str) or not 1 <= len(title.strip()) <= 300: raise ValueError('Enter an Applet title')
            definition = self._definition(conn, owner, body.get('definition'))
            self._connections(conn, owner, definition)
            if action == 'create':
                origin = 'diy'
                if body.get('source_path'):
                    source = self.published.get(body['source_path'])
                    if source is None: raise ValueError('Published Applet not found')
                    actual = [definition['trigger']['module'], *[s['module'] for s in definition['queries']], *[s['module'] for s in definition['actions']]]
                    if actual != source['modules']: raise ValueError('Applet steps do not match the published Applet')
                    title = source['title']
                    origin = 'published:' + body['source_path']
                self._quota(conn, owner)
                applet_id = identifier('local-')
                conn.execute('INSERT INTO ifttt_applets(id,owner,title,definition,enabled,archived,origin,created_at,updated_at) VALUES (?,?,?,?,1,0,?,?,?)',
                             (applet_id, owner, title.strip(), encoded(definition), origin, now, now))
            else:
                applet_id = body.get('id')
                row = self._applet(conn, owner, applet_id)
                if row['origin'] != 'diy': raise ValueError('Make this Applet your own before editing')
                if body.get('revision') != row['revision']: raise ValueError('Applet changed. Reload before saving.')
                conn.execute('UPDATE ifttt_applets SET title=?,definition=?,revision=revision+1,updated_at=? WHERE id=? AND owner=?',
                             (title.strip(), encoded(definition), now, applet_id, owner))
                self._cancel_pending(conn, owner, applet_id, now, 'Applet updated')
            return {'id': applet_id, 'redirect': '/applets/' + applet_id}
        if action == 'convert':
            row = self._applet(conn, owner, body.get('id'))
            if row['archived']: raise ValueError('Restore the Applet before converting it')
            conn.execute("UPDATE ifttt_applets SET origin='diy',revision=revision+1,updated_at=? WHERE id=? AND owner=?", (now, row['id'], owner))
            return {'redirect': '/create?edit=' + row['id']}
        if action in ('archive', 'restore', 'enable', 'disable', 'delete'):
            row = self._applet(conn, owner, body.get('id'))
            if action == 'archive': self._archive(conn, owner, row['id'], now)
            elif action == 'restore':
                if row['archived']:
                    self._quota(conn, owner)
                    self._connections(conn, owner, json.loads(row['definition']))
                    conn.execute('UPDATE ifttt_applets SET archived=0,enabled=0,revision=revision+1,updated_at=? WHERE id=? AND owner=?', (now, row['id'], owner))
            elif action == 'enable':
                if row['archived']: raise ValueError('Restore this Applet before connecting it')
                self._connections(conn, owner, json.loads(row['definition']))
                conn.execute('UPDATE ifttt_applets SET enabled=1,revision=revision+1,updated_at=? WHERE id=? AND owner=?', (now, row['id'], owner))
            elif action == 'disable':
                conn.execute('UPDATE ifttt_applets SET enabled=0,revision=revision+1,updated_at=? WHERE id=? AND owner=?', (now, row['id'], owner))
                self._cancel_pending(conn, owner, row['id'], now, 'Applet disconnected')
            else:
                if not row['archived'] and row['origin'] == 'diy': raise ValueError('Archive this Applet before deleting it permanently')
                self._cancel_pending(conn, owner, row['id'], now, 'Applet deleted')
                conn.execute('DELETE FROM ifttt_applets WHERE id=? AND owner=?', (row['id'], owner))
            return {'id': row['id'], 'message': action.title() + ' complete'}
        if action in ('event', 'run'):
            if action == 'run':
                applet = self._applet(conn, owner, body.get('id'))
                if not applet['enabled'] or applet['archived']: raise ValueError('Connect this Applet before running it')
                trigger = json.loads(applet['definition'])['trigger']
                module = trigger['module']
                service_account = trigger.get('account', 'default')
                target = applet['id']
            else:
                module = body.get('module')
                service_account = body.get('account', 'default')
                target = None
            if module not in self.modules or self.modules[module]['kind'] != 'triggers': raise ValueError('Choose a trigger')
            if not isinstance(service_account, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', service_account): raise ValueError('Invalid service account')
            ingredients = body.get('ingredients', {})
            if not isinstance(ingredients, dict) or len(encoded(ingredients)) > 16000: raise ValueError('Invalid event ingredients')
            event_key = body.get('event_key', body['operation_key'])
            if not isinstance(event_key, str) or not 1 <= len(event_key) <= 200: raise ValueError('Invalid event identity')
            if event_key.startswith('service-account:'): raise ValueError('Event identity uses a reserved prefix')
            if service_account != 'default': event_key = 'service-account:'+str(len(service_account))+':'+service_account+':'+event_key
            existing = conn.execute('SELECT * FROM ifttt_events WHERE owner=? AND event_key=?', (owner, event_key)).fetchone()
            if existing:
                if existing['module'] != module or existing['ingredients'] != encoded(ingredients): raise ValueError('Event identity already used')
                return {'event_id': existing['id'], 'duplicate': True}
            event_id = identifier('event-')
            conn.execute('INSERT INTO ifttt_events VALUES (?,?,?,?,?,?)', (event_id, owner, module, encoded(ingredients), event_key, now))
            runs = []
            for row in conn.execute('SELECT * FROM ifttt_applets WHERE owner=? AND enabled=1 AND archived=0', (owner,)).fetchall():
                definition = json.loads(row['definition'])
                if definition['trigger']['module'] != module or target and row['id'] != target: continue
                if definition['trigger'].get('account','default') != service_account: continue
                if target is None and self.modules[module]['service'] == 'feed':
                    fields = definition['trigger']['fields']
                    if ingredients.get('FeedUrl', ingredients.get('feed_url')) != fields.get('feed_url'): continue
                    if fields.get('query') and str(fields['query']).lower() not in encoded(ingredients).lower(): continue
                self._connections(conn, owner, definition)
                run_id = identifier('run-')
                steps = [{'kind': 'trigger', 'module': module, 'status': 'success', 'timestamp': now, 'ingredients': ingredients}]
                for query in definition.get('queries', []):
                    service = self.modules[query['module']]['service']
                    history = conn.execute('SELECT e.payload,e.step_index,r.definition FROM ifttt_effects e JOIN ifttt_runs r ON r.id=e.run_id AND r.owner=e.owner WHERE e.owner=? AND e.service=? ORDER BY e.created_at DESC', (owner, service))
                    results = []
                    for effect in history:
                        account = json.loads(effect['definition'])['actions'][effect['step_index']].get('account','default')
                        if account == query.get('account','default'): results.append(json.loads(effect['payload']))
                        if len(results) == 50: break
                    steps.append({'kind': 'query', 'module': query['module'], 'status': 'success', 'timestamp': now, 'results': results, 'adapter': 'local history'})
                status = 'pending'
                if definition.get('filter_code', '').strip():
                    try:
                        settings = json.loads(conn.execute('SELECT settings FROM ifttt_profiles WHERE owner=?', (owner,)).fetchone()['settings'])
                        zone = settings.get('timezone', 'UTC')
                        zone = self.timezones.get(zone, {}).get('iana', zone)
                        outcomes = evaluate_filter(definition['filter_code'], definition, self.modules, ingredients,
                                                   [s for s in steps if s['kind'] == 'query'], now, zone)
                        definition['filter_outcomes'] = outcomes
                        steps.append({'kind': 'filter', 'status': 'success', 'timestamp': now, 'outcomes': outcomes})
                    except ValueError as error:
                        status = 'failed'
                        steps.append({'kind': 'filter', 'status': 'failed', 'timestamp': now, 'message': str(error)})
                conn.execute('INSERT INTO ifttt_runs(id,owner,applet_id,event_id,status,definition,due_at,steps,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                             (run_id, owner, row['id'], event_id, status, encoded(definition), now + definition.get('delay_seconds', 0), encoded(steps), now))
                if status == 'failed': conn.execute('UPDATE ifttt_runs SET finished_at=? WHERE id=?', (now, run_id))
                runs.append(run_id)
            return {'event_id': event_id, 'run_ids': runs}
        raise ValueError('Unknown automation action')

    def schedule(self, now=None):
        """Observe local clock triggers with a durable per-Applet minute identity."""
        now = int(time.time()) if now is None else int(now)
        generated = 0
        with self.backend.lifecycle.connection(transaction=True) as conn:
            rows = conn.execute('''SELECT a.*,p.settings FROM ifttt_applets a
                JOIN ifttt_profiles p ON p.owner=a.owner WHERE a.enabled=1 AND a.archived=0''').fetchall()
            for row in rows:
                definition = json.loads(row['definition'])
                trigger = definition['trigger']
                if self.modules[trigger['module']]['service'] != 'date_and_time': continue
                zone = json.loads(row['settings']).get('timezone', 'UTC')
                connection = conn.execute('SELECT settings FROM ifttt_connections WHERE owner=? AND service=? AND account=?', (row['owner'],'date_and_time',trigger.get('account','default'))).fetchone()
                if connection: zone = json.loads(connection['settings']).get('timezone',zone)
                try: tz = ZoneInfo(zone)
                except ZoneInfoNotFoundError:
                    recorded = self.timezones.get(zone, {})
                    try: tz = ZoneInfo(recorded.get('iana') or '')
                    except (ZoneInfoNotFoundError, ValueError): tz = timezone(timedelta(minutes=recorded.get('offset_minutes', 0)))
                scheduled_at = now // 60 * 60
                moment = datetime.fromtimestamp(scheduled_at, tz)
                if not self._schedule_matches(trigger, moment): continue
                key = 'schedule:' + row['id'] + ':' + str(now // 60)
                result = self._mutate(conn, row['owner'], 'run', {'id': row['id'], 'event_key': key, 'operation_key': key,
                    'ingredients': {'CheckTime': moment.isoformat(), 'LocalTimestamp': scheduled_at}})
                generated += int(not result.get('duplicate', False))
        return generated

    def _cancel_pending(self, conn, owner, applet_id, now, reason):
        for row in conn.execute("SELECT id,steps FROM ifttt_runs WHERE owner=? AND applet_id=? AND status='pending'", (owner, applet_id)).fetchall():
            steps = json.loads(row['steps']) + [{'kind': 'lifecycle', 'status': 'cancelled', 'reason': reason, 'timestamp': now}]
            conn.execute("UPDATE ifttt_runs SET status='cancelled',steps=?,finished_at=? WHERE id=?", (encoded(steps), now, row['id']))

    def _archive(self, conn, owner, applet_id, now):
        conn.execute('UPDATE ifttt_applets SET archived=1,enabled=0,revision=revision+1,updated_at=? WHERE id=? AND owner=?', (now, applet_id, owner))
        self._cancel_pending(conn, owner, applet_id, now, 'Applet archived')

    def drain(self, now=None):
        """Durable delayed actions; serialize execution and persist each local effect once."""
        now = int(time.time()) if now is None else now
        count = 0
        with self.backend.lifecycle.connection(transaction=True) as conn:
            for run in conn.execute("SELECT * FROM ifttt_runs WHERE status='pending' AND due_at<=? ORDER BY created_at LIMIT 100", (now,)).fetchall():
                steps = json.loads(run['steps'])
                try:
                    applet = self._applet(conn, run['owner'], run['applet_id'])
                    if not applet['enabled'] or applet['archived']: raise ValueError('Applet is not connected')
                    definition = json.loads(run['definition'])
                    self._connections(conn, run['owner'], definition)
                    ingredients = steps[0]['ingredients']
                    def expand(value):
                        if isinstance(value, list): return [expand(v) for v in value]
                        return re.sub(r'\{\{\s*([\w.]+)\s*\}\}', lambda match: str(ingredients.get(match[1], '')), value)
                    for index, action in enumerate(definition['actions']):
                        service = self.modules[action['module']]['service']
                        payload = {key: expand(value) for key, value in action['fields'].items()}
                        outcome = definition.get('filter_outcomes', [{}] * len(definition['actions']))[index]
                        if outcome.get('skip'):
                            steps.append({'kind': 'action', 'module': action['module'], 'status': 'skipped', 'reason': outcome.get('reason', ''), 'timestamp': now})
                            continue
                        payload.update(outcome.get('fields', {}))
                        effect_id = identifier('effect-')
                        conn.execute('INSERT OR IGNORE INTO ifttt_effects VALUES (?,?,?,?,?,?,?,?)',
                                     (effect_id, run['owner'], run['id'], index, service, action['module'], encoded(payload), now))
                        steps.append({'kind': 'action', 'module': action['module'], 'status': 'success', 'timestamp': now,
                                      'fields': payload, 'adapter': 'local effect store', 'effect_id': effect_id})
                    status = 'success'
                except (ValueError, LookupError) as error:
                    status = 'failed'
                    steps.append({'kind': 'error', 'status': 'failed', 'message': str(error), 'timestamp': now})
                conn.execute('UPDATE ifttt_runs SET status=?,steps=?,finished_at=? WHERE id=?', (status, encoded(steps), now, run['id']))
                count += 1
        return count
