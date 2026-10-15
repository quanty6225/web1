'use strict';
(()=>{
const client=crypto.randomUUID();let sounds,cursor=null,generation=0,identity='',lastActivity=Date.now(),publishedActivity=0,busy=false,presenceBusy=false,player;
const C=()=>window.TeamworkChat;
const hostVisible=()=>!window.ChatEmbedded?.enabled||window.ChatEmbedded.visible();
const isActive=()=>hostVisible()&&!document.hidden&&document.hasFocus()&&Date.now()-lastActivity<240000;
function muteKey(){const s=C().getState();return 'teamwork-chat-sound:'+s.owner+':'+s.actor}
function muted(){try{return localStorage.getItem(muteKey())==='muted'}catch(e){return false}}
function activity(){if(document.hasFocus())lastActivity=Date.now()}
for(const event of ['pointerdown','pointermove','keydown','focus'])window.addEventListener(event,activity,{passive:true});
function currentChannel(){const match=location.pathname.match(/^\/workspace\/chat\/(?:channels|conversations)\/([^/]+)/);return match&&!['joined','discover'].includes(match[1])&&C()?.getState()?.channels.some(c=>c.id===match[1]&&c.joined)?match[1]:''}
async function presence(alive=true,beacon=false){
 if(!C()?.getState()||alive&&window.ChatEmbedded?.suspended())return;
 const active=hostVisible()&&!document.hidden&&document.hasFocus(),payload={client,focused:active,active:active&&lastActivity>publishedActivity,alive,channel:currentChannel()};
 if(beacon){navigator.sendBeacon('/api/chat/presence',new Blob([JSON.stringify(payload)],{type:'application/json'}));return}
 if(presenceBusy){if(!alive)setTimeout(()=>presence(false),100);return}presenceBusy=true;const activityAtSend=lastActivity;
 try{await C().api('/presence','POST',payload);if(payload.active)publishedActivity=activityAtSend}catch(e){}finally{presenceBusy=false}
}
async function play(sound){
 sounds??=await(await fetch('/static/chat-notification-sounds.json')).json();const choice=sounds.find(s=>s.id===sound);if(!choice)return;
 if(!player){player=new Audio();player.preload='auto'}if(player.getAttribute('src')!==choice.url)player.src=choice.url;player.currentTime=0;
 try{await player.play()}catch(e){if(e.name!=='NotAllowedError'&&e.name!=='AbortError')C().status('The notification sound could not be played.')}
}
async function notify(item,settings){
 if(C()?.getState()?.dnd)return;
 if(window.ChatEmbedded?.enabled&&!window.ChatEmbedded.notificationsEnabled())return;
 if(isActive()&&currentChannel()===item.channel)return;
 const state=C().getState(),key='teamwork-chat-alert:'+state.owner+':'+state.actor+':'+item.message,claim=client+':'+Date.now();
 try{if(localStorage.getItem(key)==='delivered')return;localStorage.setItem(key,claim)}catch(e){}
 await new Promise(resolve=>setTimeout(resolve,100));
 if(C()?.getState()?.dnd)return;
 if(window.ChatEmbedded?.enabled&&!window.ChatEmbedded.notificationsEnabled())return;
 try{if(localStorage.getItem(key)!==claim)return;localStorage.setItem(key,'delivered')}catch(e){}
 if('Notification' in window){
  try{if(Notification.permission==='default'&&!document.querySelector('dialog[open]'))await Notification.requestPermission();if(Notification.permission==='granted'){const alert=new Notification(item.title,{body:item.text,tag:item.channel+'-'+item.message,icon:'/static/chat-notification-icon.png',silent:true});alert.onclick=()=>{window.focus();location.assign(item.url);alert.close()}}}catch(e){}
 }
 if(!muted())await play(settings.notificationSound);
}
async function poll(){
 if(busy||!C()?.getState()||window.ChatEmbedded?.suspended())return;busy=true;const version=generation;
 try{const state=C().getState(),key=state.owner+':'+state.actor;if(identity!==key){identity=key;cursor=null}const result=await C().api('/notifications'+(cursor===null?'':'?after='+cursor));if(identity!==key||version!==generation)return;cursor=result.cursor;state.settings=result.settings;state.dnd=result.dnd;window.ChatStatus?.enhance();for(const item of result.notifications)await notify(item,result.settings)}catch(e){}finally{busy=false}
}
async function render(view,state){
 const {api,esc}=C();sounds??=await(await fetch('/static/chat-notification-sounds.json')).json();if(!view.isConnected)return;
 let saved={...state.settings};const handle=state.people.find(p=>p.id===state.actor)?.handle||'';
 const modes=[['all','All messages'],['mentions','@'+handle+', @all and @online mentions'],['directMentions','Only @'+handle+' mentions'],['none','No messages']];
 view.innerHTML=`<h1>Settings</h1><nav class=chat-tabs><a href="/workspace/chat/settings/profile">Profile</a><a href="/workspace/chat/settings/notifications">Notifications</a><a href="/workspace/chat/settings/preferences">Preferences</a><a href="/workspace/chat/settings/localization">Localization</a></nav><section class=chat-global-notifications><fieldset><legend>Global notifications</legend>${modes.map(([v,label])=>`<label><input type=radio name=defaultNotificationNoisiness value="${v}" ${saved.defaultNotificationNoisiness===v?'checked':''}>${esc(label)}</label>`).join('')}<button type=button data-channel-notifications>Set notifications for specific channels</button></fieldset><fieldset><legend>Notification settings</legend><label title="Disabling this will mute notifications"><input type=checkbox name=localSound ${muted()?'':'checked'}>Notification sounds</label><label title="Receive email notifications for messages when you're away or offline"><input type=checkbox name=emailNotifications ${saved.emailNotifications==='always'?'checked':''}>Email notifications</label><label title="You will not receive notifications for the conversation you are currently in"><input type=checkbox name=sendNotificationsWhenOnline ${saved.sendNotificationsWhenOnline==='always'?'checked':''}>Send email or push notifications when online</label></fieldset><label>Notification sound<select name=notificationSound aria-label="Notification sound">${sounds.map(s=>`<option value="${s.id}" ${saved.notificationSound===s.id?'selected':''}>${s.name}</option>`).join('')}</select></label></section>`;
 view.querySelector('[data-channel-notifications]').addEventListener('click',()=>channelDialog(state,modes).catch(e=>C().status(e.message)));
 view.addEventListener('change',async e=>{
  const input=e.target,key=input.name;if(!['defaultNotificationNoisiness','localSound','emailNotifications','sendNotificationsWhenOnline','notificationSound'].includes(key))return;
  if(key==='localSound'){try{localStorage.setItem(muteKey(),input.checked?'enabled':'muted');C().status('Saved.')}catch(e){input.checked=!input.checked;C().status('Browser storage is unavailable.')}return}
  const value=input.type==='checkbox'?(input.checked?'always':'never'):input.value;if(key==='notificationSound')play(value);
  const controls=view.querySelectorAll('input,select');controls.forEach(c=>c.disabled=true);C().status('');
  try{saved=await api('/settings','PATCH',{[key]:value});state.settings=saved;C().status('Saved.')}
  catch(e){if(input.type==='radio')view.querySelector(`input[name="${key}"][value="${saved[key]}"]`).checked=true;else if(input.type==='checkbox')input.checked=saved[key]==='always';else input.value=saved[key];C().status(e.message)}
  finally{controls.forEach(c=>c.disabled=false)}
 });
}
async function channelDialog(state,modes){
 const {api,esc,dialog}=C();let rows=await api('/notification-channels');
 const d=dialog('Channels notifications',`<div class=chat-notification-filters><input placeholder="Search channels" aria-label="Search channels" data-notification-search><label>Channel type<select aria-label="Channel type" data-notification-kind>${['all','public','private','project'].map(k=>`<option>${k}</option>`).join('')}</select></label><label><input type=checkbox data-notification-custom>Only channels with custom settings</label></div><div data-notification-rows></div>`),host=d.querySelector('[data-notification-rows]');
 function draw(){const q=d.querySelector('[data-notification-search]').value.toLowerCase(),kind=d.querySelector('[data-notification-kind]').value,custom=d.querySelector('[data-notification-custom]').checked;host.innerHTML=rows.filter(r=>r.name.toLowerCase().includes(q)&&(kind==='all'||r.kind===kind)&&(!custom||r.mode!=='global')).map(r=>`<fieldset data-notification-channel="${r.id}"><legend>${esc(r.name)}</legend><p>${esc(r.description)}</p><p data-current-mode>${r.mode==='global'?'Global':'Custom'}</p>${modes.map(([v,label])=>`<label><input type=radio name="channel-mode-${r.id}" value="${v}" ${(r.mode==='global'?state.settings.defaultNotificationNoisiness:r.mode)===v?'checked':''}>${esc(label)}</label>`).join('')}${r.mode!=='global'?'<button type=button data-notification-reset>Reset to Global</button>':''}</fieldset>`).join('')||'<p>No channels found.</p>'}
 d.querySelector('[data-notification-search]').addEventListener('input',draw);for(const input of d.querySelectorAll('[data-notification-kind],[data-notification-custom]'))input.addEventListener('change',draw);
 async function save(fieldset,value){const id=fieldset.dataset.notificationChannel,error=d.querySelector('[data-dialog-error]');fieldset.disabled=true;error.hidden=true;try{await api('/channels/'+id+'/notifications','PUT',{mode:value});rows.find(r=>r.id===id).mode=value;draw()}catch(e){error.hidden=false;error.textContent=e.message;draw()}finally{fieldset.disabled=false}}
 host.addEventListener('change',e=>{if(e.target.type==='radio')save(e.target.closest('fieldset'),e.target.value)});host.addEventListener('click',e=>{if(e.target.closest('[data-notification-reset]'))save(e.target.closest('fieldset'),'global')});draw();
}
document.addEventListener('chat-rendered',()=>{presence().then(poll)});
document.addEventListener('chat-host-visibility',()=>{presence(!window.ChatEmbedded?.suspended()).then(poll)});
let focusTimer;
for(const event of ['focus','blur','visibilitychange'])window.addEventListener(event,()=>{clearTimeout(focusTimer);focusTimer=setTimeout(()=>presence(),100)});
window.addEventListener('pagehide',()=>{clearTimeout(focusTimer);presence(false,true)});
setInterval(()=>presence(),15000);setInterval(poll,3000);
window.ChatNotifications={render,isActive,resetCursor:()=>{cursor=null;generation++}};
})();
