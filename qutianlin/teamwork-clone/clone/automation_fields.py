"""Resolve custom-field actions through workspace-owned field definitions."""
import json,math
from pathlib import Path
from urllib.parse import urlsplit
from datetime import date
from fastapi import HTTPException
TYPES=['Text','Number','Decimal number','Currency','Dropdown','Status','Date','URL','Checkbox']
CURRENCIES=json.loads(Path(__file__).with_name('custom-field-currencies.json').read_text())

def validate_definition(data):
 if data.get('entity') not in ['Client','Project','Task'] or data.get('type') not in TYPES:raise HTTPException(422,'Choose a field type and entity.')
 if data['type'] in ['Dropdown','Status']:
  data.setdefault('options',data.get('choices') or ['Option 1','Option 2'])
  if not isinstance(data['options'],list) or not data['options'] or any(not isinstance(v,str) or not v.strip() for v in data['options']) or len(set(data['options']))!=len(data['options']):raise HTTPException(422,'Enter distinct, non-empty field options.')
 if data['type'] in ['Decimal number','Currency']:
  try:data['decimals']=int(data.get('decimals',2))
  except (ValueError,TypeError):raise HTTPException(422,'Choose valid decimals.')
  if data['decimals'] not in [0,1,2]:raise HTTPException(422,'Choose 0, 1 or 2 decimals.')
 if data['type']=='Currency' and data.get('currency') not in {r['code'] for r in CURRENCIES}:raise HTTPException(422,'Choose a currency.')
 if not isinstance(data.get('project_specific',False),bool):raise HTTPException(422,'Choose valid project scope.')
 if data.get('project_specific') and data['entity']!='Task':raise HTTPException(422,'Project-specific fields apply to tasks.')

def validate_definition_scope(c,who,data):
 if data.get('project_specific') and (not isinstance(data.get('project_id'),str) or not c.execute('SELECT 1 FROM tw_projects WHERE owner=? AND id=?',(who,data.get('project_id'))).fetchone()):raise HTTPException(422,'Choose a project in this workspace.')

def definition(c,who,ident):
 row=c.execute("SELECT data FROM tw_records WHERE owner=? AND id=? AND kind='customfield'",(who,ident)).fetchone()
 if not row or json.loads(row['data']).get('entity')!='Task':raise HTTPException(422,'Choose a task custom field in this workspace.')
 field=json.loads(row['data'])
 if field['type'] in ['Dropdown','Status']:field.setdefault('options',field.get('choices') or ['Option 1','Option 2'])
 return field

def value_for(field,value):
 kind=field['type']
 if kind in ['Number','Decimal number','Currency']:
  try:
   if isinstance(value,bool):raise ValueError()
   number=float(value)
   if not math.isfinite(number):raise ValueError()
  except (ValueError,TypeError):raise HTTPException(422,'Enter a valid custom field number.')
  if kind=='Number' and not number.is_integer():raise HTTPException(422,'Enter a whole custom field number.')
  return int(number) if number.is_integer() else number
 if kind=='Checkbox':
  if not isinstance(value,bool):raise HTTPException(422,'Choose a custom field checkbox value.')
  return value
 if kind=='Date':
  try:return date.fromisoformat(value).isoformat()
  except (ValueError,TypeError):raise HTTPException(422,'Choose a valid custom field date.')
 if not isinstance(value,str) or not value.strip():raise HTTPException(422,'Enter a custom field value.')
 if kind in ['Dropdown','Status'] and value not in field.get('options',[]):raise HTTPException(422,'Choose a configured custom field option.')
 if kind=='URL':
  parsed=urlsplit(value)
  if parsed.scheme not in ['http','https'] or not parsed.netloc:raise HTTPException(422,'Enter a valid custom field URL.')
 return value

def validate(c,who,action):
 field=definition(c,who,action.get('custom_field'));action['value']=value_for(field,action.get('value'))

def apply(c,who,tid,action):
 # A field can be removed or reconfigured after the automation was saved.
 try:field=definition(c,who,action['custom_field']);value=value_for(field,action['value'])
 except HTTPException:return False
 row=c.execute('SELECT options,project_id FROM tw_tasks WHERE owner=? AND id=?',(who,tid)).fetchone()
 if not row:return False
 if field.get('project_specific') and row['project_id']!=field.get('project_id'):return False
 options=json.loads(row['options']);options.setdefault('custom_fields',{})[field['title']]=value
 c.execute('UPDATE tw_tasks SET options=? WHERE owner=? AND id=?',(json.dumps(options),who,tid));return True
