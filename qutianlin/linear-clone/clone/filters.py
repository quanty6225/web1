"""Bounded, inert filter documents persisted with locally created views."""
import json
from fastapi import HTTPException

def validate_view_filters(document):
 if 'filters' not in document:return
 value=document['filters'];remaining=[200]
 def walk(node,depth=0):
  remaining[0]-=1
  if depth>12 or remaining[0]<0 or not isinstance(node,dict):raise ValueError()
  for key,item in node.items():
   if key in ('__proto__','prototype','constructor'):raise ValueError()
   if key in ('and','or'):
    if not isinstance(item,list):raise ValueError()
    for child in item:walk(child,depth+1)
   elif isinstance(item,dict):walk(item,depth+1)
   elif isinstance(item,list):
    if len(item)>100 or any(v is not None and not isinstance(v,(str,int,float,bool)) for v in item):raise ValueError()
   elif item is not None and not isinstance(item,(str,int,float,bool)):raise ValueError()
 try:
  if len(json.dumps(value).encode())>20000:raise ValueError()
  walk(value)
 except (ValueError,TypeError,RecursionError):raise HTTPException(422,'Invalid filter expression.')
