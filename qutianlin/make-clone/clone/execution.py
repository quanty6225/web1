"""Bounded, deterministic local execution over a stream of data bundles."""
import json,re,time,math
from datetime import datetime,timezone

MAX_BUNDLES=100
MAX_OPERATIONS=200
FILTER_OPERATORS=frozenset(['Equal to','Not equal to','Contains','Does not contain','Starts with','Ends with','Greater than','Greater than or equal to','Less than','Less than or equal to','Exists','Does not exist','Array contains','Array does not contain','Datetime equal to','Datetime not equal to','Later than','Later than or equal to','Earlier than','Earlier than or equal to'])

def decode_json(value):
 def invalid_number(value):raise ValueError('JSON cannot contain NaN or Infinity')
 return json.loads(value,parse_constant=invalid_number)

def map_value(value,bundle):
 if not isinstance(value,str):return value
 def lookup(key):
  result=bundle
  for part in key.split('.'):
   if isinstance(result,dict) and part in result:result=result[part]
   elif isinstance(result,list) and part.isdigit() and int(part)<len(result):result=result[int(part)]
   else:raise ValueError('Mapped value not found: '+key)
  return result
 match=re.fullmatch(r'\{\{\s*([\w.]+)\s*\}\}',value)
 if match:return lookup(match[1])
 return re.sub(r'\{\{\s*([\w.]+)\s*\}\}',lambda m:str(lookup(m[1])),value)

def datetime_operand(value):
 if not isinstance(value,str):raise ValueError('Datetime comparison requires a date or time string')
 text=value.strip()
 if re.fullmatch(r'\d{1,2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?',text):
  try:
   parsed=datetime.strptime(text,'%H:%M:%S.%f' if '.' in text else '%H:%M:%S' if text.count(':')==2 else '%H:%M')
   return 'time',parsed.hour*3600+parsed.minute*60+parsed.second+parsed.microsecond/1000000
  except ValueError:raise ValueError('Enter a valid time such as 17:00')
 if re.fullmatch(r'\d{1,2}(?::\d{2})?\s*[AaPp][Mm]',text):
  try:
   text=re.sub(r'\s+','',text).upper()
   parsed=datetime.strptime(text,'%I:%M%p' if ':' in text else '%I%p')
   return 'time',parsed.hour*3600+parsed.minute*60
  except ValueError:raise ValueError('Enter a valid time such as 5PM')
 if not re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?)?',text):
  raise ValueError('Enter an ISO date or datetime, or a time such as 17:00')
 try:
  parsed=datetime.fromisoformat(text.replace('Z','+00:00'))
  if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=timezone.utc)
  return 'date',parsed.timestamp()
 except (ValueError,OverflowError):raise ValueError('Enter a valid calendar date and time')

def filter_matches(config,bundle):
 conditions=config.get('conditions')
 if conditions is None:conditions=[config]
 if not isinstance(conditions,list) or not 1<=len(conditions)<=20:raise ValueError('A filter requires 1–20 conditions')
 mode=config.get('match','all')
 if mode not in ('all','any'):raise ValueError('Select All or Any conditions')
 results=[]
 for condition in conditions:
  if not isinstance(condition,dict):raise ValueError('Invalid filter condition')
  operation=condition.get('operator','Equal to')
  if not isinstance(operation,str) or operation not in FILTER_OPERATORS:raise ValueError('Unknown filter operator')
  if operation in ('Exists','Does not exist'):
   try:
    value=map_value(condition.get('left',''),bundle)
    exists=value is not None and value!=''
   except ValueError:exists=False
   result=exists if operation=='Exists' else not exists
   if mode=='all' and not result:return False
   if mode=='any' and result:return True
   results.append(result);continue
  left=map_value(condition.get('left',''),bundle);right=map_value(condition.get('right',''),bundle)
  if operation in ('Greater than','Greater than or equal to','Less than','Less than or equal to'):
   if isinstance(left,bool) or isinstance(right,bool):raise ValueError('Numeric comparison requires finite numbers')
   a,b=float(left),float(right)
   if not math.isfinite(a) or not math.isfinite(b):raise ValueError('Numeric comparison requires finite numbers')
   result={'Greater than':a>b,'Greater than or equal to':a>=b,'Less than':a<b,'Less than or equal to':a<=b}[operation]
  elif operation in ('Datetime equal to','Datetime not equal to','Later than','Later than or equal to','Earlier than','Earlier than or equal to'):
   kind_a,a=datetime_operand(left);kind_b,b=datetime_operand(right)
   if kind_a!=kind_b:raise ValueError('Compare two dates or two times; do not mix them')
   result={'Datetime equal to':a==b,'Datetime not equal to':a!=b,'Later than':a>b,'Later than or equal to':a>=b,'Earlier than':a<b,'Earlier than or equal to':a<=b}[operation]
  elif operation in ('Array contains','Array does not contain'):
   if not isinstance(left,list):raise ValueError('Array comparison requires an array on the left')
   result=any(type(item) is type(right) and item==right for item in left)
   if operation=='Array does not contain':result=not result
  else:
   a,b=str(left),str(right)
   if operation=='Equal to':result=a==b
   elif operation=='Not equal to':result=a!=b
   elif operation=='Contains':result=b in a
   elif operation=='Does not contain':result=b not in a
   elif operation=='Starts with':result=a.startswith(b)
   elif operation=='Ends with':result=a.endswith(b)
   else:raise ValueError('Unknown filter operator')
  results.append(result)
  if mode=='all' and not result:return False
  if mode=='any' and result:return True
 return all(results) if mode=='all' else any(results)

