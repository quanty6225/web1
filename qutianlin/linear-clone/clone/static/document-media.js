import {documentBodyHTML} from '/static/document-blocks.js';
import {hydrateDocumentPDF,bindDocumentPDF} from '/static/document-pdf.js';
import {hydrateDocumentFiles,bindDocumentFiles} from '/static/document-files.js';
import {hydrateDocumentImages,bindDocumentImages} from '/static/document-images.js';
const $=(selector,root=document)=>root.querySelector(selector);
const uploadURL=value=>/^\/api\/uploads\/upload_[a-f0-9]{32}(?:\?download=1)?$/.test(value||'');
export function mediaAttributes(tag,attributes){
 const safe={};const get=key=>attributes.get(key);
 if(['IMG','AUDIO','VIDEO'].includes(tag)){
  const src=get('src');if(uploadURL(src)&&!src.includes('?')){safe.src=src;if(tag==='IMG'){safe.alt=get('alt')||'';if(/^[a-zA-Z0-9_-]{1,64}$/.test(get('data-image-id')||''))safe['data-image-id']=get('data-image-id');for(const key of ['width','height','data-display-width']){const value=Number(get(key));if(Number.isFinite(value)&&value>0&&value<=10000000)safe[key]=String(value);}}else{safe.controls='';safe.preload='metadata';}}
 }
 if(tag==='A'&&get('data-attachment')==='true'&&uploadURL(get('href'))){safe['data-attachment']='true';for(const key of ['data-file-name','data-file-size','data-file-mime'])if(get(key))safe[key]=get(key).slice(0,255);}
 return safe;
}
function sizeLabel(size){const unit=size>=1048576?'MB':size>=1024?'KB':'B',divisor=unit==='MB'?1048576:unit==='KB'?1024:1;return new Intl.NumberFormat('en-US',{maximumFractionDigits:2}).format(size/divisor)+' '+unit;}
export function hydrateDocumentMedia(body){
 for(const link of body.querySelectorAll('a[data-attachment="true"]')){link.contentEditable='false';link.download=link.dataset.fileName||'';link.title=link.dataset.fileName||link.textContent;}
 hydrateDocumentPDF(body);
 hydrateDocumentFiles(body);
 hydrateDocumentImages(body);
}
export function bindDocumentMedia({body,menu,modal,closeDialog,changed,toast,replaceTitle,imageComments,targetLabel='editor contents'}){
 bindDocumentPDF({body,menu,modal,closeDialog,changed,toast});
 bindDocumentFiles({body,menu,changed});
 bindDocumentImages({body,menu,modal,closeDialog,changed,toast,imageComments});
 let pending=0;
 async function request(path,options={}){const session=await fetch('/api/session').then(response=>response.json());const response=await fetch(path,{...options,headers:{'X-Linear-CSRF':session.csrf,...options.headers}});const result=await response.json();if(!response.ok)throw Error(result.detail||result.error||'File failed to upload');return result;}
 const currentRange=()=>{const selection=getSelection();if(selection?.rangeCount&&body.contains(selection.anchorNode))return selection.getRangeAt(0).cloneRange();const range=document.createRange();range.selectNodeContents(body);range.collapse(false);return range;};
 function anchorAt(range){const anchor=document.createElement('span');anchor.dataset.documentControl='upload-anchor';if(range?.startContainer.isConnected){range.deleteContents();range.insertNode(anchor);}else body.append(anchor);return anchor;}
 function insert(node,anchor){if(anchor.isConnected)anchor.before(node);else body.append(node);hydrateDocumentMedia(body);changed();}
 function uploadedNode(file){
  if(file.render_type==='image'){const image=document.createElement('img');image.src=file.url;image.alt=file.filename;return image;}
  if(['video','audio'].includes(file.render_type)){const media=document.createElement(file.render_type);media.src=file.url;media.controls=true;media.preload='metadata';return media;}
  const link=document.createElement('a');link.href=file.download_url;link.dataset.attachment='true';link.dataset.fileName=file.filename;link.dataset.fileSize=String(file.size);link.dataset.fileMime=file.mime;link.textContent=file.filename;const size=document.createElement('small');size.textContent=' '+sizeLabel(file.size);link.append(size);return link;
 }
 async function upload(file,mode,anchor){
  const status=document.createElement('p');status.role='status';status.className='document-upload-status';status.textContent='Uploading '+file.name+'…';body.after(status);pending++;
  try{const saved=await request('/api/uploads?name='+encodeURIComponent(file.name)+'&mode='+mode,{method:'POST',headers:{'Content-Type':file.type||'application/octet-stream'},body:file});insert(uploadedNode(saved),anchor);}
  catch(error){toast('File failed to upload. '+error.message);}
  finally{pending--;status.remove();}
 }
 async function importFile(file,mode,anchor){
  try{const parsed=await request('/api/document-import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:file.name,text:await file.text()})});
   if(mode==='replace'){body.innerHTML=replaceTitle?parsed.content_html:parsed.full_content_html;if(parsed.title&&replaceTitle)replaceTitle(parsed.title);}
   else{const template=document.createElement('template');template.innerHTML=parsed.full_content_html;insert(template.content,anchor);}
   body.dispatchEvent(new Event('input',{bubbles:true}));changed();
  }catch(error){toast(error.message);}
 }
 async function filesSelected(files,media,range){
  const anchor=anchorAt(range);
  for(const file of files){
   if(!media&&/\.(md|txt)$/i.test(file.name)&&file.size<=1048576){
    await new Promise(resolve=>{let settled=false;const finish=async action=>{if(settled)return;settled=true;try{await action();}finally{resolve();}};const hasContent=!!body.innerText.trim()||!!body.querySelector('img,audio,video,ul,ol,[data-callout],.collapsible-section');const popup=menu(body,[{text:'Keep as attachment',action:()=>finish(()=>upload(file,'attachment',anchor))},...(hasContent?[{text:'Insert file contents here',action:()=>finish(()=>importFile(file,'insert',anchor))}]:[]),{text:'Replace '+targetLabel+' with file contents',action:()=>finish(()=>importFile(file,'replace',anchor))}]);const watch=new MutationObserver(()=>{if(!popup.isConnected){watch.disconnect();if(!settled){settled=true;resolve();}}});watch.observe(document.body,{childList:true});});
   }else await upload(file,media?'media':'attachment',anchor);
  }
  anchor.remove();changed();
 }
 function choose(media,range=currentRange()){
  const input=document.createElement('input');input.type='file';input.multiple=true;input.hidden=true;if(media)input.accept='image/*,video/*,audio/*';document.body.append(input);input.onchange=()=>{const files=[...input.files];input.remove();if(files.length)filesSelected(files,media,range);};input.oncancel=()=>input.remove();input.click();
 }
 body.addEventListener('copy',event=>{const selection=getSelection();if(!selection?.rangeCount||!body.contains(selection.anchorNode)||!body.contains(selection.focusNode))return;const content=document.createElement('div');content.append(selection.getRangeAt(0).cloneContents());if(!content.querySelector('img,audio,video,a[data-attachment]'))return;event.preventDefault();event.clipboardData.setData('text/html',documentBodyHTML(content));event.clipboardData.setData('text/plain',content.textContent);});
 body.addEventListener('input',()=>hydrateDocumentMedia(body));
 body.addEventListener('paste',event=>{const files=[...(event.clipboardData?.files||[])];if(!files.length)return;event.preventDefault();filesSelected(files,files.every(file=>/^(image|audio|video)\//.test(file.type)),currentRange());});
 body.addEventListener('dragover',event=>{if(event.dataTransfer?.types.includes('Files'))event.preventDefault();});
 body.addEventListener('drop',event=>{const files=[...(event.dataTransfer?.files||[])];if(!files.length)return;event.preventDefault();const range=document.caretRangeFromPoint(event.clientX,event.clientY);filesSelected(files,files.every(file=>/^(image|audio|video)\//.test(file.type)),range&&body.contains(range.startContainer)?range:currentRange());});
 body.addEventListener('click',event=>{if(event.target.closest('a[data-attachment]'))event.stopPropagation();});
 body.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.shiftKey&&event.code==='KeyU'){event.preventDefault();choose(false);}});
 addEventListener('beforeunload',event=>{if(pending){event.preventDefault();event.returnValue='';}});hydrateDocumentMedia(body);return {choose};
}
