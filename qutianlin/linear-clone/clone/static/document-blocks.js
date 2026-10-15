import {hydrateDocumentCode} from '/static/document-code.js';
import {hydrateDocumentDiagrams} from '/static/document-diagrams.js';
const $=(selector,root)=>root.querySelector(selector);
const $$=(selector,root)=>[...root.querySelectorAll(selector)];
const classes=new Set(['todo-content','callout-content','collapsible-section','collapsible-heading','collapsible-content']);
export function blockAttributes(tag,attributes){
 const safe={};const value=key=>attributes.get(key);
 if(tag==='PRE'){for(const key of ['data-code-id','data-code-language'])if(/^[a-zA-Z0-9_-]{1,64}$/.test(value(key)||''))safe[key]=value(key);}
 if(tag==='CODE'){const name=value('data-language')||(value('class')||'').split(/\s+/).find(x=>x.startsWith('language-'))?.slice(9);if(/^[a-zA-Z0-9_+-]{1,32}$/.test(name||''))safe['data-language']=name;}
 if(tag==='UL'&&value('data-type')==='todo_list')safe['data-type']='todo_list';
 if(tag==='LI'&&value('data-type')==='todo_item'){safe['data-type']='todo_item';safe['data-done']=value('data-done')==='true'?'true':'false';}
 if(tag==='DIV'){
  if(value('data-diagram')==='true'){safe['data-diagram']='true';if(/^[a-zA-Z0-9_-]{1,64}$/.test(value('data-diagram-id')||''))safe['data-diagram-id']=value('data-diagram-id');}
  const keep=(value('class')||'').split(/\s+/).filter(name=>classes.has(name));if(keep.length)safe.class=keep.join(' ');
  if(keep.includes('collapsible-section'))safe['data-open']=value('data-open')==='false'?'false':'true';
  if(value('data-callout')==='true'){safe['data-callout']='true';safe['data-icon']=(value('data-icon')||'LightBulb').slice(0,128);const color=value('data-color')||'#26b5ce';safe['data-color']=/^(#[0-9a-f]{6}|lch\([\d.]+% [\d.]+ [\d.]+\))$/i.test(color)?color:'#26b5ce';}
 }
 return safe;
}
export function documentBodyHTML(body){
 const template=document.createElement('template'),clone=template.content.ownerDocument.importNode(body,true);
 $$('[data-pdf-card],[data-file-card]',clone).forEach(card=>{const link=card.querySelector('a[data-attachment]');if(link)card.replaceWith(link);else card.remove();});
 $$('[data-image-view]',clone).forEach(view=>{const image=view.querySelector('img');if(image)view.replaceWith(image);else view.remove();});
 $$('img',clone).forEach(image=>{image.removeAttribute('style');image.removeAttribute('draggable');});
 $$('[data-diagram="true"]',clone).forEach(block=>{for(const attribute of [...block.attributes])if(!['data-diagram','data-diagram-id'].includes(attribute.name))block.removeAttribute(attribute.name);});
 $$('pre',clone).forEach(pre=>{const code=pre.querySelector(':scope > code');if(code){const plain=document.createElement('code');plain.textContent=code.textContent;pre.replaceChildren(plain);}for(const attr of [...pre.attributes])if(!['data-code-id','data-code-language'].includes(attr.name))pre.removeAttribute(attr.name);});
 $$('[data-document-control]',clone).forEach(node=>node.remove());
 $$('a[data-attachment]',clone).forEach(node=>{for(const attribute of ['contenteditable','download','title'])node.removeAttribute(attribute);});
 $$('[role="region"],.collapsible-heading,.collapsible-content,[data-callout]' ,clone).forEach(node=>{for(const attribute of ['role','aria-label','aria-expanded','hidden','style'])node.removeAttribute(attribute);});
 return clone.innerHTML;
}
let iconCatalog;
function drawIcon(button,name){
 if(name.startsWith('emoji:')){button.textContent=name.slice(6);return;}
 iconCatalog??=fetch('/static/project-create/icons.json').then(response=>response.json());
 iconCatalog.then(items=>{if(button.dataset.icon!==name)return;const icon=items.find(item=>item.name===name);if(icon)button.innerHTML=icon.svg;}).catch(()=>{});
}
export function hydrateDocumentBlocks(body){
 hydrateDocumentDiagrams(body);
 hydrateDocumentCode(body);
 for(const item of $$('li[data-type="todo_item"]',body)){
  let control=$(':scope > [data-document-control]',item);if(!control){control=document.createElement('div');control.dataset.documentControl='check';control.className='todo-checkbox-container';control.contentEditable='false';const box=document.createElement('div');box.role='checkbox';box.tabIndex=0;box.setAttribute('aria-label','Checklist item');control.append(box);item.prepend(control);}
  const box=$('[role=checkbox]',control);box.setAttribute('aria-label',$('.todo-content',item)?.innerText.trim()||'Checklist item');box.setAttribute('aria-checked',String(item.dataset.done==='true'));box.className='todo-checkbox '+(item.dataset.done==='true'?'todo-checkbox-checked':'todo-checkbox-unchecked');
 }
 for(const block of $$('[data-callout="true"]',body)){
  let control=$(':scope > [data-document-control]',block);if(!control){control=document.createElement('span');control.dataset.documentControl='callout';control.className='callout-controls';control.contentEditable='false';const button=document.createElement('button');button.type='button';button.setAttribute('aria-label','Change callout icon or color');control.append(button);block.prepend(control);}
  const button=$('button',control),name=block.dataset.icon||'LightBulb';block.style.setProperty('--callout-color',block.dataset.color||'#26b5ce');button.dataset.icon=name;drawIcon(button,name);
 }
 for(const block of $$('.collapsible-section',body)){
  block.role='region';block.setAttribute('aria-label','Collapsible section');const heading=$(':scope > .collapsible-heading',block),content=$(':scope > .collapsible-content',block);if(!heading||!content)continue;
  let control=$(':scope > [data-document-control]',heading);if(!control){control=document.createElement('span');control.dataset.documentControl='collapse';control.className='collapse-toggle';control.contentEditable='false';const button=document.createElement('button');button.type='button';button.tabIndex=-1;button.textContent='▸';control.append(button);heading.prepend(control);}
  const open=block.dataset.open!=='false';heading.setAttribute('aria-expanded',String(open));const button=$('button',control);button.setAttribute('aria-label',open?'Collapse section':'Expand section');button.setAttribute('aria-expanded',String(open));content.hidden=!open;
 }
}
export function bindDocumentBlocks({body,changed,chooseIcon,toast}){
 hydrateDocumentBlocks(body);
 body.addEventListener('input',()=>hydrateDocumentBlocks(body));
 const toggle=target=>{const control=target.closest('[data-document-control]');if(!control||!body.contains(control))return false;
  if(control.dataset.documentControl==='check'){const item=control.closest('[data-type="todo_item"]');item.dataset.done=item.dataset.done==='true'?'false':'true';hydrateDocumentBlocks(body);changed();}
  else if(control.dataset.documentControl==='collapse'){const block=control.closest('.collapsible-section');block.dataset.open=block.dataset.open==='false'?'true':'false';hydrateDocumentBlocks(body);changed();}
  else if(control.dataset.documentControl==='callout')chooseIcon(async icon=>{control.parentElement.dataset.icon=icon;hydrateDocumentBlocks(body);changed();},{color:control.parentElement.dataset.color||'#26b5ce',onColor:async color=>{control.parentElement.dataset.color=color;hydrateDocumentBlocks(body);changed();}}).catch(error=>toast(error.message));
  else return false;
  return true;
 };
 body.addEventListener('click',event=>{if(toggle(event.target)){event.preventDefault();event.stopPropagation();}});
 body.addEventListener('keydown',event=>{
  if(['check','collapse','callout'].includes(event.target.closest('[data-document-control]')?.dataset.documentControl)&&['Enter',' '].includes(event.key)){event.preventDefault();event.stopPropagation();toggle(event.target);return;}
  if(event.key!=='Enter'||event.shiftKey)return;const selection=getSelection();if(!selection?.isCollapsed)return;const node=selection.anchorNode?.nodeType===Node.ELEMENT_NODE?selection.anchorNode:selection.anchorNode?.parentElement;const content=node?.closest('.todo-content'),item=content?.closest('li[data-type="todo_item"]');if(!item||!body.contains(item))return;
  event.preventDefault();const range=selection.getRangeAt(0);
  if(!content.innerText.trim()){
   const paragraph=document.createElement('p');paragraph.append(document.createElement('br'));const list=item.parentElement;list.after(paragraph);item.remove();if(!list.children.length)list.remove();range.selectNodeContents(paragraph);range.collapse(true);
  }else{
   const tail=document.createRange();tail.selectNodeContents(content);tail.setStart(range.startContainer,range.startOffset);const remainder=tail.extractContents();const next=document.createElement('li');next.dataset.type='todo_item';next.dataset.done='false';const nextContent=document.createElement('div');nextContent.className='todo-content';nextContent.append(remainder);if(!nextContent.textContent.trim())nextContent.innerHTML='<p><br></p>';next.append(nextContent);item.after(next);hydrateDocumentBlocks(body);range.selectNodeContents(nextContent);range.collapse(true);
  }
  selection.removeAllRanges();selection.addRange(range);changed();
 });
}
export const documentBlocks={
 Diagram:'<div data-diagram="true"><pre><code></code></pre></div><p><br></p>',
 Checklist:'<ul data-type="todo_list"><li data-type="todo_item" data-done="false"><div class="todo-content"><p><br></p></div></li></ul>',
 'Collapsible section':'<div class="collapsible-section" data-open="true"><div class="collapsible-heading"><p><br></p></div><div class="collapsible-content"><p><br></p></div></div><p><br></p>',
 Callout:'<div data-callout="true" data-icon="LightBulb"><div class="callout-content"><p><br></p></div></div><p><br></p>'
};
