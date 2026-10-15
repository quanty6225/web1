"""Record CRUD using source forms, source detail shells, and owner-isolated state."""
import json,re,secrets,time
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote,urlsplit
from lxml import html,etree
from fastapi import HTTPException
from card_table import DATA
from local_render import safe_rich_text
ROOT=Path(__file__).parent
PREFIX={'todos':'todo','messages':'message','documents':'document','schedule_entries':'schedule_entry','card_tables/cards':'kanban_card','todolists':'todolist','subtasks':'subtask','google_documents':'google_document','uploads':'upload','vaults':'vault','cloud_files':'cloud_file'}
TITLE={'todos':'content','messages':'subject','documents':'title','schedule_entries':'summary','card_tables/cards':'title','todolists':'name','subtasks':'title','google_documents':'title','uploads':'base_name','vaults':'title','cloud_files':'title'}
BODY={'todos':'description','messages':'content','documents':'content','schedule_entries':'description','card_tables/cards':'content','todolists':'description','subtasks':'description','google_documents':'description','uploads':'description','vaults':'description','cloud_files':'description'}
PREFIX['card_tables/columns']='kanban_column'
TITLE['card_tables/columns']='name'
BODY['card_tables/columns']='description'

def metadata(connection,owner,identifier):
    from trash import erased
    if erased(connection,owner,identifier):return None
    row=connection.execute('SELECT * FROM bc_records WHERE id=? AND owner=?',(identifier,owner)).fetchone()
    if row:
        data=json.loads(row['data'])
        if data.get('url'):return {**data,'id':identifier,'title':row['title'],'body':row['body'],'parent':row['parent'],'is_new':True}
    if identifier in DATA['records']:return DATA['records'][identifier]
    from column_watching import record as column_record
    return column_record(connection,owner,identifier)

def fields_for(connection,owner,record):
    fields=dict(record.get('fields',{}))
    row=connection.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="record"',(owner,record['url'])).fetchone()
    if row:fields.update(json.loads(row['payload']))
    from trash import erased
    if erased(connection,owner,record['id']):fields['_record_status']='erased'
    return fields

def text_value(value):
    return html.fragment_fromstring(str(value or ''),create_parent='div').text_content().strip()

def changes(kind,payload):
    prefix=PREFIX[kind];result={k:v for k,v in payload.items() if k.startswith(prefix+'[') or k in ['participants','category_id','notify','status']}
    body_key=prefix+'['+BODY[kind]+']'
    if body_key in result:result[body_key]=safe_rich_text(str(result[body_key]))
    title_key=prefix+'['+TITLE[kind]+']'
    if title_key in result:
        result[title_key]=text_value(result[title_key])
        if not result[title_key]:raise HTTPException(422,'Please enter a title.')
    if kind in ['google_documents','cloud_files'] and prefix+'[url]' in result:
        value=str(result[prefix+'[url]'])
        if not (value.startswith('/external?target=') or urlsplit(value).scheme in ['https','http']):raise HTTPException(422,'Enter a valid link beginning with https:// or http://.')
    return result

