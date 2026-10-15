'use strict';
(()=>{
 const host=document.createElement('div');host.className='pp-local';document.body.append(host);
 const style=document.createElement('link');style.rel='stylesheet';style.href='/local-ui.css';document.head.append(style);
 const projectIds=new Map(),projectNames=new Map();
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 async function api(path,options={}){const r=await fetch('/api/'+path,options);if(!r.ok){let j;try{j=await r.json()}catch{}throw Error(j?.detail||'Request failed')}return r}
 function dialog(title,content){
  host.querySelector('dialog')?.remove();const d=document.createElement('dialog');d.innerHTML='<button class="close" aria-label="Close">×</button><h2>'+esc(title)+'</h2>'+content+'<p class="error" role="alert"></p>';host.append(d);d.querySelector('.close').onclick=()=>d.close();d.addEventListener('close',()=>d.remove());d.showModal();return d
 }
 function notice(title,message){dialog(title,'<p>'+esc(message)+'</p>')}
 async function signedIn(){try{const status=await(await api('session')).json();if(status.user)return true;throw Error('Login required')}catch{dialog('PeaDrive','<p>Log in to save your projects and open them again later.</p><div class="actions"><a href="/account">Log In</a><a href="/account#register">Create an account</a></div>');return false}}
 async function save(){
  if(!await signedIn())return;
  let result;try{result=window.PhotopeaBridge?.savePSD();if(!result)throw Error('Create or open a document first.')}catch(e){notice('PeaDrive',e.message);return}
  const d=dialog('Save to PeaDrive','<form><label for="project-name">Name</label><input id="project-name" name="name" maxlength="180" required value="'+esc(projectNames.get(result.documentId)||result.name)+'"><div class="actions"><button class="primary" type="submit">Save</button><button type="button" id="save-copy">Save a copy</button></div></form>');
  const submit=async(copy)=>{const b=d.querySelector('button[type=submit]');b.disabled=true;try{let name=d.querySelector('input').value.trim();if(!name.toLowerCase().endsWith('.psd'))name+='.psd';const id=copy?null:projectIds.get(result.documentId);const r=await api('projects'+(id?'/'+id:'')+'?name='+encodeURIComponent(name),{method:id?'PUT':'POST',headers:{'Content-Type':'application/octet-stream'},body:result.buffer});const savedProject=await r.json();if(!copy){projectIds.set(result.documentId,savedProject.id);projectNames.set(result.documentId,savedProject.name||name)}d.close();notice('PeaDrive','Project saved.')}catch(e){d.querySelector('.error').textContent=e.message}finally{b.disabled=false}};
  d.querySelector('form').onsubmit=e=>{e.preventDefault();submit(false)};d.querySelector('#save-copy').onclick=()=>submit(true);
 }
 async function drive(){
  if(!await signedIn())return;let data;try{data=await(await api('projects')).json()}catch(e){notice('PeaDrive',e.message);return}
  const d=dialog('PeaDrive','<p>'+Math.round(data.used/1000000)+' MB / 500 MB</p><div class="actions"><button id="drive-save">Save current document</button><a href="/account">Account</a></div><div id="project-list"></div>');d.querySelector('#drive-save').onclick=()=>{d.close();save()};
  const list=d.querySelector('#project-list');if(!data.projects.length){list.innerHTML='<p>No projects yet.</p>';return}
  const table=document.createElement('table');list.append(table);
  for(const project of data.projects){const tr=document.createElement('tr');tr.innerHTML='<td><button class="project-name">'+esc(project.name)+'</button><small style="display:block">'+Math.round(project.size/1024)+' KB</small></td><td><div class="actions"><button data-action="rename">Rename</button><a href="/api/projects/'+project.id+'" download>Download</a><button data-action="delete">Delete</button></div></td>';table.append(tr);
   tr.querySelector('.project-name').onclick=async()=>{try{const buffer=await(await api('projects/'+project.id)).arrayBuffer();if(!window.PhotopeaBridge)throw Error('Wait for the editor to finish loading.');const documentId=await window.PhotopeaBridge.open(buffer,project.name);projectIds.set(documentId,project.id);projectNames.set(documentId,project.name);d.close()}catch(e){d.querySelector('.error').textContent=e.message}};
   tr.querySelector('[data-action=rename]').onclick=()=>{const name=prompt('Project name',project.name);if(!name)return;api('projects/'+project.id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})}).then(async response=>{const updated=await response.json();for(const [doc,id] of projectIds)if(id===project.id)projectNames.set(doc,updated.name||name);return drive()}).catch(e=>d.querySelector('.error').textContent=e.message)};
   tr.querySelector('[data-action=delete]').onclick=()=>{if(!confirm('Delete "'+project.name+'"?'))return;api('projects/'+project.id,{method:'DELETE'}).then(()=>{for(const [doc,id] of projectIds)if(id===project.id)projectIds.delete(doc);drive()}).catch(e=>d.querySelector('.error').textContent=e.message)};
  }
 }
 const toolbar=document.createElement('div');toolbar.className='toolbar';toolbar.hidden=true;toolbar.innerHTML='<button title="Open saved projects">PeaDrive</button><button title="Save the active document to your account">Save to PeaDrive</button>';host.append(toolbar);toolbar.children[0].onclick=drive;toolbar.children[1].onclick=save;
 setInterval(()=>accessible(),700);
 document.addEventListener('click',e=>{if(host.contains(e.target))return;let text=e.target.textContent?.trim();const labels=['PeaDrive','Log In','Templates','Generate','Video?','PeaGames','Vectorpea','Jampea','Go Premium','Team Settings','Distributors','AI credits','Dropbox','OneDrive','Google Drive','Pick any File','Plugins','Gallery'];for(let node=e.target,depth=0;node&&depth<5;node=node.parentElement,depth++){const value=node.getAttribute?.('title')||node.textContent?.trim();if(labels.includes(value)){text=value;break}}if(text==='PeaDrive'){e.preventDefault();e.stopImmediatePropagation();drive()}else if(text==='Log In'){e.preventDefault();e.stopImmediatePropagation();location.assign('/account')}else if(['Templates','Generate','Video?','PeaGames','Vectorpea','Jampea','Go Premium','Team Settings','Distributors','AI credits','Dropbox','OneDrive','Google Drive','Pick any File','Plugins','Gallery'].includes(text)){e.preventDefault();e.stopImmediatePropagation();notice(text,'This feature is outside the core editing scope.')}},true);

 // Native editor tools activate on pointer-down/up; give focused tools equivalent keyboard activation.
 document.addEventListener('keydown',e=>{
  const tool=e.target.closest?.('button.toolbtn');
  if(!tool||!['Enter',' '].includes(e.key)||e.repeat||tool.getAttribute('aria-disabled')==='true')return;
  e.preventDefault();e.stopImmediatePropagation();const r=tool.getBoundingClientRect();
  const EventType=window.PointerEvent||MouseEvent,prefix=window.PointerEvent?'pointer':'mouse';
  for(const phase of ['down','up'])tool.dispatchEvent(new EventType(prefix+phase,{bubbles:true,button:0,buttons:phase==='down'?1:0,clientX:r.x+r.width/2,clientY:r.y+r.height/2,pointerType:'mouse',isPrimary:true}));
 },true);
 const accessible=()=>{const ready=!!(document.querySelector('canvas')||window.PhotopeaBridge);toolbar.hidden=!ready;toolbar.style.display=ready?'flex':'none';for(const el of document.querySelectorAll('span.bhover,div[style*="cursor: pointer"]')){
  if(el.closest('.pp-local')||el.hasAttribute('role')||!['New Project','Open From Computer','Templates','Generate','Video?','Home','This Device','PeaDrive','Dropbox','OneDrive','Google Drive','Pick any File','PeaGames','Photopea','Vectorpea','Jampea'].includes(el.textContent.trim()))continue;
  el.setAttribute('role','button');el.tabIndex=0;el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();el.click()}});
 }
 // Mirror the original editor's visual tool state for keyboard and screen-reader users.
 // These attributes describe existing state; they never activate or disable an operation.
 for(const el of document.querySelectorAll('button.toolbtn,[role="button"]')){
  if(el.closest('.pp-local'))continue;
  if(el.matches('button.toolbtn')||['Home','Photopea','This Device'].includes(el.textContent.trim())){
   const pressed=String(el.textContent.trim()==='Photopea'||el.classList.contains('active'));
   if(el.getAttribute('aria-pressed')!==pressed)el.setAttribute('aria-pressed',pressed);
  }
 }
 for(const el of document.querySelectorAll('button,input,select,textarea,[role="button"]')){
  if(el.closest('.pp-local'))continue;
  const textWarp=el.tagName==='BUTTON'&&el.textContent.trim()==='Warp'&&document.querySelector('button.toolbtn.active[title^="Type Tool"]');
  const clipping=el.tagName==='BUTTON'&&el.title==='Clipping Mask';
  const doc=(textWarp||clipping)?window.PhotopeaBridge?.document():null;
  if(clipping)el.setAttribute('aria-pressed',String(!!doc?.clippingActive));
  const disabled=!!el.closest('.disabled')||!!(textWarp&&!doc?.textLayerSelected)||!!(clipping&&!doc?.clippingAvailable);
  if(disabled){if(el.getAttribute('aria-disabled')!=='true')el.setAttribute('aria-disabled','true');el.dataset.localDisabledState='true'}
  else if(el.dataset.localDisabledState){el.removeAttribute('aria-disabled');delete el.dataset.localDisabledState}
 }
 };
 new MutationObserver(accessible).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});accessible();
 window.PhotopeaLocalUI={drive,save,notice};
})();
