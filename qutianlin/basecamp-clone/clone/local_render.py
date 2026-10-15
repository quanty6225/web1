"""Apply account-owned changes to the captured, local HTML templates."""
import html as escape_html
import json
import re
from lxml import html, etree
from urllib.parse import quote


def safe_rich_text(markup):
    """Keep editor formatting while excluding executable and remote content."""
    root = html.fragment_fromstring(markup or '', create_parent='div')
    allowed = {'p', 'div', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'del', 'blockquote', 'pre', 'code', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'a', 'img', 'figure', 'figcaption'}
    for node in list(root.iterdescendants()):
        if node.tag in {'script', 'style', 'iframe', 'object', 'embed', 'svg', 'math', 'form', 'input', 'button'}:
            node.drop_tree()
            continue
        if node.tag not in allowed:
            if isinstance(node.tag, str):node.drop_tag()
            continue
        href = node.get('href', '')
        src = node.get('src', '')
        alt = node.get('alt', '')
        node.attrib.clear()
        if node.tag == 'a':
            if href.startswith('/') and not href.startswith('//') and '\\' not in href:node.set('href', href)
            elif href.startswith(('https://', 'http://', 'mailto:')):node.set('href', '/external?target=' + quote(href, safe=''))
            elif href.startswith('#'):node.set('href', href)
        if node.tag == 'img':
            if src.startswith(('/files/', '/static/assets/')) and '\\' not in src:node.set('src', src);node.set('alt', alt)
            else:node.drop_tree()
    return (escape_html.escape(root.text or '') + ''.join(html.tostring(c, encoding='unicode') for c in root))


