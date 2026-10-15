"""Account-owned contact lists and vCard import/export, without remote fetches."""
import base64,binascii,json,re,quopri
from backend.file_lifecycle import records


def text(value):
    return re.sub(r'\\([nN,;\\])',lambda m:'\n' if m[1].lower()=='n' else m[1],value)


def escape(value):
    return str(value or '').replace('\\','\\\\').replace('\r\n','\n').replace('\r','\n').replace('\n','\\n').replace(';','\\;').replace(',','\\,')


def components(value):
    return [text(part) for part in split_escaped(value,';')]


def split_escaped(value,separator):
    parts=[];start=0;escaped=False
    for index,char in enumerate(value):
        if escaped:escaped=False;continue
        if char=='\\':escaped=True
        elif char==separator:parts.append(value[start:index]);start=index+1
    parts.append(value[start:]);return parts


def parse(content):
    if not isinstance(content,str) or len(content.encode('utf-8'))>2_000_000:
        raise ValueError('Choose a vCard smaller than 2 MB.')
    lines=[]
    for line in content.lstrip('\ufeff').replace('\r\n','\n').replace('\r','\n').split('\n'):
        if line.startswith((' ','\t')) and lines:lines[-1]+=line[1:]
        elif lines and 'ENCODING=QUOTED-PRINTABLE' in lines[-1].upper() and lines[-1].endswith('='):lines[-1]=lines[-1][:-1]+line
        elif line:lines.append(line)
    cards=[];card=None;properties=[]
    for line in lines:
        if line.upper()=='BEGIN:VCARD':
            if card is not None:raise ValueError('Invalid vCard.')
            card={'phones':[],'emails':[],'addresses':[],'urls':[],'related':[],'extra_vcard':[]};properties=[];continue
        if line.upper()=='END:VCARD':
            if card is None:raise ValueError('Invalid vCard.')
            labels={group:text(value).removeprefix('_$!<').removesuffix('>!$_') for group,key,params,value in properties if key=='X-ABLABEL'}
            version=next((v for g,k,p,v in properties if k=='VERSION'),None)
            if version not in ('2.1','3.0','4.0'):raise ValueError('Unsupported vCard version.')
            for group,key,params,value in properties:
                opts={}
                for param in params:
                    k,sep,v=param.partition('=');opts[k.upper()]=v.strip('"') if sep else k.lower()
                if opts.get('ENCODING','').upper()=='QUOTED-PRINTABLE':
                    try:value=quopri.decodestring(value).decode(opts.get('CHARSET','utf-8'))
                    except (LookupError,UnicodeError):raise ValueError('Invalid vCard text encoding.')
                label=labels.get(group) or opts.get('TYPE') or next((p.lower() for p in params if '=' not in p),'other')
                if key=='FN':card['name']=text(value)
                elif key=='N':
                    parts=components(value)+['']*5
                    card.update(dict(zip(('last_name','first_name','middle_name','prefix','suffix'),parts)))
                elif key in ('TEL','EMAIL','URL','X-ABRELATEDNAMES'):
                    field={'TEL':'phones','EMAIL':'emails','URL':'urls','X-ABRELATEDNAMES':'related'}[key]
                    card[field].append({'label':label,'value':text(value.removeprefix('tel:') if key=='TEL' else value)})
                elif key=='ADR':
                    parts=components(value)+['']*7
                    card['addresses'].append({'label':label,**dict(zip(('po_box','extended','street','city','region','postal_code','country'),parts))})
                elif key=='ORG':
                    parts=components(value);card['company']=parts[0];card['department']='; '.join(parts[1:])
                elif key in ('NOTE','NICKNAME','BDAY','TITLE','X-PHONETIC-FIRST-NAME','X-PHONETIC-LAST-NAME'):
                    card[{'NOTE':'note','NICKNAME':'nickname','BDAY':'birthday','TITLE':'job_title','X-PHONETIC-FIRST-NAME':'phonetic_first','X-PHONETIC-LAST-NAME':'phonetic_last'}[key]]=text(value)
                elif key not in ('VERSION','UID','REV','PRODID','X-ABLABEL'):
                    card['extra_vcard'].append({'group':group,'key':key,'params':params,'value':value})
            for photo in [p for p in card['extra_vcard'] if p['key']=='PHOTO']:
                value=photo['value'];kind=next((p.split('=',1)[1].upper() for p in photo['params'] if p.upper().startswith('TYPE=')),'JPEG')
                if value.startswith('data:image/'):
                    candidate=value
                elif any(p.upper() in ('ENCODING=B','ENCODING=BASE64') for p in photo['params']):
                    candidate='data:image/'+{'JPEG':'jpeg','JPG':'jpeg','PNG':'png','WEBP':'webp'}.get(kind,'unknown')+';base64,'+value
                else:continue
                try:validate_avatar(candidate)
                except ValueError:continue
                card['avatar']=candidate;card['extra_vcard'].remove(photo);break
            if not card.get('name'):card['name']=' '.join(card.get(k,'') for k in ('prefix','first_name','middle_name','last_name','suffix')).strip() or card.get('company','')
            if not card.get('name'):raise ValueError('A contact must have a name or company.')
            cards.append(card);card=None
            if len(cards)>1000:raise ValueError('Choose a vCard with at most 1000 contacts.')
            continue
        if card is None:raise ValueError('Invalid vCard.')
        # Colons inside quoted parameter values do not delimit the property.
        match=re.match(r'^((?:[^:"]|"[^"]*")*):(.*)$',line)
        if not match:raise ValueError('Invalid vCard property.')
        head,value=match.groups();parts=re.findall(r'(?:[^;"]|"[^"]*")+',head)
        group,_,key=parts[0].rpartition('.');key=key.upper()
        if not re.fullmatch(r'[A-Z0-9-]+',key):raise ValueError('Invalid vCard property.')
        properties.append((group,key,parts[1:],value))
    if card is not None or not cards:raise ValueError('No complete contacts found in this vCard.')
    return cards