def validate_json_structure(value,schema,strict=False,path='value',depth=0):
 if depth>20:raise ValueError('Data structure nesting exceeds 20 levels')
 if not isinstance(schema,dict):raise ValueError('Invalid data structure specification')
 types={'string':str,'number':(int,float),'integer':int,'boolean':bool,'object':dict,'array':list,'null':type(None)}
 kind=schema.get('type')
 if kind is not None and kind not in types:raise ValueError('Unsupported data structure type at '+path)
 if kind and (not isinstance(value,types[kind]) or (kind in ('number','integer') and isinstance(value,bool))):raise ValueError('Invalid type at '+path+': expected '+kind)
 if isinstance(value,dict):
  properties=schema.get('properties',{});required=schema.get('required',[])
  if not isinstance(properties,dict) or not isinstance(required,list) or any(not isinstance(key,str) for key in required):raise ValueError('Invalid data structure fields')
  for key in required:
   if key not in value:raise ValueError('Required field missing: '+path+'.'+key)
  if (strict or schema.get('additionalProperties') is False) and any(key not in properties for key in value):raise ValueError('Unexpected field at '+path)
  for key,child in properties.items():
   if key in value:validate_json_structure(value[key],child,strict,path+'.'+key,depth+1)
 if isinstance(value,list) and 'items' in schema:
  for index,item in enumerate(value):validate_json_structure(item,schema['items'],strict,path+'['+str(index)+']',depth+1)

