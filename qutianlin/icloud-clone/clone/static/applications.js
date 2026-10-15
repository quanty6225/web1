let appData={},activeEntity=null,noteSelection=null,calendarDate=new Date();
const noteSaveJobs=new Map();
async function flushNoteSave(id){
 const job=noteSaveJobs.get(id);if(!job)return;
 clearTimeout(job.timer);
 if(job.inFlight){await job.inFlight;return flushNoteSave(id)}
 if(!job.payload)return;
 const payload=job.payload;job.payload=null;if(job.entity._revision)payload._revision=job.entity._revision;
 const status=text=>{if(activeEntity?.id===id&&document.querySelector('#note-save-state'))document.querySelector('#note-save-state').textContent=text};
 job.inFlight=storeItem('notes',payload).then(()=>{Object.assign(job.entity,payload);status(job.payload?'Saving…':'Saved');renderNoteTags()}).catch(error=>{if(!job.payload)job.payload=payload;status('Unable to save: '+error.message);throw error});
 try{await job.inFlight}finally{job.inFlight=null}
 if(job.payload)await flushNoteSave(id);
}
async function items(kind){const response=await api('/api/items/'+kind);if(response.generation!==undefined&&['calendars','events','lists','reminders'].includes(kind))calendarGeneration=response.generation;appData[kind]=response.items;return appData[kind]}
async function storeItem(kind,data){data.id=data.id||crypto.randomUUID();const result=await api('/api/items/'+kind+'/'+encodeURIComponent(data.id),data,'PUT');if(result.item)Object.assign(data,result.item);return data}
async function removeItem(kind,id){await api('/api/items/'+kind+'/'+id,{},'DELETE')}
function appFrame(label,sidebar,content,toolbar=''){root.innerHTML=header(label)+`<div class="app-layout"><aside>${sidebar}</aside><main class="workspace">${toolbar?'<div class="toolbar">'+toolbar+'</div>':''}${content}</main></div>`}
function formDialog(title,fields,save,extra=''){showDialog(title,`<form id="edit-form">${fields}<div class="error" role="alert"></div><div class="actions">${extra}<button type="button" data-action="close">Cancel</button><button class="primary" type="submit">Done</button></div></form>`);document.querySelector('#edit-form').onsubmit=async e=>{e.preventDefault();const form=e.target;if(form.dataset.saving)return;form.dataset.saving='true';const submit=form.querySelector('[type=submit]');submit.disabled=true;try{if(await save(Object.fromEntries(new FormData(form)))!==false)closeDialog()}catch(err){form.querySelector('.error').textContent=err.message}finally{delete form.dataset.saving;submit.disabled=false}}}
function field(name,label,value='',type='text'){return `<label>${label}<input name="${name}" type="${type}" value="${esc(value)}" aria-label="${label}"></label>`}
function safeNoteHTML(value){let doc=new DOMParser().parseFromString(value||'','text/html');let allowed=new Set(['B','STRONG','I','EM','U','S','STRIKE','BR','P','DIV','UL','OL','LI','TABLE','TBODY','TR','TD','TH','H1','H2','H3','PRE']);function clean(node){if(node.nodeType===3)return document.createTextNode(node.textContent);if(node.tagName==='INPUT'&&node.getAttribute('type')==='checkbox'){let checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.contentEditable='false';if(node.hasAttribute('checked'))checkbox.setAttribute('checked','');return checkbox}let next=document.createElement(allowed.has(node.tagName)?node.tagName.toLowerCase():'span');for(let child of node.childNodes)next.append(clean(child));return next}let wrapper=document.createElement('div');for(let node of doc.body.childNodes)wrapper.append(clean(node));return wrapper.innerHTML}
function entityBoundary(kind,item,back){navigate(`/boundary/?collection=${encodeURIComponent(kind)}&item=${encodeURIComponent(item.title||item.name)}&back=${encodeURIComponent(back)}`)}

