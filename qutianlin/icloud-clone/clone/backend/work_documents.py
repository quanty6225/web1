"""Local editable iWork documents; native Apple file conversion is not implied."""
import csv
import io
import json
import time
import uuid
import re
import base64
from html import escape
from html.parser import HTMLParser

APPS = ('pages', 'numbers', 'keynote')

def image_data(value):
    if value == '':return ''
    if not isinstance(value,str) or len(value)>1200000:raise ValueError('Choose an image smaller than 900 KB.')
    match=re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)',value)
    if not match:raise ValueError('Choose a PNG, JPEG or WebP image.')
    try:data=base64.b64decode(match[2],validate=True)
    except ValueError:raise ValueError('Image is invalid.')
    valid=(match[1]=='png' and data.startswith(b'\x89PNG\r\n\x1a\n')) or (match[1]=='jpeg' and data.startswith(b'\xff\xd8\xff')) or (match[1]=='webp' and data.startswith(b'RIFF') and data[8:12]==b'WEBP')
    if not valid:raise ValueError('Image is invalid.')
    return value

def safe_style(value):
    result=[]
    for part in value.split(';'):
        key,_,v=part.partition(':');key=key.strip().lower();v=v.strip()
        allowed=(key=='text-align' and v in ('left','center','right','justify')) or (key=='font-size' and re.fullmatch(r'(?:[8-9]|[1-6][0-9]|7[0-2])(?:px|pt)',v)) or (key in ('color','background-color') and re.fullmatch(r'#[0-9a-fA-F]{3,8}|rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\)',v)) or (key=='font-family' and v.strip('"\'') in ('Arial','Georgia','Times New Roman','Courier New','sans-serif','serif')) or (key=='font-weight' and v in ('bold','normal','700')) or (key=='font-style' and v in ('italic','normal')) or (key=='text-decoration' and v in ('underline','line-through','none'))
        if allowed:result.append(key+':'+v)
    return ';'.join(result)


