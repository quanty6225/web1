window.teamworkWebhookEvents=["BUDGET.CREATED", "BUDGET.DELETED", "BUDGET.UPDATED", "CALENDAREVENT.CREATED", "CALENDAREVENT.DELETED", "CALENDAREVENT.REMINDER", "CALENDAREVENT.UPDATED", "COMMENT.CREATED", "COMMENT.DELETED", "COMMENT.UPDATED", "COMPANY.CREATED", "COMPANY.DELETED", "COMPANY.UPDATED", "EXPENSE.CREATED", "EXPENSE.DELETED", "EXPENSE.UPDATED", "FILE.CREATED", "FILE.DELETED", "FILE.DOWNLOADED", "FILE.MOVED", "FILE.TAGGED", "FILE.UNTAGGED", "FILE.UPDATED", "FORM.CREATED", "FORM.DELETED", "FORM.PUBLISHED", "FORM.SUBMITTED", "GOOGLEDRIVE.CONNECTED", "GOOGLEDRIVE.INTEGRATED", "INVOICE.COMPLETED", "INVOICE.CREATED", "INVOICE.DELETED", "INVOICE.REOPENED", "INVOICE.UPDATED", "LINK.CREATED", "LINK.DELETED", "LINK.TAGGED", "LINK.UNTAGGED", "LINK.UPDATED", "MESSAGE.CREATED", "MESSAGE.DELETED", "MESSAGE.TAGGED", "MESSAGE.UNTAGGED", "MESSAGE.UPDATED", "MESSAGEREPLY.CREATED", "MESSAGEREPLY.DELETED", "MESSAGEREPLY.UPDATED", "MILESTONE.COMPLETED", "MILESTONE.CREATED", "MILESTONE.DELETED", "MILESTONE.REMINDER", "MILESTONE.REOPENED", "MILESTONE.TAGGED", "MILESTONE.UNTAGGED", "MILESTONE.UPDATED", "NOTEBOOK.CREATED", "NOTEBOOK.DELETED", "NOTEBOOK.TAGGED", "NOTEBOOK.UNTAGGED", "NOTEBOOK.UPDATED", "PORTFOLIOBOARD.CREATED", "PORTFOLIOBOARD.DELETED", "PORTFOLIOBOARD.UPDATED", "PORTFOLIOCARD.CREATED", "PORTFOLIOCARD.DELETED", "PORTFOLIOCARD.MOVED", "PORTFOLIOCARD.REOPENED", "PORTFOLIOCARD.UPDATED", "PORTFOLIOCOLUMN.CREATED", "PORTFOLIOCOLUMN.DELETED", "PORTFOLIOCOLUMN.UPDATED", "PROJECT.ARCHIVED", "PROJECT.COMPLETED", "PROJECT.COPIED", "PROJECT.CREATED", "PROJECT.DELETED", "PROJECT.REOPENED", "PROJECT.TAGGED", "PROJECT.UNTAGGED", "PROJECT.UPDATED", "PROJECTRATE.UPDATED", "PROJECTUPDATE.CREATED", "PROJECTUPDATE.DELETED", "PROJECTUPDATE.UPDATED", "RISK.CREATED", "RISK.DELETED", "RISK.UPDATED", "ROLE.CREATED", "ROLE.DELETED", "ROLE.UPDATED", "STAGE.CREATED", "STAGE.DELETED", "STAGE.UPDATED", "STATUS.CREATED", "STATUS.DELETED", "STATUS.UPDATED", "TASK.COMPLETED", "TASK.CREATED", "TASK.DELETED", "TASK.MOVED", "TASK.REMINDER", "TASK.REOPENED", "TASK.TAGGED", "TASK.UNTAGGED", "TASK.UPDATED", "TASKLIST.COMPLETED", "TASKLIST.CREATED", "TASKLIST.CREATEDFROMTEMPLATE", "TASKLIST.DELETED", "TASKLIST.REOPENED", "TASKLIST.UPDATED", "TEAM.CREATED", "TEAM.DELETED", "TEAM.UPDATED", "TIME.CREATED", "TIME.DELETED", "TIME.TAGGED", "TIME.UNTAGGED", "TIME.UPDATED", "TIMER.CREATED", "USER.CREATED", "USER.DELETED", "USER.UPDATED", "WORKFLOW.CREATED", "WORKFLOW.DELETED", "WORKFLOW.UPDATED"];
/* Settings controllers for captured modern pages and legacy content frames. */
(()=>{'use strict';
const b=window.teamworkSettings;if(!b)return;const {$,$$,esc,api,dialog,close,toast,field,select,pathname}=b;
const part=pathname.split('/').pop(),legacy=['templates','tags','forms','export','email','webhooks','import','beta'].includes(part);
if(legacy&&document.body.dataset.frame!=='true')return;if(!legacy&&document.body.dataset.frame==='true')return;
let settings={},tags=[],permissionGroups=[],selected=new Set(),ready=false;
const ws=()=>b.workspace();
const section=el=>el.closest('.f-setting-group')||el.closest('section')||el.parentElement.parentElement;
const title=el=>$('h3,h2,h4',section(el))?.textContent.trim()||'';
const record=(kind)=>ws().records.filter(r=>r.kind===kind);
const form=(name,heading,body,submit='Save')=>dialog(heading,`<form data-settings-form="${name}">${body}<div class="local-error" role=alert></div><button class=local-primary>${submit}</button><button type=button data-action=close>Cancel</button></form>`);
const area=(name,label,value='')=>`<label>${esc(label)}<textarea name="${name}" rows=5>${esc(value)}</textarea></label>`;
const options=(name,label,items,value='')=>`<label>${esc(label)}<select name="${name}">${items.map(([v,t])=>`<option value="${esc(v)}" ${v===value?'selected':''}>${esc(t)}</option>`).join('')}</select></label>`;
function panel(key,target=document.querySelector('main')||document.body){let n=$('#settings-'+key);if(!n){n=document.createElement('section');n.id='settings-'+key;n.className='local-records';target.append(n)}return n}
const actions=(r)=>`<button data-settings-edit="${r.id}">Edit</button><button data-settings-delete="${r.id}">Delete</button>`;
function workflow(r){form('workflow','Create workflow',`<input type=hidden name=id value="${r?.id||''}">`+field('title','Workflow name','text',r?.data.title||'',true)+area('stages','Stages — one per line',(r?.data.stages||['Backlog','To do','In progress','Completed']).join('\n')),'Save workflow')}
function customfield(entity='Task',r){return b.customFieldDefinition(entity,r)}
function tagForm(tag){form('tag',tag?'Edit tag':'Add New Tag',`<input type=hidden name=previous value="${esc(tag?.title||'')}">`+field('title','Name','text',tag?.title||'',true)+field('color','Color','color',tag?.color||'#6e65c2')+options('project','Project Specific',[['','All Projects'],...ws().projects.map(p=>[p.id,p.name])],tag?.project||''),'Add Tag')}
function webhook(r){form('webhook','Add Webhook',`<input type=hidden name=id value="${r?.id||''}">`+select('event','Webhook Event',window.teamworkWebhookEvents||['TASK.CREATED','TASK.UPDATED','TASK.DELETED'],r?.data.event||'TASK.CREATED')+field('url','Endpoint URL','url',r?.data.url||'',true)+select('version','Version',['Version 2'],'Version 2')+select('content_type','Content Type',['JSON','XML','Form'],r?.data.content_type||'JSON')+field('token','Token','password',r?.data.token||'')+'<p>Events are captured in this workspace. External delivery is disabled in the offline clone.</p>','Add Webhook')}
function generatedForm(style='Basic formatting'){
 const markup=`<form action="${location.origin}/api/auth/login" method="post"><input type="hidden" name="embedded" value="1"><label>Email <input type="email" name="email" required></label><label>Password <input type="password" name="password" required></label><button type="submit">Log in</button></form>`;
 const formatted=style==='Table based'?markup.replace('<label>Email ','<table><tr><td>Email ').replace('</label><label>Password ','</td></tr><tr><td>Password ').replace('</label><button','</td></tr></table><button'):style==='CSS based'?markup.replace('<form ','<form style="display:grid;gap:12px;max-width:360px" '):markup;
 const input=$('textarea');if(input){input.value=formatted;input.readOnly=true;input.setAttribute('aria-label','Login form HTML');input.style.minHeight='180px'}
}
async function render(){
 if(part==='tags'){
  tags=await api('/api/settings/tags');const root=$('.u-tags__list');if(root)root.innerHTML=tags.map(t=>`<button class="u-tag" data-settings-tag="${esc(t.title)}" aria-pressed="${selected.has(t.title)}" style="border-color:${esc(t.color)}">${esc(t.title)} <span>${t.count}</span></button>`).join('');
  const controls=$('.s-settings-tags__edit-buttons');if(controls){controls.classList.remove('hidden');controls.hidden=!selected.size;for(const x of $$('button',controls))x.disabled=false}
 }
 if(part==='workflows'){const rows=record('workflow');const p=panel('workflows');p.innerHTML=rows.map(r=>`<article><h3>${esc(r.data.title)}</h3><p>${r.data.stages.map(esc).join(' → ')}</p>${actions(r)}<button data-settings-apply="${r.id}">Apply to projects</button></article>`).join('');for(const n of $$('main p'))if(n.textContent.includes('Start by adding your first workflow'))n.hidden=!!rows.length}
 if(part==='customfields')b.renderCustomFieldDefinitions();
 if(part==='webhooks'){panel('webhooks',$('.f-setting-group__body')?.parentElement.parentElement||document.body).innerHTML=record('webhook').map(r=>`<article><h3>${esc(r.data.event)}</h3><p>${esc(r.data.url)}</p>${actions(r)}</article>`).join('')+'<button data-settings-events>View captured events</button>';const check=$('input[type=checkbox]');if(check)check.checked=settings.webhooks_enabled}
 if(part==='forms')generatedForm();
 if(part==='export'){const p=panel('export',$('.s-settings-export__body')||document.body);p.innerHTML='<a class="local-primary" href="/api/settings/export" download>Download backup</a><p>The archive contains this workspace’s accessible projects, tasks, records and files.</p>'}
 if(part==='import'){panel('contacts').innerHTML=record('contact').map(r=>`<article><strong>${esc(r.data.name)}</strong> ${esc(r.data.email)} ${esc(r.data.company)} ${actions(r)}</article>`).join('')}
 if(part==='templates')for(const group of $$('.f-setting-group')){const heading=$('h3',group)?.textContent.trim(),keys={'Welcome Email Template':'welcome_email','Default Task Lists':'default_task_lists','Default Message Categories':'message_categories','Default Files Categories':'file_categories','Default Notebooks Categories':'notebook_categories','Default Link Categories':'link_categories'},key=keys[heading];if(!key)continue;let node=$('[data-saved-template]',group);if(!node){node=document.createElement('p');node.dataset.savedTemplate=key;$('.f-setting-group__body',group)?.append(node)}node.textContent=Array.isArray(settings[key])?settings[key].join(', '):settings[key];}
 if(part==='ai'){for(const [index,input] of $$('main input[type=checkbox]').entries()){const key='ai:'+index;input.dataset.workspaceSetting=key;if(key in settings)input.checked=settings[key]}}
 if(part==='beta'){for(const [index,input] of $$('input[type=checkbox]').entries()){const key='beta:'+index;input.dataset.workspaceSetting=key;if(key in settings)input.checked=settings[key]}}
 if(part==='email'){const check=$('input[type=checkbox]');if(check)check.checked=settings.email_logo;const p=panel('email-values');p.textContent='From address: '+settings.email_format;}
}
function stop(e){e.preventDefault();e.stopImmediatePropagation()}
window.addEventListener('click',async e=>{
 if(!ready)return;const el=e.target.closest('button,a,[role=button]');if(!el)return;const text=(el.getAttribute('aria-label')||el.textContent).trim(),groupTitle=title(el);
 try{
 if(el.dataset.settingsDelete){stop(e);const r=ws().records.find(r=>r.id===el.dataset.settingsDelete);form('delete','Delete '+(r?.data.title||'item'),`<input type=hidden name=id value="${el.dataset.settingsDelete}"><p>Delete this saved item?</p>`,'Delete');return}
 if(el.dataset.settingsEdit){stop(e);const r=ws().records.find(r=>r.id===el.dataset.settingsEdit);if(r.kind==='workflow')workflow(r);else if(r.kind==='customfield')customfield(r.data.entity,r);else if(r.kind==='webhook')webhook(r);else form('contact','Edit contact',`<input type=hidden name=id value="${r.id}">`+field('name','Name','text',r.data.name,true)+field('email','Email','email',r.data.email,true)+field('company','Company','text',r.data.company));return}
 if(el.dataset.settingsApply){stop(e);form('apply','Apply workflow',`<input type=hidden name=id value="${el.dataset.settingsApply}">`+ws().projects.map(p=>`<label><input type=checkbox name=project value="${p.id}">${esc(p.name)}</label>`).join(''),'Apply');return}
 if(el.hasAttribute('data-settings-events')){stop(e);const rows=await api('/api/settings/webhook-events');dialog('Captured webhook events',rows.length?rows.map(r=>`<p>${esc(r.event)} · ${esc(r.payload.path)} · ${esc(r.payload.status)}</p>`).join(''):'<p>No captured events.</p>');return}
 if(el.dataset.settingsTag){stop(e);const name=el.dataset.settingsTag;selected.has(name)?selected.delete(name):selected.add(name);await render();return}
 if(part==='workflows'&&text==='Add workflow'){stop(e);workflow();return}
 if(part==='customfields'&&text==='Add custom field'){stop(e);const i=$$('main button').filter(n=>n.textContent.trim()==='Add custom field').indexOf(el);customfield(['Client','Project','Task'][i]||'Task');return}
 if(part==='tags'){
  if(text==='Add New Tag'){stop(e);tagForm();return}
  if(text==='Clear selection'){stop(e);selected.clear();await render();return}
  if(el.id==='editTagsBtn'){stop(e);tagForm(tags.find(t=>t.title===[...selected][0]));return}
  if(el.id==='mergeTagsBtn'||/delete/i.test(el.title||el.getAttribute('aria-label')||'')){stop(e);form('merge','Merge or delete tags',options('target','Merge into',[['','Delete selected tags'],...tags.map(t=>[t.title,t.title])])+`<p>${[...selected].map(esc).join(', ')}</p>`,'Apply');return}
 }
 if(part==='webhooks'&&text==='Add Webhook'){stop(e);webhook();return}
 if(part==='forms'&&['Basic formatting','CSS based','Table based'].includes(text)){stop(e);generatedForm(text);el.setAttribute('aria-selected','true');return}
 if(part==='templates'){
  const keys={'Default Task Lists':'default_task_lists','Default Message Categories':'message_categories','Default Files Categories':'file_categories','Default Notebooks Categories':'notebook_categories','Default Link Categories':'link_categories'};
  if(text==='Set Message'){stop(e);form('settings','Welcome Email Template','<input type=hidden name=key value=welcome_email>'+area('value','This message will be sent to new users with the invitation email.',settings.welcome_email),'Save Template');return}
  if(text==='Change'&&groupTitle==='New User on Project'){
   stop(e);permissionGroups=await api('/api/settings/permissions');const buttons=$$('button',section(el)).filter(n=>n.textContent.trim()==='Change'),group=permissionGroups[buttons.indexOf(el)];if(!group)throw Error('Permission group not found.');form('permissions','New User on Project — '+['Owner Company','Other Companies','Collaborators'][buttons.indexOf(el)],`<input type=hidden name=group value="${group.group}">`+group.permissions.map(p=>`<label><input type=checkbox name="${esc(p.name)}" ${group.values[p.name]?'checked':''} ${p.locked?'disabled':''}>${esc(p.name)}</label>`).join(''),'Finished');return
  }
  if(text==='Set-up'&&groupTitle==='Default Projects'){
   stop(e);form('default-projects','Manage Default Projects',ws().projects.map(project=>options(project.id,project.name,[['none','Not a default'],['owner','Owner Company'],['any','Any Company']],(settings['default_projects:other_company']||[]).includes(project.id)?'any':(settings['default_projects:owner_company']||[]).includes(project.id)?'owner':'none')).join(''),'Finished');return
  }
  if(text==='Edit'&&keys[groupTitle]){stop(e);const key=keys[groupTitle];form('settings',groupTitle,`<input type=hidden name=key value="${key}">`+area('value','One item per line',settings[key].join('\n')),'Finished');return}
 }
 if(part==='email'){
  if(text==='Change Format'){stop(e);form('settings','From Address Format','<input type=hidden name=key value=email_format>'+select('value','Format',['[firstname] [lastname] ([installationName])','[firstname] [lastname] via [installationName]','[firstname] [lastname] via Teamwork','[firstname] [lastname] via Teamwork Projects'],settings.email_format),'Set Format');return}
  if(text==='View Logs'){stop(e);dialog('Failed Log','<p>No failed emails found.</p>');return}
  if(text==='Choose Default User'){stop(e);dialog('Default User Posting via Email',`<p>${esc(ws().account.display_name)}</p><p>Only local workspace accounts can post through this clone.</p>`);return}
  if(text==='Change how these are processed'){stop(e);const key=groupTitle==='Similar Messages'?'email_similar':'email_forwarded';form('settings',groupTitle,`<input type=hidden name=key value="${key}">`+select('value',groupTitle,key==='email_similar'?['Always create a new message','Match the subject and add as a reply']:['Treat as normal messages','Extract the original message'],settings[key]?(key==='email_similar'?'Match the subject and add as a reply':'Extract the original message'):(key==='email_similar'?'Always create a new message':'Treat as normal messages')));return}
 }
 if(part==='import'&&text==='Import'){stop(e);const card=el.closest('.f-setting-group')||el.parentElement.parentElement;const description=card.textContent;const kind=/Contacts/i.test(description)?'contacts':/Users/i.test(description)?'users':null;if(kind){form('import','Import '+kind,`<input type=hidden name=kind value="${kind}"><p>Choose a UTF-8 CSV or vCard file.${kind==='users'?' Each user receives a local invitation email.':''}</p><a href="/api/settings/import/sample" download>Download Sample CSV</a><label>File<input name=file type=file accept=".csv,.vcf,text/csv,text/vcard" required></label>`,'Upload');return}dialog('Import','<p>Online provider authorization is unavailable in this offline workspace.</p><p>Export users or contacts as CSV/vCard and use the corresponding import below.</p>');return}
 }catch(err){toast(err.message,true)}
},true);
window.addEventListener('submit',async e=>{
 const f=e.target;if(!f.dataset.settingsForm)return;stop(e);const data=Object.fromEntries(new FormData(f)),kind=f.dataset.settingsForm;
 try{
 if(kind==='permissions'){const group=permissionGroups.find(g=>g.group===data.group),value=Object.fromEntries(group.permissions.map(p=>[p.name,p.locked?p.enabled:Object.hasOwn(data,p.name)]));await api('/api/settings','PUT',{['permission:'+group.group]:value})}
 else if(kind==='default-projects'){await api('/api/settings','PUT',{'default_projects:owner_company':Object.keys(data).filter(k=>['owner','any'].includes(data[k])),'default_projects:other_company':Object.keys(data).filter(k=>data[k]==='any')})}
 else if(kind==='settings'){let value=data.value;if(Array.isArray(settings[data.key]))value=value.split('\n').map(v=>v.trim()).filter(Boolean);else if(typeof settings[data.key]==='boolean')value=/Match|Extract/.test(value);await api('/api/settings','PUT',{[data.key]:value})}
 else if(kind==='tag')await api('/api/settings/tags','POST',data);
 else if(kind==='merge'){await api('/api/settings/tags/merge','POST',{names:[...selected],target:data.target});selected.clear()}
 else if(kind==='delete')await api('/api/records/'+data.id,'DELETE');
 else if(kind==='apply'){const ids=new FormData(f).getAll('project');if(!ids.length)throw Error('Select at least one project.');for(const id of ids)await api('/api/projects/'+id+'/workflow','POST',{workflow_id:data.id})}
 else if(kind==='import'){const result=await api('/api/settings/import/'+data.kind,'POST',new FormData(f));toast(result.imported+' '+result.status.toLowerCase())}
 else{const id=data.id;delete data.id;if(kind==='workflow')data.stages=data.stages.split('\n').map(x=>x.trim()).filter(Boolean);if(kind==='customfield')data.choices=data.choices.split('\n').map(x=>x.trim()).filter(Boolean);if(kind==='webhook')data.title=data.event;if(kind==='contact')data.title=data.name;await api(id?'/api/records/'+id:'/api/records/'+kind,id?'PATCH':'POST',data)}
 close();await b.refresh();settings=await api('/api/settings');await render();toast('Saved');
 }catch(err){$('.local-error',f).textContent=err.message}
},true);
window.addEventListener('change',async e=>{if(!ready||e.target.closest('#local-dialog'))return;const input=e.target;if(input.type!=='checkbox')return;const key=input.dataset.workspaceSetting||(part==='webhooks'?'webhooks_enabled':part==='email'?'email_logo':null);if(key){stop(e);try{await api('/api/settings','PUT',{[key]:input.checked});settings[key]=input.checked;toast('Saved')}catch(err){toast(err.message,true)}}},true);
async function start(){settings=await api('/api/settings');ready=true;await render()}
start().catch(e=>toast(e.message,true));
})();
