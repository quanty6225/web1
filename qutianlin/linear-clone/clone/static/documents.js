import {mediaAttributes,hydrateDocumentMedia} from '/static/document-media.js';
import {calloutColors} from '/static/document-color-picker.js';
import {blockAttributes,documentBodyHTML,hydrateDocumentBlocks} from '/static/document-blocks.js';
import {bindDocumentFormatting} from '/static/document-formatting.js';
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const route=id=>'/qqq153/document/'+encodeURIComponent(id);
const label=b=>(b.getAttribute('aria-label')||b.innerText||'').trim();
export function cleanPaste(value){
 const template=document.createElement('template');template.innerHTML=value;template.content.querySelectorAll('[data-document-control]').forEach(node=>node.remove());
 const allowed=new Set(['P','BR','STRONG','B','EM','I','U','S','STRIKE','H1','H2','H3','H4','BLOCKQUOTE','PRE','CODE','UL','OL','LI','HR','A','IMG','TABLE','THEAD','TBODY','TR','TH','TD','SPAN','DIV','VIDEO','AUDIO','SMALL']);
 for(const node of [...template.content.querySelectorAll('*')]){
  if(['SCRIPT','STYLE','IFRAME','OBJECT','EMBED','SVG','MATH','LINK','META'].includes(node.tagName)){node.remove();continue;}
  if(!allowed.has(node.tagName)){node.replaceWith(...node.childNodes);continue;}
  for(const name of ['href','src']){const value=node.getAttribute(name);if(value&&/^(https?:|\/\/)/i.test(value)){try{const url=new URL(value,location.href);if(url.origin===location.origin)node.setAttribute(name,url.pathname+url.search+url.hash);}catch{}}}
  const attributes=new Map([...node.attributes].map(attribute=>[attribute.name,attribute.value])),semantics={...blockAttributes(node.tagName,attributes),...mediaAttributes(node.tagName,attributes)};const href=node.getAttribute('href'),src=node.getAttribute('src'),alt=node.getAttribute('alt');for(const attribute of [...node.attributes])node.removeAttribute(attribute.name);for(const [name,value] of Object.entries(semantics))node.setAttribute(name,value);
  if(node.tagName==='A'&&href){if(href.startsWith('/')&&!href.startsWith('//')&&!href.includes('\\'))node.setAttribute('href',href);else if(/^(https?:|mailto:)/i.test(href))node.setAttribute('href','/external?target='+encodeURIComponent(btoa(unescape(encodeURIComponent(href)))));}
  if(node.tagName==='IMG'){if(!(src?.startsWith('/static/assets/')||/^\/api\/uploads\/upload_[a-f0-9]{32}$/.test(src||''))||src.includes('..')||src.includes('\\')){node.remove();continue;}node.setAttribute('src',src);node.setAttribute('alt',alt||'');}
 }
 return template.innerHTML;
}

export async function chooseDocumentIcon({modal,closeDialog,toast,onSelect,color,onColor}){
  let iconItems=await fetch('/static/project-create/icons.json').then(r=>r.json());let emojiItems=await fetch('/static/document-editor/emojis.json').then(r=>r.json());let tab='Icons';
  const overlay=modal('Document icon','<div role="tablist"><button type="button" role="tab" aria-selected="true">Icons</button><button type="button" role="tab" aria-selected="false">Emojis</button></div><input aria-label="Search icons" placeholder="Search icons…"><div class="document-icon-grid"></div>',null,null,true),input=$('input',overlay),grid=$('.document-icon-grid',overlay);
  if(onColor){const colors=await calloutColors(grid.parentElement,{value:color,onChange:onColor});input.before(colors);}
  const draw=()=>{grid.replaceChildren();const items=tab==='Icons'?iconItems:emojiItems;for(const item of items.filter(x=>x.name.toLowerCase().includes(input.value.toLowerCase()))){const button=document.createElement('button');button.type='button';button.setAttribute('aria-label',item.name);if(tab==='Icons')button.innerHTML=item.svg;else button.textContent=item.emoji;button.onclick=async()=>{try{await onSelect(tab==='Icons'?item.name:'emoji:'+item.emoji);closeDialog();}catch(e){toast(e.message);}};grid.append(button);}};
  $$('[role=tab]',overlay).forEach(button=>button.onclick=()=>{tab=button.textContent;$$('[role=tab]',overlay).forEach(b=>b.setAttribute('aria-selected',String(b===button)));input.value='';input.setAttribute('aria-label',tab==='Icons'?'Search icons':'Search emojis');input.placeholder=tab==='Icons'?'Search icons…':'Search emojis…';draw();});input.oninput=draw;draw();
 }

