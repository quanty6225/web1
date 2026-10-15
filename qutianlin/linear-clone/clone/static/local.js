'use strict';
(() => {
 const $=(q,r=document)=>r.querySelector(q), $$=(q,r=document)=>[...r.querySelectorAll(q)];
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const route=()=>location.pathname.replace(/\/$/,'')||'/';
 const label=e=>(e.getAttribute('aria-label')||e.innerText||e.getAttribute('title')||e.querySelector('svg[aria-label]')?.getAttribute('aria-label')||'').trim();
 let appReady,sessionInfo, state, currentIssue, currentMenu, dialog, filter={}, board=false, ordering='Priority', groupBy='Status', displaySettings={}, sourceHomeHTML=null, sourceHomeScroll=0, publicFeatureDialog=null, publicCodeTheme=null,publicCodeDraft=null;
 let workspaceUI=null;
 const teamPath=path=>path.replace('/team/QQQ/','/team/'+activeTeam()+'/').replace('/teams/QQQ','/teams/'+activeTeam());
 const activeTeam=()=>document.body.dataset.activeTeam||currentIssue?.team||state?.teams?.[0]?.id||'QQQ';
 let detailsController=null,detailsFilter=null,documentTemplates=null,issueTemplates=null,recurringIssues=null,projectLabels=null,projectLabelPage=null,projectDetail=null,viewManager=null,workspaceSearch=null;
 let filterTools,fieldTools,advancedTools,advancedPanel=null,advancedState={enabled:false,expression:{or:[]}};
 let statuses=['Backlog','Todo','In Progress','Done','Canceled','Duplicate'];
 const priorities=['No priority','Urgent','High','Medium','Low'];
 async function api(path,method='GET',body){
  const headers={'X-Linear-Team':activeTeam()};if(state?.workspace?.id||sessionInfo?.workspace?.id)headers['X-Linear-Workspace']=state?.workspace?.id||sessionInfo.workspace.id;if(body&&method==='POST'&&/^\/api\/entities\/(issues|drafts|recurring-issues|workflow-states)$/.test(path)&&body.team===undefined)body={...body,team:activeTeam()};if(method!=='GET'){headers['Content-Type']='application/json';headers['X-Linear-CSRF']=sessionInfo?.csrf||'';}
  const r=await fetch(path,{method,headers,credentials:'same-origin',...(body!==undefined?{body:JSON.stringify(body)}:{})});
  const data=await r.json().catch(()=>({error:'This request could not be completed.'}));
  if(!r.ok){if(r.status===401&&route().startsWith('/qqq153'))location.href='/login?redirectTo='+encodeURIComponent(location.pathname);throw Error(data.error||data.detail||'Please try again.');}
  return data;
 }
 function toast(text){$('.local-toast')?.remove();const e=document.createElement('div');e.className='local-toast';e.role='status';e.textContent=text;document.body.append(e);setTimeout(()=>e.remove(),2800);}
 function closeMenu(restoreFocus=true){const opener=currentMenu?._opener;if(opener){opener.setAttribute('aria-expanded','false');if(currentMenu._publicKind){opener.removeAttribute('data-popup-open');if(currentMenu._previousControls===null)opener.removeAttribute('aria-controls');else opener.setAttribute('aria-controls',currentMenu._previousControls);}}const cleanup=currentMenu?._cleanup;currentMenu?.remove();currentMenu=null;cleanup?.();if(restoreFocus&&opener?.isConnected)opener.focus({preventScroll:true});}
 function closeDialog(){const opener=dialog?._opener;dialog?.remove();dialog=null;if(opener?.isConnected)opener.focus();}
 function menu(anchor,items,title=''){
  closeMenu();const m=document.createElement('div');m.className='local-menu';m.setAttribute('role','menu');m._opener=anchor;if(anchor)anchor.setAttribute('aria-expanded','true');
  m.addEventListener('keydown',e=>{if(!['ArrowDown','ArrowUp','Home','End'].includes(e.key))return;e.preventDefault();const items=$$('[role=menuitem],[role=option]',m).filter(x=>!x.hidden);if(!items.length)return;let i=items.indexOf(document.activeElement);if(e.key==='Home')i=0;else if(e.key==='End')i=items.length-1;else i=(i+(e.key==='ArrowDown'?1:-1)+items.length)%items.length;items[i].focus();});
  if(title){const s=document.createElement('input');s.placeholder=title;s.setAttribute('aria-label',title);m.append(s);s.oninput=()=>$$('[role=menuitem]',m).forEach(b=>b.hidden=!b.textContent.toLowerCase().includes(s.value.toLowerCase()));}
  for(const item of items){if(!item){m.append(document.createElement('hr'));continue;}const i=typeof item==='string'?{text:item}:item;const b=document.createElement(i.href?'a':'button');b.setAttribute('role','menuitem');b.textContent=i.text;if(i.href)b.href=i.href;else b.onclick=async()=>{closeMenu();try{await i.action?.();}catch(e){toast(e.message);}};m.append(b);}
  document.body.append(m);const r=anchor?.getBoundingClientRect()||{left:innerWidth/2,top:innerHeight/3,bottom:innerHeight/3};m.style.left=Math.min(Math.max(8,r.left),innerWidth-m.offsetWidth-10)+'px';m.style.top=Math.min(r.bottom+6,innerHeight-m.offsetHeight-10)+'px';currentMenu=m;setTimeout(()=>$('input,button,a',m)?.focus(),0);return m;
 }
 function modal(title,content,submitText,onSubmit,small=false){
  closeMenu();closeDialog();const o=document.createElement('div');o.className='local-overlay';const tag=submitText?'form':'div';o.innerHTML=`<section role="dialog" aria-modal="true" aria-label="${esc(title)}" class="local-dialog ${small?'small':''}"><header><h2>${esc(title)}</h2><button class="local-close" aria-label="Close">×</button></header><${tag}${submitText?' novalidate':''}><div class="dialog-body">${content}<div class="local-inline-error" role="alert"></div></div>${submitText?`<footer><button type="button" data-cancel>Cancel</button><button class="primary" type="submit">${esc(submitText)}</button></footer>`:''}</${tag}></section>`;
  o._opener=document.activeElement;document.body.append(o);dialog=o;$('.local-close',o).onclick=closeDialog;$('[data-cancel]',o)?.addEventListener('click',closeDialog);o.onclick=e=>{if(e.target===o)closeDialog();};const form=$('form',o);
  if(form)form.onsubmit=async e=>{e.preventDefault();const error=$('.local-inline-error',o);error.textContent='';if(!form.checkValidity()){const invalid=$('input:invalid,textarea:invalid,select:invalid',form);let message=invalid?.validationMessage||'Complete the required fields.';if(invalid?.name==='title'&&title.includes('New issue'))message="Title required. We couldn't generate one automatically. Please enter a title before submitting.";else if(invalid?.name==='title'&&title==='New project')message='Project name required. The project name cannot be empty.';error.textContent=message;invalid?.setAttribute('aria-invalid','true');invalid?.focus();return;}const b=$('button[type=submit]',o);if(b)b.disabled=true;try{await onSubmit?.(new FormData(e.target),o);}catch(err){error.textContent=err.message;}finally{if(b)b.disabled=false;}};
  o.addEventListener('input',e=>{if(e.target.validity?.valid)e.target.removeAttribute('aria-invalid');});const firstInput=$('input:not([type=hidden]),textarea,select,[contenteditable=true]',o)||$('.dialog-body button',o)||$('.local-close',o);firstInput?.focus();return o;
 }

 const issueURL=i=>'/qqq153/issue/'+i.id+'/'+(i.title||'issue').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
 async function refresh(){state=await api('/api/state');statuses=(state.workflow_states||[]).map(s=>s.title);currentIssue=state.issues.find(i=>route().includes('/issue/'+i.id+'/')||route().endsWith('/issue/'+i.id));renderIssues();renderIssue();issueProperties?.renderSidebar();issueProperties?.renderDrafts();documentManager?.render();documentManager?.renderRelated();documentManager?.renderFavorites();documentManager?.renderTeam();documentTemplates?.render();issueTemplates?.render();recurringIssues?.render();await renderRecords();await settingsRecords();await projectLabels?.render();await projectLabelPage?.render();await projectDetail?.render();await viewManager?.render();workspaceSearch?.render();await renderInbox();renderDirectory();renderNavigationFavorites();await workspaceUI?.render();}
 function rowHTML(i){return `<a class="local-issue-row" data-issue-id="${esc(i.id)}" href="${issueURL(i)}"><span class="id">${esc(i.id)}</span><span class="status">${i.status==='Done'?'◉':'◯'}</span><span class="title">${esc(i.title)}</span><time>Oct 13</time></a>`;}
 function filteredIssues(skipDetails=false){
  let items=state.issues.filter(i=>filter.archived?i.archived:!i.archived);const path=route();
  if(/\/team\/[^/]+\/(active|backlog|all)$/.test(path))items=items.filter(i=>(i.team||'QQQ')===activeTeam());
  if(path.endsWith('/active'))items=items.filter(i=>(state.workflow_states||[]).some(s=>s.title===i.status&&['Unstarted','Started'].includes(s.category)));
  if(path.endsWith('/backlog'))items=items.filter(i=>(state.workflow_states||[]).some(s=>s.title===i.status&&s.category==='Backlog'));
  if(path.includes('/my-issues/assigned'))items=items.filter(i=>i.assignee===sessionInfo.account.email_normalized);
  if(path.includes('/my-issues/created'))items=items.filter(i=>i.creator===sessionInfo.account.email_normalized);
  if(path.includes('/my-issues/subscribed'))items=items.filter(i=>i.subscribed);
  if(displaySettings['show-subissues']===false)items=items.filter(i=>!i.parent);
  for(const [k,v] of Object.entries(filter)){
   if(k==='archived')continue;
   items=items.filter(i=>Array.isArray(i[k])?i[k].includes(v):(String(i[k]??'')===String(v)));
  }
  if(filterTools&&advancedState.enabled)items=items.filter(i=>filterTools.matchesExpression(filterTools.issueFilterRecord(i,sessionInfo.account,state.labels,state.label_groups,state.issues),advancedState.expression));
  if(detailsFilter&&!skipDetails){const {key,value}=detailsFilter;items=items.filter(i=>Array.isArray(i[key])?i[key].includes(value):String(i[key]||'')===String(value));}
  const ranks={Urgent:0,High:1,Medium:2,Low:3,'No priority':4};
  if(ordering==='Priority')items.sort((a,b)=>(ranks[a.priority]??4)-(ranks[b.priority]??4));
  else if(ordering==='Created'||ordering==='Updated')items.sort((a,b)=>(b[ordering==='Created'?'created_at':'updated_at']||0)-(a[ordering==='Created'?'created_at':'updated_at']||0));
  else if(ordering==='Due date')items.sort((a,b)=>String(a.due_date||'9999').localeCompare(b.due_date||'9999'));
  return items;
 }
 function renderIssues(){
  if(!state||route().includes('/issue/')||route().includes('/settings/'))return;
  const anchors=$$('a[data-list-row][href*="/issue/"]');let box=$('[data-local-issue-list]');
  if(!anchors.length&&!box){if(!/^\/qqq153\/(?:team\/[^/]+\/(?:active|backlog|all)|my-issues\/[^/]+)$/.test(route()))return;const main=$('main');if(!main)return;box=document.createElement('div');box.dataset.localIssueList='true';main.append(box);}
  if(anchors.length&&!box){box=anchors[0].closest('[data-contextual-menu]')||anchors[0].parentElement.parentElement.parentElement;box.dataset.localIssueList='true';box._sourceRow=anchors[0].cloneNode(true);box._sourceHeader=box.firstElementChild?.cloneNode(true);}
  if(!box)return;const items=filteredIssues();
  let chips=$('.local-filter-chips');if(!chips){chips=document.createElement('div');chips.className='local-filter-chips';box.before(chips);}
  chips.replaceChildren();for(const [key,value] of Object.entries(filter)){const b=document.createElement('button');b.textContent=key+': '+(value||'Unassigned')+' ×';b.setAttribute('aria-label','Remove '+key+' filter');b.onclick=async()=>{delete filter[key];await storeSetting('filters',filter);renderIssues();};chips.append(b);}
  const groups=new Map(),groupKey=groupBy==='No grouping'?null:groupBy.toLowerCase();
  for(const i of items){const key=groupKey?(i[groupKey]||(groupKey==='assignee'?'No assignee':groupKey==='project'?'No project':'No '+groupKey)):'';if(!groups.has(key))groups.set(key,[]);groups.get(key).push(i);}
  if(displaySettings['empty-groups']&&groupBy==='Status')for(const v of statuses)if(!groups.has(v))groups.set(v,[]);
  box.replaceChildren();box.classList.toggle('local-board',board);
  for(const [name,rows] of groups){
   const section=document.createElement('section');section.dataset.issueGroup=name;if(board)section.className='local-board-column';
   if(groupKey){
    let h;if(box._sourceHeader&&!board){h=box._sourceHeader.cloneNode(true);const collapse=$('[aria-label="Collapse group"]',h);if(collapse){const spans=$$('span',collapse).filter(e=>e.childElementCount===0&&e.textContent.trim());if(spans.length)spans.at(-1).textContent=name;collapse.setAttribute('aria-expanded','true');}const count=$('button[type=submit]',h)||$$('button',h).find(b=>/^\d+$/.test(b.textContent.trim()));if(count){count.textContent=rows.length;count.type='button';count.dataset.issueCount='true';count.setAttribute('aria-label','Show issue count');count.setAttribute('aria-pressed',String(!!displaySettings['force-count']));}}
    else{h=document.createElement('header');h.className='local-group-header';h.innerHTML='<button aria-label="Collapse group" aria-expanded="true">'+esc(name)+'</button><span>'+rows.length+'</span>';}
    section.append(h);
   }
   for(const i of rows){let a;if(box._sourceRow&&!board){a=box._sourceRow.cloneNode(true);a.href=issueURL(i);a.dataset.issueId=i.id;a.dataset.listKey=i.id;
    const title=$('[data-list-grid-column=title] [title]',a);if(title){title.textContent=i.title;title.title=i.title;}
    const ident=$('[data-list-grid-column=identifier] span span',a)||$('[data-list-grid-column=identifier]',a);if(ident)ident.textContent=i.id;
    const status=$('[data-list-grid-column=status]',a);if(status){status.setAttribute('aria-label',i.status);const sr=$('span',status);if(sr)sr.textContent=i.status;}
    const priority=$('[data-list-grid-column=priority] svg',a);if(priority)priority.setAttribute('aria-label',i.priority);
    for(const field of ['assignee','project']){const cell=$('[data-list-grid-column='+field+']',a);if(cell&&i[field])cell.textContent=i[field];}
    a.dataset.recordStatus=i.status;
   }else{const template=document.createElement('template');template.innerHTML=rowHTML(i);a=template.content.firstElementChild;}
   $$('[data-list-grid-column]',a).forEach(cell=>{if(displaySettings['display-'+cell.dataset.listGridColumn]===false)cell.hidden=true;});section.append(a);}
   box.append(section);
  }
  if(!items.length){const e=document.createElement('div');e.className='local-empty';e.textContent=Object.keys(filter).length?'No issues match your filters':'No issues';box.append(e);}
  detailsController?.refresh();renderAdvancedSummary(box);
 }
 let issueProperties,issueAttachments,originalIssueDescription,documentManager;
 function renderIssue(){
  if(!currentIssue)return;const breadcrumb=$('main h2');if(breadcrumb?.closest('a[href*="/issue/"]')){breadcrumb.textContent=currentIssue.id+' '+currentIssue.title;breadcrumb.closest('a').href=issueURL(currentIssue);}for(const el of $$('header span'))if(/^QQQ-\d+$/.test(el.textContent.trim())&&!el.children.length)el.textContent=currentIssue.id;const title=$('[aria-label="Issue title"]'),desc=$('[aria-label="Issue description"]');if(title&&document.activeElement!==title)title.textContent=currentIssue.title;if(desc&&originalIssueDescription===undefined)originalIssueDescription=desc.innerHTML;if(desc&&document.activeElement!==desc){if(currentIssue.description_edited||!/^QQQ-[1-4]$/.test(currentIssue.id))desc.textContent=currentIssue.description||'';else if(desc.innerHTML!==originalIssueDescription)desc.innerHTML=originalIssueDescription;}
  if(title&&!title.dataset.bound){title.dataset.bound='true';title.addEventListener('blur',()=>saveIssue({title:title.textContent.trim()}));}
  if(desc&&!desc.dataset.bound){desc.dataset.bound='true';let before;desc.addEventListener('focus',()=>before=desc.innerText);desc.addEventListener('blur',()=>{if(desc.innerText!==before)saveIssue({description:desc.innerText,description_edited:true});});}
  const props=$$('button').filter(b=>statuses.includes(label(b))||b.dataset.issueProperty==='status');if(props[0]){props[0].dataset.issueProperty='status';const text=[...props[0].querySelectorAll('span')].find(s=>statuses.includes(s.textContent));if(text)text.textContent=currentIssue.status;else props[0].textContent=currentIssue.status;}
  const priority=$$('button').find(b=>['Set priority',...priorities].includes(label(b))||b.dataset.issueProperty==='priority');if(priority){priority.dataset.issueProperty='priority';priority.textContent=currentIssue.priority==='No priority'?'Set priority':currentIssue.priority;}
  const assign=$$('button').find(b=>label(b)==='Assign'||b.dataset.issueProperty==='assignee');if(assign){assign.dataset.issueProperty='assignee';assign.textContent=currentIssue.assignee?(currentIssue.assignee===sessionInfo.account.email_normalized?sessionInfo.account.display_name:currentIssue.assignee):'Assign';}
  const placeholder=$('[data-empty-text="Leave a comment…"]');let editor=$('[data-local-comment-editor]');if(!editor&&placeholder){editor=placeholder.parentElement;editor.dataset.localCommentEditor='true';editor.contentEditable='true';editor.setAttribute('role','textbox');editor.setAttribute('aria-label','Leave a comment');editor.setAttribute('aria-multiline','true');}
  let comments=$('.local-comments');const submit=$('[aria-label="Submit comment"]');if(!comments&&editor){comments=document.createElement('div');comments.className='local-comments';editor.parentElement.parentElement.before(comments);}if(comments)comments.innerHTML=(currentIssue.comments||[]).map(c=>`<article class="local-comment" data-comment data-comment-id="${esc(c.id)}"><small>${esc(c.author)}</small><p>${esc(c.body)}</p></article>`).join('');if(submit)submit.disabled=!editor?.innerText.trim();const subscribe=$('button[aria-label="Subscribe to issue"],button[aria-label="Unsubscribe from issue"]');if(subscribe){subscribe.textContent=currentIssue.subscribed?'Unsubscribe':'Subscribe';subscribe.setAttribute('aria-label',currentIssue.subscribed?'Unsubscribe from issue':'Subscribe to issue');}issueProperties?.render();issueAttachments?.render();
 }
 async function saveIssue(patch){if(!currentIssue)return;try{currentIssue=await api('/api/entities/issues/'+currentIssue.id,'PATCH',patch);state.issues=state.issues.map(i=>i.id===currentIssue.id?currentIssue:i);renderIssue();}catch(e){toast(e.message);}}
 function issueDialog(parent=null){return issueProperties?.editor(parent?'child':'issue',parent);}
 function issueURLDefaults(){
  const query=new URLSearchParams(location.search),defaults={};for(const field of ['title','description'])if(query.has(field))defaults[field]=query.get(field);
  const named=(rows,value)=>rows.find(r=>r.id===value||r.title?.toLowerCase()===value?.toLowerCase());
  if(query.has('status')){const value=named(state.workflow_states,query.get('status'));if(value)defaults.status=value.title;}
  if(query.has('priority')){const value=priorities.find(p=>p.toLowerCase()===query.get('priority').toLowerCase());if(value)defaults.priority=value;}
  if(query.has('assignee')){const value=query.get('assignee').toLowerCase();if(['me',sessionInfo.account.email_normalized.toLowerCase(),sessionInfo.account.display_name.toLowerCase()].includes(value))defaults.assignee=sessionInfo.account.email_normalized;}
  for(const field of ['project','template'])if(query.has(field)){const value=named(field==='project'?state.projects:state.issue_templates||[],query.get(field));if(value)defaults[field]=value.id;}
  if(query.has('labels')||query.has('label'))defaults.labels=(query.get('labels')||query.get('label')).split(',').map(value=>named(state.labels,value.trim())?.title).filter(Boolean);
  if(query.has('links'))defaults.links=query.get('links').split(',').map(value=>{const [url,title]=value.split('|');try{const parsed=new URL(url);if(['http:','https:'].includes(parsed.protocol))return{id:crypto.randomUUID(),url:parsed.href,title:title||''};}catch{}return null;}).filter(Boolean);
  return defaults;
 }
 function property(anchor,key,options){menu(anchor,options.map(v=>({text:v||'Unassigned',action:()=>saveIssue({[key]:v})})),key==='status'?'Change status…':'Search…');}
 async function projectDialog(existing=null,defaults={}){const {openProjectEditor}=await import('/static/project-editor.js');return openProjectEditor({api,menu,closeMenu,closeDialog,toast,refresh,sessionInfo,setDialog:o=>dialog=o},existing,defaults);}
 function createRecord(kind,title){if(kind==='teams'){location.href='/qqq153/settings/new-team';return;}if(kind==='views'){sessionStorage.removeItem('linear-view-draft');location.href=teamPath('/qqq153/team/QQQ/view/new');return;}if(kind==='documents')return documentManager.create(currentIssue?{kind:'issues',id:currentIssue.id}:route().includes('/team/')?{kind:'teams',id:activeTeam()}:null);if(kind==='projects')return projectDialog();modal(title,`<label>Name<input name="title" required placeholder="${esc(title.replace('Create ','').replace('New ','')+' name')}"></label><label>Description<textarea name="description" placeholder="Add description…"></textarea></label>`,'Create '+kind.replace(/s$/,''),async f=>{await api('/api/entities/'+kind,'POST',Object.fromEntries(f));closeDialog();await refresh();toast('Created');});}
 async function renderRecords(){
  if(!sessionInfo?.authenticated||route().includes('/settings'))return;let kind=null;if(/\/projects(\/all)?$/.test(route()))kind='projects';if(/\/views(\/issues|\/projects)?$/.test(route()))kind='views';if(/\/documents$/.test(route()))kind='documents';if(!kind||kind==='projects')return;
  let items=await api('/api/entities/'+kind);if(kind==='documents'&&route().includes('/team/'))items=items.filter(item=>item.parent?.kind==='teams'&&item.parent.id===activeTeam()||item.pinned_teams?.includes(activeTeam()));$('.local-record-list')?.remove();let empty=$('[data-record-empty]');if(!empty){const create=$$('main button').find(b=>label(b)===(kind==='projects'?'Create new project':kind==='views'?'Create new view':'Create document'));if(create){empty=create.parentElement?.parentElement?.parentElement;if(empty&&empty!==$('main'))empty.dataset.recordEmpty='true';}}if(empty)empty.hidden=items.length>0;if(!items.length)return;const area=document.createElement('div');area.className='local-record-list';area.innerHTML=items.map(i=>`<article class="local-record-card" role="button" tabindex="0" data-record="${esc(i.id)}" data-kind="${kind}"><h3>${esc(i.title)}</h3><p>${esc(i.description)}</p></article>`).join('');$('main')?.append(area);
 }
 async function recordDetail(kind,id){if(kind==='documents'){location.href=documentManager.route(id);return;}const i=await api('/api/entities/'+kind+'/'+id);if(kind==='projects'){location.href='/qqq153/project/'+encodeURIComponent(i.id)+'/overview';return;}if(kind==='views'){location.href=teamPath('/qqq153/team/QQQ/view/')+encodeURIComponent(i.id);return;}modal(i.title,`<label>Name<input name="title" value="${esc(i.title)}" required></label><label>Description<textarea name="description">${esc(i.description||'')}</textarea></label><button type="button" data-delete-record>Delete ${esc(kind.replace(/s$/,''))}</button>`,'Save',async f=>{await api('/api/entities/'+kind+'/'+id,'PATCH',Object.fromEntries(f));closeDialog();await refresh();});$('[data-delete-record]',dialog).onclick=()=>modal('Delete '+kind.replace(/s$/,''),'<p>Delete '+esc(i.title)+'?</p>','Delete',async()=>{await api('/api/entities/'+kind+'/'+id,'DELETE');closeDialog();await refresh();},true);}
 let inboxSettings;
 const inboxRoute=()=>['/qqq153/inbox','/qqq153/welcome-message'].includes(route());
 async function inboxSetting(key,value){inboxSettings={...(inboxSettings||{}),[key]:value};await api('/api/settings','PUT',{route:'/qqq153/inbox',key,value});await renderInbox();}
 async function renderInbox(){
  if(!state)return;const unread=state.notifications.filter(n=>!n.read).length;const nav=$('a[href="/qqq153/inbox"]');if(nav){const badge=$$('*',nav).find(e=>!e.children.length&&/^\d+$/.test(e.textContent.trim()));if(badge){badge.textContent=unread;badge.hidden=!unread;}}
  applySidebar();if(!inboxRoute())return;if(!inboxSettings)inboxSettings=await api('/api/settings?route='+encodeURIComponent('/qqq153/inbox'));
  const notification=state.notifications.find(n=>n.id==='welcome');if(route().endsWith('/welcome-message')&&notification&&!notification.read){const item=await api('/api/entities/notifications/welcome','PATCH',{read:true});Object.assign(notification,item);return renderInbox();}
  const row=$('a[data-list-row][href="/qqq153/welcome-message"]');if(!row)return;
  $$('[data-document-notification]').forEach(el=>el.remove());
  for(const notification of state.notifications.filter(n=>n.document_id||n.issue_id)){
   if(inboxSettings['unread-only']&&notification.read||notification.snoozed_until>Date.now()/1000&&!inboxSettings['show-snoozed'])continue;
   const item=row.cloneNode(true);item.hidden=false;item.dataset.documentNotification=notification.id;item.href=(notification.issue_id?issueURL(state.issues.find(i=>i.id===notification.issue_id)||{id:notification.issue_id,title:notification.title}):'/qqq153/document/'+encodeURIComponent(notification.document_id))+'?notification='+encodeURIComponent(notification.id);item.textContent=notification.title;item.setAttribute('aria-label',notification.title);item.onclick=async e=>{e.preventDefault();await api('/api/entities/notifications/'+notification.id,'PATCH',{read:true});location.href=item.href;};row.after(item);
  }
  let visible=!!notification;
  if(notification){if(inboxSettings['unread-only']&&notification.read)visible=false;if(notification.snoozed_until>Date.now()/1000&&!inboxSettings['show-snoozed'])visible=false;const filters=inboxSettings.filters||{};for(const [key,value] of Object.entries(filters)){if(key==='Notification type'&&value!=='System notifications')visible=false;else if(key!=='Notification type')visible=false;}for(const el of $$('[aria-label="Unread"]',row))el.hidden=!!notification.read;row.dataset.notificationRead=String(!!notification.read);}
  row.hidden=!visible;$('[data-inbox-group]')?.remove();if(visible&&!notification.read&&inboxSettings.grouping==='Focus'){const heading=document.createElement('div');heading.dataset.inboxGroup='true';heading.className='local-group-header';heading.textContent='Unread';row.before(heading);}const count=state.notifications.filter(n=>!n.read).length;for(const el of $$('main *'))if(!el.children.length&&/^\d+ unread notifications?$/.test(el.textContent.trim()))el.textContent=count+' unread notification'+(count===1?'':'s');
  const toggle=$('button[aria-label="Show unreads only"],button[aria-label="Show all notifications"]');if(toggle){toggle.setAttribute('aria-pressed',String(!!inboxSettings['unread-only']));toggle.setAttribute('aria-label',inboxSettings['unread-only']?'Show all notifications':'Show unreads only');}
  $('[data-inbox-filter-state]')?.remove();if(Object.keys(inboxSettings.filters||{}).length){const box=document.createElement('div');box.dataset.inboxFilterState='true';box.className='local-filter-chips';for(const [key,value] of Object.entries(inboxSettings.filters)){const b=document.createElement('button');b.textContent=key+' is '+value+' ×';b.onclick=async()=>{const filters={...inboxSettings.filters};delete filters[key];await inboxSetting('filters',filters);};box.append(b);}if(!visible){const empty=document.createElement('p');empty.textContent='No matching notifications';box.append(empty);const clear=document.createElement('button');clear.textContent='Clear Filters';clear.onclick=()=>inboxSetting('filters',{});box.append(clear);}row.before(box);}
 }
 function inboxActions(anchor){menu(anchor,[{text:'Mark all as read',action:async()=>{for(const n of state.notifications)await api('/api/entities/notifications/'+n.id,'PATCH',{read:true});await refresh();}},{text:'Delete all',action:()=>modal('Delete all notifications','<p>Delete all notifications?</p>','Delete all',async()=>{for(const n of state.notifications)await api('/api/entities/notifications/'+n.id,'DELETE');closeDialog();location.href='/qqq153/inbox';},true)},{text:'Go to settings',href:'/qqq153/settings/account/notifications'}]);}
 function inboxDisplay(anchor){menu(anchor,[{text:(inboxSettings?.priority?'✓ ':'')+'Enable priority inbox',action:()=>inboxSetting('priority',!inboxSettings?.priority)},{text:'Group unreads by · '+(inboxSettings?.grouping||'No grouping'),action:()=>menu(anchor,['No grouping','Focus'].map(v=>({text:v,action:()=>inboxSetting('grouping',v)})))},{text:'Ordering · '+(inboxSettings?.ordering||'Newest'),action:()=>menu(anchor,['Newest','Oldest'].map(v=>({text:v,action:()=>inboxSetting('ordering',v)})))},{text:(inboxSettings?.['show-snoozed']?'✓ ':'')+'Show snoozed',action:()=>inboxSetting('show-snoozed',!inboxSettings?.['show-snoozed'])},{text:(inboxSettings?.['unread-first']?'✓ ':'')+'Show unread first',action:()=>inboxSetting('unread-first',!inboxSettings?.['unread-first'])}]);}
 function inboxFilter(anchor){const values={'Notification type':['System notifications'],'From':[sessionInfo.account.display_name],'Project':state.projects.map(p=>p.title),'Issue priority':priorities,'Issue status type':['Backlog','Unstarted','Started','Completed','Canceled']};menu(anchor,Object.entries(values).map(([key,items])=>({text:key+' ›',action:()=>menu(anchor,items.map(value=>({text:value,action:()=>inboxSetting('filters',{...(inboxSettings.filters||{}),[key]:value})})),'Search…')})));}
 function snoozeNotification(anchor){const now=new Date();const date=(days,hours=9)=>{const t=new Date(now);t.setDate(t.getDate()+days);t.setHours(hours,0,0,0);return t;};const choices=[['An hour from now',new Date(+now+3600000)],['This evening',date(0,18)],['In 3 hours',new Date(+now+10800000)],['Tomorrow',date(1)],['Next week',date((8-now.getDay())%7||7)],['A month from now',(()=>{const d=date(0);d.setMonth(d.getMonth()+1);return d;})()]];const snooze=async time=>{if(!Number.isFinite(time)||time<=Date.now())throw Error('Choose a future date and time.');await api('/api/entities/notifications/welcome','PATCH',{snoozed_until:Math.floor(time/1000)});location.href='/qqq153/inbox';};menu(anchor,[...choices.map(([text,time])=>({text,action:()=>snooze(+time)})),{text:'Custom…',action:()=>modal('Snooze notification','<label>Date and time<input type="datetime-local" name="time" required></label>','Snooze',async f=>snooze(+new Date(f.get('time'))),true)}]);}

 function configurationKind(){return /\/issue-labels$/.test(route())?'labels':/\/project-statuses$/.test(route())?'project-statuses':/\/teams\/[^/]+\/statuses$/.test(route())?'workflow-states':null;}
 const directoryRoute=()=>['/qqq153/members','/qqq153/teams'].includes(route());
 function renderDirectory(){
  if(!directoryRoute())return;const members=route().endsWith('/members'),rows=$$('main a[data-list-row]'),query=$('main input')?.value.trim().toLowerCase()||'',status=displaySettings['member-status'],order=displaySettings['directory-order']||'Name',descending=!!displaySettings['directory-desc'];
  for(const row of rows){const value=$('[data-list-grid-column=status]',row)?.textContent.trim();const record=members?{status:value==='Application'?'Member':value}:{name:$('[data-list-grid-column=title]',row)?.textContent||row.textContent};row.parentElement.hidden=!row.textContent.toLowerCase().includes(query)||(members&&status&&(status==='Member'?!['Member','Application'].includes(value):value!==status))||(advancedState.enabled&&filterTools&&!filterTools.matchesExpression(record,advancedState.expression));}
  const key=row=>order==='Name'?($('[data-list-grid-column=title]',row)?.textContent||row.textContent):($('[data-list-grid-column="'+order.toLowerCase()+'"]',row)?.textContent||'');
  rows.sort((a,b)=>key(a).localeCompare(key(b))*(descending?-1:1));for(const row of rows)row.parentElement.parentElement.append(row.parentElement);
  if(members)for(const field of ['status','joined','teams'])for(const cell of $$('main [data-list-grid-column="'+field+'"]'))cell.hidden=displaySettings['directory-'+field]===false;
  const container=$('main [data-list-container]'),visible=rows.some(r=>!r.parentElement.hidden);let empty=$('[data-directory-empty]');if(!empty&&container){empty=document.createElement('div');empty.className='local-empty';empty.dataset.directoryEmpty='true';if(members)empty.textContent='No matching members';else{empty.innerHTML='<h3>No teams matching the filters</h3><p>'+rows.length+' team'+(rows.length===1?'':'s')+' hidden by filters</p><button>Clear Filters</button>';$('button',empty).onclick=()=>{const input=$('main input');if(input)input.value='';renderDirectory();};}container.after(empty);}if(container)container.hidden=!visible;if(empty)empty.hidden=visible;
  let chips=$('[data-directory-filters]');if(!chips&&container){chips=document.createElement('div');chips.className='local-filter-chips';chips.dataset.directoryFilters='true';container.before(chips);}if(chips){chips.replaceChildren();if(status&&members){const b=document.createElement('button');b.textContent='Status: '+status+' ×';b.onclick=()=>directorySetting('member-status',null);chips.append(b);}}renderAdvancedSummary(container);
 }
 async function directorySetting(key,value){await storeSetting(key,value);displaySettings[key]=value;renderDirectory();}
 function memberFilter(anchor){menu(anchor,[{text:'Advanced filter',action:()=>openFilterBuilder(anchor)},null,{text:'Status ›',action:()=>menu(anchor,[{text:'Showing all items',action:()=>directorySetting('member-status',null)},...['Admin','Guest','Member'].map(value=>({text:value,action:()=>directorySetting('member-status',value)}))])}]);}
 function memberDisplay(anchor){menu(anchor,[{text:'Ordering · '+(displaySettings['directory-order']||'Name'),action:()=>menu(anchor,['Name','Status','Joined'].map(value=>({text:value,action:()=>directorySetting('directory-order',value)})))},null,...['Status','Joined','Teams'].map(value=>({text:(displaySettings['directory-'+value.toLowerCase()]!==false?'✓ ':'')+value,action:()=>directorySetting('directory-'+value.toLowerCase(),displaySettings['directory-'+value.toLowerCase()]===false)}))]);}
 let configurationDOM,configurationRender=0;
 async function settingsRecords(){
  const kind=configurationKind();if(!kind)return;const generation=++configurationRender;
  if(!configurationDOM){configurationDOM=[];$$('main button[aria-label="Open menu"]').forEach((button,index)=>{const row=kind==='labels'?button.closest('[data-list-row]')?.parentElement.parentElement:button.closest('div[tabindex="-1"]');if(!row)return;const marker=document.createComment('configuration row');row.before(marker);configurationDOM.push({marker,template:row.cloneNode(true),id:kind+'-default-'+index});row.remove();});}
  const labelGroups=new Map();const rows=await api('/api/entities/'+kind);if(kind==='labels'){
   rows.push(...await api('/api/entities/label-groups'));
   const stats=record=>{const used=state.issues.filter(i=>(i.labels||[]).includes(record.title));return {usage:used.length,lastAppliedAt:Math.max(0,...used.map(i=>i.updated_at||0))};};for(const record of rows)Object.assign(record,stats(record));
   const keys={Name:'title',Description:'description',Issues:'usage','Last applied':'lastAppliedAt',Created:'created_at'};const key=keys[displaySettings['label-ordering']||'Name'];rows.sort((a,b)=>{const x=a[key]??'',y=b[key]??'';return (typeof x==='number'?x-y:String(x).localeCompare(String(y)))*(displaySettings['label-descending']?-1:1);});
   for(const button of $$('main button[aria-label^="Order by"]')){const name=button.textContent.trim();button.onclick=async e=>{e.stopPropagation();const descending=displaySettings['label-ordering']===name?!displaySettings['label-descending']:false;await configurationSetting('label-ordering',name,false);await configurationSetting('label-descending',descending);};}
  }
  if(generation!==configurationRender)return;$$('[data-configuration-row],[data-label-group]').forEach(e=>e.remove());
  for(const record of rows){if(record.archived&&!displaySettings['label-show-archived'])continue;if(kind==='labels'){
   if(record.team&&displaySettings['label-show-team']===false)continue;
   const filters=displaySettings['label-filters']||{};if(filters.Team&&record.team!==filters.Team)continue;
   if(filters['Last applied']==='Never applied'&&record.usage)continue;
   if(filters['Last applied']&&filters['Last applied']!=='Never applied'){const days={'1 day ago':1,'3 days ago':3,'1 week ago':7,'1 month ago':30,'3 months ago':90,'6 months ago':180,'1 year ago':365}[filters['Last applied']];const before=days?Date.now()/1000-days*86400:+new Date(filters['Last applied'])/1000;if(!record.lastAppliedAt||record.lastAppliedAt>=before)continue;}
  }const categories=kind==='workflow-states'?['Backlog','Unstarted','Started','Completed','Canceled','Duplicate']:['Backlog','Planned','In Progress','Completed','Canceled'];const original=configurationDOM.find(x=>x.id===record.id)||configurationDOM[categories.indexOf(record.category)]||configurationDOM[0];if(!original)continue;const row=original.template.cloneNode(true);row.dataset.configurationRow=record.id;row.dataset.archived=String(!!record.archived);row.dataset.configurationKind=record.id.startsWith('label-group')?'label-groups':kind;const recordKind=record.id.startsWith('label-group')?'label-groups':kind;
   if(kind==='labels'){
    const name=$('[data-list-grid-column=name] button',row)||$$('button',row).find(b=>['Bug','Feature','Improvement'].includes(label(b)));if(name){name.textContent=record.title;name.style.fontWeight=record.is_group||recordKind==='label-groups'?'600':'';name.onclick=e=>{e.stopPropagation();configurationEdit(recordKind,record,row,'title');};}
    const description=$$('button',row).find(b=>label(b)==='Add label description…');if(description){description.textContent=record.description||'Add label description…';description.onclick=e=>{e.stopPropagation();configurationEdit(recordKind,record,row,'description');};}
    const usage=$('[data-list-grid-column=usage]',row);if(usage)usage.textContent=record.usage||'';const applied=$('[data-list-grid-column=lastAppliedAt]',row);if(applied)applied.textContent=record.lastAppliedAt?new Date(record.lastAppliedAt*1000).toLocaleDateString('en-US',{month:'short',day:'numeric'}):'';const checkbox=$('input[type=checkbox]',row);if(checkbox){checkbox.setAttribute('aria-label','Select '+record.title);checkbox.onchange=()=>configurationSelection();}
   }else{
    const leaf=$$('span,div',row).find(e=>e.children.length===0&&['Backlog','Todo','In Progress','Done','Canceled','Duplicate','Planned','Completed'].includes(e.textContent.trim()));if(leaf)leaf.textContent=record.title;
    const count=$('[aria-label="View issues"]',row);if(count){const n=state.issues.filter(i=>i.status===record.title).length;count.textContent=n+' issues';count.onclick=e=>{e.stopPropagation();location.href=teamPath('/qqq153/team/QQQ/all?status=')+encodeURIComponent(record.title);};}
   }
   const more=$('[aria-label="Open menu"]',row);if(more){more.tabIndex=0;more.onclick=e=>{e.stopPropagation();menu(more,[{text:kind==='labels'?'Edit label name':'Edit',action:()=>configurationEdit(recordKind,record,row,'title')},...(kind==='labels'?[...(!record.is_group&&recordKind==='labels'?[{text:'Move to label group',action:()=>moveIssueLabel(more,record)},{text:'Convert to label group',action:async()=>{await api('/api/entities/labels/'+record.id,'PATCH',{is_group:true,group:null});await refresh();}}]:[]),record.archived?{text:'Unarchive',action:async()=>{await api('/api/entities/'+recordKind+'/'+record.id,'PATCH',{archived:false});await settingsRecords();}}:{text:'Archive…',action:()=>modal('Archive label','<p>Archive '+esc(record.title)+'?</p>','Archive',async()=>{await api('/api/entities/'+recordKind+'/'+record.id,'PATCH',{archived:true});closeDialog();await settingsRecords();},true)}]:[]),{text:'Delete',action:()=>modal('Delete '+(kind==='labels'?'label':'status'),'<p>Delete '+esc(record.title)+'?</p>','Delete',async()=>{await api('/api/entities/'+recordKind+'/'+record.id,'DELETE');closeDialog();await refresh();},true)}]);};}
   if(kind==='labels'){
    if(displaySettings['label-grouping']==='Team'){const group=record.team||'Workspace';row.dataset.labelGroupMember=group;let heading=labelGroups.get(group);if(!heading){heading=document.createElement('div');heading.dataset.labelGroup=group;heading.className='local-group-header';const toggle=document.createElement('button');toggle.textContent=group;toggle.setAttribute('aria-expanded','true');toggle.onclick=()=>{const expanded=toggle.getAttribute('aria-expanded')==='true';$$('[data-label-group-member]').filter(e=>e.dataset.labelGroupMember===group).forEach(e=>e.hidden=expanded);toggle.setAttribute('aria-expanded',String(!expanded));};const count=document.createElement('span');count.textContent='0';heading.append(toggle,count);configurationDOM[0].marker.before(heading);labelGroups.set(group,heading);}const count=$('span',heading);count.textContent=Number(count.textContent)+1;let last=[...$$('[data-label-group-member]')].filter(e=>e.dataset.labelGroupMember===group).at(-1);(last||heading).after(row);
    }else configurationDOM[0].marker.before(row);
   }else original.marker.parentNode.insertBefore(row,original.marker.nextSibling);
  }
  $('[data-label-filter-state]')?.remove();if(kind==='labels'&&Object.keys(displaySettings['label-filters']||{}).length){const bar=document.createElement('div');bar.dataset.labelFilterState='true';bar.className='local-filter-chips';for(const [key,value] of Object.entries(displaySettings['label-filters'])){const b=document.createElement('button');b.textContent=key+': '+value+' ×';b.onclick=()=>{const filters={...displaySettings['label-filters']};delete filters[key];configurationSetting('label-filters',filters);};bar.append(b);}$('main').prepend(bar);}
  const search=$('main input[type=search]');if(search)search.oninput=()=>{for(const row of $$('[data-configuration-row]'))row.hidden=!row.textContent.toLowerCase().includes(search.value.toLowerCase());};
 }
 async function configurationSetting(key,value,render=true){displaySettings[key]=value;await storeSetting(key,value);if(render)await settingsRecords();}
 function labelFilter(anchor){menu(anchor,[{text:'Team ›',action:()=>menu(anchor,[{text:'All',action:()=>configurationSetting('label-filters',{})},{text:'Qqq153',action:()=>configurationSetting('label-filters',{...(displaySettings['label-filters']||{}),Team:'Qqq153'})}])},{text:'Last applied ›',action:()=>menu(anchor,[...['Never applied','1 day ago','3 days ago','1 week ago','1 month ago','3 months ago','6 months ago','1 year ago'].map(value=>({text:value,action:()=>configurationSetting('label-filters',{...(displaySettings['label-filters']||{}),'Last applied':value})})),{text:'Custom date or timeframe…',action:()=>modal('Last applied','<label>Before date<input name="date" type="date" required></label>','Apply',async f=>{await configurationSetting('label-filters',{...(displaySettings['label-filters']||{}),'Last applied':f.get('date')});closeDialog();},true)}])}]);}
 function labelDisplay(anchor){menu(anchor,[{text:'Grouping · '+(displaySettings['label-grouping']||'No grouping'),action:()=>menu(anchor,['No grouping','Team'].map(value=>({text:value,action:()=>configurationSetting('label-grouping',value)})))},{text:'Ordering · '+(displaySettings['label-ordering']||'Name'),action:()=>menu(anchor,['Name','Description','Issues','Last applied','Created'].map(value=>({text:value,action:()=>configurationSetting('label-ordering',value)})))},{text:(displaySettings['label-show-team']!==false?'✓ ':'')+'Show team labels',action:()=>configurationSetting('label-show-team',displaySettings['label-show-team']===false)},{text:(displaySettings['label-show-archived']?'✓ ':'')+'Show archived',action:()=>configurationSetting('label-show-archived',!displaySettings['label-show-archived'])}]);}
 function configurationSelection(){let bar=$('[data-label-selection]');const selected=$$('[data-configuration-row]').filter(row=>$('input[type=checkbox]',row)?.checked);if(!selected.length){bar?.remove();return;}if(!bar){bar=document.createElement('div');bar.dataset.labelSelection='true';bar.className='local-filter-chips';$('main').append(bar);}bar.replaceChildren();const button=document.createElement('button');button.textContent='Delete '+selected.length+' selected';button.onclick=()=>modal('Delete labels','<p>Delete '+selected.length+' selected labels?</p>','Delete',async()=>{for(const row of selected)await api('/api/entities/'+row.dataset.configurationKind+'/'+row.dataset.configurationRow,'DELETE');closeDialog();bar.remove();await settingsRecords();},true);bar.append(button);}
 async function moveIssueLabel(anchor,record){
  const groups=[...await api('/api/entities/label-groups'),...(await api('/api/entities/labels')).filter(x=>x.is_group)].filter(x=>!x.archived&&(!record.team||!x.team||x.team===record.team));
  menu(anchor,[{text:'No group',action:async()=>{await api('/api/entities/labels/'+record.id,'PATCH',{group:null});await refresh();}},...groups.map(g=>({text:(record.group===g.id?'✓ ':'')+g.title,action:async()=>{await api('/api/entities/labels/'+record.id,'PATCH',{group:g.id});await refresh();}}))],'Search label groups…');
 }
 function configurationEdit(kind,record,row,field){
  const labels=kind==='labels'||kind==='label-groups';
  if(labels){const target=field==='description'?$$('button',row).find(b=>b.textContent===record.description||b.textContent==='Add label description…'):$$('button',row).find(b=>b.textContent===record.title);if(!target)return;const input=document.createElement('textarea');input.className='local-inline-editor';input.placeholder=kind==='label-groups'?'Group name':'Label name';input.setAttribute('aria-label',field==='title'?'Name':'Description');input.value=record[field]||'';target.replaceWith(input);let saving=false;const save=async()=>{if(saving)return;if(field==='title'&&!input.value.trim()){await settingsRecords();return;}saving=true;try{await api('/api/entities/'+kind+'/'+record.id,'PATCH',{[field]:input.value.trim()});await refresh();}catch(e){saving=false;toast(e.message);}};input.onblur=save;input.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();save();}if(e.key==='Escape'){saving=true;settingsRecords();}};input.focus();input.select();return;}
  configurationForm(kind,record,row);
 }
 function configurationForm(kind,record,anchor){
  $('[data-configuration-form]')?.remove();const form=document.createElement('form');form.dataset.configurationForm='true';form.className='local-configuration-form';form.innerHTML='<input name="title" aria-label="Name" placeholder="Name" required value="'+esc(record?.title||'')+'"><input name="description" aria-label="Description" placeholder="Description…" value="'+esc(record?.description||'')+'"><button type="button">Cancel</button><button class="primary">'+(record?'Save':'Create')+'</button><span role="alert"></span>';
  const category=record?.category||anchor.dataset.statusCategory||'Backlog';anchor.after(form);$('button[type=button]',form).onclick=()=>form.remove();form.onsubmit=async e=>{e.preventDefault();e.stopPropagation();try{await api('/api/entities/'+kind+(record?'/'+record.id:''),record?'PATCH':'POST',{...Object.fromEntries(new FormData(form)),category});form.remove();await refresh();}catch(err){$('[role=alert]',form).textContent=err.message;}};$('input',form).focus();
 }
 function newConfiguration(kind,anchor){
  if(kind==='workflow-states'||kind==='project-statuses'){const selector=kind==='workflow-states'?'Create new workflow state':'Create new project status';const categories=kind==='workflow-states'?['Backlog','Unstarted','Started','Completed','Canceled','Duplicate']:['Backlog','Planned','In Progress','Completed','Canceled'];anchor.parentElement.dataset.statusCategory=categories[$$('main button[aria-label=\"'+selector+'\"]').indexOf(anchor)]||'Backlog';configurationForm(kind,null,anchor.parentElement);return;}
  const original=configurationDOM?.[0];if(!original)return;const row=original.template.cloneNode(true);row.dataset.configurationRow='new';const name=$$('button',row).find(b=>['Bug','Feature','Improvement'].includes(label(b)));const input=document.createElement('textarea');input.className='local-inline-editor';input.placeholder=kind==='label-groups'?'Group name':'Label name';input.setAttribute('aria-label',input.placeholder);name?.replaceWith(input);$$('[aria-label="Open menu"],input[type=checkbox]',row).forEach(e=>e.remove());original.marker.before(row);let saving=false;const save=async()=>{if(saving)return;if(!input.value.trim()){row.remove();return;}saving=true;try{await api('/api/entities/'+kind,'POST',{title:input.value.trim(),description:''});await settingsRecords();}catch(e){saving=false;toast(e.message);}};input.onblur=save;input.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();save();}if(e.key==='Escape'){saving=true;row.remove();}};input.focus();
 }

 async function addDateFilter(anchor,field){
  const {dateFilterMenu}=await import('/static/filter-dates.js');dateFilterMenu({anchor,field,menu,modal,closeDialog,onPick:async value=>{
   if(!advancedState.enabled)advancedState={enabled:true,expression:{and:[]}};
   const group=advancedState.expression.and||advancedState.expression.or;group.push({[field.key]:value});await advancedTools.loadFilterTemplates();await saveAdvancedFilter();
  }});
 }
 function filterMenu(anchor){
  const fields=getFilterFields(),seen=new Set();
  const entry=field=>({text:(field.basicLabel||field.label)+' ›',action:()=>{
   if(field.type==='single'){menu(anchor,field.options.filter(x=>!x.basicRoot).map(option=>({text:option.menuLabel||option.label,action:async()=>{if(!advancedState.enabled)advancedState={enabled:true,expression:{and:[]}};(advancedState.expression.and||advancedState.expression.or).push(fieldTools.makeCondition(field,field.defaultOperator,option.value));await advancedTools.loadFilterTemplates();await saveAdvancedFilter();}})));return;}
   if(field.type==='date'){addDateFilter(anchor,field);return;}
   if(field.type==='text'){openFilterBuilder(anchor);return;}
   if(['assignee','creator','lastAppliedTemplate','subscribers'].includes(field.key)){menu(anchor,field.options.map(option=>({text:option.label,action:async()=>{if(!advancedState.enabled)advancedState={enabled:true,expression:{and:[]}};(advancedState.expression.and||advancedState.expression.or).push(fieldTools.makeCondition(field,'in',[option.value]));await advancedTools.loadFilterTemplates();await saveAdvancedFilter();}})),'Filter…');return;}
   menu(anchor,[{text:'All',action:async()=>{delete filter[field.key];await storeSetting('filters',filter);renderIssues();renderDirectory();projectDetail?.render().catch(e=>toast(e.message));}},...(field.options||[]).map(option=>({text:option.label,action:async()=>{filter[field.key]=field.key==='priority'?priorities[option.value]:option.value??'';await storeSetting('filters',filter);renderIssues();renderDirectory();projectDetail?.render().catch(e=>toast(e.message));}}))],'Filter…');
  }});
  const entries=[];for(const field of fields){if(field.menuGroup){if(seen.has(field.menuGroup))continue;seen.add(field.menuGroup);entries.push({text:field.menuGroup+' ›',action:()=>menu(anchor,fields.filter(x=>x.menuGroup===field.menuGroup).map(entry))});}else entries.push(entry(field));for(const option of field.options||[])if(option.basicRoot)entries.push({text:option.menuLabel,action:async()=>{if(!advancedState.enabled)advancedState={enabled:true,expression:{and:[]}};(advancedState.expression.and||advancedState.expression.or).push(fieldTools.makeCondition(field,field.defaultOperator,option.value));await advancedTools.loadFilterTemplates();await saveAdvancedFilter();}});}
  menu(anchor,[{text:'Advanced filter',action:()=>openFilterBuilder(anchor)},null,...entries],'Add Filter…');
 }
 function saveFilterAsView(){if(document.body.dataset.viewId){return viewManager.saveFilters();}sessionStorage.setItem('linear-view-draft',JSON.stringify({filters:filterURLExpression(),returnTo:location.pathname+location.search}));location.href=teamPath('/qqq153/team/QQQ/view/new');}
 function initializeViewDraft(){
  if(!route().endsWith('/view/new'))return;let draft={};try{draft=JSON.parse(sessionStorage.getItem('linear-view-draft')||'{}');}catch{}
  if(draft.filters){filterTools.validateExpression(draft.filters);filter={};advancedState={enabled:filterTools.hasConditions(draft.filters),expression:draft.filters};}
  const name=$('main input[placeholder="All issues"]'),description=$('main input[placeholder="Description (optional)"]');if(name)name.setAttribute('aria-label','View name');if(description)description.setAttribute('aria-label','View description');if(name&&draft.title)name.value=draft.title;if(description&&draft.description)description.value=draft.description;
  const create=$$('main button').find(button=>label(button)==='Create view'),cancel=$$('main button').find(button=>label(button)==='Cancel');
  if(create)create.onclick=async event=>{event.stopPropagation();create.disabled=true;try{const view=await api('/api/entities/views'+(draft.id?'/'+draft.id:''),draft.id?'PATCH':'POST',{title:name.value.trim()||name.placeholder,description:description?.value||'',filters:filterURLExpression(),team:activeTeam(),...(draft.id?{revision:draft.revision}:{})});sessionStorage.removeItem('linear-view-draft');location.href=teamPath('/qqq153/team/QQQ/view/')+encodeURIComponent(view.id);}catch(error){create.disabled=false;toast(error.message);}};
  if(create&&draft.id)create.textContent='Save changes';
  if(cancel)cancel.onclick=event=>{event.stopPropagation();sessionStorage.removeItem('linear-view-draft');location.href=draft.returnTo?.startsWith('/qqq153/')?draft.returnTo:teamPath('/qqq153/team/QQQ/active');};
 }
 async function initializeSavedView(){
  const match=route().match(/^\/qqq153\/team\/[^/]+\/view\/(views?_[a-zA-Z0-9]+)(?:\/edit)?$/);if(!match)return;const view=await api('/api/entities/views/'+match[1]);filter={};advancedState={enabled:filterTools.hasConditions(view.filters),expression:view.filters||{or:[]}};document.title=view.title+' – Linear';if(route().endsWith('/edit')){viewManager.editForm(view);return;}
  const name=$('main input[placeholder="All issues"]'),description=$('main input[placeholder="Description (optional)"]');if(name){const title=document.createElement('h2');title.textContent=view.title;name.replaceWith(title);}if(description){const text=document.createElement('p');text.textContent=view.description||'';description.replaceWith(text);}
  for(const button of $$('main button'))if(['Create view','Cancel'].includes(label(button)))button.remove();for(const node of $$('main span'))if(!node.children.length&&node.textContent==='New view')node.textContent=view.title;
 }
 function getFilterFields(){return fieldTools?.fieldsForFilters(state,sessionInfo?.account,route())||[];}
 function filterURLExpression(){const nodes=[];for(const field of getFilterFields()){if(!(field.key in filter))continue;let value=filter[field.key];if(field.key==='priority')value=priorities.indexOf(value);if(['assignee','creator','project'].includes(field.key)&&value==='')value=null;nodes.push(fieldTools.makeCondition(field,'in',[value]));}if(advancedState.enabled&&filterTools.hasConditions(advancedState.expression))nodes.push(advancedState.expression);return {and:nodes};}
 function syncFilterURL(){if(!filterTools||!fieldTools||(!route().match(/^\/qqq153\/(?:team\/[^/]+\/(?:active|backlog|all)|my-issues\/[^/]+|project\/[^/]+\/issues|members|teams)$/)))return;const url=new URL(location.href),expression=filterURLExpression();if(filterTools.hasConditions(expression))url.searchParams.set('filter',filterTools.encodeExpression(expression));else url.searchParams.delete('filter');if(url.href!==location.href)history.pushState(null,'',url);}
 function loadFilterURL(){const value=new URLSearchParams(location.search).get('filter');if(!value)return false;const expression=filterTools.decodeExpression(value),nodes=expression.and||[expression],advanced=[];filter={};for(const node of nodes){let found=false;for(const field of getFilterFields()){const value=fieldTools.readCondition(field,node);if(value?.in?.length===1&&value.in[0]!=='current-user'&&field.key!=='lastAppliedTemplate'&&field.key!=='subscribers'&&field.key!=='member-status'&&route()!=='/qqq153/teams'){let selected=value.in[0];if(field.key==='priority')selected=priorities[selected];filter[field.key]=selected??'';found=true;break;}}if(!found)advanced.push(node);}advancedState={enabled:advanced.length>0,expression:advanced.length===1&&(advanced[0].and||advanced[0].or)?advanced[0]:{and:advanced}};return true;}
 async function saveAdvancedFilter(){await storeSetting('advanced-filter',advancedState);syncFilterURL();renderIssues();renderDirectory();projectDetail?.render().catch(e=>toast(e.message));}
 async function clearAdvancedFilter(){advancedState={enabled:false,expression:{or:[]}};advancedPanel?.close();await saveAdvancedFilter();}
 function renderAdvancedSummary(container){advancedTools?.renderFilterSummary({expression:advancedState.expression,enabled:advancedState.enabled,container,onOpen:openFilterBuilder,onClear:clearAdvancedFilter,getFields:getFilterFields,onSave:saveFilterAsView});}
 async function openFilterBuilder(anchor){
  closeMenu();if(advancedPanel)advancedPanel.close();advancedState.enabled=true;await advancedTools.loadFilterTemplates();await saveAdvancedFilter();
  advancedPanel=await advancedTools.openAdvancedFilters({anchor,getExpression:()=>advancedState.expression,getFields:getFilterFields,onChange:saveAdvancedFilter,menu,closeMenu,modal,closeDialog,onClose:()=>advancedPanel=null});
 }

 async function displaySetting(key,value){displaySettings[key]=value;await storeSetting(key,value);renderIssues();}
 function displayMenu(anchor){menu(anchor,[{text:'List',action:async()=>{board=false;await displaySetting('layout','List');}},{text:'Board',action:async()=>{board=true;await displaySetting('layout','Board');}},null,{text:'Grouping · '+groupBy,action:()=>menu(anchor,['Status','Priority','Assignee','Project','No grouping'].map(v=>({text:v,action:async()=>{groupBy=v;await displaySetting('grouping',v);}})))},{text:'Ordering · '+ordering,action:()=>menu(anchor,['Priority','Created','Updated','Due date'].map(v=>({text:v,action:async()=>{ordering=v;await displaySetting('ordering',v);}})))},{text:(displaySettings['show-subissues']!==false?'✓ ':'')+'Show sub-issues',action:()=>displaySetting('show-subissues',displaySettings['show-subissues']===false)},{text:(displaySettings['empty-groups']?'✓ ':'')+'Show empty groups',action:()=>displaySetting('empty-groups',!displaySettings['empty-groups'])},{text:'Display properties',action:()=>menu(anchor,['ID','Status','Assignee','Creator','Priority','Project','Due date','Milestone','Labels','Links','Time in status','Created','Updated'].map(v=>{const key=v==='ID'?'identifier':v.toLowerCase();return {text:(displaySettings['display-'+key]!==false?'✓ ':'')+v,action:()=>displaySetting('display-'+key,displaySettings['display-'+key]===false)};}))}]);}
 async function storeSetting(key,value){const result=await api('/api/settings','PUT',{route:route(),key,value});if(key==='filters')syncFilterURL();return result;}
 async function securitySettings(){
  if(route()!=='/qqq153/settings/account/security')return;
  await passkeyList();
  const keys=await api('/api/keys');let root=$('[data-local-api-keys]');
  if(!root){const empty=$$('main p,main span,main div').find(e=>e.childElementCount===0&&e.textContent.trim()==='No API keys created');if(!empty)return;root=document.createElement('div');root.dataset.localApiKeys='true';empty.replaceWith(root);}
  root.replaceChildren();if(!keys.length){root.textContent='No API keys created';return;}
  for(const key of keys){const row=document.createElement('div');row.className='local-key-row';const name=document.createElement('span');name.textContent=key.name+' · '+key.prefix+'…';const revoke=document.createElement('button');revoke.textContent='Revoke';revoke.onclick=()=>modal('Revoke API key','<p>Revoke '+esc(key.name)+'?</p>','Revoke',async()=>{await api('/api/keys/'+key.id,'DELETE');closeDialog();await securitySettings();},true);row.append(name,revoke);root.append(row);}
 }
 const fromBase64URL=value=>Uint8Array.from(atob(value.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0));
 const toBase64URL=value=>btoa(String.fromCharCode(...new Uint8Array(value))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
 async function passkey(register=false){
  // WebAuthn RP IDs are domains; browsers reject the numeric loopback address.
  if(location.hostname!=='localhost'){if(register){const bridge=await api('/api/auth/local-origin','POST',{});location.href=bridge.url;}else location.href='http://localhost:'+location.port+'/login?passkey=1';return;}
  if(!window.PublicKeyCredential)throw Error('Passkeys are not supported in this browser.');
  const prefix='/api/passkeys/'+(register?'register':'login');const options=await api(prefix+'/options','POST',{});options.challenge=fromBase64URL(options.challenge);
  if(options.user)options.user.id=fromBase64URL(options.user.id);
  for(const name of ['excludeCredentials','allowCredentials'])if(options[name])options[name]=options[name].map(x=>({...x,id:fromBase64URL(x.id)}));
  let credential;try{credential=register?await navigator.credentials.create({publicKey:options}):await navigator.credentials.get({publicKey:options});}catch(e){throw Error(e.name==='NotAllowedError'?'No passkey was selected. Please try again or continue with email.':e.message);}
  const response={clientDataJSON:toBase64URL(credential.response.clientDataJSON)};
  for(const field of ['attestationObject','authenticatorData','signature','userHandle'])if(credential.response[field])response[field]=toBase64URL(credential.response[field]);
  if(register)response.transports=credential.response.getTransports?.()||[];
  const result=await api(prefix+'/verify','POST',{id:credential.id,rawId:toBase64URL(credential.rawId),type:credential.type,response,clientExtensionResults:credential.getClientExtensionResults()});
  if(register){await passkeyList();toast('Passkey registered');}else location.replace(result.redirect);
 }
 async function passkeyList(){
  const keys=await api('/api/passkeys');let root=$('[data-local-passkeys]');if(!root){const empty=$$('main p,main span,main div').find(e=>e.childElementCount===0&&e.textContent.trim()==='No passkeys registered');if(!empty)return;root=document.createElement('div');root.dataset.localPasskeys='true';empty.replaceWith(root);}
  root.replaceChildren();if(!keys.length){root.textContent='No passkeys registered';return;}
  for(const key of keys){const row=document.createElement('div');row.className='local-key-row';const name=document.createElement('span');name.textContent=key.name;const remove=document.createElement('button');remove.textContent='Remove';remove.onclick=e=>{e.stopPropagation();modal('Remove passkey','<p>Remove this passkey from your account?</p>','Remove',async()=>{await api('/api/passkeys/'+encodeURIComponent(key.id),'DELETE');closeDialog();await passkeyList();},true);};row.append(name,remove);root.append(row);}
 }
 function keyPermissions(){
  if(!route().endsWith('/api-keys/new'))return;
  const name=$('input[name=label]');if(name){name.required=true;name.addEventListener('input',()=>{const submit=$('main button[type=submit]');if(submit)submit.disabled=!name.value.trim();});}
  const selected=$('input[name=selectedScope]:checked')?.value==='selectScope';let box=$('[data-key-permissions]');
  if(!box){box=document.createElement('div');box.dataset.keyPermissions='true';const field=$('input[name=selectedScope][value=selectScope]');field.closest('label').parentElement.append(box);box.innerHTML=['Read','Create','Write'].map(x=>'<label><input type="checkbox" name="permissions" value="'+x.toLowerCase()+'"> '+x+'</label>').join('');}
  box.hidden=!selected;
 }
 async function webhookSettings(){
  if(route().endsWith('/api/webhooks/new')){const form=$('main form');if(!form)return;const name=$('[name=label]',form),url=$('[name=url]',form),secret=$('[name=secret]',form);name.required=true;url.required=true;url.type='url';secret.value=crypto.randomUUID()+crypto.randomUUID();form.addEventListener('input',()=>{const submit=$('button[type=submit]',form);if(submit)submit.disabled=!(name.value.trim()&&url.validity.valid&&url.value);});return;}
  if(route()!=='/qqq153/settings/api')return;const hooks=await api('/api/entities/webhooks');let root=$('[data-local-webhooks]');if(!root){const empty=$$('main p,main div,main span').find(e=>e.childElementCount===0&&e.textContent.trim()==='No webhooks');if(!empty)return;root=document.createElement('div');root.dataset.localWebhooks='true';empty.replaceWith(root);}root.replaceChildren();if(!hooks.length){root.textContent='No webhooks';return;}
  for(const hook of hooks){const row=document.createElement('div');row.className='local-key-row';const open=document.createElement('button');open.textContent=hook.title;open.onclick=async e=>{e.stopPropagation();const events=await api('/api/webhooks/'+hook.id+'/deliveries');modal(hook.title,'<p>'+esc(hook.url)+'</p><p>Local delivery collection · '+events.length+' events</p>'+events.map(event=>'<article><strong>'+esc(event.event_type)+'</strong><pre>'+esc(event.body)+'</pre></article>').join(''),null,null);};const remove=document.createElement('button');remove.textContent='Delete';remove.onclick=e=>{e.stopPropagation();modal('Delete webhook','<p>Delete '+esc(hook.title)+'?</p>','Delete',async()=>{await api('/api/entities/webhooks/'+hook.id,'DELETE');closeDialog();await webhookSettings();},true);};row.append(open,remove);root.append(row);}
 }
 function sourceLink(path){location.href=path;}
 function help(anchor){menu(anchor,[{text:'Docs',href:'/docs'},{text:'Contact us',action:()=>contact()},{text:'Keyboard shortcuts',action:()=>modal('Keyboard shortcuts','<p><kbd>C</kbd> Create new issue</p><p><kbd>/</kbd> Search workspace</p><p><kbd>G then S</kbd> Settings</p><p><kbd>Alt Shift Q</kbd> Log out</p><p><kbd>Esc</kbd> Close dialog</p>',null,null,true)},{text:'Linear status',href:'/external?target='+btoa('https://linearstatus.com/')},{text:'Download apps',href:'/download'},{text:'Settings',href:'/qqq153/settings/account/preferences'},{text:'Slack community',href:'/join-slack'},null,{text:'What’s new',href:'/changelog'},{text:'Full changelog',href:'/changelog'}]);}
 function contact(){modal('Contact us','<label>Email<input type="email" name="email" required></label><label>Message<textarea name="message" required></textarea></label>','Send',async f=>{await api('/api/forms','POST',{kind:'support',...Object.fromEntries(f)});closeDialog();toast('Message sent');});}
 async function detailsPanel(force=null){
  const open=force===null?!detailsController:force;const button=$$('main button').find(b=>['Open details','Close details'].includes(label(b)));
  if(!open){const previous=detailsController;detailsController=null;previous?.remove();displaySettings['details-open']=false;if(button){button.setAttribute('aria-label','Open details');button.setAttribute('aria-expanded','false');}await storeSetting('details-open',false);return;}
  if(detailsController)return;const {createIssueDetails}=await import('/static/issue-details.js');detailsController=await createIssueDetails({getItems:()=>filteredIssues(true),getProjects:()=>state.projects,getAccount:()=>sessionInfo.account,getTab:()=>displaySettings['details-tab']||'Assignees',onTab:async value=>{displaySettings['details-tab']=value;await storeSetting('details-tab',value);},onFilter:value=>{detailsFilter=value;renderIssues();}});displaySettings['details-open']=true;if(button){button.setAttribute('aria-label','Close details');button.setAttribute('aria-expanded','true');}await storeSetting('details-open',true);
 }
 function invite(){return workspaceUI.invite();}
 function workspaceMenu(anchor){return workspaceUI.workspaceMenu(anchor);}

 function issueOptions(anchor){issueProperties?.options(anchor);}
 async function copy(text){try{await navigator.clipboard.writeText(text);toast('Copied to clipboard');}catch{const t=document.createElement('textarea');t.value=text;document.body.append(t);t.select();document.execCommand('copy');t.remove();toast('Copied to clipboard');}}
 let loginMode='start',loginEmail='',loginProvider='email',signup=route()==='/signup';
 const loginRedirect=()=>new URLSearchParams(location.search).get('redirectTo')||teamPath('/qqq153/team/QQQ/active');
 function renderAuth(error=''){
  document.body.classList.add('local-auth');let root=$('#root');if(!root){document.body.innerHTML='<div id="root"></div>';root=$('#root');}
  const logo="<div class=\"linear-logo\"><svg width=\"48\" height=\"48\" viewBox=\"0 0 48 48\" fill=\"currentColor\" aria-hidden=\"true\" class=\"sx-1useyqa sx-sdox4t sx-2lah0s sx-1iymm2a sx-17dzmu4\"><svg width=\"42\" height=\"42\" viewBox=\"0 0 100 100\" fill=\"inherit\" aria-hidden=\"true\" x=\"3\" y=\"3\"><path d=\"M12.927 16.371a1.47 1.47 0 0 0 .061 2.027l68.595 68.594c.555.555 1.446.59 2.026.062 10.058-9.152 16.372-22.348 16.372-37.018C99.98 22.402 77.579 0 49.945 0c-14.67 0-27.866 6.313-37.018 16.371M4.353 29.39a1.47 1.47 0 0 0 .309 1.648L68.943 95.32c.434.434 1.09.562 1.648.308a50 50 0 0 0 4.335-2.227c.834-.482.962-1.62.28-2.3L8.882 24.773c-.68-.68-1.818-.553-2.3.281a50 50 0 0 0-2.228 4.334m-3.9 18.407a1.48 1.48 0 0 1-.432-1.14q.2-2.986.74-5.866c.215-1.15 1.62-1.55 2.448-.722l56.703 56.704c.828.827.429 2.233-.722 2.448a50 50 0 0 1-5.865.74 1.48 1.48 0 0 1-1.14-.433zm3.48 13.963c-1.033-1.033-2.7-.143-2.322 1.268C6.221 80.22 19.761 93.76 36.954 98.37c1.41.379 2.3-1.289 1.268-2.322z\"></path></svg></svg></div>";
  let content='';
  if(loginMode==='start')content=`<h1>${signup?'Create your workspace':'Log in to Linear'}</h1><button class="primary" data-auth="google">Continue with Google</button><button data-auth="email">Continue with email</button><button data-auth="saml">Continue with SAML SSO</button>${signup?'':'<button data-auth="passkey">Log in with passkey</button>'}${signup?'<p class="legal">By signing up, you agree to our <a href="/terms">Terms of Service</a>, <a href="/privacy">Privacy Policy</a>, and <a href="/dpa">Data Processing Agreement</a>.</p><p>Already have an account? <a href="/login">Log in</a></p>':'<p>Don’t have an account? <a href="/signup">Sign up</a> or <a href="/homepage">learn more</a></p>'}`;
  else if(loginMode==='email')content=`<h1>What’s your email address?</h1>${loginProvider==='google'?'<p>Google · Local sign-in</p>':''}<form id="email-form"><input name="email" aria-label="Email address" type="email" placeholder="Enter your email address…" value="${esc(loginEmail)}" autofocus><button class="primary" type="submit">${loginProvider==='saml'?'Continue with SAML':'Continue with email'}</button></form><button class="link-button" data-auth="back">Back to ${signup?'signup':'login'}</button>`;
  else if(loginMode==='sent'||loginMode==='code')content=`<h1>Check your email</h1><p>We’ve sent you a temporary login ${loginMode==='code'?'code':'link'}.<br>Please check your inbox at <span class="auth-email">${esc(loginEmail)}</span>.</p>${loginMode==='code'?'<form id="code-form"><input name="code" aria-label="Login code" placeholder="Enter code" maxlength="10" autocomplete="one-time-code" required autofocus><button class="primary" type="submit">Continue with login code</button></form>':'<button data-auth="code">Enter code manually</button>'}<button class="link-button" data-auth="back">Back to ${signup?'signup':'login'}</button>`;
  else if(loginMode==='passkey')content='<h1>Log in with passkey</h1><p>No passkey is available for this local workspace.</p><button data-auth="email">Continue with email</button><button class="link-button" data-auth="back">Back to login</button>';
  root.innerHTML=`<main class="auth-box">${logo}${content}<div role="alert" class="auth-error">${esc(error)}</div></main>`;
  if(!sessionInfo)$$('button,input',root).forEach(control=>control.disabled=true);
  $('#email-form')?.addEventListener('submit',async e=>{e.preventDefault();loginEmail=new FormData(e.target).get('email').trim();if(!loginEmail){renderAuth(loginProvider==='saml'?'Please enter an email address for SAML SSO login.':'Please enter an email address for login.');return;}const b=$('button',e.target);b.disabled=true;try{await api('/api/auth/challenge','POST',{email:loginEmail,redirectTo:loginRedirect(),provider:loginProvider,signup});loginMode='sent';renderAuth();}catch(err){renderAuth(err.message);}});
  $('#code-form')?.addEventListener('submit',async e=>{e.preventDefault();const code=new FormData(e.target).get('code').trim();if(code.length!==10){renderAuth('Please enter a valid verification code.');return;}const b=$('button',e.target);b.disabled=true;try{const d=await api('/api/auth/verify','POST',{code,redirectTo:loginRedirect()});location.replace(d.redirect);}catch(err){renderAuth(err.message);}});
  $('[autofocus]')?.focus();
 }
 async function publicState(button){
  const index=button.dataset.sourceButtonIndex;if(index===undefined)return false;
  let manifest=window.__sourceStateManifest;if(!manifest){try{manifest=await (await fetch('/static/states/manifest.json')).json();window.__sourceStateManifest=manifest;}catch{return false;}}
  if(!manifest[index]&&index!=='19')return false;
  if(button.dataset.sourceButtonIndex==='19'){const next=button.getAttribute('aria-label')!=='Remove from favorites';button.setAttribute('aria-label',next?'Remove from favorites':'Add to favorites');button.setAttribute('aria-pressed',String(next));const icon=$('svg',button);if(icon){icon.style.setProperty('--x---icon-default-color',next?'var(--color-yellow)':'var(--color-text-tertiary)');icon.setAttribute('fill',next?'var(--color-yellow)':'var(--color-text-tertiary)');}return true;}
  const currentScroll=scrollY;const r=await fetch('/static/states/'+manifest[index]);if(!r.ok)return false;const text=await r.text();const doc=new DOMParser().parseFromString(text,'text/html');$$('script',doc).forEach(e=>e.remove());
  if($('[role=dialog].UBZV-G_dialog',doc)){openPublicFeatureDialog(doc,button);return true;}
  if(!sourceHomeHTML){sourceHomeHTML=document.body.innerHTML;sourceHomeScroll=currentScroll;}
  document.body.innerHTML=doc.body.innerHTML;for(const style of $$('head style',doc))document.body.append(style.cloneNode(true));document.body.dataset.publicState=index;preparePublic();scrollTo(0,currentScroll);return true;
 }
 function openPublicFeatureDialog(doc,opener){
  if(publicFeatureDialog)closePublicFeatureDialog();
  const content=$('[role=dialog].UBZV-G_dialog',doc),portal=content.closest('[data-base-ui-portal]').cloneNode(true);
  const background=[...document.body.children].map(element=>({element,inert:element.inert,hidden:element.getAttribute('aria-hidden')}));
  publicFeatureDialog={portal,opener,background,overflow:document.body.style.overflow,scroll:scrollY};
  for(const entry of background){entry.element.inert=true;entry.element.setAttribute('aria-hidden','true');}
  for(const style of $$('head style',doc))portal.append(style.cloneNode(true));
  portal.addEventListener('focusin',e=>{if(e.target.hasAttribute('data-base-ui-focus-guard'))$('.UBZV-G_close',portal)?.focus({preventScroll:true});});
  document.body.append(portal);document.body.style.overflow='hidden';
  $('.UBZV-G_close',portal)?.focus({preventScroll:true});
 }
 function closePublicFeatureDialog(){
  if(!publicFeatureDialog)return;
  const saved=publicFeatureDialog;publicFeatureDialog=null;saved.portal.remove();
  for(const entry of saved.background){entry.element.inert=entry.inert;if(entry.hidden===null)entry.element.removeAttribute('aria-hidden');else entry.element.setAttribute('aria-hidden',entry.hidden);}
  document.body.style.overflow=saved.overflow;scrollTo(0,saved.scroll);saved.opener.focus({preventScroll:true});
 }
 const publicCodeThemes=['Linear','GitHub Dark','Dracula','Nord','Tokyo Night','Rosé Pine','Catppuccin','One Dark'];
 function publicCodeRoot(){
  const marked=$('[data-public-code-demo]');if(marked)return marked;
  const editor=$('[aria-label="Editable code diff — press Space to edit"]'),combo=$$('button[role=combobox]').find(b=>publicCodeThemes.includes(b.textContent.trim()));if(!editor||!combo)return null;
  let root=editor.parentElement;while(root&&!root.contains(combo))root=root.parentElement;if(root&&root!==document.body){root.dataset.publicCodeDemo='true';return root;}return null;
 }
 async function applyPublicCodeTheme(theme){
  const root=publicCodeRoot();if(!root)return;const manifest=await (await fetch('/static/public-code-themes/manifest.json')).json(),entry=manifest[theme];if(!entry)return;
  const [markup,css]=await Promise.all([fetch('/static/public-code-themes/'+entry.file).then(r=>r.text()),fetch('/static/public-code-themes/'+entry.stylesheet).then(r=>r.text())]);
  const t=document.createElement('template');t.innerHTML=markup;const replacement=t.content.firstElementChild;if(!replacement)return;
  let style=$('style[data-public-code-theme-style]');if(!style){style=document.createElement('style');style.dataset.publicCodeThemeStyle='true';document.head.append(style);}style.textContent=css;root.replaceWith(replacement);publicCodeTheme=theme;preparePublic();
 }
 function publicCodeThemeMenu(anchor){
  const m=menu(anchor,publicCodeThemes.map(theme=>({text:theme,action:()=>applyPublicCodeTheme(theme)})));m.setAttribute('role','listbox');m.setAttribute('aria-label','Code theme');for(const option of $$('[role=menuitem]',m)){option.setAttribute('role','option');option.setAttribute('aria-selected',String(option.textContent===(publicCodeTheme||anchor.textContent.trim())));}
 }
 function preparePublic(){
  if(!['/','/homepage'].includes(route()))return;
  for(const favorite of $$('button[aria-label="Remove from favorites"],button[aria-label="Add to favorites"]'))favorite.setAttribute('aria-pressed',String(favorite.getAttribute('aria-label')==='Remove from favorites'));
  const code=publicCodeRoot();if(code&&publicCodeTheme&&code.dataset.publicCodeTheme!==publicCodeTheme)applyPublicCodeTheme(publicCodeTheme).catch(e=>toast(e.message));
  if(publicCodeDraft!==null){const input=$('textarea[aria-label="Edit code lines"]');if(input){input.value=publicCodeDraft;const display=input.parentElement.querySelector('[class*="editableDisplay"]');if(display)display.innerHTML=publicCodeDraft.split('\n').map(line=>'<span class="line">'+esc(line)+'\n</span>').join('');}}
  // The source demo uses a selected navigation item even when reselected.
  $$('button[data-active]').forEach(b=>{b.setAttribute('role','tab');b.setAttribute('aria-selected',b.dataset.active);});
  $$('button[data-source-button-index]').forEach(b=>{if(getComputedStyle(b).pointerEvents==='none'){b.setAttribute('aria-disabled','true');b.dataset.sourcePointerDisabled='true';}else if(b.dataset.sourcePointerDisabled){b.removeAttribute('aria-disabled');delete b.dataset.sourcePointerDisabled;}});
  // Source autofill proxy is hidden, never an editable text control.
  $$('input[aria-hidden=true]').forEach(e=>{if(e.id.endsWith('-hidden-input'))e.type='hidden';});
 }
 function restoreHome(){if(!sourceHomeHTML)return;document.body.innerHTML=sourceHomeHTML;delete document.body.dataset.publicState;scrollTo(0,sourceHomeScroll);sourceHomeHTML=null;}
 function publicPopupItems(panel){return $$('a[href],button:not([disabled]),[role=menuitem]',panel).filter(e=>e.checkVisibility()&&!e.closest('[inert]'));}
 function publicFocusAfter(opener,reverse=false){
  const controls=$$('a[href],button:not([disabled]),input:not([type=hidden]),select,textarea,[tabindex]').filter(e=>e.tabIndex>=0&&e.checkVisibility()&&!e.closest('[inert]')&&!e.hasAttribute('data-base-ui-focus-guard')&&!currentMenu?.contains(e));
  return controls[controls.indexOf(opener)+(reverse?-1:1)];
 }
 function bindPublicPopup(panel,button,kind){
  panel._opener=button;panel._publicKind=kind;panel._previousControls=button.getAttribute('aria-controls');
  const popup=$('nav[data-open],[role=menu],[role=dialog]',panel)||panel;
  if(popup.id)button.setAttribute('aria-controls',popup.id);
  button.setAttribute('aria-expanded','true');button.setAttribute('data-popup-open','');currentMenu=panel;
  panel.addEventListener('focusin',e=>{
   if(!e.target.hasAttribute('data-base-ui-focus-guard'))return;
   const guards=$$('[data-base-ui-focus-guard]',panel);
   if(kind==='nav')(e.target===guards[0]?button:publicFocusAfter(button))?.focus({preventScroll:true});
   if(kind==='mobile'){const items=publicPopupItems(panel);(e.target===guards[0]?items.at(-1):items[0])?.focus({preventScroll:true});}
  });
 }
 function openPublicMobile(doc,button){
  const source=$('[role=dialog].TZTsQG_mobileMenuContent',doc);if(!source)return;
  closeMenu(false);const panel=source.closest('[data-base-ui-portal]').cloneNode(true);panel.classList.add('local-source-nav');Object.assign(panel.style,{position:'relative',zIndex:'1000'});
  const background=[...document.body.children].map(element=>({element,inert:element.inert,hidden:element.getAttribute('aria-hidden')})),overflow=document.body.style.overflow,scroll=scrollY;
  for(const entry of background){entry.element.inert=true;entry.element.setAttribute('aria-hidden','true');}
  for(const style of $$('head style',doc))panel.append(style.cloneNode(true));
  for(const link of $$('a[href]',panel)){if(link.getAttribute('href')===route())link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');}
  panel._returnScroll=scroll;panel._cleanup=()=>{for(const entry of background){entry.element.inert=entry.inert;if(entry.hidden===null)entry.element.removeAttribute('aria-hidden');else entry.element.setAttribute('aria-hidden',entry.hidden);}document.body.style.overflow=overflow;scrollTo(0,panel._returnScroll);};
  panel.addEventListener('click',e=>{
   if(!e.target.closest('[role=dialog]')){e.stopPropagation();closeMenu();return;}
   const link=e.target.closest('a[href]');if(link&&!e.ctrlKey&&!e.metaKey&&!e.shiftKey&&!e.altKey){e.preventDefault();const target=new URL(link.href);if(target.pathname===location.pathname&&target.search===location.search&&!target.hash){panel._returnScroll=0;scrollTo(0,0);return;}const href=link.href;closeMenu(false);location.assign(href);}
  });
  document.body.append(panel);document.body.style.overflow='hidden';bindPublicPopup(panel,button,'mobile');publicPopupItems(panel)[0]?.focus({preventScroll:true});
 }
 async function publicNavigation(button){
  if(currentMenu?._opener===button){closeMenu();return;}
  const name=label(button);const index=name==='Product'?'000':name==='Resources'?'001':'002';const response=await fetch('/static/states/'+index+'.html');const doc=new DOMParser().parseFromString(await response.text(),'text/html');
  if(index==='002'){openPublicMobile(doc,button);return;}
  const source=$('[class*="positioner"][data-open]',doc);if(!source)return;
  closeMenu(false);const panel=source.cloneNode(true);panel.classList.add('local-source-nav');panel.style.zIndex='1000';if(index!=='002'){panel.style.left='auto';panel.style.right='max(20px, calc((100vw - 1280px) / 2))';panel.style.top=button.getBoundingClientRect().bottom+12+'px';}
  else{panel.style.position='fixed';panel.style.inset='64px 0 auto';panel.style.maxHeight='calc(100dvh - 64px)';panel.style.overflow='auto';}
  for(const style of $$('head style',doc))panel.append(style.cloneNode(true));document.body.append(panel);bindPublicPopup(panel,button,index==='002'?'mobile':'nav');
 }
 async function publicDemoMenu(button,keyboardDirection){
  if(currentMenu?._opener===button){if(!keyboardDirection){closeMenu();return;}}else{
   const response=await fetch('/static/states/003.html'),doc=new DOMParser().parseFromString(await response.text(),'text/html'),source=$('[role=menu]',doc)?.parentElement;if(!source)return;
   closeMenu(false);const panel=source.cloneNode(true);panel.classList.add('local-source-nav');for(const style of $$('head style',doc))panel.append(style.cloneNode(true));
   const rect=button.getBoundingClientRect();Object.assign(panel.style,{position:'fixed',top:rect.bottom+5+'px',left:rect.left+'px',transform:'none',zIndex:'1000'});document.body.append(panel);bindPublicPopup(panel,button,'demo');
  }
  const target=keyboardDirection?(keyboardDirection==='ArrowUp'?publicPopupItems(currentMenu).at(-1):publicPopupItems(currentMenu)[0]):$('[role=menu]',currentMenu);target?.focus({preventScroll:true});
 }
 async function publicPopupKeydown(e){
  if(route().startsWith('/qqq153'))return false;
  const panel=currentMenu,opener=panel?._opener,kind=panel?._publicKind,items=kind?publicPopupItems(panel):[];
  if(kind&&e.key==='Escape'){e.preventDefault();closeMenu(kind!=='nav'||panel.contains(e.target)||e.target===opener);return true;}
  if(kind==='mobile'&&e.key==='Tab'){
   if(e.shiftKey&&e.target===items[0]){e.preventDefault();items.at(-1)?.focus();return true;}
   if(!e.shiftKey&&e.target===items.at(-1)){e.preventDefault();items[0]?.focus();return true;}
  }
  if(kind==='nav'&&e.key==='Tab'){
   if(e.target===opener&&!e.shiftKey){e.preventDefault();items[0]?.focus();return true;}
   if(e.target===items[0]&&e.shiftKey){e.preventDefault();opener.focus();return true;}
   if(e.target===items.at(-1)&&!e.shiftKey){e.preventDefault();publicFocusAfter(opener)?.focus();return true;}
  }
  if(kind==='demo'&&panel.contains(e.target)){
   if(e.key==='Tab'){e.preventDefault();const next=publicFocusAfter(opener,e.shiftKey);closeMenu(false);next?.focus();return true;}
   if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();let index=items.indexOf(document.activeElement);index=e.key==='Home'?0:e.key==='End'?items.length-1:index<0?(e.key==='ArrowUp'?items.length-1:0):(index+(e.key==='ArrowDown'?1:-1)+items.length)%items.length;items[index]?.focus();return true;}
   if(['Enter',' '].includes(e.key)&&e.target.matches('[role=menuitem]')){e.preventDefault();closeMenu();return true;}
  }
  const button=e.target.closest('button');
  if(button&&['ArrowDown','ArrowUp'].includes(e.key)){
   if(button.matches('[class*=switchWorkspaceButton]')){e.preventDefault();await publicDemoMenu(button,e.key);return true;}
   if(['Product','Resources'].includes(label(button))){e.preventDefault();if(currentMenu?._opener!==button)await publicNavigation(button);return true;}
  }
  return false;
 }
 async function docsGroup(button){
  const expanded=button.getAttribute('aria-expanded')==='true';const li=button.parentElement;let panel=button.nextElementSibling;
  if(!panel){const groups=await (await fetch('/static/docs-nav.json')).json();const html=groups[label(button)];if(!html)return;li.insertAdjacentHTML('beforeend',html);panel=button.nextElementSibling;}
  $$('a[aria-current]',panel).forEach(a=>{if(a.getAttribute('href')!==route())a.removeAttribute('aria-current');});
  panel.hidden=expanded;panel.style.height=expanded?'0':'auto';panel.style.opacity=expanded?'0':'1';button.setAttribute('aria-expanded',String(!expanded));li.toggleAttribute('data-closed',expanded);
 }
 function publicSearch(){
  const collection=route().startsWith('/integrations')?'integrations':'docs';modal('Search','<input type="search" aria-label="Search" placeholder="Search…" autocomplete="off"><div class="local-public-results" role="listbox" aria-label="Search results"></div>',null,null);
  const input=$('input',dialog),results=$('.local-public-results',dialog);let version=0;
  input.addEventListener('input',async()=>{const n=++version;const rows=await api('/api/search?collection='+collection+'&q='+encodeURIComponent(input.value));if(n!==version)return;results.innerHTML=rows.map(row=>'<a role="option" href="'+esc(row.path)+'"><strong>'+esc(row.title)+'</strong><p>'+esc(row.excerpt)+'</p></a>').join('')||(input.value.length>=2?'<p>No results found</p>':'');});
  input.addEventListener('keydown',e=>{if(e.key==='ArrowDown'){e.preventDefault();$('a',results)?.focus();}if(e.key==='Enter'){$('a',results)?.click();}});
 }
 async function search(){if(workspaceSearch?.active()){workspaceSearch.render();return;}const q=$('input[placeholder*="Search"],input[type=search],input[aria-label*=Search]');if(!q||!state)return;let box=$('.local-search-results');if(!box){box=document.createElement('section');box.className='local-search-results';$('main')?.append(box);}const value=q.value.toLowerCase().trim();box.innerHTML=value?state.issues.filter(i=>(i.id+' '+i.title+' '+i.description).toLowerCase().includes(value)).map(rowHTML).join(''):'';}
 function bindSettings(){
  if(!route().includes('/settings/')||route().endsWith('/commit-signing-key'))return;
  api('/api/settings?route='+encodeURIComponent(route())).then(values=>{$$('main [role=combobox]').forEach((button,index)=>{if('combobox-'+index in values)button.textContent=optionText(values['combobox-'+index]);});for(const e of $$('main input,main textarea,main select')){const key=e.id&&e.id in values?e.id:e.dataset.controlId||e.name||e.placeholder;if(key in values){if(e.type==='checkbox')e.checked=values[key];else e.value=values[key];}}for(const e of $$('main [role=switch]')){const key=e.dataset.controlId||label(e);if(key in values)e.setAttribute('aria-checked',String(!!values[key]));}}).catch(e=>toast(e.message));
 }
 const optionText=value=>value.replace(/^Aa(?:\\n|\n)/,'');
 const sidebarGroups={Personal:['Inbox','My issues','Agent','Drafts'],Workspace:['Projects','Views','Teams','Members']};
 const sidebarPaths={'Inbox':'/qqq153/inbox','My issues':'/qqq153/my-issues/assigned','Agent':'/qqq153/agent','Drafts':'/qqq153/drafts','Projects':'/qqq153/projects/all','Views':'/qqq153/views/issues','Teams':'/qqq153/teams','Members':'/qqq153/members'};
 const sidebarDefaults={'Drafts':'Show when badged','Teams':"Don't show",'Members':"Don't show"};
 let sidebarPreferences={},sidebarTemplates,sidebarReady=false,codeFontPreferences={},navigationFavorites=[],navigationFavoriteMarkup=null;
 const navigationTitle=path=>({[teamPath('/qqq153/team/QQQ/overview')]:(state?.teams?.find(t=>t.id==='QQQ')?.title||'Qqq153')+' · Home',[teamPath('/qqq153/team/QQQ/active')]:'Qqq153 · Active','/qqq153/team/QQQ/backlog':'Qqq153 · Backlog','/qqq153/team/QQQ/all':'Qqq153 · All issues','/qqq153/inbox':'Inbox','/qqq153/my-issues/assigned':'My issues','/qqq153/projects/all':'Projects','/qqq153/views/issues':'Views','/qqq153/teams':'Teams','/qqq153/members':'Members'}[path]||$('main h1')?.textContent?.trim()||document.title.replace(/ [–—-] Linear$/,''));
 const navigationFavorite=path=>navigationFavorites.some(item=>item.path===path);
 let navigationSaveQueue=Promise.resolve();
 function saveNavigationFavorites(path=route(),enabled=!navigationFavorite(path)){
  const job=navigationSaveQueue.catch(()=>{}).then(async()=>{
   const next=navigationFavorites.filter(item=>item.path!==path);if(enabled)next.push({path,title:navigationTitle(path)});
   await api('/api/settings','PUT',{route:'/qqq153/settings/account/preferences',key:'navigation-favorites',value:next});navigationFavorites=next;await refresh();
  });navigationSaveQueue=job;return job;
 }
 function renderNavigationFavorites(){
  if(!sidebarReady||route().includes('/settings/'))return;
  for(const old of $$('[data-navigation-favorite]'))old.remove();
  const button=$('button[aria-controls="sidebarFavorites"]'),section=button?.closest('[data-sidebar-section]');
  if(section){let list=$('#sidebarFavorites',section);if(!list){list=document.createElement('div');list.id='sidebarFavorites';button.parentElement.after(list);}
   for(const item of navigationFavorites){
    const template=document.createElement('template');template.innerHTML=navigationFavoriteMarkup||'<a class="issue-favorite-link"><span data-project-label-favorite-title></span><button aria-label="Remove favorite">×</button></a>';const a=template.content.firstElementChild;a.href=item.path;a.dataset.navigationFavorite=item.path;a.dataset.active=String(route()===item.path);
    const title=$('[data-project-label-favorite-title]',a);if(title){title.textContent=item.title;title.title=item.title;}
    const remove=$('[aria-label="Remove favorite"]',a);if(remove){remove.onclick=e=>{e.preventDefault();e.stopPropagation();saveNavigationFavorites(item.path,false).catch(e=>toast(e.message));};remove.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();remove.click();}};}
    a.oncontextmenu=e=>{e.preventDefault();menu(a,[{text:'Remove from favorites',action:()=>saveNavigationFavorites(item.path,false)},{text:'Copy URL',action:()=>copy(location.origin+item.path)}]);};list.append(a);
   }
   const populated=!!list.children.length;button.disabled=!populated;section.parentElement.inert=!populated;Object.assign(section.parentElement.style,{height:populated?'auto':'0px',opacity:populated?'1':'0',transform:populated?'none':'translateY(-10px)'});list.hidden=button.getAttribute('aria-expanded')==='false';
  }
  if(!currentIssue&&!route().includes('/document/')&&!route().includes('/project/')&&!route().includes('/projects/label/')&&!route().includes('/view/'))for(const control of $$('main button[aria-label="Add to favorites"],main button[aria-label="Remove from favorites"]')){const active=navigationFavorite(route());control.setAttribute('aria-label',active?'Remove from favorites':'Add to favorites');control.setAttribute('aria-checked',String(active));}
 }

 const sidebarLink=name=>$(name==='Views'?'a[href="/qqq153/views"],a[href^="/qqq153/views/"]':name==='My issues'?'a[href^="/qqq153/my-issues/"]':'a[href="'+sidebarPaths[name]+'"]');
 const sidebarMode=name=>sidebarPreferences[name]||sidebarDefaults[name]||'Always show';
 const sidebarCount=name=>name==='Drafts'?(state?.drafts||[]).length:name==='Inbox'?(state?.notifications||[]).filter(n=>!n.read).length:name==='My issues'?(state?.issues||[]).filter(i=>!i.archived&&i.assignee===sessionInfo?.account?.email_normalized&&!['Done','Canceled','Duplicate'].includes(i.status)).length:0;
 const sidebarOrder=group=>{const names=sidebarGroups[group],saved=sidebarPreferences[group+' order']||[];return [...new Set([...saved.filter(n=>names.includes(n)),...names])];};
 function applySidebar(){
  if(!sidebarReady||route().includes('/settings/'))return;
  for(const [group,names] of Object.entries(sidebarGroups)){
   const example=sidebarLink(names[0]);if(!example)continue;
   const holder=a=>a.closest('[aria-roledescription="sortable"]')?.parentElement||a;
   let marker=$('[data-sidebar-group="'+group+'"]');if(!marker){marker=document.createElement('span');marker.hidden=true;marker.dataset.sidebarGroup=group;holder(example).before(marker);}
   for(const name of sidebarOrder(group)){
    let a=sidebarLink(name);if(!a&&sidebarTemplates?.[name]){const t=document.createElement('template');t.innerHTML=sidebarTemplates[name].html;a=t.content.firstElementChild;a.removeAttribute('data-control-id');marker.before(a);}
    if(!a)continue;const row=holder(a),mode=sidebarMode(name),count=sidebarCount(name);row.dataset.sidebarItem=name;const active=route()===a.getAttribute('href')||(name==='Inbox'&&route()==='/qqq153/welcome-message')||(name==='My issues'&&route().startsWith('/qqq153/my-issues/'))||(name==='Views'&&route().startsWith('/qqq153/views/'))||(name==='Projects'&&route().startsWith('/qqq153/projects/'));row.hidden=!active&&(mode==="Don't show"||(mode==='Show when badged'&&!count));marker.before(row);
    a.setAttribute('data-active',String(active));
    for(const badge of $$('[data-count-badge]',a)){badge.textContent=count;badge.hidden=!count;badge.classList.toggle('local-dot-badge',sidebarPreferences.badge==='Dot');badge.setAttribute('aria-label',count+' unread');}
   }
  }
 }
 let sidebarSaveQueue=Promise.resolve();
 function saveSidebar(changes){const job=sidebarSaveQueue.catch(()=>{}).then(async()=>{const next={...sidebarPreferences,...changes};await api('/api/settings','PUT',{route:'/qqq153/settings/account/preferences',key:'sidebar',value:next});sidebarPreferences=next;applySidebar();});sidebarSaveQueue=job;return job;}
 function customizeSidebar(){
  const grip='<svg width="6" height="10" role="img" focusable="false" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 6 10"><path fill-rule="evenodd" clip-rule="evenodd" d="M1 8C1.55228 8 2 8.44772 2 9C2 9.55228 1.55228 10 1 10C0.447715 10 0 9.55228 0 9C0 8.44772 0.447715 8 1 8ZM5 8C5.55228 8 6 8.44772 6 9C6 9.55228 5.55228 10 5 10C4.44772 10 4 9.55228 4 9C4 8.44772 4.44772 8 5 8ZM1 4C1.55228 4 2 4.44772 2 5C2 5.55228 1.55228 6 1 6C0.447715 6 0 5.55228 0 5C0 4.44772 0.447715 4 1 4ZM5 4C5.55228 4 6 4.44772 6 5C6 5.55228 5.55228 6 5 6C4.44772 6 4 5.55228 4 5C4 4.44772 4.44772 4 5 4ZM1 0C1.55228 0 2 0.447715 2 1C2 1.55228 1.55228 2 1 2C0.447715 2 0 1.55228 0 1C0 0.447715 0.447715 0 1 0ZM5 0C5.55228 0 6 0.447715 6 1C6 1.55228 5.55228 2 5 2C4.44772 2 4 1.55228 4 1C4 0.447715 4.44772 0 5 0Z"></path></svg>';
  const choices=name=>name==='Inbox'?['Always show','Show when badged']:name==='Drafts'?['Always show','Show when badged',"Don't show"]:['Always show',"Don't show"],select=(name,values,value)=>'<select aria-label="'+esc(name==='badge'?'Default badge style':name)+'" data-sidebar-setting="'+esc(name)+'">'+values.map(v=>'<option'+(v===value?' selected':'')+'>'+esc(v)+'</option>').join('')+'</select>';
  const o=modal('Customize sidebar','<div class="local-sidebar-row"><span>Default badge style</span>'+select('badge',['Count','Dot'],sidebarPreferences.badge||'Count')+'</div>'+Object.keys(sidebarGroups).map(group=>'<h3 class="local-sidebar-heading">'+group+'</h3><div data-sidebar-sort="'+group+'">'+sidebarOrder(group).map(name=>'<div class="local-sidebar-row" data-sidebar-name="'+esc(name)+'" draggable="true" role="button" tabindex="-1" aria-disabled="false" aria-roledescription="sortable" aria-label="'+esc(name)+'"><span class="local-sidebar-handle" aria-hidden="true">'+grip+'</span><span>'+esc(name)+'</span>'+select(name,choices(name),sidebarMode(name))+'</div>').join('')+'</div>').join(''),null,null,true);
  $('.local-close',o).setAttribute('aria-label','Close modal dialog');let moving=null;
  for(const s of $$('[data-sidebar-setting]',o))s.onchange=async()=>{const controls=$$('select,button',o);controls.forEach(e=>e.disabled=true);try{await saveSidebar({[s.dataset.sidebarSetting]:s.value});}catch(e){$('.local-inline-error',o).textContent=e.message;s.value=s.dataset.sidebarSetting==='badge'?(sidebarPreferences.badge||'Count'):sidebarMode(s.dataset.sidebarSetting);}finally{controls.forEach(e=>e.disabled=false);}};
  const persistOrder=async group=>{try{await saveSidebar({[group.dataset.sidebarSort+' order']:$$('[data-sidebar-name]',group).map(e=>e.dataset.sidebarName)});}catch(e){$('.local-inline-error',o).textContent=e.message;}};
  let originalOrder=null;
  const resetDrag=()=>{if(moving){moving.removeAttribute('aria-pressed');moving.classList.remove('local-sidebar-moving');}moving=null;originalOrder=null;};
  const beginDrag=row=>{resetDrag();moving=row;originalOrder=Array.from(row.parentElement.children);row.setAttribute('aria-pressed','true');row.classList.add('local-sidebar-moving');};
  const cancelDrag=()=>{if(moving&&originalOrder){const group=moving.parentElement;originalOrder.forEach(e=>group.append(e));}resetDrag();};
  for(const row of $$('[data-sidebar-name]',o)){
   row.ondragstart=e=>{if(e.target.closest('select,option')){e.preventDefault();return;}beginDrag(row);e.dataTransfer.setData('text/plain',row.dataset.sidebarName);e.dataTransfer.effectAllowed='move';};
   row.ondragover=e=>{if(moving?.parentElement===row.parentElement){e.preventDefault();e.dataTransfer.dropEffect='move';}};
   row.ondrop=async e=>{if(!moving||moving===row||moving.parentElement!==row.parentElement)return;e.preventDefault();const group=row.parentElement,box=row.getBoundingClientRect();if(e.clientY<box.top+box.height/2)row.before(moving);else row.after(moving);resetDrag();await persistOrder(group);};
   row.ondragend=resetDrag;
   row.onkeydown=async e=>{
    if(e.target!==row)return;
    if(e.key===' '||e.key==='Enter'){e.preventDefault();e.stopPropagation();if(moving===row){const group=row.parentElement;resetDrag();await persistOrder(group);}else beginDrag(row);return;}
    if(moving!==row)return;
    if(e.key==='Escape'){e.preventDefault();e.stopPropagation();cancelDrag();row.focus();return;}
    if(!['ArrowUp','ArrowDown'].includes(e.key))return;
    e.preventDefault();e.stopPropagation();const next=e.key==='ArrowUp'?row.previousElementSibling:row.nextElementSibling;if(!next)return;if(e.key==='ArrowUp')next.before(row);else next.after(row);row.focus();
   };
  }
 }
 function applyInterfacePreferences(values){
  document.body.classList.toggle('local-pointer-cursors',values['interfaceAndTheme.pointerCursors-control']??values.c50??false);
  document.body.classList.toggle('local-underline-links',values['interfaceAndTheme.underlineLinks-control']??values.c51??false);
  codeFontPreferences=values['code-font']||{};applyCodeFont();
 }
 function applyCodeFont(){
  const font=codeFontPreferences,size=Math.min(24,Math.max(10,Number(font.size)||12)),height=font.height||'Regular',family=String(font.family||'').trim(),line=size+({Tight:6,Regular:8,Relaxed:10}[height]||8);
  const button=$$('main button').find(b=>b.dataset.codeFont||/^\d+px, (Tight|Regular|Relaxed), /.test(b.textContent.trim()));if(button){button.dataset.codeFont='true';button.textContent=size+'px, '+height+', '+(family||'Default');}
  for(const block of $$('pre,code,[class*="diff-syntax-"]')){block.style.setProperty('--local-code-size',size+'px');block.style.setProperty('--local-code-line',line+'px');block.style.setProperty('--local-code-family',family||'ui-monospace, SFMono-Regular, Menlo, monospace');block.dataset.localCodeFont='true';}
  for(const row of $$('[data-row-index]')){row.style.height=line+'px';if(row.parentElement.style.height)row.parentElement.style.height=line+'px';}
  for(const grid of $$('[style*="grid-template-rows"]'))if($('[data-row-index]',grid)){const count=grid.style.gridTemplateRows.trim().split(/\s+/).length;grid.style.gridTemplateRows=Array(count).fill(line+'px').join(' ');}
 }
 function codeFontMenu(anchor){
  const font=codeFontPreferences,m=menu(anchor,[]);m.classList.add('local-font-menu');m.innerHTML='<label>Font size<select name="size" aria-label="Font size">'+Array.from({length:15},(_,i)=>i+10).map(n=>'<option value="'+n+'"'+(n===(Number(font.size)||12)?' selected':'')+'>'+n+'px</option>').join('')+'</select></label><label>Line height<select name="height" aria-label="Line height">'+['Tight','Regular','Relaxed'].map(v=>'<option'+(v===(font.height||'Regular')?' selected':'')+'>'+v+'</option>').join('')+'</select></label><label>Custom font family<input name="family" aria-label="Custom font family" maxlength="120" value="'+esc(font.family||'')+'"></label>';
  for(const input of $$('input,select',m))input.onchange=async()=>{const controls=$$('input,select',m);controls.forEach(e=>e.disabled=true);const value={size:Number($('[name=size]',m).value),height:$('[name=height]',m).value,family:$('[name=family]',m).value.trim()};try{await api('/api/settings','PUT',{route:'/qqq153/settings/account/preferences',key:'code-font',value});codeFontPreferences=value;applyCodeFont();}catch(e){toast(e.message);}finally{controls.forEach(e=>e.disabled=false);}};
 }
 async function applyAppTheme(value){
  let theme=optionText(value||'System preference');if(theme==='System preference')theme=matchMedia('(prefers-color-scheme: dark)').matches?'Dark':'Light';
  const themes=await (await fetch('/static/themes.json')).json();const values=themes[theme];if(!values)return;
  for(const [key,color] of Object.entries(values.variables))if((key.startsWith('--sx-')||key.startsWith('--bg-'))&&!/https?:/.test(color))document.documentElement.style.setProperty(key,color);
  // The app scopes palettes to separate sidebar, content, and card providers.
  // Apply the corresponding captured provider palette, preserving those layers.
  const targets=new Map((values.providers||[]).map(provider=>[provider.path,provider]));const done=new Set();
  for(const source of themes.Light.providers||[]){const target=targets.get(source.path);if(!target||done.has(source.className))continue;done.add(source.className);for(const element of $$('.'+source.className)){if(element.closest('button'))continue;for(const [key,color] of Object.entries(target.variables))if(!/https?:/.test(color))element.style.setProperty(key,color);}}
  document.documentElement.style.colorScheme=['Dark','Magic Blue','Classic Dark'].includes(theme)?'dark':'light';
 }
 document.addEventListener('change',async e=>{
  const t=e.target;if(route().endsWith('/commit-signing-key'))return;if(!sessionInfo?.authenticated||t.closest('.local-dialog,.local-menu,.local-project-overlay'))return;
  if(t.name==='selectedScope'){keyPermissions();return;}
  if(route().includes('/settings/')&&t.matches('input,textarea,select')){try{await storeSetting(t.id||t.dataset.controlId||t.name||t.placeholder,t.type==='checkbox'?t.checked:t.value);if(route().endsWith('/account/preferences'))applyInterfacePreferences(await api('/api/settings?route='+encodeURIComponent(route())));toast('Saved');}catch(err){toast(err.message);}}
  if(t.matches('input[type=checkbox]')&&t.closest('a[href*="/issue/"]')){const a=t.closest('a');a.dataset.selected=t.checked;}
 });
 document.addEventListener('input',e=>{if(directoryRoute()&&e.target.matches('main input'))renderDirectory();if(e.target.matches('textarea[aria-label="Edit code lines"]')){publicCodeDraft=e.target.value;const display=e.target.parentElement.querySelector('[class*="editableDisplay"]');if(display)display.innerHTML=e.target.value.split('\n').map(line=>'<span class="line">'+esc(line)+'\n</span>').join('');}if(currentIssue&&e.target.isContentEditable){const submit=$('[aria-label="Submit comment"]');if(submit){issueAttachments?.submitState();}}if(route().endsWith('/search')&&e.target.matches('input'))search();});
 document.addEventListener('focusout',e=>{if(sessionInfo?.authenticated&&route().includes('/settings/')&&!route().endsWith('/commit-signing-key')&&!e.target.closest('.local-dialog,.local-menu,.local-project-overlay')&&e.target.matches('input:not([type=checkbox]):not([type=radio]),textarea'))storeSetting(e.target.id||e.target.dataset.controlId||e.target.name||e.target.placeholder,e.target.value).catch(err=>toast(err.message));});
 document.addEventListener('click',async e=>{
  const authAction=e.target.closest('[data-auth]');if(authAction){e.preventDefault();const a=authAction.dataset.auth;if(a==='passkey'){authAction.disabled=true;try{await passkey();}catch(err){renderAuth(err.message);}return;}if(a==='back')loginMode='start';else if(a==='code')loginMode='code';else{loginProvider=a;loginMode='email';}renderAuth();return;}
  if(e.target.closest('[data-copy-target]')){e.preventDefault();copy($('[aria-label="Original destination"]').value);return;}
  if(currentMenu&&!e.composedPath().includes(currentMenu)&&!currentMenu._opener?.contains(e.target)&&!e.target.closest('.local-menu,.local-source-nav'))closeMenu(!currentMenu._publicKind);
  const record=e.target.closest('[data-record]');if(record){await recordDetail(record.dataset.kind,record.dataset.record);return;}
  const cell=e.target.closest('[data-list-grid-column]');if(cell&&sessionInfo?.authenticated){const a=cell.closest('a[href*="/issue/"]');if(a&&['status','priority'].includes(cell.dataset.listGridColumn)){e.preventDefault();const id=a.dataset.issueId||a.href.match(/[A-Z][A-Z0-9]*-\d+/)?.[0];const prop=cell.dataset.listGridColumn;menu(cell,(prop==='status'?statuses:priorities).map(v=>({text:v,action:async()=>{await api('/api/entities/issues/'+id,'PATCH',{[prop]:v});await refresh();}})));return;}if(cell?.dataset.listGridColumn==='checkbox'){e.stopPropagation();return;}}
  const button=e.target.closest('button,[role=button],[role=tab],[role=switch],[role=combobox],[tabindex]');if(!button||button.closest('.local-dialog,.local-menu,.local-project-overlay'))return;
  if(button.closest('a[href]'))return;
  const text=label(button),t=button.innerText?.trim()||text;
  if(!route().startsWith('/qqq153')){
   if(publicFeatureDialog&&button.matches('[role=dialog].UBZV-G_dialog .UBZV-G_close')){e.preventDefault();closePublicFeatureDialog();return;}
   if(['/','/homepage'].includes(route())&&button.getAttribute('role')==='combobox'&&publicCodeThemes.includes(t)){publicCodeThemeMenu(button);return;}
   if(text==='Toggle theme'){const theme=document.documentElement.dataset.theme==='light'?'dark':'light';document.documentElement.dataset.theme=theme;document.documentElement.style.colorScheme=theme;localStorage.setItem('linear-docs-theme',theme);return;}
   if(text==='Search'||t.startsWith('Search…')){publicSearch();return;}
   if(button.matches('li > button[aria-expanded]')&&route().startsWith('/docs')){await docsGroup(button);return;}
   if(t==='Product'||t==='Resources'||button.className.includes('mobileMenuTrigger')){await publicNavigation(button);return;}
   if(button.matches('[class*=switchWorkspaceButton]')){await publicDemoMenu(button);return;}
   if(currentMenu?._publicKind==='demo'&&button.getAttribute('role')==='menuitem'&&['Settings','Log out'].includes(text)){e.preventDefault();closeMenu();return;}
   if(sourceHomeHTML&&['/','/homepage'].includes(route())&&button.getAttribute('role')==='menuitem'&&text==='Settings'){e.preventDefault();restoreHome();return;}
   if(sourceHomeHTML&&(/Close|Dismiss/.test(text)||button.dataset.sourceButtonIndex==='2')){e.preventDefault();restoreHome();return;}
   if(route()==='/'||route()==='/homepage'){
    if(sourceHomeHTML&&['Product','Resources'].includes(t)){e.preventDefault();restoreHome();return;}
    if(await publicState(button)){e.preventDefault();return;}
   }
   if(t==='Get started'){location.href='/signup';return;}if(t==='Contact sales'){location.href='/contact/sales';return;}
   if(button.getAttribute('aria-expanded')!==null){const expanded=button.getAttribute('aria-expanded')==='true';button.setAttribute('aria-expanded',String(!expanded));const panel=button.getAttribute('aria-controls')?document.getElementById(button.getAttribute('aria-controls')):button.nextElementSibling;if(panel)panel.hidden=expanded;return;}
   if(/^(Monthly|Yearly|Annually)/.test(t)){const annual=t!=='Monthly';$$('[data-annual-price]').forEach(el=>el.textContent=annual?el.dataset.annualPrice:el.dataset.monthlyPrice);button.setAttribute('aria-pressed','true');return;}
   if(button.matches('[role=tab]')){const group=button.parentElement;$$('[role=tab]',group).forEach(b=>b.setAttribute('aria-selected',String(b===button)));return;}
   return;
  }
  await appReady;if(!sessionInfo?.authenticated)return;
  try{
   if(await documentTemplates?.handleClick(button))return;
   if(await issueTemplates?.handleClick(button))return;
   if(await recurringIssues?.handleClick(button))return;
   if(await documentManager?.handleClick(button))return;
   if(projectLabelPage?.handleClick(button)||projectDetail?.handleClick(button)||viewManager?.handleClick(button))return;
   if(/Workspace Menu/.test(text)||(/^QQ\s*(qqq153)?$/.test(t)&&button.tagName==='BUTTON')){workspaceMenu(button);return;}
   if(text==='Search workspace'){location.href='/qqq153/search';return;}
   if(['Create new issue','Create issue','New issue'].includes(text)){issueDialog();return;}
   if(['Add sub-issues','Create sub-issue'].includes(text)){issueDialog(currentIssue?.id);return;}
   if(inboxRoute()){
    if(text==='Notification actions'){inboxActions(button);return;}
    if(['Show unreads only','Show all notifications'].includes(text)){await inboxSetting('unread-only',!inboxSettings?.['unread-only']);return;}
    if(text==='Display options'){inboxDisplay(button);return;}
    if(text==='Add filter'){inboxFilter(button);return;}
    if(text==='Snooze notification'){snoozeNotification(button);return;}
    if(text==='Delete notification'){await api('/api/entities/notifications/welcome','DELETE');location.href='/qqq153/inbox';return;}
   }
   if(route()==='/qqq153/members'&&text==='Add filter'){memberFilter(button);return;}
   if(route()==='/qqq153/members'&&text==='Display options'){memberDisplay(button);return;}
   if(directoryRoute()&&text.startsWith('Order by ')){const value=text.slice(9);if((displaySettings['directory-order']||'Name')===value)await directorySetting('directory-desc',!displaySettings['directory-desc']);else await directorySetting('directory-order',value);return;}
   if(text==='Teams options'){menu(button,[{text:'Go to teams settings',href:'/qqq153/settings/teams'}]);return;}
   if(text==='Add filter'&&!configurationKind()){filterMenu(button);return;}
   if(text==='Display options'&&!configurationKind()){displayMenu(button);return;}
   if(['Open details','Close details'].includes(text)){await detailsPanel();return;}
   if(text==='Dismiss'){const item=button.closest('[data-contextual-menu]')||button.parentElement;item.hidden=true;await storeSetting('dismiss-'+button.dataset.controlId,true);return;}
   if(['Add to favorites','Remove from favorites'].includes(text)){await saveNavigationFavorites(route(),text==='Add to favorites');return;}
   if(text==='Open Help menu'){help(button);return;}
   if(button.dataset.codeFont||/^\d+px, (Tight|Regular|Relaxed), /.test(t)){codeFontMenu(button);return;}
   if(text==='Customize sidebar'){customizeSidebar();return;}
   if(text==='Show more links'||t==='More'){menu(button,[...['Members','Teams'].map(name=>({text:name,href:sidebarPaths[name]})),{text:'Customize sidebar',action:customizeSidebar}]);return;}
   if(text==='Team menu'){menu(button,[{text:navigationFavorite(teamPath('/qqq153/team/QQQ/overview'))?'Unfavorite':'Favorite',action:()=>saveNavigationFavorites(teamPath('/qqq153/team/QQQ/overview'))},{text:'Team settings',href:teamPath('/qqq153/settings/teams/QQQ')},{text:'Copy URL',action:()=>copy(location.origin+teamPath('/qqq153/team/QQQ/overview'))},{text:'Open archive',action:()=>{filter={archived:'true'};toast('Archive');renderIssues();}},{text:'Subscribe',action:()=>storeSetting('team-subscribe',true)},{text:'Configure Slack notifications…',href:'/qqq153/settings/integrations/slack'},{text:'Leave team…',action:()=>modal('Leave team','<p>Leave Qqq153?</p>','Leave team',async()=>{await api('/api/teams/'+activeTeam()+'/membership','POST',{joined:false});closeDialog();await refresh();toast('Left team');},true)}]);return;}
   if(text==='Invite people'||t==='Invite'||text==='Invite members'){invite();return;}
   if(text==='Join a team'){workspaceUI.joinTeam(button);return;}
   if(text==='Setup active issues notifications'){menu(button,[{text:'Subscribe',action:()=>storeSetting('active-notifications',true)},{text:'Configure Slack notifications…',href:'/qqq153/settings/integrations/slack'}]);return;}
   if(['Add new view','Create new view','New view','Create view'].includes(text)){createRecord('views','New view');return;}
   if(/^(Create new project|New project|Create project)$/.test(text)){createRecord('projects','New project');return;}
   if(/^(New document|Create document|Add document)$/.test(text)){createRecord('documents','New document');return;}
   if(['Create a team','Create new team'].includes(text)){createRecord('teams','Create a team');return;}
   if(button.dataset.issueCount){const value=!displaySettings['force-count'];await displaySetting('force-count',value);return;}
   if(text==='Collapse group'){const box=button.closest('[data-issue-group]')||$('[data-local-issue-list]');if(box)$$('a[href*="/issue/"]',box).forEach(a=>a.hidden=!a.hidden);button.setAttribute('aria-expanded',button.getAttribute('aria-expanded')!=='false'?'false':'true');return;}
   if(['Workspace','Favorites','Your teams','Try','Qqq153'].includes(t)&&button.tagName==='BUTTON'){const p=button.parentElement;[...p.children].filter(c=>c!==button&&!c.contains(button)).forEach(c=>c.hidden=!c.hidden);button.setAttribute('aria-expanded',button.getAttribute('aria-expanded')!=='false'?'false':'true');return;}
   if(currentIssue){
    if(statuses.includes(text)||button.dataset.issueProperty==='status'){property(button,'status',statuses);return;}
    if(['Set priority',...priorities].includes(text)||button.dataset.issueProperty==='priority'){property(button,'priority',priorities);return;}
    if(text==='Assign'||button.dataset.issueProperty==='assignee'){property(button,'assignee',[null,sessionInfo.account.email_normalized]);return;}
    if(['Add label','Add labels'].includes(text)){const labels=await api('/api/entities/labels');menu(button,[...labels.map(l=>({text:(currentIssue.labels?.includes(l.title)?'✓ ':'')+l.title,action:()=>saveIssue({labels:currentIssue.labels?.includes(l.title)?currentIssue.labels.filter(x=>x!==l.title):[...(currentIssue.labels||[]),l.title]})})),{text:'Create new label',action:()=>createRecord('labels','New label')}],'Search labels…');return;}
    if(text==='Add to project'||button.dataset.issueProperty==='project'){menu(button,[...(currentIssue.project?[{text:'No project',action:()=>saveIssue({project:null})}]:[]),...state.projects.map(p=>({text:p.title,action:()=>saveIssue({project:p.id})})),{text:'Create new project',action:()=>createRecord('projects','New project')}],'Search projects…');return;}
    if(text==='Issue options'){issueOptions(button);return;}
    if(['Copy issue URL','Copy issue ID','Copy branch name','Copy as prompt'].includes(text)){await issueProperties.copyValue({'Copy issue URL':'Copy URL','Copy issue ID':'Copy ID','Copy branch name':'Copy git branch name','Copy as prompt':'Copy as prompt'}[text]);return;}
    if(['Subscribe','Unsubscribe','Subscribe to issue','Unsubscribe from issue'].includes(text)){await saveIssue({subscribed:!currentIssue.subscribed});button.textContent=currentIssue.subscribed?'Unsubscribe':'Subscribe';return;}
    if(text==='Change subscribers'){menu(button,[{text:(currentIssue.subscribed?'✓ ':'')+sessionInfo.account.email_normalized,action:()=>saveIssue({subscribed:!currentIssue.subscribed})}]);return;}
    if(text==='Submit comment'){e.preventDefault();await issueAttachments.submit();return;}
    if(text==='Add reaction'){menu(button,['👍','❤️','🎉','👀','🚀'].map(v=>({text:v,action:async()=>{await saveIssue({reactions:[...(currentIssue.reactions||[]),v]});button.textContent=v;}})));return;}
   }
   if(/Play \(/.test(text)){const v=$('video');if(v){await v.play();button.setAttribute('aria-label','Pause (keyboard shortcut k)');}return;}
   if(/Pause \(/.test(text)){$('video')?.pause();button.setAttribute('aria-label','Play (keyboard shortcut k)');return;}
   if(/Mute \(/.test(text)){const v=$('video');if(v)v.muted=!v.muted;return;}
   if(text==='Log out'){for(const key of Object.keys(sessionStorage))if(key.startsWith('linear-issue-scratch:'))sessionStorage.removeItem(key);await api('/api/auth/logout','POST',{});location.href='/login';return;}
   if(text==='Agent'||text==='Chat history'){location.href='/qqq153/agent';return;}
   if(text==='Menu'){menu(button,[{text:navigationFavorite(route())?'Remove from favorites':'Add to favorites',action:()=>saveNavigationFavorites()},{text:'Copy URL',action:()=>copy(location.href)},{text:'Settings',href:'/qqq153/settings/account/preferences'}]);return;}
   if(route().includes('/settings/')){
    if(configurationKind()==='labels'&&text==='Add filter'){labelFilter(button);return;}
    if(configurationKind()==='labels'&&text==='Display options'){labelDisplay(button);return;}
    if(configurationKind()&&['New label','New group','Create new workflow state','Create new project status'].includes(text)){newConfiguration(text==='New group'?'label-groups':configurationKind(),button);return;}
    if(text==='New webhook'){location.href='/qqq153/settings/api/webhooks/new';return;}
    if(text==='New OAuth application'){location.href='/qqq153/settings/api/applications/new';return;}
    if(text==='Delete workspace'){const challenge=await api('/api/workspace/deletion-code','POST',{});modal('Verify workspace deletion request','<p>If you are sure you want to proceed with the deletion of the workspace '+esc(state.workspace.name)+', please continue below.</p><p>Keep in mind this operation is irreversible and will result in a complete deletion of all the data associated with the workspace.</p><label>Enter deletion code sent to '+esc(challenge.email)+'<input name="code" autocomplete="one-time-code" required></label><label><input type="checkbox" name="acknowledged" required> I acknowledge that all of the workspace data will be deleted and want to proceed.</label>','Delete my workspace',async f=>{await api('/api/workspace/delete','POST',{id:challenge.id,code:f.get('code'),acknowledged:f.has('acknowledged')});location.replace('/login');});return;}
    if(text==='New passkey'){await passkey(true);return;}
    if(text==='New API key'){location.href='/qqq153/settings/account/security/api-keys/new';return;}
    if(text==='Change email'){modal('Change email','<p>If you’d like to change the email address for your account, we’ll send a verification link to your new email address. This change will apply across all workspaces that you are a member of.</p><label>Enter the new email address you’d like to use.<input type="email" name="email" placeholder="New email address" required></label>','Check for existing account',async f=>{await api('/api/profile/email','POST',{email:f.get('email')});closeDialog();modal('Check your email','<p>We sent a verification link to '+esc(f.get('email'))+'.</p>',null,null,true);});return;}
    if(text==='Log out'){for(const key of Object.keys(sessionStorage))if(key.startsWith('linear-issue-scratch:'))sessionStorage.removeItem(key);await api('/api/auth/logout','POST',{});location.href='/login';return;}
    if(text==='Leave workspace'){workspaceUI.leave();return;}
    if(text==='Export…'){await api('/api/export','POST',{});toast('Your export is ready. Check your email for the download link.');return;}
    if(text==='Cancel'&&route().endsWith('/api-keys/new')){location.href='/qqq153/settings/account/security';return;}
    if(text==='Update'&&route().endsWith('/account/profile'))return;
    if(button.getAttribute('role')==='combobox'){
     const specs=await (await fetch('/static/settings-options.json')).json();const index=$$('main [role=combobox]').indexOf(button);const spec=specs.find(x=>x.path===route()&&x.index===index);
     if(spec?.options?.length){menu(button,spec.options.map(value=>({text:optionText(value),action:async()=>{await storeSetting('combobox-'+index,value);button.textContent=optionText(value);button.dataset.selectedValue=value;if(route().endsWith('/account/preferences')&&index===5)await applyAppTheme(value);}})));return;}
    }
    if(button.getAttribute('role')==='switch'){const value=button.getAttribute('aria-checked')!=='true';button.setAttribute('aria-checked',String(value));await storeSetting(button.dataset.controlId||text,value);return;}
    if(/Save|Update|Apply/.test(text)){for(const input of $$('main input,main textarea'))await storeSetting(input.dataset.controlId||input.name,input.value);toast('Saved');return;}
    if(/New label|Create label|Add label/.test(text)){createRecord('labels','New label');return;}
    if(/Create.*key|New.*key/.test(text)){const record=await api('/api/entities/api-keys','POST',{title:'Personal API key',key:crypto.randomUUID()});modal('Personal API key',`<input readonly value="${esc(record.key)}">`,null,null,true);return;}
    if(/Connect|Install|Add.*integration/.test(text)){modal(text,'<p>Local integration</p><label>Name<input name="title" required value="'+esc(document.title.replace(' – Linear',''))+'"></label>','Connect',async f=>{await api('/api/entities/integrations','POST',{...Object.fromEntries(f),route:route(),connected:true});closeDialog();button.textContent='Disconnect';await storeSetting('connected',true);},true);return;}
    if(/Upgrade|Manage|View all plans|All plans/.test(text)){location.href='/pricing';return;}
    if(/Delete|Remove|Leave/.test(text)){modal(text,'<p>'+esc(text)+'?</p>',text,async()=>{closeDialog();toast('This account action has not been implemented in the local copy.');},true);return;}
    if(/Dark|Light|System/.test(text)){menu(button,['System','Light','Dark'].map(v=>({text:v,action:async()=>{await storeSetting('appearance',v);button.textContent=v;document.documentElement.style.colorScheme=v==='System'?'light dark':v.toLowerCase();}})));return;}
    if(button.getAttribute('aria-haspopup')||/January|English|Default|Enabled|Disabled/.test(text)){toast('This setting has not been implemented in the local copy.');return;}
   }
  }catch(err){toast(err.message);}
 });
 document.addEventListener('submit',async e=>{
  if(e.target.closest('.auth-box,.local-dialog,.local-project-overlay'))return;e.preventDefault();try{const data=new FormData(e.target),f=Object.fromEntries(data);if(!e.target.reportValidity())return;
   if(route().endsWith('/api-keys/new')){const key=await api('/api/keys','POST',{name:f.label,permissions:f.selectedScope==='selectScope'?data.getAll('permissions'):['read','create','write']});modal('Personal API key','<p>Copy this key now. You won’t be able to see it again.</p><input aria-label="API key" readonly value="'+esc(key.token)+'"><button type="button" data-copy-key>Copy key</button>','Done',()=>{location.href='/qqq153/settings/account/security';},true);$('[data-copy-key]',dialog).onclick=()=>copy(key.token);return;}
   if(route().endsWith('/api/webhooks/new')){await api('/api/entities/webhooks','POST',{title:f.label,url:f.url,secret:f.secret,resourceTypes:data.getAll('resourceTypes')});location.href='/qqq153/settings/api';return;}
   if(route().endsWith('/account/profile')){await api('/api/profile','PATCH',{name:f.name});await storeSetting('title',f.title||'');await storeSetting('displayName',f.displayName||'');toast('Profile updated');return;}
   await api('/api/forms','POST',{kind:route(),...f});toast('Submitted');}catch(err){toast(err.message);}
 });
 let lastKey='';document.addEventListener('keydown',async e=>{
  if(await publicPopupKeydown(e))return;
  if(e.target.matches('[data-record]')&&['Enter',' '].includes(e.key)){e.preventDefault();e.target.click();return;}
  if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'&&!route().startsWith('/qqq153')){e.preventDefault();publicSearch();return;}
  if(e.target.matches('[aria-label="Editable code diff — press Space to edit"]')&&[' ','Enter'].includes(e.key)){e.preventDefault();$('textarea',e.target)?.focus();return;}
  if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='i'&&!dialog&&!currentMenu&&!e.target.isContentEditable&&!e.target.matches('input,textarea,[contenteditable=true]')&&$('[data-local-issue-list]')){e.preventDefault();await detailsPanel();return;}
  if(e.key==='Escape'){if(publicFeatureDialog){e.preventDefault();closePublicFeatureDialog();return;}if(currentMenu){closeMenu();return;}if(dialog){closeDialog();return;}if(advancedPanel){advancedPanel.close();return;}restoreHome();return;}
  if(e.key==='Tab'&&dialog){const all=$$('button,input,textarea,select,a,[contenteditable=true]',dialog).filter(x=>!x.disabled&&x.getClientRects().length);if(e.shiftKey&&document.activeElement===all[0]){e.preventDefault();all.at(-1)?.focus();}else if(!e.shiftKey&&document.activeElement===all.at(-1)){e.preventDefault();all[0]?.focus();}}
  if(dialog||currentMenu||advancedPanel||e.target.isContentEditable||e.target.matches('input,textarea,select,[contenteditable=true]'))return;
  await appReady;if(!sessionInfo?.authenticated)return;
  if(e.altKey&&e.shiftKey&&e.key.toLowerCase()==='q'){for(const key of Object.keys(sessionStorage))if(key.startsWith('linear-issue-scratch:'))sessionStorage.removeItem(key);await api('/api/auth/logout','POST',{});location.href='/login';return;}
  if(e.altKey&&!e.shiftKey&&e.key.toLowerCase()==='c'){e.preventDefault();issueProperties.editor('issue',null,{pickTemplate:true});return;}
   if(currentIssue&&e.shiftKey&&e.key.toLowerCase()==='h'){e.preventDefault();issueProperties.reminders($('button[aria-label="Issue options"]'));return;}
   if(currentIssue&&e.shiftKey&&e.key.toLowerCase()==='d'){e.preventDefault();issueProperties.calendar();return;}
  if(currentIssue&&(e.ctrlKey||e.metaKey)&&e.shiftKey&&e.key.toLowerCase()==='o'){e.preventDefault();issueDialog(currentIssue.id);return;}
  if(e.key.toLowerCase()==='f'){const button=$('main button[aria-label="Add filter"]');if(button){e.preventDefault();button.click();}return;}
  if(e.key.toLowerCase()==='c'){e.preventDefault();issueDialog();}if(e.key==='/'){e.preventDefault();location.href='/qqq153/search';}if(lastKey==='g'&&e.key==='s')location.href='/qqq153/settings/account/preferences';if(e.key==='?')help(null);lastKey=e.key;setTimeout(()=>lastKey='',900);
 });
 addEventListener('popstate',()=>{if(workspaceSearch?.active()){workspaceSearch.popstate();return;}if(projectLabelPage?.ownsRoute()){projectLabelPage.popstate();return;}if(!filterTools)return;try{if(!loadFilterURL()){filter={};advancedState={enabled:false,expression:{or:[]}};}advancedPanel?.close();renderIssues();renderDirectory();projectDetail?.render().catch(e=>toast(e.message));}catch(e){toast(e.message);}});
 addEventListener('pageshow',async e=>{if(e.persisted&&route().startsWith('/qqq153')){const s=await api('/api/session');if(!s.authenticated)location.replace('/login?redirectTo='+encodeURIComponent(route()));}});
 async function init(){
  preparePublic();
  if(['/login','/signup'].includes(route()))renderAuth();
  if(route().startsWith('/docs')){const theme=localStorage.getItem('linear-docs-theme');if(theme){document.documentElement.dataset.theme=theme;document.documentElement.style.colorScheme=theme;}}
  sessionInfo=await api('/api/session');
  if(['/login','/signup'].includes(route())){if(sessionInfo.authenticated){location.replace(teamPath('/qqq153/team/QQQ/active'));return;}renderAuth();if(new URLSearchParams(location.search).has('passkey')){try{await passkey();}catch(e){renderAuth(e.message);}}return;}
  if(route().startsWith('/qqq153')){if(!sessionInfo.authenticated){location.replace('/login?redirectTo='+encodeURIComponent(route()));return;}[filterTools,fieldTools,advancedTools]=await Promise.all([import('/static/filter-expression.js'),import('/static/filter-fields.js'),import('/static/advanced-filters.js')]);const {createIssueAttachments}=await import('/static/issue-attachments.js');issueAttachments=createIssueAttachments({api,toast,modal,closeDialog,refresh,getIssue:()=>currentIssue});const {createRecurringIssues}=await import('/static/recurring-issues.js');recurringIssues=createRecurringIssues({api,menu,modal,closeDialog,toast,refresh,getState:()=>state,getAccount:()=>sessionInfo.account,issueURL,attachments:issueAttachments});const {createIssueTemplates}=await import('/static/issue-templates.js');issueTemplates=createIssueTemplates({api,menu,modal,closeDialog,toast,refresh,getState:()=>state,getAccount:()=>sessionInfo.account,attachments:issueAttachments});const {createDocumentTemplates}=await import('/static/document-templates.js');documentTemplates=createDocumentTemplates({api,menu,modal,closeDialog,toast,refresh,getState:()=>state});const {createDocumentManager}=await import('/static/documents.js');documentManager=createDocumentManager({api,menu,modal,closeDialog,closeMenu,copy,toast,refresh,issueURL,getAccount:()=>sessionInfo.account,getState:()=>state});const documentStyle=document.createElement('link');documentStyle.rel='stylesheet';documentStyle.href='/static/documents.css';document.head.append(documentStyle);const {createIssueProperties}=await import('/static/issue-properties.js');issueProperties=createIssueProperties({api,menu,modal,closeDialog,closeMenu,refresh,copy,toast,issueURL,addDocument:()=>documentManager.create({kind:'issues',id:currentIssue.id}),getIssue:()=>currentIssue,getState:()=>state,getAccount:()=>sessionInfo.account,setDialog:o=>dialog=o,attachments:issueAttachments});const issueStyle=document.createElement('link');issueStyle.rel='stylesheet';issueStyle.href='/static/issue-properties.css';document.head.append(issueStyle);const {createProjectLabels}=await import('/static/project-labels.js');projectLabels=createProjectLabels({api,menu,modal,closeDialog,closeMenu,toast,refresh});const {createProjectLabelPage}=await import('/static/project-label-page.js');projectLabelPage=createProjectLabelPage({api,menu,modal,closeDialog,closeMenu,toast,copy,refresh,getState:()=>state,getAccount:()=>sessionInfo.account,projectDialog,labelActions:projectLabels});const {createProjectDetail}=await import('/static/project-detail.js');projectDetail=createProjectDetail({api,menu,modal,closeDialog,closeMenu,copy,toast,refresh,getState:()=>state,getAccount:()=>sessionInfo.account,newIssue:defaults=>issueProperties.editor('issue',null,defaults),createDocument:parent=>documentManager.create(parent),issueURL,getFilteredIssues:filteredIssues,renderFilters:renderAdvancedSummary});const {createViewManager}=await import('/static/views.js');viewManager=createViewManager({api,menu,modal,closeDialog,closeMenu,copy,toast,refresh,getState:()=>state,getExpression:filterURLExpression});const {createWorkspaceSearch}=await import('/static/workspace-search.js');workspaceSearch=createWorkspaceSearch({getState:()=>state,issueURL});const saved=await api('/api/settings?route='+encodeURIComponent(route()));displaySettings=saved;filter=saved.filters||{};advancedState=saved['advanced-filter']||{enabled:false,expression:{or:[]}};initializeViewDraft();await initializeSavedView();if(new URLSearchParams(location.search).has('filter')&&!projectLabelPage?.ownsRoute())loadFilterURL();if(advancedState.enabled)await advancedTools.loadFilterTemplates();if(new URLSearchParams(location.search).has('status'))filter.status=new URLSearchParams(location.search).get('status');board=saved.layout==='Board';ordering=saved.ordering||'Priority';groupBy=saved.grouping||'Status';const {createWorkspaceUI}=await import('/static/workspaces.js');workspaceUI=createWorkspaceUI({api,menu,modal,closeDialog,toast,refresh,getState:()=>state,getSession:()=>sessionInfo,activeTeam});await refresh();if(inboxRoute())setInterval(()=>refresh().catch(err=>toast(err.message)),30000);if(saved['details-open']&&$('[data-local-issue-list]'))await detailsPanel(true);bindSettings();const preferences=route().endsWith('/account/preferences')?saved:await api('/api/settings?route='+encodeURIComponent('/qqq153/settings/account/preferences'));applyInterfacePreferences(preferences);sidebarPreferences=preferences.sidebar||{};sidebarTemplates=await (await fetch('/static/sidebar-links.json')).json();sidebarReady=true;navigationFavorites=Array.isArray(preferences['navigation-favorites'])?preferences['navigation-favorites'].filter(x=>x&&typeof x.path==='string'&&x.path.startsWith('/qqq153/')&&typeof x.title==='string'):[];navigationFavoriteMarkup=await fetch('/static/project-label-page/favorite-group.html').then(r=>r.text());applySidebar();renderNavigationFavorites();if(preferences['combobox-5'])await applyAppTheme(preferences['combobox-5']);await securitySettings();if(route().includes('/settings/account/security')){const {bindSigningKeys}=await import('/static/signing-keys.js');await bindSigningKeys({api,modal,closeDialog,toast});}keyPermissions();await webhookSettings();if(route().includes('/settings/import-export')&&state.workspace.role==='admin'){const {setupImports}=await import('/static/issue-imports.js');await setupImports({api,modal,closeDialog,toast,getState:()=>state});}if(new URLSearchParams(location.search).has('new'))issueProperties.editor('issue',null,issueURLDefaults());if(new URLSearchParams(location.search).has('register-passkey')){history.replaceState(null,'',location.pathname);await passkey(true);}}
 }
 appReady=init().then(()=>{document.documentElement.dataset.linearReady='true';}).catch(e=>toast(e.message));
})();
