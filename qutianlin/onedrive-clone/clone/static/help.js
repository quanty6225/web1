'use strict';
(() => {
  const tabsIn = tab => [...(tab.closest('[role="tablist"]') || tab.parentElement.parentElement).querySelectorAll('[role="tab"]')];
  const targets = control => {
    const elements=(control.getAttribute('aria-controls') || '').split(/\s+/).filter(Boolean).map(id => document.getElementById(id)).filter(Boolean);
    if(elements.length)return elements;
    const selector=control.getAttribute('data-target')||control.getAttribute('data-bs-target')||'';
    const fallback=selector.startsWith('#')&&document.getElementById(selector.slice(1));
    return fallback?[fallback]:[];
  };
  const showPanel=(panel,visible)=>{panel.hidden=!visible;if(panel.hasAttribute('aria-hidden'))panel.setAttribute('aria-hidden',String(!visible))};
  const bulkGroup=control=>control.closest('.accordion-component')||control.closest('.help-article');
  const disclosures=root=>[...root.querySelectorAll('button[aria-expanded][aria-controls]')].filter(control=>targets(control).length);
  function setSummary(group,expanded){
    for(const [selector,visible] of [['.summary-content',!expanded],['.detail-content',expanded],['.expand-btn',!expanded],['.collapse-btn',expanded]]){
      const element=group.querySelector(selector);if(element){element.classList.remove('hidden');showPanel(element,visible)}
    }
    group.querySelector('.expand-btn')?.setAttribute('aria-expanded',String(expanded));group.querySelector('.collapse-btn')?.setAttribute('aria-expanded',String(!expanded));
  }
  function syncBulk(root){
    for(const control of root.querySelectorAll('.expandall,button[data-action=expand],button[data-action=collapse]')){
      const group=bulkGroup(control),items=control.matches('.expandall')?[...group.querySelectorAll('.expand-collapse-content .expand-btn')]:disclosures(group),all=items.length>0&&items.every(item=>item.getAttribute('aria-expanded')==='true'),none=items.every(item=>item.getAttribute('aria-expanded')!=='true');
      if(control.matches('.expandall')){control.setAttribute('aria-expanded',String(all));const expand=control.querySelector('.expanded-label'),collapse=control.querySelector('.collapsed-label');if(expand)expand.hidden=all;if(collapse){collapse.classList.remove('hidden');collapse.hidden=!all}}
      else{const inactive=control.dataset.action==='expand'?all:none;control.disabled=inactive;control.setAttribute('aria-disabled',String(inactive));control.setAttribute('aria-pressed',String(inactive));control.tabIndex=inactive?-1:0}
    }
  }
  function select(tab, focus = true) {
    if(tab.hasAttribute('data-inner-tab-target')){
      const mode=tab.getAttribute('data-inner-tab-target').slice(1),group=tab.closest('.buy-now-v2');
      if(group&&['yearly','monthly'].includes(mode)){
        for(const item of tabsIn(tab)){const active=item===tab;item.setAttribute('aria-selected',String(active));item.tabIndex=active?0:-1;item.classList.toggle('active',active)}
        for(const item of group.querySelectorAll('[data-local-'+mode+'-style]'))item.style.cssText=item.getAttribute('data-local-'+mode+'-style');
        if(focus)tab.focus();return;
      }
    }
    for (const item of tabsIn(tab)) {
      const active = item === tab;
      item.setAttribute('aria-selected', String(active));
      item.tabIndex = active ? 0 : -1;
      item.classList.toggle('active', active);
      for (const panel of targets(item)) showPanel(panel,active);
    }
    if (focus && tab.dataset.tab && tab.closest('.learn-document')) {
      const url = new URL(location.href);
      url.searchParams.set('tabs', tab.dataset.tab);
      history.replaceState(history.state, '', url);
    }
    if (focus) tab.focus();
  }
  window.selectHelpTab = select;
  window.initializeHelp = root => {
    if (!root) return;
    window.initializeLearnDocument?.(root).catch(showError);
    if(location.pathname==='/help/contact'){window.initializeContact(root).catch(showError);return}
    window.initializeCommunity?.(root).catch(showError);
    window.initializeLicensing?.(root).catch(showError);
    const licenseTable=root.querySelector('#documentTable');
    if(licenseTable){
      const query=new URLSearchParams(location.search);
      for(const [id,param] of [['timeframe-select','year'],['language-select','lang'],['assetType-select','type']]){
        const select=root.querySelector('#'+id),value=query.get(param)||'0';
        if(select)select.value=[...select.options].some(o=>o.value===value)?value:'0';
      }
      const year=root.querySelector('#timeframe-select')?.value||'0',language=root.querySelector('#language-select');
      const label=language?.value!=='0'?language?.selectedOptions[0]?.textContent.trim():null;
      for(const row of licenseTable.querySelectorAll('.documentBody .link-list__tr')){
        row.hidden=(year!=='0'&&row.querySelector('.link-list__td--year')?.textContent.trim()!==year)||Boolean(label&&row.querySelector('.link-list__td--lang')?.textContent.trim()!==label);
      }
    }
    for(const group of root.querySelectorAll('.expand-collapse-content')){
      const detail=group.querySelector('.detail-content');setSummary(group,detail?!detail.classList.contains('hidden')&&!detail.hidden:group.querySelector('.expand-btn')?.getAttribute('aria-expanded')==='true');
    }
    for (const group of root.querySelectorAll('[role="tablist"]')) {
      const tabs = [...group.querySelectorAll('[role="tab"]')];
      const selected = tabs.find(t => t.getAttribute('aria-selected') === 'true') || tabs[0];
      if (selected) select(selected, false);
    }
    for (const control of root.querySelectorAll('[aria-expanded][aria-controls]')) {
      for (const panel of targets(control)) showPanel(panel,control.getAttribute('aria-expanded') === 'true');
    }
    syncBulk(root);
    let id = '';
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    const destination = id && document.getElementById(id);
    if (destination && root.contains(destination)) {
      const summaryGroup=destination.closest('.expand-collapse-content');if(summaryGroup){setSummary(summaryGroup,true);syncBulk(root)}
      for (const tab of root.querySelectorAll('[role="tab"][aria-controls]')) {
        if (targets(tab).some(panel => panel === destination || panel.contains(destination))) select(tab, false);
      }
      for (const control of root.querySelectorAll('[aria-expanded][aria-controls]')) {
        if (targets(control).some(panel => panel === destination || panel.contains(destination))) {
          control.setAttribute('aria-expanded', 'true');
          for (const panel of targets(control)) showPanel(panel,true);
        }
      }
      destination.scrollIntoView({block:'start'});
    }
  };
  document.addEventListener('change',event=>{
    const select=event.target.closest('.help-article #timeframe-select,.help-article #language-select,.help-article #assetType-select');
    if(!select||!select.closest('.help-article').querySelector('#documentTable'))return;
    const params=new URLSearchParams(location.search),key={'timeframe-select':'year','language-select':'lang','assetType-select':'type'}[select.id];
    if(select.value==='0')params.delete(key);else params.set(key,select.value);
    go(location.pathname+(params.size?'?'+params:'')+location.hash);
  });
  document.addEventListener('click', event => {
    if(event.target.closest('.contact-support,docs-markdown-editor,popover-modal'))return;
    const control = event.target.closest('.help-article a, .help-article button, .help-article [role="button"], .help-article [role="tab"], .help-article [aria-controls]');
    if (!control) return;
    let handled = false;
    if(control.matches('a.modal-trigger[data-target^="#"]')&&control.closest('.buy-now-v2')?.querySelector('[data-local-yearly-style]')){
      const id=control.getAttribute('data-target').slice(1);
      fetch('/static/purchase-dialogs.json').then(response=>response.json()).then(states=>{
        const state=states[id];if(!state)throw Error('此购买窗口尚未取得有效原站证据。');
        modal(state.title,`<p>${esc(state.description)}</p>${state.selection_html}`,`<button class="secondary" data-action="close" aria-label="${esc(state.cancel_aria)}">${esc(state.cancel_label)}</button><a class="primary" href="${esc(state.continue_route)}" aria-label="${esc(state.continue_aria)}">${esc(state.continue_label)}</a>`);
        document.querySelector('.modal .close').setAttribute('aria-label',state.close_aria);
      }).catch(showError);
      handled=true;
    } else if(control.matches('.open-print-view')){
      window.print();handled=true;
    } else if(control.matches('.expandall,button[data-action=expand],button[data-action=collapse]')){
      const expanded=control.matches('.expandall')?control.getAttribute('aria-expanded')!=='true':control.dataset.action==='expand';
      if(control.matches('.expandall')){for(const group of bulkGroup(control).querySelectorAll('.expand-collapse-content'))setSummary(group,expanded)}
      else for(const item of disclosures(bulkGroup(control))){item.setAttribute('aria-expanded',String(expanded));for(const panel of targets(item))showPanel(panel,expanded)}
      syncBulk(control.closest('.help-article'));handled=true;
    } else if(control.matches('.expand-btn,.collapse-btn')&&control.closest('.expand-collapse-content')){
      setSummary(control.closest('.expand-collapse-content'),control.matches('.expand-btn'));syncBulk(control.closest('.help-article'));handled=true;
    } else if (control.matches('button[aria-label^="Enlarge Image"]') && control.querySelector('img')) {
      const image=control.querySelector('img');
      modal(image.alt||'Image',`<img src="${esc(image.src)}" alt="${esc(image.alt)}" style="width:100%;height:auto">`);
      handled=true;
    } else if (control.matches('[role="tab"]')) {
      select(control); handled = true;
    } else if (control.hasAttribute('aria-expanded') && targets(control).length) {
      const expanded = control.getAttribute('aria-expanded') !== 'true';
      control.setAttribute('aria-expanded', String(expanded));
      if(control.dataset.biName==='show-hide-comments'){
        const label=expanded?control.dataset.expandedTitle:control.dataset.title;
        if(label){control.title=label;const text=control.querySelector('.show-more-text');if(text)text.textContent=label}
      }
      for (const panel of targets(control)) showPanel(panel,expanded);
      syncBulk(control.closest('.help-article'));
      handled = true;
    } else if (/close.*banner|关闭通知横幅/i.test(control.getAttribute('aria-label') || '')) {
      const banner = control.parentElement.closest('[class*="banner" i],[id*="banner" i],[role="alert"]');
      if (banner) { banner.remove(); handled = true; }
    } else if (control.matches('.close,[aria-label="Close dialog"]')) {
      const panel = control.closest('[role="dialog"],.popover,.modal');
      if (panel) {
        panel.hidden = true;
        for (const toggle of document.querySelectorAll('[aria-controls]')) if (targets(toggle).includes(panel)) toggle.setAttribute('aria-expanded','false');
        handled = true;
      }
    }
    if (handled) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
  document.addEventListener('keydown', event => {
    if(event.target.closest('.contact-support,docs-markdown-editor,popover-modal'))return;
    const button=event.target.closest('.help-article [role="button"]');
    if(button&&!button.matches('button')&&['Enter',' '].includes(event.key)){event.preventDefault();button.click();return}
    const tab = event.target.closest('.help-article [role="tab"]');
    if (!tab || !['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    const tabs = tabsIn(tab), index = tabs.indexOf(tab);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    event.preventDefault(); select(tabs[next]);
  });
})();