def folded(line):
    result=[];current='';size=0
    for char in line:
        width=len(char.encode('utf-8'))
        if size+width>75:result.append(current);current=' ';size=1
        current+=char;size+=width
    result.append(current);return '\r\n'.join(result)


def export(cards):
    result=[]
    for card in cards:
        lines=['BEGIN:VCARD','VERSION:3.0','FN:'+escape(card['name']),
               'N:'+';'.join(escape(card.get(k,'')) for k in ('last_name','first_name','middle_name','prefix','suffix'))]
        if card.get('company') or card.get('department'):lines.append('ORG:'+escape(card.get('company'))+';'+escape(card.get('department')))
        for field,key in (('note','NOTE'),('nickname','NICKNAME'),('birthday','BDAY'),('job_title','TITLE'),('phonetic_first','X-PHONETIC-FIRST-NAME'),('phonetic_last','X-PHONETIC-LAST-NAME')):
            if card.get(field):lines.append(key+':'+escape(card[field]))
        if card.get('avatar'):
            mime,encoded=card['avatar'].split(';base64,',1)
            lines.append('PHOTO;ENCODING=b;TYPE='+mime.split('/')[-1].upper()+':'+encoded)
        group_index=0
        for field,key in (('phones','TEL'),('emails','EMAIL'),('urls','URL'),('addresses','ADR'),('related','X-ABRELATEDNAMES')):
            for item in card.get(field,[]):
                group_index+=1;group='item'+str(group_index)
                value=';'.join(escape(item.get(k)) for k in ('po_box','extended','street','city','region','postal_code','country')) if field=='addresses' else escape(item.get('value'))
                label=item.get('label','other');standard=label.upper() if re.fullmatch(r'[A-Za-z]+(?:,[A-Za-z]+)*',label) else 'OTHER'
                lines.extend([f'{group}.{key};TYPE={standard}:{value}',f'{group}.X-ABLabel:'+escape(label)])
        for item in card.get('extra_vcard',[]):
            # Preserve unknown properties as data; their URIs are never fetched.
            if not isinstance(item,dict):continue
            key=str(item.get('key',''));params=item.get('params',[]);value=str(item.get('value',''))
            if not re.fullmatch(r'[A-Z0-9-]+',key) or key in ('BEGIN','END','VERSION'):continue
            if not isinstance(params,list) or any(not isinstance(p,str) or '\n' in p or '\r' in p for p in params):continue
            if '\r' in value or '\n' in value:continue
            lines.append(';'.join([key,*params])+':'+value)
        lines.append('END:VCARD');result.extend(folded(line) for line in lines)
    return '\r\n'.join(result)+'\r\n'


