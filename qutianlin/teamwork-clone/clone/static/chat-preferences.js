'use strict';
(()=>{
const fields=[['teamworkCardsPreview','Show Teamwork cards'],['attachedImagePreview','Show attached images preview'],['attachedFilePreview','Show attached files card'],['urlPreview','Show URL preview'],['showMovieQuotes','Show movie quotes in the message field']];
let quotes,cardsBusy=false;
async function render(view,state){
 const C=window.TeamworkChat,{esc,api}=C;let saved={...state.settings},pending={},timer,saving=false;
 view.innerHTML=`<h1>Settings</h1><nav class=chat-tabs><a href="/workspace/chat/settings/profile">Profile</a><a href="/workspace/chat/settings/notifications">Notifications</a><a href="/workspace/chat/settings/preferences">Preferences</a><a href="/workspace/chat/settings/localization">Localization</a></nav><section class=chat-preferences><h2>Message preview</h2>${fields.map(([key,label],i)=>(i===4?'<h2>Other</h2>':'')+`<label><input type=checkbox name="${key}" ${saved[key]==='always'?'checked':''}>${esc(label)}</label>`).join('')}</section>`;
 async function save(){
  if(saving)return;const current=C.getState();if(current.owner!==state.owner||current.actor!==state.actor)return;saving=true;const change=pending;pending={};
  try{saved=await api('/settings','PATCH',change);state.settings=saved;C.status('Saved.')}
  catch(e){C.status("Preferences couldn't be updated. "+e.message);for(const key of Object.keys(change))if(!(key in pending))view.querySelector(`[name="${key}"]`).checked=saved[key]==='always'}
  finally{saving=false;if(Object.keys(pending).length)timer=setTimeout(save,500)}
 }
 view.addEventListener('change',e=>{if(!fields.some(([k])=>k===e.target.name))return;pending[e.target.name]=e.target.checked?'always':'never';clearTimeout(timer);timer=setTimeout(save,500)});
}
async function enhance(){
 refreshCards();
 const C=window.TeamworkChat,state=C?.getState();if(!state)return;
 const form=document.querySelector('form[data-chat-form=message]');if(!form)return;
 quotes??=await(await fetch('/static/chat-movie-quotes.json')).json();if(!form.isConnected)return;
 const input=form.querySelector('[name=body]'),enabled=state.settings.showMovieQuotes==='always';
 if(!enabled){input.placeholder='Message goes here';form.dataset.quoteMode='never';return}
 if(form.dataset.quoteMode==='always')return;
 form.dataset.quoteMode='always';const date=new Date();
 input.placeholder=4*Math.random()>2.5?(date.getMonth()===4&&date.getDate()===4?quotes.may_fourth:quotes.quotes[Math.floor(Math.random()*quotes.quotes.length)]):'Message goes here';
}
async function refreshCards(){
 if(cardsBusy)return;const C=window.TeamworkChat,state=C?.getState();if(!state)return;
 const search=location.pathname.includes('/search')||location.pathname.includes('/highlights');cardsBusy=true;
 try{for(const host of document.querySelectorAll('[data-chat-cards]')){
  if(search){host.replaceChildren();delete host.dataset.markup;continue}
  const signature=JSON.stringify(state.settings),who=state.owner+':'+state.actor;
  if(host.dataset.settings===signature&&host.dataset.owner===who&&Date.now()-Number(host.dataset.checked||0)<4500)continue;
  if(state.settings.teamworkCardsPreview==='never'&&state.settings.urlPreview==='never'){host.replaceChildren();delete host.dataset.markup;continue}
  const result=await C.api('/messages/'+host.dataset.messageId+'/cards');if(!host.isConnected)continue;
  const latest=C.getState();if(latest.owner+':'+latest.actor!==who)return;
  host.dataset.settings=signature;host.dataset.owner=who;host.dataset.checked=Date.now();
  const cards=result.cards.filter(card=>card.kind==='teamwork'?latest.settings.teamworkCardsPreview!=='never':latest.settings.urlPreview!=='never'&&host.dataset.hasAttachment!=='true'&&host.dataset.isGif!=='true');
  const {esc}=C;const markup=cards.map(card=>{
   if(card.status==='no-access')return `<div class=chat-teamwork-card>You don't have access to this ${esc(card.type)}.</div>`;
   if(card.kind==='url')return `<aside class=chat-url-card><small>${esc(card.provider)}</small><h3><a href="${esc(card.url)}">${esc(card.title)}</a></h3><p>${esc(card.description)}</p>${card.image?`<img src="${esc(card.image)}" alt="">`:''}</aside>`;
   return `<aside class=chat-teamwork-card><h3 class="${card.completed?'chat-card-completed':''}"><a href="${esc(card.url)}">${esc(card.title)}</a></h3><p>${esc(card.subtitle)}</p>${card.fields?.length?`<details><summary>More details</summary><dl>${card.fields.map(([label,value,url])=>`<dt>${esc(label)}</dt><dd>${url?`<a href="${esc(url)}">${esc(value)}</a>`:esc(value)}</dd>`).join('')}</dl></details>`:''}${card.comments>0?`<p>${card.comments} comments</p>`:''}<footer>Teamwork</footer></aside>`
  }).join('');
  // Do not collapse an expanded card on an unchanged polling result.
  if(host.dataset.markup!==markup){host.innerHTML=markup;host.dataset.markup=markup}
 }}catch(e){for(const host of document.querySelectorAll('[data-chat-cards]')){host.replaceChildren();delete host.dataset.markup}}
 finally{cardsBusy=false}
}
document.addEventListener('chat-rendered',enhance);
window.ChatPreferences={render,enhance};
})();