def mutate(connection,owner,path,payload,method,referer,account=None):
    match=re.fullmatch(r'/6302022/buckets/(\d+)/(?:recordings/)?(\d+)/status/(active|archived|trashed)',path)
    if match:
        connection.execute('BEGIN IMMEDIATE')
        if method not in ('PUT','POST'):raise HTTPException(405,'Use PUT to change item status.')
        record=metadata(connection,owner,match[2])
        if not record or record['bucket']!=match[1]:raise HTTPException(404,'Record not found')
        if record['kind']=='card_tables/columns':
            from column_lifecycle import validate_change
            validate_change(connection,owner,record)
        state=fields_for(connection,owner,record)
        from trash import preserve_stamp
        preserve_stamp(connection,owner,record,state)
        previous_status=state.get('_record_status','active');changed=previous_status!=match[3]
        if changed:
            if record['kind']=='card_tables/columns':
                from column_lifecycle import transition_order
                transition_order(connection,owner,record,previous_status,match[3])
            state.update(_status_at=time.time(),_status_by=account['account_id'] if account else owner)
        state['_record_status']=match[3]
        connection.execute('INSERT OR REPLACE INTO bc_mutations VALUES(?,?,?,?,?)',(owner,record['url'],'record',json.dumps(state),int(time.time())))
        column_change=record['kind']=='card_tables/columns'
        if column_change and changed and account:
            from activity_search import emit
            action=match[3] if match[3]!='active' else 'unarchived' if previous_status=='archived' else 'restored'
            emit(connection,account,record['url'],record['title'],action)
        return {'redirect':record['parent'] if match[3]=='trashed' and not column_change else record['url'],'record':record,'activity_handled':column_change}
    match=re.fullmatch(r'/6302022/buckets/(\d+)/(todos|messages|documents|schedule_entries|card_tables/cards|todolists|subtasks|google_documents|uploads|vaults|cloud_files)/(\d+)',path)
    if match:
        connection.execute('BEGIN IMMEDIATE')
        record=metadata(connection,owner,match[3])
        if not record:raise HTTPException(404,'Record not found')
        if record['url']!=path:raise HTTPException(404,'Record not found')
        state=fields_for(connection,owner,record)
        from trash import preserve_stamp
        preserve_stamp(connection,owner,record,state)
        previous=dict(state);state.update(changes(record['kind'],payload))
        from record_attachments import track
        track(connection,account,record['kind'],state,previous)
        if record['kind'] in ['todos','subtasks','card_tables/cards']:
            from task_fields import validate
            validate(state,record['kind'])
            if PREFIX[record['kind']]+'[assignees]' in payload:
                from task_fields import record_assignments
                record_assignments(connection,account,record['kind'],state,previous,record['url'])
            from task_notifications import validate_completion_people
            validate_completion_people(connection,account,record['kind'],state,payload,record['url'])
        if record['kind']=='schedule_entries' and method!='DELETE':
            from calendar_view import validate
            validate(state)
        if method=='DELETE':
            if state.get('_record_status')!='trashed':state.update(_status_at=time.time(),_status_by=account['account_id'] if account else owner)
            state['_record_status']='trashed'
        connection.execute('INSERT OR REPLACE INTO bc_mutations VALUES(?,?,?,?,?)',(owner,path,'record',json.dumps(state),int(time.time())))
        from task_notifications import assignment_changed
        notified=assignment_changed(connection,account,record,previous) if method!='DELETE' else False
        return {'redirect':record['parent'] if method=='DELETE' else path,'record':record,'activity_handled':notified}
    match=re.fullmatch(r'/6302022/buckets/(\d+)/(.*?)(todos|messages|documents|entries|cards|todolists|subtasks|google_documents|vaults|cloud_files)$',path)
    if not match:return None
    connection.execute('BEGIN IMMEDIATE')
    bucket,container,collection=match.groups();kind='schedule_entries' if collection=='entries' else 'card_tables/cards' if collection=='cards' else collection
    if kind not in PREFIX:return None
    state=changes(kind,payload);prefix=PREFIX[kind];state.setdefault(prefix+'['+BODY[kind]+']','');title=state.get(prefix+'['+TITLE[kind]+']','')
    if not title:raise HTTPException(422,'Please enter a title.')
    from record_attachments import track
    track(connection,account,kind,state,{})
    if kind in ['todos','subtasks','card_tables/cards']:
        from task_fields import validate
        validate(state,kind)
        from task_fields import record_assignments
        record_assignments(connection,account,kind,state,{},path)
        from task_notifications import validate_completion_people
        validate_completion_people(connection,account,kind,state,payload,path)
    if kind=='schedule_entries':
        from calendar_view import validate
        validate(state)
    prototype=next((r for r in DATA['records'].values() if r['kind']==kind and r['bucket']==bucket),next((r for r in DATA['records'].values() if r['kind']==kind),None))
    if not prototype and kind=='cloud_files':prototype=next(r for r in DATA['records'].values() if r['kind']=='google_documents')
    if not prototype:return None
    parent=path.rsplit('/',1)[0] if container else prototype['parent']
    if kind=='subtasks':
        recording=metadata(connection,owner,parent.rsplit('/',1)[-1])
        if recording:parent=recording['url']
    if kind=='todos' and payload.get('todo[parent_id]'):parent=f'/6302022/buckets/{bucket}/todolists/'+str(payload['todo[parent_id]'])
    if kind=='todolists' and payload.get('todolist[parent_id]'):parent=f'/6302022/buckets/{bucket}/todosets/'+str(payload['todolist[parent_id]'])
    if kind=='card_tables/cards':
        column=parent.rsplit('/',1)[-1]
        from card_table import columns_for
        columns=columns_for(connection,owner)
        destination=columns.get(column)
        if not destination or destination.get('deleted') or destination['board'].split('/')[3]!=bucket:
            raise HTTPException(404,'Column not found')
        from column_lifecycle import require_active
        require_active(columns,column)
        state['_column_id']=column;parent=destination['board']
    identifier=str(900000000000+secrets.randbelow(99999999999));url=f'/6302022/buckets/{bucket}/{kind}/{identifier}';body=state.get(prefix+'['+BODY[kind]+']','')
    data={'url':url,'kind':kind,'bucket':bucket,'fields':state,'prototype':prototype['id'],'created':time.time(),'is_new':True,'author':account['account_id'] if account else owner}
    connection.execute('INSERT INTO bc_records VALUES(?,?,?,?,?,?,?,?)',(identifier,owner,parent,kind,title,body,json.dumps(data),int(time.time())))
    record={**data,'id':identifier,'title':title,'parent':parent}
    from task_notifications import assignment_changed
    from column_watching import audience as column_audience
    watchers=column_audience(connection,account,state['_column_id']) if account and kind=='card_tables/cards' and state.get('_column_id') else set()
    notified=assignment_changed(connection,account,record,{},action='posted',additional_recipients=watchers)
    if watchers and not notified:
        from activity_search import emit
        emit(connection,account,url,title,'posted',watchers);notified=True
    return {'redirect':parent if kind=='vaults' else url,'record':record,'activity_handled':notified}

