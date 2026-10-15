let globalMenuTrigger=null;
const localeDropdown=document.querySelector('#ac-ls-dropdown');
if(localeDropdown){
 const trigger=localeDropdown.querySelector('#ac-ls-dropdown-select'),options=localeDropdown.querySelector('#ac-ls-dropdown-options'),choices=[...localeDropdown.querySelectorAll('[role="menuitem"]')],next=document.querySelector('#ac-ls-continue');
 const toggle=open=>{trigger.setAttribute('aria-expanded',String(open));localeDropdown.classList.toggle('select-collapsed',!open);localeDropdown.classList.toggle('select-expanded',open);options.hidden=!open;options.style.display=open?'block':'none'};
 toggle(false);
 document.addEventListener('click',event=>{
  if(event.target.closest('#ac-ls-dropdown-select')){event.preventDefault();event.stopImmediatePropagation();const open=trigger.getAttribute('aria-expanded')!=='true';toggle(open);if(open)(choices.find(choice=>choice.dataset.acLsSelected==='true')||choices[0])?.focus();return}
  const choice=event.target.closest('#ac-ls-dropdown [role="menuitem"]');
  if(choice){event.preventDefault();event.stopImmediatePropagation();choices.forEach(item=>item.dataset.acLsSelected=String(item===choice));document.querySelector('#ac-ls-dropdown-title .ac-ls-dropdown-copy').textContent=choice.querySelector('.ac-ls-dropdown-copy').textContent;if(next)next.href=choice.dataset.href||location.pathname;toggle(false);trigger.focus();return}
  if(event.target.closest('#ac-ls-close')){event.preventDefault();event.stopImmediatePropagation();document.querySelector('#ac-localeswitcher')?.remove();return}
  if(!localeDropdown.contains(event.target))toggle(false);
 },true);
 document.addEventListener('keydown',event=>{
  if(!localeDropdown.contains(event.target))return;
  if(['Enter',' '].includes(event.key)){event.preventDefault();event.target.click()}
  else if(event.key==='Escape'){event.preventDefault();toggle(false);trigger.focus()}
  else if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();toggle(true);const index=choices.indexOf(document.activeElement),nextIndex=event.key==='Home'?0:event.key==='End'?choices.length-1:(index+(event.key==='ArrowDown'?1:-1)+choices.length)%choices.length;choices[nextIndex]?.focus()}
 });
}
let compactNav=null;
const compactViewport=window.matchMedia('(max-width: 833px)');
function clearCapturedStyle(root){[root,...root.querySelectorAll('*')].forEach(el=>{el.removeAttribute('class');el.removeAttribute('id');el.removeAttribute('style')});return root}
function closeCompactNav(focus=true){
 if(!compactNav)return;
 const {trigger,overflow}=compactNav;compactNav=null;
 document.querySelector('#local-compact-menu')?.remove();
 document.body.style.overflow=overflow;
 trigger.setAttribute('aria-expanded','false');trigger.setAttribute('aria-label',trigger.dataset.topnavMenuLabelOpen||'Menu');
 if(focus)trigger.focus();
}
function compactMenu(trigger,source=null){
 closeGlobalMenu();
 if(!compactNav)compactNav={trigger,overflow:document.body.style.overflow};
 document.querySelector('#local-compact-menu')?.remove();
 const menu=document.createElement('nav');menu.id='local-compact-menu';menu.setAttribute('aria-label',source?.getAttribute('aria-label')||'Main menu');
 trigger.setAttribute('aria-expanded','true');trigger.setAttribute('aria-label',trigger.dataset.topnavMenuLabelClose||'Close');
 document.body.style.overflow='hidden';
 if(source){
  const back=document.createElement('button');back.textContent=document.querySelector('.globalnav-menuback button')?.getAttribute('aria-label')||'Main menu';back.onclick=()=>compactMenu(trigger);menu.append(back);
  const target=document.getElementById(source.getAttribute('aria-controls'));
  target?.querySelectorAll('.globalnav-submenu-group').forEach(group=>menu.append(clearCapturedStyle(group.cloneNode(true))));
 }else{
  document.querySelectorAll('#globalnav .globalnav-submenu-trigger-button').forEach(sourceButton=>{
   const button=document.createElement('button');button.textContent=sourceButton.getAttribute('aria-label').replace(/ menu$/,'');button.setAttribute('aria-label',sourceButton.getAttribute('aria-label'));button.onclick=()=>compactMenu(trigger,sourceButton);menu.append(button);
  });
 }
 document.body.append(menu);menu.querySelector('button,a')?.focus();
}
function supportSearch(trigger){
 if(globalMenuTrigger===trigger){closeGlobalMenu(true);return}
 closeCompactNav(false);closeGlobalMenu();
 const source=document.getElementById(trigger.getAttribute('aria-controls'));if(!source)return;
 const menu=document.createElement('section');menu.id='local-global-menu';menu.className='local-support-search';menu.setAttribute('role','search');menu.setAttribute('aria-label',trigger.getAttribute('aria-label'));
 const form=source.querySelector('form');if(!form)return;
 menu.append(clearCapturedStyle(form.cloneNode(true)));
 const results=source.querySelector('.globalnav-searchresults-current');if(results)menu.append(clearCapturedStyle(results.cloneNode(true)));
 const input=menu.querySelector('input:not([type="hidden"])'),reset=menu.querySelector('button[type="button"]'),submit=menu.querySelector('button[type="submit"]');
 const update=()=>{for(const button of [reset,submit]){if(!button)continue;button.disabled=!input.value.trim();button.removeAttribute('aria-hidden');button.tabIndex=0}};
 input.addEventListener('input',update);if(reset)reset.onclick=()=>{input.value='';update();input.focus()};update();
 trigger.dataset.localOriginalControls=trigger.getAttribute('aria-controls');trigger.setAttribute('aria-controls',menu.id);trigger.setAttribute('aria-expanded','true');globalMenuTrigger=trigger;
 document.body.append(menu);input.focus();
}
document.addEventListener('click',event=>{
 const trigger=event.target.closest('#globalnav-menutrigger-button,#globalnav-menubutton-link-search,#globalnav-menubutton-link-bag');if(!trigger)return;
 event.preventDefault();event.stopImmediatePropagation();
 if(trigger.id==='globalnav-menutrigger-button'){if(compactNav)closeCompactNav();else compactMenu(trigger)}
 else if(trigger.id==='globalnav-menubutton-link-search')supportSearch(trigger);
 else location.href=trigger.href;
},true);
document.addEventListener('keydown',event=>{
 if(!compactNav)return;
 if(event.key==='Escape'){event.preventDefault();closeCompactNav();return}
 if(event.key==='Tab'){
  const controls=[compactNav.trigger,...document.querySelectorAll('#local-compact-menu button,#local-compact-menu a[href]')];
  const first=controls[0],last=controls.at(-1);
  if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}
  else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
 }
});
compactViewport.addEventListener('change',()=>{closeCompactNav(false);closeGlobalMenu()});
let guideModal=null;
function openGuideContents(button){
 const content=document.getElementById(button.getAttribute('aria-controls'));
 const modal=content?.closest('.modal');if(!modal)return false;
 if(guideModal){closeGuideContents();return true}
 const inactive=[...document.body.children].filter(el=>el!==modal&&!el.contains(modal)&&!el.inert);
 inactive.forEach(el=>el.inert=true);
 guideModal={modal,button,inactive,scrollLocked:document.body.classList.contains('preventscroll')};
 modal.classList.add('modal-open');modal.removeAttribute('aria-hidden');
 document.body.classList.add('preventscroll');button.setAttribute('aria-expanded','true');content.focus();return true;
}
function closeGuideContents(){
 if(!guideModal)return;
 const {modal,button,inactive,scrollLocked}=guideModal;guideModal=null;
 modal.classList.remove('modal-open');modal.setAttribute('aria-hidden','true');
 inactive.forEach(el=>el.inert=false);if(!scrollLocked)document.body.classList.remove('preventscroll');
 button.setAttribute('aria-expanded','false');button.focus();
}
document.addEventListener('click',event=>{
 if(guideModal&&event.target.closest('.modal-close')?.closest('.modal')===guideModal.modal){closeGuideContents();return}
 if(guideModal&&event.target.hasAttribute('data-modal-close')&&guideModal.modal.contains(event.target))closeGuideContents();
});
document.addEventListener('keydown',event=>{
 if(!guideModal)return;
 if(event.key==='Escape'){event.preventDefault();closeGuideContents();return}
 if(event.key!=='Tab')return;
 const controls=[...guideModal.modal.querySelectorAll('a[href],button,input,select,textarea,[tabindex]')].filter(el=>!el.disabled&&el.tabIndex>=0&&el.getClientRects().length&&getComputedStyle(el).visibility!=='hidden');
 const first=controls[0],last=controls.at(-1),current=document.activeElement;
 if(!first){event.preventDefault();return}
 if(event.shiftKey&&(current===first||!controls.includes(current))){event.preventDefault();last.focus()}
 else if(!event.shiftKey&&(current===last||!controls.includes(current))){event.preventDefault();first.focus()}
});
function publicSignIn(){location.href=location.pathname.startsWith('/account/')?'/signin/?return=%2Faccount%2Fmanage%2F':'/signin/'}
document.addEventListener('click',event=>{
 const link=event.target.closest('[data-local-video]');if(!link)return;event.preventDefault();
 const dialog=document.createElement('dialog');dialog.className='local-film';dialog.setAttribute('aria-label','Video');
 const close=document.createElement('button');close.textContent='Close';close.onclick=()=>dialog.close();
 const video=document.createElement('video');video.src=link.href;video.controls=true;video.playsInline=true;
 if(link.dataset.localCaptions){const track=document.createElement('track');track.kind='captions';track.srclang='en';track.label='English';track.src=link.dataset.localCaptions;video.append(track)}
 dialog.append(close,video);dialog.addEventListener('close',()=>{video.pause();dialog.remove();link.focus()});document.body.append(dialog);dialog.showModal();video.play().catch(()=>{});
});
function closeGlobalMenu(focus=false){document.querySelector('#local-global-menu')?.remove();if(globalMenuTrigger){globalMenuTrigger.setAttribute('aria-expanded','false');globalMenuTrigger.setAttribute('aria-controls',globalMenuTrigger.dataset.localOriginalControls);if(focus)globalMenuTrigger.focus();globalMenuTrigger=null}}
function globalMenu(button){
 if(globalMenuTrigger===button){closeGlobalMenu(true);return}
 closeGlobalMenu();const target=document.getElementById(button.getAttribute('aria-controls'));if(!target)return;
 const menu=document.createElement('nav');menu.id='local-global-menu';menu.setAttribute('aria-label',button.getAttribute('aria-label'));
 target.querySelectorAll('.globalnav-submenu-group').forEach(group=>{let copy=group.cloneNode(true);[copy,...copy.querySelectorAll('*')].forEach(el=>{el.removeAttribute('class');el.removeAttribute('id');el.removeAttribute('style')});menu.append(copy)});
 if(!menu.childElementCount)return;
 button.dataset.localOriginalControls=button.getAttribute('aria-controls');button.setAttribute('aria-controls',menu.id);button.setAttribute('aria-expanded','true');globalMenuTrigger=button;document.body.append(menu);menu.querySelector('a')?.focus();
}
document.addEventListener('click',event=>{if(globalMenuTrigger&&!event.target.closest('#local-global-menu,.globalnav-submenu-trigger-button'))closeGlobalMenu()});
document.addEventListener('keydown',event=>{if(event.key==='Escape')closeGlobalMenu(true)});
function helpMenu(button){let menu=document.querySelector('#local-help-menu');if(menu){menu.remove();button.setAttribute('aria-expanded','false');return}menu=document.createElement('div');menu.id='local-help-menu';menu.setAttribute('role','menu');menu.innerHTML='<a role="menuitem" href="/help/welcome/">iCloud User Guide</a>';document.body.append(menu);button.setAttribute('aria-expanded','true');menu.querySelector('a').focus()}
document.addEventListener('click',event=>{let el=event.target.closest('ui-button,button,[role=button]');if(!el)return;if(el.matches('.toggle-toc')&&openGuideContents(el)){event.preventDefault();return}let name=el.getAttribute('aria-label')||el.getAttribute('title')||el.textContent.trim();if(el.matches('.globalnav-submenu-trigger-button')){globalMenu(el);return}if(name==='Sign In'){publicSignIn();return}if(name==='Help'){helpMenu(el);return}let controlled=el.getAttribute('aria-controls');if(controlled){let target=document.getElementById(controlled);if(target){event.preventDefault();let open=el.getAttribute('aria-expanded')!=='true';el.setAttribute('aria-expanded',String(open));target.hidden=!open;target.style.display=open?'block':'none'}}});
document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelector('#local-help-menu')?.remove();if((['Enter',' '].includes(e.key)&&e.target.matches('ui-button'))||(e.key===' '&&e.target.matches('a[role="button"]'))){e.preventDefault();e.target.click()}});
document.querySelectorAll('video').forEach(v=>{v.muted=true;v.play().catch(()=>{})});
const guideSearch=document.querySelector('#as-search-input');
if(guideSearch){
 const form=guideSearch.closest('form'),submit=form?.querySelector('button[type="submit"]');
 const update=()=>{if(submit)submit.disabled=!guideSearch.value.trim()};
 guideSearch.addEventListener('input',update);form?.addEventListener('reset',()=>setTimeout(update,0));update();
}

