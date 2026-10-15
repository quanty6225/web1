import csv,io,json,re,time,secrets,math
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import Response
from backend.services import db,require_account,check_csrf,survey_owned,survey_data
from backend.survey_model import new_id

router=APIRouter()
KINDS={'multiple_choice','checkboxes','dropdown','star_rating','slider','ranking','matrix','matrix_dropdown','single_text','comment','multiple_text','date','contact','file','text','image','image_choice','nps','best_worst'}

def text(value,maximum=10000):
    value=str(value or '').strip()
    if len(value)>maximum:raise HTTPException(422,'The value is too long.')
    return value

def choices(values):
    if not isinstance(values,list) or len(values)>300:raise HTTPException(422,'Enter valid answer choices.')
    return [{'id':str(v.get('id') or new_id()),'label':text(v.get('label'),1000)} if isinstance(v,dict) else {'id':new_id(),'label':text(v,1000)} for v in values if (v.get('label') if isinstance(v,dict) else v)]

def question_payload(payload):
    if not isinstance(payload,dict):raise HTTPException(422,'Enter a valid question.')
    kind=payload.get('kind','multiple_choice')
    if kind not in KINDS:raise HTTPException(422,'Choose a question type.')
    title=text(payload.get('title'))
    if not title:raise HTTPException(422,'Enter your question.')
    options=payload.get('options',{})
    if not isinstance(options,dict):raise HTTPException(422,'Question options must be an object.')
    values=choices(payload.get('choices',[]))
    if kind in ('multiple_choice','checkboxes','dropdown','ranking','image_choice','best_worst','matrix','matrix_dropdown') and not values:raise HTTPException(422,'Enter an answer choice.')
    if kind in ('star_rating','slider'):
        try:low=float(options.get('min',1 if kind=='star_rating' else 0));high=float(options.get('max',5 if kind=='star_rating' else 100))
        except (ValueError,TypeError):raise HTTPException(422,'Enter a valid rating range.')
        if not math.isfinite(low) or not math.isfinite(high) or not 0<=low<high<=100000:raise HTTPException(422,'Enter a valid rating range.')
    return kind,title,values,bool(payload.get('required')),options

@router.get('/api/surveys')
def list_surveys(request:Request):
    owner=require_account(request)['account_id']
    with db() as c:
        query='SELECT s.*, (SELECT COUNT(*) FROM sm_responses r WHERE r.survey_id=s.id AND r.status="complete") response_count,(SELECT COUNT(*) FROM sm_questions q JOIN sm_pages p ON p.id=q.page_id WHERE p.survey_id=s.id) question_count FROM sm_surveys s WHERE s.owner=? AND s.deleted=0'
        params=[owner]
        if request.query_params.get('folder'):query+=' AND s.folder_id=?';params.append(request.query_params['folder'])
        if request.query_params.get('q'):query+=' AND s.title LIKE ?';params.append('%'+request.query_params['q']+'%')
        query+=' ORDER BY s.updated DESC'
        return {'surveys':[dict(x) for x in c.execute(query,params)],'folders':[dict(x) for x in c.execute('SELECT * FROM sm_folders WHERE owner=? ORDER BY name',(owner,))]}

@router.post('/api/folders')
async def create_folder(request:Request):
    check_csrf(request);owner=require_account(request)['account_id'];data=await request.json();name=text(data.get('name'),100)
    if not name:raise HTTPException(422,'Enter a folder name.')
    id=new_id()
    with db() as c:c.execute('INSERT INTO sm_folders VALUES (?,?,?,?)',(id,owner,name,int(time.time())))
    return {'id':id,'name':name}

@router.patch('/api/folders/{id}')
async def rename_folder(id:str,request:Request):
    check_csrf(request);owner=require_account(request)['account_id'];data=await request.json();name=text(data.get('name'),100)
    if not name:raise HTTPException(422,'Enter a folder name.')
    with db() as c:
        if c.execute('UPDATE sm_folders SET name=? WHERE id=? AND owner=?',(name,id,owner)).rowcount!=1:raise HTTPException(404,'Folder not found.')
    return {'ok':True}

