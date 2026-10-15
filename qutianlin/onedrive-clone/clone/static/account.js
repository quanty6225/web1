'use strict';
(() => {
 const sections=[['帐户','/account'],['您的信息','/account/profile'],['订阅','/account/services'],['安全','/account/security'],['隐私','/account/privacy'],['付款选项','/account/payments'],['订单历史记录','/account/orders']];
 const categoryOptions=[['all','所有类别'],['processing','处理中'],['refunded','已退货/已退款'],['digital','数字'],['physical','物理']];
 const periodOptions=[[3,'过去 3 个月'],[6,'过去 6 个月'],[12,'过去 12 个月'],[84,'过去 7 年']];
 let catalog,profile;
 function style(){for(const name of ['account-source','account'])if(!document.querySelector('link[data-account-style="'+name+'"]')){const link=document.createElement('link');link.rel='stylesheet';link.href='/static/'+name+'.css';link.dataset.accountStyle=name;document.head.append(link)}}
 const consent=()=>localStorage.getItem('onedrive-cookie-choice')?'':`<aside class="account-consent"><p>我们使用可选的 Cookie，通过社交媒体连接等方式改善你在我们网站上的体验，并且根据你的在线活动投放个性化的广告。 如果你拒绝可选 Cookie，则我们将仅使用为你提供服务所必须的 Cookie。 你可以单击页面底部的“管理 Cookie”更改你的选择。${link('隐私声明','/privacy')}</p>${btn('接受','account-cookie','data-choice="all"')}${btn('拒绝','account-cookie','data-choice="essential"')}${btn('管理 Cookie','account-cookie-manage')}</aside>`;
 function frame(body){return `<div class="account-layout">${consent()}<header class="account-header">${authLogo()}<strong>Microsoft 帐户</strong><span class="spacer"></span>${link('OneDrive','/my')}${btn(esc(S.account.display_name),'account-menu','aria-label="帐户管理器"')}</header><div class="account-columns"><nav class="account-nav" aria-label="Microsoft 帐户">${sections.map(([t,p])=>link(t,p,p===location.pathname?'active':'')).join('')}</nav><div class="account-content">${body}</div></div><footer class="account-footer">${link('隐私与 Cookie','/privacy')}${link('使用条款','/terms')}${link('联系我们','/help')}${btn('反馈','feedback','','link')}${btn('管理 Cookie','account-cookie-manage','','link')}<span>© Microsoft 2026</span></footer></div>`}
 window.renderAccountPage=async()=>{
  style();catalog||=await(await fetch('/static/account-pages.json')).json();profile=await api('/api/account/profile');const path=location.pathname,doc=catalog[path];
  if(!doc){$('#app').innerHTML=frame(`<main class="account-unavailable"><h1>${esc(sections.find(s=>s[1]===path)?.[0]||'Microsoft 帐户')}</h1><p>此关联流程尚未取得完整原站证据。</p>${link('返回帐户','/account')}</main>`);return}
  $('#app').innerHTML=frame(`<div class="account-source" data-account-page="${esc(path)}"><div class="account-provider ${esc(doc.provider_classes.join(' '))}">${doc.html}</div></div>`);
  if(!profile.source_snapshot){
   if(path==='/account/services')for(const button of $$('.account-source [data-control*=perpetual-install]')){let container=button;while(container.parentElement&&!container.textContent.includes('Office 家庭和学生版 2021'))container=container.parentElement;if(container.tagName!=='MAIN')container.remove()}
   if(path==='/account')for(const control of $$('.account-source [aria-controls][aria-labelledby]')){const label=document.getElementById(control.getAttribute('aria-labelledby')),panel=document.getElementById(control.getAttribute('aria-controls'));if(panel&&/设备|付款选项/.test(label?.textContent||'')){panel.replaceChildren();const message=document.createElement('p');message.textContent=label.textContent.includes('设备')?'我们看不到任何设备':'付款选项';panel.append(message)}}
  }
  $$('[data-account-value]').forEach(el=>el.textContent=el.dataset.accountValue==='email'?profile.email_normalized:profile[el.dataset.accountValue]||'');
  window.decorateAccountPhoto(profile);
  if(path==='/account/profile')await window.refreshAccountLanguageSummary();
  if(!profile.source_snapshot)$$('[data-account-country]').forEach(el=>el.textContent=profile.country||'');
  if(path==='/account'){
   const storage=await api('/api/storage'),used=storage.used===0?'0 GB':storage.used<.1*1024**3?'< 0.1 GB':(storage.used/1024**3).toFixed(1)+' GB';
   for(const el of $$('[data-account-storage]'))switch(el.dataset.accountStorage){
    case 'total':el.textContent=used+' / '+(storage.quota/1024**3)+' GB';break;
    case 'percentage':el.textContent='已用 '+storage.percentage+'%';break;
    case 'drive-value':el.textContent=used;break;
    case 'drive':el.setAttribute('aria-label','打开 OneDrive, 已使用 '+used);break;
    case 'bar':el.style.width=Math.min(100,storage.used/storage.quota*100)+'%';break;
   }
  }
  for(const control of $$('.account-source [aria-expanded][aria-controls]')){const panel=document.getElementById(control.getAttribute('aria-controls'));if(panel)panel.hidden=control.getAttribute('aria-expanded')!=='true'}
  if(path==='/account/orders'){
   const params=new URLSearchParams(location.search),category=params.get('category')||'all',period=Number(params.get('period')||3);
   for(const [id,name,options,selected] of [['filter-dropdown-OrderType','category',categoryOptions,category],['filter-dropdown-OrderRange','period',periodOptions,period]]){
    const previous=document.getElementById(id);if(!previous)continue;const select=document.createElement('select');select.id=id;select.dataset.orderFilter=name;select.setAttribute('aria-label',name==='category'?'查看':'订购时段');select.innerHTML=options.map(([v,t])=>`<option value="${v}" ${String(v)===String(selected)?'selected':''}>${t}</option>`).join('');previous.replaceWith(select)
   }
   await refreshOrders();
  }
 };
 async function refreshOrders(){const cat=$('[data-order-filter=category]')?.value||'all',period=$('[data-order-filter=period]')?.value||'3';const data=await api('/api/account/orders?'+new URLSearchParams({category:cat,period}));let results=$('#account-order-results');if(!results){results=document.createElement('div');results.id='account-order-results';$('.account-source main').append(results)}results.innerHTML=data.orders.map(r=>r.html||`<article><h2>${esc(r.plan)}</h2><p>订单号 ${esc(r.id)}</p><p>${esc(r.status)}</p></article>`).join('');const sourceEmpty=$('[data-order-empty]');if(sourceEmpty)sourceEmpty.hidden=data.orders.length>0;const empty=$('#order-history-wrapper');if(empty){const walker=document.createTreeWalker(empty,NodeFilter.SHOW_TEXT);let node;while(node=walker.nextNode()){if(/过去 [0-9]+ (个月|年)内/.test(node.nodeValue))node.nodeValue=node.nodeValue.replace(/过去 [0-9]+ (个月|年)内/,period==='84'?'过去 7 年内':`过去 ${period} 个月内`)}}}
 window.accountControl=async el=>{
  const id=el.dataset.control||'',text=el.textContent.trim();
  if(el.hasAttribute('aria-expanded')&&el.hasAttribute('aria-controls')){const target=document.getElementById(el.getAttribute('aria-controls'));if(target){const expanded=el.getAttribute('aria-expanded')!=='true';el.setAttribute('aria-expanded',String(expanded));target.hidden=!expanded;return}}
  if(id==='profile.profile-page.personal-section.edit-name'){modal('编辑名称',`<form id="account-name-form"><label for="account-last-name">姓氏</label><input id="account-last-name" name="last_name" value="${esc(profile.last_name)}" autocomplete="family-name"><label for="account-first-name">名字</label><input id="account-first-name" name="first_name" value="${esc(profile.first_name)}" autocomplete="given-name"><footer><button class="primary" type="submit">保存</button>${btn('取消','close','','secondary')}</footer></form>`);return}
  if(/m365|subscriptions.cold|storage-link/.test(id)||id==='orders-start-shopping'){go('/plans');return}
  if(id.includes('quota-bar.OneDrive')){go('/settings/storage');return}
  if(id.includes('quota-bar.Outlook')){go('/boundary/account-outlook');return}
  if(id==='home.drawers.privacy.privacy-dashboard'){go('/account/privacy');return}
  if(id==='home.drawers.payment-options.manage-payment'){go('/account/payments');return}
  if(id==='home.drawers.security.change-password'){go('/recover');return}
  if(id.startsWith('home.drawers.security.')){go('/account/security');return}
  if(id.includes('language')||id.includes('regional-formats')){await window.openAccountLanguage(id.includes('regional-formats')?'region':'language');return}
  if(id.includes('secondary-profile-info')){go('/account/security');return}
  if(id.includes('xbox')){go('/boundary/account-xbox');return}
  if(id.includes('perpetual-install')){go('/boundary/account-office-install');return}
  if(id.includes('edit-picture')){await window.openAccountPhoto(profile);return}
  modal(text||'Microsoft 帐户','<p>此控件的后续原站流程尚未完成取证。</p>',btn('关闭','close','','primary'));
 };
 window.accountCookieAction=async(action,el)=>{if(action==='account-cookie'){localStorage.setItem('onedrive-cookie-choice',el.dataset.choice);localStorage.removeItem('onedrive-cookie-categories');$('.account-consent')?.remove();closeOverlay()}else await window.showAccountCookiePreferences()};
 document.addEventListener('change',async e=>{if(!e.target.matches('[data-order-filter]'))return;const query=new URLSearchParams({category:$('[data-order-filter=category]').value,period:$('[data-order-filter=period]').value});history.replaceState({},'',location.pathname+'?'+query);try{await refreshOrders()}catch(err){showError(err)}});
 document.addEventListener('submit',async e=>{if(e.target.id!=='account-name-form')return;e.preventDefault();e.stopImmediatePropagation();try{profile=await api('/api/account/name','POST',Object.fromEntries(new FormData(e.target)));closeOverlay();await refreshSession();await window.renderAccountPage()}catch(err){const form=e.target;let box=$('.error',form);if(!box){box=document.createElement('p');box.className='error';box.setAttribute('role','alert');form.prepend(box)}box.textContent=err.message}},true);
 document.addEventListener('keydown',e=>{const target=e.target.closest('.account-source [role=button],.account-source [role=listitem][data-action=account-control][tabindex="0"]');if(target&&['Enter',' '].includes(e.key)){e.preventDefault();target.click()}});
})();
