import {createFormFields} from '/static/issue-forms.js';
import {subissueTemplates} from '/static/subissue-templates.js';
import {chooseDocumentIcon,cleanPaste} from '/static/documents.js';
const $=(q,r=document)=>r.querySelector(q),$$=(q,r=document)=>[...r.querySelectorAll(q)];
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function createIssueTemplates({api,menu,modal,closeDialog,toast,refresh,getState,getAccount,attachments}){
 let current=null,data=null,bound=false,dirty=false,saving=false,subissues=null,formFields=null;
 const match=()=>location.pathname.match(/^\/qqq153\/settings\/(teams\/[^/]+\/)?templates\/issue\/([^/]+)(\/form)?$/);
 const scope=()=>location.pathname.match(/\/teams\/([^/]+)\//)?.[1]||null;
 const home=()=>scope()?'/qqq153/settings/teams/'+scope()+'/templates':'/qqq153/settings/issue-templates';
 const isForm=()=>location.pathname.endsWith('/form');
 const editor=(id='new',team=scope(),type=records().find(r=>r.id===id)?.template_type)=>'/qqq153/settings/'+(team?'teams/'+team+'/':'')+'templates/issue/'+encodeURIComponent(id)+(type==='form'?'/form':'');
 const records=()=>getState()?.issue_templates||[];
 const fields={'Template name':'title','Template description':'description','Issue title':'issue_title','Issue description':'issue_description'};
 function values(){for(const [label,key]of Object.entries(fields)){const field=$('[aria-label="'+label+'"]');if(field)data[key]=field.innerText.trim();}if(!isForm())data.issue_content_html=$('[aria-label="Issue description"]').innerHTML;return data;}
 function error(message){let node=$('[data-issue-template-error]');if(!node){node=document.createElement('p');node.dataset.issueTemplateError='';node.className='document-save-error';node.role='alert';$('main form')?.prepend(node);}node.textContent=message;}
 async function save(){if(saving)return;values();if(!data.title){error('Template has no name. A name is required.');$('[aria-label="Template name"]').focus();return;}saving=true;try{await api('/api/entities/issue-templates'+(current?'/'+current.id:''),current?'PATCH':'POST',{...data,scope_team:scope(),...(current?{revision:current.revision}:{})});dirty=false;location.href=home();}catch(e){error(e.message);saving=false;}}
 function paint(){
  for(const button of $$('main button')){const label=button.getAttribute('aria-label')||'';
   if(label==='Set team')button.textContent=data.team?'Qqq153':'Team';
   if(label==='Change status')button.textContent=data.status||'Backlog';
   if(label.startsWith('Change priority'))button.textContent=data.priority==='No priority'?'Priority':data.priority;
   if(label.startsWith('Change assignee'))button.textContent=data.assignee?getAccount().display_name:'Assignee';
   if(label==='Change labels')button.textContent=data.labels?.length?data.labels.join(', '):'Labels';
  }
  const icon=$('[aria-label="Template icon"]');if(data.icon?.startsWith('emoji:'))icon.textContent=data.icon.slice(6);
 }
 function renderEditor(){
  const path=match();if(!path||bound)return;current=path[2]==='new'?null:records().find(x=>x.id===path[2]);if(path[2]!=='new'&&!current)return;
  const copy=records().find(x=>x.id===new URLSearchParams(location.search).get('copy'));data={template_type:isForm()?'form':'standard',form_fields:[],title:'',description:'',issue_title:'',issue_description:'',issue_content_html:'',team:scope(),status:scope()?'Backlog':null,priority:'No priority',assignee:null,labels:[],icon:'',...(current||copy||{})};
  const from=getState().issues.find(i=>i.id===new URLSearchParams(location.search).get('from'));if(from&&!current&&!copy)Object.assign(data,{title:from.title,issue_title:from.title,issue_description:from.description||'',priority:from.priority,assignee:from.assignee,labels:from.labels||[],project:from.project,team:from.team||'QQQ',status:from.status});
  for(const [label,key]of Object.entries(fields)){const field=$('[aria-label="'+label+'"]');if(!field)continue;field.contentEditable='true';field.setAttribute('aria-readonly','false');field.textContent=data[key]||'';if(key==='issue_description'&&data.issue_content_html)field.innerHTML=data.issue_content_html;field.addEventListener('input',()=>{dirty=true;field.dataset.empty=String(!field.innerText.trim());});field.addEventListener('paste',e=>{e.preventDefault();const rich=e.clipboardData.getData('text/html');if(key==='issue_description'&&rich)document.execCommand('insertHTML',false,cleanPaste(rich));else document.execCommand('insertText',false,e.clipboardData.getData('text/plain'));dirty=true;});}
  if(current){const button=$('button[aria-label="Create"]');button.textContent='Save';button.setAttribute('aria-label','Save');document.title='Edit '+current.title+' template · Linear';}
  for(const form of $$('main form'))form.addEventListener('submit',e=>{e.preventDefault();e.stopPropagation();save();});
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();save();}});addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});if(isForm())formFields=createFormFields({getState,getTeam:()=>data.scope_team||data.team,get:()=>data.form_fields||[],set:fields=>{data.form_fields=fields;dirty=true;},menu});subissues=subissueTemplates({get:()=>data.subissue_templates||[],set:value=>{data.subissue_templates=value;dirty=true;},getState,getAccount,modal,closeDialog,menu,attachments});paint();bound=true;
 }
 function rowMenu(anchor,item){menu(anchor,[{text:'Edit',href:editor(item.id,item.scope_team)},{text:'Duplicate…',href:editor('new',item.scope_team,item.template_type)+'?copy='+encodeURIComponent(item.id)},{text:'Copy URL to create issue from template',action:async()=>{await navigator.clipboard.writeText(location.origin+'/team/QQQ/new?template='+encodeURIComponent(item.id));toast('URL copied to clipboard');}},{text:getState().default_issue_template===item.id?'Remove as default':'Set as default',action:async()=>{await api('/api/issue-templates/default','PUT',{team:scope()||'QQQ',template_id:getState().default_issue_template===item.id?null:item.id});await refresh();}},{text:'Delete',action:()=>modal('Delete the template "'+item.title+'"?','<p>You cannot undo this action.</p>','Delete',async()=>{await api('/api/entities/issue-templates/'+item.id,'DELETE');closeDialog();await refresh();},true)}]);}
 function renderList(){
  if(!['/qqq153/settings/issue-templates','/qqq153/settings/teams/'+scope()+'/templates'].includes(location.pathname))return;
  const list=records().filter(t=>(t.scope_team||null)===scope()).sort((a,b)=>a.sort_order-b.sort_order);$('[data-issue-template-list]')?.remove();const empty=$$('main *').find(e=>!e.children.length&&(e.textContent.trim()==='No issue templates'||e.dataset.issueTemplateCount));
  if(empty){empty.dataset.issueTemplateCount='true';empty.textContent=list.length?list.length+' issue template'+(list.length===1?'':'s'):'No issue templates';}
  if(!list.length)return;const box=document.createElement('section');box.dataset.issueTemplateList='';box.className='document-template-list';
  for(const item of list){const row=document.createElement('article'),link=document.createElement('a'),details=document.createElement('span'),button=document.createElement('button');row.dataset.issueTemplate=item.id;link.href=editor(item.id,item.scope_team);link.textContent=item.title;details.textContent=getState().default_issue_template===item.id?'Default':item.description||(item.template_type==='form'?'Custom Form':'Standard');button.type='button';button.textContent='…';button.setAttribute('aria-label','Open menu');button.onclick=e=>{e.stopPropagation();rowMenu(button,item);};row.append(link,details,button);box.append(row);}if(empty)empty.parentElement.after(box);else $('main').append(box);
 }
 async function handleClick(button){const label=(button.getAttribute('aria-label')||button.innerText||'').trim();
  if(label.startsWith('Create new issue template')){const box=modal('Choose issue template type','<div class="issue-template-types"><a href="'+editor()+'"><strong>Standard</strong><p>Basic template with title, description, and default attributes</p></a><a href="'+editor('new',scope(),'form')+'"><strong>Custom Form</strong><p>Define structured fields and inputs. Ideal for Asks</p></a></div>',null,null);return true;}
  if(!match()||!button.closest('main'))return false;
  const select=(field,options)=>menu(button,options.map(([title,value])=>({text:title,action:()=>{data[field]=value;if(field==='team'&&!value)data.status=null;dirty=true;paint();}})));
  if(['Create','Save'].includes(label))await save();else if(label==='Cancel'){dirty=false;location.href=home();}
  else if(label==='Set team')select('team',scope()?[['Qqq153','QQQ']]:[['No team',null],['Qqq153','QQQ']]);
  else if(label==='Change status')select('status',getState().workflow_states.map(s=>[s.title,s.title]));
  else if(label.startsWith('Change priority'))select('priority',['No priority','Urgent','High','Medium','Low'].map(p=>[p,p]));
  else if(label.startsWith('Change assignee'))select('assignee',[['Unassigned',null],[getAccount().display_name,getAccount().email_normalized]]);
  else if(label==='Change labels')menu(button,getState().labels.map(item=>({text:(data.labels.includes(item.title)?'✓ ':'')+item.title,action:()=>{data.labels=data.labels.includes(item.title)?data.labels.filter(x=>x!==item.title):[...data.labels,item.title];dirty=true;paint();}})),'Search labels…');
  else if(label==='Add field')formFields.add(button);
  else if(label==='Add sub-issue')subissues.add();
  else if(label==='Open menu')menu(button,[{text:'Add sub-issue',action:()=>subissues.add()}]);
  else if(label==='Template icon')await chooseDocumentIcon({modal,closeDialog,toast,onSelect:async icon=>{data.icon=icon;dirty=true;paint();}});
  else return false;return true;
 }
 return {render:()=>{renderEditor();renderList();},handleClick,editor};
}