@router.delete('/api/folders/{id}')
def delete_folder(id:str,request:Request):
    check_csrf(request);owner=require_account(request)['account_id']
    with db() as c:
        if c.execute('DELETE FROM sm_folders WHERE id=? AND owner=?',(id,owner)).rowcount!=1:raise HTTPException(404,'Folder not found.')
    return {'ok':True}

@router.post('/api/surveys')
async def create_survey(request:Request):
    check_csrf(request);owner=require_account(request)['account_id'];data=await request.json();id=new_id();page=new_id();now=int(time.time());title=text(data.get('title') or 'Untitled',250)
    pages=data.get('pages',[{'questions':data.get('questions',[])}])
    if not isinstance(pages,list) or not 1<=len(pages)<=100:raise HTTPException(422,'Enter between 1 and 100 survey pages.')
    if any(not isinstance(p,dict) or not isinstance(p.get('questions',[]),list) for p in pages):raise HTTPException(422,'Questions must be a list.')
    if sum(len(p.get('questions',[])) for p in pages)>100:raise HTTPException(422,'A survey can contain up to 100 questions.')
    with db() as c:
        profile=c.execute('SELECT preferences FROM sm_profiles WHERE owner=?',(owner,)).fetchone()
        preferences=json.loads(profile['preferences']) if profile else {}
        settings={'response_alerts':preferences.get('response_alerts',{}).get('new',True)}
        c.execute('INSERT INTO sm_surveys(id,owner,title,description,settings,created,updated) VALUES (?,?,?,?,?,?,?)',(id,owner,title,text(data.get('description')),json.dumps(settings),now,now))
        for page_position,source_page in enumerate(pages):
            page=new_id()
            c.execute('INSERT INTO sm_pages(id,survey_id,title,description,position) VALUES (?,?,?,?,?)',(page,id,text(source_page.get('title'),250),text(source_page.get('description')),page_position))
            for position,q in enumerate(source_page.get('questions',[])):
                kind,heading,values,required,options=question_payload(q)
                c.execute('INSERT INTO sm_questions VALUES (?,?,?,?,?,?,?,?)',(new_id(),page,kind,heading,json.dumps(values),required,json.dumps(options),position))
        return survey_data(c,id)

@router.get('/api/surveys/{id}')
def get_survey(id:str,request:Request):
    owner=require_account(request)['account_id']
    with db() as c:survey_owned(c,id,owner);return survey_data(c,id)

@router.patch('/api/surveys/{id}')
async def update_survey(id:str,request:Request):
    check_csrf(request);owner=require_account(request)['account_id'];data=await request.json()
    with db() as c:
        c.execute('BEGIN IMMEDIATE');old=survey_owned(c,id,owner)
        if 'version'in data and int(data['version'])!=old['version']:raise HTTPException(409,'This survey was updated in another window. Refresh it before saving.')
        changes={}
        for key in ('title','description'):
            if key in data:changes[key]=text(data[key],250 if key=='title' else 10000)
        if 'title'in changes and not changes['title']:raise HTTPException(422,'Enter a survey title.')
        for key in ('theme','settings'):
            if key in data:
                if not isinstance(data[key],dict):raise HTTPException(422,'Enter valid settings.')
                changes[key]=json.dumps(data[key])
        if 'folder_id'in data:
            folder=data['folder_id'] or None
            if folder and not c.execute('SELECT 1 FROM sm_folders WHERE id=? AND owner=?',(folder,owner)).fetchone():raise HTTPException(404,'Folder not found.')
            changes['folder_id']=folder
        if changes:
            c.execute('UPDATE sm_surveys SET '+','.join(k+'=?' for k in changes)+',updated=?,version=version+1 WHERE id=?',list(changes.values())+[int(time.time()),id])
        return survey_data(c,id)

@router.delete('/api/surveys/{id}')
def delete_survey(id:str,request:Request):
    check_csrf(request);owner=require_account(request)['account_id']
    with db() as c:
        survey_owned(c,id,owner);c.execute('UPDATE sm_surveys SET deleted=1,status="closed" WHERE id=?',(id,));c.execute('UPDATE sm_collectors SET status="closed" WHERE survey_id=?',(id,))
    return {'ok':True}

