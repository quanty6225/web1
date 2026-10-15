'use strict';
(() => {
 let loading;
 let helpLinks;
 // The captured client's Home/End handlers pass a ResolvedPos object (or null)
 // to coordsAtPos, causing RangeError. Native browser line navigation already
 // gives the intended selection; keep the default action and skip that handler.
 document.addEventListener('keydown',event=>{if(['Home','End'].includes(event.key)&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&event.target.closest('docs-markdown-editor [contenteditable=true]'))event.stopImmediatePropagation()},true);
 document.addEventListener('click',event=>{
  const link=event.target.closest('docs-markdown-editor a[href],popover-modal a[href]');if(!link||(link.closest('[contenteditable=true]')&&!event.ctrlKey&&!event.metaKey))return;
  const url=new URL(link.href,location.href);if(url.origin===location.origin){if(url.pathname.startsWith('/help/')){event.preventDefault();event.stopImmediatePropagation();go(url.pathname+url.search+url.hash)}return;}
  event.preventDefault();event.stopImmediatePropagation();
  (helpLinks||=(fetch('/static/community-editor-links.json').then(r=>r.json()))).then(routes=>{if(routes[url.href])go(routes[url.href]);else modal(link.textContent||'导航目标','<code>'+esc(url.href)+'</code>',btn('复制地址','copy-target','data-target="'+esc(url.href)+'"','primary')+btn('关闭','close'))}).catch(showError);
 },true);
 const load=()=>loading||=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='/static/community-editor/markdown-editor.js';script.onload=resolve;script.onerror=()=>reject(Error('Editor could not be loaded'));document.head.append(script)});
 const target=form=>form.dataset.formType+(form.dataset.answerId?':'+form.dataset.answerId:'');
 const error=(form,message)=>{const box=form.querySelector('[data-form-error-container]');box.setAttribute('role','alert');box.textContent=message};
 const reveal=card=>{for(let node=card?.parentElement;node;node=node.parentElement)if(node.hidden&&node.id){const control=[...document.querySelectorAll('[aria-controls]')].find(e=>e.getAttribute('aria-controls')===node.id);if(control&&control.getAttribute('aria-expanded')!=='true')control.click()}};
 async function renderPosts(root,qid){
  root.querySelectorAll('[data-local-community-post]').forEach(e=>e.remove());const data=await api('/api/community/'+qid+'/posts');
  const total=root.querySelector('[data-comment-total]');if(total){total.dataset.sourceCommentTotal??=total.dataset.commentTotal;const count=Number(total.dataset.sourceCommentTotal)+data.posts.filter(p=>p.target!=='answer').length;total.dataset.commentTotal=count;total.textContent=count+' '+(count===1?'comment':'comments')}
  const hosts=new Map();
  for(const form of root.querySelectorAll('form[data-form-type]')){
   const posts=data.posts.filter(p=>p.target===target(form));if(form.dataset.formType==='answer'||!posts.length)continue;
   const auth=form.closest('.authenticated'),group=auth?.parentElement;if(!group)continue;
   const counter=[...group.querySelectorAll('span')].find(e=>/^\d+ comments?$/.test(e.textContent.trim()));if(!counter)continue;
   counter.dataset.sourceCount??=counter.textContent.trim().split(' ')[0];const count=Number(counter.dataset.sourceCount)+posts.length;counter.textContent=count+' '+(count===1?'comment':'comments');
   let control=group.querySelector('[data-bi-name=show-hide-comments]'),panel;
   if(control)panel=document.getElementById(control.getAttribute('aria-controls'));
   else{
    const previous=counter.parentElement;control=document.createElement('button');control.type='button';control.className='comment-expander button button-clear text-decoration-none inner-focus button-sm button-primary';control.dataset.biName='show-hide-comments';control.setAttribute('aria-expanded','false');
    const id='local-comments-'+qid+'-'+target(form).replace(':','-');control.setAttribute('aria-controls',id);control.append(...previous.childNodes);control.querySelector('.visually-hidden')?.remove();previous.replaceWith(control);
    panel=document.createElement('div');panel.id=id;panel.hidden=true;panel.className='width-full';panel.append(document.createElement('ol'));auth.before(panel);
   }
   if(panel)hosts.set(target(form),panel.querySelector('ol')||panel);
  }
  for(const post of data.posts){
   const form=[...root.querySelectorAll('form[data-form-type]')].find(f=>target(f)===post.target);if(!form)continue;
   const host=hosts.get(post.target),card=document.createElement(post.target==='answer'?'article':host?.tagName==='OL'?'li':'div');card.className='padding-sm border border-radius-lg margin-block-xs';card.dataset.localCommunityPost=post.id;card.id=post.id;
   const date=new Date(post.created*1000);card.innerHTML='<p><strong>'+esc(post.author)+'</strong> <time datetime="'+date.toISOString()+'">'+esc(date.toLocaleString('en-US'))+'</time></p><div class="content">'+post.html+'</div>';
   for(const link of card.querySelectorAll('a[href]')){const url=new URL(link.getAttribute('href'),location.href);if(url.origin!==location.origin)link.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();modal(link.textContent,'<code>'+esc(url.href)+'</code>',btn('复制地址','copy-target','data-target="'+esc(url.href)+'"','primary')+btn('关闭','close'))})}
   if(host)host.append(card);else (form.closest('.authenticated')||form).before(card);
  }
  for(const heading of root.querySelectorAll('h2,h3')){const match=heading.textContent.trim().match(/^(\d+) (additional )?answers?$/);if(match){heading.dataset.sourceAnswerCount??=match[1];const count=Number(heading.dataset.sourceAnswerCount)+data.posts.filter(p=>p.target==='answer').length;heading.textContent=count+' '+(match[2]||'')+(count===1?'answer':'answers')}}
  if(location.hash.startsWith('#newest-')){const requested=new URLSearchParams(location.search).get('comment'),kind=requested==='question'?'comment':requested?.startsWith('answer-')?'answerComment:'+requested.slice(7):null;const latest=data.posts.filter(p=>p.target===kind).at(-1);if(latest)reveal(document.getElementById(latest.id))}
  return data.posts;
 }
 window.initializeCommunityEditor=async(root,qid)=>{
  await renderPosts(root,qid);if(!S.account||!root.isConnected)return;
  const forms=[...root.querySelectorAll('form[data-form-type]')].filter(f=>f.querySelector('docs-markdown-editor'));if(!forms.length)return;
  const labels=await(await fetch('/static/community-draft-labels.json')).json();
  const key=form=>'onedrive-qna-draft:'+S.account.account_id+':'+qid+':'+target(form);
  for(const form of forms){const saved=localStorage.getItem(key(form));if(saved)form.querySelector('docs-markdown-editor').setAttribute('content',saved)}
  await load();await customElements.whenDefined('docs-markdown-editor');
  for(const form of forms){
   if(!root.isConnected)return;
   const editor=form.querySelector('docs-markdown-editor'),field=form.querySelector('textarea[name=body]'),discard=form.querySelector('[data-modal-type=qna-discard-draft]');
   for(let retry=0;!editor.editor&&retry<200;retry++)await new Promise(resolve=>setTimeout(resolve,50));
   if(!editor.editor)throw Error('Editor could not be loaded');
   const upload=async file=>{const body=new FormData();body.append('formFile',file);const result=await api('/api/attachments?platform=QnA','POST',body);return {url:result.path}};
   for(const options of [editor.options,editor.editor.options])for(const kind of ['imageUpload','fileUpload'])if(options?.[kind])options[kind].uploadHandler=upload;
   const saved=localStorage.getItem(key(form));if(saved){editor.editor.content=saved;editor.setAttribute('content',saved)}
   let lastSaved;const save=()=>{if(!editor.editor?.editorView)return;field.value=editor.editor.content;const body=field.value;if(body===lastSaved)return;lastSaved=body;if(body.trim())localStorage.setItem(key(form),body);else localStorage.removeItem(key(form));if(discard)discard.hidden=!body.trim()};save();
   const observer=new MutationObserver(save);observer.observe(editor,{attributes:true,attributeFilter:['content'],childList:true,subtree:true,characterData:true});
   editor.addEventListener('input',()=>queueMicrotask(save));
   if(discard)discard.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();modal(labels.discard_title,'<p>'+esc(labels.discard_description)+'</p>','<button class="primary" data-confirm-community-discard>'+esc(labels.ok)+'</button>'+btn(esc(labels.cancel),'close'));document.querySelector('[data-confirm-community-discard]').onclick=()=>{editor.editor.content='';editor.setAttribute('content','');save();closeOverlay()}});
   let requestId=crypto.randomUUID(),lastBody='';
   form.addEventListener('submit',async e=>{e.preventDefault();e.stopImmediatePropagation();save();const submit=form.querySelector('button[type=submit]');if(submit.disabled)return;submit.disabled=true;error(form,'');try{if(field.value!==lastBody){requestId=crypto.randomUUID();lastBody=field.value}const result=await api('/api/community/'+qid+'/posts','POST',{target:target(form),body:field.value,request_id:requestId});editor.editor.content='';editor.setAttribute('content','');save();history.replaceState({},'',location.pathname+(result.navigation||''));await renderPosts(root,qid);const card=document.getElementById(result.id);reveal(card);card?.scrollIntoView({block:'center'})}catch(err){error(form,err.message)}finally{submit.disabled=false}});
   form.dataset.localEditorReady='true';
  }
 };
})();