@lru_cache(maxsize=256)
def bookmark_reference(template):
    tree=html.fromstring((ROOT/'frontend/pages'/template).read_bytes())
    frames=tree.xpath('//turbo-frame[starts-with(@id,"bookmark_quick_toggle_recording_")]/@src')
    return frames[0].removesuffix('/quick_toggle') if frames else None

def dynamic_info(connection,owner,path,routes):
    bookmark=re.fullmatch(r'/6302022/my/bookmarks/local-(\d+)/quick_toggle',path)
    if bookmark:
        record=metadata(connection,owner,bookmark[1])
        if not record or not record.get('is_new'):raise HTTPException(404,'Bookmark item not found')
        if record['kind']=='card_tables/columns':
            from card_table import dynamic_info as column_info
            source=column_info(connection,owner,record['url'],routes)['bookmark_source']
            prototype={'id':source['id']};reference=source['reference']
        else:
            prototype=DATA['records'][record['prototype']];reference=bookmark_reference(prototype['template'])
        info=routes.get(reference+'/quick_toggle') if reference else None
        if not info:raise HTTPException(404,'Bookmark control not found')
        return {**info,'component':True,'local_record':record,'substitutions':{prototype['id']:record['id'],reference:path.removesuffix('/quick_toggle')}}
    match=re.fullmatch(r'(/6302022/buckets/\d+/(?:todos|messages|documents|schedule_entries|card_tables/cards|todolists|subtasks|google_documents|uploads|vaults|cloud_files)/(\d+))(/edit)?',path)
    if not match:return None
    record=metadata(connection,owner,match[2])
    if not record or not record.get('is_new'):return None
    if record['url']!=match[1]:raise HTTPException(404,'Record not found')
    prototype=DATA['records'][record['prototype']];source=prototype['url']+(match[3] or '');info=routes.get(source)
    if not info and match[3]:
        alternative=next((r for r in DATA['records'].values() if r['kind']==record['kind'] and routes.get(r['url']+'/edit')),None)
        if alternative:prototype=alternative;info=routes[prototype['url']+'/edit']
    if not info:return None
    substitutions={prototype['id']:record['id'],prototype['bucket']:record['bucket']}
    reference=bookmark_reference(prototype['template'])
    if reference:substitutions[reference]='/6302022/my/bookmarks/local-'+record['id']
    if record['kind']=='cloud_files':substitutions.update({'/google_documents/':'/cloud_files/','google_document[':'cloud_file['})
    old_parent=prototype['parent'].rsplit('/',1)[-1];new_parent=record['parent'].rsplit('/',1)[-1]
    if old_parent.isdigit() and new_parent.isdigit() and old_parent!=prototype['bucket']:substitutions[old_parent]=new_parent
    return {**info,'substitutions':substitutions,'local_record':record}