export function createDocumentManager(env){
 const {api,menu,modal,closeDialog,closeMenu,copy,toast,refresh,issueURL}=env;
 let doc=null,title=null,body=null,timer=null,saveTail=Promise.resolve(),bound=false,problem=null;
 let iconItems=null,showResolved=false;const activeDiagramComments=new Set(),activeImageComments=new Set();
 const documentId=()=>location.pathname.match(/^\/qqq153\/document\/([^/]+)/)?.[1];
 const account=()=>env.getAccount(),state=()=>env.getState();
 const snapshot=()=>({title:title?.innerText.trim()||'New document',content_html:body?documentBodyHTML(body):''});
 let lastSaved=null;
 const dirty=()=>doc&&title&&JSON.stringify(snapshot())!==lastSaved;
 function error(message){if(problem){problem.textContent=message;problem.hidden=!message;}}
 function paintMetadata(){
  if(!doc)return;document.title=doc.title+' · Linear';
  let heading=$('header [data-document-heading]');if(!heading){heading=$$('header span').find(x=>!x.children.length&&x.textContent==='New document');if(heading)heading.dataset.documentHeading='true';}if(heading)heading.textContent=doc.title;
  const icon=$('[aria-label="Document icon"]');if(icon&&doc.icon){if(doc.icon.startsWith('emoji:'))icon.textContent=doc.icon.slice(6);else if(iconItems){const item=iconItems.find(x=>x.name===doc.icon);if(item)icon.innerHTML=item.svg;}else fetch('/static/project-create/icons.json').then(r=>r.json()).then(items=>{iconItems=items;paintMetadata();});}
  const metadata=$$('button').find(b=>label(b).startsWith('Document display options and metadata'));
  if(metadata){const text='Edited '+new Date(doc.updated_at*1000).toLocaleDateString('en-US',{month:'short',day:'numeric'});metadata.setAttribute('aria-label','Document display options and metadata; '+text);const leaf=$$('span',metadata).find(x=>!x.children.length&&x.textContent.trim());if(leaf)leaf.textContent=text;else metadata.textContent=text;}
  const favorite=$('header button[aria-label="Add to favorites"],header button[aria-label="Remove from favorites"]');if(favorite){favorite.setAttribute('aria-label',doc.favorite?'Remove from favorites':'Add to favorites');favorite.setAttribute('aria-checked',String(doc.favorite));}
  const parent=$('header a[href*="/issue/"],header [data-document-parent]');if(parent){parent.dataset.documentParent='true';const location=doc.parent;parent.hidden=!location;if(location?.kind==='issues'){const issue=state().issues.find(x=>x.id===location.id);parent.textContent=location.id;parent.href=issue?issueURL(issue):'/qqq153/team/QQQ/all';}else if(location?.kind==='teams'){parent.textContent=state().teams.find(t=>t.id===location.id)?.title||location.id;parent.href='/qqq153/team/'+location.id+'/overview';}else if(location?.kind==='projects'){parent.textContent=state().projects.find(x=>x.id===location.id)?.title||'Projects';parent.href='/qqq153/project/'+encodeURIComponent(location.id)+'/overview';}}
  let apply=$('[data-apply-document-template]');const available=availableTemplates();if(!apply&&available.length&&title){apply=document.createElement('button');apply.type='button';apply.textContent='Template';apply.dataset.applyDocumentTemplate='';apply.className='document-template-trigger';const icon=$('[aria-label="Document icon"]');(icon?.parentElement||title.parentElement).append(apply);apply.onclick=e=>{e.stopPropagation();templateMenu(apply);};}if(apply)apply.hidden=!!body?.innerText.trim()||!!body?.querySelector('img,audio,video,table,hr,pre,ul,ol,[data-callout],.collapsible-section')||!available.length;
  let reminder=$('[data-document-reminder]');if(!reminder&&title){reminder=document.createElement('button');reminder.dataset.documentReminder='';reminder.className='document-reminder';title.before(reminder);reminder.onclick=()=>reminders(reminder);}if(reminder){reminder.hidden=!doc.remind_at;reminder.textContent=doc.remind_at?'Remind me · '+new Date(doc.remind_at*1000).toLocaleString('en-US'):'';}
  let authors=$('[data-document-authors]');if(!authors&&body){authors=document.createElement('div');authors.dataset.documentAuthors='';authors.className='document-authors';body.parentElement.after(authors);}if(authors){authors.hidden=!doc.show_authors;authors.textContent=doc.last_editor;}
 }
 function save(){
  clearTimeout(timer);timer=null;if(!doc||!title)return saveTail;
  const value=snapshot(),serialized=JSON.stringify(value);if(serialized===lastSaved)return saveTail;
  saveTail=saveTail.catch(()=>{}).then(async()=>{const saved=await api('/api/entities/documents/'+doc.id,'PATCH',{...value,revision:doc.revision});doc=saved;lastSaved=serialized;error('');paintMetadata();return saved;}).catch(e=>{error(e.message);throw e;});return saveTail;
 }
 async function flush(){await save();await saveTail;}
 async function mutate(patch){await flush();doc=await api('/api/entities/documents/'+doc.id,'PATCH',{...patch,revision:doc.revision});paintMetadata();await refresh();return doc;}
 function schedule(){paintMetadata();clearTimeout(timer);timer=setTimeout(()=>save().catch(()=>{}),500);}
 function render(){
  const id=documentId();if(!id)return;const fresh=state().documents?.find(x=>x.id===id);if(!fresh)return;
  if(!doc||!dirty())doc=fresh;
  title=$('[aria-label="Document title"]');body=$('[aria-label="Document content"]');if(!title||!body)return;
  if(!bound){
   title.textContent=doc.title==='New document'?'':doc.title;body.innerHTML=doc.content_html||'<p><br></p>';lastSaved=JSON.stringify(snapshot());
   for(const element of [title,body]){element.contentEditable='true';element.setAttribute('aria-readonly','false');}
   problem=document.createElement('p');problem.role='alert';problem.className='document-save-error';problem.hidden=true;body.parentElement.after(problem);
   for(const element of [title,body]){element.addEventListener('input',schedule);element.addEventListener('blur',()=>save().catch(()=>{}));}
   title.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();body.focus();}});
   body.addEventListener('paste',e=>{if(!e.clipboardData||e.clipboardData.files.length||getSelection()?.anchorNode?.parentElement?.closest('pre'))return;e.preventDefault();const rich=e.clipboardData.getData('text/html');if(rich)document.execCommand('insertHTML',false,cleanPaste(rich));else document.execCommand('insertText',false,e.clipboardData.getData('text/plain'));hydrateDocumentBlocks(body);schedule();});
   addEventListener('beforeunload',event=>{if(dirty()){event.preventDefault();event.returnValue='';}});
   document.addEventListener('click',e=>{const a=e.target.closest('a[href]');if(!a||a.hasAttribute('download')||a.pathname.startsWith('/api/uploads/')||!dirty()||!documentId())return;e.preventDefault();flush().then(()=>location.href=a.href).catch(()=>{});},true);
   bindDocumentFormatting({body,menu,modal,closeDialog,changed:schedule,comment,diagramComments:{get:id=>({threads:(doc?.comments||[]).filter(item=>item.diagram_id===id&&!item.parent&&!item.resolved),active:activeDiagramComments.has(id)}),add:(quote,id)=>comment(quote,null,id),toggle:id=>{if(activeDiagramComments.has(id))activeDiagramComments.delete(id);else activeDiagramComments.add(id);renderComments();hydrateDocumentBlocks(body);}},imageComments:{get:id=>({threads:(doc?.comments||[]).filter(item=>item.image_id===id&&!item.parent&&!item.resolved),active:activeImageComments.has(id)}),add:image=>comment(image.alt||'Image',null,null,image),toggle:id=>{if(activeImageComments.has(id))activeImageComments.delete(id);else activeImageComments.add(id);renderComments();hydrateDocumentMedia(body);}},toast,targetLabel:'document',replaceTitle:value=>{title.textContent=value;},chooseIcon:(onSelect,options={})=>chooseDocumentIcon({modal,closeDialog,toast,onSelect,...options})});if(dirty())schedule();
   document.addEventListener('keydown',event=>{if(event.key==='Escape'&&$('.document-sidebar-open'))mobileMenu($('header [aria-label="Menu"]'));});
   bound=true;
  }
  hydrateDocumentBlocks(body);hydrateDocumentMedia(body);paintMetadata();renderFavorites();renderComments();
 }
 function availableTemplates(){const parent=doc?.parent;if(!parent)return (state().document_templates||[]).slice().sort((a,b)=>Number(!a.team)-Number(!b.team)||a.title.localeCompare(b.title));let teams=parent.kind==='teams'?[parent.id]:parent.kind==='projects'?(state().projects.find(x=>x.id===parent.id)?.teams||[]):[state().issues.find(x=>x.id===parent.id)?.team||'QQQ'];return (state().document_templates||[]).filter(x=>!x.team||teams.includes(x.team)).sort((a,b)=>Number(!a.team)-Number(!b.team)||a.title.localeCompare(b.title));}
 function templateMenu(anchor){menu(anchor,availableTemplates().map(item=>({text:item.title,action:async()=>{await flush();doc=await api('/api/documents/'+encodeURIComponent(doc.id)+'/template','POST',{template_id:item.id,revision:doc.revision});title.textContent=doc.title;body.innerHTML=doc.content_html||'<p><br></p>';lastSaved=JSON.stringify(snapshot());await refresh();}})));}
 async function create(parent=null){const created=await api('/api/entities/documents','POST',{title:'New document',content_html:'',parent});location.href=route(created.id);}
 async function rename(){await flush();const overlay=modal('Rename document','<input name="title" aria-label="Document name" value="'+escape(doc.title)+'" required>','Save',async f=>{await mutate({title:f.get('title').trim()});title.textContent=doc.title;lastSaved=JSON.stringify(snapshot());closeDialog();},true);$('input',overlay).select();}
 async function duplicate(){await flush();const result=await api('/api/entities/documents','POST',{title:doc.title+' (copy)',content_html:doc.content_html,parent:doc.parent,icon:doc.icon});location.href=route(result.id);}
 async function history(){
  await flush();const versions=doc.history||[];
  if(!versions.length){modal('Restore version for '+doc.title,'<p>There is no history yet.</p>',null,null);return;}
  const rows=[{title:doc.title,content_html:doc.content_html,at:doc.content_updated_at,author:doc.last_editor,current:true},...versions.slice().reverse()];let selected=0;
  const overlay=modal('Restore version for '+doc.title,'<div class="document-history"><nav></nav><article></article></div>','Restore version',async()=>{await mutate({title:rows[selected].title,content_html:rows[selected].content_html});title.textContent=doc.title;body.innerHTML=doc.content_html;hydrateDocumentBlocks(body);hydrateDocumentMedia(body);lastSaved=JSON.stringify(snapshot());closeDialog();});
  function show(){const item=rows[selected];$('article',overlay).innerHTML='<h2>'+escape(item.title)+'</h2>'+item.content_html;const submit=$('[type=submit]',overlay);submit.disabled=!!item.current;submit.setAttribute('aria-label',item.current?'This is the current version, you cannot restore it':'Restore version');$$('nav button',overlay).forEach((b,n)=>b.setAttribute('aria-pressed',String(n===selected)));}
  rows.forEach((item,n)=>{const b=document.createElement('button');b.type='button';b.textContent=new Date(item.at*1000).toLocaleString('en-US')+' · '+item.author+(item.current?' · Current':'');b.onclick=()=>{selected=n;show();};$('nav',overlay).append(b);});show();
 }
 function markdown(){
  const root=document.createElement('div');root.innerHTML=doc.content_html;
  function content(node){if(node.nodeType===Node.TEXT_NODE)return node.textContent;if(node.nodeType!==Node.ELEMENT_NODE)return '';const inner=[...node.childNodes].map(content).join('');switch(node.tagName){case 'BR':return '\n';case 'STRONG':case 'B':return '**'+inner+'**';case 'EM':case 'I':return '*'+inner+'*';case 'CODE':return '`'+inner+'`';case 'PRE':return '\n```\n'+node.textContent+'\n```\n';case 'A':return '['+inner+']('+new URL(node.getAttribute('href')||'#',location.origin).href+')';case 'IMG':return '!['+(node.getAttribute('alt')||'')+']('+new URL(node.getAttribute('src'),location.origin).href+')';case 'LI':return (node.dataset.type==='todo_item'?'* ['+(node.dataset.done==='true'?'x':' ')+'] ':'* ')+inner.trim()+'\n';case 'BLOCKQUOTE':return '\n'+inner.trim().split('\n').map(x=>'> '+x).join('\n')+'\n';case 'H1':case 'H2':case 'H3':case 'H4':return '\n'+'#'.repeat(+node.tagName[1])+' '+inner+'\n\n';case 'P':case 'DIV':return inner+'\n\n';case 'HR':return '\n---\n';default:return inner;}}
  return [...root.childNodes].map(content).join('').trim()+'\n';
 }
 async function copyAction(kind){await flush();const url=location.origin+route(doc.id);return copy(kind==='Copy URL'?url:kind==='Copy title'?doc.title:kind==='Copy title as link'?'['+doc.title+']('+url+')':markdown());}
 async function downloadMarkdown(){await flush();const blob=new Blob([markdown()],{type:'text/markdown;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=doc.title.replace(/[\\/:*?"<>|]/g,'-')+'.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 async function downloadPDF(){await flush();const response=await fetch('/api/documents/'+encodeURIComponent(doc.id)+'/pdf');if(!response.ok)throw Error('Could not download this document.');const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download=doc.title.replace(/[\\/:*?"<>|]/g,'-')+'.pdf';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 function move(anchor){menu(anchor,state().teams.filter(t=>!t.archived).map(t=>({text:t.title,action:()=>mutate({parent:{kind:'teams',id:t.id}})})),'My teams');}
 function pin(anchor){menu(anchor,state().teams.filter(t=>!t.archived).map(t=>({text:(doc.pinned_teams?.includes(t.id)?'✓ ':'')+t.title,action:()=>mutate({pinned_teams:doc.pinned_teams?.includes(t.id)?doc.pinned_teams.filter(id=>id!==t.id):[...(doc.pinned_teams||[]),t.id]})})));}
 function subscribers(anchor){menu(anchor,[account().email_normalized,'linear','agent'].map(value=>({text:(doc.subscribers?.includes(value)?'✓ ':'')+(value==='linear'?'Linear':value==='agent'?'Agent':account().display_name),action:()=>mutate({subscribers:doc.subscribers?.includes(value)?doc.subscribers.filter(x=>x!==value):[...(doc.subscribers||[]),value]})})),'Search users…');}
 function metadata(anchor){menu(anchor,[{text:(doc.show_authors?'✓ ':'')+'Show author names',action:()=>mutate({show_authors:!doc.show_authors})},{text:'Owned by · '+account().display_name,action:()=>menu(anchor,[{text:account().display_name,action:()=>mutate({owner:account().email_normalized})}])},{text:'Last edit by · '+doc.last_editor+' · '+new Date(doc.content_updated_at*1000).toLocaleString('en-US'),action:history},{text:'Show document history',action:history}]);}
 async function icons(anchor){await chooseDocumentIcon({modal,closeDialog,toast,onSelect:icon=>mutate({icon})});}

 function options(anchor){menu(anchor,[{text:'Move to ›',action:()=>move(anchor)},{text:'Pin to team ›',action:()=>pin(anchor)},{text:'Duplicate',action:duplicate},{text:'Rename…',action:rename},{text:doc.favorite?'Unfavorite':'Favorite',action:()=>mutate({favorite:!doc.favorite})},{text:'Copy ›',action:()=>menu(anchor,['Copy URL','Copy title','Copy title as link','Copy content as Markdown'].map(text=>({text,action:()=>copyAction(text)})))},{text:'Download ›',action:()=>menu(anchor,[{text:'Download as markdown',action:downloadMarkdown},{text:'Download as PDF',action:downloadPDF}])},{text:'Remind me ›',action:()=>reminders(anchor)},{text:(doc.show_authors?'✓ ':'')+'Show author names',action:()=>mutate({show_authors:!doc.show_authors})},{text:'Show document history',action:history},{text:'Delete',action:()=>modal('Delete document','<p>Delete '+escape(doc.title)+'?</p>','Delete',async()=>{await api('/api/entities/documents/'+doc.id,'DELETE');location.href=doc.parent?.kind==='issues'?issueURL(state().issues.find(x=>x.id===doc.parent.id)):'/qqq153/team/QQQ/overview';},true)}]);}
 async function handleClick(button){if(!documentId()||!doc)return false;const text=label(button);if(text==='Menu'){mobileMenu(button);}else if(text==='Document options'){await flush();options(button);}else if(text.startsWith('Document display options and metadata')){await flush();metadata(button);}else if(['Add to favorites','Remove from favorites'].includes(text))await mutate({favorite:!doc.favorite});else if(text==='Copy document URL')await copyAction('Copy URL');else if(text==='Change document subscribers')subscribers(button);else if(text==='Document icon')await icons(button);else return false;return true;}
 function renderRelated(){
  document.querySelectorAll('[data-related-documents]').forEach(x=>x.remove());const id=location.pathname.match(/\/issue\/([^/]+)/)?.[1];if(!id)return;const documents=(state().documents||[]).filter(x=>x.parent?.kind==='issues'&&x.parent.id===id);const description=$('[aria-label="Issue description"]');if(!description||!documents.length)return;const root=document.createElement('section');root.dataset.relatedDocuments='';root.className='related-documents';for(const item of documents){const a=document.createElement('a');a.href=route(item.id);a.textContent=item.title;root.append(a);}description.parentElement.after(root);
 }
 function renderFavorites(){
  document.querySelectorAll('[data-document-favorite]').forEach(x=>x.remove());const items=(state().documents||[]).filter(x=>x.favorite),button=$('button[aria-controls="sidebarFavorites"]'),section=button?.closest('[data-sidebar-section]');if(!button||!section)return;let list=$('#sidebarFavorites',section);if(!list){list=document.createElement('div');list.id='sidebarFavorites';button.parentElement.after(list);}if(items.length){button.disabled=false;section.parentElement.inert=false;section.parentElement.style.height='auto';section.parentElement.style.opacity='1';section.parentElement.style.transform='none';}
  for(const item of items){const a=document.createElement('a');a.dataset.documentFavorite='';a.className='issue-favorite-link';a.href=route(item.id);a.textContent=item.title;list.append(a);}
 }
 function reminderCalendar(){
  const today=new Date();today.setHours(0,0,0,0);let selected=new Date(today);selected.setDate(selected.getDate()+1);selected.setHours(9);let month=new Date(today.getFullYear(),today.getMonth(),1);
  const overlay=modal('Remind me about this document on','<div class="issue-calendar-nav"><button type="button" data-prev aria-label="Previous month">‹</button><button type="button" data-next aria-label="Next month">›</button></div><div class="issue-calendars"></div>','Apply',async()=>{await mutate({remind_at:Math.floor(+selected/1000)});closeDialog();});
  const draw=()=>{const root=$('.issue-calendars',overlay);root.replaceChildren();$('[data-prev]',overlay).disabled=month<=today;
   for(let n=0;n<2;n++){const date=new Date(month.getFullYear(),month.getMonth()+n,1),box=document.createElement('section');box.innerHTML='<h3>'+date.toLocaleDateString('en-US',{month:'long',year:'numeric'})+'</h3><div class="issue-days">'+['Su','Mo','Tu','We','Th','Fr','Sa'].map(x=>'<span>'+x+'</span>').join('')+'</div>';const grid=$('.issue-days',box);for(let j=0;j<date.getDay();j++)grid.append(document.createElement('span'));
    for(let j=1;j<=new Date(date.getFullYear(),date.getMonth()+1,0).getDate();j++){const value=new Date(date.getFullYear(),date.getMonth(),j,9),button=document.createElement('button');button.type='button';button.textContent=j;button.disabled=value<=new Date(+today+86400000-1);button.setAttribute('aria-label',value.toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric'}));button.setAttribute('aria-pressed',String(value.toDateString()===selected.toDateString()));button.onclick=()=>{selected=value;draw();};grid.append(button);}root.append(box);
   }
  };$('[data-prev]',overlay).onclick=()=>{month.setMonth(month.getMonth()-1);draw();};$('[data-next]',overlay).onclick=()=>{month.setMonth(month.getMonth()+1);draw();};draw();
 }
 function reminders(anchor){
  const now=new Date(),next=days=>{const value=new Date(now);value.setDate(value.getDate()+days);value.setHours(9,0,0,0);return value;};
  const choices=[['An hour from now',new Date(+now+3600000)],['In 3 hours',new Date(+now+10800000)],['Tomorrow',next(1)],['Next week',next((8-now.getDay())%7||7)],['A month from now',(()=>{const value=next(0);value.setMonth(value.getMonth()+1);return value;})()]];
  const choose=async value=>mutate({remind_at:Math.floor(+value/1000)});
  const box=menu(anchor,[...choices.map(([text,value])=>({text,action:()=>choose(value)})),{text:'Custom…',action:reminderCalendar},...(doc.remind_at?[{text:'Cancel reminder',action:()=>mutate({remind_at:null})}]:[])],'Try: 4 pm, 2 days, in 5 weeks…');
  const input=$('input',box),custom=document.createElement('button');custom.role='menuitem';custom.hidden=true;box.append(custom);
  input.addEventListener('input',()=>{const text=input.value.trim().toLowerCase();let parsed=null;const duration=text.match(/^(?:in |for )?(\d+)\s+(minutes?|hours?|days?|weeks?|months?)$/),clock=text.match(/^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$/);
   if(duration){parsed=new Date(now);const value=+duration[1],unit=duration[2];if(unit.startsWith('month'))parsed.setMonth(parsed.getMonth()+value);else parsed=new Date(+now+value*(unit.startsWith('week')?604800000:unit.startsWith('day')?86400000:unit.startsWith('hour')?3600000:60000));}
   else if(clock&&+clock[1]>=1&&+clock[1]<=12&&+(clock[2]||0)<60){parsed=new Date(now);parsed.setHours(+clock[1]%12+(clock[3]==='pm'?12:0),+(clock[2]||0),0,0);if(parsed<=now)parsed.setDate(parsed.getDate()+1);}
   else if(text==='next quarter'){parsed=new Date(now.getFullYear(),Math.floor(now.getMonth()/3)*3+3,1,9);}
   else if(/^\d{4}-\d\d-\d\d|^[a-z]{3,9}\s+\d{1,2}/.test(text)){const value=new Date(text);if(Number.isFinite(+value))parsed=value;}
   custom.hidden=!parsed||!Number.isFinite(+parsed)||parsed<=now;if(!custom.hidden){custom.textContent=parsed.toLocaleString('en-US');custom.onclick=async()=>{closeMenu();try{await choose(parsed);}catch(error){toast(error.message);}};}
  });
 }
 async function writeComment(data,id=null){await flush();doc=await api('/api/documents/'+encodeURIComponent(doc.id)+'/comments'+(id?'/'+encodeURIComponent(id):''),id?'PATCH':'POST',data);await refresh();renderComments();}
 function comment(quote,parent=null,diagramId=null,image=null){
  modal(parent?'Reply':'Comment','<blockquote>'+(image?'<img class="document-comment-image" src="'+escape(image.getAttribute('src'))+'" alt="'+escape(quote)+'">':escape(quote))+'</blockquote><textarea name="body" aria-label="'+(parent?'Reply':'Comment')+'" required></textarea>','Submit comment',async form=>{if(diagramId)activeDiagramComments.add(diagramId);if(image)activeImageComments.add(image.dataset.imageId);await writeComment({body:form.get('body'),quote,parent,...(diagramId?{diagram_id:diagramId}:{}),...(image?{image_id:image.dataset.imageId}:{})});closeDialog();});
 }
 function renderComments(){
  if(!doc||!body)return;
  const comments=doc.comments||[];let section=$('[data-document-comments]');
  if(!comments.length){section?.remove();return;}
  if(!section){section=document.createElement('aside');section.dataset.documentComments='';section.className='document-comments';section.setAttribute('aria-label','Document comments');const toggle=document.createElement('button');toggle.dataset.resolvedComments='';toggle.onclick=()=>{showResolved=!showResolved;renderComments();};section.append(toggle);body.parentElement.after(section);}
  const toggle=$('[data-resolved-comments]',section);toggle.textContent=showResolved?'Hide resolved comments':'Show resolved comments';toggle.setAttribute('aria-pressed',String(showResolved));
  const threads=comments.filter(item=>!item.parent&&(showResolved||!item.resolved)),keep=new Set(threads.map(item=>item.id));
  for(const article of $$('[data-comment-thread]',section))if(!keep.has(article.dataset.commentThread))article.remove();
  for(const [index,thread] of threads.entries()){
   let article=$$('[data-comment-thread]',section).find(item=>item.dataset.commentThread===thread.id);
   if(!article){article=document.createElement('article');article.dataset.commentThread=thread.id;article.append(document.createElement('blockquote'));const entries=document.createElement('div');entries.dataset.commentEntries='';article.append(entries);const resolve=document.createElement('button'),reply=document.createElement('button');resolve.dataset.resolveComment='';reply.dataset.replyComment='';reply.textContent='Reply';article.append(resolve,reply);section.insertBefore(article,section.children[index+1]||null);}
   if(thread.diagram_id)article.dataset.diagramComment=thread.diagram_id;
   if(thread.image_id)article.dataset.imageComment=thread.image_id;
   article.hidden=!showResolved&&(thread.diagram_id&&!activeDiagramComments.has(thread.diagram_id)||thread.image_id&&!activeImageComments.has(thread.image_id));
   const quote=$('blockquote',article);
   if(thread.image_src){let preview=$('img',quote);if(!preview){preview=document.createElement('img');preview.className='document-comment-image';quote.replaceChildren(preview);}if(preview.getAttribute('src')!==thread.image_src)preview.src=thread.image_src;preview.alt=thread.quote;}
   else if(quote.textContent!==thread.quote)quote.textContent=thread.quote;
   const entries=$('[data-comment-entries]',article),items=[thread,...comments.filter(item=>item.parent===thread.id)];
   for(const entry of [...entries.children])if(!items.some(item=>item.id===entry.dataset.documentComment))entry.remove();
   for(const item of items){let entry=[...entries.children].find(entry=>entry.dataset.documentComment===item.id);if(!entry){entry=document.createElement('div');entry.dataset.documentComment=item.id;entry.append(document.createElement('small'),document.createElement('p'));entries.append(entry);}$('small',entry).textContent=item.author+' · '+new Date(item.created_at*1000).toLocaleString('en-US');$('p',entry).textContent=item.body;}
   const resolve=$('[data-resolve-comment]',article);resolve.textContent=thread.resolved?'Reopen comment':'Resolve comment';resolve.onclick=()=>writeComment({resolved:!thread.resolved},thread.id).catch(error=>toast(error.message));$('[data-reply-comment]',article).onclick=()=>comment(thread.quote,thread.id);
  }
 }

 function renderTeam(){
  $('[data-team-documents]')?.remove();const team=document.body.dataset.activeTeam||'QQQ';if(location.pathname!=='/qqq153/team/'+team+'/overview')return;const items=(state().documents||[]).filter(item=>item.parent?.kind==='teams'&&item.parent.id===team||item.pinned_teams?.includes(team));if(!items.length)return;
  const heading=$$('main *').find(e=>!e.children.length&&e.textContent.trim()==='Team resources');if(!heading)return;const root=document.createElement('section');root.dataset.teamDocuments='';root.className='related-documents';for(const item of items){const a=document.createElement('a');a.href=route(item.id);a.textContent=item.title;root.append(a);}heading.parentElement.after(root);
 }
 function mobileMenu(button){const surface=$('[data-sidebar-surface]');if(!surface)return;const open=!surface.classList.contains('document-sidebar-open');surface.classList.toggle('document-sidebar-open',open);button.setAttribute('aria-expanded',String(open));$('.document-sidebar-backdrop')?.remove();if(open){const backdrop=document.createElement('button');backdrop.className='document-sidebar-backdrop';backdrop.setAttribute('aria-label','Close navigation');backdrop.onclick=e=>{e.stopPropagation();mobileMenu(button);};surface.before(backdrop);}}

 return {create,render,renderRelated,renderFavorites,renderTeam,handleClick,flush,route};
}
