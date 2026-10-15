const cards=new WeakMap(),environments=new WeakMap();
const button=name=>{const element=document.createElement('button');element.type='button';element.textContent=name;element.setAttribute('aria-label',name);return element;};
function download(link){const anchor=document.createElement('a');anchor.href=link.getAttribute('href').split('?')[0]+'?download=1';anchor.download=link.dataset.fileName||'';document.body.append(anchor);anchor.click();anchor.remove();}
export function hydrateDocumentFiles(body){
 for(const link of body.querySelectorAll('a[data-attachment="true"]')){
  if(link.closest('[data-pdf-card]'))continue;
  link.removeAttribute('download');if(cards.has(link))continue;
  const card=document.createElement('div');card.dataset.fileCard='true';card.className='document-file-card';card.contentEditable='false';link.before(card);card.append(link);
  const controls=document.createElement('div');controls.dataset.documentControl='file-actions';controls.className='document-file-actions';card.append(controls);
  const save=button('Download'),menu=button('Open menu');controls.append(save,menu);
  const actions=anchor=>{const env=environments.get(body);if(!env)return;env.menu(anchor,[{text:'Download',action:()=>download(link)},...(body.isContentEditable?[null,{text:'Delete',action:()=>{card.remove();if(!body.children.length)body.innerHTML='<p><br></p>';env.changed();}}]:[])]);};
  link.onclick=event=>{event.preventDefault();event.stopPropagation();};save.onclick=event=>{event.preventDefault();event.stopPropagation();download(link);};menu.onclick=event=>{event.preventDefault();event.stopPropagation();actions(menu);};card.oncontextmenu=event=>{event.preventDefault();event.stopPropagation();actions(card);};cards.set(link,card);
 }
}
export function bindDocumentFiles(env){environments.set(env.body,env);hydrateDocumentFiles(env.body);}