@router.post('/api/surveys/{id}/copy')
async def copy_survey(id:str,request:Request):
    check_csrf(request);owner=require_account(request)['account_id'];payload=await request.json();new=new_id();now=int(time.time())
    with db() as c:
        survey_owned(c,id,owner);original=survey_data(c,id)
        c.execute('INSERT INTO sm_surveys(id,owner,title,description,theme,settings,created,updated) VALUES (?,?,?,?,?,?,?,?)',(new,owner,text(payload.get('title') or original['title']+' (copy)',250),original['description'],json.dumps(original['theme']),json.dumps(original['settings']),now,now))
        media_urls={}
        for attachment in c.execute('SELECT * FROM sm_attachments WHERE survey_id=? AND collector_id IS NULL',(id,)).fetchall():
            attachment_id=new_id()
            c.execute('INSERT INTO sm_attachments VALUES (?,?,?,?,?,?,?,?,?)',(attachment_id,new,None,owner,attachment['name'],attachment['mime'],attachment['path'],attachment['size'],now))
            media_urls['/api/media/'+attachment['id']]='/api/media/'+attachment_id
        page_ids={p['id']:new_id() for p in original['pages']}
        for page in original['pages']:
            page_id=page_ids[page['id']];c.execute('INSERT INTO sm_pages VALUES (?,?,?,?,?,?)',(page_id,new,page['title'],page['description'],page['position'],'{}'))
            for q in page['questions']:
                if q['options'].get('url') in media_urls:q['options']['url']=media_urls[q['options']['url']]
                q['options']['skip']={key:page_ids.get(value,value) for key,value in q['options'].get('skip',{}).items()}
                c.execute('INSERT INTO sm_questions VALUES (?,?,?,?,?,?,?,?)',(new_id(),page_id,q['kind'],q['title'],json.dumps(q['choices']),q['required'],json.dumps(q['options']),q['position']))
        return survey_data(c,new)

@router.post('/api/surveys/{id}/pages')
async def add_page(id:str,request:Request):
    check_csrf(request);owner=require_account(request)['account_id'];payload=await request.json()
    with db() as c:
        survey_owned(c,id,owner);position=c.execute('SELECT COUNT(*) FROM sm_pages WHERE survey_id=?',(id,)).fetchone()[0]
        c.execute('INSERT INTO sm_pages VALUES (?,?,?,?,?,?)',(new_id(),id,text(payload.get('title'),250),text(payload.get('description')),position,'{}'))
        return survey_data(c,id)

@router.patch('/api/surveys/{id}/pages/{page_id}')
async def update_page(id:str,page_id:str,request:Request):
    check_csrf(request);owner=require_account(request)['account_id'];data=await request.json()
    with db() as c:
        survey_owned(c,id,owner);page=c.execute('SELECT * FROM sm_pages WHERE id=? AND survey_id=?',(page_id,id)).fetchone()
        if not page:raise HTTPException(404,'Page not found.')
        c.execute('UPDATE sm_pages SET title=?,description=?,logic=? WHERE id=?',(text(data.get('title',page['title']),250),text(data.get('description',page['description'])),json.dumps(data.get('logic',json.loads(page['logic']))),page_id))
        return survey_data(c,id)

@router.delete('/api/surveys/{id}/pages/{page_id}')
def delete_page(id:str,page_id:str,request:Request):
    check_csrf(request);owner=require_account(request)['account_id']
    with db() as c:
        survey_owned(c,id,owner)
        if c.execute('SELECT COUNT(*) FROM sm_pages WHERE survey_id=?',(id,)).fetchone()[0]<=1:raise HTTPException(422,'Keep at least one page in your survey.')
        c.execute('DELETE FROM sm_pages WHERE id=? AND survey_id=?',(page_id,id));return survey_data(c,id)

@router.post('/api/surveys/{id}/questions')
async def add_question(id:str,request:Request):
    check_csrf(request);owner=require_account(request)['account_id'];data=await request.json();kind,title,values,required,options=question_payload(data)
    with db() as c:
        survey_owned(c,id,owner);page_id=data.get('page_id')
        page=c.execute('SELECT * FROM sm_pages WHERE survey_id=?'+(' AND id=?' if page_id else '')+' ORDER BY position LIMIT 1',([id,page_id] if page_id else [id])).fetchone()
        if not page:raise HTTPException(404,'Page not found.')
        position=c.execute('SELECT COALESCE(MAX(position),-1)+1 FROM sm_questions WHERE page_id=?',(page['id'],)).fetchone()[0]
        c.execute('INSERT INTO sm_questions VALUES (?,?,?,?,?,?,?,?)',(new_id(),page['id'],kind,title,json.dumps(values),required,json.dumps(options),position));c.execute('UPDATE sm_surveys SET updated=?,version=version+1 WHERE id=?',(int(time.time()),id));return survey_data(c,id)

