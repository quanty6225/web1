/* The original controllers use local endpoints and locally owned sessions. */
(()=>{'use strict';
 function openRequestedForm(){
  if(new URL(location.href).searchParams.get('trigger_add_dialog')!=='true')return;
  const main=document.querySelector('main');
  if(!main||main.dataset.localAddDialogOpened)return;
  const eventLink=main.querySelector('a[data-hotkey="m"][href*="/entries/new"]');
  if(eventLink){
   main.dataset.localAddDialogOpened='true';
   eventLink.click();
  }
 }
 document.addEventListener('turbo:load',openRequestedForm);
 // Captured share links are localized to paths. Copy a complete URL so the
 // result also works when pasted outside this page or into another browser.
 document.addEventListener('click',event=>{
  const action=event.target.closest('[data-action~="copy-to-clipboard#copy"]');
  const source=action?.closest('[data-controller~="copy-to-clipboard"]')?.querySelector('[data-copy-to-clipboard-target~="copyable"]');
  if(source&&/^\/(?:6302022|files)\//.test(source.value))source.value=new URL(source.value,location.origin).href;
 },true);
 // Typing can finish before the people request. The native collection render
 // updates selected chips but leaves an existing suggestion list stale.
 const autocomplete=window.BC?.AutocompleteController?.prototype;
 if(autocomplete){
  const setCollection=autocomplete.setCollection;
  autocomplete.setCollection=function(collection){
   const changed=this.collection!==collection;
   const result=setCollection.call(this,collection);
   if(changed&&this.element.isConnected&&document.activeElement===this.inputElement&&this.suggestionController){
    this.suggestionController.destroy();this.suggestionController=null;
    this.displaySuggestions();
   }
   return result;
  };
 }
 document.addEventListener('click',event=>{
  const picture=event.target.closest('img[data-behavior~=lightboxable]');
  if(picture?.getAttribute('src')?.startsWith('/files/')&&picture.naturalWidth){
   picture.dataset.width=picture.naturalWidth;picture.dataset.height=picture.naturalHeight;
  }
 },true);
 // A full-page navigation makes Chromium reject pending frame requests with
 // TypeError unless their AbortSignal is cancelled first. Cancel those reads
 // explicitly on departure so Turbo receives its supported AbortError path.
 let navigationReads=new AbortController();
 const cancelNavigationReads=()=>{navigationReads.abort();navigationReads=new AbortController();};
 addEventListener('beforeunload',cancelNavigationReads);
 addEventListener('pagehide',cancelNavigationReads);
 document.addEventListener('turbo:before-fetch-request',event=>{
  const options=event.detail.fetchOptions;
  if((options.method||'GET').toUpperCase()==='GET'){
   options.signal=options.signal?AbortSignal.any([options.signal,navigationReads.signal]):navigationReads.signal;
  }
 });
 // Keep an open reminder action sheet while the sidebar updates its row.
 // Refresh only changed action data, so a due reminder drops "Now" without
 // discarding the menu (or losing an in-flight pointer/keyboard action).
 function changedBubbleMenus(current,incoming){
  return [...incoming.querySelectorAll('[data-local-bubble]')].flatMap(row=>{
   const previous=current.querySelector('#'+CSS.escape(row.id));
   return previous&&previous.dataset.morphVersion!==row.dataset.morphVersion
    ?[previous.querySelector('[data-local-bubble-menu]')?.id].filter(Boolean):[];
  });
 }
 function refreshBubbleMenus(ids){
  for(const id of ids)document.getElementById(id)?.querySelector('turbo-frame')?.reload();
 }
 document.addEventListener('turbo:before-frame-render',event=>{
  if(event.target.id!=='sidebar_frame')return;
  const ids=changedBubbleMenus(event.target,event.detail.newFrame),render=event.detail.render;
  event.detail.render=async(...args)=>{await render(...args);refreshBubbleMenus(ids);};
 });
 document.addEventListener('turbo:before-stream-render',event=>{
  if(event.target.getAttribute('target')!=='sidebar_frame')return;
  const current=document.getElementById('sidebar_frame');
  if(!current)return;
  const ids=changedBubbleMenus(current,event.target.templateElement.content),render=event.detail.render;
  event.detail.render=async(...args)=>{await render(...args);refreshBubbleMenus(ids);};
 });
 // Turbo catches cancellations while fetching headers, but its frame delegate
 // reads the body in a separate promise. Replacing a still-streaming frame
 // cancels that body too. Keep that expected cancellation inside the delegate
 // and let every other rendering/network error propagate normally.
 const frameDelegate=customElements.get('turbo-frame')?.delegateConstructor?.prototype;
 if(frameDelegate){
  const loadResponse=frameDelegate.loadResponse;
  frameDelegate.loadResponse=async function(response){
   try{return await loadResponse.call(this,response);}
   catch(error){if(error?.name!=='AbortError')throw error;}
  };
 }
 // A fetch-followed redirect drops its fragment. Keep the committed comment's
 // destination intact when the native composer submits through Turbo.
 if(window.Turbo)window.Turbo.StreamActions.local_visit=function(){
  const destination=new URL(this.getAttribute('url'),location.href);
  if(destination.origin===location.origin&&destination.pathname.startsWith('/6302022/'))window.Turbo.visit(destination.href);
 };
 document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-behavior~=unsubscribe_from_report],[data-behavior~=subscribe_to_report]');
  if(!button)return;event.preventDefault();event.stopImmediatePropagation();
  const enabled=button.dataset.behavior.includes('subscribe_to_report');
  const response=await fetch(button.dataset.url,{method:enabled?'POST':'DELETE',headers:{'X-CSRF-Token':csrf(),'Accept':'application/json'}});
  if(!response.ok)return;const result=await response.json();
  const boosts=button.dataset.url.includes('/boost_reports/');
  button.textContent=boosts?(result.subscribed?'Notifying you of new boosts every 3 hours':'Notify me of new boosts every 3 hours'):(result.subscribed?'Emailing tasks every Monday':'Email me tasks every Monday');button.dataset.behavior=result.subscribed?'unsubscribe_from_report':'subscribe_to_report';
 },true);
 const csrf=()=>document.querySelector('meta[name="local-csrf"]')?.content||'';
 document.addEventListener('dragstart',event=>{
  const card=event.target.closest('[data-drag-and-drop-type="kanban_card"]');
  const link=card?.querySelector('a.kanban-card__link');
  if(link&&event.dataTransfer)event.dataTransfer.setData('application/x-basecamp-local-card',new URL(link.href).pathname);
 },true);
 document.addEventListener('dragover',event=>{
  if(event.target.closest('[data-local-wormhole]')&&event.dataTransfer?.types.includes('application/x-basecamp-local-card')){
   event.preventDefault();event.stopPropagation();event.dataTransfer.dropEffect='move';
  }
 },true);
 document.addEventListener('drop',async event=>{
  const wormhole=event.target.closest('[data-local-wormhole]');
  const card=event.dataTransfer?.getData('application/x-basecamp-local-card');
  if(!wormhole||!card||!/^\/6302022\/buckets\/\d+\/card_tables\/cards\/\d+$/.test(card))return;
  event.preventDefault();event.stopImmediatePropagation();
  try{
   const response=await fetch(card+'/moves',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json','X-CSRF-Token':csrf()},body:JSON.stringify({column_id:wormhole.dataset.localWormhole})});
   if(!response.ok){const result=await response.json();throw new Error(result.detail||'The card could not be moved.');}
   window.Turbo.visit(location.pathname);
  }catch(error){
   let status=wormhole.querySelector('[role="status"]');
   if(!status){status=document.createElement('p');status.setAttribute('role','status');wormhole.append(status);}
   status.textContent=error.message;
  }
 },true);
 let checking=false;
 async function check(){
  if(checking)return;checking=true;
  try{const r=await fetch('/api/me',{cache:'no-store',signal:navigationReads.signal});if(r.status===401)location.replace('/signin?return_to='+encodeURIComponent(location.pathname+location.search));}
  catch(error){if(error?.name!=='AbortError')throw error;}
  finally{checking=false;}
 }
 addEventListener('pageshow',e=>{if(e.persisted)check()});
 document.addEventListener('turbo:load',check);
 async function markRead(){
  const id=location.pathname.match(/\/onboarding\/messages\/(\d+)$/)?.[1];
  if(id)await fetch('/api/notifications/read',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf()},body:JSON.stringify({id})});
 }
 document.addEventListener('turbo:load',markRead);markRead();
 document.addEventListener('turbo:before-cache',()=>{
  document.querySelectorAll('dialog[open]').forEach(e=>e.close());
 });
 document.addEventListener('click',event=>{
  const button=event.target.closest('[data-action]');
  const action=button?.dataset.action||'';
  if(action.includes('page-tint#cycle')||action.includes('home-layout#toggle')){
   setTimeout(()=>{
    const name=action.includes('page-tint')?'theme':'grid';
    const value=name==='theme'?Number(document.cookie.split('; ').find(c=>c.startsWith('page_tint_6302022='))?.split('=')[1]||1):!!document.querySelector('[data-home-layout-grid]');
    fetch('/api/settings/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf()},body:JSON.stringify({value})});
   },0);
  }
 });
})();