// The captured guide includes all three feedback states and their exact labels.
// Persist ratings only to this clone; no Apple feedback endpoint is contacted.
const helpFeedback=document.querySelector('#helpful');
if(helpFeedback){
 let rating=null;
 const question=helpFeedback.querySelector('#question-state'),formState=helpFeedback.querySelector('#feedback-state'),done=helpFeedback.querySelector('#rating-done'),form=formState?.querySelector('form'),textarea=form?.querySelector('textarea');
 const show=(element,visible)=>{element.classList.toggle('show',visible);element.classList.toggle('hide',!visible);element.hidden=!visible};
 const error=document.createElement('p');error.setAttribute('role','alert');helpFeedback.append(error);
 const save=async comment=>{const response=await fetch('/api/help/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({page:location.pathname,helpful:rating,comment})});if(!response.ok){const data=await response.json();throw Error(data.detail||'Unable to save feedback.')}};
 for(const id of ['yes-button','no-button']){
  const button=helpFeedback.querySelector('#'+id);if(!button)continue;
  button.onclick=async()=>{
   rating=id==='yes-button';error.textContent='';question.querySelectorAll('button').forEach(b=>b.disabled=true);
   try{
    await save('');const variant=rating?'yes':'no';
    helpFeedback.querySelector('#feedback-label').textContent=helpFeedback.querySelector('#feedback-label').getAttribute('data-'+variant+'-label');
    const label=textarea.getAttribute('data-'+variant+'-placeholder');textarea.placeholder=label;helpFeedback.querySelector('#optional_label').textContent=label;
    show(question,false);show(formState,true);textarea.focus();
   }catch(e){error.textContent=e.message;question.querySelectorAll('button').forEach(b=>b.disabled=false)}
  };
 }
 if(form&&textarea){
  textarea.maxLength=250;form.action='/api/help/feedback';form.method='post';
  textarea.oninput=()=>{helpFeedback.querySelector('.form-counter').textContent=String(250-textarea.value.length)};
  form.onsubmit=async event=>{
   event.preventDefault();const submit=form.querySelector('[type="submit"]');submit.disabled=true;error.textContent='';
   try{await save(textarea.value);show(formState,false);show(done,true);done.setAttribute('role','status');done.tabIndex=-1;done.focus()}
   catch(e){error.textContent=e.message;submit.disabled=false}
  };
 }
}
