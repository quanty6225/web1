import {subissueTemplates} from '/static/subissue-templates.js';
import {chooseDocumentIcon,cleanPaste} from '/static/documents.js';
const $=(q,r=document)=>r.querySelector(q),$$=(q,r=document)=>[...r.querySelectorAll(q)];
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const team=document.body.dataset.activeTeam||'QQQ';
const home='/qqq153/settings/teams/'+team+'/recurring-issues';
export function createRecurringIssues({api,menu,modal,closeDialog,toast,refresh,getState,getAccount,issueURL,attachments}){
 let current=null,data=null,bound=false,dirty=false,saving=false,subissues=null;
 const path=()=>location.pathname;
 const records=()=>(getState()?.recurring_issues||[]).filter(x=>(x.team||'QQQ')===team);
 function error(message){let node=$('[data-recurring-error]');if(!node){node=document.createElement('p');node.dataset.recurringError='';node.className='document-save-error';node.role='alert';$('main form')?.prepend(node);}node.textContent=message;}
 function paint(){
  for(const b of $$('main button')){const label=b.getAttribute('aria-label')||'';
   if(label==='Change status')b.textContent=data.status;
   if(label.startsWith('Change priority'))b.textContent=data.priority==='No priority'?'Priority':data.priority;
   if(label.startsWith('Change assignee'))b.textContent=data.assignee?getAccount().display_name:'Assignee';
   if(label==='Change labels')b.textContent=data.labels.length?data.labels.join(', '):'Labels';
   if(b.dataset.recurringField)b.textContent=data[b.dataset.recurringField];
  }
 }
 async function save(){
  if(saving)return;data.title=$('[aria-label="Issue title"]').innerText.trim();data.description=$('[aria-label="Issue description"]').innerText.trim();data.content_html=$('[aria-label="Issue description"]').innerHTML;data.first_due_date=$('[data-recurring-date]').value;
  if(!data.title){error('Enter an issue title.');$('[aria-label="Issue title"]').focus();return;}saving=true;
  try{await api('/api/entities/recurring-issues'+(current?'/'+current.id:''),current?'PATCH':'POST',{...data,...(current?{revision:current.revision}:{})});dirty=false;location.href=home;}catch(e){error(e.message);saving=false;}
 }
 function renderEditor(){
  if(!path().startsWith(home+'/')||bound)return;const id=path().split('/').at(-1);current=id==='new'?null:records().find(r=>r.id===id);if(id!=='new'&&!current)return;
  const source=getState().issues.find(i=>i.id===new URLSearchParams(location.search).get('from'));data={title:'',description:'',status:'Backlog',priority:'No priority',assignee:null,labels:[],first_due_date:'',interval:1,unit:'week',timezone:Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC',enabled:true,...(source?{title:source.title,description:source.description||'',priority:source.priority,status:source.status,assignee:source.assignee,labels:[...(source.labels||[])],project:source.project,source_issue_id:source.id}:{}),...(current||{})};
  for(const [label,key]of [['Issue title','title'],['Issue description','description']]){const field=$('[aria-label="'+label+'"]');if(!field)return;field.contentEditable='true';field.setAttribute('aria-readonly','false');field.textContent=data[key];if(key==='description'&&data.content_html)field.innerHTML=data.content_html;field.addEventListener('input',()=>dirty=true);field.addEventListener('paste',e=>{e.preventDefault();const rich=e.clipboardData.getData('text/html');if(key==='description'&&rich)document.execCommand('insertHTML',false,cleanPaste(rich));else document.execCommand('insertText',false,e.clipboardData.getData('text/plain'));dirty=true;});}
  const date=$('main input[type=text]');date.dataset.recurringDate='';date.setAttribute('aria-label','First due date');date.type='date';date.value=data.first_due_date;date.oninput=()=>dirty=true;if(current)date.readOnly=true;
  const choices=$$('main button[role=combobox]');choices.forEach((button,index)=>{button.dataset.recurringField=index?'unit':'interval';button.setAttribute('aria-label',index?'Repeat period':'Repeat interval');});
  if(current){const b=$('button[aria-label=Create]');b.textContent='Save';b.setAttribute('aria-label','Save');const title=$$('main h1,main h2').find(e=>e.textContent.trim()==='New recurring issue');if(title)title.textContent='Edit recurring issue';}
  for(const form of $$('main form'))form.addEventListener('submit',e=>{e.preventDefault();e.stopPropagation();save();});addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();save();}});subissues=subissueTemplates({get:()=>data.subissue_templates||[],set:value=>{data.subissue_templates=value;dirty=true;},getState,getAccount,modal,closeDialog,menu,attachments});paint();bound=true;
 }
 function rowMenu(anchor,item){menu(anchor,[{text:'Edit',href:home+'/'+item.id},{text:'Open latest issue',href:issueURL(getState().issues.find(i=>i.id===item.last_issue_id)||{id:item.last_issue_id,title:item.title})},{text:item.enabled?'Pause':'Resume',action:async()=>{await api('/api/entities/recurring-issues/'+item.id,'PATCH',{enabled:!item.enabled,revision:item.revision});await refresh();}},{text:'Delete',action:()=>modal('Delete recurring issue','<p>Delete '+escape(item.title)+'? Existing issues will be kept.</p>','Delete',async()=>{await api('/api/entities/recurring-issues/'+item.id,'DELETE');closeDialog();await refresh();},true)}]);}
 function renderList(){
  if(path()!==home)return;const items=records();$('[data-recurring-list]')?.remove();const empty=$$('main *').find(e=>!e.children.length&&(e.textContent.trim()==='No recurring issues'||e.hasAttribute('data-recurring-count')));if(empty){empty.dataset.recurringCount='';empty.textContent=items.length?items.length+' recurring issue'+(items.length===1?'':'s'):'No recurring issues';}
  if(!items.length)return;const box=document.createElement('section');box.dataset.recurringList='';box.className='document-template-list';for(const item of items){const row=document.createElement('article'),link=document.createElement('a'),cadence=document.createElement('span'),more=document.createElement('button');row.dataset.recurringIssue=item.id;link.href=home+'/'+item.id;link.textContent=item.title;cadence.textContent=item.enabled?'Every '+item.interval+' '+item.unit+(item.interval===1?'':'s')+' · Next due '+item.next_due_date:'Paused';more.type='button';more.textContent='…';more.setAttribute('aria-label','Open menu');more.onclick=e=>{e.stopPropagation();rowMenu(more,item);};row.append(link,cadence,more);box.append(row);}if(empty)empty.parentElement.after(box);else $('main').append(box);
 }
 async function handleClick(button){const label=(button.getAttribute('aria-label')||button.innerText||'').trim();if(label==='New recurring issue'){location.href=home+'/new';return true;}if(!path().startsWith(home+'/')||!button.closest('main'))return false;
  const choose=(field,items)=>menu(button,items.map(([title,value])=>({text:String(title),action:()=>{data[field]=value;dirty=true;paint();}})));
  if(label==='Cancel'){dirty=false;location.href=home;}else if(['Create','Save'].includes(label))await save();
  else if(label==='Repeat interval')choose('interval',Array.from({length:30},(_,i)=>[i+1,i+1]));
  else if(label==='Repeat period')choose('unit',['day','week','month','year'].map(x=>[x,x]));
  else if(label==='Change status')choose('status',getState().workflow_states.map(s=>[s.title,s.title]));
  else if(label.startsWith('Change priority'))choose('priority',['No priority','Urgent','High','Medium','Low'].map(x=>[x,x]));
  else if(label.startsWith('Change assignee'))choose('assignee',[['Unassigned',null],[getAccount().display_name,getAccount().email_normalized]]);
  else if(label==='Change labels')menu(button,getState().labels.map(item=>({text:(data.labels.includes(item.title)?'✓ ':'')+item.title,action:()=>{data.labels=data.labels.includes(item.title)?data.labels.filter(x=>x!==item.title):[...data.labels,item.title];dirty=true;paint();}})),'Search labels…');
  else if(label==='Add sub-issue')subissues.add();
  else if(label==='Open menu')menu(button,[{text:'Add sub-issue',action:()=>subissues.add()}]);
  else if(label==='Template icon')await chooseDocumentIcon({modal,closeDialog,toast,onSelect:async icon=>{data.icon=icon;dirty=true;if(icon.startsWith('emoji:'))button.textContent=icon.slice(6);}});
  else return false;return true;
 }
 return {render:()=>{renderEditor();renderList();},handleClick};
}
