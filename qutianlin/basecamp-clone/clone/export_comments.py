"""Preserve the same retained discussion content in project downloads."""
import json
from datetime import datetime, timezone
from functools import lru_cache
from lxml import html
from comment_replies import ROOT, original, source_comments


@lru_cache(maxsize=128)
def source_total(route):
    path = ROOT / 'frontend/pages' / route.lstrip('/') / 'index.html'
    if not path.is_file(): return 0
    tree = html.fromstring(path.read_text())
    values = tree.xpath('//*[@data-source-comment-total]/@data-source-comment-total')
    return int(values[0]) if values else len(source_comments(route))


def discussion(c, account, record):
    comments = []
    total = 0
    if not record.get('is_new'):
        total = source_total(record['url'])
        for identifier in source_comments(record['url']):
            row = original(c, account, record, identifier)
            row.update(source=True, reply=None)
            comments.append(row)
    retained = len(comments)
    for row in c.execute('SELECT m.*,a.display_name FROM bc_comments m LEFT JOIN local_auth_accounts a ON a.account_id=m.author WHERE m.owner=? AND m.route=? ORDER BY m.created,m.id', (account['workspace_id'], record['url'])):
        comments.append({'id': row['id'], 'author': row['author'], 'name': row['display_name'] or 'Member',
                         'created': row['created'], 'timestamp': datetime.fromtimestamp(row['created'], timezone.utc).isoformat(),
                         'body': row['body'], 'source': False, 'reply': json.loads(row['reply']) if row['reply'] else None})
    return comments, {'source_total': total, 'source_retained': retained, 'total': total + len(comments) - retained}
