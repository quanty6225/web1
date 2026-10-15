let noteSeen={};
function noteChanged(note){
 if(!note._share)return false;
 const key='icloud-note-seen:'+session.account.account_id;
 if(noteSeen.key!==key){try{noteSeen={key,values:JSON.parse(localStorage.getItem(key)||'{}')}}catch{noteSeen={key,values:{}}}}
 const changed=noteSeen.values[note.id]&&noteSeen.values[note.id]!==note._revision;
 if(!noteSeen.values[note.id]||note.id===activeEntity?.id){noteSeen.values[note.id]=note._revision;localStorage.setItem(key,JSON.stringify(noteSeen.values));return false}
 return !!changed;
}
let noteShareTimer=null,noteShareContext=null;
function stopNoteSharePolling(){clearInterval(noteShareTimer);noteShareTimer=null}
async function openNoteSharing(kind,item){
 if(!item)return;await flushNoteSave(activeEntity?.id);
 if(item._share){return manageNoteParticipants(item._share.id,kind==='notes'&&item._share.kind==='folders')}
 noteShareForm({kind,target:item.id},'link');
}
function noteShareForm(context,method='link'){
 noteShareContext={...context,method};
 showDialog(context.share_id?'Add People':context.kind==='folders'?'Share Folder':'Share Note',`<div class="sharing-methods"><button data-share="method" data-method="email" aria-pressed="${method==='email'}">Email</button><button data-share="method" data-method="link" aria-pressed="${method==='link'}">Copy Link</button></div><form id="note-share-form">${method==='link'?'<label>Add People<input name="recipients" aria-label="Add People" placeholder="Email addresses or phone numbers" required></label>':''}<label>Permission<select name="permission" aria-label="Permission"><option value="write">Can make changes</option><option value="read">View only</option></select></label><label class="sharing-check"><input type="checkbox" name="can_invite">Participants can add other people</label><p class="hint">Only the people you invite can access this ${context.kind==='folders'?'folder':'note'}.</p><div class="error" role="alert"></div><div class="actions"><button type="button" data-action="close">Cancel</button><button class="primary">Share</button></div></form>`);
 document.querySelector('#note-share-form').onsubmit=async event=>{
  event.preventDefault();const form=event.target,data=Object.fromEntries(new FormData(form));
  const options={...context,method,permission:data.permission,can_invite:data.can_invite==='on'};
  if(method==='email')return composeNoteInvite(options);
  await submitNoteInvite(form,{...options,recipients:data.recipients.split(/[,;\n]/).map(s=>s.trim()).filter(Boolean)});
 };
}
function composeNoteInvite(options){
 showDialog('Share via Email','<form id="note-share-form"><label>To<input name="recipients" aria-label="To" required placeholder="Email addresses"></label><label>Message<textarea name="message" aria-label="Message"></textarea></label><div class="error" role="alert"></div><div class="actions"><button type="button" data-action="close">Cancel</button><button class="primary">Send</button></div></form>');
 document.querySelector('#note-share-form').onsubmit=async event=>{event.preventDefault();const data=Object.fromEntries(new FormData(event.target));await submitNoteInvite(event.target,{...options,message:data.message,recipients:data.recipients.split(/[,;\n]/).map(s=>s.trim()).filter(Boolean)})};
}
async function submitNoteInvite(form,data){
 const button=form.querySelector('button.primary');button.disabled=true;
 try{
  const result=await api('/api/note-shares',data);await notesPage();
  if(data.method==='email')return manageNoteParticipants(result.id);
  showDialog('Share Link',`<p>Only invited people can open this link.</p><input readonly id="note-share-link" aria-label="Share link" value="${esc(location.origin+result.path)}"><p role="status" id="copy-link-state"></p><button data-share="copy">Copy Link</button><button data-action="close">Done</button>`);
 }catch(error){form.querySelector('.error').textContent=error.message}finally{button.disabled=false}
}
async function manageNoteParticipants(id,folderNote=false){
 const data=await api('/api/note-shares/'+id);noteShareContext={share_id:id};
 if(folderNote){showDialog('Shared Folder','<p>This note uses the permissions of its shared folder.</p><button class="folder-sharing-control" data-share="manage" data-id="'+esc(id)+'">Manage Shared Folder</button><button data-action="close">Done</button>');return}
 showDialog('Participants',`<p>${esc(data.owner_name)} — Owner${data.owner?' (You)':''}</p><div class="note-participants">${data.participants.map(person=>`<section><strong>${esc(person.email)}${person.self?' (You)':''}</strong><small>${person.accepted?(person.permission==='write'?'Can make changes':'View only'):'Invited'}</small>${data.owner||data.can_invite?`<label>Permission<select data-participant="permission" data-email="${esc(person.email)}" aria-label="Permission for ${esc(person.email)}"><option value="write" ${person.permission==='write'?'selected':''}>Can make changes</option><option value="read" ${person.permission==='read'?'selected':''}>View only</option></select></label><label class="sharing-check"><input type="checkbox" data-participant="can-invite" data-email="${esc(person.email)}" ${person.can_invite?'checked':''}>Can add people</label><button data-share="remove" data-email="${esc(person.email)}">Remove Access</button>`:''}${person.self?'<button data-share="leave">Remove Me</button>':''}</section>`).join('')}</div><div class="error" role="alert"></div><div class="actions">${data.owner||data.can_invite?'<button data-share="add">Add People</button>':''}${data.owner?'<button data-share="stop">Stop Sharing</button>':''}<button data-action="close">Done</button></div>`);
 document.querySelectorAll('[data-participant]').forEach(input=>input.onchange=async()=>{
  const section=input.closest('section'),email=input.dataset.email;
  try{await api('/api/note-shares/'+id,{action:'permission',email,permission:section.querySelector('select').value,can_invite:section.querySelector('input').checked});section.querySelector('small').textContent=!data.participants.find(p=>p.email===email).accepted?'Invited':section.querySelector('select').value==='write'?'Can make changes':'View only'}catch(error){modal.querySelector('.error').textContent=error.message}
 });
}
async function noteInvitationPage(){
 stopNoteSharePolling();const id=location.pathname.split('/')[3];
 try{
  const data=await api('/api/note-shares/'+id);
  root.innerHTML=header('Notes')+`<main class="settings-page"><h1>${esc(data.title)}</h1><p>${esc(data.owner_name)} invited you to collaborate.</p><p>${data.permission==='write'?'You can make changes.':'You can only view this item.'}</p><button id="accept-note-invitation" class="primary">${data.kind==='folders'?'Open in Notes':'Accept Invitation'}</button><p class="error" role="alert"></p></main>`;
  document.querySelector('#accept-note-invitation').onclick=async event=>{event.target.disabled=true;try{await api('/api/note-shares/'+id,{action:'accept'});const key=data.owner?data.target:'shared:'+id+':'+data.target;navigate(data.kind==='folders'?'/notes/folder/'+encodeURIComponent(key)+'/':'/notes/?item='+encodeURIComponent(key))}catch(error){root.querySelector('.error').textContent=error.message;event.target.disabled=false}};
 }catch(error){root.innerHTML=header('Notes')+'<main class="settings-page"><h1>Unable to Open Note</h1><p>'+esc(error.message)+'</p><a href="/notes/">Back to Notes</a></main>'}
}
async function confirmSharedNoteDelete(note){
 if(!note._share.owner&&note._share.permission==='read')return;
 const confirmed=await noteDeletionConfirmation({title:'Delete this shared note?',body:note._share.owner?'If you delete this shared note, other people will no longer have access, and it will be deleted on all of their devices.':'It will be deleted on all of your devices. To reopen the note, click the link you were invited with.',kind:'note',action:'OK',previous:document.querySelector('[data-op="delete-note"]'),perform:async()=>{
  await flushNoteSave(note.id);
  if(note._share.owner)await storeItem('notes',{...note,deleted:true});else await removeItem('notes',note.id);
 }});
 if(!confirmed)return;root.inert=true;
 try{history.replaceState(null,'','/notes/');await notesPage()}finally{root.inert=false}
}
function configureNoteSharing(readOnly){
 const note=activeEntity,folder=appData.folders?.find(f=>f.id===selectedNoteFolder());
 for(const op of ['note-style','note-checklist','note-table']){const button=document.querySelector('[data-op="'+op+'"]');if(button)button.disabled=!note||readOnly}
 const remove=document.querySelector('[data-op="delete-note"]');if(remove)remove.disabled=!note||!!(note._share&&!note._share.owner&&note._share.permission==='read');
 for(const create of document.querySelectorAll('[data-op="new-note"]'))create.disabled=folder?._share?.permission==='read';
 document.querySelectorAll('.note-row').forEach(row=>{const item=appData.notes.find(n=>n.id===row.dataset.id);if(item?._share&&!item._share.owner&&item._share.kind==='folders')row.draggable=false});
 if(!(appData.notes||[]).some(n=>n._share)&&!(appData.folders||[]).some(f=>f._share))return;
 let busy=false;
 noteShareTimer=setInterval(async()=>{
  if(busy||!location.pathname.startsWith('/notes/')||location.pathname.startsWith('/notes/share/')||modal.open)return;
  busy=true;
  try{
   const [noteData,folderData]=await Promise.all([api('/api/items/notes'),api('/api/items/folders')]);
   const current=noteData.items,next=current.find(n=>n.id===activeEntity?.id),old=activeEntity;
   if(old?._share&&!old._share.owner&&!next){
    const job=noteSaveJobs.get(old.id);if(job){clearTimeout(job.timer);job.payload=null}
    const editor=document.querySelector('#note-editor'),title=document.querySelector('#note-title');if(editor)editor.contentEditable='false';if(title)title.readOnly=true;
    document.querySelectorAll('.note-row').forEach(row=>{if(row.dataset.id===old.id)row.remove()});
    const state=document.querySelector('#note-save-state');if(state)state.textContent='Access removed. Copy any unsaved text before leaving.';const remove=document.querySelector('[data-op="delete-note"]');if(remove)remove.disabled=true;stopNoteSharePolling();return;
   }
   if(next&&old&&next._share?.permission==='write'&&old._share?.permission==='read'){await notesPage();return}
   if(next&&old&&next._share?.permission==='read'&&old._share?.permission!=='read'){
    const job=noteSaveJobs.get(old.id);if(job){clearTimeout(job.timer);job.payload=null}
    document.querySelector('#note-title').readOnly=true;document.querySelector('#note-editor').contentEditable='false';
    Object.assign(old._share,next._share);for(const op of ['note-style','note-checklist','note-table','delete-note'])document.querySelector('[data-op="'+op+'"]').disabled=true;
    document.querySelector('#note-save-state').textContent='You can only view this note.';
   }
   const dirty=[...noteSaveJobs.values()].some(job=>job.payload||job.inFlight);
   const changed=JSON.stringify(current)!==JSON.stringify(appData.notes)||JSON.stringify(folderData.items)!==JSON.stringify(appData.folders);
   if(!dirty&&changed&&!document.querySelector('#note-detail')?.contains(document.activeElement))await notesPage();
  }catch(error){const state=document.querySelector('#note-save-state');if(state)state.textContent=error.message}finally{busy=false}
 },2000);
}
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-share]');if(!button)return;
 try{
  const action=button.dataset.share;
  if(action==='folder')return openNoteSharing('folders',appData.folders.find(f=>f.id===button.dataset.id));
  if(action==='method')return noteShareForm(noteShareContext,button.dataset.method);
  if(action==='manage')return manageNoteParticipants(button.dataset.id);
  if(action==='add')return noteShareForm(noteShareContext);
  if(action==='copy'){
   const field=document.querySelector('#note-share-link');field.select();
   try{await navigator.clipboard.writeText(field.value);document.querySelector('#copy-link-state').textContent='Link copied.'}catch{document.querySelector('#copy-link-state').textContent='Select and copy the link above.'}return;
  }
  if(['stop','leave','remove'].includes(action)){
   const key=noteShareContext.share_id;
   await api('/api/note-shares/'+key,{action,email:button.dataset.email});
   closeDialog();await notesPage();if(action==='remove')await manageNoteParticipants(key);
  }
 }catch(error){showDialog('Unable to Share','<p>'+esc(error.message)+'</p><button data-action="close">OK</button>')}
});
window.addEventListener('pagehide',stopNoteSharePolling);