def render(markup, path, owner, connection, name, query=None, account=None):
    tree = html.document_fromstring(markup)
    # Hydrate query-opened forms through the same controller as a real click.
    # Captured dialogs contain live custom elements which the controller resets.
    if query and query.get('trigger_add_dialog') == 'true':
        for modal in tree.xpath('//bc-modal[@opened="true" and @data-desktop-modal-target="modal"]'):
            for child in list(modal):modal.remove(child)
            modal.set('opened','false')
    for chooser in tree.xpath('//*[@data-controller="cloud-file-chooser"]'):
        service=chooser.get('data-cloud-file-chooser-service')
        if service not in ('box','dropbox'):continue
        # Provider authentication is outside the offline runtime. Preserve the
        # working link form and route Browse to the explicit external boundary.
        chooser.attrib.pop('data-controller',None)
        for link in chooser.xpath('.//a[@data-action="cloud-file-chooser#startChoosingFiles"]'):
            link.attrib.pop('data-action',None)
            link.set('href','/external?target='+quote('https://www.'+service+'.com/',safe=''))
    for frame in tree.xpath('//*[@id="sidebar_frame" and @data-prefetched-frame-url-value]'):
        # A delayed prefetched inbox can overwrite a conversation the user has
        # already opened. Let Turbo own this frame's request and cancellation.
        controllers=frame.get('data-controller','').split()
        frame.set('data-controller',' '.join(value for value in controllers if value!='prefetched-frame'))
        if not frame.get('src'):frame.set('src',frame.get('data-prefetched-frame-url-value'))
        frame.set('loading','eager')
        frame.attrib.pop('data-prefetched-frame-url-value',None)
    for autocomplete in tree.xpath('//bc-autocomplete[.//input[@name="circle[users]"]]'):
        # Sidebar notification morphs must preserve the live Ping input. Its
        # custom element otherwise reconnects while Turbo is moving children.
        autocomplete.set('id', 'sidebar-new-circle-people')
        autocomplete.set('data-turbo-permanent', '')
        # Preserve the controller and its required input together during Turbo
        # frame replacement; moving only the input briefly leaves no target.
        groups=autocomplete.xpath('ancestor::*[@data-controller="group-ping-matches"][1]')
        if groups:
            groups[0].set('id','sidebar-new-circle-group')
            groups[0].set('data-turbo-permanent','')
            autocomplete.attrib.pop('data-turbo-permanent',None)
    from tool_operations import render as render_tools
    render_tools(tree,path,owner,connection)
    from card_table import render as render_cards
    render_cards(tree,path,owner,connection)
    personal_owner=account['account_id'] if account else owner
    subscription=connection.execute('SELECT value FROM bc_settings WHERE owner=? AND name="assignments_subscribed"',(personal_owner,)).fetchone()
    if subscription:
        enabled=json.loads(subscription['value'])
        for button in tree.xpath('//button[@data-url="/6302022/my/assignments/subscription.js"]'):
            button.text='Emailing tasks every Monday' if enabled else 'Email me tasks every Monday'
            for child in list(button):button.remove(child)
            button.set('data-behavior','unsubscribe_from_report' if enabled else 'subscribe_to_report')
    read = {r['name'].removeprefix('welcome-read-') for r in connection.execute('SELECT name FROM bc_settings WHERE owner=? AND name LIKE "welcome-read-%" AND value="true"', (personal_owner,))}
    for article in tree.xpath('//article[@data-reading]'):
        links = article.xpath('.//a[contains(@href,"/onboarding/messages/")]')
        if links and links[0].get('href').rsplit('/', 1)[-1] in read:
            previous = tree.xpath('//*[@data-sidebar--readings-target="reads"]')
            if previous:
                article.set('data-read', '')
                previous[0].append(article)
            else:
                article.getparent().remove(article)
    for item in tree.xpath('//*[@id="sidebar_badge"]//*'):
        if (item.text or '').strip() == '3':
            item.text = str(max(0, 3 - len(read)))
    mutations = connection.execute('SELECT * FROM bc_mutations WHERE (owner=? AND route NOT LIKE ?) OR (owner=? AND route LIKE ?)', (owner,'/6302022/my/%',personal_owner,'/6302022/my/%')).fetchall()
    for mutation in mutations:
        route = mutation['route']
        payload = json.loads(mutation['payload'])
        kind = mutation['kind']
        if kind == 'stars' and re.fullmatch(r'/6302022/buckets/\d+/stars',route):
            continue
        if kind == 'bookmarks' and payload.get('active') and path == '/6302022/my/navigation/bookmarks':
            from trash import erased
            if erased(connection, owner, payload.get('recording_path', '').rsplit('/', 1)[-1]):
                continue
            targets = tree.xpath('//*[@id="my_navigation_bookmarks"]') or [tree.find('body')]
            link = etree.SubElement(targets[0], 'a', {'href': payload.get('recording_path', '/6302022/'), 'class': 'local-new-item'})
            link.text = payload.get('title', 'Bookmark')
            for empty in tree.xpath('//*[contains(@class,"blank-slate") or contains(@class,"empty-state") or contains(@class,"tray__empty")]'):
                if empty.getparent() is not None:
                    empty.getparent().remove(empty)
        if kind == 'completion':
            for checkbox in tree.xpath('//*[@data-url]'):
                if checkbox.get('data-url', '').split('?')[0] != route:
                    continue
                done = payload.get('active', False)
                if done:
                    checkbox.set('checked', 'checked')
                else:
                    checkbox.attrib.pop('checked', None)
                for container in checkbox.iterancestors():
                    if 'completion_container' in container.get('data-role', ''):
                        classes = set(container.get('class', '').split())
                        classes.discard('completed')
                        if done:
                            classes.add('completed')
                        container.set('class', ' '.join(sorted(classes)))
                        break
        for form in tree.xpath('//form[@action]'):
            if form.get('action', '').split('?')[0] != route:
                continue
            if kind in ('stars', 'bookmarks'):
                active = bool(payload.get('active'))
                for button in form.xpath('.//button'):
                    if 'set-aside-btn' in button.get('class','').split():
                        classes=set(button.get('class','').split());classes.discard('set-aside-btn--on')
                        if active:classes.add('set-aside-btn--on')
                        button.set('class',' '.join(sorted(classes)));button.set('aria-pressed',str(active).lower())
                        continue
                    classes = button.get('class', '').replace('star-button--starred', '').replace('star-button--unstarred', '')
                    button.set('class', classes + (' star-button--starred' if active else ' star-button--unstarred'))
                    button.set('aria-pressed', str(active).lower())
                for field in form.xpath('.//input[@name="_method"]'):
                    field.set('value', 'delete' if active else 'put')
        from record_operations import apply_fields
        apply_fields(tree,route,payload)
    records = connection.execute('SELECT * FROM bc_records WHERE owner=? ORDER BY created', (owner,)).fetchall()
    for record in records:
        if json.loads(record['data']).get('url'):continue
        if path.rstrip('/') != record['parent'].rstrip('/'):
            continue
        targets = tree.xpath('//main') or [tree.find('body')]
        link = etree.SubElement(targets[0], 'a', {'href': '/6302022/local/' + record['id'], 'class': 'local-new-item', 'data-local-record': record['id']})
        link.text = record['title']
    from record_operations import render as render_records
    render_records(tree,path,owner,connection,name)
    from calendar_view import render as render_calendar
    render_calendar(tree,path,owner,connection,query)
    from task_reports import render as render_task_reports
    render_task_reports(tree,path,connection,account)
    if account:
        from home_preferences import render as render_home_preferences
        render_home_preferences(tree,connection,account)
    from task_fields import render as render_tasks
    render_tasks(tree,path,owner,connection,account)
    from comment_operations import render as render_comments
    render_comments(tree,path,owner,connection,account)
    from payment_operations import render as render_payments
    render_payments(tree,path,owner,connection,query)
    from settings_operations import render as render_settings
    render_settings(tree,path,owner,connection,query)
    from file_operations import render as render_files
    render_files(tree,path,owner,connection)
    if account:
        from social_operations import render as render_social
        render_social(tree,path,account,connection)
        from activity_search import render as render_activity
        render_activity(tree,path,owner,connection,account,query)
    if account:
        from notification_preferences import render as render_notification_preferences
        render_notification_preferences(tree,path,connection,account)
        from ping_actions import render_bookmarks
        render_bookmarks(tree,path,connection,account)
        from bubble_up import render as render_bubble_up
        render_bubble_up(tree,path,connection,account)
        from workspaces import render as render_members
        render_members(tree,path,account,connection)
        from role_overview import render as render_role_overview
        render_role_overview(tree,path,account,connection,query)
        from navigation_search import render as render_navigation_search
        render_navigation_search(tree,account,connection)
        from column_lifecycle import render as render_column_lifecycle
        render_column_lifecycle(tree,path,connection,account,query)
        from card_wormholes import render as render_wormholes
        render_wormholes(tree,path,connection,account,query or {})
        from trash import render as render_trash
        render_trash(tree,path,connection,account)
        from project_lifecycle import render as render_project_lifecycle
        render_project_lifecycle(tree,connection,account)
    # Resolve full-image links after owned-file rendering has replaced any
    # prototype media; never retain a prototype's viewer URL on a new upload.
    for image in tree.xpath('//img[contains(@data-behavior,"lightboxable")]'):
        target=None
        if image.get('src','').startswith('/files/'):
            target=image.get('src')
        else:
            links=image.xpath('ancestor::a[starts-with(@href,"/static/assets/")][1]')
            if links and image.get('data-src','').startswith('/external?'):
                candidate=links[0].get('href')
                if candidate.rsplit('.',1)[-1].lower() in {'png','jpg','jpeg','gif','webp','avif'}:target=candidate
        if target:
            image.set('data-src',target);image.set('data-download-url',target)
            image.attrib.pop('data-srcset',None)
    return '<!doctype html>\n' + html.tostring(tree, encoding='unicode')
