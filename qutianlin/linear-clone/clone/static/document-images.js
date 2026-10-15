const views=new WeakMap(),environments=new WeakMap();
const positive=value=>Number.isFinite(Number(value))&&Number(value)>0?Number(value):null;
const button=name=>{const node=document.createElement('button');node.type='button';node.textContent=name;node.setAttribute('aria-label',name);return node;};
function dimensions(image,body){const width=positive(image.getAttribute('width'))||image.naturalWidth,height=positive(image.getAttribute('height'))||image.naturalHeight,container=body.clientWidth||width,ratio=width/height;return {width,height,container,min:Math.min(120,width),max:Math.min(width*2,ratio*600,image.closest('td,th')?Infinity:container),resizable:ratio>Math.min(120,width)/600&&ratio<container/Math.min(120,height)};}
function openImage(image,env){const overlay=env.modal(image.alt||'Image','<div class="document-media-preview"></div>',null,null),copy=image.cloneNode(true);for(const attr of ['style','width','height','data-display-width'])copy.removeAttribute(attr);overlay.querySelector('.document-media-preview').append(copy);}
function download(image){const link=document.createElement('a');link.href=image.getAttribute('src')+'?download=1';link.download=image.alt||'image';document.body.append(link);link.click();link.remove();}
async function copyImage(image,env){try{await image.decode();const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;canvas.getContext('2d').drawImage(image,0,0);const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!blob)throw Error('Image could not be encoded');await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);}catch{env.toast('Could not copy image');}}
function commentAction(state,body){
 const comments=environments.get(body)?.imageComments;if(!comments||!body.isContentEditable)return null;
 const id=state.image.dataset.imageId,value=comments.get(id),count=value.threads.length;
 return {text:count?(value.active?'Hide':'View')+' comment'+(count>1?'s':''):'Add comment',active:count>0&&value.active,action:()=>{if(count)comments.toggle(id);else comments.add(state.image);}};
}
function paintComment(state,body){
 const action=commentAction(state,body),comments=environments.get(body)?.imageComments?.get(state.image.dataset.imageId);
 state.wrapper.dataset.visibleComment=String(!!comments?.threads.length);state.wrapper.dataset.activeComment=String(!!comments?.threads.length&&comments.active);
 let control=state.controls.querySelector('[data-image-comment]');
 if(!action){control?.remove();return;}
 if(!control){control=button(action.text);control.textContent='▱';control.dataset.imageComment='';state.controls.prepend(control);control.onclick=event=>{event.preventDefault();event.stopPropagation();commentAction(state,body)?.action();};}
 control.setAttribute('aria-label',action.text);control.title=action.text;control.setAttribute('aria-pressed',String(action.active));
}
function menu(state,body,anchor){
 const env=environments.get(body);if(!env)return;const {image,wrapper}=state,comment=commentAction(state,body);
 env.menu(anchor,[{text:'View image',action:()=>openImage(image,env)},{text:'Download',action:()=>download(image)},...(navigator.clipboard?.write&&window.ClipboardItem?[{text:'Copy image',action:()=>copyImage(image,env)}]:[]),{text:'Copy link',action:async()=>{try{await navigator.clipboard.writeText(location.origin+image.getAttribute('src'));env.toast('Image URL copied to clipboard');}catch{env.toast('Could not copy link');}}},...(comment?[null,comment]:[]),...(body.isContentEditable?[null,{text:'Delete',action:()=>{wrapper.remove();if(!body.children.length)body.innerHTML='<p><br></p>';env.changed();}}]:[])]);
}
function paint(state,body){const {image,wrapper,handles}=state;paintComment(state,body);if(!image.naturalWidth)return;const limits=dimensions(image,body),width=Math.min(limits.max,positive(image.dataset.displayWidth)||limits.width);wrapper.style.width=width+'px';wrapper.dataset.smallImage=String(width<200||width*limits.height/limits.width<48);image.style.width='100%';image.style.height='auto';for(const handle of handles){handle.hidden=!body.isContentEditable||!limits.resizable;handle.setAttribute('aria-valuemin',String(limits.min));handle.setAttribute('aria-valuemax',String(Math.round(limits.max)));handle.setAttribute('aria-valuenow',String(Math.round(width)));}}
function commit(state,body,value){const limits=dimensions(state.image,body),width=Math.max(limits.min,Math.min(value,limits.max));if(width>=limits.container&&limits.width>=limits.container)delete state.image.dataset.displayWidth;else state.image.dataset.displayWidth=String(Math.round(width));paint(state,body);environments.get(body)?.changed();}
export function hydrateDocumentImages(body){
 const images=[...body.querySelectorAll('img[src^="/api/uploads/"]')],seen=new Set(images.filter(image=>views.has(image)).map(image=>image.dataset.imageId));
 for(const image of images){
  if(!image.dataset.imageId||!views.has(image)&&seen.has(image.dataset.imageId)){image.dataset.imageId=crypto.randomUUID();if(body.isContentEditable)environments.get(body)?.changed();}seen.add(image.dataset.imageId);
  let state=views.get(image);if(state){paint(state,body);continue;}
  const wrapper=document.createElement('div');wrapper.dataset.imageView='true';wrapper.className='document-image-block';wrapper.contentEditable='false';image.before(wrapper);wrapper.append(image);image.draggable=false;
  const controls=document.createElement('div');controls.dataset.documentControl='image-actions';controls.className='document-image-actions';const open=button('Open image menu');open.textContent='⋯';controls.append(open);wrapper.append(controls);state={image,wrapper,controls,handles:[]};views.set(image,state);
  open.onclick=event=>{event.preventDefault();event.stopPropagation();menu(state,body,open);};wrapper.oncontextmenu=event=>{event.preventDefault();event.stopPropagation();menu(state,body,wrapper);};image.onclick=event=>{event.stopPropagation();if(!body.isContentEditable&&environments.has(body))openImage(image,environments.get(body));};image.ondblclick=event=>{event.preventDefault();event.stopPropagation();if(body.isContentEditable&&environments.has(body))openImage(image,environments.get(body));};
  for(const side of ['left','right']){
   const handle=document.createElement('div');handle.dataset.documentControl='image-resize';handle.className='document-image-resize '+side;handle.tabIndex=0;handle.setAttribute('role','separator');handle.setAttribute('aria-label','Resize image from '+side);handle.setAttribute('aria-orientation','vertical');wrapper.append(handle);state.handles.push(handle);let drag;
   handle.onpointerdown=event=>{if(event.button!==0||!body.isContentEditable)return;event.preventDefault();event.stopPropagation();drag={x:event.clientX,width:wrapper.getBoundingClientRect().width,original:image.dataset.displayWidth,snaps:[...body.querySelectorAll('img')].filter(other=>other!==image).map(other=>positive(other.dataset.displayWidth)||positive(other.getAttribute('width'))||other.naturalWidth).filter(Boolean)};handle.setPointerCapture(event.pointerId);};
   handle.onpointermove=event=>{if(!drag)return;const limits=dimensions(image,body);let width=drag.width+(event.clientX-drag.x)*(side==='left'?-2:2);const snap=drag.snaps.find(value=>Math.abs(value-width)<16);if(snap!==undefined)width=snap;image.dataset.displayWidth=String(Math.max(limits.min,Math.min(width,limits.max)));paint(state,body);};
   handle.onpointerup=event=>{if(!drag)return;event.preventDefault();const width=positive(image.dataset.displayWidth)||drag.width;drag=null;commit(state,body,width);};
   handle.onpointercancel=()=>{if(!drag)return;if(drag.original===undefined)delete image.dataset.displayWidth;else image.dataset.displayWidth=drag.original;drag=null;paint(state,body);};
   handle.ondblclick=event=>{event.preventDefault();event.stopPropagation();commit(state,body,dimensions(image,body).max);};
   handle.onkeydown=event=>{const limits=dimensions(image,body),width=wrapper.getBoundingClientRect().width,direction=side==='left'?-1:1;let next;if(event.key==='ArrowLeft')next=width-direction*10;else if(event.key==='ArrowRight')next=width+direction*10;else if(event.key==='Home')next=limits.min;else if(event.key==='End')next=limits.max;else return;event.preventDefault();event.stopPropagation();commit(state,body,next);};
  }
  const loaded=()=>{if(!image.naturalWidth)return;let changed=false;for(const [attribute,value] of [['width',image.naturalWidth],['height',image.naturalHeight]])if(!positive(image.getAttribute(attribute))){image.setAttribute(attribute,String(value));changed=true;}paint(state,body);if(changed&&body.isContentEditable)environments.get(body)?.changed();};image.addEventListener('load',loaded);loaded();
 }
}
export function bindDocumentImages(env){environments.set(env.body,env);hydrateDocumentImages(env.body);new ResizeObserver(()=>{for(const image of env.body.querySelectorAll('img')){const state=views.get(image);if(state)paint(state,env.body);}}).observe(env.body);}
