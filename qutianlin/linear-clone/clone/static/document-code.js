import highlight from '/static/document-editor/highlight.js';
import {convertCodeToDiagram} from '/static/document-diagrams.js';
let languages=[],showNumbers=true;
const catalog=fetch('/static/document-editor/code-languages.json').then(r=>r.json()).then(rows=>languages=rows);
const blocks=body=>[...body.querySelectorAll('pre')].filter(pre=>!pre.closest('[data-diagram="true"]'));
const language=id=>languages.find(row=>row.id===id||row.aliases.includes(id));
const wrapKey=id=>'linear-codeblock-line-wrap:'+id;
const collapsed=new Map();
const predictions=new WeakMap();let worker,requestId=0;const requests=new Map();
const measured=new WeakSet();
function measureLines(pre){
 const code=pre.querySelector(':scope > code'),gutter=pre.querySelector('[data-document-control="code-lines"]');if(!code||!gutter)return;const style=getComputedStyle(code),height=parseFloat(style.lineHeight)||20;
 const max=pre.dataset.collapsed==='true'?height*15+'px':'';if(code.style.maxHeight!==max)code.style.maxHeight=max;if(gutter.style.maxHeight!==max)gutter.style.maxHeight=max;
 pre.style.setProperty('--document-code-line',height+'px');gutter.style.fontFamily=style.fontFamily;gutter.style.fontSize=style.fontSize;gutter.style.lineHeight=style.lineHeight;
 const nodes=[];let offset=0;const walker=document.createTreeWalker(code,NodeFilter.SHOW_TEXT);let current;while(current=walker.nextNode()){nodes.push({node:current,start:offset,end:offset+current.length});offset+=current.length;}
 let start=0;gutter.replaceChildren();for(const [index,line] of code.textContent.split('\n').entries()){const span=document.createElement('span');span.textContent=index+1;let lineHeight=height;if(line.length){const first=nodes.find(item=>item.end>start),last=nodes.find(item=>item.end>=start+line.length);if(first&&last){const range=document.createRange();range.setStart(first.node,start-first.start);range.setEnd(last.node,start+line.length-last.start);lineHeight=Math.max(height,range.getBoundingClientRect().height);}}span.style.display='block';span.style.height=lineHeight+'px';gutter.append(span);start+=line.length+1;}
}
function predict(text){
 if(text.startsWith('diff --git a/'))return Promise.resolve('diff');if(text.length<20)return Promise.resolve(null);
 if(!worker){worker=new Worker('/static/document-editor/code-language-worker.js');worker.onmessage=event=>{const pending=requests.get(event.data.id);requests.delete(event.data.id);if(event.data.error)pending?.reject(Error(event.data.error));else pending?.resolve(event.data.results);};worker.onerror=()=>{for(const pending of requests.values())pending.reject(Error('Code language detection failed'));requests.clear();worker.terminate();worker=null;};}
 return new Promise((resolve,reject)=>{const id=++requestId;requests.set(id,{resolve,reject});worker.postMessage({id,text});}).then(results=>{const row=results.find(item=>languages.some(lang=>lang.aliases.includes(item.languageId)));if(!row)return null;const found=language(row.languageId);const threshold=Math.min(.25,Math.max(found.id==='markdown'?.15:.05,text.length*.00025));return row.confidence>threshold?found.id:null;});
}
function wrapState(id){try{return localStorage.getItem(wrapKey(id))==='true';}catch{return false;}}
function selectionOffsets(code){
 const selection=getSelection();if(!selection?.rangeCount||!code.contains(selection.anchorNode)||!code.contains(selection.focusNode))return null;
 const offset=(node,index)=>{const range=document.createRange();range.selectNodeContents(code);range.setEnd(node,index);return range.toString().length;};
 return [offset(selection.anchorNode,selection.anchorOffset),offset(selection.focusNode,selection.focusOffset)];
}
function restoreOffsets(code,offsets){
 if(!offsets)return;const point=offset=>{const walker=document.createTreeWalker(code,NodeFilter.SHOW_TEXT);let node,last;while(node=walker.nextNode()){last=node;if(offset<=node.length)return [node,offset];offset-=node.length;}return last?[last,last.length]:[code,0];};
 getSelection().setBaseAndExtent(...point(offsets[0]),...point(offsets[1]));
}
function paint(pre){
 if(pre.closest('[data-diagram="true"]'))return;
 const code=pre.querySelector(':scope > code');if(!code)return;
 const text=code.textContent,selected=selectionOffsets(code),id=pre.dataset.codeLanguage||'auto';let result,prediction=predictions.get(pre);
 if(id==='auto'&&(!prediction||prediction.text!==text)){clearTimeout(prediction?.timer);prediction={text,language:null};predictions.set(pre,prediction);prediction.timer=setTimeout(()=>predict(text).then(detected=>{if(predictions.get(pre)!==prediction||!pre.isConnected)return;prediction.language=detected;paint(pre);}).catch(()=>{}),250);}
 const effective=id==='auto'?prediction?.language:id;
 try{result=highlight.highlight(text,{language:language(effective)?.id||'plaintext',ignoreIllegals:true});}catch{result={value:null};}
 const markup=result.value==null?null:result.value+(!text||text.endsWith('\n')?'<br data-code-sentinel="true">':'');
 if(markup!=null&&code.innerHTML!==markup){code.innerHTML=markup;restoreOffsets(code,selected);}
 const control=pre.querySelector('[data-document-control="code"]');if(!control)return;
 control.querySelector('[aria-label="Change language"]').textContent=language(effective)?.name||'Plaintext';
 const count=text.split('\n').length,gutter=pre.querySelector('[data-document-control="code-lines"]');
 gutter.hidden=!showNumbers;
 pre.dataset.lineNumbers=String(showNumbers);pre.dataset.lineWrap=String(wrapState(pre.dataset.codeId));
 const isCollapsed=collapsed.get(pre.dataset.codeId)??count>=30;pre.dataset.collapsed=String(count>=30&&isCollapsed);
 const button=pre.querySelector('[data-document-control="code-collapse"]');button.hidden=count<30;button.textContent=isCollapsed?'Expand ('+count+' lines)':'Collapse';button.setAttribute('aria-expanded',String(!isCollapsed));
 measureLines(pre);
}
export function hydrateDocumentCode(body){
 for(const pre of blocks(body)){
  pre.classList.add('document-code-block');pre.dataset.codeId||=crypto.randomUUID();
  let code=pre.querySelector(':scope > code');if(!code){code=document.createElement('code');code.textContent=pre.textContent;pre.replaceChildren(code);}
  pre.dataset.codeLanguage||=code.dataset.language||[...code.classList].find(name=>name.startsWith('language-'))?.slice(9)||'auto';
  code.removeAttribute('contenteditable');code.tabIndex=0;code.spellcheck=false;code.setAttribute('aria-label','Code content');
  if(!pre.querySelector('[data-document-control="code"]')){
   const toolbar=document.createElement('span');toolbar.dataset.documentControl='code';toolbar.className='document-code-controls';toolbar.contentEditable='false';
   for(const name of ['Change language','Display options','Copy content']){const button=document.createElement('button');button.type='button';button.setAttribute('aria-label',name);button.textContent=({'Change language':'Plaintext','Display options':'☷','Copy content':'⧉'})[name];toolbar.append(button);}pre.prepend(toolbar);
   const gutter=document.createElement('span');gutter.dataset.documentControl='code-lines';gutter.className='document-code-lines';gutter.setAttribute('aria-hidden','true');gutter.contentEditable='false';code.before(gutter);
   const collapse=document.createElement('button');collapse.type='button';collapse.dataset.documentControl='code-collapse';collapse.contentEditable='false';pre.append(collapse);
  }
  if(!measured.has(code)){measured.add(code);new ResizeObserver(()=>{if(pre.isConnected)measureLines(pre);}).observe(code);new MutationObserver(()=>{if(pre.isConnected)measureLines(pre);}).observe(code,{attributes:true,attributeFilter:['style']});}
  paint(pre);
 }
}
export function bindDocumentCode({body,menu,modal,closeDialog,changed,toast,serialize}){
 let allSelected=false;
 body.addEventListener('keydown',event=>{const key=event.key.toLowerCase(),modifier=event.ctrlKey||event.metaKey;if(modifier&&key==='a')allSelected=true;else if(!['control','meta','shift','alt'].includes(key)&&!(modifier&&key==='c'))allSelected=false;});
 body.addEventListener('mousedown',()=>allSelected=false);body.addEventListener('beforeinput',()=>allSelected=false);
 document.addEventListener('copy',event=>{if(!allSelected||!blocks(body).length||!(document.activeElement===body||body.contains(document.activeElement)))return;const html=serialize(body),plain=document.createElement('div');plain.innerHTML=html;event.preventDefault();event.clipboardData.setData('text/html',html);event.clipboardData.setData('text/plain',plain.textContent);},true);
 const selectedCode=()=>{const node=getSelection()?.anchorNode,pre=(node?.nodeType===1?node:node?.parentElement)?.closest('pre');return pre&&!pre.closest('[data-diagram="true"]')?pre.querySelector(':scope > code'):null;};
 function insertPlain(code,text){const selection=getSelection();if(!selection?.rangeCount)return;const range=selection.getRangeAt(0);range.deleteContents();const node=document.createTextNode(text);range.insertNode(node);range.setStartAfter(node);range.collapse(true);selection.removeAllRanges();selection.addRange(range);paint(code.closest('pre'));body.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:text}));changed();}
 async function setting(key,value){const session=await fetch('/api/session').then(r=>r.json());const r=await fetch('/api/settings',{method:'PUT',headers:{'Content-Type':'application/json','X-Linear-CSRF':session.csrf},body:JSON.stringify({route:'/qqq153/settings/account/preferences',key,value})});if(!r.ok)throw Error('Could not save code display options.');}
 Promise.all([catalog,fetch('/api/settings?route='+encodeURIComponent('/qqq153/settings/account/preferences')).then(r=>r.json())]).then(([,settings])=>{showNumbers=settings.showCodeBlockLineNumbers!==false;hydrateDocumentCode(body);}).catch(error=>toast(error.message));
 function languageMenu(pre,anchor){catalog.then(()=>{const popup=menu(anchor,[{text:'Auto detect',selected:pre.dataset.codeLanguage==='auto',action:()=>choose('auto')},...languages.map(row=>({text:row.name,selected:pre.dataset.codeLanguage===row.id,action:()=>choose(row.id)})),{text:'Mermaid',action:()=>convertCodeToDiagram(pre,body,changed)}],'Filter…');const item=[...popup.querySelectorAll('[role=menuitem]')].find(item=>item.textContent==='Mermaid'),search=popup.querySelector('input');item.hidden=true;search.addEventListener('input',()=>{item.hidden=!search.value.trim()||!'mermaid'.includes(search.value.toLowerCase());});});function choose(id){pre.dataset.codeLanguage=id;paint(pre);changed();}}
 async function copy(pre){
  const code=pre.querySelector(':scope > code'),text=code.textContent,container=document.createElement('pre');container.dataset.codeLanguage=pre.dataset.codeLanguage;const plain=document.createElement('code');plain.textContent=text;container.append(plain);
  try{await navigator.clipboard.write([new ClipboardItem({'text/plain':new Blob([text],{type:'text/plain'}),'text/html':new Blob([container.outerHTML],{type:'text/html'})})]);toast('Code contents copied to clipboard');}catch{toast('Code contents could not be copied to clipboard');}
 }
 body.addEventListener('mousedown',event=>{if(event.target.closest('[data-document-control="code"]'))event.preventDefault();});
 body.addEventListener('click',event=>{
  const pre=event.target.closest('pre');if(!pre||!body.contains(pre)||pre.closest('[data-diagram="true"]'))return;const button=event.target.closest('button');
  if(button){event.preventDefault();event.stopPropagation();const name=button.getAttribute('aria-label');
   if(name==='Change language')languageMenu(pre,button);
   else if(name==='Copy content')copy(pre);
   else if(name==='Display options'){
    const overlay=modal('Display options','<label class="document-code-option">Wrap lines<input type="checkbox" name="wrap" aria-label="Wrap lines"></label><label class="document-code-option">Show line numbers<input type="checkbox" name="numbers" aria-label="Show line numbers"></label>',null,null);
    const wrap=overlay.querySelector('[name=wrap]'),numbers=overlay.querySelector('[name=numbers]');wrap.checked=wrapState(pre.dataset.codeId);numbers.checked=showNumbers;
    wrap.onchange=()=>{try{localStorage.setItem(wrapKey(pre.dataset.codeId),String(wrap.checked));paint(pre);}catch(error){toast(error.message);}};
    numbers.onchange=async()=>{numbers.disabled=true;try{await setting('showCodeBlockLineNumbers',numbers.checked);showNumbers=numbers.checked;hydrateDocumentCode(body);}catch(error){numbers.checked=showNumbers;toast(error.message);}finally{numbers.disabled=false;}};
   }else if(button.dataset.documentControl==='code-collapse'){collapsed.set(pre.dataset.codeId,pre.dataset.collapsed==='true'?false:true);paint(pre);}
  }else if(pre.dataset.collapsed==='true'){collapsed.set(pre.dataset.codeId,false);paint(pre);}
 });
 body.addEventListener('input',event=>{const pre=event.target.closest('pre');if(pre){paint(pre);changed();}});
 body.addEventListener('paste',event=>{const code=selectedCode();if(!code)return;event.preventDefault();event.stopPropagation();insertPlain(code,event.clipboardData.getData('text/plain'));});
 body.addEventListener('beforeinput',event=>{const code=selectedCode();if(code&&event.inputType==='insertText'&&event.data?.includes('\n')){event.preventDefault();insertPlain(code,event.data);}});
 body.addEventListener('copy',event=>{const selection=getSelection();if(!selection?.rangeCount||!body.contains(selection.anchorNode)||!body.contains(selection.focusNode))return;const fragment=document.createElement('div');fragment.append(selection.getRangeAt(0).cloneContents());if(!fragment.querySelector('pre')&&!selection.anchorNode?.parentElement?.closest('pre'))return;event.preventDefault();event.clipboardData.setData('text/html',serialize(fragment));fragment.querySelectorAll('[data-document-control]').forEach(node=>node.remove());event.clipboardData.setData('text/plain',fragment.textContent);});
 body.addEventListener('keydown',event=>{
  const selection=getSelection(),node=selection?.anchorNode,pre=(node?.nodeType===1?node:node?.parentElement)?.closest('pre')||event.target.closest('pre');if(!pre||!body.contains(pre)||pre.closest('[data-diagram="true"]'))return;
  if((event.ctrlKey||event.metaKey)&&event.shiftKey&&(event.code==='Backslash'||event.key==='\\'||event.key==='|')){event.preventDefault();languageMenu(pre,pre.querySelector('[aria-label="Change language"]'));}
  else if(event.key==='Enter'&&!event.ctrlKey&&!event.metaKey){event.preventDefault();insertPlain(pre.querySelector(':scope > code'),'\n');}
 });
 hydrateDocumentCode(body);
}