function selectedNoteFolder(){return location.pathname.startsWith('/notes/folder/')?decodeURIComponent(location.pathname.split('/')[3]):null}
async function createNote(){
 const title=document.querySelector('#note-title'),editor=document.querySelector('#note-editor');
 const readOnly=title?.readOnly,editable=editor?.contentEditable;
 if(title)title.readOnly=true;if(editor)editor.contentEditable='false';root.inert=true;
 try{
  await flushNoteSave(activeEntity?.id);
  const selectedFolder=selectedNoteFolder();const note=selectedFolder?.startsWith('shared:')?await api('/api/notes/shared-create',{folder:selectedFolder}):await storeItem('notes',{title:'New Note',body:'',folder:selectedFolder||'notes',deleted:false,pinned:false});
  history.replaceState(null,'',location.pathname+'?item='+note.id);await notesPage();
 }finally{root.inert=false;if(title?.isConnected)title.readOnly=readOnly;if(editor?.isConnected)editor.contentEditable=editable}
}
function noteTags(note){return [...new Set([...((note.title||'')+' '+(note.body||'')).matchAll(/(?:^|[^\p{L}\p{N}_#-])#([\p{L}\p{N}_-]+)/gu)].map(m=>m[1].toLocaleLowerCase()))]}
function renderNoteTags(){
 const target=document.querySelector('#note-tags');if(!target)return;
 const selected=new URLSearchParams(location.search).getAll('tag');
 const tags=[...new Set((appData.notes||[]).filter(n=>!n.deleted).flatMap(noteTags))].sort((a,b)=>a.localeCompare(b));
 target.innerHTML=tags.length?'<h3>Tags</h3>'+tags.map(tag=>`<button data-op="note-tag" data-tag="${esc(tag)}" aria-pressed="${selected.includes(tag)}">#${esc(tag)}</button>`).join('')+(selected.length?'<button data-op="clear-note-tags">All Notes</button>':''):'';
}
function suggestNoteTags(editor){
 let panel=document.querySelector('#note-tag-suggestions');
 if(!panel){panel=document.createElement('div');panel.id='note-tag-suggestions';panel.setAttribute('role','listbox');panel.setAttribute('aria-label','Suggested tags');editor.after(panel)}
 panel.replaceChildren();panel.hidden=true;
 const selection=getSelection();if(!selection?.isCollapsed||!editor.contains(selection.anchorNode)||selection.anchorNode.nodeType!==Node.TEXT_NODE)return;
 const node=selection.anchorNode,offset=selection.anchorOffset,match=node.textContent.slice(0,offset).match(/(?:^|[^\p{L}\p{N}_#-])#([\p{L}\p{N}_-]*)$/u);if(!match)return;
 const partial=match[1].toLocaleLowerCase();
 const tags=[...new Set((appData.notes||[]).filter(n=>!n.deleted).flatMap(noteTags))].filter(tag=>tag.startsWith(partial)&&tag!==partial).sort();
 for(const tag of tags){const button=document.createElement('button');button.type='button';button.setAttribute('role','option');button.textContent='#'+tag;
  button.onmousedown=event=>event.preventDefault();
  button.onclick=()=>{const range=document.createRange();range.setStart(node,offset-match[1].length-1);range.setEnd(node,offset);range.deleteContents();const text=document.createTextNode('#'+tag+' ');range.insertNode(text);range.setStartAfter(text);range.collapse(true);selection.removeAllRanges();selection.addRange(range);editor.focus();panel.hidden=true;editor.dispatchEvent(new InputEvent('input'))};panel.append(button)
 }
 panel.hidden=!tags.length;
 editor.onkeydown=event=>{if(panel.hidden)return;if(event.key==='Escape'){panel.hidden=true;event.preventDefault()}else if(event.key==='ArrowDown'){panel.querySelector('button')?.focus();event.preventDefault()}};
}
function noteFolderLevel(id){
 let level=0;const seen=new Set();
 while(id){if(seen.has(id))return Infinity;seen.add(id);level++;id=appData.folders.find(f=>f.id===id)?.parent}
 return level;
}
function noteFolderHeight(id,seen=new Set()){
 if(seen.has(id))return Infinity;seen.add(id);
 return 1+Math.max(0,...appData.folders.filter(f=>f.parent===id).map(f=>noteFolderHeight(f.id,seen)));
}
let noteDeletionPending=false;
function confirmNoteFolderDeletion(folder){
 const previous=[...document.querySelectorAll('[data-op="folder-menu"]')].find(el=>el.dataset.id===folder.id);
 const shared=folder._share,received=shared&&!shared.owner;
 const title=shared?'Are you sure you want to delete this shared folder?':`Are you sure you want to delete “${folder.name}”?`;
 const body=received?'It will be deleted from all of your devices. To rejoin this shared folder, click the link you were invited with.':shared?'If you delete this folder, other people will no longer have access to it and it will be deleted from all of their devices.':'All notes and any subfolders will be deleted.';
 return noteDeletionConfirmation({title,body,previous,kind:'folder',action:'Delete Folder',perform:async()=>{await flushNoteSave(activeEntity?.id);await removeItem('folders',folder.id)}});
}
function noteDeletionConfirmation({title,body,previous,kind,action,perform}){
 if(noteDeletionPending)return Promise.resolve(false);noteDeletionPending=true;
 showDialog(title,`<p>${esc(body)}</p><div class="error" role="alert"></div><div class="actions"><button type="button" data-${kind}-confirm="cancel">Cancel</button><button type="button" class="primary" data-${kind}-confirm="delete">${esc(action)}</button></div>`);
 modal.classList.add(`notes-${kind}-confirmation`);modal.querySelector('h2').id='notes-delete-title';modal.setAttribute('aria-labelledby','notes-delete-title');
 return new Promise(resolve=>{
  let busy=false,finished=false;
  const cancelButton=modal.querySelector(`[data-${kind}-confirm="cancel"]`),deleteButton=modal.querySelector(`[data-${kind}-confirm="delete"]`),error=modal.querySelector('.error');
  const finish=deleted=>{
   if(finished)return;finished=true;noteDeletionPending=false;
   modal.removeEventListener('cancel',cancel);modal.removeEventListener('close',closed);modal.removeEventListener('keydown',keydown);
   window.removeEventListener('popstate',abandon);window.removeEventListener('pagehide',abandon);
   modal.classList.remove(`notes-${kind}-confirmation`);modal.removeAttribute('aria-labelledby');closeDialog();
   if(!deleted&&previous?.isConnected)previous.focus();resolve(deleted);
  };
  const cancel=event=>{event?.preventDefault();if(!busy)finish(false)};
  const closed=()=>finish(false),abandon=()=>finish(false);
  const confirm=async()=>{
   if(busy||finished)return;busy=true;cancelButton.disabled=true;deleteButton.disabled=true;error.textContent='';
   try{await perform();finish(true)}
   catch(err){if(!finished){error.textContent=err.message;deleteButton.disabled=false;deleteButton.focus()}}
   finally{busy=false;cancelButton.disabled=false;deleteButton.disabled=false}
  };
  const keydown=event=>{if(event.key==='Enter'&&!event.target.closest('#alarm-banner')){event.preventDefault();confirm()}};
  cancelButton.onclick=cancel;deleteButton.onclick=confirm;
  modal.addEventListener('cancel',cancel);modal.addEventListener('close',closed);modal.addEventListener('keydown',keydown);
  window.addEventListener('popstate',abandon);window.addEventListener('pagehide',abandon);deleteButton.focus();
 });
}
async function moveNoteItem(kind,id,folder){
 if(root.inert)return;root.inert=true;
 try{
  if(kind==='folders'&&noteFolderLevel(folder)+noteFolderHeight(id)>5)throw Error('Notes is limited to 5 levels of folders.');
  await flushNoteSave(activeEntity?.id);
  await api('/api/notes/move',{kind,id,folder});
  noteSaveJobs.delete(id);
  history.pushState(null,'',folder?'/notes/folder/'+encodeURIComponent(folder)+'/'+(kind==='notes'?'?item='+encodeURIComponent(id):''):'/notes/');
  await notesPage();
 }finally{root.inert=false}
}
function validNoteDrop(kind,id,target){
 const folder=appData.folders?.find(f=>f.id===target),item=appData[kind]?.find(n=>n.id===id);
 if(!item||folder?._share)return false;
 if(kind==='notes')return !!folder&&item._share?.kind!=='folders';
 if(kind!=='folders'||id==='notes'||target==='notes'||target===id||item._share&&!item._share.root)return false;
 for(let parent=folder;parent;parent=appData.folders.find(f=>f.id===parent.parent))if(parent.id===id)return false;
 return !target||!!folder;
}
async function notesPage(){stopNoteSharePolling();await flushNoteSave(activeEntity?.id);let notes=await items('notes'),folders=await items('folders'),trash=location.pathname==='/notes/recently-deleted/',folder=selectedNoteFolder();const selectedTags=new URLSearchParams(location.search).getAll('tag');let visible=notes.filter(n=>!!n.deleted===trash&&(!folder||n.folder===folder)&&selectedTags.every(tag=>noteTags(n).includes(tag))).sort((a,b)=>Number(b.pinned)-Number(a.pinned)||(a.order||0)-(b.order||0));let id=new URLSearchParams(location.search).get('item');activeEntity=visible.find(n=>n.id===id)||visible[0]||null;
 const folderTree=(parent=null,depth=0)=>folders.filter(f=>(f.parent||null)===parent).sort((a,b)=>a.name.localeCompare(b.name)).map(f=>`<div class="note-folder-row" style="padding-left:${depth*16}px" data-note-drop="${esc(f.id)}" ${f.id==='notes'||f._share&&!f._share.owner&&!f._share.root?'':`draggable="true" data-note-drag="folders" data-id="${esc(f.id)}"`}><a class="${folder===f.id?'active':''}" href="/notes/folder/${encodeURIComponent(f.id)}/"><span class="note-folder-name">${f._share?'♧ ':''}${esc(f.name)}</span> <span class="note-folder-count">${notes.filter(n=>!n.deleted&&n.folder===f.id).length}</span></a><button data-op="folder-menu" data-id="${esc(f.id)}" aria-label="Actions for ${esc(f.name)}">•••</button></div>`+folderTree(f.id,depth+1)).join('');
 let side='<h2>Folders</h2><a data-note-drop="" href="/notes/">All iCloud <span>'+notes.filter(n=>!n.deleted).length+'</span></a>'+folderTree()+(notes.some(n=>n.deleted)?'<a href="/notes/recently-deleted/">Recently Deleted</a>':'')+'<button data-op="new-folder">＋ New Folder</button><section id="note-tags" aria-label="Tag Browser"></section>';
 let tools=(trash?'<button data-op="recover-note" '+(!activeEntity?'disabled':'')+'>Recover</button><button data-op="delete-note" aria-label="Delete note permanently" '+(!activeEntity?'disabled':'')+'>♲</button>':'<button data-op="new-note" aria-label="Create a note">▧</button><button data-op="delete-note" aria-label="Delete note">♲</button><button data-op="note-style" aria-label="Text formatting">Aa</button><button data-op="note-checklist" aria-label="Add checklist">☑</button><button data-op="note-table" aria-label="Add table">▦</button>')+(!trash?'<button data-op="share-note" aria-label="'+(activeEntity?._share?'View Participants':'Share Note')+'" '+(!activeEntity?'disabled':'')+'>♧</button>':'')+'<span class="spacer"></span>';
 noteFrame(side,tools);renderNoteTags();
 function list(){
  const q=document.querySelector('#note-search').value.toLowerCase(),filtered=visible.filter(n=>(n.title+' '+n.body).toLowerCase().includes(q));
  const row=n=>`<button draggable="true" data-note-drag="notes" class="note-row ${n===activeEntity?'active':''}" data-op="open-note" data-id="${esc(n.id)}"><strong>${n._share?'♧ ':''}${noteChanged(n)?'<span class="note-changed" aria-label="Updated by another participant">●</span> ':''}${n.pinned?'⌖ ':''}${esc(n.title)}</strong><small>${esc((n.body||'').slice(0,60))}</small><small>${esc(folders.find(f=>f.id===n.folder)?.name||'Notes')}</small>${n._share&&n._modified?'<small>'+esc(new Date(n._modified*1000).toLocaleString())+'</small>':''}</button>`;
  const pinned=filtered.filter(n=>n.pinned),ordinary=filtered.filter(n=>!n.pinned);
  document.querySelector('#note-list').innerHTML=(!trash&&pinned.length?'<h3 class="note-section-title">Pinned</h3>'+pinned.map(row).join('')+(ordinary.length?'<h3 class="note-section-title">Notes</h3>'+ordinary.map(row).join(''):''):filtered.map(row).join(''))+`<p class="hint">${filtered.length} Notes</p>`;
 }
 list();document.querySelector('#note-search').oninput=()=>{history.replaceState({...history.state,noteSearch:document.querySelector('#note-search').value},'',location.href);list()};
 const layout=document.querySelector('.app-layout');
 layout.addEventListener('contextmenu',event=>{const row=event.target.closest('.note-row');if(!row||trash||noteLayoutMode()==='one')return;event.preventDefault();const note=notes.find(n=>n.id===row.dataset.id);showDialog(note.title,`<button data-op="context-pin-note" data-id="${esc(note.id)}">${note.pinned?'Unpin Note':'Pin Note'}</button><button data-action="close">Done</button>`)});
 layout.addEventListener('click',async event=>{const link=event.target.closest('aside a');if(!link||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;event.preventDefault();try{await navigateNotes(link.getAttribute('href'),{notesView:{pane:'list',side:'list',popup:noteLayoutMode()==='overlay'}})}catch(error){showDialog('Unable to save',`<p>${esc(error.message)}</p><button data-action="close">OK</button>`)}});
 let dragging=null;
 layout.addEventListener('dragstart',event=>{const item=event.target.closest('[data-note-drag]');if(item){dragging={kind:item.dataset.noteDrag,id:item.dataset.id};event.dataTransfer.setData('application/x-icloud-note',JSON.stringify(dragging));event.dataTransfer.effectAllowed='move'}});
 layout.addEventListener('dragend',()=>{dragging=null});
 layout.addEventListener('dragover',event=>{const target=event.target.closest('[data-note-drop]');if(target&&dragging&&validNoteDrop(dragging.kind,dragging.id,target.dataset.noteDrop||null)){event.preventDefault();event.dataTransfer.dropEffect='move'}});
 layout.addEventListener('drop',async event=>{const target=event.target.closest('[data-note-drop]'),raw=event.dataTransfer.getData('application/x-icloud-note');if(!target||!raw)return;event.preventDefault();try{const item=JSON.parse(raw),folder=target.dataset.noteDrop||null;if(validNoteDrop(item.kind,item.id,folder))await moveNoteItem(item.kind,item.id,folder)}catch(error){showDialog(error.message==='Notes is limited to 5 levels of folders.'?'Folder can’t be moved.':'Unable to move',`<p>${esc(error.message)}</p><button data-action="close">OK</button>`)}});
 const n=activeEntity,readOnly=trash||n?._share?.permission==='read';if(n&&n.order>5&&id){entityBoundary('Notes',n,'/notes/');return}let detail=document.querySelector('#note-detail');detail.innerHTML=n?`<div class="note-heading"><input id="note-title" aria-label="Note title" ${readOnly?'readonly':''} value="${esc(n.title)}"><span id="note-save-state"></span></div><div id="note-editor" contenteditable="${!readOnly}" role="textbox" aria-label="Note content" aria-multiline="true">${n.html?safeNoteHTML(n.html):esc(n.body||'')}</div>`:'<div class="empty"><h2>No Notes</h2></div>';
 if(readOnly)detail.querySelectorAll('input[type=checkbox]').forEach(checkbox=>checkbox.disabled=true);
 if(n&&!readOnly){
  const save=()=>{
   const editor=document.querySelector('#note-editor');
   const payload={...n,body:editor.innerText,html:safeNoteHTML(editor.innerHTML),title:document.querySelector('#note-title').value};
   let job=noteSaveJobs.get(n.id);if(!job){job={entity:n};noteSaveJobs.set(n.id,job)}
   job.entity=n;job.payload=payload;clearTimeout(job.timer);document.querySelector('#note-save-state').textContent='Saving…';
   job.timer=setTimeout(()=>flushNoteSave(n.id).catch(()=>{}),300);
  };
  document.querySelector('#note-editor').oninput=event=>{save();suggestNoteTags(event.currentTarget)};document.querySelector('#note-title').oninput=save;
 }
 configureNoteSharing(readOnly);applyNoteLayout();
}

async function editEvent(existing={},date=calendarDateKey(calendarDate),occurrence=undefined){
 if(existing.id){existing=await api('/api/event-occurrence/'+encodeURIComponent(existing.id)+(occurrence?'?occurrence='+encodeURIComponent(occurrence):''));occurrence=existing._edit_occurrence;delete existing._edit_occurrence}
 occurrence=existing._recurrence_date||occurrence;eventEditorContext={existing,occurrence};
 const attachments=(existing.attachments||[]).map(a=>({...a}));
 if(existing._invitation&&existing._sharing?.permission!=='write')return eventInvitationDialog(existing._invitation.token);
 if(existing._sharing?.permission==='read'){showDialog(existing.title,`<p>${esc(calendarDateTimeLabel(existing.start))} – ${esc(calendarDateTimeLabel(existing.end))}</p>${existing.allDay?'':'<p>Time Zone: '+esc(existing.timezone||'Floating')+'</p>'}<p>${esc(existing.location)}</p><p>${esc(existing.notes)}</p><dl><dt>Repeat</dt><dd>${esc(existing.repeat||'Never')}</dd><dt>Alert</dt><dd>${esc(existing.alert||'None')}</dd><dt>2nd Alert</dt><dd>${esc(existing.second_alert||'None')}</dd><dt>Invitees</dt><dd>${esc((existing.invitees||[]).join(', '))}</dd><dt>Responses</dt><dd>${(existing._responses||[]).map(p=>esc(p.email)+' · '+esc(eventReplyLabels[p.status]||p.status)).join('<br>')}</dd><dt>URL</dt><dd>${esc(existing.url||'')}</dd></dl><div class="event-attachments">${eventAttachmentList(attachments,existing.id)}</div><p>Read-Only</p><button data-action="close">Done</button>`);return}
 if(!writableCalendars().length){showDialog('Calendar','<p>No editable calendar is available.</p><button data-action="close">Done</button>');return}
 const select=(name,label,values,selected)=>`<label>${label}<select name="${name}" aria-label="${label}">${values.map(value=>`<option ${value===selected?'selected':''}>${value}</option>`).join('')}</select></label>`;
 const fields=(existing._invitation?`<button type="button" data-event-reply="open" data-token="${esc(existing._invitation.token)}">Your Reply: ${esc(eventReplyLabels[existing._invitation.status])}</button>`:'')+field('title','Title',existing.title)+field('location','Location or Video Call',existing.location)+`<label>Calendar<select name="calendar" aria-label="Calendar">${writableCalendars().map(c=>`<option value="${c.id}" ${c.id===(existing.calendar||calendarPreferences.effective_default_calendar)?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label><label class="calendar-toggle"><input type="checkbox" name="allDay" ${existing.allDay?'checked':''}>All Day</label>`+eventTimezoneField(existing)+calendarDateTimeField('start','Starts',existing.start||date+'T09:00',existing.allDay)+calendarDateTimeField('end','Ends',existing.end||date+'T10:00',existing.allDay)+select('repeat','Repeat',['Never','Every Day','Every Week','Every Month','Every Year'],existing.repeat||'Never')+calendarAlertSelect('alert','Alert',existing.alert??(existing.id?'None':calendarPreferences.default_alert))+calendarAlertSelect('second_alert','2nd Alert',existing.second_alert||'None')+field('invitees','Invitees',(existing.invitees||[]).join(', '))+((existing._responses||[]).length?'<div class="event-responses">'+existing._responses.map(p=>'<p>'+esc(p.email)+' · '+esc(eventReplyLabels[p.status]||p.status)+'</p>').join('')+'</div>':'')+field('url','URL',existing.url,'url')+`<label>Notes<textarea name="notes">${esc(existing.notes)}</textarea></label><fieldset><legend>Attachments</legend><div id="event-attachments"></div><label>Add Attachments<input type="file" id="event-attachment-input" multiple aria-label="Add Attachments"></label><p id="event-attachment-status" role="status"></p></fieldset>`;
 formDialog(existing.id?'Edit Event':'Add Event',fields,async f=>{
  readCalendarDates(f);if(!f.title.trim())throw Error('Enter an event title.');if(f.end<f.start)throw Error('The end date must follow the start date.');
  const invitees=f.invitees.split(',').map(x=>x.trim()).filter(Boolean);if(invitees.some(x=>!/^\S+@\S+\.\S+$/.test(x)))throw Error('Enter an email address for each invitee.');
  const payload={...existing,...f,timezone:f.timezone||existing.timezone||calendarTimeSettings.timezone,allDay:!!f.allDay,invitees,attachments};
  if(existing.id&&!eventValuesChanged(existing,payload))return;
  if(existing.id&&existing.repeat&&existing.repeat!=='Never'){const scope=await chooseEventEditScope(existing,payload);if(!scope)return;payload.scope=scope;payload.occurrence=occurrence}
  if(!await confirmEventUpdate(existing,payload))return false;
  await storeItem('events',payload);await calendarPage();
 },existing.id?'<button type="button" data-op="delete-event" data-id="'+existing.id+'">Delete</button>':'');
 document.querySelector('#edit-form [type="submit"]').textContent=existing.id?'Done':'Add';
 setupEventAttachments(existing,attachments);
 setupCalendarDateFields();
}


async function settingsPage(path){let accountData=session.account;let settings=await items('settings');let preferences=settings.find(x=>x.id==='preferences')||{id:'preferences',language:'English',timezone:'America/Toronto'};activeEntity=preferences;let title=path.startsWith('/storage')?'Your Storage':path.startsWith('/plan')?'Your Plan':path.startsWith('/recovery')?'Data Recovery':path.includes('/account')?'Apple Account':'iCloud Settings';let content='';if(title==='Your Plan')content='<h2>Standard</h2><strong>5 GB</strong><p>Free</p><a class="primary" href="/icloud-plus/">Learn about iCloud+</a>';else if(title==='Your Storage')content='<h2>iCloud Storage</h2><strong>5 GB</strong><div class="storage-bar"></div><p>Photos · iCloud Drive · Notes</p><a href="/plan/">Manage Plan</a>';else if(title==='Data Recovery')content=['Restore Files','Restore Contacts','Restore Calendars','Restore Bookmarks'].map(x=>`<button class="settings-row" data-op="restore" data-label="${x}">${x} ›</button>`).join('');else content=`<div class="avatar">${esc(accountData.display_name[0])}</div><h2>${esc(accountData.display_name)}</h2><p>${esc(accountData.email_normalized)}</p><a href="/settings/account/">Manage Apple Account</a><button class="settings-row" data-op="preferences">Language and Time Zone <span>${esc(preferences.language)}</span></button><a class="settings-row" href="/plan/">Your Plan ›</a><a class="settings-row" href="/storage/">Your Storage ›</a><a class="settings-row" href="/recovery/">Data Recovery ›</a><button class="settings-row" data-op="signout-all">Sign Out of All Browsers</button>`;root.innerHTML=header()+`<main class="settings-page"><h1>${title}</h1><section class="settings-card">${content}</section><a href="/home/">Back to iCloud</a></main>`+footer()}

function driveParent(){return new URLSearchParams(location.search).get('folder')||null}
let driveContext=null,pendingDriveAction=null;
function fileActions(file){
 activeEntity=file;
 const buttons=file.deleted?'<button data-op="recover-file">Recover</button><button data-op="permanently-delete-file">Delete</button>':'<button data-op="rename-file">Rename</button><button data-move-file>Move</button><button data-op="delete-file">Delete</button>';
 showDialog(file.name,buttons+'<button data-action="close">Done</button>');
}
async function driveAction(action,ids){
 if(!ids.length)return;
 if(action!=='recover'){
  pendingDriveAction={action,ids,kind:driveContext.kind};
  showDialog(action==='trash'?'Delete Files?':'Permanently Delete Files?',`<p>${action==='trash'?'Files you delete from iCloud Drive are recoverable for 30 days.':'You can’t recover or restore files you permanently remove.'}</p><div class="actions"><button data-action="close">Cancel</button><button class="primary" data-op="confirm-file-action">Delete</button></div>`);return;
 }
 await api('/api/files/trash',{action,ids,kind:driveContext.kind});closeDialog();await documentPage(location.pathname);
}
async function documentPage(path){
 const work=/^\/(pages|numbers|keynote)\//.exec(path)?.[1],kind=work?'documents':'files';
 if(work&&/\/(create|edit)\/$/.test(path))return workEditorPage(work,path.endsWith('/create/')); 
 if(work&&!((await items('settings')).find(s=>s.id==='welcome-'+work)?.complete)){workWelcome(work,1);return}
 const all=(await items(kind)).filter(f=>!work||f.app===work),parent=driveParent();
 const tab=path.includes('browse')?'Browse':path.includes('shared')?'Shared':path.includes('recently-deleted')?'Recently Deleted':'Recents';
 const folder=all.find(f=>f.id===parent&&f.folder&&!f.deleted);
 let data=all.filter(f=>tab==='Recently Deleted'?f.deleted:!f.deleted);
 if(tab==='Shared')data=data.filter(f=>f.shared);
 else if(tab==='Browse')data=data.filter(f=>(f.parent||null)===(folder?.id||null));
 else if(tab==='Recents')data=data.filter(f=>!f.folder);
 data.sort((a,b)=>(a.order||0)-(b.order||0));
 driveContext={kind,app:work||null,data,selected:new Set()};
 const label=work?work[0].toUpperCase()+work.slice(1):'Drive',prefix=work||'iclouddrive';
 const side='<h2>'+label+'</h2>'+['Recents','Browse','Shared','Recently Deleted'].map((n,i)=>`<a class="${tab===n?'active':''}" href="/${prefix}/${i===0?'':n.toLowerCase().replaceAll(' ','-')+'/'}">${n}</a>`).join('')+(work?'':'<h3>Favorites</h3><a href="/'+prefix+'/browse/?folder=downloads">Downloads</a>');
 const trash=tab==='Recently Deleted';
 const toolbar=(folder?'<a href="/'+prefix+'/browse/" aria-label="Back to Browse">‹</a>':'')+'<h1>'+esc(folder?.name||tab)+'</h1><span class="spacer"></span>'+(trash?'<button data-op="file-trash-selected" data-file-action="recover" disabled>Recover</button><button data-op="file-trash-selected" data-file-action="delete" disabled>Delete</button><button data-op="file-trash-all" data-file-action="recover" '+(!data.length?'disabled':'')+'>Recover All</button><button data-op="file-trash-all" data-file-action="delete" '+(!data.length?'disabled':'')+'>Delete All</button>':'<button data-op="upload-file" aria-label="Upload">↑</button><button data-op="new-drive-folder" aria-label="New folder">▱＋</button><button data-op="file-trash-selected" data-file-action="trash" disabled>Delete</button>'+(work?`<button data-op="new-work-document" data-app="${work}" aria-label="Create a new ${label} document">＋</button>`:''))+'<input id="file-search" placeholder="Search" aria-label="Search files"><button data-op="file-view" aria-label="View options">▦</button>';
 appFrame(label,side,'<div id="files-list"></div><div class="file-count" aria-live="polite"></div>',toolbar);
 function render(){
  let q=document.querySelector('#file-search').value.toLowerCase(),visible=data.filter(f=>f.name?.toLowerCase().includes(q));
  document.querySelector('#files-list').innerHTML=visible.length?visible.map(f=>`<div class="list-row"><input type="checkbox" data-file-select="${f.id}" aria-label="Select ${esc(f.name)}" ${driveContext.selected.has(f.id)?'checked':''}><button data-op="open-file" data-id="${f.id}">${f.folder?'▱':'▤'} ${esc(f.name)}</button><span>${esc(f.modified||'')}</span><button data-op="file-menu" data-id="${f.id}" aria-label="Actions for ${esc(f.name)}">•••</button></div>`).join(''):`<div class="empty"><h2>${q?'No Results':tab==='Recently Deleted'?'No Recently Deleted Items':tab==='Shared'?'No Shared Items':'No items'}</h2>${!q&&tab==='Recents'?'<p>Files which you’ve opened recently will appear here.</p>':''}</div>`;
  document.querySelectorAll('[data-file-select]').forEach(checkbox=>checkbox.onchange=()=>{if(checkbox.checked)driveContext.selected.add(checkbox.dataset.fileSelect);else driveContext.selected.delete(checkbox.dataset.fileSelect);document.querySelectorAll('[data-op="file-trash-selected"]').forEach(button=>button.disabled=!driveContext.selected.size)});
  document.querySelector('.file-count').textContent=visible.length+' '+(visible.length===1?'item':'items');
 }
 render();document.querySelector('#file-search').oninput=render;
 const item=new URLSearchParams(location.search).get('item');if(item)openDriveFile(item,false);
}
function workWelcome(work,step){
 const label=work[0].toUpperCase()+work.slice(1),object=work==='pages'?'document':work==='numbers'?'spreadsheet':'presentation';
 root.innerHTML=header(label)+`<main class="work-welcome"><img src="/static/icons/${work}.png" alt=""><h1>${step===1?'Welcome to ':'Get Started with '}${label}</h1>${step===1?'':`<section><h2>Collaboration</h2><p>Edit a ${object} with others at the same time on Mac, iPad, iPhone, or iCloud.com.cn.</p><h2>Easy Sharing</h2><p>Send a link to your ${object} so others always have the latest version.</p><h2>Works with the Latest</h2><p>${label} for iCloud works seamlessly with the latest ${label} apps.</p></section>`}<button class="primary" data-op="${step===1?'work-welcome-next':'work-welcome-use'}" data-app="${work}">${step===1?'Continue':'Use '+label}</button></main>`;
}
function openDriveFile(id,push=true){
 const data=appData[driveContext?.kind]||[],f=data.find(f=>f.id===id);if(!f)return;
 if(f.deleted){fileActions(f);return}
 if(f._editor){navigate('/'+f.app+'/edit/?item='+encodeURIComponent(f.id));return}
 if(f.folder){navigate(location.pathname.replace(/(?:shared|recently-deleted)\//,'browse/').replace(/^\/iclouddrive\/$/,'/iclouddrive/browse/')+'?folder='+encodeURIComponent(f.id));return}
 if(push){const url=new URL(location.href);url.searchParams.set('item',id);history.pushState(null,'',url.pathname+url.search)}
 const preview='/api/files/'+encodeURIComponent(f.id)+'/preview',download='/api/files/'+encodeURIComponent(f.id)+'/download';
 let content=f.type?.startsWith('image/')?`<img class="file-preview" src="${preview}" alt="${esc(f.name)}">`:['application/pdf','text/plain'].includes(f.type)?`<iframe class="file-preview" src="${preview}" title="${esc(f.name)}"></iframe>`:'<p>No preview is available for this file.</p>';
 showDialog(f.name,content+`<div class="actions"><a href="${download}">Download a Copy</a><button data-op="close-file-preview">Done</button></div>`);modal.classList.add('file-dialog');
}

async function renderApplication(path){if(path.startsWith('/account/manage'))return accountPage();if(path.startsWith('/contacts/'))return contactsPage();if(path.startsWith('/notes/share/'))return noteInvitationPage();if(path.startsWith('/notes/'))return notesPage();if(path.startsWith('/reminders/share/'))return reminderInvitationPage();if(path.startsWith('/reminders/')){await remindersPage();const query=new URLSearchParams(location.search);if(query.has('new'))beginReminder();else if(query.has('item')){const item=reminderContext.reminders.find(r=>r.id===query.get('item'));if(item)editReminder(item)}return}if(path.startsWith('/calendar/invitation/'))return eventInvitationPage();if(path.startsWith('/calendar/share/'))return calendarInvitationPage();if(path.startsWith('/calendar/')){await calendarPage();let query=new URLSearchParams(location.search);if(query.has('new'))editEvent();else if(query.has('item')){let event=appData.events.find(e=>e.id===query.get('item'));if(event){const occurrence=query.get('occurrence');if(occurrence&&/^\d{4}-\d{2}-\d{2}$/.test(occurrence)){calendarDate=new Date(occurrence+'T12:00:00');await calendarPage()}await editEvent(event,undefined,occurrence||undefined)}}return}if(path.startsWith('/find/'))return findPage();if(/^\/(settings|plan|storage|recovery)/.test(path))return settingsPage(path);if(/^\/(iclouddrive|pages|numbers|keynote)/.test(path))return documentPage(path)}

document.addEventListener('click',async event=>{let el=event.target.closest('[data-op]');if(!el)return;let op=el.dataset.op,id=el.dataset.id;try{
 if(op==='work-welcome-next'){workWelcome(el.dataset.app,2);return}if(op==='work-welcome-use'){await storeItem('settings',{id:'welcome-'+el.dataset.app,complete:true});await documentPage(location.pathname);return}
 if(op==='share-note')return openNoteSharing('notes',activeEntity);
 if(op==='delete-note'&&activeEntity?._share)return await confirmSharedNoteDelete(activeEntity);
 if(op==='new-note')return await createNote();if(op==='open-note'){const query=new URLSearchParams(location.search);query.set('item',id);return await navigateNotes(location.pathname+'?'+query,{noteSearch:document.querySelector('#note-search')?.value||''})}if((op==='delete-note'||op==='recover-note')&&activeEntity){
  if(root.inert)return;const note=activeEntity;root.inert=true;
  try{
   await flushNoteSave(note.id);
   if(op==='recover-note')await api('/api/notes/'+note.id+'/recover',{});
   else if(note.deleted)await removeItem('notes',note.id);
   else await storeItem('notes',{...note,deleted:true});
   history.replaceState(null,'',op==='recover-note'?'/notes/folder/notes/?item='+note.id:location.pathname);
   await notesPage();
  }finally{root.inert=false}
  return;
 }if(op==='new-folder')return formDialog('New Folder',field('name','Name'),async f=>{if(!f.name.trim())throw Error('Enter a folder name.');await storeItem('folders',{...f,parent:el.dataset.parent||null});await notesPage()});
 if(op==='note-tag'||op==='clear-note-tags'){await flushNoteSave(activeEntity?.id);const selected=new Set(new URLSearchParams(location.search).getAll('tag'));if(op==='clear-note-tags')selected.clear();else if(selected.has(el.dataset.tag))selected.delete(el.dataset.tag);else selected.add(el.dataset.tag);const query=new URLSearchParams();for(const tag of selected)query.append('tag',tag);return await navigateNotes('/notes/'+(query.size?'?'+query:''),{notesView:{pane:'list',side:'list',popup:noteLayoutMode()==='overlay'}})}
 if(op==='context-pin-note'){el.disabled=true;try{await flushNoteSave(activeEntity?.id);const note=appData.notes.find(n=>n.id===id);await api('/api/notes/'+encodeURIComponent(id)+'/pin',{pinned:!note.pinned});await notesPage();closeDialog()}finally{if(el.isConnected)el.disabled=false}return}
 if(op==='folder-menu'){const folder=appData.folders.find(f=>f.id===id),received=folder._share&&!folder._share.owner;showDialog(folder.name,`${!folder._share&&noteFolderLevel(id)<5?`<button data-op="new-folder" data-parent="${esc(id)}">New Folder</button>`:''}<button class="folder-sharing-control" data-share="folder" data-id="${esc(id)}">${folder._share?'Manage Participants':'Share Folder'}</button>${id==='notes'?'':`${!received||folder._share.root||folder._share.permission==='write'?`<button data-op="rename-note-folder" data-id="${esc(id)}">Rename Folder</button>`:''}<button data-op="delete-note-folder" data-id="${esc(id)}">Delete Folder</button>`}<button data-action="close">Done</button>`);return}
 if(op==='rename-note-folder'){const folder=appData.folders.find(f=>f.id===id);return formDialog('Rename Folder',field('name','Name',folder.name),async f=>{await storeItem('folders',folder._share&&!folder._share.owner?{id:folder.id,name:f.name}:{...folder,...f});await notesPage()})}
 if(op==='delete-note-folder'){const folder=appData.folders.find(f=>f.id===id);if(!folder||!await confirmNoteFolderDeletion(folder))return;root.inert=true;try{history.replaceState(null,'','/notes/');await notesPage()}finally{root.inert=false}return}

 if(op==='note-style'){showDialog('Text Formatting','<div class="format-options">'+['Bold','Italic','Underline','Strikethrough','Title','Heading','Subheading','Body','Monospaced','Dashed List','Numbered List'].map(x=>`<button data-op="apply-format" data-format="${x}">${x}</button>`).join('')+'</div><button data-action="close">Done</button>');return}if(op==='apply-format'){closeDialog();let editor=document.querySelector('#note-editor');editor?.focus();if(noteSelection&&editor?.contains(noteSelection.commonAncestorContainer)){const selection=getSelection();selection.removeAllRanges();selection.addRange(noteSelection)}const map={Bold:'bold',Italic:'italic',Underline:'underline',Strikethrough:'strikeThrough','Dashed List':'insertUnorderedList','Numbered List':'insertOrderedList'};let f=el.dataset.format;document.execCommand(map[f]||'formatBlock',false,map[f]?null:({Title:'h1',Heading:'h2',Subheading:'h3',Body:'div',Monospaced:'pre'})[f]);editor?.dispatchEvent(new InputEvent('input'));return}if(op==='note-checklist'||op==='note-table'){let editor=document.querySelector('#note-editor');editor?.focus();document.execCommand('insertHTML',false,op==='note-checklist'?'<div><input type="checkbox" contenteditable="false"> </div>':'<table border="1"><tbody><tr><td> </td><td> </td></tr><tr><td> </td><td> </td></tr></tbody></table>');editor?.dispatchEvent(new InputEvent('input'));return}
 if(op==='new-event')return editEvent({},el.dataset.date);if(op==='edit-event')return editEvent(appData.events.find(e=>e.id===id),undefined,el.dataset.occurrence);if(op==='delete-event')return deleteEventOccurrence();if(op==='calendar-prev'||op==='calendar-next'){if(location.pathname.includes('month')){calendarDate.setDate(1);calendarDate.setMonth(calendarDate.getMonth()+(op==='calendar-prev'?-1:1))}else calendarDate.setDate(calendarDate.getDate()+(op==='calendar-prev'?-1:1)*(location.pathname.includes('day')?1:7));return calendarPage()}if(op==='calendar-today'){calendarDate=new Date();return calendarPage()}if(op==='new-calendar')return formDialog('New Calendar',field('name','Name')+field('color','Color','#42b75b','color'),async f=>{await storeItem('calendars',f);await calendarPage()});if(op==='calendar-inbox')return calendarInbox();if(op==='calendar-settings')return calendarSettings();
 if(op==='find-device'){history.pushState(null,'','/find/?device='+id);return findPage()}if(op==='find-back'){history.pushState(null,'','/find/');return findPage()}if(op==='map-type'){showDialog('Map','<p>Standard</p><button data-action="close">Done</button>');return}if(op==='device-action')return await openDeviceAction(el.dataset.actionName);
 if(op==='preferences')return formDialog('Language and Time Zone',`<label>Language<select name="language"><option>English</option><option>简体中文</option></select></label>`+field('timezone','Time Zone',activeEntity.timezone),async f=>{await storeItem('settings',{...activeEntity,...f});await settingsPage(location.pathname)});if(op==='restore'){if(el.dataset.label==='Restore Files')return await restoreFiles();if(el.dataset.label==='Restore Contacts')return await contactArchives();if(el.dataset.label==='Restore Calendars')return await calendarArchives();showDialog(el.dataset.label,'<p>No Archives Available</p><button data-action="close">Done</button>');return}if(op==='signout-all'){await api('/api/auth/logout-all',{});navigate('/');return}
 if(op==='file-trash-selected')return driveAction(el.dataset.fileAction,[...driveContext.selected]);if(op==='file-trash-all')return driveAction(el.dataset.fileAction,driveContext.data.map(f=>f.id));if(op==='recover-file')return driveAction('recover',[activeEntity.id]);if(op==='permanently-delete-file')return driveAction('delete',[activeEntity.id]);if(op==='confirm-file-action'){await api('/api/files/trash',pendingDriveAction);pendingDriveAction=null;closeDialog();return documentPage(location.pathname)}
 if(op==='new-drive-folder')return formDialog('New Folder',field('name','Name'),async f=>{if(!f.name.trim())throw Error('Enter a folder name.');await storeItem(driveContext.kind,{...f,...(driveContext.app?{app:driveContext.app}:{}),folder:true,parent:driveParent()});await documentPage(location.pathname)});if(op==='file-view'){document.querySelector('#files-list').classList.toggle('file-grid');return}if(op==='new-work-document'){window.open('/'+el.dataset.app+'/create/'+(driveParent()?'?folder='+encodeURIComponent(driveParent()):''),'_blank','noopener');return}if(op==='upload-file'){uploadDriveFile();return}if(op==='close-file-preview'){modal.classList.remove('file-dialog');closeDialog();let url=new URL(location.href);url.searchParams.delete('item');history.replaceState(null,'',url.pathname+url.search);return}if(op==='open-file'){openDriveFile(id);return}if(op==='file-menu'){activeEntity=appData.files?.find(f=>f.id===id)||appData.documents?.find(f=>f.id===id);fileActions(activeEntity);return}if(op==='rename-file')return formDialog('Rename',field('name','Name',activeEntity.name),async f=>{await storeItem(activeEntity.app?'documents':'files',{...activeEntity,...f});await documentPage(location.pathname)});if(op==='delete-file')return driveAction('trash',[activeEntity.id]);
 }catch(err){showDialog('Unable to complete request',`<p>${esc(err.message)}</p><button data-action="close">OK</button>`)}});

document.addEventListener('selectionchange',()=>{const selection=getSelection(),editor=document.querySelector('#note-editor');if(selection.rangeCount&&editor?.contains(selection.anchorNode))noteSelection=selection.getRangeAt(0).cloneRange()});
document.addEventListener('change',event=>{if(event.target.matches('#note-editor input[type=checkbox]')){event.target.toggleAttribute('checked',event.target.checked);document.querySelector('#note-editor').dispatchEvent(new InputEvent('input'))}});