class RichText(HTMLParser):
    tags = {'p', 'div', 'br', 'b', 'strong', 'i', 'em', 'u', 's', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'blockquote','span','table','thead','tbody','tr','td','th','hr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []

    def handle_starttag(self, tag, attrs):
        attrs={k:v or "" for k,v in attrs}
        if tag=='img':
            try:src=image_data(attrs.get('src',''))
            except ValueError:return
            if src:self.output.append('<img src="'+src+'" alt="'+escape(attrs.get('alt',''),quote=True)+'">')
            return
        if tag=='font':
            tag='span';style=attrs.get('style','')
            for attr,prop in [('color','color'),('face','font-family')]:
                if attrs.get(attr):style+=';'+prop+':'+attrs[attr]
            if attrs.get('size') in ('1','2','3','4','5','6','7'):style+=';font-size:'+str([10,13,16,18,24,32,48][int(attrs['size'])-1])+'px'
            attrs['style']=style
        if tag in self.tags:
            style=safe_style(attrs.get('style',''))
            self.output.append('<' + tag + (' style="'+escape(style,quote=True)+'"' if style else '')+'>')

    def handle_endtag(self, tag):
        if tag=='font':tag='span'
        if tag in self.tags and tag != 'br':
            self.output.append('</' + tag + '>')

    def handle_data(self, data):
        self.output.append(escape(data))


def text(value, limit, label):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(label + ' is too long or invalid.')
    return value


def clean_body(app, body):
    if not isinstance(body, dict):
        raise ValueError('Document content is invalid.')
    if len(json.dumps(body)) > 2000000:
        raise ValueError('This document exceeds the local editor size limit.')
    if app == 'pages':
        parser = RichText()
        parser.feed(text(body.get('html'), 1600000, 'Document'))
        parser.close()
        return {'html': ''.join(parser.output)}
    if app == 'numbers':
        sheets = body.get('sheets')
        if not isinstance(sheets, list) or not 1 <= len(sheets) <= 10:
            raise ValueError('Keep between 1 and 10 sheets.')
        result = []
        for sheet in sheets:
            if not isinstance(sheet, dict):
                raise ValueError('Sheet is invalid.')
            cells = sheet.get('cells')
            if not isinstance(cells, list) or not 1 <= len(cells) <= 200:
                raise ValueError('Keep between 1 and 200 rows.')
            width = len(cells[0]) if isinstance(cells[0], list) else 0
            if not 1 <= width <= 26 or any(not isinstance(row, list) or len(row) != width for row in cells):
                raise ValueError('Keep between 1 and 26 columns in each row.')
            result.append({'name': text(sheet.get('name'), 100, 'Sheet name'),
                           'cells': [[text(cell, 2000, 'Cell') for cell in row] for row in cells]})
            if 'formats' in sheet:
                formats=sheet['formats']
                if not isinstance(formats,dict) or len(formats)>5200:raise ValueError('Cell formats are invalid.')
                clean={}
                for key,style in formats.items():
                    match=re.fullmatch(r'([A-Z])([1-9][0-9]*)',key)
                    if not match or ord(match[1])-65>=width or int(match[2])>len(cells) or not isinstance(style,dict):raise ValueError('Cell format is invalid.')
                    if style.get('number','general') not in ('general','number','currency','percent'):raise ValueError('Choose a number format.')
                    if type(style.get('bold',False)) is not bool:raise ValueError('Cell format is invalid.')
                    if not isinstance(style.get('color','#222222'),str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',style.get('color','#222222')):raise ValueError('Choose a text color.')
                    clean[key]={'number':style.get('number','general'),'bold':style.get('bold',False),'color':style.get('color','#222222')}
                result[-1]['formats']=clean
            if 'chart' in sheet:
                if sheet['chart'] not in ('none','bar','line'):raise ValueError('Choose a chart type.')
                result[-1]['chart']=sheet['chart']
        return {'sheets': result}
    slides = body.get('slides')
    if not isinstance(slides, list) or not 1 <= len(slides) <= 100:
        raise ValueError('Keep between 1 and 100 slides.')
    result = []
    for slide in slides:
        if not isinstance(slide, dict):
            raise ValueError('Slide is invalid.')
        result.append({key: text(slide.get(key, ''), limit, key) for key, limit in
                       [('title', 500), ('body', 20000), ('notes', 10000)]})
        if 'image' in slide:result[-1]['image']=image_data(slide['image'])
        if 'background' in slide:
            if not isinstance(slide['background'],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',slide['background']):raise ValueError('Choose a valid slide color.')
            result[-1]['background']=slide['background']
        for key,choices in [('layout',('title-body','title-only','image-left')),('transition',('none','fade','slide'))]:
            if key in slide:
                if slide[key] not in choices:raise ValueError('Choose a valid '+key+'.')
                result[-1][key]=slide[key]
    return {'slides': result}


def initial(app):
    if app == 'pages':
        return {'html': '<p><br></p>'}
    if app == 'numbers':
        return {'sheets': [{'name': 'Sheet 1', 'cells': [[''] * 5 for _ in range(12)]}]}
    return {'slides': [{'title': '', 'body': '', 'notes': ''}]}


def load(db, owner, identifier):
    row = db.execute("SELECT payload FROM icloud_entities WHERE owner=? AND kind='documents' AND id=?", (owner, identifier)).fetchone()
    item = json.loads(row[0]) if row else None
    if not item or item.get('deleted') or not item.get('_editor'):
        raise LookupError('This editable document is unavailable. Recover deleted documents first.')
    return item

def migrate(db):
    db.execute("""CREATE TABLE IF NOT EXISTS icloud_work_versions (
      owner TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'documents',id TEXT NOT NULL,
      revision INTEGER NOT NULL,name TEXT NOT NULL,body TEXT NOT NULL,created INTEGER NOT NULL,
      PRIMARY KEY(owner,id,revision),
      FOREIGN KEY(owner,kind,id) REFERENCES icloud_entities(owner,kind,id) ON DELETE CASCADE)""")

def remember(db,owner,item):
    db.execute('INSERT OR IGNORE INTO icloud_work_versions VALUES (?,?,?,?,?,?,?)',(owner,'documents',item['id'],item['_editor_revision'],item['name'],json.dumps(item['_editor']),int(time.time())))
    db.execute('DELETE FROM icloud_work_versions WHERE owner=? AND id=? AND revision NOT IN (SELECT revision FROM icloud_work_versions WHERE owner=? AND id=? ORDER BY revision DESC LIMIT 20)',(owner,item['id'],owner,item['id']))

def versions(db,owner,identifier):
    load(db,owner,identifier)
    return [dict(row) for row in db.execute('SELECT revision,name,created FROM icloud_work_versions WHERE owner=? AND id=? ORDER BY revision DESC',(owner,identifier))]

def restore(db,owner,identifier,data):
    if not isinstance(data,dict) or type(data.get('version')) is not int:raise ValueError('Choose a saved version.')
    item=load(db,owner,identifier)
    row=db.execute('SELECT name,body FROM icloud_work_versions WHERE owner=? AND id=? AND revision=?',(owner,identifier,data['version'])).fetchone()
    if not row:raise LookupError('Version not found.')
    return save(db,owner,identifier,{'name':row['name'],'body':json.loads(row['body']),'revision':data.get('revision')})


def create(db, owner, data):
    if not isinstance(data, dict) or data.get('app') not in APPS:
        raise ValueError('Choose a document application.')
    app = data['app']
    name = text(data.get('name', 'Untitled'), 255, 'Name').strip()
    if not name or any(ord(c) < 32 for c in name):
        raise ValueError('Enter a valid document name.')
    parent = data.get('parent')
    if parent is not None:
        if not isinstance(parent, str):
            raise ValueError('Choose a folder in this application.')
        row = db.execute("SELECT payload FROM icloud_entities WHERE owner=? AND kind='documents' AND id=?", (owner, parent)).fetchone()
        folder = json.loads(row[0]) if row else {}
        if folder.get('app') != app or not folder.get('folder') or folder.get('deleted'):
            raise ValueError('Choose a folder in this application.')
    now = int(time.time())
    item = {'id': str(uuid.uuid4()), 'app': app, 'name': name, 'parent': parent,
            '_editor': initial(app), '_editor_revision': 1, 'modified': time.strftime('%Y-%m-%d'), 'order': -now}
    db.execute('INSERT INTO icloud_entities VALUES (?,?,?,?,?)', (owner, 'documents', item['id'], json.dumps(item), now))
    return item


def save(db, owner, identifier, data):
    if not isinstance(data, dict):
        raise ValueError('Document content is invalid.')
    item = load(db, owner, identifier)
    if type(data.get('revision')) is not int or data['revision'] != item['_editor_revision']:
        raise FileExistsError('This document changed in another window. Download your unsaved copy, then reload.')
    name = text(data.get('name'), 255, 'Name').strip()
    if not name or any(ord(c) < 32 for c in name):
        raise ValueError('Enter a valid document name.')
    body=clean_body(item['app'],data.get('body'))
    remember(db,owner,item)
    item.update(name=name, _editor=body,
                _editor_revision=item['_editor_revision'] + 1, modified=time.strftime('%Y-%m-%d'))
    db.execute("UPDATE icloud_entities SET payload=?,updated_at=? WHERE owner=? AND kind='documents' AND id=?",
               (json.dumps(item), int(time.time()), owner, identifier))
    return item


def export(item, sheet=0):
    body = item['_editor']
    if item['app'] == 'numbers':
        if not 0 <= sheet < len(body['sheets']):
            raise ValueError('Sheet not found.')
        output = io.StringIO(newline='')
        csv.writer(output).writerows(body['sheets'][sheet]['cells'])
        return output.getvalue(), 'text/csv', '.csv'
    if item['app'] == 'pages':
        content = body['html']
    else:
        content = ''.join('<section style="background:'+s.get('background','#ffffff')+'"><h1>' + escape(s['title']) + '</h1>'+('<img src="'+s['image']+'" alt="">' if s.get('image') else '')+'<p>' + escape(s['body']).replace('\n', '<br>') + '</p></section>' for s in body['slides'])
    html = '<!doctype html><html><head><meta charset="utf-8"><title>' + escape(item['name']) + '</title><style>body{font:18px system-ui;max-width:900px;margin:40px auto;padding:24px}section{min-height:75vh;page-break-after:always;padding:24px}p{white-space:pre-wrap}img{max-width:100%;max-height:65vh}table{border-collapse:collapse;width:100%}td,th{border:1px solid #888;padding:8px}</style></head><body>' + content + '</body></html>'
    return html, 'text/html', '.html'
