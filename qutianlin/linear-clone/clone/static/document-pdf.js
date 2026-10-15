const cards=new WeakMap(),frames=new WeakMap(),environments=new WeakMap();
const path=link=>link.getAttribute('href').split('?')[0];
const isPDF=link=>link.dataset.fileMime==='application/pdf'||/\.pdf$/i.test(link.dataset.fileName||'');
const button=name=>{const node=document.createElement('button');node.type='button';node.textContent=name;node.setAttribute('aria-label',name);return node;};
function viewer(parent,state,mode,onMessage){
 const frame=document.createElement('iframe');frame.title=mode==='inline'?'PDF preview':'PDF viewer';frame.src='/static/pdf-renderer/index.html';frame.setAttribute('sandbox','allow-scripts allow-same-origin allow-modals allow-downloads');frame.allow='clipboard-read; clipboard-write';parent.append(frame);
 const record={frame,state,mode,onMessage};frames.set(frame.contentWindow,record);frame.onload=()=>frames.set(frame.contentWindow,record);return frame;
}
addEventListener('message',event=>{
 if(event.origin!==location.origin||!event.data?.linearPDF)return;const record=frames.get(event.source);if(!record||!record.frame.isConnected)return;const data=event.data;
 if(data.type==='ready')record.frame.contentWindow.postMessage({type:'load',url:path(record.state.link),title:record.state.link.dataset.fileName,mode:record.mode},location.origin);
 else record.onMessage(data);
});
function download(state){const anchor=document.createElement('a');anchor.href=path(state.link)+'?download=1';anchor.download=state.link.dataset.fileName||'';document.body.append(anchor);anchor.click();anchor.remove();}
async function copyLink(state,env){try{await navigator.clipboard.writeText(location.origin+path(state.link));env.toast('PDF URL copied to clipboard');}catch{env.toast('Could not copy link');}}
function fullscreen(state,env){
 const overlay=env.modal(state.link.dataset.fileName||'PDF','<div class="document-pdf-viewer"></div>',null,null);overlay.classList.add('document-pdf-fullscreen');viewer(overlay.querySelector('.document-pdf-viewer'),state,'fullscreen',data=>{if(data.type==='notice')env.toast(data.message);else if(data.type==='close')env.closeDialog();});
}
function print(state,env){
 const host=document.createElement('div');host.className='document-pdf-print-host';document.body.append(host);const timer=setTimeout(()=>host.remove(),300000);
 const close=()=>{clearTimeout(timer);host.remove();};const frame=viewer(host,state,'fullscreen',data=>{if(data.type==='loaded')frame.contentWindow.postMessage({type:'print'},location.origin);else if(data.type==='error'){env.toast('Can’t print this file\nThis file couldn’t be prepared. Download to print.');close();}else if(data.type==='notice'){env.toast(data.message);close();}else if(data.type==='print-finished')close();});
}
function actions(state,body,anchor){const env=environments.get(body);if(!env)return;
 env.menu(anchor,[...(!state.refused?[{text:'View PDF',action:()=>fullscreen(state,env)}]:[]),{text:'Download',action:()=>download(state)},{text:'Copy link',action:()=>copyLink(state,env)},...(!state.refused?[{text:'Print',action:()=>print(state,env)}]:[]),...(body.isContentEditable?[null,{text:'Delete',action:()=>{state.card.remove();if(!body.children.length)body.innerHTML='<p><br></p>';env.changed();}}]:[])]);
}
export function hydrateDocumentPDF(body){
 for(const link of body.querySelectorAll('a[data-attachment="true"]')){
  if(!isPDF(link)||Number(link.dataset.fileSize)<=0||matchMedia('(pointer:coarse)').matches)continue;
  let state=cards.get(link);if(state)continue;const card=document.createElement('div');card.dataset.pdfCard='true';card.className='document-pdf-card';card.contentEditable='false';link.before(card);card.append(link);link.removeAttribute('download');const controls=document.createElement('div');controls.dataset.documentControl='pdf-actions';controls.className='document-pdf-actions';card.append(controls);
  const open=button('View PDF'),save=button('Download'),menu=button('Open menu');controls.append(open,save,menu);state={card,link,refused:false,frame:null};cards.set(link,state);
  const env=()=>environments.get(body);open.onclick=event=>{event.preventDefault();event.stopPropagation();if(env())fullscreen(state,env());};save.onclick=event=>{event.preventDefault();event.stopPropagation();download(state);};menu.onclick=event=>{event.preventDefault();event.stopPropagation();actions(state,body,menu);};link.onclick=event=>{event.preventDefault();event.stopPropagation();};card.ondblclick=event=>{if(!event.target.closest('button')&&!state.refused&&env()){event.preventDefault();event.stopPropagation();fullscreen(state,env());}};card.oncontextmenu=event=>{event.preventDefault();event.stopPropagation();actions(state,body,card);};
  if(body.getAttribute('aria-label')==='Document content'){
   const preview=document.createElement('div');preview.dataset.documentControl='pdf-preview';preview.className='document-pdf-preview';card.append(preview);
   state.frame=viewer(preview,state,'inline',data=>{if(data.type==='loaded'){card.dataset.pdfStatus='ready';const width=preview.clientWidth||600;state.frame.style.height=Math.max(96,Math.min(480,(width-16)*data.height/data.width+16))+'px';card.dataset.pdfPages=String(data.pages);}else if(data.type==='error'){card.dataset.pdfStatus=data.reason;state.refused=data.reason!=='failed';open.disabled=state.refused;}else if(data.type==='open'&&!state.refused&&env())fullscreen(state,env());});
  }
 }
}
export function bindDocumentPDF(env){environments.set(env.body,env);hydrateDocumentPDF(env.body);}
