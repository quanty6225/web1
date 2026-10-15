function eventAttachmentURL(attachment,eventId){return '/api/event-attachments/'+encodeURIComponent(attachment.id)+'/download'+(eventId&&!attachment._pending?'?event='+encodeURIComponent(eventId):'')}
function eventAttachmentList(attachments,eventId,editable=false){return (attachments||[]).map((a,index)=>`<div class="event-attachment"><span aria-hidden="true">📎</span><a href="${esc(eventAttachmentURL(a,eventId))}" download="${esc(a.name)}">${esc(a.name)}</a><small>${Number(a.size).toLocaleString()} bytes</small><button type="button" data-attachment-preview="${esc(eventAttachmentURL(a,eventId))}" data-name="${esc(a.name)}">View ${esc(a.name)}</button>${editable?`<button type="button" data-attachment-remove="${index}" aria-label="Remove ${esc(a.name)}">×</button>`:''}</div>`).join('')}
function setupEventAttachments(existing,attachments){
 const form=document.querySelector('#edit-form'),input=form.querySelector('#event-attachment-input'),list=form.querySelector('#event-attachments'),status=form.querySelector('#event-attachment-status'),submit=form.querySelector('[type=submit]');let uploading=false,saving=false;
 const render=()=>{list.innerHTML=eventAttachmentList(attachments,existing.id,true);list.querySelectorAll('[data-attachment-remove]').forEach(button=>button.onclick=()=>{attachments.splice(Number(button.dataset.attachmentRemove),1);render()})};render();
 input.onchange=async()=>{
  if(saving||uploading)return;uploading=true;submit.disabled=true;input.disabled=true;status.textContent='Uploading…';
  try{
   if(attachments.length+input.files.length>20)throw Error('Choose at most 20 attachments.');
   for(const file of input.files){
    if(/[\\/:*?"<>|]/.test(file.name))throw Error('This filename contains characters that cannot be used in Calendar.');
    if(file.size>20*1024*1024)throw Error('Choose a file smaller than 20 MB.');
    const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('Unable to read the attachment.'));reader.readAsDataURL(file)});
    const item=await api('/api/event-attachments/upload',{name:file.name,content});attachments.push({...item,_pending:true});
   }
   if(form.isConnected){render();status.textContent='Attachments ready.'}
  }catch(error){if(form.isConnected)status.textContent=error.message}
  finally{uploading=false;if(form.isConnected){input.value='';submit.disabled=false;input.disabled=false}}
 };
 const save=form.onsubmit;
 form.onsubmit=async event=>{
  if(uploading||saving){event.preventDefault();return}saving=true;
  const controls=[...form.elements].map(el=>[el,el.disabled]);
  // The original handler reads FormData before its first await.
  const pending=save(event);controls.forEach(([el])=>el.disabled=true);
  try{await pending}finally{saving=false;if(form.isConnected)controls.forEach(([el,disabled])=>el.disabled=disabled)}
 };
}
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-attachment-preview]');if(!button)return;
 const container=button.closest('form,main,dialog');container.querySelector('[data-attachment-view]')?.remove();
 const panel=document.createElement('section');panel.dataset.attachmentView='';panel.className='event-attachment-preview';container.append(panel);
 panel.innerHTML=`<h3>${esc(button.dataset.name)}</h3><p role="status">Loading…</p><button type="button" data-close-preview>Close Preview</button>`;panel.querySelector('[data-close-preview]').onclick=()=>panel.remove();
 try{
  const response=await fetch(button.dataset.attachmentPreview);if(!response.ok){const error=await response.json();throw Error(error.error||error.detail||'Unable to open attachment.')}
  const bytes=new Uint8Array(await response.arrayBuffer());let mime='';
  if(bytes[0]===137&&bytes[1]===80&&bytes[2]===78&&bytes[3]===71)mime='image/png';
  else if(bytes[0]===255&&bytes[1]===216&&bytes[2]===255)mime='image/jpeg';
  else if(String.fromCharCode(...bytes.slice(0,6)).startsWith('GIF8'))mime='image/gif';
  else if(String.fromCharCode(...bytes.slice(0,4))==='RIFF'&&String.fromCharCode(...bytes.slice(8,12))==='WEBP')mime='image/webp';
  const status=panel.querySelector('[role=status]');
  if(mime){const image=document.createElement('img');image.alt=button.dataset.name;const url=URL.createObjectURL(new Blob([bytes],{type:mime}));image.onload=image.onerror=()=>URL.revokeObjectURL(url);image.src=url;status.replaceWith(image)}
  else{
   let text;try{if(bytes.includes(0)||String.fromCharCode(...bytes.slice(0,5))==='%PDF-')throw Error();text=new TextDecoder('utf-8',{fatal:true}).decode(bytes)}catch(error){}
   if(text!==undefined&&bytes.length<1024*1024){const pre=document.createElement('pre');pre.textContent=text;status.replaceWith(pre)}
   else status.textContent='Download this attachment to open it.';
  }
  const link=document.createElement('a');link.href=button.dataset.attachmentPreview;link.download=button.dataset.name;link.textContent='Download';panel.append(link);
 }catch(error){panel.querySelector('[role=status]').textContent=error.message}
});
