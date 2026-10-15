"""IFTTT offline application, bound to the generated site backend runtime."""
import html
import hashlib
import json
import mimetypes
import os
import secrets
import re
import threading
import time
import smtplib
from email.message import EmailMessage
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit, unquote

from backend.site_backend_integration import open_site_services
from backend.automation import Automation
from backend.account import Accounts
from websitebench.local_clone_auth import LocalAuthStore
from websitebench.local_clone_auth.store import AuthError
from websitebench.site_backend.errors import PaymentError

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get('PORT', '18180'))
if PORT not in range(18180, 18190) and os.environ.get('IFTTT_ISOLATED_VERIFY') != '1':
    raise RuntimeError('IFTTT port must be in 18180–18189 outside verifier-owned isolation')
ORIGIN = f'http://127.0.0.1:{PORT}'
BACKEND, _ = open_site_services()
WORKER = secrets.token_urlsafe(32)
AUTH = LocalAuthStore(BACKEND.lifecycle.database_path, site_id=BACKEND.config.site_id,
                      mail_mode='SMTP_PENDING', mail_worker_token=WORKER)
AUTH.ensure_schema()
AUTH.seed_account(subject_id='ifttt-demo', email='demo@ifttt.offline.invalid',
                  display_name='IFTTT Demo', password='IFTTT-Demo-2026!')
COOKIE = BACKEND.session_cookie['name']
ROUTES = json.loads((ROOT / 'routes.json').read_text())
ALIASES = json.loads((ROOT / 'route-aliases.json').read_text()) if (ROOT / 'route-aliases.json').exists() else {}
INVENTORY = json.loads((ROOT / 'scope-inventory.json').read_text())
UNAVAILABLE = json.loads((ROOT / 'unavailable-pages.json').read_text())
BOUNDARIES = {r['route']: r for r in INVENTORY['data_boundaries']}
MODULES = json.loads((ROOT / 'module-catalog.json').read_text())
PUBLISHED = json.loads((ROOT / 'published-applets.json').read_text())
AUTOMATION = Automation(BACKEND, MODULES, PUBLISHED, json.loads((ROOT / 'timezones.json').read_text()))
ACCOUNTS = Accounts(BACKEND, AUTH, AUTOMATION)
HELP = json.loads((ROOT / 'help-catalog.json').read_text())
SEARCH = json.loads((ROOT / 'search-catalog.json').read_text()) if (ROOT / 'search-catalog.json').exists() else []
ROUTE_INDEX = {}
for row in ROUTES:
    ROUTE_INDEX.setdefault(row['path'], []).append(row)
# Captures are indexed by requested path, while their canonical redirect targets
# must also serve the captured body (e.g. discovery/goals and renamed services).
for source, actors in ALIASES.items():
    for actor, target in actors.items():
        key = urlsplit(target).path
        if key not in ROUTE_INDEX:
            captured = [row for row in ROUTE_INDEX.get(source, []) if row['actor'] == actor]
            if captured: ROUTE_INDEX[key] = captured
PRIVATE_PATHS = {urlsplit(row['route']).path for row in INVENTORY['full_routes'] if row['family'] in {'account', 'activity', 'service-management', 'private-applet-management', 'create'}}
if (ROOT / 'linked-targets.json').exists():
    PRIVATE_PATHS.update(json.loads((ROOT / 'linked-targets.json').read_text()).get('protected_aliases', []))
ASSET_MIMES = {v['url']: v['mime'] for v in json.loads((ROOT / 'asset-map.json').read_text()).values()}


def destination(value):
    if isinstance(value, str) and urlsplit(value).hostname in {'ifttt.com', 'www.ifttt.com'}:
        parsed = urlsplit(value)
        value = parsed.path + ('?' + parsed.query if parsed.query else '')
    if not isinstance(value, str) or not value.startswith('/') or value.startswith('//') or '\\' in value:
        return '/my_applets'
    if any(ord(c) < 32 for c in value): return '/my_applets'
    return value


