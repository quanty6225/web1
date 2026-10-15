/* Notes3 pane thresholds and navigation; resize moves no editor DOM. */
function noteLayoutMode(){
 if(matchMedia('(min-width:1195px)').matches)return 'three';
 if(matchMedia('(min-width:668px) and (min-aspect-ratio:1/1)').matches)return 'two';
 return matchMedia('(min-width:668px)').matches?'overlay':'one';
}
function noteView(){return history.state?.notesView||{pane:'editor',side:'list',popup:false}}
function noteViewState(value){return {...history.state,notesView:{...noteView(),...value}}}
function noteFrame(side,tools){
 const folder=appData.folders.find(f=>f.id===selectedNoteFolder()),trash=location.pathname==='/notes/recently-deleted/';
 const title=trash?'Recently Deleted':folder?.name||'All iCloud';
 root.innerHTML=header('Notes')+`<div class="app-layout note-columns notes-layout"><div class="note-popup-backdrop" data-note-navigation="dismiss" aria-hidden="true" hidden></div><div class="note-navigation"><aside id="note-folders" aria-label="Folders">${side}</aside><section class="note-list-pane" aria-label="Notes list"><nav class="note-list-toolbar" aria-label="Notes list navigation"><button data-note-navigation="folders" aria-label="Back to folders">‹ Folders</button><strong>${esc(title)}</strong><button data-op="new-note" aria-label="Create a note">▧</button></nav><div class="note-search-field"><input id="note-search" aria-label="Search notes" placeholder="Search"></div><section id="note-list"></section></section></div><main class="workspace note-editor-pane" aria-label="Note"><div class="toolbar note-editor-toolbar"><button data-note-navigation="list" aria-label="Back to notes">‹</button>${tools}</div><section id="note-detail"></section></main></div>`;
 document.querySelector('#note-search').value=history.state?.noteSearch||'';
 history.replaceState(noteViewState({}), '',location.href);
 applyNoteLayout();
}
function noteFocusable(container){return [...container.querySelectorAll('a[href],button,input,select,textarea,[tabindex="0"]')].filter(el=>!el.disabled&&!el.closest('[hidden],[inert]')&&el.getClientRects().length)}
function applyNoteLayout({focus=false}={}){
 const layout=document.querySelector('.notes-layout');if(!layout)return;
 let state=noteView();const mode=noteLayoutMode(),nav=layout.querySelector('.note-navigation'),folders=layout.querySelector('#note-folders'),list=layout.querySelector('.note-list-pane'),editor=layout.querySelector('.note-editor-pane');
 const oldMode=layout.dataset.noteMode;
 if(oldMode&&oldMode!==mode){history.replaceState(noteViewState({pane:'editor',side:'list',popup:false}),'',location.href);state=noteView()}
 layout.dataset.noteMode=mode;layout.dataset.notePane=state.pane;layout.dataset.noteSide=state.side;
 const popup=mode==='overlay'&&state.popup;
 nav.hidden=mode==='one'?state.pane==='editor':mode==='overlay'?!popup:false;
 folders.hidden=mode==='three'?false:mode==='one'?state.pane!=='folders':state.side!=='folders';
 list.hidden=mode==='three'?false:mode==='one'?state.pane!=='list':state.side!=='list';
 editor.hidden=mode==='one'&&state.pane!=='editor';editor.inert=popup;
 root.querySelector('header').inert=popup;
 layout.querySelector('.note-popup-backdrop').hidden=!popup;
 if(popup){nav.setAttribute('role','dialog');nav.setAttribute('aria-modal','true');nav.setAttribute('aria-label','Folders and notes')}
 else{nav.removeAttribute('role');nav.removeAttribute('aria-modal');nav.removeAttribute('aria-label')}
 const listToolbar=layout.querySelector('.note-list-toolbar');listToolbar.hidden=mode==='three';
 listToolbar.querySelector('[data-op="new-note"]').hidden=mode!=='one'||location.pathname==='/notes/recently-deleted/';
 layout.querySelector('[data-note-navigation="list"]').hidden=mode==='three'||mode==='two';
 const share=editor.querySelector('[data-op="share-note"]');if(share)share.hidden=mode==='one';
 // Preserve the caret whenever its region remains visible across resize.
 if(!modal.open&&(focus||oldMode&&oldMode!==mode&&document.activeElement?.closest('[hidden],[inert]'))){
  const region=popup?nav:mode==='one'&&state.pane!=='editor'?nav:editor;
  const target=region.querySelector('.note-row.active')||noteFocusable(region)[0];
  if(target&&!target.closest('[hidden],[inert]'))target.focus();else noteFocusable(region)[0]?.focus();
 }
}
async function navigateNotes(url,state){
 if(root.inert)return;root.inert=true;
 try{await flushNoteSave(activeEntity?.id);history.pushState(state,'',url);await notesPage()}
 finally{root.inert=false}
}
async function noteNavigation(action){
 const layout=document.querySelector('.notes-layout');if(!layout||root.inert)return;
 root.inert=true;
 try{
  await flushNoteSave(activeEntity?.id);
  const mode=noteLayoutMode(),next=action==='folders'?{pane:'folders',side:'folders',popup:mode==='overlay'}:action==='dismiss'?{pane:'editor',popup:false}:{pane:'list',side:mode==='overlay'?noteView().side:'list',popup:mode==='overlay'};
  history.replaceState(noteViewState(next),'',location.href);applyNoteLayout();
 }catch(error){showDialog('Unable to save',`<p>${esc(error.message)}</p><button data-action="close">OK</button>`)}
 finally{root.inert=false;applyNoteLayout({focus:true})}
}
document.addEventListener('click',event=>{const button=event.target.closest('[data-note-navigation]');if(button){event.preventDefault();noteNavigation(button.dataset.noteNavigation)}});
document.addEventListener('keydown',event=>{
 const layout=document.querySelector('.notes-layout');if(!layout||modal.open||noteLayoutMode()!=='overlay'||!noteView().popup)return;
 if(event.key==='Escape'){event.preventDefault();noteNavigation('dismiss')}
 if(event.key==='Tab'){
  const choices=noteFocusable(layout.querySelector('.note-navigation')),first=choices[0],last=choices.at(-1);
  if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus()}
  else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}
 }
});
window.addEventListener('resize',()=>applyNoteLayout());
