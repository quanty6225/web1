'use strict';
const path = location.pathname;
const query = new URLSearchParams(location.search);
async function api(action, data) {
  const response = await fetch('/local/auth/' + action, {method:'POST', headers:{'Content-Type':'application/json','X-IFTTT-Local':'1'}, body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) {const error=new Error(result.error || 'Please try again.');error.status=response.status;throw error;}
  return result;
}
function alertIn(form, message) {
  let target = form.querySelector('.local-error');
  if (!target) {target=document.createElement('p');target.className='local-error';target.setAttribute('role','alert');form.append(target);}
  target.textContent=message;
}
document.querySelectorAll('form').forEach(form => {
  const developerRegistration=!!form.querySelector('#user_email')&&!!form.querySelector('#user_password')&&path!=='/join';
  const action = form.dataset.authAction || ({'/login':'login','/join':'register','/passwords/forgot':'forgot','/forgot':'forgot'})[path] || (developerRegistration?'register':null);
  if (!action) return;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const values=Object.fromEntries(new FormData(form));
    const data={email:values['user[username]'] || values['user[email]'] || values.email,
      password:values['user[password]'] || values.password,code:values.code,return_to:query.get('return_to')||(developerRegistration?path:null)};
    const submit=form.querySelector('[type="submit"]');if(submit)submit.disabled=true;
    try {const result=await api(action,data);location.assign(result.redirect);}
    catch(error){
      alertIn(form,error.message);
      const purpose=({register:'registration',forgot:'password-reset','identity-start':'passwordless-signin'})[action];
      if(error.status===503&&purpose&&!form.querySelector('[data-mail-recovery]')){
        const retry=document.createElement('button');retry.type='button';retry.dataset.mailRecovery='1';retry.textContent='Retry email delivery';
        retry.onclick=async()=>{retry.disabled=true;try{await api('retry',{purpose});const next=({registration:'/join/verify','password-reset':'/passwords/reset','passwordless-signin':'/local-identity/verify'})[purpose];location.assign(next+(data.return_to?'?return_to='+encodeURIComponent(data.return_to):''));}catch(failure){alertIn(form,failure.message);}finally{retry.disabled=false;}};
        form.append(retry);
      }
    }
    finally{if(submit)submit.disabled=false;}
  });
});
if (query.has('code') && document.querySelector('[name="code"]')) {
  document.querySelector('[name="code"]').value=query.get('code');
  history.replaceState(null,'',path);
}
document.querySelectorAll('[aria-label="Show password"]').forEach(button=>button.addEventListener('click',()=>{
  const input=button.parentElement.querySelector('input[type="password"],input[type="text"]');if(!input)return;
  const show=input.type==='password';input.type=show?'text':'password';button.setAttribute('aria-label',show?'Hide password':'Show password');
}));
document.querySelector('[aria-label="Account menu"]')?.addEventListener('click',event=>{
  const panel=document.querySelector('.account-menu-panel');if(!panel)return;
  const opened=panel.toggleAttribute('data-local-open');event.currentTarget.setAttribute('aria-expanded',String(opened));
});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'){document.querySelector('.account-menu-panel')?.removeAttribute('data-local-open');document.querySelector('dialog[open]')?.close();}
});
for(const [selector,prefix] of [['.featured-tab','featured-'],['.story-spotlight__tab','story-category-'],['.mcp-agent-showcase__tab','mcp-']]){
  const tabs=[...document.querySelectorAll(selector)];
  tabs.forEach((tab,index)=>{
    tab.setAttribute('aria-label',tab.textContent.trim());
    const activate=()=>{tabs.forEach((item,i)=>{
      const selected=i===index;item.classList.toggle('active',selected);item.setAttribute('aria-selected',String(selected));item.tabIndex=selected?0:-1;
      const panel=document.getElementById(item.getAttribute('aria-controls'));
      if(panel){panel.classList.toggle('active',selected);panel.setAttribute('aria-hidden',String(!selected));}
      if(prefix==='mcp-'){item.classList.toggle('is-active',selected);if(panel){panel.hidden=!selected;panel.classList.toggle('is-active',selected);}}
    });};
    tab.addEventListener('click',activate);
    tab.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){
      event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;tabs[next].focus();tabs[next].click();
    }});
  });
}
document.querySelectorAll('input[type="search"]').forEach(input=>input.addEventListener('keydown',event=>{
  if(event.key==='Enter'&&input.value.trim()){event.preventDefault();location.assign('/search/query/'+encodeURIComponent(input.value.trim()));}
}));
const mobileMenu=document.querySelector('#unified_mobile_menu');
mobileMenu?.addEventListener('click',()=>{
  const open=document.body.classList.toggle('mobile-menu-opened');mobileMenu.classList.toggle('open',open);mobileMenu.classList.toggle('closed',!open);mobileMenu.setAttribute('aria-expanded',String(open));
});
mobileMenu?.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();mobileMenu.click();}});
document.querySelectorAll('button').forEach(button=>{
  if(button.textContent.trim()!=='quick demo')return;
  button.addEventListener('click',async()=>{
    const response=await fetch('/my_applets?_view=quick-demo');
    const source=new DOMParser().parseFromString(await response.text(),'text/html').querySelector('.modal');
    if(!source)return;
    const modal=document.importNode(source,true);modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');document.body.append(modal);
    const close=()=>{modal.remove();button.focus();document.removeEventListener('keydown',escape);};
    const escape=event=>{if(event.key==='Escape')close();};document.addEventListener('keydown',escape);
    const control=modal.querySelector('.modal-close');if(control){control.setAttribute('role','button');control.setAttribute('aria-label','Close demo');control.tabIndex=0;control.addEventListener('click',close);control.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key))close();});control.focus();}
  });
});
document.querySelectorAll('[data-retry-purpose]').forEach(button=>button.addEventListener('click',async()=>{
  try{const result=await api('retry',{purpose:button.dataset.retryPurpose});alertIn(document.querySelector('form'),result.message);}
  catch(error){alertIn(document.querySelector('form'),error.message);}
}));
document.querySelectorAll('[data-resend-purpose]').forEach(button=>button.addEventListener('click',async()=>{
  try{const result=await api('resend',{purpose:button.dataset.resendPurpose});alertIn(document.querySelector('form'),result.message);}
  catch(error){alertIn(document.querySelector('form'),error.message);}
}));
if(['/login','/join'].includes(path)||document.querySelector('form #user_email'))document.querySelectorAll('a,button').forEach(control=>{
  const text=control.textContent.trim();const provider=['Google','Apple','Facebook'].find(name=>text.includes(name)&&/continue|sign|log/i.test(text));
  if(provider)control.addEventListener('click',event=>{event.preventDefault();const target=query.get('return_to')||(!['/login','/join'].includes(path)?path:'');location.assign('/local-identity?provider='+provider+(target?'&return_to='+encodeURIComponent(target):''));});
});
document.querySelector('[data-copy-destination]')?.addEventListener('click',async event=>{
  const button=event.currentTarget;
  try{await navigator.clipboard.writeText(document.querySelector('input[readonly]').value);button.textContent='Copied';}
  catch{button.textContent='Select and copy the source address above';}
});
window.addEventListener('pageshow',async event=>{
  if(event.persisted && document.body.dataset.localActor==='member'){
    const current=await fetch('/local/session').then(r=>r.json());if(!current.authenticated)location.replace('/login');
  }
});
document.querySelectorAll('.prompt-hero-input').forEach(input=>{
  const container=input.closest('section')||input.parentElement;
  const button=container.querySelector('.prompt-hero-submit');
  const update=()=>{const count=container.querySelector('.prompt-hero-count');if(count){count.hidden=!input.value;count.textContent=input.value.length+'/500';}if(button)button.disabled=!input.value.trim();};
  input.addEventListener('input',update);update();
  container.querySelectorAll('.prompt-hero-examples button').forEach(example=>example.addEventListener('click',()=>{input.value=example.textContent.trim();update();input.focus();}));
  button?.addEventListener('click',()=>{if(input.value.trim())location.assign('/create?prompt='+encodeURIComponent(input.value.trim()));});
});
document.querySelectorAll('.service-category-chip').forEach(button=>button.addEventListener('click',()=>{
  const label=button.textContent.trim();
  const slug=({'New to IFTTT':'new','All':'all','Popular':'popular'})[label]||label.toLowerCase().replace(/&/g,'').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
  location.assign('/explore/services/'+slug);
}));
document.querySelectorAll('.chips-arrow').forEach(button=>button.addEventListener('click',()=>{
  const viewport=button.closest('.services-curated-section')?.querySelector('.chips-viewport');
  viewport?.scrollBy({left:(button.classList.contains('chips-arrow-forward')?1:-1)*Math.max(240,viewport.clientWidth*.7),behavior:'smooth'});
}));
document.querySelectorAll('.tqas-ui').forEach(container=>{
  const tabs=[...container.querySelectorAll('.tqa-tab')],panels=[...container.querySelectorAll('.tqas-tab-panel')];
  const more=container.querySelector('.tqas-load-more-btn');
  function sync(){const active=container.querySelector('.tqas-tab-panel.active');const remainder=active?.querySelector('.tqas-remaining-items');if(more)more.hidden=!remainder||!remainder.children.length||remainder.style.display==='block';}
  tabs.forEach((tab,index)=>{tab.setAttribute('aria-selected',String(tab.classList.contains('active')));
    if(tab.classList.contains('disabled')){tab.setAttribute('aria-disabled','true');tab.tabIndex=-1;}
    tab.addEventListener('click',event=>{event.preventDefault();if(tab.classList.contains('disabled'))return;
      tabs.forEach(item=>{item.classList.toggle('active',item===tab);item.setAttribute('aria-selected',String(item===tab));});
      panels.forEach((panel,i)=>panel.classList.toggle('active',i===[3,0,1,2][index]));sync();
    });
  });
  more?.addEventListener('click',()=>{const remainder=container.querySelector('.tqas-tab-panel.active .tqas-remaining-items');if(remainder)remainder.style.display='block';sync();});sync();
});
document.querySelectorAll('.clean-search').forEach(control=>{
  control.setAttribute('role','button');control.setAttribute('aria-label','Clear search');control.tabIndex=0;
  const clear=()=>{const input=control.closest('.ifttt-search')?.querySelector('input');if(input){input.value='';input.dispatchEvent(new Event('input'));input.focus();}};
  control.addEventListener('click',clear);control.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();clear();}});
});
document.querySelectorAll('.toggle-container label.toggle').forEach(toggle=>{
  toggle.setAttribute('role','switch');toggle.tabIndex=0;toggle.setAttribute('aria-label','Yearly billing');toggle.setAttribute('aria-checked',String(toggle.classList.contains('active')));
  const change=()=>location.assign('/plans?_view='+(toggle.classList.contains('active')?'monthly':'default'));
  toggle.addEventListener('click',change);toggle.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();change();}});
});
document.querySelectorAll('.ifttt-search').forEach(container=>{
  const input=container.querySelector('input[type=search]'),helper=container.querySelector('.universal-search-helper');
  if(!input||!helper)return;
  let sequence=0;
  const close=()=>{helper.style.display='none';input.setAttribute('aria-expanded','false');};
  const open=()=>{helper.style.display='block';input.setAttribute('aria-expanded','true');};
  input.setAttribute('aria-expanded','false');input.addEventListener('focus',open);
  document.addEventListener('click',event=>{if(!container.contains(event.target))close();});
  container.addEventListener('keydown',event=>{if(event.key==='Escape'){close();input.focus();close();}if(event.key==='ArrowDown'&&event.target===input){event.preventDefault();helper.querySelector('a')?.focus();}});
  input.addEventListener('input',async()=>{
    const query=input.value.trim(),request=++sequence;open();
    const defaults=helper.querySelector('.default-recommendations'),preview=helper.querySelector('.search-preview');
    if(defaults)defaults.hidden=!!query;
    if(!preview)return;
    preview.replaceChildren();if(!query)return;
    try{const result=await fetch('/local/search?query='+encodeURIComponent(query)).then(r=>r.json());if(request!==sequence)return;
      for(const item of result.items){const link=document.createElement('a');link.href=item.route;link.textContent=item.title;link.className='local-search-suggestion';preview.append(link);}
      if(!result.items.length){const notice=document.createElement('p');notice.textContent='No matching suggestions';preview.append(notice);}
      const all=document.createElement('a');all.href='/search/query/'+encodeURIComponent(query);all.textContent='See all results';all.className='local-search-suggestion';preview.append(all);
    }catch{const notice=document.createElement('p');notice.textContent='Search is temporarily unavailable. Please try again.';preview.append(notice);}
  });
  container.querySelectorAll('a.search-navigation[href="#"]').forEach(link=>link.addEventListener('click',event=>{event.preventDefault();location.assign(input.value.trim()?'/search/query/'+encodeURIComponent(input.value.trim()):'/explore');}));
});
document.querySelectorAll('.modal-open').forEach(button=>button.addEventListener('click',()=>{
  const target=button.textContent.trim().toLowerCase().includes('share')?document.querySelector('.share-modal')?.closest('.modal'):null;
  if(!target)return;
  target.classList.remove('hidden');target.setAttribute('role','dialog');target.setAttribute('aria-modal','true');
  target.querySelectorAll('.share-url-input').forEach(input=>input.value=location.origin+location.pathname);
  const control=target.querySelector('.modal-close');
  const close=()=>{target.classList.add('hidden');target.removeAttribute('role');button.focus();document.removeEventListener('keydown',escape);};
  const escape=event=>{if(event.key==='Escape')close();};document.addEventListener('keydown',escape);
  if(control){control.setAttribute('role','button');control.setAttribute('aria-label','Close share dialog');control.tabIndex=0;control.onclick=close;control.onkeydown=event=>{if(['Enter',' '].includes(event.key))close();};control.focus();}
  target.querySelectorAll('button.copy').forEach(copy=>copy.onclick=async()=>{try{await navigator.clipboard.writeText(location.origin+location.pathname);copy.textContent='Copied';}catch{target.querySelector('input')?.select();}});
}));
document.querySelector('#load-more-applets')?.addEventListener('click',async event=>{
  const button=event.currentTarget,section=button.closest('.discover_applets'),list=section?.querySelector('ul.web-applet-cards');if(!list)return;
  button.disabled=true;
  try{const response=await fetch('/local/applet-pages?collection='+encodeURIComponent(location.pathname)+'&offset='+list.querySelectorAll('li.web-applet-card').length);const result=await response.json();if(!response.ok)throw Error(result.error);
    for(const card of result.cards)list.insertAdjacentHTML('beforeend',card);
    if(!result.more&&result.complete)button.remove();else{button.disabled=false;if(!result.more)alertIn(section,'Further source results were unavailable during capture. The captured Applets remain available.');}
  }catch(error){alertIn(section,error.message);button.disabled=false;}
});
document.querySelectorAll('.mcp-agent-showcase__code-copy,.mcp-agent-showcase__copy').forEach(button=>button.addEventListener('click',async()=>{
  const text=button.parentElement.querySelector('pre,code')?.textContent;if(!text)return;
  try{await navigator.clipboard.writeText(text);button.querySelector('span').textContent='Copied';}
  catch{const range=document.createRange();range.selectNodeContents(button.parentElement.querySelector('pre,code'));const selection=getSelection();selection.removeAllRanges();selection.addRange(range);button.querySelector('span').textContent='Selected';}
}));
const legalDrawer=document.querySelector('#terms-legal-drawer'),legalToggle=document.querySelector('.terms-legal-menu-toggle');
if(legalDrawer&&legalToggle){
  const close=()=>{legalDrawer.hidden=true;legalToggle.setAttribute('aria-expanded','false');legalToggle.focus();};
  legalToggle.onclick=()=>{legalDrawer.hidden=false;legalToggle.setAttribute('aria-expanded','true');legalDrawer.querySelector('button').focus();};
  legalDrawer.querySelector('.terms-legal-drawer-close').onclick=close;
  legalDrawer.addEventListener('click',e=>{if(e.target===legalDrawer)close();});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!legalDrawer.hidden)close();});
  document.querySelectorAll('.terms-legal-link').forEach(link=>link.addEventListener('click',()=>{
    document.querySelectorAll('.terms-legal-link').forEach(item=>item.classList.toggle('active',item.hash===link.hash));
    document.querySelector('.terms-legal-current').textContent=link.textContent.trim();
    if(!legalDrawer.hidden)close();
  }));
}
document.querySelectorAll('.create-applet-button').forEach(button=>button.addEventListener('click',()=>location.assign('/create')));
if(path==='/contact_sales'){
  const form=document.querySelector('form');let operation=crypto.randomUUID();
  if(form)form.onsubmit=async event=>{event.preventDefault();const button=form.querySelector('[type=submit]');button.disabled=true;
    try{const response=await fetch('/local/contact-sales',{method:'POST',headers:{'Content-Type':'application/json','X-IFTTT-Local':'1'},body:JSON.stringify({...Object.fromEntries(new FormData(form)),operation_key:operation})});const result=await response.json();if(!response.ok)throw Error(result.error);alertIn(form,result.message+' Reference: '+result.reference);}
    catch(error){alertIn(form,error.message);button.disabled=false;}
  };
}
