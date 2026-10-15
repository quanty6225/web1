const states=new WeakMap(),frames=new WeakMap(),bindings=new WeakMap();
const selector='div[data-diagram="true"]';
const storage=(key,value)=>{try{if(value===undefined)return localStorage.getItem(key);localStorage.setItem(key,String(value));}catch{}return null;};
const key=(block,name)=>'linear-diagram-'+name+':'+block.dataset.diagramId;
const source=block=>block.querySelector(':scope > pre > code');
const button=(name,text=name)=>{const node=document.createElement('button');node.type='button';node.setAttribute('aria-label',name);node.textContent=text;return node;};
const control=(name,tag='div')=>{const node=document.createElement(tag);node.dataset.documentControl=name;node.contentEditable='false';return node;};
function frame(container,onResult,onAction){
 const iframe=document.createElement('iframe');iframe.title='Diagram preview';iframe.setAttribute('sandbox','allow-scripts allow-same-origin');iframe.src='/static/diagram-renderer/index.html';container.append(iframe);
 const state={iframe,ready:false,request:0,text:'',onResult,onAction,timer:null};frames.set(iframe.contentWindow,state);iframe.addEventListener('load',()=>{frames.set(iframe.contentWindow,state);});return state;
}
function render(state,text){
 state.text=text;if(!state.ready)return;const request=++state.request;clearTimeout(state.timer);
 state.timer=setTimeout(()=>{if(state.iframe.isConnected)state.onResult({error:'Diagram rendering timed out. Try simplifying the diagram or reloading the page.'});},15000);
 state.iframe.contentWindow.postMessage({type:'render',request,text,theme:getComputedStyle(document.documentElement).colorScheme==='dark'?'dark':'default'},location.origin);
}
addEventListener('message',event=>{
 if(event.origin!==location.origin||!event.data?.linearDiagram)return;const state=frames.get(event.source);if(!state||!state.iframe.isConnected)return;const data=event.data;
 if(data.type==='ready'){state.ready=true;render(state,state.text);}
 else if(data.type==='rendered'&&data.request===state.request){clearTimeout(state.timer);state.onResult(data);}
 else if(data.type!=='rendered')state.onAction?.(data);
});
function transformPreview(state){const {iframe}=state.preview;iframe.style.width=state.width+'px';iframe.style.height=state.height+'px';iframe.style.transform=`translate(${state.x}px,${state.y}px) scale(${state.zoom})`;}
function navigate(url){try{const target=new URL(url,location.href);if(!['https:','http:','mailto:'].includes(target.protocol))return;location.href=target.origin===location.origin?target.href:'/external?target='+encodeURIComponent(btoa(unescape(encodeURIComponent(target.href))));}catch{}}
function focusCode(block){const code=source(block);code.focus();const range=document.createRange();range.selectNodeContents(code);range.collapse(false);getSelection().removeAllRanges();getSelection().addRange(range);}
function insertText(code,text){const selection=getSelection();if(!selection?.rangeCount||!code.contains(selection.anchorNode)||!code.contains(selection.focusNode))return;const range=selection.getRangeAt(0);range.deleteContents();const node=document.createTextNode(text);range.insertNode(node);range.setStartAfter(node);range.collapse(true);selection.removeAllRanges();selection.addRange(range);if(text.endsWith('\n')&&!code.lastElementChild?.matches('[data-diagram-sentinel]')){const br=document.createElement('br');br.dataset.diagramSentinel='true';code.append(br);}code.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:text}));}
function showState(block){
 const state=states.get(block);if(!state)return;const visible=state.visible||!!state.result?.error;
 block.dataset.sourceVisible=String(visible);block.querySelector(':scope > pre').hidden=!visible;state.container.hidden=visible;state.console.hidden=!visible;state.console.textContent=state.result?.error||'No errors found';state.console.dataset.error=String(!!state.result?.error);
 const toggle=state.toolbar.querySelector('[data-diagram-toggle]'),copy=state.toolbar.querySelector('[data-diagram-copy]');const name=visible?(state.result?.error?'Show error':'Show diagram'):'Show source';toggle.setAttribute('aria-label',state.result?.empty||!state.result?'No diagram to show':name);toggle.title=toggle.getAttribute('aria-label');toggle.textContent=name;toggle.disabled=!!state.result?.empty||!state.result;copy.setAttribute('aria-label',visible?'Copy source':'Copy diagram');copy.textContent=visible?'Copy source':'Copy diagram';copy.disabled=!source(block).textContent.trim();
 const env=state.diagramComments;if(env){let comment=state.toolbar.querySelector('[data-diagram-comment]');if(!comment){comment=button('Add comment');comment.dataset.diagramComment='';state.toolbar.append(comment);}const value=env.get(block.dataset.diagramId),count=value.threads.length;comment.hidden=visible;comment.disabled=!count&&!source(block).textContent.trim();comment.textContent=count?(value.active?'Hide':'View')+' comment'+(count>1?'s':''):'Add comment';comment.setAttribute('aria-label',comment.textContent);comment.setAttribute('aria-pressed',String(count>0&&value.active));}
}
export function hydrateDocumentDiagrams(body){
 const seen=new Set();
 for(const block of body.querySelectorAll(selector)){
  if(!block.dataset.diagramId||seen.has(block.dataset.diagramId))block.dataset.diagramId=crypto.randomUUID();seen.add(block.dataset.diagramId);block.id='diagram-'+block.dataset.diagramId;block.classList.add('document-diagram');block.spellcheck=false;
  let code=source(block);if(!code){const pre=document.createElement('pre');code=document.createElement('code');code.textContent=block.textContent;pre.append(code);block.replaceChildren(pre);}
  code.tabIndex=0;code.setAttribute('aria-label','Diagram source');code.spellcheck=false;
  let state=states.get(block);
  if(!state){
   const toolbar=control('diagram-toolbar');toolbar.className='diagram-toolbar';const copy=button('Copy source'),toggle=button('No diagram to show','Show diagram'),full=button('Fullscreen','⛶'),menu=button('Open menu','•••');copy.dataset.diagramCopy='';toggle.dataset.diagramToggle='';toolbar.append(copy,toggle,full,menu);block.prepend(toolbar);
   const container=control('diagram-preview');container.className='diagram-preview';const console=control('diagram-console');console.className='diagram-console';console.setAttribute('aria-label','Diagram errors');console.setAttribute('role','status');const resize=control('diagram-console-resize');resize.className='diagram-console-resize';resize.setAttribute('role','separator');resize.setAttribute('aria-label','Resize diagram console');console.before(resize);block.append(container,resize,console);
   state={toolbar,container,console,visible:storage(key(block,'source-visibility'))!=='false',result:null,last:null};states.set(block,state);const height=Number(storage(key(block,'console-size')))||90;console.style.height=Math.max(90,height)+'px';
   let start;resize.onpointerdown=event=>{start={y:event.clientY,height:console.offsetHeight};resize.setPointerCapture(event.pointerId);event.preventDefault();};resize.onpointermove=event=>{if(start){const value=Math.max(90,start.height+event.clientY-start.y);console.style.height=value+'px';storage(key(block,'console-size'),value);}};resize.onpointerup=()=>start=null;
   state.preview=frame(container,result=>{state.result=result;block.dataset.diagramStatus=result.error?'error':result.empty?'empty':'success';if(result.width&&result.height)state.preview.iframe.style.height=Math.max(50,Math.min(500,container.clientWidth*result.height/result.width||result.height))+'px';showState(block);},data=>{const env=bindings.get(body);if(data.type==='fullscreen')env?.fullscreen(block);else if(data.type==='link')navigate(data.url);else if(data.type==='key'&&['Delete','Backspace'].includes(data.key))env?.remove(block);});
  }
  if(code.textContent!==state.last){state.last=code.textContent;clearTimeout(state.debounce);state.debounce=setTimeout(()=>render(state.preview,state.last),180);}
  state.diagramComments=bindings.get(body)?.diagramComments;showState(block);
 }
}
export function newDiagram(text=''){
 const block=document.createElement('div');block.dataset.diagram='true';block.dataset.diagramId=crypto.randomUUID();const pre=document.createElement('pre'),code=document.createElement('code');code.textContent=text;pre.append(code);block.append(pre);return block;
}
export function convertCodeToDiagram(pre,body,changed){const block=newDiagram(pre.querySelector(':scope > code')?.textContent||pre.textContent);pre.replaceWith(block);hydrateDocumentDiagrams(body);focusCode(block);changed();}
export function bindDocumentDiagrams({body,menu,modal,closeDialog,changed,toast,serialize,diagramComments}){
 async function copy(block,rich){
  const text=source(block).textContent;let html;if(rich){const container=document.createElement('div');container.append(newDiagram(text));html=serialize(container);}else{const pre=document.createElement('pre'),code=document.createElement('code');code.textContent=text;pre.append(code);html=pre.outerHTML;}
  try{await navigator.clipboard.write([new ClipboardItem({'text/plain':new Blob([text],{type:'text/plain'}),'text/html':new Blob([html],{type:'text/html'})})]);toast(rich?'Diagram copied to clipboard':'Code contents copied to clipboard');}catch{toast('Could not copy to clipboard');}
 }
 function remove(block){const next=block.nextElementSibling;block.remove();if(!body.children.length)body.innerHTML='<p><br></p>';changed();(next||body).focus();}
 function fullscreen(block){
  const overlay=modal('Diagram','<div class="diagram-full-toolbar"></div><div class="diagram-full-layout"><div class="diagram-full-preview"></div><div class="diagram-full-divider" role="separator" aria-label="Resize diagram source"></div><div class="diagram-full-source"><textarea aria-label="Diagram source code editor" spellcheck="false"></textarea><div class="diagram-full-console-resize" role="separator" aria-label="Resize diagram console" tabindex="0"></div><div class="diagram-console" role="status" aria-label="Diagram errors"></div></div></div>',null,null);overlay.classList.add('diagram-fullscreen');
  const toolbar=overlay.querySelector('.diagram-full-toolbar'),container=overlay.querySelector('.diagram-full-preview'),pane=overlay.querySelector('.diagram-full-source'),editor=pane.querySelector('textarea'),console=pane.querySelector('.diagram-console'),divider=overlay.querySelector('.diagram-full-divider');editor.value=source(block).textContent;
  const copyButton=button('Copy source to clipboard','Copy source'),toggle=button('Hide source');toolbar.append(copyButton,toggle);copyButton.onclick=()=>copy(block,!visible);
  const state={width:1024,height:600,zoom:1,x:0,y:0};let needsFit=true,visible=states.get(block).visible||!!states.get(block).result?.error;
  const show=()=>{pane.hidden=!visible;divider.hidden=!visible;toggle.textContent=visible?'Hide source':'Show source';toggle.setAttribute('aria-label',toggle.textContent);copyButton.setAttribute('aria-label',visible?'Copy source to clipboard':'Copy diagram to clipboard');copyButton.textContent=visible?'Copy source':'Copy diagram';copyButton.disabled=!editor.value.trim();};show();
  const fit=()=>{state.zoom=Math.max(.2,Math.min((container.clientWidth-24)/state.width,(container.clientHeight-24)/state.height,1));state.x=(container.clientWidth-state.width*state.zoom)/2;state.y=(container.clientHeight-state.height*state.zoom)/2;transformPreview(state);};
  const act=data=>{if(data.type==='wheel'){if(data.zoom){state.zoom=Math.max(.2,Math.min(4,state.zoom*Math.exp(-data.y*.005)));}else{state.x-=data.x;state.y-=data.y;}transformPreview(state);}else if(data.type==='pan'){state.x+=data.x;state.y+=data.y;transformPreview(state);}else if(data.type==='key'&&data.key==='Escape')closeDialog();else if(data.type==='link')navigate(data.url);};
  state.preview=frame(container,result=>{console.textContent=result.error||'No errors found';console.dataset.error=String(!!result.error);if(result.error){visible=true;show();}if(result.width&&result.height){state.width=result.width;state.height=result.height;if(needsFit){fit();needsFit=false;}else transformPreview(state);}},act);render(state.preview,editor.value);
  toggle.onclick=()=>{visible=!visible;show();fit();};let debounce;editor.oninput=()=>{show();source(block).textContent=editor.value;hydrateDocumentDiagrams(body);changed();clearTimeout(debounce);debounce=setTimeout(()=>render(state.preview,editor.value),180);};editor.onkeydown=event=>{if(event.key==='Tab'){event.preventDefault();const start=editor.selectionStart,end=editor.selectionEnd;editor.setRangeText('  ',start,end,'end');editor.dispatchEvent(new Event('input'));}};
  container.addEventListener('wheel',event=>{event.preventDefault();act({type:'wheel',x:event.deltaX,y:event.deltaY,zoom:event.ctrlKey||event.metaKey});},{passive:false});let pan;container.onpointerdown=event=>{if(event.target===container){pan={x:event.clientX,y:event.clientY};container.setPointerCapture(event.pointerId);}};container.onpointermove=event=>{if(pan){act({type:'pan',x:event.clientX-pan.x,y:event.clientY-pan.y});pan={x:event.clientX,y:event.clientY};}};container.onpointerup=()=>pan=null;
  let resize;divider.onpointerdown=event=>{resize={x:event.clientX,width:pane.offsetWidth};divider.setPointerCapture(event.pointerId);};divider.onpointermove=event=>{if(resize){pane.style.width=Math.max(300,Math.min(overlay.clientWidth-180,resize.width+resize.x-event.clientX))+'px';fit();}};divider.onpointerup=()=>resize=null;
  const consoleResize=pane.querySelector('.diagram-full-console-resize'),heightKey='linear-diagram-modal-console-height:v1';let resizing;
  const setHeight=value=>{const height=Math.max(90,Math.min(Math.max(90,pane.clientHeight-100),value));console.style.height=height+'px';consoleResize.setAttribute('aria-valuenow',String(height));storage(heightKey,height);};consoleResize.setAttribute('aria-orientation','horizontal');consoleResize.setAttribute('aria-valuemin','90');console.style.height=Math.max(90,Number(storage(heightKey))||90)+'px';
  consoleResize.onpointerdown=event=>{resizing={y:event.clientY,height:console.offsetHeight};consoleResize.setPointerCapture(event.pointerId);event.preventDefault();};consoleResize.onpointermove=event=>{if(resizing)setHeight(resizing.height+resizing.y-event.clientY);};consoleResize.onpointerup=()=>resizing=null;consoleResize.onkeydown=event=>{if(['ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();setHeight(console.offsetHeight+(event.key==='ArrowUp'?10:-10));}};
  if(visible)editor.focus();else toggle.focus();
 }
 bindings.set(body,{fullscreen,remove,diagramComments});
 body.addEventListener('click',event=>{const block=event.target.closest(selector);if(!block||!body.contains(block))return;const target=event.target.closest('button');if(!target)return;event.preventDefault();event.stopPropagation();const state=states.get(block),name=target.getAttribute('aria-label');
  if(target.hasAttribute('data-diagram-copy'))copy(block,!state.visible&&!state.result?.error);
  else if(target.hasAttribute('data-diagram-toggle')){if(state.result?.error)state.console.scrollIntoView({block:'nearest'});else{state.visible=!state.visible;storage(key(block,'source-visibility'),state.visible);showState(block);if(state.visible)focusCode(block);}}
  else if(target.hasAttribute('data-diagram-comment')){const value=diagramComments.get(block.dataset.diagramId);if(value.threads.length)diagramComments.toggle(block.dataset.diagramId);else diagramComments.add(source(block).textContent,block.dataset.diagramId);}
  else if(name==='Fullscreen')fullscreen(block);
  else if(name==='Open menu')menu(target,[{text:'Copy link',action:async()=>{await navigator.clipboard.writeText(location.href.split('#')[0]+'#'+block.id);toast('Diagram URL copied to clipboard');}},{text:'Copy diagram',action:()=>copy(block,true)},{text:'Copy source',action:()=>copy(block,false)},null,{text:'Select',action:()=>{body.focus();const range=document.createRange();range.selectNode(block);getSelection().removeAllRanges();getSelection().addRange(range);}},{text:'Delete',action:()=>remove(block)}]);
 });
 const selected=()=>{const node=getSelection()?.anchorNode;return (node?.nodeType===1?node:node?.parentElement)?.closest(selector)?.querySelector(':scope > pre > code');};
 body.addEventListener('keydown',event=>{const code=selected();if(code&&event.key==='Enter'&&!event.ctrlKey&&!event.metaKey){event.preventDefault();insertText(code,'\n');}});
 body.addEventListener('paste',event=>{const code=selected();if(code){event.preventDefault();insertText(code,event.clipboardData.getData('text/plain'));}});
 body.addEventListener('beforeinput',event=>{const code=selected();if(code&&event.inputType==='insertText'&&event.data?.includes('\n')){event.preventDefault();insertText(code,event.data);}});
 body.addEventListener('input',()=>{hydrateDocumentDiagrams(body);changed();});
 hydrateDocumentDiagrams(body);
}
