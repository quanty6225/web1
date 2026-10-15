import {mountIssueForm} from '/static/issue-forms.js';
const $=(s,r=document)=>r.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const day=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
const asDate=s=>new Date(s+'T12:00:00');
const fullDate=d=>d.toLocaleDateString('en-US',{weekday:'long',year:'numeric',month:'long',day:'numeric'});

export function createIssueProperties(env){
 const {api,menu,modal,closeDialog,closeMenu,refresh,copy,toast,issueURL}=env;
 const issue=()=>env.getIssue(), all=()=>env.getState().issues;
 const copyDescriptions=fetch('/static/issue-copy-descriptions.json').then(r=>{if(!r.ok)throw Error('Unable to load issue formatting.');return r.json();});
 async function update(data,id=issue().id){await api('/api/entities/issues/'+id,'PATCH',data);await refresh();}
 function run(fn){return e=>{e?.stopPropagation();Promise.resolve().then(fn).catch(e=>toast(e.message));};}
 function dueDate(anchor){
  const now=new Date(),shift=n=>{const d=new Date(now);d.setDate(d.getDate()+n);return day(d);};
  menu(anchor,[{text:'Custom…',action:calendar},{text:'Tomorrow',action:()=>update({due_date:shift(1)})},{text:'End of this week',action:()=>update({due_date:shift((5-now.getDay()+7)%7)})},{text:'In one week',action:()=>update({due_date:shift(7)})},...(issue().due_date?[null,{text:'Remove due date',action:()=>update({due_date:null})}]:[])]);
 }
 function calendar(){
  let selected=issue().due_date||'',month=selected?asDate(selected):new Date();month=new Date(month.getFullYear(),month.getMonth(),1);
  const o=modal('Set due date','<p>Due date - Issue needs to be completed by this date</p><input name="date" aria-label="Due date" autocomplete="off" value="'+esc(selected)+'" required><div class="issue-calendar-nav"><button type="button" data-prev aria-label="Previous month">‹</button><button type="button" data-next aria-label="Next month">›</button></div><div class="issue-calendars"></div>','Save due date',async f=>{
   let text=f.get('date').trim(),date=asDate(text);if(!/^\d{4}-\d{2}-\d{2}$/.test(text)){date=new Date(text);text=Number.isFinite(+date)?day(date):'';}
   if(!text||!Number.isFinite(+date)||day(date)!==text)throw Error('Enter a valid due date.');await update({due_date:text});closeDialog();
  });
  const draw=()=>{const root=$('.issue-calendars',o);root.replaceChildren();for(let n=0;n<2;n++){
   const date=new Date(month.getFullYear(),month.getMonth()+n,1),box=document.createElement('section');box.innerHTML='<h3>'+date.toLocaleDateString('en-US',{month:'long',year:'numeric'})+'</h3><div class="issue-days">'+['Su','Mo','Tu','We','Th','Fr','Sa'].map(x=>'<span>'+x+'</span>').join('')+'</div>';
   const grid=$('.issue-days',box),offset=date.getDay();for(let j=0;j<offset;j++)grid.append(document.createElement('span'));
   for(let j=1;j<=new Date(date.getFullYear(),date.getMonth()+1,0).getDate();j++){const d=new Date(date.getFullYear(),date.getMonth(),j),b=document.createElement('button');b.type='button';b.textContent=j;b.setAttribute('aria-label',fullDate(d));b.setAttribute('aria-pressed',String(day(d)===selected));b.onclick=()=>{selected=day(d);$('[name=date]',o).value=selected;draw();};grid.append(b);}root.append(box);
  }};
  $('[data-prev]',o).onclick=()=>{month.setMonth(month.getMonth()-1);draw();};$('[data-next]',o).onclick=()=>{month.setMonth(month.getMonth()+1);draw();};draw();
 }
 const markFields={'Parent of…':'child','Sub-issue of…':'parent','Related to…':'related','Blocked by…':'blocked_by','Blocking…':'blocks','Duplicate of…':'duplicate_of'};
 function markMenu(anchor){menu(anchor,Object.keys(markFields).map(text=>({text,action:()=>search(markFields[text])})));}
 async function relate(field,target){
  if(field==='child')await update({parent:issue().id},target);
  else if(['parent','duplicate_of'].includes(field))await update({[field]:target});
  else await update({[field]:[...new Set([...(issue()[field]||[]),target])]});
 }
 function search(field){
  const id=issue().id,placeholder={child:'Search for issue to add as a sub-issue…',parent:'Search for issue to set as a parent…',related:'Search for issue to reference…',blocked_by:'Search for issue to mark blocked by…',blocks:'Search for issue to mark as blocked by '+id+'…',duplicate_of:'Search for issue to mark as duplicate of…'}[field];
  closeMenu();closeDialog();const o=document.createElement('div');o.className='local-overlay issue-command-overlay';o._opener=document.activeElement;o.innerHTML='<section class="issue-command"><input role="combobox" aria-label="Command menu" aria-expanded="true" aria-controls="issue-command-results" placeholder="'+esc(placeholder)+'"><div id="issue-command-results" role="listbox"></div><p role="alert"></p></section>';document.body.append(o);env.setDialog(o);o.onclick=e=>{if(e.target===o)closeDialog();};
  const input=$('input',o),list=$('[role=listbox]',o);let active=0;
  const draw=()=>{list.replaceChildren();const query=input.value.toLowerCase(),rows=all().filter(x=>x.id!==id&&(x.id+' '+x.title).toLowerCase().includes(query));const heading=document.createElement('div');heading.className='issue-command-heading';heading.textContent=query?'Quick results for "'+input.value+'"':'Similar issues';list.append(heading);active=0;
   for(const x of rows){const b=document.createElement('button');b.type='button';b.role='option';b.id='relation-option-'+x.id;b.textContent=x.id+' '+x.title;b.onclick=async()=>{try{await relate(field,x.id);closeDialog();}catch(e){$('[role=alert]',o).textContent=e.message;}};list.append(b);}
   if(!rows.length){const empty=document.createElement('p');empty.textContent='No results';list.append(empty);}select();
  };
  const select=()=>{const rows=[...list.querySelectorAll('[role=option]')];rows.forEach((b,i)=>b.setAttribute('aria-selected',String(i===active)));if(rows[active])input.setAttribute('aria-activedescendant',rows[active].id);else input.removeAttribute('aria-activedescendant');};
  input.oninput=draw;input.onkeydown=e=>{const rows=[...list.querySelectorAll('[role=option]')];if(!rows.length)return;if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();active=(active+(e.key==='ArrowDown'?1:-1)+rows.length)%rows.length;select();}if(e.key==='Enter'){e.preventDefault();rows[active].click();}};draw();input.focus();
 }
 async function removeRelation(field,target){
  const current=issue(),other=all().find(x=>x.id===target);
  if(field==='parent')return update({parent:null});
  if(field==='child')return update({parent:null},target);
  if(field==='duplicate_of')return update({duplicate_of:null});
  const opposite={related:'related',blocked_by:'blocks',blocks:'blocked_by'}[field];
  if(other?.[opposite]?.includes(current.id))await api('/api/entities/issues/'+target,'PATCH',{[opposite]:other[opposite].filter(x=>x!==current.id)});
  await update({[field]:(current[field]||[]).filter(x=>x!==target)});
 }
 function link(){modal('Add link to '+issue().id,'<label>URL<input name="url" type="url" placeholder="https://…" required></label><label>Title (optional)<input name="title"></label>','Add link',async f=>{
  const url=new URL(f.get('url'));if(!['https:','http:'].includes(url.protocol))throw Error('Enter an HTTP or HTTPS link.');await update({links:[...(issue().links||[]),{id:crypto.randomUUID(),url:url.href,title:f.get('title').trim()}]});closeDialog();
 },true);}
 function history(){
  const current=issue(),versions=[{description:current.description||'',description_edited:current.description_edited,at:current.description_updated_at||current.created_at,current:true},...(current.description_history||[]).slice().reverse()];let selected=0;
  const o=modal('Restore version for '+current.id+' '+current.title,'<div class="issue-versions"><nav></nav><pre></pre></div>','Restore version',async()=>{await update({description:versions[selected].description,description_edited:versions[selected].description_edited??true});closeDialog();});
  const draw=()=>{$('pre',o).textContent=versions[selected].description;const submit=$('[type=submit]',o);submit.disabled=!!versions[selected].current;submit.setAttribute('aria-label',versions[selected].current?'This is the current version, you cannot restore it':'Restore version');};
  versions.forEach((v,n)=>{const b=document.createElement('button');b.type='button';b.textContent=new Date(v.at*1000).toLocaleString('en-US')+(v.current?' · Current':'');b.onclick=()=>{selected=n;draw();};$('nav',o).append(b);});draw();
 }
 function editor(mode='issue',parentId=null,defaults={}){
  const scratchKey='linear-issue-scratch:'+env.getState().workspace.id;
  if(mode==='issue'&&!parentId&&!Object.keys(defaults).length){try{defaults=JSON.parse(sessionStorage.getItem(scratchKey)||'{}');}catch{}}

  const source=issue(),parent=parentId?all().find(x=>x.id===parentId):mode==='child'?source:null,isCopy=mode==='copy',account=env.getAccount();
  const seed=isCopy?{...source}:{priority:parent?.priority||'No priority',project:parent?.project||null,assignee:parent?.assignee===account.email_normalized?parent.assignee:null};
  const initialTemplate=mode==='issue'&&!parent&&!defaults.template?env.getState().issue_templates?.find(t=>t.id===env.getState().default_issue_template):env.getState().issue_templates?.find(t=>t.id===defaults.template);if(initialTemplate)Object.assign(seed,{title:initialTemplate.issue_title,description:initialTemplate.issue_description,status:initialTemplate.status||'Todo',priority:initialTemplate.priority,assignee:initialTemplate.assignee,labels:initialTemplate.labels,project:initialTemplate.project,template:initialTemplate.id});Object.assign(seed,defaults);
  if(parent&&!seed.assignee){const children=all().filter(x=>x.parent===parent.id);if(children.length&&children.every(x=>x.assignee===parent.assignee))seed.assignee=parent.assignee;}
  const states=env.getState().workflow_states.map(x=>x.title),priorities=['No priority','Urgent','High','Medium','Low'];
  const options=(values,selected)=>values.map(v=>'<option '+(v===selected?'selected':'')+'>'+esc(v)+'</option>').join('');
  const o=modal('QQQ › New issue','<input name="title" aria-label="Issue title" class="issue-title" placeholder="Issue title" required value="'+esc(isCopy?source.title+' (copy)':seed.title||'')+'"><textarea name="description" aria-label="Issue description" class="issue-description" placeholder="Add description…">'+esc(isCopy?source.description:seed.description||'')+'</textarea><div class="row"><select name="status" aria-label="Status">'+options(states,isCopy?source.status:seed.status||'Todo')+'</select><select name="priority" aria-label="Priority">'+options(priorities,seed.priority)+'</select><select name="assignee" aria-label="Assignee"><option value="">Assignee</option><option value="'+esc(account.email_normalized)+'" '+(seed.assignee===account.email_normalized?'selected':'')+'>'+esc(account.display_name)+'</option>'+(seed.assignee&&seed.assignee!==account.email_normalized?'<option selected>'+esc(seed.assignee)+'</option>':'')+'</select></div><label><input type="checkbox" name="more" '+(parent?'checked':'')+'> Create more</label>',isCopy?'Save copy':'Create issue',async f=>{
   if(files?.pending()||form?.pending())throw Error('Wait for the upload to finish.');const data=Object.fromEntries(f);delete data.more;data.attachments=files?.files()||[];data.form_answers=form?.answers()||{};data.project=seed.project||null;data.labels=[...(isCopy?source.labels||[]:seed.labels||[])];data.template=seed.template||null;if(defaults.draft_id){data.draft_id=defaults.draft_id;data.draft_revision=defaults.draft_revision;}if(seed.links)data.links=seed.links;data.description_edited=true;
   if(parent)data.parent=parent.id;if(mode==='related')data.related=[source.id];if(mode==='blocked')data.blocked_by=[source.id];if(mode==='blocking')data.blocks=[source.id];
   const created=await api('/api/entities/issues','POST',data);sessionStorage.removeItem(scratchKey);if(mode==='parent')await api('/api/entities/issues/'+source.id,'PATCH',{parent:created.id});await refresh();
   if(f.has('more')&&!defaults.draft_id){files?.clear();form?.remove();form=mountIssueForm({getState:env.getState,overlay:o,template:env.getState().issue_templates?.find(t=>t.id===seed.template),attachments:env.attachments});$('[name=title]',o).value='';$('[name=description]',o).value='';$('[name=title]',o).focus();}else closeDialog();toast('Issue created');
  });
  const files=env.attachments?.mountDraft(o,seed.attachments||[]);let form=mountIssueForm({getState:env.getState,overlay:o,template:env.getState().issue_templates?.find(t=>t.id===seed.template)||initialTemplate,answers:seed.form_answers||{},attachments:env.attachments});
  const snapshot=()=>{const value=Object.fromEntries(new FormData($('form',o)));delete value.more;return{...value,attachments:files?.files()||[],form_answers:form?.answers()||{},labels:[...(seed.labels||[])],project:seed.project||null,template:seed.template||null,...(parent?{parent:parent.id}:{}),...(seed.links?{links:seed.links}:{})};};
  const saveDraft=async value=>{if(files?.pending()||form?.pending())throw Error('Wait for the upload to finish.');await api('/api/entities/drafts'+(defaults.draft_id?'/'+defaults.draft_id:''),defaults.draft_id?'PATCH':'POST',{...value,...(defaults.draft_id?{revision:defaults.draft_revision}:{})});sessionStorage.removeItem(scratchKey);closeDialog();await refresh();toast('Draft saved');};
  const draftButton=document.createElement('button');draftButton.type='button';draftButton.textContent='Save as draft';draftButton.setAttribute('aria-label','Save draft');draftButton.onclick=async()=>{try{await saveDraft(snapshot());}catch(e){$('.local-inline-error',o).textContent=e.message;}};$('.local-close',o).before(draftButton);
  if(!isCopy&&!parent&&!defaults.draft_id)o.addEventListener('input',()=>{try{sessionStorage.setItem(scratchKey,JSON.stringify(snapshot()));}catch{}});
  const requestClose=()=>{if(isCopy){closeDialog();return;}const value=snapshot();if(!value.title.trim()&&!value.description.trim()&&!value.attachments?.length&&!Object.values(value.form_answers||{}).some(v=>Array.isArray(v)?v.length:!!v)){sessionStorage.removeItem(scratchKey);closeDialog();return;}
   const prompt=modal('Save to drafts?','<p>You can finish this issue later from your drafts.</p><button type="button" data-discard-draft>Discard</button>','Save',()=>saveDraft(value),true);
   $('[data-discard-draft]',prompt).onclick=()=>{sessionStorage.removeItem(scratchKey);closeDialog();};
   const resume=()=>{closeDialog();editor(mode,parentId,{...seed,...value,...(defaults.draft_id?{draft_id:defaults.draft_id,draft_revision:defaults.draft_revision}:{})});};$('[data-cancel]',prompt).onclick=resume;$('.local-close',prompt).onclick=resume;
  };
  $('.local-close',o).onclick=requestClose;$('[data-cancel]',o).onclick=requestClose;o.onclick=e=>{if(e.target===o)requestClose();};o.addEventListener('keydown',e=>{if(e.key==='Escape'&&!document.querySelector('.local-menu')){e.preventDefault();e.stopPropagation();requestClose();}});
  if(!isCopy){const picker=document.createElement('button');picker.type='button';picker.dataset.issueTemplatePicker='';picker.textContent=initialTemplate?.title||'Template';picker.onclick=()=>menu(picker,[{text:'No template',action:()=>{seed.template=null;picker.textContent='Template';form?.remove();form=null;}},...(env.getState().issue_templates||[]).filter(t=>!t.scope_team||t.scope_team===(document.body.dataset.activeTeam||issue()?.team||env.getState().teams[0]?.id||'QQQ')).map(t=>({text:t.title,action:()=>{Object.assign(seed,{template:t.id,project:t.project||null,labels:[...(t.labels||[])]});$('[name=title]',o).value=t.issue_title||'';$('[name=description]',o).value=t.issue_description||'';$('[name=status]',o).value=t.status||'Todo';$('[name=priority]',o).value=t.priority||'No priority';$('[name=assignee]',o).value=t.assignee||'';picker.textContent=t.title;form?.remove();form=mountIssueForm({getState:env.getState,overlay:o,template:t,attachments:env.attachments});}})),{text:'Manage templates',href:'/qqq153/settings/issue-templates'}],'Search templates…');$('.dialog-body',o).prepend(picker);if(defaults.pickTemplate)picker.click();}
  return o;
 }
 async function copyValue(name){
  const i=issue(),account=env.getAccount(),url=location.origin+issueURL(i),title=i.id+': '+i.title,source=(await copyDescriptions)[i.id],username=(account.display_name||account.email_normalized.split('@')[0]).trim().toLowerCase().replace(/[^a-z0-9._-]+/g,'-'),branch=username+'/'+i.id.toLowerCase()+'-'+i.title.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/-$/,'');
  const absolute=text=>text.replace(/([(<"])(\/(?:static|docs|external|qqq153|join-slack|settings)[^\s<>"\)]*)/g,(_,before,path)=>before+location.origin+path);
  const body=absolute(!i.description_edited&&source?source.markdown:i.description||''),markdown='# '+i.title+'\n\n'+body;
  let value;
  if(name==='Copy ID')value=i.id;else if(name==='Copy URL')value=url;else if(name==='Copy title')value=title;else if(name==='Copy title as link')value='['+title+']('+url+')';else if(name==='Copy git branch name')value=branch;
  else if(name==='Copy as prompt')value='Work on Linear issue '+i.id+':\n\nSuggested branch name: '+branch+'\n\n<issue identifier="'+esc(i.id)+'">\n<title>'+esc(i.title)+'</title>\n<description>\n'+absolute(!i.description_edited&&source?.prompt?source.prompt:i.description||'')+'\n</description>\n<team name="Qqq153"/>\n</issue>';
  else if(name==='Copy everything as Markdown')value=markdown.trimEnd()+'\n\n## Metadata\n- URL: ['+url+']('+url+')\n- Identifier: '+i.id+'\n- Status: '+i.status+'\n- Priority: '+i.priority+'\n- Assignee: '+(i.assignee||'Unassigned')+'\n- Created: '+new Date(i.created_at*1000).toISOString()+'\n- Updated: '+new Date(i.updated_at*1000).toISOString()+'\n'+(i.comments?.length?'\n## Comments\n'+i.comments.map(c=>'\n'+c.author+'\n\n'+c.body).join('\n'):'');
  else value=markdown;
  return copy(value);
 }
 function copyMenu(anchor){menu(anchor,['Copy ID','Copy URL','Copy title','Copy title as link','Copy issue as Markdown','Copy everything as Markdown','Copy git branch name','Copy as prompt'].map(text=>({text,action:()=>copyValue(text)})));}
 function reminderCalendar(){
  const today=new Date();today.setHours(0,0,0,0);let selected=new Date(today);selected.setDate(selected.getDate()+1);selected.setHours(9);let month=new Date(today.getFullYear(),today.getMonth(),1);
  const overlay=modal('Remind me about this issue on','<div class="issue-calendar-nav"><button type="button" data-prev aria-label="Previous month">‹</button><button type="button" data-next aria-label="Next month">›</button></div><div class="issue-calendars"></div>','Apply',async()=>{await update({remind_at:Math.floor(+selected/1000)});closeDialog();});
  const draw=()=>{const root=$('.issue-calendars',overlay);root.replaceChildren();$('[data-prev]',overlay).disabled=month<=today;
   for(let n=0;n<2;n++){const date=new Date(month.getFullYear(),month.getMonth()+n,1),box=document.createElement('section');box.innerHTML='<h3>'+date.toLocaleDateString('en-US',{month:'long',year:'numeric'})+'</h3><div class="issue-days">'+['Su','Mo','Tu','We','Th','Fr','Sa'].map(x=>'<span>'+x+'</span>').join('')+'</div>';const grid=$('.issue-days',box);for(let j=0;j<date.getDay();j++)grid.append(document.createElement('span'));
    for(let j=1;j<=new Date(date.getFullYear(),date.getMonth()+1,0).getDate();j++){const value=new Date(date.getFullYear(),date.getMonth(),j,9),button=document.createElement('button');button.type='button';button.textContent=j;button.disabled=value<=new Date(+today+86400000-1);button.setAttribute('aria-label',value.toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric'}));button.setAttribute('aria-pressed',String(value.toDateString()===selected.toDateString()));button.onclick=()=>{selected=value;draw();};grid.append(button);}root.append(box);
   }
  };$('[data-prev]',overlay).onclick=()=>{month.setMonth(month.getMonth()-1);draw();};$('[data-next]',overlay).onclick=()=>{month.setMonth(month.getMonth()+1);draw();};draw();
 }
 function reminders(anchor){
  const now=new Date(),next=days=>{const value=new Date(now);value.setDate(value.getDate()+days);value.setHours(9,0,0,0);return value;};
  const choices=[['An hour from now',new Date(+now+3600000)],['In 3 hours',new Date(+now+10800000)],['Tomorrow',next(1)],['Next week',next((8-now.getDay())%7||7)],['A month from now',(()=>{const value=next(0);value.setMonth(value.getMonth()+1);return value;})()]];
  const choose=async value=>update({remind_at:Math.floor(+value/1000)});
  const box=menu(anchor,[...choices.map(([text,value])=>({text,action:()=>choose(value)})),{text:'Custom…',action:reminderCalendar},...(issue().remind_at?[{text:'Cancel reminder',action:()=>update({remind_at:null})}]:[])],'Try: 4 pm, 2 days, in 5 weeks…');
  const input=$('input',box),custom=document.createElement('button');custom.role='menuitem';custom.hidden=true;box.append(custom);
  input.addEventListener('input',()=>{const text=input.value.trim().toLowerCase();let parsed=null;const duration=text.match(/^(?:in |for )?(\d+)\s+(minutes?|hours?|days?|weeks?|months?)$/),clock=text.match(/^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$/);
   if(duration){parsed=new Date(now);const value=+duration[1],unit=duration[2];if(unit.startsWith('month'))parsed.setMonth(parsed.getMonth()+value);else parsed=new Date(+now+value*(unit.startsWith('week')?604800000:unit.startsWith('day')?86400000:unit.startsWith('hour')?3600000:60000));}
   else if(clock&&+clock[1]>=1&&+clock[1]<=12&&+(clock[2]||0)<60){parsed=new Date(now);parsed.setHours(+clock[1]%12+(clock[3]==='pm'?12:0),+(clock[2]||0),0,0);if(parsed<=now)parsed.setDate(parsed.getDate()+1);}
   else if(text==='next quarter'){parsed=new Date(now.getFullYear(),Math.floor(now.getMonth()/3)*3+3,1,9);}
   else if(/^\d{4}-\d\d-\d\d|^[a-z]{3,9}\s+\d{1,2}/.test(text)){const value=new Date(text);if(Number.isFinite(+value))parsed=value;}
   custom.hidden=!parsed||!Number.isFinite(+parsed)||parsed<=now;if(!custom.hidden){custom.textContent=parsed.toLocaleString('en-US');custom.onclick=async()=>{closeMenu();try{await choose(parsed);}catch(error){toast(error.message);}};}
  });
 }
 function options(anchor){menu(anchor,[{text:'Due date ›',action:()=>dueDate(anchor)},{text:'Add link…',action:link},{text:'Add document…',action:()=>env.addDocument()},{text:'Create related ›',action:()=>menu(anchor,[['Issue…','related'],['Sub-issue…','child'],['Parent issue…','parent'],['Blocked issue…','blocked'],['Blocking issue…','blocking']].map(([text,mode])=>({text,action:()=>editor(mode)})))},{text:'Mark as ›',action:()=>markMenu(anchor)},{text:'Copy ›',action:()=>copyMenu(anchor)},{text:'Convert to ›',action:()=>menu(anchor,[{text:'Template…',href:'/qqq153/settings/teams/QQQ/templates/issue/new?from='+encodeURIComponent(issue().id)},{text:'Recurring issue…',href:'/qqq153/settings/teams/QQQ/recurring-issues/new?from='+encodeURIComponent(issue().id)}])},{text:'Make a copy…',action:()=>editor('copy')},{text:issue().favorite?'Unfavorite':'Favorite',action:()=>update({favorite:!issue().favorite})},{text:'Remind me ›',action:()=>reminders(anchor)},{text:issue().subscribed?'Unsubscribe':'Subscribe',action:()=>update({subscribed:!issue().subscribed})},{text:'Show description history',action:history},null,{text:'Delete',action:()=>modal('Delete issue','<p>Delete '+esc(issue().id)+'?</p>','Delete',async()=>{await api('/api/entities/issues/'+issue().id,'DELETE');location.href='/qqq153/team/QQQ/active';},true)}]);}
 function render(){
  let reminder=$('[data-issue-reminder]'),heading=$('main [aria-label="Issue title"]')||$('main h1')||$('[data-issue-title]');if(!reminder&&heading){reminder=document.createElement('button');reminder.dataset.issueReminder='';reminder.className='document-reminder';heading.before(reminder);reminder.onclick=()=>reminders(reminder);}let recurring=$('[data-issue-recurring]');if(recurring)recurring.remove();if(issue()?.recurring_issue_id&&heading){recurring=document.createElement('a');recurring.dataset.issueRecurring='';recurring.className='document-reminder';recurring.href='/qqq153/settings/teams/QQQ/recurring-issues/'+encodeURIComponent(issue().recurring_issue_id);recurring.textContent='Recurring issue';heading.before(recurring);}if(reminder){reminder.hidden=!issue()?.remind_at;reminder.textContent=issue()?.remind_at?'Remind me · '+new Date(issue().remind_at*1000).toLocaleString('en-US'):'';}
  const i=issue();if(!i)return;document.querySelectorAll('[data-issue-extra]').forEach(x=>x.remove());
  const labelsButton=$('button[aria-label="Add labels"]');if(labelsButton&&i.labels?.length){const labels=document.createElement('div');labels.dataset.issueExtra='labels';for(const label of i.labels){const b=document.createElement('button');b.textContent=label+' ×';b.setAttribute('aria-label','Remove label '+label);b.onclick=run(()=>update({labels:i.labels.filter(x=>x!==label)}));labels.append(b);}labelsButton.before(labels);}
  const projectButton=$('[data-issue-property=project]')||[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Add to project');if(projectButton){projectButton.dataset.issueProperty='project';projectButton.textContent=env.getState().projects.find(p=>p.id===i.project)?.title||'Add to project';}
  const props=[...document.querySelectorAll('h3')].find(x=>x.textContent==='Properties')?.parentElement.parentElement.parentElement;
  const panel=document.createElement('section');panel.dataset.issueExtra='properties';panel.className='issue-extra-properties';
  if(i.due_date){const b=document.createElement('button');b.textContent='Due date · '+asDate(i.due_date).toLocaleDateString('en-US',{month:'short',day:'numeric'});b.title=fullDate(asDate(i.due_date));b.setAttribute('aria-label','Due date');b.onclick=run(()=>dueDate(b));const remaining=(asDate(i.due_date)-asDate(day(new Date())))/86400000;b.dataset.urgency=remaining<=0?'overdue':remaining<=7?'soon':'later';panel.append(b);}
  const groups=[['parent','Parent issue',i.parent?[i.parent]:[]],['blocked_by','Blocked by',[...(i.blocked_by||[]),...all().filter(x=>x.blocks?.includes(i.id)).map(x=>x.id)]],['blocks','Blocks',[...(i.blocks||[]),...all().filter(x=>x.blocked_by?.includes(i.id)).map(x=>x.id)]],['related','Related',[...(i.related||[]),...all().filter(x=>x.related?.includes(i.id)).map(x=>x.id)]],['duplicate_of','Duplicate of',i.duplicate_of?[i.duplicate_of]:[]]];
  function relationRow(field,id){const item=all().find(x=>x.id===id);if(!item)return null;const row=document.createElement('div');row.className='issue-relation-row';row.innerHTML='<a href="'+esc(issueURL(item))+'">'+esc(item.id+' '+item.title)+'</a><button type="button" aria-label="Remove '+esc(field==='child'?'sub-issue':field.replaceAll('_',' '))+' '+esc(id)+'">×</button>';$('button',row).onclick=run(()=>removeRelation(field,id));return row;}
  for(const [field,title,ids] of groups){if(!ids.length)continue;const box=document.createElement('div');box.dataset.relation=field;const h=document.createElement('h3');h.textContent=title;box.append(h);for(const id of new Set(ids)){const row=relationRow(field,id);if(row)box.append(row);}panel.append(box);}props?.append(panel);
  const subButton=$('[aria-label="Add sub-issues"]');if(subButton){const box=document.createElement('section');box.dataset.issueExtra='subissues';box.className='issue-subissues';const children=all().filter(x=>x.parent===i.id);if(children.length){const h=document.createElement('h3');h.textContent='Sub-issues';box.append(h);for(const child of children)box.append(relationRow('child',child.id));}subButton.closest('[data-contextual-menu]')?.before(box);}
  const description=$('[aria-label="Issue description"]');if(i.duplicate_of&&description){const banner=document.createElement('div');banner.dataset.issueExtra='duplicate';banner.className='issue-duplicate-banner';banner.textContent='This issue is a duplicate of ';const canonical=all().find(x=>x.id===i.duplicate_of);if(canonical){const a=document.createElement('a');a.href=issueURL(canonical);a.textContent=canonical.id+' '+canonical.title;banner.append(a);}description.parentElement.before(banner);}
  if(i.links?.length&&description){const links=document.createElement('section');links.dataset.issueExtra='links';for(const item of i.links){const row=document.createElement('div');row.className='issue-relation-row';const a=document.createElement('a');a.textContent=item.title||item.url;a.href='/external?target='+btoa(unescape(encodeURIComponent(item.url)));const b=document.createElement('button');b.type='button';b.textContent='×';b.setAttribute('aria-label','Remove link '+(item.title||item.url));b.onclick=run(()=>update({links:i.links.filter(x=>x.id!==item.id)}));row.append(a,b);links.append(row);}description.parentElement.after(links);}
 }
 function renderDrafts(){
  if(location.pathname!=='/qqq153/drafts')return;const items=env.getState().drafts||[],main=$('main');if(!main)return;let list=$('[data-draft-list]');if(!list){list=document.createElement('section');list.dataset.draftList='';main.append(list);}list.replaceChildren();
  const empty=[...main.querySelectorAll('*')].find(e=>!e.children.length&&e.textContent.trim()==='No active drafts');if(empty)empty.hidden=!!items.length;
  for(const item of items){const row=document.createElement('div');row.className='local-issue-row';row.dataset.draftId=item.id;const open=document.createElement('button');open.textContent=item.title||'Untitled issue';open.style.flex='1';open.style.textAlign='left';open.onclick=e=>{e.stopPropagation();editor(item.parent?'child':'issue',item.parent||null,{...item,draft_id:item.id,draft_revision:item.revision});};const more=document.createElement('button');more.textContent='…';more.setAttribute('aria-label','Draft options');more.onclick=e=>{e.stopPropagation();menu(more,[{text:'Delete',action:()=>modal('Delete draft','<p>Delete this draft?</p>','Delete',async()=>{await api('/api/entities/drafts/'+item.id,'DELETE');closeDialog();await refresh();},true)}]);};row.append(open,more);list.append(row);}
 }
 function renderSidebar(){
  const button=$('button[aria-controls="sidebarFavorites"]'),section=button?.closest('[data-sidebar-section]');if(!section)return;const wrapper=section.parentElement,items=all().filter(x=>x.favorite);let list=$('#sidebarFavorites',section);
  if(!list){list=document.createElement('div');list.id='sidebarFavorites';button.parentElement.after(list);}list.replaceChildren();button.disabled=!items.length;wrapper.inert=!items.length;wrapper.style.height=items.length?'auto':'0px';wrapper.style.opacity=items.length?'1':'0';wrapper.style.transform=items.length?'none':'translateY(-10px)';
  for(const item of items){const a=document.createElement('a');a.href=issueURL(item);a.textContent=item.id+' '+item.title;a.className='issue-favorite-link';list.append(a);}list.hidden=button.getAttribute('aria-expanded')==='false';button.onclick=e=>{e.stopPropagation();list.hidden=!list.hidden;button.setAttribute('aria-expanded',String(!list.hidden));};
 }
 return {options,render,renderSidebar,renderDrafts,editor,calendar,reminders,search,copyValue};
}
