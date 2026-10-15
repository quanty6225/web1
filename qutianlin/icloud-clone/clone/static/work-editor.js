/* Local document editing based on the documented iCloud basic workflows. */
let workEditor=null;
async function workEditorPage(app,create){
 const label=app[0].toUpperCase()+app.slice(1);
 if(create){
  root.innerHTML=header(label)+`<main class="work-chooser"><h1>${app==='keynote'?'Choose a Theme':'Choose a Template'}</h1><p>Basic editing is available in this local edition.</p><form id="work-create"><label>Name<input name="name" maxlength="255" value="Untitled" required></label><button class="work-blank" type="submit"><span aria-hidden="true">${app==='numbers'?'▦':app==='keynote'?'▱':'▤'}</span>${app==='keynote'?'Basic':'Blank'}</button><p class="error" role="alert"></p></form><button id="work-import-local" type="button">Import Local Copy</button> <a href="/${app}/">Cancel</a></main>`;
  document.querySelector('#work-import-local').onclick=()=>workImport(app);
  document.querySelector('#work-create').onsubmit=async event=>{event.preventDefault();const form=event.target,button=form.querySelector('button');button.disabled=true;try{const doc=await api('/api/work',{app,name:form.elements.name.value,parent:new URLSearchParams(location.search).get('folder')});navigate('/'+app+'/edit/?item='+encodeURIComponent(doc.id))}catch(error){form.querySelector('.error').textContent=error.message;button.disabled=false}};
  return;
 }
 let doc;
 try{doc=await api('/api/work/'+encodeURIComponent(new URLSearchParams(location.search).get('item')||''));if(doc.app!==app)throw Error('Open this document in '+doc.app+'.')}
 catch(error){root.innerHTML=header(label)+`<main class="work-chooser"><h1>Unable to Open Document</h1><p>${esc(error.message)}</p><a href="/${app}/">Back to ${label}</a></main>`;return}
 const state={app,doc,body:structuredClone(doc._editor),index:0,dirty:false,saving:null,timer:null,history:[],future:[],version:0,error:null};workEditor=state;
 root.innerHTML=header(label)+`<main class="work-editor ${app}"><nav class="work-toolbar" aria-label="Document toolbar"><a href="/${app}/" id="work-back">${label}</a><input id="work-name" aria-label="Document name" maxlength="255" value="${esc(doc.name)}"><span id="work-status" role="status">Saved</span><button id="work-save">Save</button><button id="work-undo" disabled>Undo</button><button id="work-redo" disabled>Redo</button><button id="work-download">Download a Copy</button>${app==='keynote'?'<button id="work-play">Play</button>':''}</nav><p class="work-limit">Basic editing · ${app==='numbers'?'CSV download · SUM, AVERAGE, MIN, MAX, COUNT and arithmetic':'HTML download'} · Advanced features unavailable</p><p class="work-error error" role="alert" hidden></p><div class="work-actions"></div><div class="work-surface"></div></main>`;
 const status=document.querySelector('#work-status'),errorBox=document.querySelector('.work-error');
 function remember(){state.history.push(structuredClone(state.body));if(state.history.length>30)state.history.shift();state.future=[]}
 function changed(){state.dirty=true;state.version++;state.error=null;status.textContent='Not saved';errorBox.hidden=true;clearTimeout(state.timer);state.timer=setTimeout(()=>save().catch(()=>{}),800);buttons()}
 function buttons(){document.querySelector('#work-undo').disabled=!state.history.length;document.querySelector('#work-redo').disabled=!state.future.length}
 async function save(){
  clearTimeout(state.timer);
  if(state.saving){await state.saving;if(state.dirty)return save();return}
  if(!state.dirty)return;
  const version=state.version,payload={name:document.querySelector('#work-name').value,body:structuredClone(state.body),revision:state.doc._editor_revision};
  status.textContent='Saving…';
  state.saving=(async()=>{
   try{const updated=await api('/api/work/'+doc.id,payload,'PUT');state.doc=updated;state.dirty=state.version!==version;state.error=null;status.textContent=state.dirty?'Not saved':'Saved';errorBox.hidden=true}
   catch(error){state.error=error;status.textContent='Not saved';errorBox.hidden=false;errorBox.innerHTML=esc(error.message)+' <button id="work-unsaved-copy">Download Unsaved Copy</button>';errorBox.querySelector('button').onclick=()=>localDownload(JSON.stringify({app,name:payload.name,body:state.body},null,2),'application/json',payload.name+'.json');throw error}
   finally{state.saving=null}
  })();
  await state.saving;if(state.dirty)return save();
 }
 state.save=save;
 document.querySelector('#work-save').onclick=()=>save().catch(()=>{});
 document.querySelector('#work-name').oninput=changed;
 document.querySelector('#work-back').onclick=async event=>{event.preventDefault();try{await save();navigate('/'+app+'/')}catch(error){}};
 document.querySelector('#work-download').onclick=async()=>{try{await save();const link=document.createElement('a');link.href='/api/files/'+doc.id+'/download'+(app==='numbers'?'?sheet='+state.index:'');link.click()}catch(error){}};
 document.querySelector('#work-undo').onclick=()=>{if(!state.history.length)return;state.future.push(structuredClone(state.body));state.body=state.history.pop();changed();draw()};
 document.querySelector('#work-redo').onclick=()=>{if(!state.future.length)return;state.history.push(structuredClone(state.body));state.body=state.future.pop();changed();draw()};
 function update(action){remember();action();changed();draw()}
 function draw(){
  const actions=document.querySelector('.work-actions'),surface=document.querySelector('.work-surface');
  if(app==='pages'){
   actions.innerHTML='<div role="toolbar" aria-label="Text formatting">'+[['bold','Bold'],['italic','Italic'],['underline','Underline'],['insertUnorderedList','Bulleted List'],['insertOrderedList','Numbered List']].map(([cmd,name])=>`<button data-work-format="${cmd}">${name}</button>`).join('')+'</div>';
   surface.innerHTML='<div id="work-page" class="work-paper" contenteditable="true" role="textbox" aria-label="Document text" aria-multiline="true" spellcheck="true"></div>';
   const editor=surface.querySelector('#work-page');editor.innerHTML=state.body.html;
   editor.oninput=()=>{remember();state.body.html=editor.innerHTML;changed()};
   // Plain-text paste prevents external images and active markup from entering the editor.
   editor.onpaste=event=>{event.preventDefault();document.execCommand('insertText',false,event.clipboardData.getData('text/plain'))};
   editor.ondrop=event=>event.preventDefault();
   actions.querySelectorAll('button').forEach(button=>{button.onmousedown=event=>event.preventDefault();button.onclick=()=>{editor.focus();document.execCommand(button.dataset.workFormat,false,null)}});
  }else if(app==='numbers'){
   const sheets=state.body.sheets;state.index=Math.min(state.index,sheets.length-1);const sheet=sheets[state.index];
   actions.innerHTML='<div class="work-tabs" role="tablist" aria-label="Sheets">'+sheets.map((s,i)=>`<button role="tab" aria-selected="${i===state.index}" data-work-sheet="${i}">${esc(s.name)}</button>`).join('')+'</div><button id="work-add-sheet" '+(sheets.length>=10?'disabled':'')+'>Add Sheet</button><button id="work-rename-sheet">Rename Sheet</button><button id="work-delete-sheet" '+(sheets.length===1?'disabled':'')+'>Delete Sheet</button><button id="work-add-row" '+(sheet.cells.length>=200?'disabled':'')+'>Add Row</button><button id="work-add-column" '+(sheet.cells[0].length>=26?'disabled':'')+'>Add Column</button>';
   surface.innerHTML='<div class="work-table-wrap"><table class="work-table" aria-label="Spreadsheet"><thead><tr><th></th>'+sheet.cells[0].map((_,i)=>'<th scope="col">'+String.fromCharCode(65+i)+'</th>').join('')+'</tr></thead><tbody>'+sheet.cells.map((row,r)=>'<tr><th scope="row">'+(r+1)+'</th>'+row.map((_,c)=>`<td><input data-row="${r}" data-col="${c}" aria-label="${String.fromCharCode(65+c)+(r+1)}" autocomplete="off" spellcheck="false" maxlength="2000"></td>`).join('')+'</tr>').join('')+'</tbody></table></div>';
   const inputs=[...surface.querySelectorAll('input')];
   const recalculate=()=>{if(!inputs[0]?.isConnected)return;const values=workCalculate(sheet.cells);for(const input of inputs)if(input!==document.activeElement)input.value=workFormatValue(values[+input.dataset.row][+input.dataset.col],sheet.formats?.[input.getAttribute('aria-label')]);workRefreshChart(sheet)};
   for(const input of inputs){const r=+input.dataset.row,c=+input.dataset.col;input.onfocus=()=>{state.cell={row:r,col:c};input.value=sheet.cells[r][c];input.select();workSyncCellFormat(sheet,input.getAttribute('aria-label'))};input.oninput=()=>{remember();sheet.cells[r][c]=input.value;changed();recalculate()};input.onblur=()=>setTimeout(recalculate,0);input.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();surface.querySelector(`[data-row="${r+1}"][data-col="${c}"]`)?.focus()}if(event.key==='Escape'){input.blur()}}}
   recalculate();
   actions.querySelectorAll('[data-work-sheet]').forEach(button=>button.onclick=()=>{state.index=+button.dataset.workSheet;state.cell=null;draw()});
   actions.querySelector('#work-add-sheet').onclick=()=>update(()=>{sheets.push({name:'Sheet '+(sheets.length+1),cells:Array.from({length:12},()=>Array(5).fill(''))});state.index=sheets.length-1;state.cell=null});
   actions.querySelector('#work-rename-sheet').onclick=()=>formDialog('Rename Sheet',field('name','Name',sheet.name),values=>{if(!values.name.trim()||values.name.length>100)throw Error('Enter a sheet name up to 100 characters.');update(()=>sheet.name=values.name.trim())});
   actions.querySelector('#work-delete-sheet').onclick=()=>{showDialog('Delete Sheet?',`<p>${esc(sheet.name)}</p><div class="actions"><button data-action="close">Cancel</button><button id="work-confirm-delete">Delete</button></div>`);modal.querySelector('#work-confirm-delete').onclick=()=>{closeDialog();update(()=>{sheets.splice(state.index,1);state.cell=null})}};
   actions.querySelector('#work-add-row').onclick=()=>update(()=>sheet.cells.push(Array(sheet.cells[0].length).fill('')));
   actions.querySelector('#work-add-column').onclick=()=>update(()=>sheet.cells.forEach(row=>row.push('')));
  }else{
   const slides=state.body.slides;state.index=Math.min(state.index,slides.length-1);const slide=slides[state.index];
   actions.innerHTML='<button id="work-add-slide" '+(slides.length>=100?'disabled':'')+'>Add Slide</button><button id="work-duplicate-slide" '+(slides.length>=100?'disabled':'')+'>Duplicate Slide</button><button id="work-delete-slide" '+(slides.length===1?'disabled':'')+'>Delete Slide</button><button id="work-slide-up" '+(!state.index?'disabled':'')+'>Move Up</button><button id="work-slide-down" '+(state.index===slides.length-1?'disabled':'')+'>Move Down</button>';
   surface.innerHTML='<nav class="work-slide-list" aria-label="Slide navigator">'+slides.map((s,i)=>`<button data-work-slide="${i}" aria-current="${state.index===i}">${i+1}. ${esc(s.title||'Slide')}</button>`).join('')+'</nav><div class="work-slide-area"><section class="work-slide"><textarea id="work-slide-title" aria-label="Slide title" placeholder="Title" maxlength="500"></textarea><textarea id="work-slide-body" aria-label="Slide text" placeholder="Body" maxlength="20000"></textarea></section><label class="work-notes">Presenter Notes<textarea id="work-slide-notes" aria-label="Presenter notes" maxlength="10000"></textarea></label></div>';
   for(const key of ['title','body','notes']){const input=surface.querySelector('#work-slide-'+key);input.value=slide[key];input.oninput=()=>{remember();slide[key]=input.value;changed();if(key==='title')surface.querySelector(`[data-work-slide="${state.index}"]`).textContent=(state.index+1)+'. '+(input.value||'Slide')}}
   surface.querySelectorAll('[data-work-slide]').forEach(button=>button.onclick=()=>{state.index=+button.dataset.workSlide;draw()});
   actions.querySelector('#work-add-slide').onclick=()=>update(()=>{slides.splice(++state.index,0,{title:'',body:'',notes:''})});
   actions.querySelector('#work-duplicate-slide').onclick=()=>update(()=>slides.splice(++state.index,0,structuredClone(slide)));
   actions.querySelector('#work-delete-slide').onclick=()=>{showDialog('Delete Slide?',`<p>${esc(slide.title||'Slide '+(state.index+1))}</p><div class="actions"><button data-action="close">Cancel</button><button id="work-confirm-delete">Delete</button></div>`);modal.querySelector('#work-confirm-delete').onclick=()=>{closeDialog();update(()=>slides.splice(state.index,1))}};
   for(const [id,delta] of [['up',-1],['down',1]])actions.querySelector('#work-slide-'+id).onclick=()=>update(()=>{const [moving]=slides.splice(state.index,1);state.index+=delta;slides.splice(state.index,0,moving)});
  }
  buttons();
  enhanceWorkSurface(state,{save,changed,remember,update,draw});
 }
 if(app==='keynote')document.querySelector('#work-play').onclick=async()=>{
  try{await save()}catch(error){return}let index=state.index;
  function play(){const slide=state.body.slides[index];showDialog(state.doc.name,`<section class="work-slide work-play transition-${esc(slide.transition||'none')} ${esc(slide.layout||'title-body')}" style="background:${esc(slide.background||'#ffffff')}">${slide.image?'<img src="'+esc(slide.image)+'" alt="Slide image">':''}<h1>${esc(slide.title)}</h1><p>${esc(slide.body)}</p></section><div class="actions"><button id="work-previous" ${index===0?'disabled':''}>Previous</button><span>${index+1} / ${state.body.slides.length}</span><button id="work-next" ${index===state.body.slides.length-1?'disabled':''}>Next</button><button data-action="close">Done</button></div>`);modal.querySelector('#work-previous').onclick=()=>{index--;play()};modal.querySelector('#work-next').onclick=()=>{index++;play()};modal.onkeydown=event=>{if(['ArrowRight',' ','PageDown'].includes(event.key)&&index<state.body.slides.length-1){event.preventDefault();index++;play()}else if(['ArrowLeft','PageUp'].includes(event.key)&&index>0){event.preventDefault();index--;play()}};modal.tabIndex=-1;modal.focus();modal.addEventListener('close',()=>{modal.onkeydown=null},{once:true})}
  play();
 };
 draw();
 enhanceWorkToolbar(state,{save,changed,remember,update,draw});
}
function localDownload(content,type,name){const url=URL.createObjectURL(new Blob([content],{type})),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
window.addEventListener('beforeunload',event=>{if(workEditor?.dirty||workEditor?.saving){event.preventDefault();event.returnValue=''}});
