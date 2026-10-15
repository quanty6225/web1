let contactsContext=null;
const CONTACT_EXTRA_FIELDS={prefix:'Prefix',middle_name:'Middle Name',suffix:'Suffix',nickname:'Nickname',job_title:'Job Title',department:'Department',birthday:'Birthday',phonetic_first:'Phonetic First Name',phonetic_last:'Phonetic Last Name'};
function contactAvatar(contact,small=false){return contact.avatar?`<img class="${small?'mini-avatar':'avatar'}" src="${esc(contact.avatar)}" alt="${small?'':'Contact photo'}">`:`<div class="${small?'mini-avatar':'avatar'}">${esc(contact.name?.[0]||'')}</div>`}
function contactPath(id=null){const query=new URLSearchParams();if(contactsContext?.list)query.set('list',contactsContext.list);if(id)query.set('item',id);return '/contacts/'+(query.size?'?'+query:'')}
function contactHighlight(value,query=''){
 const text=String(value||'');if(!query)return esc(text);let result='',start=0,index;const lower=text.toLocaleLowerCase(),needle=query.toLocaleLowerCase();
 while((index=lower.indexOf(needle,start))!==-1){result+=esc(text.slice(start,index))+'<mark>'+esc(text.slice(index,index+query.length))+'</mark>';start=index+query.length}return result+esc(text.slice(start));
}
function contactCard(contact,query=''){
 const value=v=>contactHighlight(v,query);
 const sections=[['phones','Phone'],['emails','Email'],['urls','Website'],['related','Related Name']].map(([key,label])=>(contact[key]||[]).map(item=>`<div class="contact-field"><small>${esc(item.label||label)}</small><p>${value(item.value)}</p></div>`).join('')).join('');
 const addresses=(contact.addresses||[]).map(item=>`<div class="contact-field"><small>${esc(item.label||'Address')}</small><p>${['po_box','extended','street','city','region','postal_code','country'].filter(k=>item[k]).map(k=>value(item[k])).join('<br>')}</p></div>`).join('');
 const details=[['nickname','Nickname'],['birthday','Birthday'],['job_title','Job Title'],['department','Department'],['note','Notes']].filter(([key])=>contact[key]).map(([key,label])=>`<div class="contact-field"><small>${label}</small><p>${value(contact[key])}</p></div>`).join('');
 return `<div class="contact-profile">${contactAvatar(contact)}<h1>${value(contact.name)}</h1><p>${value(contact.company)}</p><button data-op="edit-contact">Edit</button><button data-op="delete-contact">Delete Contact</button></div>${sections}${addresses}${details}`;
}
async function contactsPage(){
 const state=await api('/api/contacts/state');
 const data=await items('contacts'),lists=await items('contact_lists'),preferences=(await items('settings')).find(s=>s.id==='contacts')||{id:'contacts',sort:'First Name'};
 const query=new URLSearchParams(location.search),listId=query.get('list'),list=lists.find(l=>l.id===listId),id=query.get('item');
 contactsContext={data,lists,generation:state.generation,list:list?.id||null,preferences,selected:new Set(data.some(c=>c.id===id)?[id]:[]),visible:[]};activeEntity=data.find(c=>c.id===id)||null;
 const name=list?.name||'All Contacts';
 const side='<h2>Contacts</h2><a href="/contacts/" class="'+(!list?'active':'')+'">All Contacts</a>'+lists.sort((a,b)=>a.name.localeCompare(b.name)).map(l=>`<div class="contact-list-nav" data-contact-drop="${esc(l.id)}"><a class="${l===list?'active':''}" href="/contacts/?list=${encodeURIComponent(l.id)}">${esc(l.name)}</a><button data-op="contact-list-menu" data-id="${esc(l.id)}" aria-label="Actions for ${esc(l.name)}">•••</button></div>`).join('')+'<button data-op="new-contact-list">＋ New List</button>';
 const toolbar=`<input id="contact-search" placeholder="Search ${esc(name)}" aria-label="Search ${esc(name)}"><button data-op="contact-selection-menu" aria-label="Contact selection actions">•••</button><span class="spacer"></span><select id="contact-sort" aria-label="Sort contacts">${['First Name','Last Name','Date Created'].map(option=>`<option ${preferences.sort===option?'selected':''}>${option}</option>`).join('')}</select><button data-op="contact-create-menu" aria-label="Create new contact or import">＋</button><button data-op="contact-export-menu" aria-label="Export or print contacts">↑</button>`;
 appFrame('Contacts',side,'<div class="contact-columns"><section id="contact-list"></section><section id="contact-detail"></section></div>',toolbar);
 const render=()=>{
  const search=document.querySelector('#contact-search').value.trim();const sort=document.querySelector('#contact-sort').value;
  const candidates=data.filter(c=>!list||(list.contacts||[]).includes(c.id));
  const textValues=c=>[c.name,c.first_name,c.last_name,c.company,c.department,c.note,c.nickname,c.birthday,c.job_title,...['phones','emails','urls','related','addresses'].flatMap(key=>(c[key]||[]).flatMap(v=>Object.values(v)))].join(' ').toLocaleLowerCase();
  const visible=candidates.filter(c=>textValues(c).includes(search.toLocaleLowerCase())).sort((a,b)=>{
   if(sort==='Date Created')return (a.created_at||a.order||0)-(b.created_at||b.order||0);
   const key=c=>sort==='Last Name'?(c.last_name||c.name.split(/\s+/).at(-1)):(c.first_name||c.name);
   return key(a).localeCompare(key(b))||a.name.localeCompare(b.name);
  });contactsContext.visible=visible;
  document.querySelector('#contact-list').innerHTML=visible.map(c=>`<button draggable="true" data-contact-drag="${esc(c.id)}" class="contact-row ${contactsContext.selected.has(c.id)?'active':''}" data-op="open-contact" data-id="${esc(c.id)}" aria-pressed="${contactsContext.selected.has(c.id)}">${contactAvatar(c,true)}${contactHighlight(c.name,search)}${preferences.my_card===c.id?'<small>My Card</small>':''}</button>`).join('')+`<p class="hint">${visible.length} Contacts</p>`;
  const selected=data.filter(c=>contactsContext.selected.has(c.id));activeEntity=selected.length===1?selected[0]:null;
  const detail=document.querySelector('#contact-detail');detail.innerHTML=activeEntity?contactCard(activeEntity,search):`<div class="empty"><h2>${selected.length?selected.length+' Contacts Selected':'No Contact Selected'}</h2></div>`;
 };contactsContext.render=render;render();
 document.querySelector('#contact-search').oninput=()=>{contactsContext.selected.clear();render()};
 document.querySelector('#contact-sort').onchange=async event=>{try{preferences.sort=event.target.value;await storeItem('settings',preferences);render()}catch(error){showDialog('Unable to save',`<p>${esc(error.message)}</p><button data-action="close">OK</button>`)}};
 if(activeEntity?.order>5){entityBoundary('Contacts',activeEntity,contactPath());return}
 const layout=document.querySelector('.app-layout');
 layout.addEventListener('dragstart',event=>{const row=event.target.closest('[data-contact-drag]');if(!row)return;const ids=contactsContext.selected.has(row.dataset.contactDrag)?[...contactsContext.selected]:[row.dataset.contactDrag];event.dataTransfer.setData('application/x-icloud-contacts',JSON.stringify(ids));event.dataTransfer.effectAllowed='copy'});
 layout.addEventListener('dragover',event=>{if(event.target.closest('[data-contact-drop]')&&Array.from(event.dataTransfer.types).includes('application/x-icloud-contacts')){event.preventDefault();event.dataTransfer.dropEffect='copy'}});
 layout.addEventListener('drop',async event=>{const target=event.target.closest('[data-contact-drop]'),raw=event.dataTransfer.getData('application/x-icloud-contacts');if(!target||!raw)return;event.preventDefault();try{await api('/api/contacts/action',{action:'add',list:target.dataset.contactDrop,ids:JSON.parse(raw)});await contactsPage()}catch(error){showDialog('Unable to add contacts',`<p>${esc(error.message)}</p><button data-action="close">OK</button>`)}});
 document.querySelector('#contact-list').onkeydown=event=>{if(event.key==='Delete'&&contactsContext.selected.size){event.preventDefault();confirmContactDelete()}};
}
function confirmContactDelete(){
 if(!contactsContext.selected.size)return;
 showDialog('Delete Contact?',`<p>${contactsContext.list?'Remove the selected contacts from this list? They will remain in All Contacts.':'Delete the selected contacts?'}</p><button data-action="close">Cancel</button><button data-op="confirm-contact-delete">Delete</button>`);
}
function editContact(existing={}){
 let avatar=existing.avatar||'';
 const first=existing.first_name??existing.name??'',last=existing.last_name||'';
 const labels='<datalist id="contact-labels">'+['Home','Work','School','Other','mobile','iPhone'].map(label=>`<option value="${label}">`).join('')+'</datalist>';
 const repeated=(key,label,type='text')=>`<fieldset data-contact-fields="${key}"><legend>${label}</legend>${(existing[key]?.length?existing[key]:[{label:key==='phones'?'mobile':'Home',value:''}]).map((item,index)=>contactInputRow(key,label,item,index,type)).join('')}<button type="button" data-contact-add="${key}" data-label="${label}" data-type="${type}">Add ${label}</button></fieldset>`;
 const optional=(key,value='')=>`<div class="contact-extra-field" data-extra-field="${key}">${field(key,CONTACT_EXTRA_FIELDS[key],value)}<button type="button" data-contact-remove-extra aria-label="Remove ${CONTACT_EXTRA_FIELDS[key]}">−</button></div>`;
 const fields=`<div id="contact-edit-body"><button type="button" id="contact-edit-photo">${avatar?contactAvatar({...existing,avatar}):'Add Photo'}</button><h3>Contact Details <button type="button" data-contact-more aria-label="Add Contact Details">＋</button></h3>`+field('first_name','First Name',first)+field('last_name','Last Name',last)+field('company','Company',existing.company)+labels+repeated('phones','Phone','tel')+repeated('emails','Email','email')+repeated('urls','Website')+`<section id="contact-extra-fields">${Object.keys(CONTACT_EXTRA_FIELDS).filter(key=>existing[key]).map(key=>optional(key,existing[key])).join('')}${existing.related?.length?repeated('related','Related Name'):''}${existing.addresses?.length?repeated('addresses','Address'):''}</section><button type="button" data-contact-more>Add Field</button><div id="contact-field-picker" hidden></div><label>Notes<textarea name="note">${esc(existing.note)}</textarea></label></div>`;
 formDialog(existing.id?'Edit Contact':'New Contact',fields,async form=>{
  const payload={...existing,avatar};for(const key of ['first_name','last_name','company','note',...Object.keys(CONTACT_EXTRA_FIELDS)])payload[key]=(form[key]||'').trim();
  payload.name=[payload.prefix,payload.first_name,payload.middle_name,payload.last_name,payload.suffix].filter(Boolean).join(' ')||payload.company;
  if(!payload.name)throw Error('Enter a contact name or company.');
  for(const key of ['phones','emails','urls','related'])payload[key]=[...document.querySelectorAll(`[data-contact-fields="${key}"] .contact-input-row`)].map(row=>({label:row.querySelector('[data-contact-label]').value.trim()||'Other',value:row.querySelector('[data-contact-value]').value.trim()})).filter(item=>item.value);
  payload.addresses=[...document.querySelectorAll('[data-contact-fields="addresses"] .contact-address-row')].map(row=>Object.fromEntries([...row.querySelectorAll('[data-address-part]')].map(input=>[input.dataset.addressPart,input.value.trim()]))).filter(address=>Object.entries(address).some(([key,value])=>key!=='label'&&value));
  if(!existing.id&&contactsContext.list)payload.contact_list=contactsContext.list;
  const saved=await storeItem('contacts',payload);
  history.replaceState(null,'',contactPath(saved.id));await contactsPage();
 });
 document.querySelector('#edit-form button[type=submit]').textContent='Save';
 document.querySelector('#contact-edit-photo').onclick=()=>contactPhotoEditor(avatar,value=>{avatar=value;document.querySelector('#contact-edit-photo').innerHTML=avatar?contactAvatar({...existing,avatar}):'Add Photo'});
 document.querySelector('#edit-form').addEventListener('click',event=>{
  const add=event.target.closest('[data-contact-add]'),remove=event.target.closest('[data-contact-remove]'),more=event.target.closest('[data-contact-more]'),insert=event.target.closest('[data-contact-insert]'),removeExtra=event.target.closest('[data-contact-remove-extra]');
  if(add){const list=add.closest('fieldset'),index=Number(list.dataset.nextIndex||list.querySelectorAll('.contact-input-row,.contact-address-row').length);list.dataset.nextIndex=index+1;add.insertAdjacentHTML('beforebegin',contactInputRow(add.dataset.contactAdd,add.dataset.label,{label:'Other',value:''},index,add.dataset.type));add.previousElementSibling.querySelector('input').focus()}
  if(remove){const row=remove.closest('.contact-input-row,.contact-address-row'),group=row.closest('fieldset');row.remove();if(!group.querySelector('.contact-input-row,.contact-address-row'))group.remove()}
  if(removeExtra)removeExtra.closest('.contact-extra-field').remove();
  if(more){const picker=document.querySelector('#contact-field-picker');picker.hidden=false;const options={...CONTACT_EXTRA_FIELDS,related:'Related Name',addresses:'Address'};picker.innerHTML='<label>Field<select aria-label="Field">'+Object.entries(options).filter(([key])=>!document.querySelector(`[data-extra-field="${key}"],[data-contact-fields="${key}"]`)).map(([key,label])=>`<option value="${key}">${label}</option>`).join('')+'</select></label><button type="button" data-contact-insert>Add</button>';picker.querySelector('select').focus()}
  if(insert){const picker=document.querySelector('#contact-field-picker'),key=picker.querySelector('select').value;if(!key)return;document.querySelector('#contact-extra-fields').insertAdjacentHTML('beforeend',key==='related'?repeated('related','Related Name'):key==='addresses'?repeated('addresses','Address'):optional(key));picker.hidden=true;document.querySelector('#contact-extra-fields').lastElementChild.querySelector('input').focus()}
 });
}
function contactInputRow(key,label,item,index,type){if(key==='addresses')return `<div class="contact-address-row">${Object.entries({label:'Address Label',po_box:'PO Box',extended:'Address Line 2',street:'Street',city:'City',region:'State or Province',postal_code:'Postal Code',country:'Country'}).map(([part,title])=>`<label>${title}<input data-address-part="${part}" aria-label="${title}${index?' '+(index+1):''}" value="${esc(item[part]||'')}"></label>`).join('')}<button type="button" data-contact-remove aria-label="Remove Address ${index+1}">−</button></div>`;return `<div class="contact-input-row"><label>${label} Label<input data-contact-label list="contact-labels" aria-label="${label} Label ${index+1}" value="${esc(item.label||'Other')}"></label><label>${label}<input data-contact-value type="${type}" aria-label="${label}${index?' '+(index+1):''}" value="${esc(item.value||'')}"></label>${index||key==='related'?`<button type="button" data-contact-remove aria-label="Remove ${label} ${index+1}">−</button>`:''}</div>`}
async function exportContacts(){
 const response=await fetch('/api/contacts/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:[...contactsContext.selected]})});
 if(!response.ok)throw Error((await response.json()).detail||'Unable to export contacts.');
 const link=document.createElement('a');link.href=URL.createObjectURL(await response.blob());link.download='Contacts.vcf';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);closeDialog();
}
function contactPhotoEditor(current,save){
 const form=document.querySelector('#edit-form'),body=document.querySelector('#contact-edit-body'),actions=form.querySelector('.actions');body.hidden=true;actions.hidden=true;
 const panel=document.createElement('section');panel.className='contact-photo-editor';panel.innerHTML='<h3>Contact Photo</h3><div class="contact-photo-drop"><canvas width="256" height="256" aria-label="Contact photo crop"></canvas><p>Choose Photo or drag a photo here.</p></div><button type="button" data-photo-choose>Choose Photo</button><label>Resize<input type="range" aria-label="Resize photo" min="1" max="4" step="0.05" value="1" disabled></label><button type="button" data-photo-rotate disabled>Rotate</button><p class="error" role="alert"></p><div><button type="button" data-photo-cancel>Cancel</button><button type="button" data-photo-done disabled>Done</button></div>';
 form.append(panel);const canvas=panel.querySelector('canvas'),context=canvas.getContext('2d'),slider=panel.querySelector('input');let photo=null,angle=0,zoom=1,x=0,y=0,drag=null;
 const draw=()=>{context.fillStyle='#fff';context.fillRect(0,0,256,256);if(!photo)return;const rotated=angle%180!==0,width=rotated?photo.height:photo.width,height=rotated?photo.width:photo.height,scale=Math.max(256/width,256/height)*zoom;x=Math.max(-(width*scale-256)/2,Math.min((width*scale-256)/2,x));y=Math.max(-(height*scale-256)/2,Math.min((height*scale-256)/2,y));context.save();context.translate(128+x,128+y);context.rotate(angle*Math.PI/180);context.drawImage(photo,-photo.width*scale/2,-photo.height*scale/2,photo.width*scale,photo.height*scale);context.restore()};
 const load=async source=>{const image=new Image();await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error('Choose a supported image.'));image.src=source});if(image.naturalWidth*image.naturalHeight>40_000_000)throw Error('Choose a smaller photo.');photo=image;angle=0;zoom=1;x=0;y=0;slider.value='1';slider.disabled=false;panel.querySelector('[data-photo-done]').disabled=false;panel.querySelector('[data-photo-rotate]').disabled=false;panel.querySelector('.error').textContent='';draw()};
 const file=async selected=>{if(!selected)return;if(selected.size>20*1024*1024){panel.querySelector('.error').textContent='Choose a photo smaller than 20 MB.';return}const bytes=new Uint8Array(await selected.slice(0,16).arrayBuffer()),starts=values=>values.every((value,index)=>bytes[index]===value);const valid=starts([137,80,78,71,13,10,26,10])||starts([255,216,255])||starts([71,73,70,56])||(starts([82,73,70,70])&&String.fromCharCode(...bytes.slice(8,12))==='WEBP');if(!valid){panel.querySelector('.error').textContent='Choose a JPEG, PNG, WebP, or GIF photo.';return}const url=URL.createObjectURL(selected);try{await load(url)}catch(error){panel.querySelector('.error').textContent=error.message}finally{URL.revokeObjectURL(url)}};
 panel.querySelector('[data-photo-choose]').onclick=()=>{const input=document.createElement('input');input.type='file';input.accept='image/jpeg,image/png,image/webp,image/gif';input.onchange=()=>file(input.files[0]);input.click()};
 const drop=panel.querySelector('.contact-photo-drop');drop.ondragover=event=>event.preventDefault();drop.ondrop=event=>{event.preventDefault();file(event.dataTransfer.files[0])};
 slider.oninput=()=>{zoom=Number(slider.value);draw()};panel.querySelector('[data-photo-rotate]').onclick=()=>{angle=(angle+90)%360;draw()};
 canvas.onpointerdown=event=>{if(!photo)return;drag={x:event.clientX,y:event.clientY};canvas.setPointerCapture(event.pointerId)};
 canvas.onpointermove=event=>{if(!drag)return;const scale=256/canvas.getBoundingClientRect().width;x+=(event.clientX-drag.x)*scale;y+=(event.clientY-drag.y)*scale;drag={x:event.clientX,y:event.clientY};draw()};canvas.onpointerup=()=>drag=null;canvas.onpointercancel=()=>drag=null;
 const close=()=>{panel.remove();body.hidden=false;actions.hidden=false;document.querySelector('#contact-edit-photo').focus()};
 panel.querySelector('[data-photo-cancel]').onclick=close;panel.querySelector('[data-photo-done]').onclick=()=>{save(canvas.toDataURL('image/jpeg',.85));close()};draw();
 if(current)load(current).catch(error=>panel.querySelector('.error').textContent=error.message);
 panel.querySelector('[data-photo-choose]').focus();
}
function printContacts(){
 closeDialog();document.querySelector('#contact-print')?.remove();const section=document.createElement('section');section.id='contact-print';section.innerHTML=contactsContext.data.filter(c=>contactsContext.selected.has(c.id)).map(c=>'<article>'+contactCard(c)+'</article>').join('');document.body.append(section);window.addEventListener('afterprint',()=>section.remove(),{once:true});window.print();
}
async function contactArchives(){
 const state=await api('/api/contacts/archives');
 showDialog('Restore Contacts',state.archives.length?'<div class="contact-archives">'+state.archives.map(archive=>`<div class="contact-archive-row"><time datetime="${new Date(archive.created_at).toISOString()}">${esc(new Date(archive.created_at).toLocaleString())}</time><button data-op="restore-contact-version" data-id="${esc(archive.id)}" data-generation="${state.generation}">Restore</button></div>`).join('')+'</div><button data-action="close">Done</button>':'<p>No Archives Available</p><button data-action="close">Done</button>');
}
document.addEventListener('click',async event=>{
 const el=event.target.closest('[data-op]');if(!el)return;const op=el.dataset.op,id=el.dataset.id;
 try{
  if(op==='restore-contact-version'){showDialog('Restore Contacts',`<p>Your current contacts will be archived before this version is restored.</p><button data-action="close">Cancel</button><button data-op="confirm-restore-contact-version" data-id="${esc(id)}" data-generation="${esc(el.dataset.generation)}">Restore</button>`);return}
  if(op==='confirm-restore-contact-version'){
   const generation=el.dataset.generation;modal.querySelectorAll('button').forEach(button=>button.disabled=true);
   const result=await api('/api/contacts/restore',{id},'POST',{'X-Contacts-Generation':generation});
   if(contactsContext)contactsContext.generation=result.generation;
   showDialog('Restore Contacts','<p>Your contacts have been restored.</p><a href="/contacts/">Go to Contacts</a><button data-action="close">Done</button>');return;
  }
  if(op==='contact-create-menu'){showDialog('Contacts','<button data-op="new-contact">Create New Contact</button><button data-op="import-contacts">Import Contact…</button><button data-action="close">Done</button>');return}
  if(op==='contact-export-menu'){showDialog('Contacts',`<button data-op="export-contacts" ${contactsContext.selected.size?'':'disabled'}>Export vCard…</button><button data-op="print-contacts" ${contactsContext.selected.size?'':'disabled'}>Print Contacts</button><button data-action="close">Done</button>`);return}
  if(op==='contact-selection-menu'){showDialog('Contacts',`<button data-op="select-all-contacts">Select All Contacts</button><button data-op="make-my-card" ${contactsContext.selected.size===1?'':'disabled'}>Make This My Card</button><button data-op="delete-contact" ${contactsContext.selected.size?'':'disabled'}>Delete Contact</button><button data-action="close">Done</button>`);return}
  if(op==='new-contact')return editContact();if(op==='edit-contact'&&activeEntity)return editContact(activeEntity);
  if(op==='open-contact'){
   const card=contactsContext.data.find(c=>c.id===id);
   if(event.ctrlKey||event.metaKey){if(contactsContext.selected.has(id))contactsContext.selected.delete(id);else contactsContext.selected.add(id)}
   else{if(card.order>5){entityBoundary('Contacts',card,contactPath());return}contactsContext.selected=new Set([id])}
   history.pushState(null,'',contactPath(contactsContext.selected.size===1?[...contactsContext.selected][0]:null));contactsContext.render();return;
  }
  if(op==='select-all-contacts'){contactsContext.selected=new Set(contactsContext.visible.map(c=>c.id));contactsContext.render();closeDialog();return}
  if(op==='make-my-card'){contactsContext.preferences.my_card=[...contactsContext.selected][0];await storeItem('settings',contactsContext.preferences);contactsContext.render();closeDialog();return}
  if(op==='delete-contact')return confirmContactDelete();
  if(op==='confirm-contact-delete'){await api('/api/contacts/action',{action:contactsContext.list?'remove':'delete',list:contactsContext.list,ids:[...contactsContext.selected]});closeDialog();history.replaceState(null,'',contactPath());return await contactsPage()}
  if(op==='new-contact-list')return formDialog('New List',field('name','Name'),async form=>{await storeItem('contact_lists',{name:form.name,contacts:[]});await contactsPage()});
  if(op==='contact-list-menu'){const list=contactsContext.lists.find(l=>l.id===id);showDialog(list.name,`<button data-op="rename-contact-list" data-id="${esc(id)}">Rename List</button><button data-op="delete-contact-list" data-id="${esc(id)}">Delete List</button><button data-action="close">Done</button>`);return}
  if(op==='rename-contact-list'){const list=contactsContext.lists.find(l=>l.id===id);return formDialog('Rename List',field('name','Name',list.name),async form=>{await storeItem('contact_lists',{id:list.id,name:form.name});await contactsPage()})}
  if(op==='delete-contact-list'){await removeItem('contact_lists',id);closeDialog();if(contactsContext.list===id)history.replaceState(null,'','/contacts/');return await contactsPage()}
  if(op==='export-contacts')return await exportContacts();if(op==='print-contacts')return printContacts();
  if(op==='import-contacts'){
   const input=document.createElement('input');input.type='file';input.accept='.vcf,text/vcard';
   input.onchange=async()=>{if(!input.files[0])return;try{const imported=await api('/api/contacts/import',{content:await input.files[0].text()});closeDialog();history.replaceState(null,'','/contacts/?item='+imported.ids[0]);await contactsPage()}catch(error){showDialog('Unable to import contacts',`<p>${esc(error.message)}</p><button data-action="close">OK</button>`)}};input.click();return;
  }
 }catch(error){showDialog('Unable to complete this action',`<p>${esc(error.message)}</p><button data-action="close">OK</button>`)}
});
