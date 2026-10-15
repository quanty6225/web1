"""Owned reminder lists, validated details, completion and atomic deletion."""
import calendar,json,re,secrets
from datetime import date,timedelta

PRIORITIES=('None','Low','Medium','High')
REPEATS=('Never Repeat','Every Day','Every Week','Every 2 Weeks','Every Month','Every Year')


def rows(db,owner,kind):
    return {r[0]:json.loads(r[1]) for r in db.execute('SELECT id,payload FROM icloud_entities WHERE owner=? AND kind=?',(owner,kind))}


def save(db,owner,kind,item,now):
    db.execute('INSERT INTO icloud_entities VALUES (?,?,?,?,?) ON CONFLICT(owner,kind,id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',
        (owner,kind,item['id'],json.dumps(item),now))


def validate_list(data,previous):
    name=data.get('name',previous.get('name',''));color=data.get('color',previous.get('color','#ed7846'))
    if not isinstance(name,str) or not name.strip() or len(name)>255:raise ValueError('Enter a list name.')
    if not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color):raise ValueError('Choose a list color.')
    data.update(name=name.strip(),color=color.lower())


def validate(db,owner,data,previous,now):
    lists=rows(db,owner,'lists');target=data.get('list',previous.get('list'))
    if not isinstance(target,str) or target not in lists:raise ValueError('Choose one of your reminder lists.')
    title=data.get('title',previous.get('title',''));notes=data.get('notes',previous.get('notes',''))
    if not isinstance(title,str) or not title.strip():raise ValueError('Enter a reminder.')
    if len(title)>1000:raise ValueError('Reminders must contain at most 1000 characters.')
    if not isinstance(notes,str) or len(notes)>10000:raise ValueError('Notes must contain at most 10000 characters.')
    completed=data.get('completed',previous.get('completed',False))
    if not isinstance(completed,bool):raise ValueError('Invalid completion state.')
    due=data.get('due',previous.get('due','')) or '';due_time=data.get('due_time',previous.get('due_time','')) or ''
    if not isinstance(due,str) or not isinstance(due_time,str):raise ValueError('Enter a valid reminder date and time.')
    if due:
        try:parsed=date.fromisoformat(due)
        except ValueError:raise ValueError('Enter a valid reminder date.')
        if parsed.isoformat()!=due:raise ValueError('Enter a valid reminder date.')
        if due_time and not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',due_time):raise ValueError('Enter a valid reminder time.')
    else:due_time=''
    priority=data.get('priority',previous.get('priority','None'));repeat=data.get('repeat',previous.get('repeat','Never Repeat'))
    if priority not in PRIORITIES:raise ValueError('Choose a reminder priority.')
    if repeat not in REPEATS or repeat!='Never Repeat' and not due:raise ValueError('Choose a date before repeating a reminder.')
    order=previous.get('order') if target==previous.get('list') else None
    if order is None:
        collection=sorted([v for v in rows(db,owner,'reminders').values() if v.get('list')==target],key=lambda r:r.get('order',0))
        after=data.pop('after',None)
        if after is not None:
            if not isinstance(after,str) or not any(v['id']==after for v in collection):raise ValueError('Reminder not found in this list.')
            index=next(i for i,v in enumerate(collection) if v['id']==after)
            # Rebalance on insertion instead of accumulating floating precision.
            for i,entry in enumerate(collection):
                entry['order']=(i+1+(i>index))*1024;save(db,owner,'reminders',entry,now)
            order=(index+2)*1024
        else:order=max([v.get('order',0) for v in collection]+[0])+1024
    else:data.pop('after',None)
    origin=previous.get('_repeat_origin') if due==previous.get('due') and repeat==previous.get('repeat') else due
    data.update(title=title.strip(),notes=notes,list=target,due=due,due_time=due_time,priority=priority,repeat=repeat,completed=completed,order=order,_repeat_origin=origin or due)
    data.pop('_next_id',None)
    if previous.get('_next_id'):data['_next_id']=previous['_next_id']
    data.pop('completed_at',None)
    if completed:data['completed_at']=previous.get('completed_at',now) if previous.get('completed') else now


def next_date(item):
    current=date.fromisoformat(item['due']);origin=date.fromisoformat(item.get('_repeat_origin') or item['due']);repeat=item['repeat']
    try:
        if repeat in ('Every Day','Every Week','Every 2 Weeks'):
            result=current+timedelta(days={'Every Day':1,'Every Week':7,'Every 2 Weeks':14}[repeat])
        else:
            year=current.year+(repeat=='Every Year');month=current.month+(repeat=='Every Month')
            if month==13:year+=1;month=1
            result=date(year,month,min(origin.day,calendar.monthrange(year,month)[1]))
    except (ValueError,OverflowError):raise ValueError('The next reminder date is outside the supported range.')
    return result.isoformat()


def repeat_after_completion(db,owner,data,previous,now):
    if not data['completed'] or previous.get('completed') or data['repeat']=='Never Repeat' or data.get('_next_id'):return
    generated={**data,'id':secrets.token_hex(16),'completed':False,'due':next_date(data)}
    generated.pop('completed_at',None)
    generated['order']=max([v.get('order',0) for v in rows(db,owner,'reminders').values() if v.get('list')==data['list']]+[0])+1024
    data['_next_id']=generated['id'];save(db,owner,'reminders',generated,now)


def delete(db,owner,kind,identifier,now):
    collection=rows(db,owner,kind)
    if identifier not in collection:raise LookupError('Item not found.')
    targets=[(kind,identifier)]
    if kind=='lists':targets.extend(('reminders',r['id']) for r in rows(db,owner,'reminders').values() if r.get('list')==identifier)
    for target_kind,key in targets:
        db.execute('INSERT OR IGNORE INTO icloud_entity_tombstones VALUES (?,?,?,?)',(owner,target_kind,key,now))
        db.execute('DELETE FROM icloud_entities WHERE owner=? AND kind=? AND id=?',(owner,target_kind,key))


def clear_completed(db,owner,list_id,now):
    if not isinstance(list_id,str) or list_id not in rows(db,owner,'lists'):raise LookupError('List not found.')
    targets=[r['id'] for r in rows(db,owner,'reminders').values() if r.get('list')==list_id and r.get('completed')]
    for key in targets:delete(db,owner,'reminders',key,now)
    return len(targets)
