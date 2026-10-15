import {documentBodyHTML,hydrateDocumentBlocks} from '/static/document-blocks.js';
import {cleanPaste,chooseDocumentIcon} from '/static/documents.js';
import {bindDocumentFormatting} from '/static/document-formatting.js';
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
const label=e=>(e.getAttribute('aria-label')||e.innerText||'').trim();
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function createDocumentTemplates({api,menu,modal,closeDialog,toast,refresh,getState}){
 let current=null,title=null,body=null,icon='',bound=false,dirty=false,saving=false;
 const match=()=>location.pathname.match(/^\/qqq153\/settings\/(teams\/[^/]+\/)?templates\/document\/([^/]+)$/);
 const team=()=>location.pathname.match(/\/teams\/([^/]+)\//)?.[1]||null;
 const home=()=>team()?'/qqq153/settings/teams/'+team()+'/templates':'/qqq153/settings/documents';
 const editor=(id='new',scope=team())=>'/qqq153/settings/'+(scope?'teams/'+scope+'/':'')+'templates/document/'+encodeURIComponent(id);
 const templates=()=>getState().document_templates||[];
 function error(message){let node=$('[data-template-error]');if(!node){node=document.createElement('p');node.dataset.templateError='';node.role='alert';node.className='document-save-error';title.parentElement.before(node);}node.textContent=message;}
 async function save(){
  if(saving)return;const name=title.innerText.trim();if(!name){error('Template has no name. A name is required.');title.focus();return;}saving=true;
  const button=$('button[aria-label="Create"],button[aria-label="Save"]');if(button)button.disabled=true;
  try{await api('/api/entities/document-templates'+(current?'/'+current.id:''),current?'PATCH':'POST',{title:name,content_html:documentBodyHTML(body),team:team(),icon,...(current?{revision:current.revision}:{})});dirty=false;location.href=home();}catch(e){error(e.message);saving=false;if(button)button.disabled=false;}
 }
 async function chooseIcon(anchor){await chooseDocumentIcon({modal,closeDialog,toast,onSelect:async value=>{icon=value;dirty=true;if(value.startsWith('emoji:'))anchor.textContent=value.slice(6);else{const items=await fetch('/static/project-create/icons.json').then(r=>r.json());const item=items.find(x=>x.name===value);if(item)anchor.innerHTML=item.svg;}}});}

 function renderEditor(){
  const route=match();if(!route)return;if(bound)return;current=route[2]==='new'?null:templates().find(x=>x.id===route[2]);if(route[2]!=='new'&&!current)return;
  title=$('[aria-label="Template name"]');body=$('[aria-label="Document template content"]');if(!title||!body)return;icon=current?.icon||'';
  const copied=route[2]==='new'?templates().find(x=>x.id===new URLSearchParams(location.search).get('copy')):null;const initial=current||copied;if(initial){icon=initial.icon||'';title.textContent=initial.title;body.innerHTML=initial.content_html||'<p><br></p>';}
  if(current){const heading=$$('main *').find(e=>!e.children.length&&e.textContent==='New document template');if(heading)heading.textContent='Edit document template';document.title='Edit '+current.title+' document template · Linear';const button=$('button[aria-label="Create"]');if(button){button.setAttribute('aria-label','Save');button.textContent='Save';}}
  for(const field of [title,body]){field.contentEditable='true';field.setAttribute('aria-readonly','false');field.addEventListener('input',()=>dirty=true);}
  title.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();body.focus();}});
  bindDocumentFormatting({body,menu,modal,closeDialog,changed:()=>dirty=true,toast,chooseIcon:(onSelect,options={})=>chooseDocumentIcon({modal,closeDialog,toast,onSelect,...options})});
  body.addEventListener('paste',event=>{if(event.clipboardData.files.length||getSelection()?.anchorNode?.parentElement?.closest('pre'))return;event.preventDefault();const rich=event.clipboardData.getData('text/html');if(rich)document.execCommand('insertHTML',false,cleanPaste(rich));else document.execCommand('insertText',false,event.clipboardData.getData('text/plain'));hydrateDocumentBlocks(body);dirty=true;});
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();save();}});
  for(const form of $$('main form'))form.addEventListener('submit',e=>{e.preventDefault();e.stopPropagation();save();});
  addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
  if(icon.startsWith('emoji:'))$('[aria-label="Document icon"]').textContent=icon.slice(6);else if(icon)fetch('/static/project-create/icons.json').then(r=>r.json()).then(items=>{const selected=items.find(item=>item.name===icon);if(selected)$('[aria-label="Document icon"]').innerHTML=selected.svg;});bound=true;
 }
 function rowMenu(anchor,item){menu(anchor,[{text:'Edit',href:editor(item.id,item.team)},{text:'Duplicate…',href:editor('new',item.team)+'?copy='+encodeURIComponent(item.id)},{text:'Delete',action:()=>modal('Delete the template "'+item.title+'"?','<p>You cannot undo this action.</p>','Delete',async()=>{await api('/api/entities/document-templates/'+item.id,'DELETE');closeDialog();await refresh();},true)}]);}
 function renderList(){
  if(!['/qqq153/settings/documents','/qqq153/settings/teams/'+team()+'/templates'].includes(location.pathname))return;const records=templates().filter(item=>(item.team||null)===team()).sort((a,b)=>(a.sort_order||0)-(b.sort_order||0));const create=$$('main button').find(b=>label(b).startsWith('Create new document template'));if(create){create.setAttribute('aria-label',records.length?'Create new document template…':'Create new document template');create.textContent=records.length?'+':'New template';}let list=$('[data-document-template-list]');if(list)list.remove();
  const empty=$$('main *').find(e=>!e.children.length&&(e.textContent.trim()==='No document templates'||e.dataset.documentTemplateCount));if(empty){empty.dataset.documentTemplateCount='true';empty.textContent=records.length?records.length+' document template'+(records.length===1?'':'s'):'No document templates';}
  if(!records.length)return;list=document.createElement('section');list.dataset.documentTemplateList='';list.className='document-template-list';
  for(const item of records){const row=document.createElement('article'),link=document.createElement('a'),date=document.createElement('small'),more=document.createElement('button');row.dataset.documentTemplate=item.id;row.tabIndex=-1;row.draggable=records.length>1;const grip=document.createElement('span');grip.className='document-template-grip';grip.setAttribute('aria-hidden','true');grip.textContent='⠿';row.append(grip);link.href=editor(item.id,item.team);link.textContent=item.title;date.textContent='Created on '+(Date.now()-item.created_at*1000<60000?'just now':new Date(item.created_at*1000).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}));more.type='button';more.setAttribute('aria-label','Open menu');more.textContent='…';more.onclick=e=>{e.stopPropagation();rowMenu(more,item);};row.append(link,date,more);list.append(row);}bindOrdering(list,records);if(empty)empty.parentElement.after(list);else $('main').append(list);
 }
 function bindOrdering(list,records){
  if(records.length<2)return;let dragging=null,keyboard=null;const original=records.map(x=>x.id);const ids=()=>$$('[data-document-template]',list).map(x=>x.dataset.documentTemplate);
  const save=async()=>{try{await api('/api/document-templates/order','POST',{team:team(),ids:ids()});await refresh();}catch(error){toast(error.message);await refresh();}};
  for(const row of $$('[data-document-template]',list)){
   row.addEventListener('dragend',()=>dragging=null);row.addEventListener('pointerdown',event=>{if(event.target.closest('.document-template-grip'))row.focus();});row.addEventListener('dragstart',event=>{dragging=row;event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',row.dataset.documentTemplate);});row.addEventListener('dragover',event=>{if(dragging&&dragging!==row){event.preventDefault();event.dataTransfer.dropEffect='move';}});row.addEventListener('drop',event=>{if(!dragging||dragging===row)return;event.preventDefault();const rows=$$('[data-document-template]',list);if(rows.indexOf(dragging)<rows.indexOf(row))row.after(dragging);else row.before(dragging);dragging=null;save();});
   row.addEventListener('keydown',event=>{if(event.target!==row)return;if(event.key===' '&&!keyboard){event.preventDefault();keyboard=row;row.classList.add('document-template-moving');return;}if(keyboard!==row)return;if(['ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();const sibling=event.key==='ArrowUp'?row.previousElementSibling:row.nextElementSibling;if(sibling){if(event.key==='ArrowUp')sibling.before(row);else sibling.after(row);}row.focus();}else if(event.key==='Enter'||event.key===' '){event.preventDefault();keyboard=null;row.classList.remove('document-template-moving');save();}else if(event.key==='Escape'){event.preventDefault();for(const id of original)list.append($('[data-document-template="'+id+'"]',list));keyboard=null;row.classList.remove('document-template-moving');row.focus();}});
  }
 }
 async function handleClick(button){const text=label(button);if(['Create new document template','Create new document template…'].includes(text)){location.href=editor();return true;}if(!match())return false;if(text==='Cancel'){dirty=false;location.href=home();}else if(['Create','Save'].includes(text))await save();else if(text==='Document icon')await chooseIcon(button);else return false;return true;}
 return {render:()=>{renderEditor();renderList();},handleClick};
}