def validate_avatar(value):
    if not isinstance(value,str) or len(value)>150000:raise ValueError('Choose a smaller contact photo.')
    match=re.fullmatch(r'data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)',value)
    if not match:raise ValueError('Choose a JPEG, PNG, or WebP photo.')
    try:raw=base64.b64decode(match[2],validate=True)
    except binascii.Error:raise ValueError('Invalid contact photo.')
    valid=(match[1]=='png' and raw.startswith(b'\x89PNG\r\n\x1a\n') and len(raw)>24) or (match[1]=='jpeg' and raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9')) or (match[1]=='webp' and raw.startswith(b'RIFF') and raw[8:12]==b'WEBP')
    if not valid:raise ValueError('Invalid contact photo.')


def validate_contact(data,previous,now):
    for key in ('name','first_name','last_name','middle_name','prefix','suffix','company','department','note','nickname','birthday','job_title','phonetic_first','phonetic_last'):
        if key in data and not isinstance(data[key],str):raise ValueError('Invalid contact field.')
    data['name']=data.get('name','').strip() or ' '.join(data.get(k,'') for k in ('first_name','middle_name','last_name')).strip() or data.get('company','').strip()
    if not data['name']:raise ValueError('Enter a contact name or company.')
    if data.get('avatar'):validate_avatar(data['avatar'])
    elif 'avatar' in data:data['avatar']=''
    for key in ('phones','emails','urls','addresses','related'):
        values=data.get(key,[])
        if not isinstance(values,list) or len(values)>100 or any(not isinstance(v,dict) or any(not isinstance(s,str) for s in v.values()) for v in values):raise ValueError('Invalid contact field.')
    data['created_at']=previous.get('created_at',now)


def validate_list(db,owner,identifier,data):
    if identifier=='all':raise ValueError('All Contacts cannot be modified.')
    if not isinstance(data.get('name'),str) or not data['name'].strip():raise ValueError('Enter a list name.')
    data['name']=data['name'].strip()
    previous=records(db,owner,'contact_lists').get(identifier,{})
    ids=data.get('contacts',previous.get('contacts',[]))
    if not isinstance(ids,list) or any(not isinstance(i,str) for i in ids):raise ValueError('Choose valid contacts.')
    if not set(ids)<=records(db,owner,'contacts').keys():raise ValueError('Contact not found.')
    data['contacts']=list(dict.fromkeys(ids))


def remove_references(db,owner,identifiers,now):
    for item in records(db,owner,'contact_lists').values():
        ids=item.get('contacts',[])
        if set(identifiers).intersection(ids):
            item['contacts']=[i for i in ids if i not in identifiers]
            db.execute("UPDATE icloud_entities SET payload=?,updated_at=? WHERE owner=? AND kind='contact_lists' AND id=?",(json.dumps(item),now,owner,item['id']))
    row=db.execute("SELECT payload FROM icloud_entities WHERE owner=? AND kind='settings' AND id='contacts'",(owner,)).fetchone()
    if row:
        settings=json.loads(row[0])
        if settings.get('my_card') in identifiers:
            settings.pop('my_card')
            db.execute("UPDATE icloud_entities SET payload=?,updated_at=? WHERE owner=? AND kind='settings' AND id='contacts'",(json.dumps(settings),now,owner))


def selected(db,owner,ids):
    if not isinstance(ids,list) or not ids or len(ids)>5000 or any(not isinstance(i,str) for i in ids):raise ValueError('Select contacts to continue.')
    data=records(db,owner,'contacts')
    if not set(ids)<=data.keys():raise LookupError('Contact not found.')
    return [data[i] for i in dict.fromkeys(ids)]


def action(db,owner,data,now):
    cards=selected(db,owner,data.get('ids'));ids=[c['id'] for c in cards]
    operation=data.get('action');list_id=data.get('list')
    if operation not in ('add','remove','delete'):raise ValueError('Choose a contact action.')
    if operation in ('add','remove'):
        if not isinstance(list_id,str):raise ValueError('Choose a contact list.')
        item=records(db,owner,'contact_lists').get(list_id)
        if not item:raise LookupError('List not found.')
        members=item.get('contacts',[])
        item['contacts']=list(dict.fromkeys(members+ids)) if operation=='add' else [i for i in members if i not in ids]
        db.execute("UPDATE icloud_entities SET payload=?,updated_at=? WHERE owner=? AND kind='contact_lists' AND id=?",(json.dumps(item),now,owner,list_id))
    else:
        remove_references(db,owner,ids,now)
        db.executemany("DELETE FROM icloud_entities WHERE owner=? AND kind='contacts' AND id=?",[(owner,i) for i in ids])
