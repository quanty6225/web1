import {openLabelColors} from './project-label-colors.js';
import {dateFilterMenu} from './filter-dates.js';
import {matchesExpression} from './filter-expression.js';
export function createProjectLabels({api,menu,modal,closeDialog,closeMenu,toast,refresh}) {
 const active=()=>location.pathname.endsWith('/settings/project-labels');
 const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
 const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let templates,labels=[],projects=[],host,rows,original,query='',order='title',descending=false,showArchived=false,draft=null,lastApplied=null,settingsLoaded=false;
 const selectedIds=new Set(),collapsed=new Set();
 const orderingNames={Name:'title',Description:'description',Projects:'usage','Last applied':'lastAppliedAt',Created:'createdAt',Archived:'archivedAt'};
 const periodOptions=[['Never applied',true,'null'],['1 day ago','-P1D','gte'],['3 days ago','-P3D','gte'],['1 week ago','-P1W','gte'],['1 month ago','-P1M','gte'],['3 months ago','-P3M','gte'],['6 months ago','-P6M','gte'],['1 year ago','-P1Y','gte']];
 const persist=async()=>api('/api/settings','PUT',{route:location.pathname,key:'project-label-display',value:{order,descending,showArchived,lastApplied,collapsed:[...collapsed]}});
 const update=async()=>{paint();await persist();};
 const date=value=>value?new Date(value*1000).toLocaleDateString('en-US',{month:'short',day:'numeric'}):'';
 const element=markup=>{const t=document.createElement('template');t.innerHTML=markup;return t.content.firstElementChild;};
 const changed=async()=>active()?render():refresh();
 const retired=item=>!!(item.archived||labels.find(x=>x.id===item.parent_id)?.archived);
 const save=async(item,patch)=>{await api('/api/entities/project-labels/'+item.id,'PATCH',{...patch,revision:item.revision});await changed();};
 function edit(row,item,field='title') {
  const cell=$('[data-list-grid-column="'+field.replace('title','title')+'"]',row),button=$('button',cell);
  if(!button)return;
  const input=document.createElement('textarea');input.className='local-inline-editor';input.placeholder=field==='title'?(item.is_group?'Group name':'Label name'):'Add label description…';input.setAttribute('aria-label',field==='title'?'Name':'Description');input.value=item[field]||'';if(field==='title')input.maxLength=80;
  button.replaceWith(input);let done=false;
  const commit=async()=>{if(done)return;if(field==='title'&&!input.value.trim()){done=true;draft=null;await render();return;}done=true;try{if(item.id)await save(item,{[field]:input.value.trim()});else{await api('/api/entities/project-labels','POST',{...item,title:input.value.trim()});draft=null;await render();}}catch(e){done=false;toast(e.message);input.focus();}};
  input.onblur=commit;input.onkeydown=e=>{e.stopPropagation();if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();commit();}if(e.key==='Escape'){e.preventDefault();done=true;draft=null;render();}};
  input.addEventListener('focusout',e=>e.stopPropagation());input.addEventListener('change',e=>e.stopPropagation());input.focus();input.select();
 }
 function archive(item){
  const body=item.is_group?'The labels in this group will no longer be available to apply to projects. Projects with these labels already applied will remain unchanged.':'This label will no longer be available to apply to projects. Projects with the label already applied will remain unchanged.';
  modal('Archive "'+item.title+'"?','<p>'+body+'</p>','Archive',async()=>{await save(item,{archived:true});closeDialog();},true);
 }
 function requireDeleteText(dialog,count){
  if(count<10)return;
  const label=document.createElement('label');label.append('To confirm, type ');const strong=document.createElement('strong');strong.textContent='delete';label.append(strong,' below:');
  const input=document.createElement('input');input.name='confirmation';input.autocomplete='off';input.required=true;input.pattern='\\s*delete\\s*';input.setAttribute('aria-label','To confirm, type delete below:');label.append(input);$('.dialog-body',dialog).append(label);
  const button=$('button[type=submit]',dialog);button.disabled=true;input.oninput=()=>{button.disabled=input.value.trim()!=='delete';};input.focus();
 }
 function remove(item){
  const ids=new Set([item.id,...labels.filter(x=>x.parent_id===item.id).map(x=>x.id)]),count=projects.filter(p=>p.labels?.some(id=>ids.has(id))).length;
  const title='Delete the '+(item.is_group?'group':'label')+' "'+item.title+'"?';
  const active=!item.archived&&!labels.find(x=>x.id===item.parent_id)?.archived;
  const body=(item.is_group?'All labels in this group will be removed from ':'This label will be removed from ')+count+' project'+(count===1?'':'s')+'.'+(active?' Deletion cannot be undone.':'');
  const dialog=modal(title,'<p>'+escape(body)+'</p><p>'+(active?'To prevent future application of this label, archive the label instead.':'This action cannot be undone.')+'</p>','Delete',async()=>{await api('/api/entities/project-labels/'+item.id,'DELETE');closeDialog();await changed();},true);
  requireDeleteText(dialog,count);
  if(!item.archived&&!labels.find(x=>x.id===item.parent_id)?.archived){const button=document.createElement('button');button.type='button';button.textContent='Archive';button.onclick=()=>{closeDialog();archive(item);};$('footer',dialog).prepend(button);}
 }
 function more(button,item,row){
  if(retired(item)){menu(button,[...(!labels.find(x=>x.id===item.parent_id)?.archived?[{text:'Restore',action:()=>save(item,{archived:false})}]:[]),{text:'Delete',action:()=>deleteMany([item])}]);return;}
  const groups=labels.filter(x=>x.is_group&&!x.archived);
  menu(button,[{text:'Edit label name',action:()=>edit(row,item)},
   ...(item.is_group?[{text:'Add label to group',action:()=>create(false,item.id)},...(!labels.some(x=>x.parent_id===item.id)?[{text:'Convert to label',action:()=>save(item,{is_group:false})}]:[])]:[
    ...(groups.length?[{text:item.parent_id?'Change group':'Move to group',action:()=>moveMenu(button,[item])}]:[]),
    ...(!item.parent_id&&!projects.some(p=>p.labels?.includes(item.id))?[{text:'Convert to label group',action:()=>save(item,{is_group:true,parent_id:null})}]:[])]),
   item.archived?{text:'Restore',action:()=>save(item,{archived:false})}:{text:'Archive…',action:()=>archiveMany([item])},
   {text:'Delete',action:()=>deleteMany([item])}]);
 }
 function appliedMenu(anchor){
  dateFilterMenu({anchor,field:{label:'Last applied',key:'lastAppliedAt',defaultOperator:'gte',custom:true,options:periodOptions.map(([label,value,operator])=>({label,value,operator}))},menu,modal,closeDialog,onPick:async value=>{lastApplied=value;await update();}});
 }
 function filterBar(){
  $('[data-project-label-filter]',host)?.remove();if(!lastApplied)return;
  const bar=document.createElement('div');bar.dataset.projectLabelFilter='true';bar.className='local-filter-chips';
  const keys=Object.keys(lastApplied),operator=keys.length>1?'range':keys[0],value=lastApplied[operator];
  const name=document.createElement('span');name.textContent='Last applied';bar.append(name);
  const comparison=document.createElement('button');comparison.textContent=operator==='range'?'in':operator==='null'?'is':operator==='gte'?'after':'before';comparison.onclick=e=>{e.stopPropagation();if(operator==='range'||operator==='null')return;menu(comparison,['after','before'].map(text=>({text,action:async()=>{lastApplied={[text==='after'?'gte':'lte']:value};await update();}})));};bar.append(comparison);
  const choice=document.createElement('button');choice.textContent=operator==='range'?lastApplied.gte+' – '+lastApplied.lt:periodOptions.find(x=>x[1]===value)?.[0]||String(value);choice.onclick=e=>{e.stopPropagation();appliedMenu(choice);};bar.append(choice);
  const clear=document.createElement('button');clear.textContent='Clear';clear.onclick=async e=>{e.stopPropagation();lastApplied=null;await update();};bar.append(clear);
  const anchor=$('input[placeholder="Filter by name…"]',host);(anchor?.closest('form')||host.firstElementChild||host).after(bar);
 }
 function paint(){
  if(rows){let archived=$('[data-project-archived-header]',host);if(!archived){archived=element(templates.archivedHeader);archived.dataset.projectArchivedHeader='';$('[data-list-grid-column=createdAt]',host).after(archived);$('button',archived).onclick=e=>{e.stopPropagation();descending=order==='archivedAt'?!descending:true;order='archivedAt';update().catch(e=>toast(e.message));};}archived.hidden=!showArchived;
   const grid=$('[style*="grid-template-columns"]',host);if(grid){grid.dataset.defaultColumns ||=grid.style.gridTemplateColumns;grid.style.gridTemplateColumns=showArchived?templates.archivedGridStyle.match(/grid-template-columns: ([^;]+)/)[1]:grid.dataset.defaultColumns;}for(const e of [host,...$$('[style*="--x-gridTemplateColumns"]',host)]){const value=e.style.getPropertyValue('--x-gridTemplateColumns');if(!value)continue;e.dataset.defaultGridVariable ||=value;e.style.setProperty('--x-gridTemplateColumns',showArchived?templates.archivedGridStyle.match(/grid-template-columns: ([^;]+)/)[1]:e.dataset.defaultGridVariable);}}
  for(const button of $$('button[aria-label^="Order by " ]',host)){const name=button.getAttribute('aria-label').slice(9).split(',')[0];button.setAttribute('aria-label','Order by '+name+(orderingNames[name]===order?', sorted '+(descending?'descending':'ascending'):''));}
  filterBar();if(!rows){const empty=$$('*',host).find(e=>!e.childElementCount&&['No labels found','No matching labels'].includes(e.textContent));if(empty)empty.textContent=query||lastApplied?'No matching labels':'No labels found';return;}
  rows.replaceChildren();const groups=labels.filter(x=>x.is_group),visible=labels.filter(item=>(showArchived||!item.archived&&!labels.find(x=>x.id===item.parent_id)?.archived)&&(!query||item.title.toLowerCase().includes(query.toLowerCase()))&&(!lastApplied||matchesExpression({lastAppliedAt:item.last_applied_at||null},{lastAppliedAt:lastApplied})));
  const value=item=>order==='usage'?projects.filter(p=>p.labels?.includes(item.id)).length:order==='lastAppliedAt'?item.last_applied_at||0:order==='archivedAt'?item.archived_at||0:order==='createdAt'?item.created_at||0:item[order]||'';
  const compare=(a,b)=>{const x=value(a),y=value(b);return (typeof x==='number'?x-y:String(x).localeCompare(String(y)))*(descending?-1:1);};
  const sorted=[...visible.filter(x=>!x.parent_id||!visible.some(g=>g.id===x.parent_id)).sort(compare)];
  for(let i=0;i<sorted.length;i++)if(sorted[i].is_group&&(!collapsed.has(sorted[i].id)||query||lastApplied))sorted.splice(i+1,0,...visible.filter(x=>x.parent_id===sorted[i].id).sort(compare));
  if(draft)sorted.unshift(draft);
  for(const item of sorted){
   const row=element(templates[item.is_group?'group':'label']);if(showArchived)row.style.setProperty('--x-gridTemplateColumns',templates.archivedGridStyle.match(/grid-template-columns: ([^;]+)/)[1]);row.dataset.projectLabelId=item.id||'draft';row.onclick=e=>e.stopPropagation();if(item.is_group&&labels.some(x=>x.parent_id===item.id)){row.setAttribute('aria-expanded',String(!collapsed.has(item.id)));row.onclick=e=>{if(e.target.closest('button,input,textarea,[role=button]'))return;e.stopPropagation();collapsed.has(item.id)?collapsed.delete(item.id):collapsed.add(item.id);update().catch(e=>toast(e.message));};}if(item.parent_id)row.dataset.projectLabelGroup=item.parent_id;
   const title=$('[data-list-grid-column=title] button',row);title.textContent=item.title;if(retired(item))title.setAttribute('aria-label','Cannot edit archived labels');title.onclick=e=>{e.stopPropagation();edit(row,item);};
   if(item.parent_id)title.style.marginLeft='18px';
   if(item.is_group&&labels.some(x=>x.parent_id===item.id)){const arrow=element(templates.collapseArrow);arrow.dataset.projectGroupChevron='true';arrow.style.transform=collapsed.has(item.id)?'rotate(0deg)':'rotate(90deg)';$('[name=color]',row)?.parentElement.before(arrow);}
   const color=$('[name=color]',row);if(color){color.tabIndex=retired(item)?-1:0;color.setAttribute('aria-disabled',String(retired(item)));color.setAttribute('role','button');color.setAttribute('aria-label','Change color for '+item.title);const swatch=$('[aria-hidden=true]',color);if(swatch){if(swatch.tagName.toLowerCase()==='svg'){swatch.setAttribute('fill',item.color||'#4cb782');swatch.style.setProperty('--x---icon-default-color',item.color||'#4cb782');}else swatch.style.background=item.color||'#4cb782';}color.onclick=e=>{e.preventDefault();e.stopPropagation();if(item.id&&!retired(item)&&!selectedIds.size)openLabelColors({anchor:color,item,templates,menu,closeMenu,save,toast});};color.onkeydown=e=>{if(e.key===' '||e.key==='Enter'){e.preventDefault();color.click();}};}
   const description=$('[data-list-grid-column=description] button',row);description.textContent=item.description||'Add label description…';description.disabled=!item.id;description.onclick=e=>{e.stopPropagation();edit(row,item,'description');};
   const ids=new Set([item.id,...(item.is_group?labels.filter(x=>x.parent_id===item.id).map(x=>x.id):[])]),usage=projects.filter(p=>p.labels?.some(id=>ids.has(id))).length;
   $('[data-list-grid-column=usage]',row).textContent=usage||'';
   $('[data-list-grid-column=lastAppliedAt]',row).textContent=date(item.last_applied_at);
   $('[data-list-grid-column=createdAt]',row).textContent=date(item.created_at);if(showArchived){const cell=element(templates.archivedCell);cell.textContent=date(item.archived_at);$('[data-list-grid-column=createdAt]',row).after(cell);}
   const checkbox=$('input[type=checkbox]',row);if(checkbox){checkbox.tabIndex=0;checkbox.setAttribute('aria-label','Select '+item.title);checkbox.checked=selectedIds.has(item.id);checkbox.setAttribute('aria-checked',String(checkbox.checked));row.dataset.selected=String(checkbox.checked);checkbox.onchange=e=>{e.stopPropagation();for(const id of [item.id,...(item.is_group?labels.filter(x=>x.parent_id===item.id).map(x=>x.id):[])])checkbox.checked?selectedIds.add(id):selectedIds.delete(id);for(const r of $$('[data-project-label-id]',rows)){const c=$('input[type=checkbox]',r);if(c){c.checked=selectedIds.has(r.dataset.projectLabelId);c.setAttribute('aria-checked',String(c.checked));r.dataset.selected=String(c.checked);}}selection();};}
   const button=$('[aria-label="Open menu"]',row);button.disabled=!item.id;button.onclick=e=>{e.stopPropagation();more(button,item,row);};
   row.addEventListener('keydown',e=>{if(e.target!==row)return;if(e.key==='Enter'||e.key.toLowerCase()==='e'){e.preventDefault();edit(row,item);}if(e.key===' '){e.preventDefault();checkbox?.click();}});
   rows.append(row);if(!item.id)edit(row,item);
  }
  const visibleIds=new Set([...sorted.map(x=>x.id),...sorted.filter(x=>x.is_group).flatMap(g=>labels.filter(x=>x.parent_id===g.id).map(x=>x.id))]);for(const id of selectedIds)if(!visibleIds.has(id))selectedIds.delete(id);selection();
  if(!sorted.length){const empty=document.createElement('div');empty.className='local-empty';empty.textContent=query||lastApplied?'No matching labels':'No labels found';rows.append(empty);}
 }
 const batch=async(action,items,extra={})=>{await api('/api/project-labels/batch','POST',{action,ids:items.map(x=>x.id),...extra});await changed();};
 const appliedProjects=items=>{const ids=new Set(items.flatMap(x=>[x.id,...(x.is_group?labels.filter(c=>c.parent_id===x.id).map(c=>c.id):[])]));return projects.filter(p=>p.labels?.some(id=>ids.has(id)));};
 const selectionName=items=>{const roots=items.filter(x=>!items.some(g=>g.id===x.parent_id));if(roots.length===1)return '"'+roots[0].title+'"';const groups=roots.filter(x=>x.is_group).length,count=roots.length-groups;return[groups?groups+' group'+(groups===1?'':'s'):'',count?count+' label'+(count===1?'':'s'):''].filter(Boolean).join(' and ');};
 async function archiveMany(items){
  if(!appliedProjects(items).length){await batch('archive',items);return;}
  if(items.length===1){archive(items[0]);return;}
  modal('Archive '+selectionName(items)+'?','<p>These labels will no longer be available to apply to projects. Projects with these labels already applied will remain unchanged.</p>','Archive',async()=>{await batch('archive',items);closeDialog();},true);
 }
 async function deleteMany(items){
  const count=appliedProjects(items).length;if(!count){await batch('delete',items);return;}if(items.length===1){remove(items[0]);return;}
  const active=items.every(x=>!x.archived&&!labels.find(g=>g.id===x.parent_id)?.archived);
  const d=modal('Delete '+selectionName(items)+'?','<p>These labels will be removed from '+count+' project'+(count===1?'':'s')+'.'+(active?' Deletion cannot be undone.':'')+'</p><p>'+(active?'To prevent future application of these labels, archive them instead.':'This action cannot be undone.')+'</p>','Delete',async()=>{await batch('delete',items);closeDialog();},true);
  requireDeleteText(d,count);
  if(items.every(x=>!x.archived&&!labels.find(g=>g.id===x.parent_id)?.archived)){const b=document.createElement('button');b.type='button';b.textContent='Archive';b.onclick=()=>{closeDialog();archiveMany(items);};$('footer',d).prepend(b);}
 }
 function moveToGroup(items,parent){
  const ids=new Set(items.map(x=>x.id)),conflicts=parent?projects.filter(p=>{const assigned=items.filter(x=>p.labels?.includes(x.id));return assigned.length&&(assigned.length>1||p.labels?.some(id=>!ids.has(id)&&labels.find(x=>x.id===id)?.parent_id===parent.id));}):[];
  if(!conflicts.length)return batch('move',items,{parent_id:parent?.id||null});
  const names=[...new Set(conflicts.flatMap(p=>items.filter(x=>p.labels?.includes(x.id)).map(x=>x.title)))],single=names.length===1;
  const body='<p>'+(single?'The "'+escape(names[0])+'" label is currently present on':'The labels '+escape(names.join(', '))+' are currently present on')+' '+(conflicts.length===1?'a project that already has':'projects that already have')+' another label from the "'+escape(parent.title)+'" group. Each project can only have one label from the group.</p><p>'+(conflicts.length===1?'The project':conflicts.length+' projects')+' will have labels removed to keep only one from the group.</p>';
  modal('Resolve conflict and add '+(items.length===1?'label':'labels')+' to group?',body,'Remove '+(single?'label':'labels')+' from '+(conflicts.length===1?'project':'projects'),async()=>{await batch('move',items,{parent_id:parent.id,resolve_conflicts:true});closeDialog();},true);
 }
 function moveMenu(anchor,items){menu(anchor,[...(items.every(x=>x.parent_id)?[{text:'Remove from group',action:()=>moveToGroup(items,null)}]:[]),...labels.filter(x=>x.is_group&&!x.archived).map(group=>({text:group.title,action:()=>moveToGroup(items,group)}))]);}
 function merge(items){
  const used=item=>projects.filter(p=>p.labels?.includes(item.id)).length,target=[...items].sort((a,b)=>used(b)-used(a)||(b.last_applied_at||0)-(a.last_applied_at||0)||a.title.toLowerCase().localeCompare(b.title.toLowerCase()))[0],count=appliedProjects(items).length;
  modal('Merge '+items.length+' labels?','<p>These labels will be merged into <strong>'+escape(target.title)+'</strong>'+(count?'. The merged label will be applied to '+count+' project'+(count===1?'':'s'):'')+'.</p><p>This action cannot be undone.</p>','Merge',async()=>{await batch('merge',items,{target_id:target.id});closeDialog();},true);
 }
 function selection(){
  for(const button of $$('[data-list-grid-column=title] button,[data-list-grid-column=description] button',rows))button.disabled=retired(labels.find(x=>x.id===button.closest('[data-project-label-id]')?.dataset.projectLabelId)||{})||selectedIds.size>0||button.closest('[data-project-label-id]')?.dataset.projectLabelId==='draft'&&button.closest('[data-list-grid-column]')?.dataset.listGridColumn==='description';
  $('[data-project-label-selection]',host)?.remove();const items=labels.filter(x=>selectedIds.has(x.id));if(!items.length)return;
  const bar=document.createElement('div');bar.dataset.projectLabelSelection='true';bar.className='local-filter-chips';host.append(bar);const count=document.createElement('span');count.textContent=items.length+' selected';bar.append(count);
  const button=document.createElement('button');button.textContent='Actions';button.onclick=e=>{e.stopPropagation();const single=items.length===1,item=items[0],onlyLabels=items.every(x=>!x.is_group),noun=items.every(x=>x.is_group)?'group':'label',plural=noun+(single?'':'s');
   const actions=[{text:'Ask Linear',action:()=>$('[aria-label=Agent]')?.click()},...(single&&!retired(item)?[{text:'Rename label',action:()=>{selectedIds.clear();paint();const row=$('[data-project-label-id="'+item.id+'"]',rows);edit(row,item);}}]:[]),
    ...(items.every(x=>!!x.favorite===!!item.favorite)?[{text:(item.favorite?'Unfavorite':'Favorite')+' label'+(single?'':'s'),action:()=>batch(item.favorite?'unfavorite':'favorite',items)}]:[]),
    ...(onlyLabels&&items.every(x=>!retired(x))&&(labels.some(x=>x.is_group&&!x.archived)||items.every(x=>x.parent_id))?[{text:items.every(x=>x.parent_id)?'Change label group'+(single?'':'s'):'Move label'+(single?'':'s')+' to group',action:()=>moveMenu(button,items)}]:[]),
    ...(single&&!retired(item)&&item.is_group&&!labels.some(x=>x.parent_id===item.id)?[{text:'Convert to label',action:()=>save(item,{is_group:false})}]:[]),
    ...(single&&!retired(item)&&!item.is_group&&!item.parent_id&&!appliedProjects(items).length?[{text:'Convert to label group',action:()=>save(item,{is_group:true})}]:[]),
    ...(items.length>1&&onlyLabels&&items.every(x=>x.parent_id===item.parent_id)?[{text:'Merge labels…',action:()=>merge(items)}]:[]),
    ...(items.every(x=>retired(x)&&(!labels.find(g=>g.id===x.parent_id)?.archived||items.some(g=>g.id===x.parent_id)))?[{text:'Restore '+plural+'…',action:()=>batch('restore',items)}]:items.some(x=>!retired(x))?[{text:'Archive '+plural+'…',action:()=>archiveMany(items)}]:[]),
    {text:'Delete '+plural+'…',action:()=>deleteMany(items)}];menu(button,actions);
  };bar.append(button);
 }
 function bind(){
  const input=$('input[placeholder="Filter by name…"]',host);if(input){input.value=query;input.oninput=()=>{query=input.value;paint();};input.addEventListener('focusout',e=>e.stopPropagation());input.addEventListener('change',e=>e.stopPropagation());}
  for(const button of $$('button',host)){
   const text=button.getAttribute('aria-label')||button.textContent.trim();
   let action;if(text==='New label')action=()=>create(false);else if(text==='New group')action=()=>create(true);
   else if(text.startsWith('Order by '))action=()=>{const key={Name:'title',Description:'description',Projects:'usage','Last applied':'lastAppliedAt',Created:'createdAt',Archived:'archivedAt'}[text.slice(9).split(',')[0]];descending=order===key?!descending:false;order=key;update().catch(e=>toast(e.message));};
   else if(text==='Add filter')action=()=>menu(button,[{text:'Last applied',action:()=>appliedMenu(button)}]);
   else if(text==='Display options')action=()=>menu(button,[{text:'Ordering · '+(Object.keys(orderingNames).find(key=>orderingNames[key]===order)||'Name'),action:()=>menu(button,Object.entries({Name:'title',Description:'description',Projects:'usage','Last applied':'lastAppliedAt',Created:'createdAt',Archived:'archivedAt'}).map(([text,key])=>({text,action:()=>{order=key;descending=false;return update();}})))},{text:(showArchived?'✓ ':'')+'Show archived',action:()=>{showArchived=!showArchived;return update();}}]);
   if(action)button.onclick=e=>{e.preventDefault();e.stopPropagation();action();};
  }
 }
 async function render(){
  if(!active())return;
  if(!settingsLoaded){const settings=await api('/api/settings?route='+encodeURIComponent(location.pathname));const saved=settings['project-label-display']||{};order=Object.values(orderingNames).includes(saved.order)?saved.order:'title';descending=!!saved.descending;showArchived=!!saved.showArchived;lastApplied=saved.lastApplied||null;if(Array.isArray(saved.collapsed))for(const id of saved.collapsed)if(typeof id==='string')collapsed.add(id);settingsLoaded=true;}
  [labels,projects]=await Promise.all([api('/api/entities/project-labels'),api('/api/entities/projects')]);
  if(!templates){templates=await (await fetch('/static/project-labels/templates.json')).json();const style=document.createElement('style');style.textContent=templates.styles+'\n'+(templates.colorStyles||'')+'\n'+(templates.archivedStyles||'');document.head.append(style);host=$('main > [data-loading-caret]');original=host.outerHTML;}
  const table=!!(labels.length||draft);if(!host.dataset.projectLabelsMounted||!!rows!==table){const next=element(table?templates.shell:original);host.replaceWith(next);host=next;host.dataset.projectLabelsMounted='true';rows=$('[data-project-label-rows]',host);bind();}
  paint();
 }
 async function create(is_group,parent_id=null){if(parent_id)collapsed.delete(parent_id);draft={title:'',description:'',is_group,parent_id};await render();}
 async function act(action,ids){[labels,projects]=await Promise.all([api('/api/entities/project-labels'),api('/api/entities/projects')]);const items=labels.filter(x=>ids.includes(x.id));if(action==='archive')return archiveMany(items);if(action==='delete')return deleteMany(items);if(action==='restore')return batch('restore',items);}
 return {render,act};
}