@router.put('/api/surveys/{id}/questions/{qid}')
async def update_question(id:str,qid:str,request:Request):
    check_csrf(request);owner=require_account(request)['account_id'];data=await request.json();kind,title,values,required,options=question_payload(data)
    with db() as c:
        survey_owned(c,id,owner)
        old=c.execute('SELECT q.* FROM sm_questions q JOIN sm_pages p ON p.id=q.page_id WHERE q.id=? AND p.survey_id=?',(qid,id)).fetchone()
        if not old:raise HTTPException(404,'Question not found.')
        page_id=data.get('page_id',old['page_id'])
        if not c.execute('SELECT 1 FROM sm_pages WHERE id=? AND survey_id=?',(page_id,id)).fetchone():raise HTTPException(404,'Page not found.')
        c.execute('UPDATE sm_questions SET page_id=?,kind=?,title=?,choices=?,required=?,options=? WHERE id=?',(page_id,kind,title,json.dumps(values),required,json.dumps(options),qid));c.execute('UPDATE sm_surveys SET updated=?,version=version+1 WHERE id=?',(int(time.time()),id));return survey_data(c,id)

@router.delete('/api/surveys/{id}/questions/{qid}')
def delete_question(id:str,qid:str,request:Request):
    check_csrf(request);owner=require_account(request)['account_id']
    with db() as c:
        survey_owned(c,id,owner)
        c.execute('DELETE FROM sm_questions WHERE id=? AND page_id IN (SELECT id FROM sm_pages WHERE survey_id=?)',(qid,id));c.execute('UPDATE sm_surveys SET updated=?,version=version+1 WHERE id=?',(int(time.time()),id));return survey_data(c,id)

@router.post('/api/surveys/{id}/reorder')
async def reorder(id:str,request:Request):
    check_csrf(request);owner=require_account(request)['account_id'];data=await request.json()
    with db() as c:
        survey_owned(c,id,owner)
        for page in data.get('pages',[]):
            if not c.execute('SELECT 1 FROM sm_pages WHERE id=? AND survey_id=?',(page['id'],id)).fetchone():raise HTTPException(404,'Page not found.')
            for position,qid in enumerate(page.get('questions',[])):
                if not c.execute('SELECT 1 FROM sm_questions q JOIN sm_pages p ON p.id=q.page_id WHERE q.id=? AND p.survey_id=?',(qid,id)).fetchone():raise HTTPException(404,'Question not found.')
                c.execute('UPDATE sm_questions SET page_id=?,position=? WHERE id=?',(page['id'],position,qid))
        return survey_data(c,id)

@router.get('/api/surveys/{id}/collectors')
def collectors(id:str,request:Request):
    owner=require_account(request)['account_id']
    with db() as c:
        survey_owned(c,id,owner);return {'collectors':[dict(x) for x in c.execute('SELECT c.*,(SELECT COUNT(*) FROM sm_responses r WHERE r.collector_id=c.id AND r.status="complete") response_count FROM sm_collectors c WHERE c.survey_id=? ORDER BY c.created DESC',(id,))]}

@router.post('/api/surveys/{id}/collectors')
async def create_collector(id:str,request:Request):
    check_csrf(request);owner=require_account(request)['account_id'];data=await request.json();kind=data.get('kind','weblink')
    if kind not in ('weblink','email','website','manual','kiosk'):raise HTTPException(422,'Choose a collection method.')
    with db() as c:
        survey_owned(c,id,owner)
        if not c.execute('SELECT 1 FROM sm_questions q JOIN sm_pages p ON p.id=q.page_id WHERE p.survey_id=?',(id,)).fetchone():raise HTTPException(422,'Add a question before publishing your survey.')
        collector=new_id();token=secrets.token_urlsafe(9)
        c.execute('INSERT INTO sm_collectors VALUES (?,?,?,?,?,?,?,?)',(collector,id,text(data.get('name') or 'Web link',100),kind,token,'open',json.dumps(data.get('options',{})),int(time.time())));c.execute('UPDATE sm_surveys SET status="open",updated=? WHERE id=?',(int(time.time()),id))
        return dict(c.execute('SELECT * FROM sm_collectors WHERE id=?',(collector,)).fetchone())

