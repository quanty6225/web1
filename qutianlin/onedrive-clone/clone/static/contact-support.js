'use strict';
(() => {
  window.initializeContact = async root => {
    const states=await(await fetch('/static/contact-support.json')).json(),params=new URLSearchParams(location.search),query=params.get('query')||'',history=params.get('history')==='1';
    root.innerHTML=history?states.history:(states.queries[query]||states.initial);
    root.classList.add('contact-support');
    root.dataset.contactState=history?'history':query||'initial';
    const search=root.querySelector('#search-box-description-id'),getHelp=root.querySelector('#getHelp');
    let suggest;
    function closeSuggestions(){suggest?.remove();suggest=null;if(search){search.setAttribute('aria-expanded','false');search.removeAttribute('aria-controls')}}
    function suggestions(){
      closeSuggestions();if(!search||search.value.trim().toLowerCase()!=='onedrive')return;
      suggest=document.createElement('ul');suggest.id='contact-suggestions';suggest.setAttribute('role','listbox');suggest.setAttribute('aria-label','Search Suggestions');suggest.className='contact-suggestions';
      states.suggestions.forEach((item,index)=>{const li=document.createElement('li');li.setAttribute('role','option');li.tabIndex=-1;li.setAttribute('aria-label',item.label);li.setAttribute('aria-posinset',index+1);li.setAttribute('aria-setsize',5);li.innerHTML=item.html;li.addEventListener('mousedown',e=>{e.preventDefault();submit(item.label)});li.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();submit(item.label)}else if(e.key==='Escape'){e.preventDefault();closeSuggestions();search.focus()}else if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();const next=(index+(e.key==='ArrowDown'?1:-1)+5)%5;suggest.children[next].focus()}});suggest.append(li)});
      search.parentElement.append(suggest);search.setAttribute('aria-expanded','true');search.setAttribute('aria-controls',suggest.id);
    }
    function sync(){
      if(!search)return;const remaining=80-search.value.length,counter=root.querySelector('#issueDescRemainChar');if(counter)counter.textContent=remaining+' characters remaining';search.setAttribute('aria-label',remaining+' characters remaining, Search., Auto suggest list is hidden');getHelp.disabled=!search.value.trim();getHelp.setAttribute('aria-disabled',String(getHelp.disabled));
    }
    function submit(value){
      const text=value.trim();if(!text)return;
      const canonical=Object.keys(states.queries).find(q=>q.toLocaleLowerCase()===text.toLocaleLowerCase());
      if(canonical)go('/help/contact?query='+encodeURIComponent(canonical));
      else{
        let status=root.querySelector('[data-contact-unavailable]');if(!status){status=document.createElement('p');status.dataset.contactUnavailable='';status.setAttribute('role','status');getHelp.parentElement.append(status)}
        status.textContent='此查询的原站结果尚未完成取证。';
      }
    }
    if(search){search.value=query;search.addEventListener('input',()=>{sync();suggestions()});search.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();submit(search.value)}else if(e.key==='ArrowDown'&&suggest){e.preventDefault();suggest.firstElementChild.focus()}else if(e.key==='Escape'){search.value='';closeSuggestions();sync()}});search.addEventListener('blur',()=>setTimeout(()=>{if(suggest&&!suggest.contains(document.activeElement))closeSuggestions()},0));sync()}
    root.addEventListener('click',event=>{
      const tab=event.target.closest('[data-contact-tab]');if(tab){event.preventDefault();event.stopPropagation();go('/help/contact'+(tab.dataset.contactTab==='history'?'?history=1':''));return}
      const button=event.target.closest('button');if(!button)return;
      if(button===getHelp){event.preventDefault();submit(search.value)}
      else if(button.hasAttribute('data-contact-query'))submit(button.dataset.contactQuery);
      else if(button.dataset.automationId==='FT-SignIn-BTn'||button.textContent.trim()==='Sign In')go('/login?next='+encodeURIComponent('/help/contact?history=1'));
      else if(button.getAttribute('aria-label')==='Close')button.closest('[role=region]')?.remove();
      else if(button.getAttribute('aria-label')==='Clear text'||button.title==='Clear'){search.value='';closeSuggestions();sync();search.focus()}
      else if(button.textContent.includes('Back'))go('/help/contact');
    });
    root.addEventListener('keydown',event=>{
      const tab=event.target.closest('[data-contact-tab]');if(!tab)return;
      if(['ArrowLeft','ArrowRight','Home','End','Enter',' '].includes(event.key)){
        event.preventDefault();let dest=tab.dataset.contactTab;
        if(event.key==='Home')dest='search';else if(event.key==='End')dest='history';else if(event.key.startsWith('Arrow'))dest=dest==='history'?'search':'history';
        go('/help/contact'+(dest==='history'?'?history=1':''));
      }
    });
    if(history&&S.account){const p=document.createElement('p');p.setAttribute('role','status');p.textContent='已登录；原站服务请求记录需额外认证，尚未取得有效证据。';root.append(p)}
  };
})();