def execute(graph,initial=None,trigger='manual',increment=None,store_action=None,json_structure=None):
 started=time.time();steps=[];initial=initial or {};bundles=[{**initial,'input':initial} if initial else {}];status='success'
 for module in graph:
  if module['type'] in ('text-aggregator','numeric-aggregator','json-aggregate'):
   before=json.loads(json.dumps(bundles));cfg=module.get('config',{});typ=module['type']
   try:
    if len(steps)>=MAX_OPERATIONS:raise ValueError('Local execution exceeds 200 operations')
    if time.time()-started>10:raise ValueError('Local execution exceeded its 10 second time limit')
    if typ=='json-aggregate':
     field=cfg.get('value','')
     values=[map_value(field,item) if field!='' else item for item in bundles]
     result={'json':json.dumps(values,ensure_ascii=False,allow_nan=False)}
    elif typ=='text-aggregator':
     separator=cfg.get('separator','\n')
     if not isinstance(separator,str) or len(separator)>1000:raise ValueError('Enter a text separator of up to 1000 characters')
     result={'text':separator.join(str(map_value(cfg.get('text',''),item)) for item in bundles)}
    else:
     operation=cfg.get('operation','sum')
     if operation not in ('sum','average','min','max','count'):raise ValueError('Unknown aggregation function')
     if operation=='count':value=len(bundles)
     else:
      values=[]
      for item in bundles:
       number=map_value(cfg.get('number',''),item)
       if isinstance(number,bool) or not isinstance(number,(str,int,float)):raise ValueError('Numeric aggregator requires finite numbers')
       number=float(number)
       if not math.isfinite(number):raise ValueError('Numeric aggregator requires finite numbers')
       values.append(number)
      value=sum(values) if operation=='sum' else sum(values)/len(values) if operation=='average' else min(values) if operation=='min' else max(values)
      if not math.isfinite(value):raise ValueError('Aggregation result is outside the supported numeric range')
     result={'result':value}
    if len(json.dumps(result).encode())>200000:raise ValueError('Module output exceeds the local 200 KB limit')
    bundles=[result]
    steps.append({'module':module['id'],'type':typ,'status':'success','input':{'bundles':before},'output':result,'output_count':1})
   except (ValueError,TypeError,KeyError,OverflowError) as exc:
    steps.append({'module':module['id'],'type':typ,'status':'error','input':{'bundles':before},'error':str(exc)[:300],'output_count':0});status='error';bundles=[];break
   continue
  following=[]
  for bundle in bundles:
   before=json.loads(json.dumps(bundle));cfg=module.get('config',{});typ=module['type']
   def mapped(value):return map_value(value,bundle)
   def variable_name(value):
    if not isinstance(value,str) or not re.fullmatch(r'\w{1,80}',value.strip()):
     raise ValueError('Variable names must contain 1–80 letters, digits or underscores')
    return value.strip()
   def map_tree(value,depth=0):
    if depth>20:raise ValueError('Variable value nesting exceeds 20 levels')
    if isinstance(value,dict):return {key:map_tree(item,depth+1) for key,item in value.items()}
    if isinstance(value,list):return [map_tree(item,depth+1) for item in value]
    return mapped(value)
   try:
    if len(steps)>=MAX_OPERATIONS:raise ValueError('Local execution exceeds 200 operations')
    if time.time()-started>10:raise ValueError('Local execution exceeded its 10 second time limit')
    outputs=[];step_status='success';multiple=typ in ('iterator','basic-trigger','store-search')
    if typ=='webhook':
     if trigger!='webhook':raise ValueError('Waiting for webhook data. Send a payload to the webhook endpoint.')
     bundle={**bundle,'payload':initial}
    elif typ.startswith('store-'):
     if store_action is None:raise ValueError('Data store execution is unavailable')
     config={key:map_tree(value) for key,value in cfg.items() if key!='record'}
     if typ in ('store-put','store-update'):
      record=cfg.get('record',{})
      if isinstance(record,str):
       if re.fullmatch(r'\{\{\s*([\w.]+)\s*\}\}',record):record=mapped(record)
       else:record=map_tree(decode_json(record))
      else:record=map_tree(record)
      config['record']=record
     result=store_action(typ,config)
     if typ=='store-search':outputs=[{**bundle,**item} for item in result]
     else:bundle={**bundle,**result}
    elif typ=='set-variable':
     key=str(cfg.get('name','')).strip()
     if not key:raise ValueError('Variable name is required')
     bundle={**bundle,key:mapped(cfg.get('value',''))}
    elif typ=='set-variables':
     values=cfg.get('variables',{})
     if isinstance(values,str):values=decode_json(values)
     if not isinstance(values,dict) or not 1<=len(values)<=50:raise ValueError('Enter a JSON object containing 1–50 variables')
     values={variable_name(key):map_tree(value) for key,value in values.items()}
     bundle={**bundle,**values}
    elif typ=='get-variable':
     key=variable_name(cfg.get('name',''))
     if key not in bundle:raise ValueError('Variable not found: '+key)
     bundle={**bundle,'value':bundle[key]}
    elif typ=='get-variables':
     names=cfg.get('names',[])
     if isinstance(names,str):names=[part.strip() for part in re.split(r'[,\n]',names) if part.strip()]
     if not isinstance(names,list) or not 1<=len(names)<=50:raise ValueError('Enter 1–50 variable names separated by commas or new lines')
     names=[variable_name(key) for key in names]
     for key in names:
      if key not in bundle:raise ValueError('Variable not found: '+key)
     bundle={**bundle,'variables':{key:bundle[key] for key in names}}
    elif typ=='increment':
     if increment is None:raise ValueError('Persistent counter storage is unavailable')
     bundle={**bundle,'value':increment(module['id'])}
    elif typ=='switch':
     value=mapped(cfg.get('input',''));cases=cfg.get('cases',[])
     if isinstance(cases,str):cases=decode_json(cases)
     if not isinstance(cases,list) or len(cases)>50:raise ValueError('Enter a JSON array containing up to 50 switch cases')
     if any(not isinstance(case,dict) or 'match' not in case or 'output' not in case for case in cases):raise ValueError('Each switch case requires match and output fields')
     selected=next((case for case in cases if type(mapped(case['match'])) is type(value) and mapped(case['match'])==value),None)
     result=map_tree(selected['output']) if selected is not None else map_tree(cfg.get('fallback',''))
     bundle={**bundle,'output':result}
    elif typ=='basic-trigger':
     values=cfg.get('bundles',[])
     if isinstance(values,str):values=decode_json(values)
     if not isinstance(values,list) or not all(isinstance(item,dict) for item in values):raise ValueError('Basic trigger requires a JSON array of objects')
     if len(values)>MAX_BUNDLES:raise ValueError('Basic trigger exceeds 100 output bundles')
     outputs=values
    elif typ=='text':
     value=str(mapped(cfg.get('text','')));op=cfg.get('operation','compose')
     if op not in ('compose','uppercase','lowercase','trim'):raise ValueError('Unknown text operation')
     bundle={**bundle,'text':value.upper() if op=='uppercase' else value.lower() if op=='lowercase' else value.strip() if op=='trim' else value}
    elif typ=='json-parse':
     parsed=decode_json(str(mapped(cfg.get('json',''))));mode=cfg.get('array_mode','single')
     if mode not in ('split','single'):raise ValueError('Select how to handle a JSON array')
     if isinstance(parsed,list) and mode=='split':
      multiple=True
      if len(parsed)>MAX_BUNDLES:raise ValueError('Parse JSON exceeds 100 output bundles')
      outputs=[{**bundle,'data':item} for item in parsed]
     else:bundle={**bundle,'data':parsed}
    elif typ=='json-create':
     value=cfg.get('value','')
     if value=='':value=bundle
     elif isinstance(value,str) and re.fullmatch(r'\{\{\s*([\w.]+)\s*\}\}',value):value=mapped(value)
     else:
      if isinstance(value,str):value=decode_json(value)
      value=map_tree(value)
     structure=cfg.get('structure','')
     if structure:
      if not isinstance(structure,str) or json_structure is None:raise ValueError('Select an available data structure')
      definition=json_structure(structure)
      validate_json_structure(value,definition.get('schema',{}),bool(definition.get('strict')))
     indent=cfg.get('indent','compact')
     if indent not in ('compact','2 spaces','4 spaces'):raise ValueError('Select a JSON indentation option')
     bundle={**bundle,'json':json.dumps(value,ensure_ascii=False,allow_nan=False,indent=None if indent=='compact' else int(indent[0]))}
    elif typ=='filter':
     if not filter_matches(cfg,bundle):step_status='filtered'
    elif typ=='iterator':
     values=mapped(cfg.get('array',''))
     if isinstance(values,str):values=decode_json(values)
     if not isinstance(values,list):raise ValueError('Iterator requires an array')
     if len(values)+len(following)>MAX_BUNDLES:raise ValueError('Iterator exceeds 100 output bundles')
     outputs=[{**bundle,'item':item,'value':item,'index':i+1,'count':len(values)} for i,item in enumerate(values)]
    elif typ=='sleep':
     delay=float(cfg.get('seconds',1))
     if not 0<=delay<=2:raise ValueError('Local sleep must be between 0 and 2 seconds')
     time.sleep(delay)
    else:raise ValueError('This module requires a local integration adapter. No external request was sent.')
    if not multiple and step_status!='filtered':outputs=[bundle]
    if len(json.dumps(outputs).encode())>200000:raise ValueError('Module output exceeds the local 200 KB limit')
    if len(following)+len(outputs)>MAX_BUNDLES:raise ValueError('Execution exceeds 100 active bundles')
    following.extend(outputs)
    steps.append({'module':module['id'],'type':typ,'status':step_status,'input':before,'output':{'bundles':outputs,'count':len(outputs)} if multiple else bundle,'output_count':len(outputs)})
   except (ValueError,TypeError,KeyError,OverflowError) as exc:
    steps.append({'module':module['id'],'type':typ,'status':'error','input':before,'error':str(exc)[:300],'output_count':0});status='error';break
  bundles=following
  if status=='error' or not bundles:break
 return {'status':status,'steps':steps,'output':json.loads(json.dumps(bundles)),'started':started,'duration':round(time.time()-started,4),'operations':len(steps)}