@router.patch('/api/surveys/{id}/collectors/{collector}')
async def edit_collector(id:str,collector:str,request:Request):
    check_csrf(request);owner=require_account(request)['account_id'];data=await request.json()
    with db() as c:
        survey_owned(c,id,owner);old=c.execute('SELECT * FROM sm_collectors WHERE id=? AND survey_id=?',(collector,id)).fetchone()
        if not old:raise HTTPException(404,'Collector not found.')
        status=data.get('status',old['status'])
        if status not in ('open','closed'):raise HTTPException(422,'Choose open or closed.')
        c.execute('UPDATE sm_collectors SET name=?,status=?,options=? WHERE id=?',(text(data.get('name',old['name']),100),status,json.dumps(data.get('options',json.loads(old['options']))),collector))
        c.execute('UPDATE sm_surveys SET status=? WHERE id=?',('open' if c.execute('SELECT 1 FROM sm_collectors WHERE survey_id=? AND status="open"',(id,)).fetchone() else 'closed',id));return {'ok':True}

@router.get('/api/respond/{token}')
def respondent_survey(token:str):
    with db() as c:
        collector=c.execute('SELECT * FROM sm_collectors WHERE token=?',(token,)).fetchone()
        if not collector:raise HTTPException(404,'Survey not found.')
        survey=survey_data(c,collector['survey_id'],public=True)
        if collector['status']!='open':raise HTTPException(410,'This survey is currently closed.')
        return {'survey':survey,'collector':{'name':collector['name'],'options':json.loads(collector['options'])}}

def active_questions(survey,answers):
    pages=survey['pages'];by_id={p['id']:i for i,p in enumerate(pages)};index=0;visited=set();result=[]
    while index<len(pages) and index not in visited:
        visited.add(index);page=pages[index];result.extend(page['questions']);target=None
        for q in page['questions']:
            rules=q['options'].get('skip',{})
            value=answers.get(q['id'])
            if isinstance(value,(str,int)) and str(value) in rules:target=rules[str(value)];break
        if target=='end':break
        index=by_id[target] if target in by_id else index+1
    return result

