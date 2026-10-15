'use strict';
(()=>{
let catalog;
function offset(zone,date){
 const text=new Intl.DateTimeFormat('en',{timeZone:zone,timeZoneName:'longOffset'}).formatToParts(date).find(p=>p.type==='timeZoneName').value;
 const m=text.match(/GMT([+-])(\d{2}):(\d{2})/);
 return m?(m[1]==='-'?-1:1)*(Number(m[2])*60+Number(m[3])):0;
}
function offsetName(n){return 'GMT'+(n===0?'':(n>0?'+':'-')+Math.floor(Math.abs(n)/60)+(Math.abs(n)%60?':'+String(Math.abs(n)%60).padStart(2,'0'):''))}
async function localization(view,state){
 const C=window.TeamworkChat,{esc,api}=C;
 catalog??=await(await fetch('/static/chat-timezones.json')).json();
 const now=new Date(),zones=catalog.map(z=>({...z,offset:offset(z.referenceCode,now)})).sort((a,b)=>a.offset-b.offset||a.name.localeCompare(b.name,'en'));
 let saved={...state.settings},matches=zones,active=-1,busy=false;
 view.innerHTML=`<h1>Settings</h1><nav class=chat-tabs><a href="/workspace/chat/settings/profile">Profile</a><a href="/workspace/chat/settings/notifications">Notifications</a><a href="/workspace/chat/settings/preferences">Preferences</a><a href="/workspace/chat/settings/localization">Localization</a></nav><section class="s-settings-localization chat-localization"><h2>Localization</h2><label>Time format<select aria-label="Time format" data-chat-time-format><option>12hr</option><option>24hr</option></select></label><div class=chat-timezone-picker><label for=chat-timezone>Timezone</label><input id=chat-timezone role=combobox autocomplete=off aria-autocomplete=list aria-haspopup=listbox aria-expanded=false aria-controls=chat-timezones placeholder="Select option"><div id=chat-timezones role=listbox aria-label=Timezone hidden></div></div></section>`;
 const format=view.querySelector('[data-chat-time-format]'),input=view.querySelector('#chat-timezone'),list=view.querySelector('#chat-timezones');
 function restore(){format.value=saved.timeFormat;input.value=zones.find(z=>z.id===saved.timezoneId).name}
 function close(){list.hidden=true;input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');active=-1;restore()}
 function highlight(){for(const option of list.querySelectorAll('[role=option]'))option.classList.toggle('chat-option-active',Number(option.dataset.index)===active);if(active>=0){input.setAttribute('aria-activedescendant','chat-zone-'+matches[active].id);list.querySelector('#chat-zone-'+matches[active].id)?.scrollIntoView({block:'nearest'})}else input.removeAttribute('aria-activedescendant')}
 function draw(query=''){
  matches=zones.filter(z=>z.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));active=-1;
  let previous;
  list.innerHTML=matches.map((z,i)=>{const group=z.offset!==previous?`<div class=chat-timezone-offset>${esc(offsetName(z.offset))}</div>`:'';previous=z.offset;return group+`<div id="chat-zone-${z.id}" role=option aria-selected="${z.id===saved.timezoneId}" data-index="${i}">${esc(z.name)}</div>`}).join('')||'<p>No timezone found</p>';
  list.hidden=false;input.setAttribute('aria-expanded','true');highlight();
 }
 async function save(change){
  busy=true;format.disabled=true;input.disabled=true;C.status('');
  try{saved=await api('/settings','PATCH',change);state.settings=saved;state.timezone=zones.find(z=>z.id===saved.timezoneId).referenceCode;C.status('Saved.')}
  catch(e){C.status(e.message)}
  finally{busy=false;format.disabled=false;input.disabled=false;restore()}
 }
 async function choose(index){const zone=matches[index];if(!zone||busy)return;close();input.value=zone.name;await save({timezoneId:zone.id});input.focus({preventScroll:true});close()}
 format.addEventListener('change',()=>save({timeFormat:format.value}));
 input.addEventListener('click',()=>{if(!busy&&list.hidden){input.value='';draw()}});
 input.addEventListener('input',()=>draw(input.value));
 input.addEventListener('keydown',e=>{
  if(e.key==='Escape'){e.preventDefault();close();return}
  if(e.key==='Tab'){close();return}
  if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){
   e.preventDefault();if(list.hidden){input.value='';draw()}
   if(!matches.length)return;
   active=e.key==='Home'?0:e.key==='End'?matches.length-1:e.key==='ArrowDown'?Math.min(active+1,matches.length-1):Math.max(active-1,0);highlight();
  }else if(e.key==='Enter'){e.preventDefault();if(list.hidden){input.value='';draw()}else if(active>=0)choose(active)}
 });
 list.addEventListener('mousedown',e=>e.preventDefault());
 list.addEventListener('click',e=>{const item=e.target.closest('[role=option]');if(item)choose(Number(item.dataset.index))});
 input.addEventListener('blur',()=>{if(!busy)close()});
 restore();
}
window.ChatSettings={localization};
})();