def shell(title, body, *, boundary=False):
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)} - IFTTT</title><link rel="stylesheet" href="/local.css"></head>'
            '<body class="local-shell"' + (' data-boundary-page="true"' if boundary else '') + '>'
            '<header><a class="brand" href="/">IFTTT</a><nav><a href="/explore">Explore</a>'
            '<a href="/my_applets">My Applets</a><a href="/create">Create</a></nav></header>'
            f'<main><h1>{html.escape(title)}</h1>{body}</main><footer><a href="/hc/en-us">Help</a></footer>'
            '<script src="/local.js" defer></script><script src="/automation.js" defer></script></body></html>')


def verification_page(purpose):
    registration = purpose == 'registration'
    title = 'Verify your email' if registration else 'Reset your password'
    action = 'verify' if registration else 'reset'
    body = ('<p>Use the code from your IFTTT email. This local account flow sends mail to the local inbox.</p>'
            f'<form data-auth-action="{action}"><label>Verification code<input name="code" inputmode="numeric" autocomplete="one-time-code" required></label>')
    if not registration: body += '<label>New password<input name="password" type="password" minlength="8" required autocomplete="new-password"></label>'
    body += (f'<button type="submit">Continue</button><p role="alert" class="local-error"></p></form>'
             f'<button type="button" data-retry-purpose="{purpose}">Retry email delivery</button>'
             f'<button type="button" data-resend-purpose="{purpose}">Resend code</button>')
    return shell(title, body)


def send_challenge(token, purpose):
    claim = AUTH.claim_pending_mail_for_session(token, purpose=purpose, worker_token=WORKER)
    if claim is None:
        with AUTH.connect() as conn:
            session = AUTH._session_row(conn, token)
            mail = conn.execute('SELECT status FROM local_auth_mail_outbox WHERE session_digest=? AND purpose=? ORDER BY mail_id DESC LIMIT 1', (session['session_digest'], purpose)).fetchone() if session else None
        if (mail and mail['status'] != 'SMTP_SENT') or (not mail and purpose != 'password-reset'):
            raise ConnectionError('Email could not be sent. Retry delivery.')
        return
    rendered = BACKEND.mail.issue(purpose, claim['recipient'],
                                 {'code': claim['verification_code'], 'minutes': '10'})
    msg = EmailMessage()
    msg['From'] = 'IFTTT <' + os.environ.get('WEBSITEBENCH_SMTP_FROM', 'no-reply@ifttt.clone.test') + '>'
    msg['To'] = claim['recipient']
    msg['Subject'] = rendered['subject']
    route = {'registration': '/join/verify', 'password-reset': '/passwords/reset', 'passwordless-signin': '/local-identity/verify'}[purpose]
    # Only the short-lived challenge is included; a session token never appears in mail URLs.
    link = ORIGIN + route + '?code=' + quote(claim['verification_code'])
    msg.set_content(rendered['text'] + '\n\n' + link + '\n')
    AUTH.reserve_mail_target_request(claim['mail_id'], claim['claim_token'], worker_token=WORKER)
    try:
        host = os.environ.get('WEBSITEBENCH_SMTP_HOST', '127.0.0.1')
        if host not in {'127.0.0.1', 'localhost', '::1'}: raise ValueError('SMTP must use local Mailpit')
        with smtplib.SMTP(host, int(os.environ.get('WEBSITEBENCH_SMTP_PORT', '1025')), timeout=10) as smtp:
            smtp.send_message(msg)
    except Exception:
        AUTH.finish_mail_claim(claim['mail_id'], claim['claim_token'], sent=False, target_request_count=1,
                               accepted_request_count=0, error='network', worker_token=WORKER)
        raise ConnectionError('Email could not be sent. Retry delivery.') from None
    AUTH.finish_mail_claim(claim['mail_id'], claim['claim_token'], sent=True, target_request_count=1,
                           accepted_request_count=1, worker_token=WORKER)


