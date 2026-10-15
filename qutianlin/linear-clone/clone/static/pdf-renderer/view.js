import {getDocument,GlobalWorkerOptions} from './vendor/pdf.min.mjs';
GlobalWorkerOptions.workerSrc='/static/pdf-renderer/vendor/pdf.worker.min.mjs';
const root=document.querySelector('main'),toolbar=document.querySelector('nav'),status=document.querySelector('[role=status]');
const steps=[50,75,100,125,150,200,300,400],messages={password:'This file is password protected. Download to view.',pageLimit:'This file has too many pages to preview. Download to view.',size:'This file is too large to preview. Download to view.',invalid:'This file couldn’t be displayed. Download to view.',failed:'This file couldn’t be displayed. Download to view.'};
let file,title,mode,pdf,loading,pages=[],zoom=100,current=1,observer,serial=0,printing=false;
const send=value=>parent.postMessage({linearPDF:true,...value},location.origin);
const action=(name,fn,text=name)=>{const button=document.createElement('button');button.type='button';button.textContent=text;button.setAttribute('aria-label',name);button.onclick=fn;toolbar.append(button);return button;};
let zoomOut,zoomIn,previous,next,pageLabel,zoomLabel,printButton;
function scaleFor(page,requested){const box=page.getViewport({scale:1});return Math.min(requested,Math.sqrt(16777216/(box.width*box.height)),16384/Math.max(box.width,box.height));}
function failure(error){return error?.reason||({PasswordException:'password',InvalidPDFException:'invalid'})[error?.name]||'failed';}
async function readFile(url){
 const response=await fetch(url);if(!response.ok)throw Error('File could not be loaded');const lengthHeader=response.headers.get('content-length'),length=Number(lengthHeader);if(length>52428800){await response.body?.cancel();throw {reason:'size'};}
 // Our authenticated upload endpoint supplies exact, uncompressed lengths and
 // enforces its own upload bound. Consume these responses to completion through
 // the browser's body reader; retain a bounded stream path for unknown lengths.
 if(lengthHeader!==null&&Number.isSafeInteger(length)&&length>=0&&!response.headers.get('content-encoding')){const data=new Uint8Array(await response.arrayBuffer());if(data.byteLength>52428800)throw {reason:'size'};return data;}
 const reader=response.body.getReader(),chunks=[];let size=0;for(;;){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>52428800){await reader.cancel();throw {reason:'size'};}chunks.push(value);}
 await reader.closed;reader.releaseLock();const data=new Uint8Array(size);let offset=0;for(const chunk of chunks){data.set(chunk,offset);offset+=chunk.byteLength;}return data;
}
async function load(){
 const generation=++serial;document.body.dataset.state='loading';status.textContent='';root.replaceChildren();observer?.disconnect();pages=[];
 try{
  const data=await readFile(file);if(generation!==serial)return;
  loading=getDocument({data,cMapUrl:'/static/pdf-renderer/vendor/cmaps/',cMapPacked:true,standardFontDataUrl:'/static/pdf-renderer/vendor/standard_fonts/',wasmUrl:'/static/pdf-renderer/vendor/wasm/',iccUrl:'/static/pdf-renderer/vendor/iccs/',maxImageSize:64000000,isEvalSupported:false,useWorkerFetch:true});pdf=await loading.promise;
  if(pdf.numPages>500)throw {reason:'pageLimit'};
  const count=mode==='inline'?1:pdf.numPages;const sizes=[];for(let number=1;number<=pdf.numPages;number++){const page=await pdf.getPage(number);sizes.push(page.getViewport({scale:1}));if(number<=count){const article=document.createElement('article');article.setAttribute('role','img');article.setAttribute('aria-label',title+' · Page '+number+' of '+pdf.numPages);article.dataset.page=String(number);root.append(article);pages.push({page,article,number,task:null,painted:null,visible:false});}}
  if(generation!==serial)return;document.body.dataset.state='ready';const widest=Math.max(...sizes.map(box=>box.width));zoom=Math.min(100,Math.min(1084,root.clientWidth-(mode==='inline'?16:32))/(widest*96/72)*100);
  observer=new IntersectionObserver(entries=>{for(const entry of entries){const item=pages.find(row=>row.article===entry.target);if(item){item.visible=entry.isIntersecting;if(item.visible)paint(item);else if(mode!=='inline'){item.task?.cancel();item.article.replaceChildren();item.painted=null;}}}},{root,rootMargin:'700px'});
  layout();for(const item of pages)observer.observe(item.article);await paint(pages[0]);send({type:'loaded',pages:pdf.numPages,width:widest,height:sizes[0].height,mode});updateControls();
 }catch(error){if(generation!==serial)return;const reason=failure(error);document.body.dataset.state='error';status.textContent=messages[reason];root.replaceChildren();toolbar.hidden=true;send({type:'error',reason,message:messages[reason]});await loading?.destroy().catch(()=>{});pdf=null;}
}
function layout(){for(const item of pages){const box=item.page.getViewport({scale:zoom/100*96/72});item.article.style.width=box.width+'px';item.article.style.height=box.height+'px';if(item.visible)paint(item);}if(mode!=='inline'&&pages.length)root.style.paddingBottom=Math.max(16,root.clientHeight-pages.at(-1).article.offsetHeight-32)+'px';updateControls();}
async function paint(item){
 if(!item||!item.article.isConnected)return;const requested=zoom/100*96/72*Math.min(devicePixelRatio||1,2),scale=scaleFor(item.page,requested);if(item.painted===scale)return;
 item.task?.cancel();const canvas=document.createElement('canvas'),viewport=item.page.getViewport({scale});canvas.width=Math.max(1,Math.floor(viewport.width));canvas.height=Math.max(1,Math.floor(viewport.height));item.article.replaceChildren(canvas);item.painted=scale;
 const task=item.page.render({canvas,viewport});item.task=task;try{await task.promise;canvas.dataset.rendered='true';}catch(error){if(error.name!=='RenderingCancelledException'){item.painted=null;send({type:'error',reason:'failed',message:messages.failed});}}finally{if(item.task===task)item.task=null;}
}
function updateControls(){if(!zoomOut)return;zoomOut.disabled=!pdf||zoom<=50;zoomIn.disabled=!pdf||zoom>=400;zoomLabel.textContent=Math.round(zoom)+'%';previous.disabled=!pdf||current<=1;next.disabled=!pdf||current>=pdf.numPages;pageLabel.textContent=pdf?'Page '+current+' of '+pdf.numPages:'';previous.hidden=next.hidden=pageLabel.hidden=!pdf||pdf.numPages<=1;printButton.disabled=!pdf||printing;}
function setZoom(value,point={x:root.clientWidth/2,y:root.clientHeight/2}){
 if(!pdf)return;value=Math.max(50,Math.min(400,value));const y=root.scrollTop+point.y,item=[...pages].reverse().find(item=>item.article.offsetTop<=y)||pages[0],ratio=(y-item.article.offsetTop)/item.article.offsetHeight,xratio=(root.scrollLeft+point.x)/root.scrollWidth;
 zoom=value;layout();root.scrollTop=item.article.offsetTop+ratio*item.article.offsetHeight-point.y;root.scrollLeft=xratio*root.scrollWidth-point.x;updatePage();
}
function updatePage(){if(!pages.length)return;current=([...pages].reverse().find(item=>item.article.offsetTop<=root.scrollTop+17)||pages[0]).number;updateControls();}
function stepPage(direction){const item=pages[current-1+direction];if(item){root.scrollTop=item.article.offsetTop-16;current=item.number;updateControls();}}
async function print(){
 if(!pdf||printing)return;if(pdf.numPages>100){send({type:'notice',message:'Can’t print this file\nThis file has too many pages. Download to print.'});return;}printing=true;updateControls();const frame=document.createElement('iframe');frame.dataset.print='';frame.title='Print PDF';document.body.append(frame);const urls=[];let timeout;
 const cleanup=()=>{clearTimeout(timeout);frame.remove();urls.forEach(url=>URL.revokeObjectURL(url));};
 try{const items=[];let area=0;for(let number=1;number<=pdf.numPages;number++){const page=await pdf.getPage(number),box=page.getViewport({scale:1});items.push(page);area+=box.width*box.height;}const requested=Math.min(150/72,Math.sqrt(80000000/area)),doc=frame.contentDocument,style=doc.createElement('link');style.rel='stylesheet';style.href='/static/pdf-renderer/print.css';doc.head.append(style);await new Promise((resolve,reject)=>{style.onload=resolve;style.onerror=reject;});
  for(const page of items){const canvas=document.createElement('canvas'),viewport=page.getViewport({scale:scaleFor(page,requested)});canvas.width=Math.floor(viewport.width);canvas.height=Math.floor(viewport.height);await page.render({canvas,viewport,intent:'print'}).promise;const blob=await new Promise(resolve=>canvas.toBlob(resolve));if(!blob)throw Error('Print page could not be encoded');const url=URL.createObjectURL(blob);urls.push(url);const image=doc.createElement('img');image.src=url;doc.body.append(image);await image.decode();}
  frame.contentWindow.addEventListener('afterprint',()=>{cleanup();send({type:'print-finished'});});timeout=setTimeout(cleanup,300000);frame.contentWindow.focus();send({type:'print-ready',pages:items.length});frame.contentWindow.print();
 }catch{cleanup();send({type:'notice',message:'Can’t print this file\nThis file couldn’t be prepared. Download to print.'});}finally{printing=false;updateControls();}
}
function controls(){toolbar.replaceChildren();if(mode==='inline'){toolbar.hidden=true;return;}toolbar.hidden=false;zoomOut=action('Zoom out',()=>setZoom([...steps].reverse().find(value=>value<zoom)),'−');zoomLabel=document.createElement('span');toolbar.append(zoomLabel);zoomIn=action('Zoom in',()=>setZoom(steps.find(value=>value>zoom)),'+');previous=action('Previous page',()=>stepPage(-1),'‹');pageLabel=document.createElement('span');toolbar.append(pageLabel);next=action('Next page',()=>stepPage(1),'›');const download=document.createElement('a');download.href=file+'?download=1';download.download=title;download.textContent='Download';toolbar.append(download);action('Copy link',async()=>{try{await navigator.clipboard.writeText(location.origin+file);send({type:'notice',message:'PDF URL copied to clipboard'});}catch{send({type:'notice',message:'Could not copy link'});}});printButton=action('Print',print);updateControls();}
addEventListener('message',event=>{
 if(event.source!==parent||event.origin!==location.origin)return;const data=event.data;
 if(data?.type==='load'&&/^\/api\/uploads\/upload_[a-f0-9]{32}$/.test(data.url)&&!file){file=data.url;title=String(data.title||'PDF');mode=data.mode==='inline'?'inline':'fullscreen';document.body.dataset.mode=mode;controls();load();}
 else if(data?.type==='print')print();else if(data?.type==='retry'&&!pdf)load();
});
root.addEventListener('scroll',updatePage,{passive:true});root.addEventListener('dblclick',()=>{if(mode==='inline')send({type:'open'});});
new ResizeObserver(()=>{if(pdf&&pages.length)layout();}).observe(root);
root.addEventListener('wheel',event=>{if(mode!=='inline'&&(event.ctrlKey||event.metaKey)){event.preventDefault();const box=root.getBoundingClientRect();setZoom(zoom*Math.exp(-event.deltaY*.005),{x:event.clientX-box.left,y:event.clientY-box.top});}},{passive:false});
let drag;root.addEventListener('pointerdown',event=>{if(mode!=='inline'&&event.button===0){drag={x:event.clientX,y:event.clientY,left:root.scrollLeft,top:root.scrollTop};root.setPointerCapture(event.pointerId);}});root.addEventListener('pointermove',event=>{if(drag){root.scrollLeft=drag.left+drag.x-event.clientX;root.scrollTop=drag.top+drag.y-event.clientY;}});root.addEventListener('pointerup',()=>drag=null);
addEventListener('keydown',event=>{if(event.key==='Escape')send({type:'close'});if(mode!=='inline'&&['PageDown','PageUp'].includes(event.key)){event.preventDefault();stepPage(event.key==='PageDown'?1:-1);}});
send({type:'ready'});
