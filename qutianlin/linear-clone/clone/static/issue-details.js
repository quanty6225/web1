const $=(q,r=document)=>r.querySelector(q),$$=(q,r=document)=>[...r.querySelectorAll(q)];
let cache;
export async function createIssueDetails({getItems,getProjects,getAccount,onFilter,onTab,getTab}){
 if(!cache){const manifest=await fetch('/static/issue-details/manifest.json').then(r=>r.json());const templates={};await Promise.all(Object.entries(manifest.tabs).map(async([name,file])=>templates[name]=await fetch('/static/issue-details/'+file).then(r=>r.text())));cache={manifest,templates};}
 if(!$('link[data-issue-details-style]')){const style=document.createElement('link');style.rel='stylesheet';style.href='/static/issue-details/source.css';style.dataset.issueDetailsStyle='true';document.head.append(style);}
 const list=$('[data-local-issue-list]'),parent=list?.closest(cache.manifest.parent_selector)||$(cache.manifest.parent_selector,$('main'));
 if(!parent)throw Error('Issue details container is unavailable.');
 let root,selected=null;
 const groups=tab=>{const result=new Map();for(const issue of getItems()){const values=tab==='Labels'?(issue.labels||[]):[issue[tab==='Assignees'?'assignee':tab==='Priority'?'priority':'project']||''];for(const value of values)result.set(value,(result.get(value)||0)+1);}return result;};
 function name(tab,value){if(tab==='Assignees')return value?(value===getAccount().email_normalized?getAccount().display_name:value):'No assignee';if(tab==='Projects')return value?(getProjects().find(p=>p.id===value)?.title||value):'No project';return value||(tab==='Priority'?'No priority':'');}
 function render(){
  const tab=getTab()||'Assignees',holder=document.createElement('template');holder.innerHTML=cache.templates[tab];const next=holder.content.firstElementChild;if(root)root.replaceWith(next);else parent.append(next);root=next;root.addEventListener('click',e=>e.stopPropagation());
  const tabs=$$('[role=tab]',root);
  for(const button of tabs){const value=button.textContent.trim();button.id='local-details-'+value.toLowerCase();button.setAttribute('aria-selected',String(value===tab));button.setAttribute('aria-controls','local-details-content');button.tabIndex=value===tab?0:-1;button.onclick=async()=>{selected=null;onFilter(null);await onTab(value);render();};button.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();e.stopPropagation();const index=tabs.indexOf(button);const target=e.key==='Home'?0:e.key==='End'?3:(index+(e.key==='ArrowRight'?1:-1)+4)%4;tabs[target].click();setTimeout(()=>$('[aria-selected=true]',root)?.focus(),0);};}
  let countCell=$('[data-column-id=row-count]',root),template=countCell?.closest('[role=button]'),host;
  if(template){host=template.parentElement.hasAttribute('data-contextual-menu')?template.parentElement.parentElement:template.parentElement;}
  else{const original=document.createElement('template');original.innerHTML=cache.templates.Assignees;template=$('[data-column-id=row-count]',original.content).closest('[role=button]');const empty=$$('*',root).find(e=>!e.children.length&&e.textContent.trim()==='No labels used');if(!groups(tab).size)return;host=document.createElement('div');empty?.replaceWith(host);}
  host.id='local-details-content';host.setAttribute('role','tabpanel');host.setAttribute('aria-labelledby','local-details-'+tab.toLowerCase());host.replaceChildren();
  for(const [value,count] of groups(tab)){
   const row=template.cloneNode(true);row.dataset.detailValue=value;const user=$('[data-column-id=user]',row),text=$$('span',user).find(e=>!e.children.length&&e.textContent.trim()&&!e.closest('button'));if(text)text.textContent=name(tab,value);const countButton=$('button',$('[data-column-id=row-count]',row));countButton.textContent=count;countButton.setAttribute('aria-label','Issue count: '+count);
   const action=$('button',user),active=selected?.tab===tab&&selected.value===value;action.textContent=active?'Clear filter':'See issues';action.setAttribute('aria-pressed',String(active));action.style.display='none';row.onmouseenter=()=>action.style.display='inline-flex';row.onmouseleave=()=>{if(document.activeElement!==action)action.style.display='none';};row.onfocusin=()=>action.style.display='inline-flex';action.tabIndex=0;
   const toggleFilter=()=>{selected=active?null:{tab,value};onFilter(selected?{key:tab==='Assignees'?'assignee':tab==='Labels'?'labels':tab==='Priority'?'priority':'project',value}:null);render();};
   row.setAttribute('aria-pressed',String(active));row.onclick=e=>{if(e.target.closest('button'))return;toggleFilter();};row.onkeydown=e=>{if(e.target===row&&['Enter',' '].includes(e.key)){e.preventDefault();e.stopPropagation();toggleFilter();}};
   action.onclick=e=>{e.stopPropagation();toggleFilter();};
   let tooltip;const show=()=>{tooltip?.remove();tooltip=document.createElement('span');tooltip.className='local-details-tooltip';tooltip.role='tooltip';tooltip.textContent='Issue count';row.append(tooltip);};countButton.onclick=e=>{e.stopPropagation();show();};countButton.onmouseenter=show;countButton.onfocus=show;countButton.onmouseleave=()=>tooltip?.remove();countButton.onblur=()=>tooltip?.remove();host.append(row);
  }
 }
 render();return {refresh:render,remove(){root?.remove();onFilter(null);}};
}
