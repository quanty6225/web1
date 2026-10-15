// Source-backed project form. Business state is saved through the local entity API.
const $=(q,r=document)=>r.querySelector(q),$$=(q,r=document)=>[...r.querySelectorAll(q)];
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label=e=>(e.getAttribute('aria-label')||e.textContent).trim();
const dateString=d=>[d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');
const dateValue=s=>new Date(s+'T12:00:00');
const months=Array.from({length:12},(_,m)=>new Date(2026,m,1).toLocaleString('en-US',{month:'long'}));
export function dateLabel(value,precision='day'){
 if(!value)return '';
 const d=dateValue(value),y=d.getFullYear(),m=d.getMonth();
 return precision==='year'?String(y):precision==='half-year'?`H${Math.floor(m/6)+1} ${y}`:precision==='quarter'?`Q${Math.floor(m/3)+1} ${y}`:precision==='month'?`${months[m]} ${y}`:d.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
}
export function openProjectDatePicker({menu,closeMenu},anchor,field,values,onPick){
  const title=field==='start_date'?'Start date':'Target date',m=menu(anchor,[]);m.classList.add('local-project-popover');m.setAttribute('role','dialog');m.setAttribute('aria-label',title);m.innerHTML='<strong>'+escape(title)+'</strong>';let focus=values[field]?dateValue(values[field]):new Date();let precision=values[field+'_precision']||'day';
  const modes=document.createElement('div');modes.className='local-project-date-modes';modes.setAttribute('role','tablist');m.append(modes);
  const input=document.createElement('input');input.type='text';input.placeholder='Try: May 2027, Q4, 05/20/2027';input.setAttribute('aria-label',field==='start_date'?'Start date':'Target date');m.append(input);
  const calendar=document.createElement('div');m.append(calendar);const problem=document.createElement('div');problem.role='alert';m.append(problem);
  const select=(d,p=precision)=>{values[field]=dateString(d);values[field+'_precision']=p;onPick();closeMenu();};
  function paint(){
   modes.replaceChildren();for(const value of ['day','month','quarter','half-year','year']){const b=document.createElement('button');b.type='button';b.textContent=value[0].toUpperCase()+value.slice(1);b.setAttribute('role','tab');b.setAttribute('aria-selected',String(precision===value));b.onclick=()=>{precision=value;paint();};b.tabIndex=precision===value?0:-1;modes.append(b);}
   calendar.innerHTML=precision==='day'?`<div class="local-project-calendar-nav"><button type="button" aria-label="Previous month">‹</button><strong>${months[focus.getMonth()]} ${focus.getFullYear()}</strong><button type="button" aria-label="Next month">›</button></div><div class="local-project-calendar-grid days"></div>`:'<div class="local-project-year-groups"></div>';
   const nav=$$('button',calendar);if(precision==='day'){nav[0].onclick=()=>{focus=new Date(focus.getFullYear(),focus.getMonth()-1,1);paint();};nav[1].onclick=()=>{focus=new Date(focus.getFullYear(),focus.getMonth()+1,1);paint();};}
   let grid=$('.local-project-calendar-grid',calendar);const y=focus.getFullYear(),month=focus.getMonth();
   function choice(text,d){const b=document.createElement('button');b.type='button';b.textContent=text;b.setAttribute('aria-label',dateLabel(dateString(d),precision));b.setAttribute('aria-pressed',String(values[field]===dateString(d)&&values[field+'_precision']===precision));b.onclick=()=>select(d);grid.append(b);}
   if(precision==='day'){for(const day of ['Su','Mo','Tu','We','Th','Fr','Sa']){const span=document.createElement('small');span.textContent=day;grid.append(span);}const first=new Date(y,month,1).getDay();for(let n=0;n<42;n++){const d=new Date(y,month,n-first+1);choice(d.getDate(),d);}}
   else{const groups=$('.local-project-year-groups',calendar),current=new Date().getFullYear();for(let year=current-4;year<=current+5;year++){const section=document.createElement('section');section.dataset.year=year;if(precision!=='year'){const heading=document.createElement('strong');heading.textContent=year;section.append(heading);}grid=document.createElement('div');grid.className='local-project-calendar-grid periods';section.append(grid);groups.append(section);if(precision==='month')for(let i=0;i<12;i++)choice(months[i].slice(0,3),new Date(year,i,1));else if(precision==='quarter')for(let i=0;i<4;i++)choice('Q'+(i+1),new Date(year,i*3,1));else if(precision==='half-year')for(let i=0;i<2;i++)choice('H'+(i+1),new Date(year,i*6,1));else choice(String(year),new Date(year,0,1));}const active=$('[data-year="'+y+'"]',groups);if(active)groups.scrollTop=active.offsetTop-groups.offsetTop;}

  }
  modes.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();e.stopPropagation();const values=['day','month','quarter','half-year','year'];let i=values.indexOf(precision);i=e.key==='Home'?0:e.key==='End'?4:(i+(e.key==='ArrowRight'?1:-1)+5)%5;precision=values[i];paint();$('[aria-selected=true]',modes).focus();};
  input.onkeydown=e=>{if(e.key!=='Enter')return;e.preventDefault();e.stopPropagation();const value=input.value.trim();let d,p='day',match;
   if((match=/^(\d{4})-(\d{2})-(\d{2})$/.exec(value))){d=new Date(+match[1],+match[2]-1,+match[3]);if(dateString(d)!==value)d=null;}
   else if((match=/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(value))){d=new Date(+match[3],+match[1]-1,+match[2]);if(d.getFullYear()!==+match[3]||d.getMonth()!==+match[1]-1||d.getDate()!==+match[2])d=null;}
   else if((match=/^Q([1-4])(?:\s+(\d{4}))?$/i.exec(value))){d=new Date(+(match[2]||focus.getFullYear()),(+match[1]-1)*3,1);p='quarter';}
   else if((match=/^H([12])(?:\s+(\d{4}))?$/i.exec(value))){d=new Date(+(match[2]||focus.getFullYear()),(+match[1]-1)*6,1);p='half-year';}
   else if(/^\d{4}$/.test(value)){d=new Date(+value,0,1);p='year';}
   else if((match=/^([a-z]+)\s+(\d{4})$/i.exec(value))){const month=months.findIndex(m=>m.toLowerCase().startsWith(match[1].toLowerCase()));if(month>=0){d=new Date(+match[2],month,1);p='month';}}
   if(d&&!Number.isNaN(+d))select(d,p);else problem.textContent='Enter a valid date.';
  };
  if(values[field]){const clear=document.createElement('button');clear.type='button';clear.textContent='Remove date';clear.onclick=()=>{values[field]=null;onPick();closeMenu();};m.append(clear);}paint();setTimeout(()=>input.focus(),0);
 }