def send_account_mail(purpose, recipient, variables, attachment=None):
    rendered = BACKEND.mail.issue(purpose, recipient, variables)
    msg = EmailMessage()
    msg['From'] = 'IFTTT <' + os.environ.get('WEBSITEBENCH_SMTP_FROM', 'no-reply@ifttt.clone.test') + '>'
    msg['To'], msg['Subject'] = recipient, rendered['subject']
    msg.set_content(rendered['text'] + '\n\n' + ORIGIN + '/settings\n')
    if attachment is not None:
        msg.add_attachment(json.dumps(attachment, ensure_ascii=False, indent=2).encode(), maintype='application', subtype='json', filename='ifttt-local-export.json')
    try:
        host = os.environ.get('WEBSITEBENCH_SMTP_HOST', '127.0.0.1')
        if host not in {'127.0.0.1', 'localhost', '::1'}: raise ValueError('SMTP must use local Mailpit')
        with smtplib.SMTP(host, int(os.environ.get('WEBSITEBENCH_SMTP_PORT', '1025')), timeout=10) as smtp: smtp.send_message(msg)
    except Exception:
        raise ConnectionError('Email could not be sent. Please retry.') from None


class Handler(BaseHTTPRequestHandler):
    server_version = 'IFTTTLocal/1'

    def log_message(self, *_): pass  # Never log verification codes or account inputs.

    def respond(self, status, body=b'', mime='text/html; charset=utf-8', token=None, location=None):
        if isinstance(body, str): body = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; media-src 'self'; connect-src 'self'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'self'")
        if token is not None:
            self.send_header('Set-Cookie', f'{COOKIE}={token}; Path=/; Secure; HttpOnly; SameSite=Lax')
        if location: self.send_header('Location', location)
        self.end_headers()
        if self.command != 'HEAD':
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError): pass  # Browser cancelled navigation/media.

    def serve_asset(self, file, mime):
        """Serve media byte ranges without buffering entire videos in memory."""
        size = file.stat().st_size
        start, end, status = 0, size - 1, 200
        requested = self.headers.get('Range', '') if self.command == 'GET' else ''
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
        if match and any(match.groups()) and not self.headers.get('If-Range'):
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            else:
                length = int(last)
                start = max(0, size - length)
            if start >= size or start > end or (not first and int(last) == 0):
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.send_header('Content-Length', '0')
                self.send_header('Accept-Ranges', 'bytes')
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(max(0, end - start + 1)))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; media-src 'self'; connect-src 'self'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'self'")
        if status == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        if self.command == 'HEAD':
            return
        remaining = end - start + 1
        try:
            with file.open('rb') as stream:
                stream.seek(start)
                while remaining > 0:
                    block = stream.read(min(65536, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Metadata preload and seeking may cancel a previous media range.

    def session(self):
        cookies = SimpleCookie()
        try: cookies.load(self.headers.get('Cookie', ''))
        except Exception: pass
        return AUTH.ensure_session(cookies[COOKIE].value if COOKIE in cookies else None)

    def do_HEAD(self): self.do_GET()

    def do_GET(self):
        u = urlsplit(self.path)
        path, query = unquote(u.path), parse_qs(u.query)
        if path == '/healthz':
            self.respond(200, json.dumps({'ok': True, 'site_id': 'ifttt', 'stage': 'full-implementation'}), 'application/json'); return
        if path.startswith('/assets/') or path in {'/local.js', '/local.css', '/automation.js'}:
            file = (ROOT / path.lstrip('/')).resolve()
            if not file.is_relative_to(ROOT) or not file.is_file(): self.respond(404, 'Asset unavailable'); return
            self.serve_asset(file, ASSET_MIMES.get(path) or mimetypes.guess_type(file)[0] or 'application/octet-stream'); return
        token, session = self.session()
        if path == '/local/session':
            self.respond(200, json.dumps(session), 'application/json', token); return
        if path in UNAVAILABLE:
            self.respond(303, token=token, location='/source-unavailable?path=' + quote(path, safe='')); return
        if path == '/source-unavailable':
            original = query.get('path', [''])[0]
            record = UNAVAILABLE.get(original)
            if not record:
                self.respond(404, shell('Unknown source record', '<p>No unavailable-source record exists for this address.</p>'), token=token); return
            source = ('https://help.ifttt.com' if original.startswith('/hc/') else 'https://ifttt.com') + original
            body = '<p>This is a local availability notice, not a reproduction of the missing source page.</p><p>' + html.escape(record['reason']) + '</p><label>Source address<input readonly value="' + html.escape(source, quote=True) + '"></label><button data-copy-destination>Copy source address</button><p><a href="/explore">Back to Explore</a></p>'
            self.respond(200, shell('Source page unavailable', body), token=token); return
        service_intent = re.fullmatch(r'/([^/]+)/(activation/start|settings/destroy/[^/]+)', path)
        if service_intent:
            service = service_intent[1]
            if service not in MODULES.get('service_icons', {}) and not any(row.get('service') == service for row in MODULES['modules']):
                self.respond(404, shell('Service unavailable', '<p>This service is not in the captured catalog.</p>'), token=token); return
            if not session['authenticated']:
                self.respond(303, token=token, location='/login?return_to=' + quote(self.path, safe='')); return
            intent = 'connect' if service_intent[2] == 'activation/start' else 'disconnect'
            body = '<section data-service-intent="' + intent + '" data-service="' + html.escape(service, quote=True) + '"><p>This manages your local service connection. No external provider is contacted.</p><button type="button">' + ('Connect locally' if intent == 'connect' else 'Review service removal') + '</button></section>'
            self.respond(200, shell('Service connection', body), token=token); return
        if path == '/explore/stories.rss':
            stories = json.loads((ROOT / 'stories-feed.json').read_text())['items']
            items = ''.join('<item><title>' + html.escape(row['title']) + '</title><link>' + html.escape(ORIGIN + urlsplit(row['url']).path) + '</link><pubDate>' + html.escape(row['published']) + '</pubDate></item>' for row in stories)
            feed = '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>IFTTT captured stories</title><link>' + ORIGIN + '/explore/stories</link><description>Stories available in this local snapshot.</description>' + items + '</channel></rss>'
            self.respond(200, feed, 'application/rss+xml', token); return
        if path == '/local/modules':
            self.respond(200, json.dumps(MODULES), 'application/json', token); return
        if path == '/local/timezones':
            self.respond(200, (ROOT / 'timezones.json').read_bytes(), 'application/json', token); return
        if path == '/local/applet-pages':
            catalog = json.loads((ROOT / 'applet-pages.json').read_text()) if (ROOT / 'applet-pages.json').exists() else {}
            collection = query.get('collection', [''])[0]
            record = catalog.get(collection) or next((row for row in catalog.values() if urlsplit(row['source_url']).path == collection), None)
            if not record:
                self.respond(503, '{"error":"This collection is still being captured. Please try again later."}', 'application/json', token); return
            try: offset = max(0, int(query.get('offset', ['0'])[0]))
            except ValueError: offset = 0
            end = next((count for count in record['counts'] if count > offset), len(record['cards']))
            end = min(end, len(record['cards']))
            self.respond(200, json.dumps({'cards': record['cards'][offset:end], 'next_offset': end,
                'more': end < len(record['cards']), 'complete': record['status'] == 'complete'}), 'application/json', token); return
        if path == '/local/private-template':
            if not session['authenticated']:
                self.respond(401, '{"error":"Sign in to continue"}', 'application/json', token); return
            template = json.loads((ROOT / 'private-templates.json').read_text()).get(query.get('from', [''])[0])
            self.respond(200 if template else 404, json.dumps(template or {'error': 'Template not found'}), 'application/json', token); return
        if path == '/local/search':
            term = query.get('query', [''])[0].strip().casefold()[:1024]
            kind = query.get('kind', ['all'])[0]
            matches = [item for item in SEARCH if term and term in item['text'].casefold() and (kind == 'all' or item['kind'] == kind)]
            self.respond(200, json.dumps({'total': len(matches), 'items': [{k: item[k] for k in ('route', 'title', 'kind')} for item in matches[:8]]}), 'application/json', token); return
        if path == '/local/published':
            source = PUBLISHED.get(query.get('path', [''])[0])
            self.respond(200 if source else 404, json.dumps(source or {'error': 'Published Applet not found'}), 'application/json', token); return
        if path == '/local/account':
            if not session['authenticated']:
                self.respond(401, '{"error":"Sign in to continue"}', 'application/json', token); return
            self.respond(200, json.dumps(ACCOUNTS.public(session['account']['account_id'])), 'application/json', token); return
        if path == '/local/automation':
            if not session['authenticated']:
                self.respond(401, '{"error":"Sign in to continue"}', 'application/json', token); return
            AUTOMATION.drain()
            self.respond(200, json.dumps(AUTOMATION.snapshot(session['account']['account_id'])), 'application/json', token); return
        if path == '/session/logout':
            AUTH.sign_out(token)
            self.respond(303, token=AUTH.create_anonymous_session(), location='/login'); return
        private = path in PRIVATE_PATHS or path.startswith(('/local/', '/applets/local-', '/settings', '/activity', '/two-step-verification', '/p/me/', '/applet_discovery')) or path in {'/create', '/my_applets', '/my_services', '/billing', '/profile/edit'}
        if private and not session['authenticated']:
            self.respond(303, token=token, location='/login?return_to=' + quote(self.path, safe='')); return
        if path in {'/login', '/join'} and session['authenticated']:
            self.respond(303, token=token, location=destination(query.get('return_to', ['/my_applets'])[0])); return
        if path in {'/join/verify', '/passwords/reset'}:
            self.respond(200, verification_page('registration' if path == '/join/verify' else 'password-reset'), token=token); return
        if path == '/login/two-step':
            self.respond(200, shell('Two-step verification', '<form data-auth-action="two-step"><label>Authenticator or backup code<input name="code" autocomplete="one-time-code" required></label><button type="submit">Verify</button><p role="alert" class="local-error"></p></form>'), token=token); return
        if path == '/local-identity':
            provider = query.get('provider', ['Google'])[0]
            if provider not in {'Google', 'Apple', 'Facebook'}: provider = 'Google'
            body = '<p>This is the local ' + html.escape(provider) + ' sign-in adapter. Verify a local email address to continue. No external identity provider is contacted.</p><form data-auth-action="identity-start"><label>Email<input name="email" type="email" required></label><button type="submit">Continue</button></form>'
            self.respond(200, shell('Continue with ' + provider, body), token=token); return
        if path == '/local-identity/verify':
            self.respond(200, shell('Verify local sign-in', '<form data-auth-action="identity-verify"><label>Email verification code<input name="code" autocomplete="one-time-code" required></label><button type="submit">Continue</button></form><button data-resend-purpose="passwordless-signin">Resend code</button>'), token=token); return
        if path == '/external':
            url = query.get('url', [''])[0]
            self.respond(200, shell('External link', '<p>This destination is outside the offline IFTTT site.</p>'
                f'<label>Original destination<input readonly value="{html.escape(url, quote=True)}"></label>'
                '<button data-copy-destination>Copy destination</button><p><a href="/explore">Back to Explore</a></p>', boundary=True), token=token); return
        if path == '/catalog-boundary':
            collection = destination(query.get('collection', ['/explore'])[0])
            self.respond(200, shell('More Applets', '<p>The captured cards from this collection remain available. Further catalog results are outside this offline snapshot.</p><p>Collection: ' + html.escape(collection) + '</p><p><a href="' + html.escape(collection, quote=True) + '">Back to this collection</a></p><p><a href="/explore/applets">Explore captured Applets</a></p>', boundary=True), token=token); return
        actor = 'member' if session['authenticated'] else 'anonymous'
        alias = ALIASES.get(self.path, ALIASES.get(path, {})).get(actor)
        # The source empty-account capture redirects its archive query to the
        # default list. Locally persisted archived Applets must retain this view.
        if path == '/my_applets' and query.get('tab') == ['archived'] and session['authenticated']:
            if any(applet['archived'] for applet in AUTOMATION.snapshot(session['account']['account_id'])['applets']):
                alias = None
        if alias:
            self.respond(303, token=token, location=alias); return
        if path.startswith('/search/query/') and path not in ROUTE_INDEX:
            term = path.removeprefix('/search/query/').strip()[:1024]
            try: offset = max(0, int(query.get('offset', ['0'])[0]))
            except ValueError: offset = 0
            kind = query.get('kind', ['all'])[0]
            found = [item for item in SEARCH if term.casefold() in item['text'].casefold() and (kind == 'all' or item['kind'] == kind)]
            content = '<div class="explore-discover-container"><h1>Results for “' + html.escape(term) + '”</h1><p>' + str(len(found)) + ' results in the offline catalog</p><nav class="local-search-kinds">'
            content += ''.join('<a href="' + quote(path, safe='/') + '?kind=' + k + '">' + label + '</a>' for k, label in [('all', 'All'), ('applets', 'Applets'), ('services', 'Services'), ('stories', 'Stories')])
            content += '</nav><div class="local-search-results">' + ''.join('<div class="local-search-card">' + item['card'] + '</div>' for item in found[offset:offset + 30]) + '</div>'
            if not found: content += '<p>No results found. Try a service name or a different keyword.</p>'
            if offset: content += '<a class="button-secondary" href="' + quote(path, safe='/') + '?kind=' + quote(kind) + '&offset=' + str(max(0, offset - 30)) + '">Previous</a>'
            if offset + 30 < len(found): content += '<a class="button-secondary" href="' + quote(path, safe='/') + '?kind=' + quote(kind) + '&offset=' + str(offset + 30) + '">Next</a>'
            content += '</div>'
            template = next(r for r in ROUTE_INDEX['/search/query/calendar'] if r['state'] == 'default')
            page = (ROOT / template['file']).read_text()
            page = re.sub(r'(<main\b[^>]*>).*?(</main>)', lambda m: m[1] + content + m[2], page, count=1, flags=re.S)
            self.respond(200, page.replace('</body>', '<script src="/automation.js" defer></script></body>'), token=token); return
        view = query.get('_view', ['default'])[0]
        if path.startswith('/applets/local-'):
            try:
                with BACKEND.lifecycle.connection() as conn:
                    applet = AUTOMATION._applet(conn, session['account']['account_id'], path.split('/')[2])
                self.respond(200, shell(applet['title'], '<div id="local-applet-detail" data-applet-id="' + html.escape(applet['id'], quote=True) + '"></div>'), token=token)
            except LookupError:
                self.respond(404, shell('Applet not found', '<a href="/my_applets">My Applets</a>'), token=token)
            return
        if path == '/hc/en-us/search':
            term = query.get('query', [''])[0].strip().lower()
            found = [a for a in HELP['articles'] if term and term in (a['title'] + ' ' + a['body']).lower()]
            links = ''.join('<li><a href="/hc/en-us/articles/' + str(a['id']) + '">' + html.escape(a['title']) + '</a></li>' for a in found)
            self.respond(200, shell('Search Help', '<form><label>Search<input name="query" value="' + html.escape(term, quote=True) + '"></label><button>Search</button></form><ul>' + links + '</ul>' + ('' if found else '<p>No articles found.</p>')), token=token); return
        if re.match(r'^/hc/en-us/(articles|sections|categories)/\d+-', path):
            normalized = re.sub(r'(/\d+)-.*$', r'\1', path)
            self.respond(303, token=token, location=normalized); return
        available = ROUTE_INDEX.get(self.path, ROUTE_INDEX.get(path, []))
        candidates = [r for r in available if r['state'] == view]
        if not candidates and view == 'default':
            candidates = [r for r in ROUTE_INDEX.get(path, []) if r['state'] == 'default'] or available
        selected = next((r for r in candidates if r['actor'] == actor), None)
        if selected is None and path != '/my_applets': selected = next((r for r in candidates if r['actor'] == 'anonymous'), None)
        if selected is None and not private: selected = next((r for r in candidates if r['actor'] == 'member'), None)
        if selected:
            content = (ROOT / selected['file']).read_text().replace('</body>', '<script src="/automation.js" defer></script></body>')
            if actor == 'anonymous' and selected['actor'] == 'member':
                anonymous = next(r for r in ROUTE_INDEX['/explore'] if r['actor'] == 'anonymous' and r['state'] == 'default')
                public_header = re.search(r'<header\b[^>]*class="[^"]*unified-header[^"]*"[^>]*>.*?</header>', (ROOT / anonymous['file']).read_text(), re.S)
                if public_header: content = re.sub(r'<header\b[^>]*class="[^"]*unified-header[^"]*"[^>]*>.*?</header>', lambda _: public_header[0], content, count=1, flags=re.S)
                content = content.replace('data-local-actor="member"', 'data-local-actor="anonymous"')
            self.respond(200, content, token=token); return
        boundary = BOUNDARIES.get(self.path) or BOUNDARIES.get(path)
        if boundary:
            content = '<p>This item is outside the first five full details of its source collection in this offline edition.</p><p><a href="' + html.escape(destination(boundary['collection']), quote=True) + '">Back to source collection</a></p>'
            self.respond(200, shell(boundary['label'] or path, content, boundary=True), token=token); return
        self.respond(404, shell('Page unavailable', '<p>This address is not available in the captured catalog.</p><p><a href="/explore">Return to Explore</a></p>'), token=token)

    def do_POST(self):
        if urlsplit(self.path).path == '/local/test-session':
            expected = os.environ.get('IFTTT_TEST_SESSION_TOKEN', '')
            supplied = self.headers.get('X-IFTTT-Test', '')
            if not expected or not secrets.compare_digest(expected, supplied):
                self.respond(404, '{"error":"Unknown action"}', 'application/json'); return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length < 4096: raise ValueError('Invalid request')
                values = parse_qs(self.rfile.read(length).decode())
                token = AUTH.create_anonymous_session()
                result = AUTH.sign_in(token, email=values.get('email', [''])[0], password=values.get('password', [''])[0])
                self.respond(200, '{"authenticated":true}', 'application/json', result['session_token'])
            except (AuthError, ValueError):
                self.respond(403, '{"error":"Credentials rejected"}', 'application/json')
            return
        if self.headers.get('Origin') not in {ORIGIN, f'http://localhost:{PORT}'} or self.headers.get('X-IFTTT-Local') != '1':
            self.respond(403, '{"error":"Request origin rejected"}', 'application/json'); return
        token, session = self.session()
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length < 32768: raise ValueError('Invalid request size')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict): raise ValueError('Expected an object')
            if urlsplit(self.path).path == '/local/contact-sales':
                owner = session['account']['account_id'] if session['authenticated'] else 'contact-session:'+hashlib.sha256(token.encode()).hexdigest()
                answer = ACCOUNTS.contact_sales(owner, body, json.loads((ROOT / 'contact-options.json').read_text()))
                self.respond(200, json.dumps(answer), 'application/json', token); return
            if urlsplit(self.path).path.startswith('/local/account/'):
                if not session['authenticated']:
                    self.respond(401, '{"error":"Sign in to continue"}', 'application/json', token); return
                action = urlsplit(self.path).path.removeprefix('/local/account/')
                owner = session['account']['account_id']
                if action in {'email-start', 'delete-start'}:
                    purpose = 'email-change' if action == 'email-start' else 'account-deletion'
                    address, code = getattr(ACCOUNTS, action.replace('-', '_'))(owner, body)
                    try: send_account_mail(purpose, address, {'code': code, 'minutes': '10'})
                    except ConnectionError:
                        with BACKEND.lifecycle.connection(transaction=True) as conn:
                            conn.execute('DELETE FROM ifttt_preferences WHERE owner=? AND key=?', (owner, purpose))
                        raise
                    answer = {'message': 'Verification email sent'}
                elif action == 'export':
                    data = {'account': session['account'], 'preferences': ACCOUNTS.public(owner), 'automations': AUTOMATION.snapshot(owner)}
                    data['account'] = {key: value for key, value in data['account'].items() if key not in {'account_id', 'subject_id'}}
                    send_account_mail('data-export', session['account']['email_normalized'], {}, attachment=data)
                    answer = {'message': 'Your data export was sent to your local email inbox.'}
                elif action in {'settings', 'password', 'profile', 'delete', 'delete-verify', 'preference', 'two-step-start', 'two-step-enable', 'two-step-disable', 'email-verify'}:
                    answer = getattr(ACCOUNTS, action.replace('-', '_'))(owner, body)
                else: raise ValueError('Unknown account action')
                self.respond(200, json.dumps(answer), 'application/json', token); return
            if urlsplit(self.path).path.startswith('/local/automation/'):
                if not session['authenticated']:
                    self.respond(401, '{"error":"Sign in to continue"}', 'application/json', token); return
                action = urlsplit(self.path).path.removeprefix('/local/automation/')
                answer = AUTOMATION.mutate(session['account']['account_id'], action, body)
                AUTOMATION.drain()
                self.respond(200, json.dumps(answer), 'application/json', token); return
            action = urlsplit(self.path).path.removeprefix('/local/auth/')
            if action == 'login':
                email = body.get('email', '')
                if '@' not in email:
                    with AUTH.connect() as conn:
                        row = conn.execute('SELECT email_normalized FROM local_auth_accounts WHERE display_name=?', (email,)).fetchone()
                    email = row[0] if row else 'unknown@ifttt.offline.invalid'
                result = AUTH.sign_in(token, email=email, password=body.get('password', ''))
                target = destination(body.get('return_to'))
                pending = ACCOUNTS.require_factor(result, target)
                token = pending or result['session_token']
                answer = {'redirect': '/login/two-step' if pending else target}
            elif action == 'two-step':
                result = ACCOUNTS.verify_login(token, body.get('code', ''))
                token = result['session_token']
                answer = {'redirect': destination(result['redirect'])}
            elif action == 'identity-start':
                AUTH.start_passwordless_signin(token, email=body.get('email', ''), restart_invalid_flow=True)
                send_challenge(token, 'passwordless-signin')
                answer = {'redirect': '/local-identity/verify' + ('?return_to=' + quote(destination(body['return_to']), safe='') if body.get('return_to') else '')}
            elif action == 'identity-verify':
                AUTH.verify_passwordless_code(token, body.get('code', ''))
                result = AUTH.complete_passwordless_signin(token)
                target = destination(body.get('return_to'))
                pending = ACCOUNTS.require_factor(result, target)
                token = pending or result['session_token']
                answer = {'redirect': '/login/two-step' if pending else target}
            elif action == 'register':
                email = body.get('email', '')
                AUTH.start_registration(token, email=email, display_name=email.split('@')[0],
                                        password=body.get('password', ''), restart_invalid_flow=True)
                send_challenge(token, 'registration')
                answer = {'redirect': '/join/verify' + ('?return_to=' + quote(destination(body['return_to']), safe='') if body.get('return_to') else '')}
            elif action == 'verify':
                AUTH.verify_registration_code(token, body.get('code', ''))
                result = AUTH.complete_registration(token)
                AUTH.sign_out(result['session_token'])
                token = AUTH.create_anonymous_session()
                answer = {'redirect': '/login?verified=1' + ('&return_to=' + quote(destination(body['return_to']), safe='') if body.get('return_to') else '')}
            elif action == 'forgot':
                AUTH.start_password_reset(token, email=body.get('email', ''), restart_invalid_flow=True)
                send_challenge(token, 'password-reset')
                answer = {'redirect': '/passwords/reset'}
            elif action == 'reset':
                AUTH.verify_password_reset_code(token, body.get('code', ''))
                rotated = AUTH.complete_password_reset(token, new_password=body.get('password', ''))
                AUTH.sign_out(rotated)
                token = AUTH.create_anonymous_session()
                answer = {'redirect': '/login?reset=1'}
            elif action == 'retry':
                purpose = body.get('purpose')
                ACCOUNTS.resend(token, purpose, retry=True)
                send_challenge(token, purpose)
                answer = {'message': 'Email sent'}
            elif action == 'resend':
                purpose = body.get('purpose')
                ACCOUNTS.resend(token, purpose)
                send_challenge(token, purpose)
                answer = {'message': 'A new verification code was sent. Older codes no longer work.'}
            else:
                self.respond(404, '{"error":"Unknown action"}', 'application/json', token); return
            self.respond(200, json.dumps(answer), 'application/json', token)
        except ConnectionError as error:
            self.respond(503, json.dumps({'error': str(error)}), 'application/json', token)
        except LookupError as error:
            self.respond(404, json.dumps({'error': str(error)}), 'application/json', token)
        except (AuthError, PaymentError, ValueError, TypeError) as error:
            self.respond(400, json.dumps({'error': str(error)}), 'application/json', token)


if __name__ == '__main__':
    def worker():
        minute = None
        while True:
            try:
                current = int(time.time()) // 60
                if current != minute:
                    AUTOMATION.schedule()
                    minute = current
                AUTOMATION.drain()
            except Exception as error: print('Automation worker:', type(error).__name__, flush=True)
            time.sleep(1)
    threading.Thread(target=worker, daemon=True).start()
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