def validate_answers(survey,answers):
    if not isinstance(answers,dict):raise HTTPException(422,'Enter valid answers.')
    errors={};clean={}
    for q in active_questions(survey,answers):
        if q['kind'] in ('text','image'):continue
        value=answers.get(q['id']);empty=value is None or value=='' or value==[] or value=={}
        if empty:
            if q['required']:errors[q['id']]='This question requires an answer.'
            continue
        allowed={v['id'] if isinstance(v,dict) else v for v in q['choices']}
        if q['kind'] in ('multiple_choice','dropdown','image_choice') and (not isinstance(value,str) or value not in allowed):errors[q['id']]='Choose an available answer.'
        elif q['kind'] in ('checkboxes','ranking','best_worst'):
            if not isinstance(value,list) or any(not isinstance(v,str) or v not in allowed for v in value) or len(value)!=len(set(value)):errors[q['id']]='Choose valid answers.'
            elif q['kind']=='best_worst' and len(value)!=2:errors[q['id']]='Select one best and one different worst answer.'
            elif q['kind']=='ranking' and set(value)!=allowed:errors[q['id']]='Rank every answer choice.'
        elif q['kind'] in ('star_rating','slider','nps'):
            try:
                if isinstance(value,bool):raise ValueError()
                minimum=0 if q['kind'] in ('slider','nps') else 1;maximum=10 if q['kind']=='nps' else 100 if q['kind']=='slider' else 5
                number=float(value)
                if not math.isfinite(number) or not float(q['options'].get('min',minimum))<=number<=float(q['options'].get('max',maximum)):raise ValueError()
                if q['kind'] in ('nps','star_rating') and not number.is_integer():raise ValueError()
                value=number
            except (TypeError,ValueError):errors[q['id']]='Choose a value within the range.'
        elif q['kind'] in ('matrix','matrix_dropdown','multiple_text','contact'):
            if not isinstance(value,dict) or len(json.dumps(value))>20000:errors[q['id']]='Complete the fields in this question.'
            elif q['kind'] in ('matrix','matrix_dropdown'):
                rows=q['options'].get('rows',['Row 1','Row 2']);keys={str(i) for i in range(len(rows))}
                if any(str(k) not in keys or v not in allowed for k,v in value.items()) or q['required'] and set(value)!=keys:errors[q['id']]='Answer each row using an available choice.'
            else:
                rows=q['options'].get('rows') or (['Name','Company','Address','City','State','ZIP','Country','Email','Phone'] if q['kind']=='contact' else ['Field 1','Field 2'])
                keys={str(i) for i in range(len(rows))}
                if any(k not in keys or not isinstance(v,str) or len(v)>20000 for k,v in value.items()):errors[q['id']]='Complete the fields in this question.'
                elif q['required'] and any(not str(value.get(k,'')).strip() for k in keys):errors[q['id']]='Please complete every required field.'
        elif not isinstance(value,str) or len(value)>20000:errors[q['id']]='Enter a valid answer.'
        if q['options'].get('validation')=='email' and isinstance(value,str) and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',value):errors[q['id']]='Enter a valid email address.'
        if q['kind'] in ('checkboxes','multiple_choice'):
            labels={v['id']:v['label'] for v in q['choices']}
            selected=value if isinstance(value,list) else [value]
            if any(labels.get(v) in q['options'].get('exclusive_labels',[]) for v in selected if isinstance(v,str)) and len(selected)>1:errors[q['id']]='Select the exclusive answer by itself.'
            other=q['options'].get('other_label')
            if other and any(labels.get(v)==other for v in selected if isinstance(v,str)):
                other_value=answers.get(q['id']+'__other','')
                if not isinstance(other_value,str) or not other_value.strip() or len(other_value)>20000:errors[q['id']]='Please specify your other answer.'
                else:clean[q['id']+'__other']=other_value.strip()
        clean[q['id']]=value
    if errors:raise HTTPException(422,{'message':'Please check your answers.','fields':errors})
    return clean

@router.post('/api/respond/{token}')
async def submit_response(token:str,request:Request):
    check_csrf(request);data=await request.json();key=text(data.get('submission_key'),100)
    if len(key)<12:raise HTTPException(422,'Your response session has expired. Reload the survey.')
    with db() as c:
        c.execute('BEGIN IMMEDIATE');collector=c.execute('SELECT * FROM sm_collectors WHERE token=?',(token,)).fetchone()
        if not collector:raise HTTPException(404,'Survey not found.')
        existing=c.execute('SELECT id,status FROM sm_responses WHERE collector_id=? AND submission_key=?',(collector['id'],key)).fetchone()
        if existing and existing['status']=='complete':return {'submitted':True,'response_id':existing['id'],'duplicate':True}
        if collector['status']!='open':raise HTTPException(410,'This survey is currently closed.')
        survey=survey_data(c,collector['survey_id']);answers=validate_answers(survey,data.get('answers',{}));now=int(time.time());id=existing['id'] if existing else new_id()
        for question in active_questions(survey,answers):
            if question['kind']=='file' and answers.get(question['id']):
                attachment=c.execute('SELECT 1 FROM sm_attachments WHERE id=? AND collector_id=?',(answers[question['id']],collector['id'])).fetchone()
                if not attachment:raise HTTPException(422,'Upload a file for this survey.')
        if existing:c.execute('UPDATE sm_responses SET answers=?,status="complete",completed=? WHERE id=?',(json.dumps(answers),now,id))
        else:c.execute('INSERT INTO sm_responses VALUES (?,?,?,?,?,?,?,?)',(id,survey['id'],collector['id'],key,json.dumps(answers),'complete',now,now))
        return {'submitted':True,'response_id':id,'message':survey['settings'].get('thank_you','Thank you for completing this survey.')}

