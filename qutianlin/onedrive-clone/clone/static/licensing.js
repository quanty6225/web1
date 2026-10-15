'use strict';
(() => {
  window.initializeLicensing = async root => {
    if(!root.querySelector('.document-filters'))return;
    const memberships=await(await fetch('/static/licensing-membership.json')).json();
    const cards=[...root.querySelectorAll('.resultDocument')],size=root.querySelector('.documents-page-size'),language=root.querySelector('#languages'),field=root.querySelector('#search-input');
    let matching=cards;
    const union=sets=>new Set(sets.flat()),intersect=(items,allowed)=>items.filter(item=>allowed.has(Number(item.dataset.sourcePosition)));
    function paging(){
      const limit=Number(size.value);cards.forEach(e=>e.hidden=true);matching.slice(0,limit).forEach(e=>e.hidden=false);
      const count=root.querySelector('.document-counts');count.replaceChildren(document.createTextNode('Showing Resources '+(matching.length?'1':'0')+' - '));const end=document.createElement('span');end.className='documentsTo';end.textContent=Math.min(limit,matching.length);count.append(end,document.createTextNode(' of '+matching.length));
    }
    function update(reset=true){
      matching=intersect(cards,new Set(memberships.language[language.value]||[]));
      const yearValues=[...root.querySelectorAll('.years input.valid-tag:checked')].map(e=>e.value);
      if(yearValues.length)matching=intersect(matching,union(yearValues.map(v=>memberships.year[v]||[])));
      for(const input of root.querySelectorAll('.tags input:checked'))matching=intersect(matching,new Set(memberships.tag[input.value]||[]));
      const term=field.value.trim().toLocaleLowerCase();if(term&&term!=='onedrive')matching=matching.filter(e=>e.textContent.toLocaleLowerCase().includes(term));
      if(reset){size.replaceChildren(...[['10','10'],['20','20'],[String(matching.length||1),'All']].map(([value,text])=>{const o=document.createElement('option');o.value=value;o.textContent=text;return o}));size.value='10'}
      const selected=root.querySelector('#selected-filters');selected.replaceChildren();
      root.querySelectorAll('.filter-list input.valid-tag:checked').forEach(input=>{const b=document.createElement('button');b.type='button';b.textContent=input.nextElementSibling.textContent;b.addEventListener('click',()=>{input.checked=false;update()});selected.append(b)});
      paging();
    }
    function tab(){for(const n of ['1','2'])root.querySelector('section > .tab'+n).hidden=!root.querySelector('#tab'+n).checked}
    root.addEventListener('change',event=>{
      const e=event.target;
      if(e===size){paging();return}
      if(e.matches('#tab1,#tab2')){tab();return}
      if(e.matches('.document-filters input[type=checkbox]')){
        const group=e.closest('.select-all');group.querySelectorAll(e.matches('.all-value')?'input.valid-tag':'input.all-value').forEach(i=>i.checked=false);update();
      }else if(e===language)update();
    });
    root.addEventListener('click',event=>{
      if(event.target.closest('.reset-filters-link')){event.preventDefault();go('/help/licensing-search?term='+encodeURIComponent(field.value));}
    });
    field.value=new URLSearchParams(location.search).get('term')||'OneDrive';update();tab();
  };
  function search(event){
    const trigger=event.target.closest?.('#banner-search-button,#search-button'),form=event.target.closest?.('#search-form');
    if(!trigger&&!(event.type==='submit'&&form))return;
    const root=event.target.closest('.help-article');if(!root)return;
    const input=root.querySelector('#search-input');if(!input)return;
    event.preventDefault();event.stopImmediatePropagation();if(input.value.trim())go('/help/licensing-search?term='+encodeURIComponent(input.value.trim()));else input.focus();
  }
  document.addEventListener('click',search,true);document.addEventListener('submit',search,true);
})();
