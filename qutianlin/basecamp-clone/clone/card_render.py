"""Current card column, native move menu, and recorded completion timestamp."""
import copy
from datetime import datetime, timezone
from lxml import html, etree


def column_label(column, columns=None):
    if columns and column.get('parent') in columns:
        return column_label(columns[column['parent']], columns)
    name = column.get('name', '')
    if column.get('html'):
        tree = html.fromstring(column['html'])
        if not name.strip() and columns and 'kanban-column-onhold' in tree.get('class', ''):
            marker = 'id="' + tree.get('id', '') + '"'
            for parent in columns.values():
                if parent['id'] != column['id'] and parent['board'] == column['board'] and marker in parent.get('html', ''):
                    return column_label(parent)
        titles = tree.xpath('.//h2[contains(@class,"kanban-column__title")]')
        if titles and name.strip() == titles[0].text_content().strip():
            for counter in titles[0].xpath('.//*[contains(@class,"kanban-column__cards-number")]'):
                counter.getparent().remove(counter)
            return ' '.join(titles[0].text_content().split())
    return name.strip()


def detail(tree, record, card, columns, state):
    from card_table import is_done, parent_columns
    identifier = state.get('column_id', card['column'])
    column = columns.get(identifier)
    if not column:
        return
    name = column_label(column, columns)
    parent = parent_columns(columns).get(identifier)
    bucket = record['bucket']
    column_url = '/6302022/buckets/' + bucket + '/card_tables/columns/' + (parent or identifier)
    for link in tree.xpath('//a[contains(@class,"perma-toolbar__breadcrumb") and contains(@href,"/card_tables/columns/")]'):
        link.set('href', column_url)
        link.set('title', name)
        for child in list(link):
            link.remove(child)
        link.text = name
    for content in tree.xpath('//*[contains(@class,"field-row--column")]/*[contains(@class,"field-row__content")]'):
        popups = content.xpath('./div[contains(@class,"popup-dropdown")]')
        if not popups:
            continue
        popup = popups[0]
        for label in popup.xpath('./span[contains(@class,"field-row__kanban-color-title")]'):
            popup.remove(label)
        old_done = content.xpath('./div[contains(@class,"card-perma-meta__done")]')
        if is_done(column):
            if old_done:
                marker = old_done[0]
            else:
                marker = etree.Element('div', {'class': 'card-perma-meta__done'})
                content.insert(0, marker)
                etree.SubElement(marker, 'span', {'class': 'field-row__kanban-color-title', 'style': '--recording-color: var(--recording-color-green);'})
            for label in marker.xpath('./span'):
                label.text = name
            if state.get('completed_at'):
                for previous in marker.xpath('./time'):
                    marker.remove(previous)
                instant = datetime.fromtimestamp(state['completed_at'], timezone.utc)
                etree.SubElement(marker, 'time', {'datetime': instant.isoformat(), 'data-local': 'time-or-date', 'title': instant.strftime('%B %d, %Y at %H:%M UTC')}).text = instant.strftime('%H:%M')
        else:
            for marker in old_done:
                content.remove(marker)
            label = etree.Element('span', {'class': 'field-row__kanban-color-title', 'tabindex': '-1', 'data-action': 'click->dialog#toggle:stop'})
            label.text = name + (', on hold' if parent else '')
            popup.insert(0, label)
    for menu in tree.xpath('//ul[@id="move-card-columns"]'):
        options = menu.xpath('./li')
        if not options:
            continue
        originals = {node.get('id', '').removeprefix('move_option_recording_'): node for node in options}
        prototype = options[0]
        for node in options:
            menu.remove(node)
        # Preserve the captured menu order, then append locally created columns.
        choices = list(originals) + [key for key in columns if key not in originals]
        parents = parent_columns(columns)
        choices = [nested for key in choices if key not in parents
                   for nested in [key] + [child for child in choices if parents.get(child) == key]]
        for key in choices:
            choice = columns.get(key)
            if not choice or choice.get('deleted') or choice['board'] != card['board']:
                continue
            from column_lifecycle import status as column_status
            if column_status(columns, key, parents) != 'active':
                continue
            source_key = '10398823195' if key in parents else html.fromstring(choice['html']).get('id', '').removeprefix('recording_') if choice.get('html') else key
            node = copy.deepcopy(originals.get(key, originals.get(source_key, prototype)))
            node.set('id', 'move_option_recording_' + key)
            node.set('aria-selected', str(key == identifier).lower())
            for form in node.xpath('.//form'):
                form.set('action', record['url'] + '/moves?column_id=' + key)
                # The breadcrumb is outside card-details. Complete navigation
                # must refresh it alongside the newly rendered column state.
                form.set('data-turbo-frame', '_top')
            for label in node.xpath('.//span[contains(@class,"truncate")]'):
                label.text = column_label(choice, columns)
            for button in node.xpath('.//button[@data-hotkey]'):
                if not is_done(choice):
                    button.attrib.pop('data-hotkey', None)
            if is_done(choice):
                node.xpath('.//button')[0].set('data-hotkey', 'd')
            menu.append(node)