def results(connection,id,filters=None):
    survey=survey_data(connection,id);responses=[dict(x) for x in connection.execute('SELECT * FROM sm_responses WHERE survey_id=? AND status="complete" ORDER BY completed DESC',(id,))]
    for row in responses:row['answers']=json.loads(row['answers']);row.pop('submission_key',None)
    total_unfiltered=len(responses);filters=filters or {}
    if filters.get('collector'):responses=[r for r in responses if r['collector_id']==filters['collector']]
    for key,comparison in [('from',lambda date,bound:date>=bound),('to',lambda date,bound:date<=bound)]:
        if filters.get(key):
            try:bound=time.mktime(time.strptime(filters[key],'%Y-%m-%d'))+(86399 if key=='to' else 0)
            except ValueError:raise HTTPException(422,'Enter a valid date.')
            responses=[r for r in responses if comparison(r['completed'],bound)]
    if filters.get('question') and filters.get('answer'):
        qid=filters['question'];answer=filters['answer']
        def matches(value):
            if isinstance(value,list):return answer in value
            if isinstance(value,(int,float)) and not isinstance(value,bool):
                try:return math.isfinite(float(answer)) and value==float(answer)
                except (ValueError,TypeError):return False
            return str(value)==answer
        responses=[r for r in responses if qid in r['answers'] and matches(r['answers'][qid])]
    questions=[]
    for page in survey['pages']:
        for q in page['questions']:
            values=[r['answers'][q['id']] for r in responses if q['id'] in r['answers']];counts={}
            for value in values:
                for item in value if isinstance(value,list) else [value]:
                    key=json.dumps(item,ensure_ascii=False) if isinstance(item,dict) else str(item);counts[key]=counts.get(key,0)+1
            numeric=[float(x) for x in values if isinstance(x,(int,float))]
            summary={'question':q,'answered':len(values),'skipped':len(responses)-len(values),'counts':counts,'values':values,'average':sum(numeric)/len(numeric) if numeric else None}
            if q['kind']=='nps':
                promoters=sum(v>=9 for v in numeric);detractors=sum(v<=6 for v in numeric)
                summary['nps']={'promoters':promoters,'passives':len(numeric)-promoters-detractors,'detractors':detractors,'score':round((promoters-detractors)/len(numeric)*100,2) if numeric else None}
            questions.append(summary)
    return {'survey':survey,'total':len(responses),'total_unfiltered':total_unfiltered,'questions':questions,'responses':responses}

@router.get('/api/surveys/{id}/results')
def survey_results(id:str,request:Request):
    owner=require_account(request)['account_id']
    with db() as c:survey_owned(c,id,owner);return results(c,id,dict(request.query_params))

@router.delete('/api/surveys/{id}/responses/{response_id}')
def delete_response(id:str,response_id:str,request:Request):
    check_csrf(request);owner=require_account(request)['account_id']
    with db() as c:survey_owned(c,id,owner);c.execute('DELETE FROM sm_responses WHERE id=? AND survey_id=?',(response_id,id))
    return {'ok':True}

@router.get('/api/surveys/{id}/export.csv')
def export_csv(id:str,request:Request):
    owner=require_account(request)['account_id']
    with db() as c:survey_owned(c,id,owner);data=results(c,id,dict(request.query_params))
    out=io.StringIO();writer=csv.writer(out);questions=[row['question'] for row in data['questions']]
    writer.writerow(['Response ID','Completed']+[("'"+q['title'] if q['title'].startswith(('=','+','-','@')) else q['title']) for q in questions])
    for response in data['responses']:
        row=[response['id'],time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime(response['completed']))]
        for q in questions:
            value=response['answers'].get(q['id'],'');labels={str(x['id']):x['label'] for x in q['choices'] if isinstance(x,dict)}
            if isinstance(value,list):value='; '.join(labels.get(str(v),str(v)) for v in value)
            elif isinstance(value,dict):value=json.dumps(value,ensure_ascii=False)
            else:value=labels.get(str(value),str(value))
            if response['answers'].get(q['id']+'__other'):value+=': '+response['answers'][q['id']+'__other']
            if value.startswith(('=','+','-','@')):value="'"+value
            row.append(value)
        writer.writerow(row)
    return Response('\ufeff'+out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="survey-responses.csv"'})