export async function openProjectEditor(env,existing=null,defaults={}){
 const {api,menu,closeMenu,closeDialog,toast,refresh,sessionInfo,setDialog}=env;
 const [markup,icons,milestoneMarkup,statuses,labels,projects]=await Promise.all([
  fetch('/static/project-create/dialog.html').then(r=>r.text()),fetch('/static/project-create/icons.json').then(r=>r.json()),fetch('/static/project-create/milestone.html').then(r=>r.text()),api('/api/entities/project-statuses'),api('/api/entities/project-labels'),api('/api/entities/projects')]);
 if(!$('link[data-project-editor-style]')){const style=document.createElement('link');style.rel='stylesheet';style.href='/static/project-create/source.css';style.dataset.projectEditorStyle='';document.head.append(style);}
 closeMenu();closeDialog();
 const root=document.createElement('div');root.className='local-project-overlay';root.innerHTML=markup;root._opener=document.activeElement;document.body.append(root);setDialog(root);
 const form=$('form',root),panel=$('[role=dialog]',root),name=$('[aria-label="Project name"]',root),summary=$('[aria-label="Project summary"]',root),description=$('[aria-label="Project description"]',root);
 const data={title:'',summary:'',description:'',status:'Backlog',priority:'No priority',lead:null,members:[],start_date:null,target_date:null,start_date_precision:'day',target_date_precision:'day',labels:[],dependencies:[],milestones:[],icon:'Project',...defaults,...(existing?structuredClone(existing):{})};
 const error=document.createElement('div');error.className='local-project-error';error.role='alert';form.append(error);
 const buttons=new Map($$('button',root).map(b=>[label(b),b]));
 const action=(key,fn)=>{const b=buttons.get(key);if(b){b.type='button';b.onclick=e=>{e.preventDefault();Promise.resolve(fn(b)).catch(e=>{error.textContent=e.message;});};}return b;};
 const setText=(key,text)=>{const b=buttons.get(key);if(!b)return;let span=$$('span',b).find(e=>!e.children.length&&e.textContent.trim());if(span)span.textContent=text;else{b.replaceChildren();b.textContent=text;}};
 const editorText=e=>(e.innerText||'').trim();
 function fillEditor(e,value){e.replaceChildren();if(value)e.textContent=value;else{const p=document.createElement('p');p.className='text-node editor-placeholder';p.dataset.emptyText=e.dataset.placeholder;p.append(document.createElement('br'));e.append(p);}}
 for(const [e,key] of [[name,'title'],[summary,'summary'],[description,'description']]){
  e.dataset.placeholder=$('[data-empty-text]',e)?.dataset.emptyText||'';fillEditor(e,data[key]);
  e.addEventListener('input',()=>{data[key]=editorText(e);e.removeAttribute('aria-invalid');for(const p of $$('[data-empty-text]',e)){p.classList.toggle('editor-placeholder',!data[key]);p.removeAttribute('aria-hidden');}});
  e.addEventListener('blur',()=>{if(!editorText(e))fillEditor(e,'');});
  if(key!=='description')e.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();if(key==='title')summary.focus();else description.focus();}});
 }
 function renderProperties(){
  setText('Change project status',data.status);setText('Change project priority',data.priority);
  setText('Set project lead',data.lead?(sessionInfo.account.display_name||data.lead):'Lead');
  setText('Change project members',data.members.length?`${data.members.length} member${data.members.length===1?'':'s'}`:'Members');
  setText('Change start date',dateLabel(data.start_date,data.start_date_precision)||'Start');setText('Change target date',dateLabel(data.target_date,data.target_date_precision)||'Target');
  setText('Change labels',data.labels.length?data.labels.map(id=>labels.find(x=>x.id===id)?.title).filter(Boolean).join(', '):'Labels');
  setText('Add dependencies',data.dependencies.length?`${data.dependencies.length} dependenc${data.dependencies.length===1?'y':'ies'}`:'Dependencies');
  const icon=icons.find(i=>i.name===data.icon);if(icon){buttons.get('Choose icon').innerHTML=icon.svg;if(data.icon_color)buttons.get('Choose icon').style.color=data.icon_color;}
 }
 function single(key,field,items){action(key,b=>menu(b,items.map(v=>({text:(data[field]===v?'✓ ':'')+v,action:()=>{data[field]=v;renderProperties();}}))));}
 single('Change project status','status',statuses.map(x=>x.title));single('Change project priority','priority',['No priority','Urgent','High','Medium','Low']);
 action('Set project lead',b=>menu(b,[{text:'No lead',action:()=>{data.lead=null;renderProperties();}},{text:sessionInfo.account.display_name||sessionInfo.account.email_normalized,action:()=>{data.lead=sessionInfo.account.email_normalized;renderProperties();}}],'Assign lead…'));
 action('Change project members',b=>menu(b,[{text:(data.members.includes(sessionInfo.account.email_normalized)?'✓ ':'')+(sessionInfo.account.display_name||sessionInfo.account.email_normalized),action:()=>{data.members=data.members.length?[]:[sessionInfo.account.email_normalized];renderProperties();}}],'Search members…'));
 function floating(anchor,title){const m=menu(anchor,[]);m.classList.add('local-project-popover');m.setAttribute('role','dialog');m.setAttribute('aria-label',title);m.innerHTML=`<strong>${escape(title)}</strong>`;return m;}
 const datePicker=(anchor,field,values=data,onPick=renderProperties)=>openProjectDatePicker({menu,closeMenu},anchor,field,values,onPick);
 action('Change start date',b=>datePicker(b,'start_date'));action('Change target date',b=>datePicker(b,'target_date'));
 action('Choose icon',b=>{const m=floating(b,'Choose icon');const input=document.createElement('input');input.placeholder='Search icons…';input.setAttribute('aria-label','Search icons');m.append(input);const grid=document.createElement('div');grid.className='local-project-icons';m.append(grid);for(const icon of icons){const button=document.createElement('button');button.type='button';button.setAttribute('aria-label',icon.name);button.title=icon.name;button.innerHTML=icon.svg;button.onclick=()=>{data.icon=icon.name;renderProperties();closeMenu();};grid.append(button);}input.oninput=()=>$$('button',grid).forEach(b=>b.hidden=!label(b).toLowerCase().includes(input.value.toLowerCase()));input.focus();});
 action('Change labels',b=>{
  const m=floating(b,'Labels'),input=document.createElement('input');input.type='search';input.placeholder='Add labels…';input.setAttribute('aria-label','Add labels…');m.append(input);const results=document.createElement('div');m.append(results);
  const paint=()=>{results.replaceChildren();const query=input.value.trim();for(const item of labels.filter(x=>!x.is_group&&!x.archived&&!labels.find(g=>g.id===x.parent_id)?.archived&&(x.title+' '+(labels.find(g=>g.id===x.parent_id)?.title||'')).toLowerCase().includes(query.toLowerCase()))){const button=document.createElement('button');button.type='button';button.textContent=(data.labels.includes(item.id)?'✓ ':'')+(item.parent_id?(labels.find(g=>g.id===item.parent_id)?.title+' / '):'')+item.title;button.onclick=()=>{data.labels=data.labels.includes(item.id)?data.labels.filter(id=>id!==item.id):[...data.labels.filter(id=>!item.parent_id||labels.find(x=>x.id===id)?.parent_id!==item.parent_id),item.id];renderProperties();paint();};results.append(button);}if(!query&&!labels.length)results.textContent='Start typing to create a new label';if(query&&!labels.some(x=>x.title.toLowerCase()===query.toLowerCase())){const create=document.createElement('button');create.type='button';create.textContent='Create new workspace label: '+query;create.onclick=async()=>{create.disabled=true;try{const item=await api('/api/entities/project-labels','POST',{title:query,description:''});labels.push(item);data.labels.push(item.id);renderProperties();paint();}catch(e){error.textContent=e.message;}finally{create.disabled=false;}};results.append(create);}};input.oninput=paint;paint();input.focus();
 });
 action('Add dependencies',b=>{
  const values=projects.filter(p=>p.id!==data.id);menu(b,values.length?values.map(p=>({text:(data.dependencies.includes(p.id)?'✓ ':'')+p.title,action:()=>{data.dependencies=data.dependencies.includes(p.id)?data.dependencies.filter(id=>id!==p.id):[...data.dependencies,p.id];renderProperties();}})):['No matching actions'],'Dependencies…');
 });
 const milestoneButton=buttons.get('Milestones');let milestoneSection=milestoneButton.parentElement;
 while(milestoneSection.parentElement&&(!milestoneSection.contains(buttons.get('Add'))||milestoneSection===milestoneButton))milestoneSection=milestoneSection.parentElement;
 milestoneSection.classList.add('local-project-milestone-section');const originalMilestones=milestoneSection.innerHTML;
 function renderMilestones(){
  milestoneSection.innerHTML=originalMilestones;const toggle=$$('button',milestoneSection).find(b=>label(b)==='Milestones'),add=$$('button',milestoneSection).find(b=>label(b)==='Add');
  const list=document.createElement('div');list.className='local-project-milestones';milestoneSection.append(list);
  data.milestones.forEach((item,index)=>{const row=document.createElement('div');row.className='local-project-milestone-row';row.innerHTML=`<button type="button" aria-label="Edit milestone ${escape(item.title)}">◇ ${escape(item.title)}</button><button type="button" aria-label="Set target date for ${escape(item.title)}">${escape(dateLabel(item.target_date,item.target_date_precision)||'▣+')}</button><button type="button" aria-label="Remove milestone ${escape(item.title)}">×</button>`;const [edit,date,remove]=$$('button',row);edit.onclick=()=>milestoneForm(index);date.onclick=()=>datePicker(date,'target_date',item,renderMilestones);remove.onclick=()=>{data.milestones.splice(index,1);renderMilestones();};list.append(row);});
  toggle.type='button';toggle.style.flex='1';toggle.style.textAlign='left';if(data.milestones.length)toggle.textContent='Milestones '+data.milestones.length+' ▾';toggle.setAttribute('aria-expanded','true');toggle.onclick=()=>{list.hidden=!list.hidden;toggle.setAttribute('aria-expanded',String(!list.hidden));};add.type='button';if(data.milestones.length){add.textContent='+ Add milestone';add.setAttribute('aria-label','Add milestone');add.classList.add('local-project-add-milestone');milestoneSection.append(add);}add.onclick=()=>milestoneForm();
 }
 function milestoneForm(index=null){
  milestoneSection.innerHTML=milestoneMarkup;const title=$('[aria-label="Milestone name"]',milestoneSection),desc=$('[aria-label="Milestone description"]',milestoneSection);if(index!==null){title.textContent=data.milestones[index].title;desc.textContent=data.milestones[index].description||'';}
  for(const e of [title,desc])e.oninput=()=>{for(const p of $$('[data-empty-text]',e)){p.classList.toggle('editor-placeholder',!editorText(e));p.removeAttribute('aria-hidden');}};
  const cancel=$('[aria-label="Discard changes"]',milestoneSection),save=$('[aria-label="Add milestone"]',milestoneSection);cancel.type='button';cancel.onclick=renderMilestones;save.type='button';save.onclick=()=>{if(!editorText(title)){error.textContent='Enter a milestone name.';title.focus();return;}const value={...(index===null?{}:data.milestones[index]),id:index===null?'milestone_'+crypto.randomUUID():data.milestones[index].id,title:editorText(title),description:editorText(desc)};if(index===null)data.milestones.push(value);else data.milestones[index]=value;error.textContent='';renderMilestones();};title.focus();
 }
 action('Discard project',closeDialog);
 // Source Agent entry is retained; real agent execution remains tracked as incomplete.
 action('Create with Agent',()=>{error.textContent='Agent execution is not configured in this local workspace.';});
 const submit=$('button[type=submit]',form);if(existing){submit.textContent='Save project';panel.setAttribute('aria-label','Edit project');const remove=document.createElement('button');remove.type='button';remove.textContent='Delete project';remove.className='local-project-delete';submit.before(remove);remove.onclick=()=>{if(remove.dataset.confirm!=='true'){remove.dataset.confirm='true';remove.textContent='Confirm delete';return;}api('/api/entities/projects/'+existing.id,'DELETE').then(async()=>{closeDialog();await refresh();toast('Project deleted');}).catch(e=>{error.textContent=e.message;});};}
 form.onsubmit=async event=>{event.preventDefault();error.textContent='';data.title=editorText(name);data.summary=editorText(summary);data.description=editorText(description);if(!data.title){error.textContent='Project name required. The project name cannot be empty.';name.setAttribute('aria-invalid','true');name.focus();return;}submit.disabled=true;try{await api('/api/entities/projects'+(existing?'/'+existing.id:''),existing?'PATCH':'POST',data);closeDialog();await refresh();toast(existing?'Project updated':'Project created');}catch(e){error.textContent=e.message;}finally{submit.disabled=false;}};
 root.addEventListener('click',e=>{if(e.target===panel)closeDialog();});root.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key==='Enter'){e.preventDefault();form.requestSubmit();}});
 renderProperties();renderMilestones();setTimeout(()=>name.focus(),50);
}
