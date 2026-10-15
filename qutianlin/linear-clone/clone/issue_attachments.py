"""Canonical workspace upload references for issues and comments."""
from fastapi import HTTPException
from uploads import metadata

def attachments(connection,wid,value):
 if not isinstance(value,list) or len(value)>100:raise HTTPException(422,'Select up to 100 files.')
 result=[];seen=set()
 for item in value:
  id=item.get('id') if isinstance(item,dict) else item
  if not isinstance(id,str):raise HTTPException(422,'Select a file from this workspace.')
  row=connection.execute('SELECT * FROM linear_uploads WHERE workspace_id=? AND id=?',(wid,id)).fetchone()
  if not row:raise HTTPException(422,'Select a file from this workspace.')
  if id not in seen:result.append(metadata(row));seen.add(id)
 return result