def put_rich(element,value):
    for child in list(element):element.remove(child)
    fragment=html.fragment_fromstring(safe_rich_text(str(value)),create_parent='div');element.text=fragment.text
    for child in fragment:element.append(child)

def apply_fields(tree,action,fields):
    for form in tree.xpath('//form[@action]'):
        if form.get('action','').split('?')[0]!=action:continue
        for element in form.xpath('.//*[@name]'):
            key=element.get('name')
            if key not in fields:continue
            value=fields[key]
            if element.tag=='select':
                for option in element.xpath('.//option'):
                    option.attrib.pop('selected',None)
                    if option.get('value') in (value if isinstance(value,list) else [str(value)]):option.set('selected','selected')
            elif element.get('type') in ['checkbox','radio']:
                element.attrib.pop('checked',None)
                if element.get('value','on') in (value if isinstance(value,list) else [str(value)]):element.set('checked','checked')
            elif element.tag in ['input','textarea','lexxy-editor','bc-date-picker'] and element.get('type') not in ['password','file']:
                element.set('value',str(value))
                if element.tag=='textarea':element.text=str(value)

def render(tree,path,owner,connection,name):
    records=dict(DATA['records'])
    for row in connection.execute('SELECT * FROM bc_records WHERE owner=?',(owner,)):
        record=metadata(connection,owner,row['id'])
        if record:records[record['id']]=record
    for record in records.values():
        state=fields_for(connection,owner,record);kind=record['kind'];prefix=PREFIX[kind];title_key=prefix+'['+TITLE[kind]+']';body_key=prefix+'['+BODY[kind]+']';title=state.get(title_key,record['title']);url=record['url'];identifier=record['id'];status=state.get('_record_status','active')
        modified=connection.execute('SELECT 1 FROM bc_mutations WHERE owner=? AND route=? AND kind="record"',(owner,url)).fetchone()
        if not modified and not record.get('is_new') and status!='erased':continue
        apply_fields(tree,url,state)
        for link in tree.xpath('//a[@href]'):
            if link.get('href','').split('?')[0]!=url:continue
            if status!='active' and path!=url:
                container=next((a for a in link.iterancestors() if a.tag in ['article','li','tr'] or a.get('data-recording-id')==identifier),None)
                if container is not None and container.getparent() is not None:container.getparent().remove(container)
                else:link.getparent().remove(link)
            else:
                headers=link.xpath('.//h3|.//h2')
                if headers:headers[0].text=title
                elif not link.xpath('.//img'):link.text=title
        if path==url:
            for document_title in tree.xpath('//head/title'):document_title.text=title
            article=tree.xpath('//article[@data-recording-id="'+identifier+'"]') or tree.xpath('//article[contains(@class,"recordable")]')
            headings=(article[0].xpath('.//h1') if article else []) or tree.xpath('//h1[contains(@class,"perma-header__title")]')
            if headings:
                target=next(iter(headings[0].xpath('.//a')),headings[0]);target.text=title
                for child in list(target):target.remove(child)
            if article and body_key in state:
                bodies=article[0].xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," formatted_content ") and not(self::lexxy-editor)]')
                target=bodies[0] if bodies else etree.SubElement(article[0],'div',{'class':'formatted_content document-style-content'})
                put_rich(target,state[body_key])
            if kind in ['google_documents','cloud_files'] and article:
                target_url=state.get(prefix+'[url]','')
                if target_url:
                    target_url=target_url if target_url.startswith('/external?') else '/external?target='+quote(target_url,safe='')
                    for link in article[0].xpath('.//a[starts-with(@href,"/external?")]'):
                        link.set('href',target_url)
                        if kind=='cloud_files' and 'View on Google' in link.text_content():link.text='Open linked file'
            if record.get('is_new') and not record.get('relocated_source'):
                from record_attribution import render as render_attribution
                render_attribution(tree,connection,owner,record)
                if kind in ['vaults','todolists']:
                    for container in tree.xpath('//*[starts-with(@id,"vaultables_recording_")]|//ul[contains(@class,"todos")]'):
                        for child in list(container):container.remove(child)
                for source_comment in tree.xpath('//*[@data-comment]'):
                    if source_comment.getparent() is not None:source_comment.getparent().remove(source_comment)
                for entry in tree.xpath('//*[@data-source-comment-total]'):entry.set('data-source-comment-total','0')
            if status!='active':
                targets=tree.xpath('//main');banner=etree.Element('p',{'role':'status','class':'recording-status-notice'});banner.text='This item is '+status+'.';targets[0].insert(0,banner)
        if record.get('is_new') and kind not in ['card_tables/cards','schedule_entries'] and path.rstrip('/')==record['parent'].rstrip('/') and status=='active':
            if kind=='todos':
                targets=tree.xpath('//ul[contains(@class,"todos remaining")]')
                sample=next(iter(tree.xpath('//li[@data-behavior and contains(@data-behavior,"todo")]')),None)
                if targets and sample is None:
                    seed=next(r for r in DATA['records'].values() if r['kind']=='todos')
                    source=html.fromstring((ROOT/'frontend/pages'/DATA['records'][seed['parent'].rsplit('/',1)[-1]]['template']).read_text())
                    sample=next(iter(source.xpath('//li[@data-recording-id="'+seed['id']+'"]')),None)
                if targets and sample is not None:
                    old=sample.get('data-recording-id');node=html.fromstring(html.tostring(sample,encoding='unicode').replace(old,identifier).replace('/buckets/49234166/','/buckets/'+record['bucket']+'/'));node.set('data-local-record',identifier)
                    for link in node.xpath('.//a[@href="'+url+'"]'):link.text=title
                    for field in node.xpath('.//input[@type="checkbox"]'):field.attrib.pop('checked',None);field.set('aria-label',title)
                    for detail in node.xpath('.//span[contains(@class,"task-details")]'):
                        for child in list(detail):detail.remove(child)
                    targets[0].append(node);continue
            if kind=='messages':
                from record_attribution import creator
                author=creator(connection,owner,record)
                targets=tree.xpath('//ul[contains(@class,"article-list")]')
                if targets:
                    node=etree.SubElement(targets[0],'li',{'class':'article-list__item','data-local-record':identifier,'data-quick-find-target':'searchable'})
                    if author['id']:etree.SubElement(node,'img',{'class':'avatar article-list__avatar','src':'/api/avatar.svg?person='+author['id'],'alt':author['name']})
                    link=etree.SubElement(node,'a',{'href':url,'class':'article-list__link'});etree.SubElement(link,'h2',{'class':'article-list__title'}).text=title
                    content=etree.SubElement(link,'div',{'class':'article-list__content'});etree.SubElement(content,'span',{'class':'meta-dot'}).text=author['name'];etree.SubElement(content,'span',{'class':'meta-dot'}).text=text_value(state.get(body_key,''))[:280];continue
            targets=tree.xpath('//*[starts-with(@id,"vaultables_recording_")]') if kind in ['uploads','documents','google_documents','vaults','cloud_files'] else []
            targets=targets or tree.xpath('//main')
            if targets:
                node=etree.SubElement(targets[0],'article',{'class':'vaultable-tile image-grid__item' if kind in ['uploads','documents','google_documents','vaults','cloud_files'] else 'recordable local-created-record','data-local-record':identifier})
                link=etree.SubElement(node,'a',{'href':url,'class':'local-new-item'});link.text=title
    return tree
