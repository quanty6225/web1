"""Bounded OOXML text extraction for the local Office text-editing equivalent.

Never rewrites the package. Formatting, calculations and embedded objects are
not rendered; the caller stores edited text separately from original bytes.
"""
import io
import posixpath
import re
import zipfile
import zlib
from xml.etree import ElementTree as ET

MAX_XML = 4 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_TEXT = 2_000_000
OFFICE_KINDS = {'document', 'spreadsheet', 'presentation', 'notebook'}
TEXT_KINDS = OFFICE_KINDS | {'text', 'markdown'}


def original_office(file):
    body = bytes(file.get('content') or b'')
    return file['kind'] in OFFICE_KINDS and body.startswith((b'PK', b'\xd0\xcf\x11\xe0', b'\xe4\x52\x5c\x7b'))


def local_name(tag):
    return tag.rsplit('}', 1)[-1]


class Package:
    def __init__(self, body):
        self.archive = zipfile.ZipFile(io.BytesIO(body) if isinstance(body,(bytes,bytearray)) else body)
        entries = self.archive.infolist()
        if len(entries) > 2000 or sum(e.file_size for e in entries) > MAX_TOTAL:
            raise ValueError('Package exceeds extraction limits')
        if len({e.filename for e in entries}) != len(entries) or any(e.flag_bits & 1 for e in entries):
            raise ValueError('Ambiguous or encrypted package')
        self.cache = {}

    def xml(self, name):
        if name not in self.cache:
            entry = self.archive.getinfo(name)
            if entry.file_size > MAX_XML:
                raise ValueError('XML exceeds extraction limits')
            body = self.archive.read(entry)
            # Also reject UTF-16/32 encoded declarations; no entity expansion.
            guard = body.replace(b'\x00', b'').upper()
            if b'<!DOCTYPE' in guard or b'<!ENTITY' in guard:
                raise ValueError('DTD is not supported')
            self.cache[name] = ET.fromstring(body)
        return self.cache[name]

    def related(self, source):
        directory, filename = posixpath.split(source)
        rels = self.xml(posixpath.join(directory, '_rels', filename + '.rels'))
        result = {}
        for rel in rels:
            if rel.get('TargetMode') == 'External':
                continue
            target = rel.get('Target', '')
            path = posixpath.normpath(posixpath.join(directory, target)) if not target.startswith('/') else target[1:]
            if not target or path.startswith('../') or ':' in path or '\\' in path:
                continue
            result[rel.get('Id')] = path
        return result

    def ordered(self, source, element):
        relationships = self.related(source)
        for node in self.xml(source).iter():
            if local_name(node.tag) == element:
                rid = next((v for k, v in node.attrib.items() if k.endswith('}id')), None)
                if rid not in relationships:
                    raise ValueError('Missing internal relationship')
                yield node, relationships[rid]


def paragraphs(root):
    lines = []
    length = 0
    for para in root.iter():
        if local_name(para.tag) != 'p':
            continue
        parts = []
        for node in para.iter():
            tag = local_name(node.tag)
            if tag == 't': parts.append(node.text or '')
            elif tag == 'tab': parts.append('\t')
            elif tag in {'br', 'cr'}: parts.append('\n')
        line = ''.join(parts)
        length += len(line) + 1
        if length > MAX_TEXT: raise ValueError('Text exceeds extraction limits')
        lines.append(line)
    return '\n'.join(lines)


def spreadsheet(package):
    shared = []
    if 'xl/sharedStrings.xml' in package.archive.namelist():
        shared = [''.join(n.text or '' for n in si.iter() if local_name(n.tag) == 't') for si in package.xml('xl/sharedStrings.xml')]
    sections = []
    length = 0
    for sheet, path in package.ordered('xl/workbook.xml', 'sheet'):
        lines = [sheet.get('name', '')]
        for row in package.xml(path).iter():
            if local_name(row.tag) != 'row': continue
            cells = []
            row_length = 0
            for cell in row:
                if local_name(cell.tag) != 'c': continue
                address = re.fullmatch(r'([A-Z]{1,3})[1-9][0-9]*', cell.get('r', ''))
                column = 0
                if address:
                    for char in address[1]: column = column * 26 + ord(char) - 64
                else: column = len(cells) + 1
                if not 1 <= column <= 16384 or column <= len(cells):
                    raise ValueError('Invalid cell order')
                values = {local_name(n.tag): n for n in cell}
                value = values.get('v')
                text = value.text or '' if value is not None else ''
                if cell.get('t') == 's':
                    index = int(text)
                    if not 0 <= index < len(shared): raise ValueError('Invalid shared string')
                    text = shared[index]
                elif cell.get('t') == 'inlineStr':
                    text = ''.join(n.text or '' for n in cell.iter() if local_name(n.tag) == 't')
                elif value is None and 'f' in values: text = '=' + (values['f'].text or '')
                row_length += len(text) + column - len(cells)
                if length + row_length > MAX_TEXT: raise ValueError('Text exceeds extraction limits')
                cells.extend([''] * (column - len(cells) - 1))
                cells.append(text)
            line = '\t'.join(cells)
            length += len(line) + 1
            if length > MAX_TEXT: raise ValueError('Text exceeds extraction limits')
            lines.append(line)
        sections.append('\n'.join(lines))
    return '\n\n'.join(sections)


def extract_text(body, kind):
    package = None
    try:
        package = Package(body)
        if kind == 'document': text = paragraphs(package.xml('word/document.xml'))
        elif kind == 'spreadsheet': text = spreadsheet(package)
        elif kind == 'presentation':
            sections = []
            length = 0
            for _, path in package.ordered('ppt/presentation.xml', 'sldId'):
                section = paragraphs(package.xml(path))
                length += len(section) + 2
                if length > MAX_TEXT: raise ValueError('Text exceeds extraction limits')
                sections.append(section)
            text = '\n\n'.join(sections)
        else: return None
        return text if len(text) <= MAX_TEXT else None
    except (ValueError, KeyError, zipfile.BadZipFile, ET.ParseError, RuntimeError, NotImplementedError, OSError, OverflowError, EOFError, zlib.error):
        return None
    finally:
        if package is not None: package.archive.close()
