'use strict';
(() => {
  const currentPath = location.pathname;
  const params = new URLSearchParams(location.search);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let state, modules, account, serviceIcons={};
  const byRoute = route => modules.find(m => m.route === route);
  const serviceName = service => serviceIcons[service]?.label||({date_and_time:'Date & Time', feed:'RSS Feed', email:'Email', email_digest:'Email Digest', space:'Space', ifttt:'IFTTT', weather:'Weather Underground'}[service] || service.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase()));
  const serviceIcon = service => serviceIcons[service]?'<img class="local-module-icon" src="'+escape(serviceIcons[service].src)+'" alt="'+escape(serviceName(service))+'" width="32" height="32">':'';
  async function get(url) {const response = await fetch(url);const data=await response.json();if(!response.ok)throw Error(data.error || 'Unable to load');return data;}
  async function act(action, body={}) {
    const response=await fetch('/local/automation/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-IFTTT-Local':'1'},body:JSON.stringify({...body,operation_key:crypto.randomUUID()})});
    const data=await response.json();if(!response.ok)throw Error(data.error || 'Please try again');return data;
  }
  async function accountAction(action, body={}) {
    const response=await fetch('/local/account/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-IFTTT-Local':'1'},body:JSON.stringify(body)});
    const data=await response.json();if(!response.ok)throw Error(data.error||'Unable to save account');return data;
  }
  function message(host,text) {let target=host.querySelector('.local-error');if(!target){target=document.createElement('p');target.className='local-error';target.setAttribute('role','alert');host.append(target);}target.textContent=text;}
  async function refresh() {state=await get('/local/automation');return state;}
  function modal(title, content) {
    const dialog=document.createElement('dialog');dialog.className='local-business-dialog';
    dialog.innerHTML='<button type="button" class="local-close" aria-label="Close">×</button><h2>'+escape(title)+'</h2>'+content;
    document.body.append(dialog);dialog.querySelector('.local-close').onclick=()=>dialog.close();
    dialog.addEventListener('close',()=>dialog.remove());dialog.showModal();return dialog;
  }
  async function connect(service, done, additional=false) {
    const dialog=modal('Connect '+serviceName(service), '<p>This connection uses a local account. Events and actions stay in this offline IFTTT site.</p><form><label>Account name<input name="label" value="Local '+escape(serviceName(service))+'" required maxlength="160"></label><button class="button-primary" type="submit">Connect</button></form>');
    dialog.querySelector('form').onsubmit=async event=>{event.preventDefault();const form=event.currentTarget;
      try{const selected=additional?'local-'+crypto.randomUUID():'default';await act('connect',{service,label:new FormData(form).get('label'),account:selected});await refresh();dialog.close();if(done)done(selected);}catch(error){message(form,error.message);}};
  }
  function stepsOf(definition) {return [definition.trigger,...definition.actions,...(definition.queries||[])].filter(Boolean);}
  function connected(service, account='default') {return state.connections.some(c=>c.service===service&&c.account===account&&c.connected);}
  async function builder() {
    const privateEditor=currentPath==='/p/me/applets/new';
    const root=document.querySelector(privateEditor?'.applet-composer':'#diy-composer');
    if(!root){if(privateEditor)message(document.querySelector('main'),'This template’s source page did not provide a usable editor. Choose another template or create a new Applet.');return;}
    let draft={trigger:null,actions:[],queries:[],delay_seconds:0}, editing=null, published=null;
    let template=null;
    if(privateEditor&&params.get('from')){
      template=await get('/local/private-template?from='+encodeURIComponent(params.get('from')));
      if(template.unavailable){message(root,'This template has unavailable source modules: '+template.missing_schema_titles.join(', '));return;}
      draft=structuredClone(template.definition);
    }
    if(params.get('published')){
      published=await get('/local/published?path='+encodeURIComponent(params.get('published')));
      for(const route of published.modules){const module=byRoute(route);if(!module){message(root,'The source service no longer publishes this module. This Applet cannot be connected locally.');return;}
        const step={module:route,fields:{},account:'default'};if(module.kind==='triggers')draft.trigger=step;else draft[module.kind].push(step);
      }
    }
    if(params.get('edit')){editing=state.applets.find(a=>a.id===params.get('edit'));if(editing)draft=structuredClone(editing.definition);}
    function pick(kind, index=0) {
      const dialog=modal('Choose '+({triggers:'a trigger',actions:'an action',queries:'a query'}[kind]), '<label>Search services and modules<input type="search" placeholder="Search" autocomplete="off"></label><div class="local-module-options"></div>');
      const results=dialog.querySelector('.local-module-options');
      function list(term='') {
        const choices=modules.filter(m=>m.kind===kind && (serviceName(m.service)+' '+m.title).toLowerCase().includes(term.toLowerCase()));
        results.innerHTML=choices.map(m=>'<button type="button" data-module="'+escape(m.route)+'"><span>'+escape(serviceName(m.service))+'</span><strong>'+escape(m.title)+'</strong></button>').join('') || '<p>No matching modules.</p>';
        results.querySelectorAll('[data-module]').forEach(button=>button.onclick=()=>configure(byRoute(button.dataset.module)));
      }
      function configure(module, fieldValues=null, preferredAccount=null) {
        const previous=kind==='triggers'?draft.trigger:(kind==='actions'?draft.actions[index]:draft.queries[index]);
        const values=fieldValues||(previous?.module===module.route?previous.fields:{});
        dialog.querySelector('h2').textContent=module.title;
        dialog.querySelector('label').hidden=true;
        results.innerHTML='<p>'+escape(module.description)+'</p><form>'+module.fields.map(field=>{
          const name=field.Slug, required=field.Required==='true';
          return '<label>'+escape(field.Label || name)+(required?' *':'')+'<input name="'+escape(name)+'" '+(required?'required':'')+' value="'+escape(values[name]||'')+'"></label>';
        }).join('')+'<button type="submit" class="button-primary">'+(kind==='triggers'?'Create trigger':kind==='actions'?'Create action':'Add query')+'</button></form>';
        const accounts=state.connections.filter(c=>c.service===module.service&&c.connected);
        if(accounts.length){const field=document.createElement('label');field.innerHTML='Service account<select data-service-account>'+accounts.map(c=>'<option value="'+escape(c.account)+'">'+escape(c.label)+'</option>').join('')+'</select>';results.querySelector('form').prepend(field);field.querySelector('select').value=preferredAccount||(accounts.some(c=>c.account===previous?.account)?previous.account:accounts[0].account);}
        if(!accounts.length){
          const button=document.createElement('button');button.type='button';button.textContent='Connect '+serviceName(module.service);results.prepend(button);
          button.onclick=()=>connect(module.service,selected=>configure(module,Object.fromEntries(new FormData(results.querySelector('form'))),selected));
        }
        if(state.plan==='pro_plus'){const button=document.createElement('button');button.type='button';button.textContent='Connect another account';results.append(button);button.onclick=()=>connect(module.service,selected=>configure(module,Object.fromEntries(new FormData(results.querySelector('form'))),selected),true);}
        results.querySelector('form').onsubmit=event=>{event.preventDefault();const form=event.currentTarget;
          const selectedAccount=form.querySelector('[data-service-account]')?.value||'default';
          if(!connected(module.service,selectedAccount)){message(form,'Connect '+serviceName(module.service)+' to continue.');return;}
          const step={module:module.route,fields:Object.fromEntries(new FormData(form)),account:selectedAccount};
          if(kind==='triggers')draft.trigger=step;else draft[kind==='actions'?'actions':'queries'][index]=step;
          dialog.close();classic();
        };
      }
      dialog.querySelector('input').oninput=event=>list(event.target.value);
      const fixed=kind==='triggers'?draft.trigger:draft[kind][index];
      if(published&&fixed)configure(byRoute(fixed.module));else list();
    }
    function block(step,label,kind,index) {
      return '<section class="local-diy-block"><span>'+label+'</span>'+(step?serviceIcon(byRoute(step.module)?.service)+'<h3>'+escape(byRoute(step.module)?.title||step.module)+'</h3><p>'+escape(serviceName(byRoute(step.module)?.service||''))+'</p>':'')+'<button type="button" class="button-tertiary button-on-color" data-kind="'+kind+'" data-index="'+index+'" '+(kind!=='triggers'&&!draft.trigger?'disabled':'')+'>'+(step?'Edit':'Add')+'</button></section>';
    }
    function classic() {
      if(privateEditor){renderPrivate();return;}
      root.innerHTML='<div class="local-composer"><header><a href="/my_applets" aria-label="Cancel">‹</a><h1>Create</h1><span></span></header><p>You’re using '+state.applets.filter(a=>!a.archived).length+' of '+(state.limit??'unlimited')+' Applets. <a href="/plans">Upgrade for more Applets</a></p><div class="local-creation-modes"><button type="button" data-chat>Chat</button><button type="button" aria-pressed="true">Classic</button></div>'+block(draft.trigger,'If This','triggers',0)+draft.queries.map((step,i)=>block(step,'Query','queries',i)).join('')+(draft.actions.length?draft.actions.map((step,i)=>block(step,'Then That','actions',i)).join(''):block(null,'Then That','actions',0))+'<div class="local-composer-tools"><button type="button" data-more-action>Add action</button><button type="button" data-query>Add query</button><button type="button" data-filter>Filter code</button><label>Delay (seconds)<input type="number" min="0" max="10800" value="'+draft.delay_seconds+'" data-delay></label></div><button type="button" class="button-primary" data-continue '+(!draft.trigger||!draft.actions.length?'disabled':'')+'>Continue</button><p class="local-adapter-note">Connected services run locally. No events or actions are sent to third-party services.</p></div>';
      root.querySelectorAll('[data-kind]').forEach(button=>button.onclick=()=>pick(button.dataset.kind,Number(button.dataset.index)));
      root.querySelector('[data-chat]').onclick=()=>location.assign('/create');
      root.querySelector('[data-more-action]').onclick=()=>{if(state.plan==='free'){message(root,'Multiple actions require Pro.');return;}pick('actions',draft.actions.length);};
      root.querySelector('[data-query]').onclick=()=>{if(state.plan!=='pro_plus'){message(root,'Queries require Pro+.');return;}pick('queries',draft.queries.length);};
      root.querySelector('[data-filter]').onclick=()=>{
        if(state.plan!=='pro_plus'){message(root,'Filter code requires Pro+.');return;}
        if(!draft.trigger||!draft.actions.length){message(root,'Add a trigger and an action before adding filter code.');return;}
        const dialog=modal('Filter code','<p>Use the ingredient names and action methods shown in the module documentation. This local JavaScript runtime can skip actions and update their fields.</p><form><label>JavaScript<textarea name="filter_code" rows="12" maxlength="10000">'+escape(draft.filter_code||'')+'</textarea></label><button>Save filter code</button></form>');
        dialog.querySelector('form').onsubmit=event=>{event.preventDefault();draft.filter_code=new FormData(event.currentTarget).get('filter_code');dialog.close();message(root,'Filter code added.');};
      };
      root.querySelector('[data-delay]').onchange=event=>{if(state.plan!=='pro_plus'&&Number(event.target.value)){event.target.value=draft.delay_seconds;message(root,'Delay requires Pro+.');return;}draft.delay_seconds=Number(event.target.value);};
      root.querySelector('[data-continue]').onclick=()=>{
      const title=editing?.title || published?.title || 'If '+byRoute(draft.trigger.module).title+', then '+byRoute(draft.actions[0].module).title;
        const dialog=modal('Review and finish','<form><label>Applet title<input name="title" value="'+escape(title)+'" required maxlength="300"></label><p>Finish will connect this Applet using your local service accounts.</p><button class="button-primary" type="submit">Finish</button></form>');
        dialog.querySelector('form').onsubmit=async event=>{event.preventDefault();const form=event.currentTarget,button=form.querySelector('button');button.disabled=true;
          try{const result=await act(editing?'update':'create',{id:editing?.id,revision:editing?.revision,title:new FormData(form).get('title'),definition:draft,source_path:published?params.get('published'):undefined});location.assign(result.redirect);}
          catch(error){message(form,error.message);button.disabled=false;}
        };
      };
    }
    function renderPrivate() {
      const title=root.querySelector('input[maxlength="100"]'), description=root.querySelector('textarea[maxlength="500"]');
      if(!title||!description)return;
      title.setAttribute('aria-label','Applet title');description.setAttribute('aria-label','Applet description');
      if(!root.dataset.localReady){title.value=template?.title||editing?.title||'';description.value=draft.description||'';root.dataset.localReady='true';}
      const save=root.querySelector('.actions button[type="submit"]');
      const update=()=>{draft.description=description.value;save.disabled=!draft.trigger||!draft.actions.length||!title.value.trim()||!description.value.trim();
        for(const input of [title,description]){const counter=input.closest('.limited-text-input')?.querySelector('.limit');if(counter)counter.textContent=input.value.length+'/'+input.maxLength;}};
      title.oninput=description.oninput=update;
      const trigger=root.querySelector('#trigger .partners-tanda-composer-selectors');
      if(trigger){
        if(draft.trigger)trigger.innerHTML='<p>'+escape(serviceName(byRoute(draft.trigger.module).service))+' · '+escape(byRoute(draft.trigger.module).title)+'</p><button type="button" data-private-trigger>Edit trigger</button>';
        const control=trigger.querySelector('button,input');control.setAttribute('aria-label','Choose trigger');control.onclick=()=>pick('triggers');
        if(control.tagName==='INPUT')control.oninput=()=>pick('triggers');
      }
      const sectionFor=name=>root.querySelector('[title="'+name+'"]')?.closest('.composer-section-with-icon');
      const actionSection=sectionFor('Action');
      if(actionSection){
        root.querySelectorAll('[title="Action"]').forEach(icon=>{const section=icon.closest('.composer-section-with-icon');if(section!==actionSection)section.hidden=true;});
        actionSection.querySelectorAll('.local-private-steps').forEach(node=>node.remove());
        if(draft.actions.length){const items=document.createElement('div');items.className='local-private-steps';items.innerHTML=draft.actions.map((s,i)=>'<p>'+escape(serviceName(byRoute(s.module).service))+' · '+escape(byRoute(s.module).title)+' <button type="button" data-step="'+i+'">Edit action</button> <button type="button" data-remove-step="'+i+'">Remove</button></p>').join('');
          actionSection.append(items);items.querySelectorAll('[data-step]').forEach(button=>button.onclick=()=>pick('actions',Number(button.dataset.step)));
          items.querySelectorAll('[data-remove-step]').forEach(button=>button.onclick=()=>{draft.actions.splice(Number(button.dataset.removeStep),1);renderPrivate();});}
        // Template snapshots contain filled source selectors; the live local steps replace them.
        actionSection.querySelectorAll('.partners-tanda-composer').forEach(node=>node.hidden=true);
        let add=actionSection.querySelector('input[type="button"]');
        if(!add){add=document.createElement('input');add.type='button';add.value='Add action';add.className='button-tertiary';actionSection.append(add);}
        add.disabled=!draft.trigger;add.onclick=()=>{if(draft.actions.length&&state.plan==='free'){message(root,'Multiple actions require Pro.');return;}pick('actions',draft.actions.length);};
      }
      const filterSection=sectionFor('Filter'), filterButton=filterSection?.querySelector('input[type="button"]');
      if(filterButton){filterButton.disabled=!draft.trigger||!draft.actions.length;filterButton.onclick=()=>{
        if(state.plan!=='pro_plus'){message(root,'Filter code requires Pro+.');return;}
        const dialog=modal('Filter code','<form><label>JavaScript<textarea name="filter_code" rows="12" maxlength="10000">'+escape(draft.filter_code||'')+'</textarea></label><button>Save filter code</button></form>');
        dialog.querySelector('form').onsubmit=e=>{e.preventDefault();draft.filter_code=new FormData(e.currentTarget).get('filter_code');dialog.close();message(root,'Filter code saved in this draft.');};
      };}
      const delayButton=sectionFor('Delay')?.querySelector('input[type="button"]');
      if(delayButton){delayButton.disabled=!draft.trigger;delayButton.onclick=()=>{
        if(state.plan!=='pro_plus'){message(root,'Delay requires Pro+.');return;}
        const dialog=modal('Delay','<form><label>Delay in seconds (0 removes the delay)<input name="seconds" type="number" min="0" max="10800" value="'+draft.delay_seconds+'" required></label><button>Save delay</button></form>');
        dialog.querySelector('form').onsubmit=e=>{e.preventDefault();const seconds=Number(new FormData(e.currentTarget).get('seconds'));if(seconds!==0&&seconds<15){message(e.currentTarget,'Delay must be between 15 seconds and 3 hours.');return;}draft.delay_seconds=seconds;dialog.close();delayButton.value=seconds?'Delay: '+seconds+' seconds':'Add delay';};
      };}
      if(state.plan==='pro_plus'){
        const section=sectionFor('Query');if(section){let button=section.querySelector('[data-private-query]');if(!button){section.querySelector('.composer-add-field-message')?.remove();button=document.createElement('button');button.type='button';button.dataset.privateQuery='true';section.append(button);}button.textContent=draft.queries.length?'Add query ('+draft.queries.length+' added)':'Add query';button.disabled=!draft.trigger;button.onclick=()=>pick('queries',draft.queries.length);}
      }
      const service=root.querySelector('.applet-composer-primary-service-input select');
      const choices=[...new Set(stepsOf(draft).map(step=>byRoute(step.module).service))];
      if(choices.length){service.disabled=false;service.innerHTML=choices.map(s=>'<option value="'+escape(s)+'">'+escape(serviceName(s))+'</option>').join('');service.value=choices.includes(draft.card_service)?draft.card_service:choices[0];draft.card_service=service.value;service.onchange=()=>draft.card_service=service.value;}
      root.querySelector('.local-private-connections')?.remove();
      const missing=choices.filter(s=>!connected(s));
      if(missing.length){const connections=document.createElement('div');connections.className='local-private-connections';connections.innerHTML='<p>Connect local service accounts to save this Applet.</p>'+missing.map(s=>'<button type="button" data-connect="'+escape(s)+'">Connect '+escape(serviceName(s))+'</button>').join('');root.querySelector('.actions').before(connections);connections.querySelectorAll('button').forEach(button=>button.onclick=()=>connect(button.dataset.connect,renderPrivate));}
      root.querySelectorAll('.composer-fieldset-disabled').forEach(node=>{if(node.querySelector('input[type="button"]:not(:disabled)'))node.classList.remove('composer-fieldset-disabled');});
      save.onclick=async e=>{e.preventDefault();update();if(save.disabled)return;save.disabled=true;
        try{const result=await act(editing?'update':'create',{id:editing?.id,revision:editing?.revision,title:title.value,definition:draft});location.assign(result.redirect);}catch(error){message(root,error.message);update();}};
      update();
    }
    if(privateEditor){renderPrivate();return;}
    root.querySelectorAll('button').forEach(button=>{
      const text=button.textContent.trim();
      if(text==='Classic')button.onclick=classic;
      if(button.getAttribute('aria-label')==='Cancel')button.onclick=()=>location.assign('/my_applets');
      if(text==='Upgrade for more Applets')button.onclick=()=>location.assign('/plans');
      if(text==='Add')button.onclick=()=>{classic();pick('triggers');};
    });
    const textarea=root.querySelector('textarea'), start=root.querySelector('#continue');
    if(textarea&&start){textarea.oninput=()=>{start.disabled=!textarea.value.trim();};
      if(params.get('prompt')){textarea.value=params.get('prompt').slice(0,500);start.disabled=false;}
      root.querySelectorAll('[class*="examples"] button').forEach(button=>button.onclick=()=>{textarea.value=button.textContent.trim();textarea.dispatchEvent(new Event('input'));textarea.focus();});
      start.onclick=()=>{const description=textarea.value.trim();classic();const notice=document.createElement('p');notice.className='local-adapter-note';notice.textContent='Local builder: choose the trigger and action for “'+description+'”. Cloud AI is not connected.';root.querySelector('.local-composer').prepend(notice);pick('triggers');};
    }
    const uncapturedModules=[];
    for(const [key,kind] of [['template_trigger','triggers'],['template_actions','actions'],['template_action','actions'],['template_queries','queries'],['template_query','queries']]){
      const module=modules.find(m=>m.kind===kind&&m.developer_info?.['API endpoint slug']===params.get(key));
      if(module){const step={module:module.route,fields:{},account:'default'};if(kind==='triggers')draft.trigger=step;else if(!draft[kind].some(item=>item.module===step.module))draft[kind].push(step);classic();}
      else if(params.get(key))uncapturedModules.push(params.get(key));
    }
    if(editing||published||params.get('mode')==='classic')classic();
    if(uncapturedModules.length){classic();const notice=document.createElement('p');notice.className='local-adapter-note';notice.textContent='Requested module: '+uncapturedModules.join(', ')+'. Its configuration is outside the captured full-detail selection. Choose one of the captured modules to build a local Applet.';root.querySelector('.local-composer').prepend(notice);}
  }
  function cards() {
    const host=document.querySelector('.my-applets-wrapper');if(!host)return;
    const archived=params.get('tab')==='archived';
    const list=state.applets.filter(a=>Boolean(a.archived)===archived);
    const navigation='<nav class="local-applet-tabs"><a href="/my_applets">My Applets</a><a href="/my_applets?tab=archived">Archived</a><a href="/create">Create</a></nav>';
    if(!list.length&&!archived){host.insertAdjacentHTML('afterbegin',navigation);return;}
    host.innerHTML=navigation+'<h1>'+(archived?'Archived Applets':'My Applets')+'</h1><ul class="web-applet-cards local-applet-cards">'+list.map(a=>'<li class="my-web-applet-card web-applet-card"><a class="applet-card-body local-applet-card" href="/applets/'+escape(a.id)+'"><div class="content"><div class="title">'+escape(a.title)+'</div></div><p>'+(a.archived?'Archived':a.enabled?'Connected':'Disconnected')+'</p></a></li>').join('')+'</ul>'+(list.length?'':'<p>No archived Applets.</p>');
  }
  function privateCards() {
    if(!currentPath.startsWith('/p/me/applets')||currentPath.endsWith('/new'))return;
    const own=state.applets.filter(a=>a.origin==='diy');
    document.querySelectorAll('.applets-sidebar .sidebar-nav-count').forEach(count=>{const href=count.closest('a').getAttribute('href');count.textContent=href.endsWith('/private')?own.filter(a=>!a.archived).length:href.endsWith('/archived')?own.filter(a=>a.archived).length:0;});
    if(currentPath.endsWith('/templates')||currentPath.endsWith('/published'))return;
    const list=own.filter(a=>Boolean(a.archived)===currentPath.endsWith('/archived'));
    if(!list.length)return;
    const host=document.querySelector('.main-content-column');host.querySelector('.zero-case')?.remove();
    const cards=document.createElement('ul');cards.className='web-applet-cards local-applet-cards';cards.innerHTML=list.map(a=>'<li class="web-applet-card"><a class="applet-card-body local-applet-card" href="/applets/'+escape(a.id)+'"><span class="title">'+escape(a.title)+'</span><p>'+escape(a.definition.description||'')+'</p><p>'+(a.archived?'Archived':a.enabled?'Connected':'Disconnected')+'</p></a></li>').join('');host.append(cards);
  }
  function details() {
    const host=document.querySelector('#local-applet-detail');if(!host)return;
    const applet=state.applets.find(a=>a.id===host.dataset.appletId);if(!applet)return;
    const title=a=>escape(byRoute(a.module)?.title||a.module);
    host.innerHTML='<p class="local-applet-status">'+(applet.archived?'Archived':applet.enabled?'Connected':'Disconnected')+'</p><section><h2>If '+title(applet.definition.trigger)+'</h2>'+applet.definition.actions.map(a=>'<h2>Then '+title(a)+'</h2>').join('')+'</section><div class="local-applet-actions">'+(applet.archived?'<button data-action="restore">Restore</button><button data-action="delete">Delete permanently</button>':'<button data-action="'+(applet.enabled?'disable':'enable')+'">'+(applet.enabled?'Disconnect':'Connect')+'</button><a href="/create?edit='+escape(applet.id)+'">Edit</a><button data-action="archive">Archive</button>')+'</div>'+(!applet.archived?'<section class="local-event-form"><h2>Run a local event</h2><p>Enter trigger ingredients. Actions write results to this local account’s activity and effect store.</p><form><label>Ingredients (JSON)<textarea name="ingredients" rows="5">{}</textarea></label><button type="submit" '+(!applet.enabled?'disabled':'')+'>Run once</button></form></section>':'')+'<p><a href="/activity?applet='+escape(applet.id)+'">View activity</a> · <a href="/my_applets">My Applets</a></p><div class="local-effect-results"></div>';
    host.querySelectorAll('[data-action]').forEach(button=>button.onclick=()=>{
      const perform=async()=>{try{await act(button.dataset.action,{id:applet.id});if(button.dataset.action==='delete'){location.assign('/my_applets?tab=archived');return;}await refresh();details();}catch(error){message(host,error.message);}};
      if(['delete','archive'].includes(button.dataset.action)){
        const dialog=modal(button.dataset.action==='delete'?'Delete this Applet permanently?':'Archive this Applet?','<p>'+(button.dataset.action==='delete'?'This removes the Applet. Its activity history is retained.':'This stops the Applet and frees a place in your plan. You can restore it later.')+'</p><button type="button" data-confirm>Confirm</button>');
        dialog.querySelector('[data-confirm]').onclick=()=>{dialog.close();perform();};
      }else perform();
    });
    if(applet.origin!=='diy'){
      const edit=host.querySelector('a[href^="/create?edit="]');if(edit){edit.textContent='Make it your own';edit.onclick=event=>{event.preventDefault();const dialog=modal('Make it your own','<p>Convert this published Applet into an editable Applet in your local account.</p><button data-convert>Convert</button>');dialog.querySelector('[data-convert]').onclick=async()=>{try{const result=await act('convert',{id:applet.id});location.assign(result.redirect);}catch(error){message(dialog,error.message);}};};}
      const archive=host.querySelector('[data-action="archive"]');if(archive){archive.textContent='Delete';archive.dataset.action='delete';}
    }
    host.querySelector('form')?.addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget,button=form.querySelector('button');button.disabled=true;
      try{await act('run',{id:applet.id,ingredients:JSON.parse(new FormData(form).get('ingredients'))});await refresh();details();message(host,'Local event recorded. See activity for execution details.');}
      catch(error){message(form,error.message);button.disabled=false;}
    });
    const effects=state.effects.filter(effect=>state.runs.some(run=>run.id===effect.run_id&&run.applet_id===applet.id));
    if(effects.length)host.querySelector('.local-effect-results').innerHTML='<h2>Local action results</h2>'+effects.map(effect=>'<details><summary>'+escape(serviceName(effect.service))+' · '+escape(new Date(effect.created_at*1000).toLocaleString())+'</summary><pre>'+escape(JSON.stringify(effect.payload,null,2))+'</pre></details>').join('');
  }
  function activity() {
    if(!currentPath.startsWith('/activity'))return;
    const host=document.querySelector('.feed .items')||document.querySelector('main');if(!host)return;
    let runs=state.runs;
    if(params.get('applet'))runs=runs.filter(r=>r.applet_id===params.get('applet'));
    const service=currentPath.startsWith('/activity/service/')?currentPath.split('/')[3]:null;
    if(service)runs=runs.filter(r=>stepsOf(r.definition).some(s=>byRoute(s.module)?.service===service));
    if(!runs.length){const time=host.querySelector('.item-time');if(time)time.textContent=new Date(account.created_at*1000).toLocaleString();return;}
    host.innerHTML=runs.map(run=>'<li class="item"><div class="feed-item"><div class="item-header"><h3><a href="/applets/'+escape(run.applet_id)+'">'+escape(state.applets.find(a=>a.id===run.applet_id)?.title||'Deleted Applet')+'</a></h3><time>'+escape(new Date(run.created_at*1000).toLocaleString())+'</time></div><p>'+escape(run.status==='pending'?'Waiting for delay':run.status)+'</p><details><summary>View details</summary>'+run.steps.map(step=>'<section><h4>'+escape(step.kind)+' · '+escape(step.status)+'</h4><pre>'+escape(JSON.stringify(step,null,2))+'</pre></section>').join('')+'</details></div></li>').join('');
  }
  function services() {
    if(currentPath==='/my_services'){
      const list=document.querySelector('.services-list');if(!list)return;
      const originals=new Map([...list.querySelectorAll('.service-card')].map(a=>[a.getAttribute('href').split('/')[1],a.closest('li').outerHTML]));
      list.innerHTML=state.connections.filter(c=>c.connected).map(c=>originals.get(c.service)||'<li class="service-item"><a class="service-card service-card-small" style="background:#333" href="/'+escape(c.service)+'"><span class="service-card-title">'+escape(serviceName(c.service))+'</span></a></li>').join('');
    }
    const service=currentPath.split('/')[1];
    if(!modules.some(m=>m.service===service))return;
    if(currentPath.endsWith('/my_applets')){
      const host=document.querySelector('.my-applets-tab .my_applets');
      const applets=state.applets.filter(a=>!a.archived&&stepsOf(a.definition).some(step=>byRoute(step.module)?.service===service));
      if(host&&applets.length)host.innerHTML='<ul class="web-applet-cards local-applet-cards">'+applets.map(a=>'<li class="web-applet-card"><a class="applet-card-body local-applet-card" href="/applets/'+escape(a.id)+'"><span class="title">'+escape(a.title)+'</span><p>'+(a.enabled?'Connected':'Disconnected')+'</p></a></li>').join('')+'</ul>';
    }
    if(currentPath.endsWith('/settings')){
      const connection=state.connections.find(c=>c.service===service&&c.account==='default');
      document.querySelectorAll('.settings-attribute').forEach(item=>{const label=item.querySelector('.label')?.textContent.trim();const value=item.querySelector('.value');if(value){if(label==='Status')value.textContent=connected(service)?'Active':'Disconnected';else if(label==='Time Zone')value.textContent=connection?.settings?.timezone||state.settings.timezone||'UTC';else if(value.textContent.includes('[PRIVATE]'))value.textContent=account.account.display_name;}});
      document.querySelectorAll('.credential-actions a.edit').forEach(control=>control.onclick=async event=>{event.preventDefault();try{const zones=await get('/local/timezones');const dialog=modal('Update timezone','<form><label>Time zone<select name="timezone">'+Object.keys(zones).map(zone=>'<option>'+escape(zone)+'</option>').join('')+'</select></label><button>Save timezone</button></form>');dialog.querySelector('select').value=connection?.settings?.timezone||state.settings.timezone||'UTC';dialog.querySelector('form').onsubmit=async e=>{e.preventDefault();try{await act('service-settings',{service,timezone:new FormData(e.currentTarget).get('timezone')});await refresh();dialog.close();services();}catch(error){message(e.target,error.message);}};}catch(error){message(document.querySelector('.after-header-content')||document.querySelector('main'),error.message);}});
      document.querySelectorAll('a.remove').forEach(link=>link.onclick=event=>{event.preventDefault();const dialog=modal('Remove '+serviceName(service)+'?', '<p>Associated Applets will be archived and will stop running.</p><button data-remove>Remove service</button>');dialog.querySelector('[data-remove]').onclick=async()=>{try{await act('disconnect',{service});location.assign('/my_services');}catch(error){message(dialog,error.message);}};});
    } else if(currentPath==='/'+service){
      document.querySelectorAll('main a, main button, .after-header-content a, .after-header-content button').forEach(control=>{
        if(control.textContent.trim()==='Connect')control.onclick=event=>{event.preventDefault();connect(service,()=>location.reload());};
      });
    }
  }
  function billing() {
    if(currentPath.startsWith('/subscriptions/')){
      const plan=currentPath.split('/')[2];if(!['pro','pro_plus'].includes(plan))return;
      let interval=['month','monthly'].includes(params.get('interval'))?'monthly':'yearly';
      const segments=[...document.querySelectorAll('[class*="price-toggle-segment"]')];
      const selectedClass=segments.flatMap(segment=>[...segment.classList]).find(name=>name.includes('selected-price'));
      segments.forEach((segment,index)=>{
        segment.tabIndex=0;
        const choose=()=>{interval=index?'monthly':'yearly';segments.forEach((s,i)=>{s.setAttribute('aria-pressed',String(i===index));s.classList.toggle('local-selected-price',i===index);if(selectedClass)s.classList.toggle(selectedClass,i===index);});
          const amount=plan==='pro'?(index?'4.99':'35.88'):(index?'14.99':'107.88');
          const notice=document.querySelector('[data-local-price]');if(notice)notice.textContent='$'+amount+' billed '+interval+' after the 7-day local trial.';
        };segment.onclick=choose;segment.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();choose();}};
      });
      document.querySelector('[aria-label="Back button"]')?.addEventListener('click',()=>location.assign('/plans'));
      const form=document.querySelector('.payment-info-form');if(!form)return;
      form.querySelectorAll('[class*="express-checkout-region"], [class*="payment-element-slot"]').forEach(element=>element.remove());
      form.insertAdjacentHTML('afterbegin','<section class="local-checkout"><h2>Local payment sandbox</h2><p>This offline trial does not charge a card or connect to a bank.</p><p data-local-price>$'+(plan==='pro'?'35.88':'107.88')+' billed yearly after the 7-day local trial.</p><label>Payment outcome<select name="scenario"><option value="sandbox-approved">Approve test payment</option><option value="sandbox-declined">Decline test payment</option><option value="sandbox-retry">Temporary failure</option></select></label></section>');
      segments[interval==='monthly'?1:0]?.click();
      form.onsubmit=async event=>{event.preventDefault();const button=form.querySelector('[type=submit]');button.disabled=true;
        try{const result=await act('checkout',{plan,interval,scenario:new FormData(form).get('scenario')});if(result.redirect)location.assign(result.redirect);else message(form,result.message);}
        catch(error){message(form,error.message);}finally{button.disabled=false;}
      };
      form.querySelector('[type=submit]').disabled=false;
      form.querySelector('a[href="#"]')?.addEventListener('click',event=>{event.preventDefault();location.assign('/hc/en-us');});
    }
    if(currentPath==='/billing'&&state.billing){
      const host=document.querySelector('.side-menu-content')||document.querySelector('main');
      host.innerHTML='<h1>Billing</h1><section class="local-billing"><h2>'+escape(state.plan==='free'?'Free':state.plan==='pro'?'Pro':'Pro+')+'</h2><p>'+escape(state.billing.status)+'</p><p>Local payment sandbox · $'+(state.billing.amount_minor/100).toFixed(2)+' / '+escape(state.billing.interval)+'</p><p>Trial ends '+escape(new Date(state.billing.trial_ends_at*1000).toLocaleString())+'</p><a href="/plans">Switch plans</a>'+(state.billing.status==='cancelled'?'':'<button type="button" data-cancel-plan>Cancel subscription</button>')+'</section>';
      host.querySelector('[data-cancel-plan]')?.addEventListener('click',()=>{
        const dialog=modal('Cancel local subscription?','<p>Your account returns to Free immediately in this local sandbox. Only the newest two unarchived Applets will remain; any additional Applets are archived.</p><button data-confirm>Cancel subscription</button>');
        dialog.querySelector('[data-confirm]').onclick=async()=>{try{await act('cancel-subscription');location.reload();}catch(error){message(dialog,error.message);}};
      });
    }
  }
  async function accountSettings() {
    if(!['/settings','/settings/change_password','/profile/edit','/two-step-verification/start','/settings/confirm_deletion','/referral','/applet_discovery','/applet_discovery/goals','/applet_discovery/services','/developer_sign_up/new'].includes(currentPath))return;
    const details=await get('/local/account');
    const username=document.querySelector('#account_login');if(username)username.value=account.account.display_name;
    if(currentPath==='/settings'){
      const email=document.querySelector('#account_email');if(email)email.value=account.account.email_normalized;
      const timezone=document.querySelector('#account_timezone');if(timezone)timezone.value=state.settings.timezone||'UTC';
      const password=document.querySelector('#password');if(password){password.value='********';password.readOnly=true;}
      document.querySelectorAll('input[type=checkbox]').forEach(input=>{const key=input.name.match(/\[(.+)\]/)?.[1];if(key)input.checked=state.settings[key]??['auto_shorten_urls','send_alerts'].includes(key);});
      document.querySelectorAll('main .form-section').forEach(section=>{
        if(section.querySelector('h3,h4,h2')?.textContent.trim()==='Active sessions')section.innerHTML='<h3>Active sessions</h3><p>Devices and browsers currently signed in to your local IFTTT account.</p><ul>'+details.sessions.map(session=>'<li>Local browser session · Signed in '+escape(new Date(session.created_at*1000).toLocaleString())+'</li>').join('')+'</ul>';
      });
      const form=document.querySelector('#account_email')?.closest('form');
      if(form){const submit=form.querySelector('[type=submit]');if(submit)submit.value='Save changes';
        form.onsubmit=async event=>{event.preventDefault();const values=new FormData(form),body={username:values.get('account[login]'),timezone:values.get('account[timezone]')};
          document.querySelectorAll('input[type=checkbox]').forEach(input=>{const key=input.name.match(/\[(.+)\]/)?.[1];if(key)body[key]=input.checked;});
          try{const result=await accountAction('settings',body);message(form,result.message);
            if(values.get('account[email]')!==account.account.email_normalized){
              const dialog=modal('Verify your new email','<form><label>Current password<input type="password" name="password" required></label><button>Send verification email</button></form>');
              dialog.querySelector('form').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget;
                try{await accountAction('email-start',{email:values.get('account[email]'),password:new FormData(form).get('password')});
                  form.innerHTML='<p>A verification code was sent to the new address in the local inbox.</p><label>Verification code<input name="code" required></label><button>Verify email</button>';
                  form.onsubmit=async event=>{event.preventDefault();try{const verified=await accountAction('email-verify',{code:new FormData(form).get('code')});location.assign(verified.redirect);}catch(error){message(form,error.message);}};
                }catch(error){message(form,error.message);}
              };
            }
          }catch(error){message(form,error.message);}
        };
      }
      const mfa=document.querySelector('a[href="/two-step-verification/start"]');
      if(mfa&&details.two_step_enabled){mfa.textContent='Disable two-step verification';mfa.onclick=event=>{event.preventDefault();const dialog=modal('Disable two-step verification','<form><label>Current password<input type="password" name="password" required></label><label>Authenticator or backup code<input name="code" required></label><button>Disable</button></form>');dialog.querySelector('form').onsubmit=async e=>{e.preventDefault();try{const result=await accountAction('two-step-disable',Object.fromEntries(new FormData(e.currentTarget)));location.assign(result.redirect);}catch(error){message(e.target,error.message);}};};}
      if(details.profile.provider!=='None'){
        const profile=document.querySelector('a[href="/profile/edit"]');if(profile)profile.textContent='Profile: '+details.profile.provider+' (local)';
      }
      const exportLink=document.querySelector('a[href="/settings/export_my_data"]');
      if(exportLink)exportLink.onclick=async event=>{event.preventDefault();try{const result=await accountAction('export');message(form,result.message);}catch(error){message(form,error.message);}};
      const linkProvider=(control,provider)=>{
        if(!control)return;control.setAttribute('role','button');control.tabIndex=0;
        if(details['linked-accounts']?.[provider]?.connected){control.textContent=provider+' linked locally';control.setAttribute('aria-label',control.textContent);}
        control.onclick=event=>{event.preventDefault();const dialog=modal('Link '+provider+' locally','<p>This links the local identity adapter to your current IFTTT account. No credentials are sent to '+escape(provider)+'.</p><form><label>Current password<input type="password" name="password" required></label><button>Link account</button></form>');
          dialog.querySelector('form').onsubmit=async e=>{e.preventDefault();try{await accountAction('preference',{kind:'linked-accounts',provider,password:new FormData(e.currentTarget).get('password')});location.reload();}catch(error){message(e.target,error.message);}};
        };control.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();control.click();}};
      };
      linkProvider(document.querySelector('#appleid-signin a'),'Apple');
      linkProvider(document.querySelector('#facebook-signin'),'Facebook');
      linkProvider(document.querySelector('.profile-linked-accounts button'),'Google');
      linkProvider(document.querySelector('a[href^="/settings/shortener_oauth_connect"]'),'Bitly');
    }
    if(currentPath==='/settings/change_password'){
      if(username)username.readOnly=true;
      const form=document.querySelector('#old_password')?.closest('form');if(form)form.onsubmit=async event=>{event.preventDefault();const values=new FormData(form);
        try{const result=await accountAction('password',{current_password:values.get('old_password'),password:values.get('user[password]'),confirmation:values.get('user[password_confirmation]')});location.assign(result.redirect);}catch(error){message(form,error.message);}
      };
    }
    if(currentPath==='/profile/edit'){
      let selected=details.profile.provider;
      const items=[...document.querySelectorAll('.provider-view li')],button=document.querySelector('.set-profile-actions button');
      items.forEach(item=>{item.tabIndex=0;item.setAttribute('role','radio');const name=item.querySelector('span').textContent;item.setAttribute('aria-checked',String(selected===name));
        const choose=()=>{selected=name;items.forEach(i=>{const active=i===item;i.classList.toggle('checked',active);i.classList.toggle('unchecked',!active);i.setAttribute('aria-checked',String(active));});button.disabled=false;};
        item.onclick=choose;item.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();choose();}};
      });
      const label=document.querySelector('.provider-name');if(label)label.textContent=selected;
      if(button)button.onclick=async()=>{try{const result=await accountAction('profile',{provider:selected});location.assign(result.redirect);}catch(error){message(document.querySelector('.provider-view'),error.message);}};
    }
    if(currentPath==='/two-step-verification/start'){
      const form=document.querySelector('main form');if(form)form.onsubmit=async event=>{event.preventDefault();
        try{const result=await accountAction('two-step-start',{password:new FormData(form).get('password')});
          const dialog=modal('Set up your authenticator','<p>'+escape(result.message)+'</p><label>Setup key<input readonly value="'+escape(result.secret)+'"></label><form><label>Verification code<input name="code" inputmode="numeric" autocomplete="one-time-code" required></label><button>Enable two-step verification</button></form>');
          dialog.querySelector('form').onsubmit=async e=>{e.preventDefault();try{const enabled=await accountAction('two-step-enable',{code:new FormData(e.currentTarget).get('code')});dialog.close();const backup=modal('Save your backup codes','<p>'+escape(enabled.message)+'</p><pre>'+enabled.backup_codes.map(escape).join('\n')+'</pre><a href="/settings">Done</a>');backup.querySelector('a').focus();}catch(error){message(e.target,error.message);}};
        }catch(error){message(form,error.message);}
      };
    }
    if(currentPath==='/settings/confirm_deletion'){
      const link=document.querySelector('#verify-by-password');
      const original=document.querySelector('form.account-form');
      if(link)link.onclick=event=>{event.preventDefault();original.querySelector('.completable-form').classList.remove('hidden');link.closest('p')?.setAttribute('hidden','');document.querySelector('#verify-delete-account').hidden=true;original.querySelector('#password').focus();};
      original?.querySelectorAll('.survey .title').forEach(control=>{control.setAttribute('role','button');control.tabIndex=0;control.onclick=()=>{original.querySelectorAll('.item-content').forEach(node=>node.classList.add('hidden'));control.closest('li').querySelector('.item-content').classList.remove('hidden');};control.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();control.click();}};});
      if(original)original.onsubmit=event=>{event.preventDefault();const password=original.querySelector('#password').value;
        const dialog=modal('Delete your account','<p>This permanently removes your local Applets and account data.</p><form>'+(details.two_step_enabled?'<label>Authenticator or backup code<input name="code" required></label>':'')+'<label>Type DELETE<input name="confirmation" required></label><button>Delete account</button></form>');
        dialog.querySelector('form').onsubmit=async e=>{e.preventDefault();try{const result=await accountAction('delete',{...Object.fromEntries(new FormData(e.currentTarget)),password});location.assign(result.redirect);}catch(error){message(e.target,error.message);}};
      };
      const send=document.querySelector('#verify-delete-account');if(send){send.type='button';send.onclick=async()=>{send.disabled=true;
        try{await accountAction('delete-start');const dialog=modal('Verify account deletion','<p>A verification code was sent to your local inbox. Deletion permanently removes your local Applets and account data.</p><form><label>Email verification code<input name="code" required inputmode="numeric"></label>'+(details.two_step_enabled?'<label>Authenticator or backup code<input name="factor" required></label>':'')+'<label>Type DELETE<input name="confirmation" required></label><button>Delete account</button></form>');
          dialog.querySelector('form').onsubmit=async e=>{e.preventDefault();try{const result=await accountAction('delete-verify',Object.fromEntries(new FormData(e.currentTarget)));location.assign(result.redirect);}catch(error){message(e.target,error.message);}};
        }catch(error){message(original,error.message);}finally{send.disabled=false;}
      };}
    }
    if(currentPath==='/referral'){
      const input=document.querySelector('.referral-code'),url=location.origin+'/join?referral_code='+encodeURIComponent(details.referral_code);
      if(input){input.value=url;input.setAttribute('aria-label','Your referral link');}
      const copy=document.querySelector('button.share-link');if(copy)copy.onclick=async()=>{try{await navigator.clipboard.writeText(url);document.querySelector('.copy-feedback').textContent='Link copied';}catch{input.focus();input.select();document.querySelector('.copy-feedback').textContent='Select and copy your link';}};
      document.querySelectorAll('a.share-button').forEach(control=>{const title=control.title;const target=title.includes('Facebook')?'https://www.facebook.com/sharer/sharer.php?u='+encodeURIComponent(url):title.includes('email')?'mailto:?subject=Join%20IFTTT&body='+encodeURIComponent(url):'https://twitter.com/intent/tweet?text='+encodeURIComponent(url);control.href='/external?url='+encodeURIComponent(target);});
    }
    if(currentPath.startsWith('/applet_discovery')){
      const host=document.querySelector('main');
      host.querySelectorAll('button').forEach(button=>{if(button.textContent.trim()==='Back')button.onclick=()=>location.assign(currentPath.endsWith('/services')?'/applet_discovery':'/settings');});
      if(['/applet_discovery','/applet_discovery/goals'].includes(currentPath))host.querySelectorAll('a:not([href])').forEach((control,index)=>{const goal=['home','business','other'][index];if(!goal)return;control.tabIndex=0;control.setAttribute('role','button');control.onclick=async()=>{try{await accountAction('preference',{kind:'discovery',goal});location.assign('/applet_discovery/services');}catch(error){message(host,error.message);}};control.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();control.click();}};});
      else host.querySelectorAll('a').forEach(control=>{if(control.textContent.trim()==='Skip')control.href='/explore';});
    }
    if(currentPath==='/developer_sign_up/new'){
      const form=document.querySelector('form.apply-form');if(form){if(details.developer)form.querySelector('#org_name').value=details.developer.name;
        form.onsubmit=async event=>{event.preventDefault();try{const result=await accountAction('preference',{kind:'developer',name:new FormData(form).get('org_name')});form.innerHTML='<h1>'+escape(result.value.name)+'</h1><p>Your local developer workspace is ready. Manage private Applets and templates here; publishing to IFTTT is not connected.</p><a class="button-primary" href="/p/me/applets/private">Manage Applets</a>';}catch(error){message(form,error.message);}};
      }
    }
  }
  document.querySelector('#account_submenu_select')?.addEventListener('change',event=>location.assign(event.target.value));
  document.querySelector('#zendesk-widget-button')?.addEventListener('click',()=>location.assign('/hc/en-us'));
  async function init() {
    const serviceIntent=document.querySelector('[data-service-intent]');
    const needed=serviceIntent||currentPath==='/create'||currentPath==='/my_applets'||currentPath==='/my_services'||currentPath.startsWith('/p/me/applets')||currentPath.startsWith('/applets/local-')||currentPath.startsWith('/activity')||currentPath.split('/').length<=3;
    if(!needed)return;
    const loadingButtons=currentPath==='/create'?[...document.querySelectorAll('#diy-composer button')].map(button=>[button,button.disabled]):[];
    loadingButtons.forEach(([button])=>button.disabled=true);
    account=await get('/local/session');
    document.querySelectorAll('.connect-button').forEach(control=>{
      control.setAttribute('role','button');control.setAttribute('aria-label','Connect');control.tabIndex=0;
      control.onclick=()=>{
        if(!account.authenticated){location.assign('/login?return_to='+encodeURIComponent(currentPath));return;}
        if(currentPath.startsWith('/applets/'))location.assign('/create?published='+encodeURIComponent(currentPath));
        else connect(currentPath.split('/')[1],()=>location.reload());
      };control.onkeydown=event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();control.click();}};
    });
    if(currentPath.startsWith('/applets/')&&!currentPath.startsWith('/applets/local-')){
      document.querySelectorAll('main a, main button, .after-header-content a, .after-header-content button').forEach(control=>{
        if(control.textContent.trim()==='Connect')control.onclick=event=>{event.preventDefault();location.assign(account.authenticated?'/create?published='+encodeURIComponent(currentPath):'/login?return_to='+encodeURIComponent(currentPath));};
      });
    }
    if(!account.authenticated)return;
    const menu=document.querySelector('.account-menu-panel');if(menu){const text=document.createTreeWalker(menu,NodeFilter.SHOW_TEXT);let node;while(node=text.nextNode()){if(node.textContent.trim()==='[PRIVATE]')node.textContent=account.account.display_name;}}
    const loaded=await Promise.all([get('/local/automation'),get('/local/modules')]);state=loaded[0];modules=loaded[1].modules;serviceIcons=loaded[1].service_icons||{};
    if(serviceIntent){
      const service=serviceIntent.dataset.service;
      serviceIntent.querySelector('button').onclick=()=>{
        if(serviceIntent.dataset.serviceIntent==='connect'){connect(service,()=>location.assign('/my_services'));return;}
        const connected=state.connections.filter(item=>item.service===service&&item.connected);
        if(!connected.length){message(serviceIntent,'This service is already disconnected.');return;}
        const dialog=modal('Remove '+serviceName(service)+'?', '<p>Associated Applets will be archived and will stop running.</p><label>Account<select>'+connected.map(item=>'<option value="'+escape(item.account)+'">'+escape(item.label||item.account)+'</option>').join('')+'</select></label><button data-remove>Remove service</button>');
        dialog.querySelector('[data-remove]').onclick=async()=>{try{await act('disconnect',{service,account:dialog.querySelector('select').value});location.assign('/my_services');}catch(error){message(dialog,error.message);}};
      };
    }
    if(currentPath==='/create'||currentPath==='/p/me/applets/new'){await builder();loadingButtons.forEach(([button,disabled])=>{if(button.isConnected)button.disabled=disabled;});}
    if(currentPath==='/my_applets')cards();
    privateCards();details();activity();services();billing();await accountSettings();
  }
  init().catch(error=>{const main=document.querySelector('main');if(main)message(main,error.message);});
})();
