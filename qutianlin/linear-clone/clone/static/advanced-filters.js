import {dateFilterMenu} from './filter-dates.js';
import {condition,readPath,hasConditions} from './filter-expression.js';
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
let templates;
export async function loadFilterTemplates(){
 if(templates)return templates;
 const names=['condition','add','bar'];templates={};await Promise.all(names.map(async name=>templates[name]=await fetch('/static/filter-builder/'+name+'.html').then(r=>r.text())));
 if(!$('[data-filter-builder-style]')){const link=document.createElement('link');link.rel='stylesheet';link.href='/static/filter-builder/source.css';link.dataset.filterBuilderStyle='true';document.head.append(link);}
 return templates;
}
function fragment(name){const t=document.createElement('template');t.innerHTML=templates[name];return t.content.firstElementChild;}
export function renderFilterSummary({expression,enabled,container,onOpen,onClear,getFields,onSave}){
 $('[data-advanced-filter-bar]')?.remove();if(!enabled||!container||!templates)return;
 const bar=fragment('bar');bar.classList.add('local-advanced-summary');
 const opener=$('[aria-label="Open advanced filter"]',bar)?.closest('[role=button]');
 if(opener){
  function summary(node){const group=node.and||node.or;if(group)return group.filter(hasConditions).map(child=>summary(child)).join(node.and?' and ':' or ');for(const field of getFields()){const value=field.read?field.read(node):readPath(node,field.path);if(value){const [op,values]=Object.entries(value)[0],all=Array.isArray(values)?values:[values],text=field.format?field.format(values,op):all.map(v=>field.options?.find(x=>x.value===v)?.label??String(v)).join(', ');return field.label+' '+(field.operatorLabel?field.operatorLabel(op,all):op==='nin'?'is not':op==='in'?'is':op.startsWith('contains')?'contains':op)+' '+text;}}return ''; }
  opener.textContent=summary(expression)||'Advanced filter';bar.firstElementChild.replaceChildren(opener);opener.classList.add('local-advanced-summary-open');opener.setAttribute('aria-label','Open advanced filter');opener.onclick=e=>{e.stopPropagation();onOpen(opener);};opener.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();opener.click();}};}
 const remove=$$('[role=button]',bar).find(x=>$('[aria-label="Remove filter"]',x));if(remove){remove.setAttribute('aria-label','Remove advanced filter');remove.onclick=e=>{e.stopPropagation();onClear();};}
 const clear=$('[aria-label="Clear all filters"]',bar);clear.disabled=!hasConditions(expression);clear.closest('[data-disabled]')?.setAttribute('data-disabled',String(clear.disabled));clear.onclick=e=>{e.stopPropagation();onClear();};
 for(const add of $$('[aria-label="Add another filter"]',bar))add.onclick=e=>{e.stopPropagation();onOpen(add);};
 const save=$$('button',bar).find(b=>b.textContent.trim()==='Save');if(save)save.onclick=e=>{e.stopPropagation();onSave?.();};
 const header=$('main header');if(header)header.after(bar);else container.before(bar);
}
export async function openAdvancedFilters({anchor,getExpression,getFields,onChange,menu,closeMenu,modal,closeDialog,onClose}){
 await loadFilterTemplates();
 const backdrop=document.createElement('div');backdrop.className='local-filter-backdrop';
 const root=document.createElement('section');root.className='local-advanced-filters';root.setAttribute('role','dialog');root.setAttribute('aria-label','Advanced filter');root.setAttribute('aria-modal','true');
 const rect=anchor?.getBoundingClientRect()||{left:264,bottom:135};root.style.left=Math.max(8,Math.min(rect.left,innerWidth-540))+'px';root.style.top=Math.max(8,Math.min(rect.bottom+8,innerHeight-180))+'px';
 document.body.append(backdrop,root);root.addEventListener('click',e=>e.stopPropagation());
 const close=()=>{closeMenu();root.remove();backdrop.remove();anchor?.isConnected&&anchor.focus();onClose?.();};backdrop.onclick=close;
 async function save(){await onChange(getExpression());render();}
 function detect(node){for(const field of getFields()){const value=field.read?field.read(node):readPath(node,field.path);if(value&&typeof value==='object')return {field,value};}return null;}
 function operatorText(field,operator,values){if(field.operatorLabel)return field.operatorLabel(operator,values);if(operator==='containsIgnoreCase'||operator==='contains')return 'contains';if(operator==='notContainsIgnoreCase')return 'does not contain';if(operator==='nin')return 'is not';return Array.isArray(values)&&values.length>1?'is either of':'is';}
 function make(field,operator,values){return field.build?field.build(operator,values):condition(field.path,operator,values);}
 function replace(target,value){for(const key of Object.keys(target))delete target[key];Object.assign(target,value);}
 function display(field,values,operator){if(field.format)return field.format(values,operator);return (Array.isArray(values)?values:[values]).map(v=>field.options?.find(x=>x.value===v)?.label??String(v)).join(', ');}
 function textEditor(field,target,parent){const old=target?detect(target)?.value:null;const text=old?Object.values(old)[0]:'';modal(field.inputTitle||'Filter by content…','<label>'+field.label+'<input name="input" aria-label="'+field.label+'" required></label>','Apply',async form=>{const next=make(field,field.operators?.[0]||'containsIgnoreCase',form.get('input'));if(target)replace(target,next);else parent.push(next);closeDialog();await save();},true);const input=$('.local-dialog input[name=input]');if(input)input.value=text||'';}
 function valuesMenu(anchor,field,target,parent){
  if(field.type==='text'){textEditor(field,target,parent);return;}
  if(field.type==='date'){dateFilterMenu({anchor,field,menu,modal,closeDialog,onPick:async value=>{const next={[field.key]:value};if(target)replace(target,next);else parent.push(next);await save();}});return;}

  if(field.type==='single'){const current=target?detect(target)?.value:null,operator=current?Object.keys(current)[0]:field.defaultOperator;menu(anchor,field.options.map(option=>({text:option.label,action:async()=>{const next=make(field,operator,option.value);if(target)replace(target,next);else parent.push(next);await save();}})));return;}
  const value=target?detect(target)?.value:null,operator=value?Object.keys(value)[0]:'in',selected=value?Object.values(value)[0]:[];
  const choices=field.options||[];
  const m=menu(anchor,choices.map(option=>({text:option.label,action:async()=>{
   const nextValues=target?(Array.isArray(selected)?selected:[]).filter(v=>v!==option.value):[];if(!target||!selected.includes(option.value))nextValues.push(option.value);
   if(!nextValues.length){const index=parent.indexOf(target);if(index>=0)parent.splice(index,1);}else if(target)replace(target,make(field,operator,nextValues));else parent.push(make(field,operator,nextValues));await save();
  }})),'Filter…');
  $$('[role=menuitem]',m).forEach((button,index)=>button.setAttribute('aria-checked',String(Array.isArray(selected)&&selected.includes(choices[index].value))));
 }
 function addMenu(anchor,group){const children=group.and||group.or;menu(anchor,[{text:'Add filter group',action:async()=>{children.push({and:[]});await save();}},null,...getFields().map(field=>({text:field.label+' ›',action:()=>valuesMenu(anchor,field,null,children)}))],'Filter…');}
 function renderCondition(node,parent){
  const found=detect(node);if(!found){const text=document.createElement('p');text.textContent='Unable to load filter';return text;}
  const {field,value}=found,operator=Object.keys(value)[0],values=Object.values(value)[0];const row=fragment('condition');row.dataset.filterFieldName=field.label;
  $('[data-filter-field]',row).textContent=field.label;
  const op=$('[data-filter-operator]',row);op.textContent=operatorText(field,operator,values);op.setAttribute('aria-label',op.textContent);op.onclick=()=>menu(op,(field.operatorsFor?.(operator)||((field.operators&&Array.isArray(values)&&values.length===1&&field.key==='labels'?['in','nin']:field.operators)||(field.type==='text'?['containsIgnoreCase','notContainsIgnoreCase']:['in','nin']))).map(key=>({text:operatorText(field,key,values),action:async()=>{replace(node,make(field,key,values));await save();}})));
  const val=$('[data-filter-value]',row);val.textContent=display(field,values,operator);val.setAttribute('aria-label',field.label);val.onclick=()=>valuesMenu(val,field,node,parent);
  const remove=$('[data-filter-remove]',row);remove.setAttribute('aria-label','Remove '+field.label.toLowerCase()+' filter');remove.onclick=async()=>{parent.splice(parent.indexOf(node),1);await save();};
  for(const el of $$('[role=button]',row))el.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();el.click();}};
  return row;
 }
 function renderGroup(group,parent=null){
  const box=document.createElement('div');box.className='local-expression-group';box.dataset.filterGroup='true';const operator=group.and?'and':'or',items=group[operator];
  if(parent){const remove=document.createElement('button');remove.className='local-filter-delete-group';remove.setAttribute('aria-label','Delete group');remove.textContent='×';remove.onclick=async()=>{parent.splice(parent.indexOf(group),1);await save();};box.append(remove);}
  function connector(){const button=document.createElement('button');button.className='local-filter-connector';button.textContent=operator;button.setAttribute('aria-label','Toggle filter operator, currently '+operator);button.onclick=async()=>{delete group[operator];group[operator==='and'?'or':'and']=items;await save();};return button;}
  for(const [index,item] of items.entries()){if(index)box.append(connector());box.append(item.and||item.or?renderGroup(item,items):renderCondition(item,items));}
  if(items.length)box.append(connector());const add=fragment('add');add.tabIndex=0;add.onclick=()=>addMenu(add,group);box.append(add);return box;
 }
 function render(){const expression=getExpression();root.replaceChildren(renderGroup(expression));}
 render();$('button,[role=button]',root)?.focus();return {close,root};
}
