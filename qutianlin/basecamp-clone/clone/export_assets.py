"""Embed locally stored rich-content files in an offline project archive."""
from pathlib import Path
from urllib.parse import urlsplit
from lxml import html

ROOT = Path(__file__).parent


class Assets:
    def __init__(self, archive, connection, owner, data_root):
        self.archive = archive
        self.connection = connection
        self.owner = owner
        self.data_root = Path(data_root)
        self.saved = set()

    def local(self, value):
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc: return value
        parts = parsed.path.split('/')
        path = None
        if parsed.path.startswith('/static/assets/') and len(parts) == 4 and parts[3] not in ('', '.', '..'):
            path = ROOT / 'static/assets' / parts[3]
            name = 'assets/' + parts[3]
        elif parsed.path.startswith('/files/') and len(parts) == 4:
            file = self.connection.execute('SELECT id,filename FROM bc_files WHERE id=? AND owner=? AND uploaded=1', (parts[2], self.owner)).fetchone()
            if file:
                path = self.data_root / 'uploads' / file['id']
                name = 'assets/' + file['id'] + '-' + Path(file['filename']).name
        if path is None or not path.is_file(): return value
        if name not in self.saved:
            self.archive.write(path, name)
            self.saved.add(name)
        return '../' + name + ('#' + parsed.fragment if parsed.fragment else '')

    def render(self, markup):
        tree = html.document_fromstring(markup)
        for node in tree.xpath('//*[@src or @href]'):
            for key in ('src', 'href'):
                if node.get(key): node.set(key, self.local(node.get(key)))
        return html.tostring(tree, encoding='unicode', doctype='<!doctype html>')
