/* Signed-in shell alarms; all resources and acknowledgement stay local. */
let alarmDelivery=null;
function startAlarmDelivery(){
 stopAlarmDelivery();
 if(!session?.authenticated)return;
 const state={owner:session.account.account_id,timers:new Map(),delivered:new Map(),firing:new Set(),busy:false,stopped:false};
 alarmDelivery=state;
 async function request(path,body){
  const response=await fetch(path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
  if(response.status===401){stopAlarmDelivery();return null}
  const data=await response.json();
  if(!response.ok){const error=Error(data.detail||'Unable to update this reminder.');error.status=response.status;throw error}
  return state.stopped?null:data;
 }
 function render(){
  if(state.stopped)return;
  const alarm=[...state.delivered.values()].sort((a,b)=>a.trigger_at-b.trigger_at||a.id.localeCompare(b.id))[0];
  let banner=document.querySelector('#alarm-banner');
  if(!alarm){banner?.remove();return}
  const host=[...document.querySelectorAll('dialog[open]')].at(-1)||document.body;
  if(!banner){banner=document.createElement('section');banner.id='alarm-banner';banner.setAttribute('role','region');banner.setAttribute('aria-live','polite');host.append(banner)}
  else if(banner.parentNode!==host)host.append(banner);
  const identity=JSON.stringify([alarm.id,alarm.title,alarm.start_at,alarm.location]);
  if(banner.dataset.identity===identity)return;
  banner.dataset.identity=identity;banner.setAttribute('aria-label',alarm.application==='calendar'?'Calendar reminder':'Reminders notification');
  const start=new Date(alarm.start_at),now=new Date(),tomorrow=new Date(now);tomorrow.setDate(tomorrow.getDate()+1);
  const day=start.toDateString()===now.toDateString()?'':start.toDateString()===tomorrow.toDateString()?' tomorrow':' on '+start.toLocaleDateString();
  const title=alarm.title.length>40?alarm.title.slice(0,40)+'…':alarm.title;
  banner.innerHTML=`<a class="alarm-open" href="${esc(alarm.path)}"><img src="/static/icons/${alarm.application}.png" alt=""><span><strong>${esc('“'+title+'”'+day+' at '+start.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'}))}</strong><small>${esc(alarm.location)}</small></span></a><div class="alarm-actions"><select data-alarm-minutes aria-label="Remind me again in"><option value="">Remind me again…</option><option value="5">5 minutes</option><option value="10">10 minutes</option><option value="15">15 minutes</option><option value="30">30 minutes</option><option value="60">60 minutes</option></select><button type="button" data-alarm-snooze disabled>Snooze</button><button type="button" data-alarm-dismiss>Dismiss</button></div><p role="alert" class="alarm-error" hidden></p>`;
  const snooze=banner.querySelector('[data-alarm-snooze]'),minutes=banner.querySelector('[data-alarm-minutes]');
  minutes.onchange=()=>snooze.disabled=!minutes.value;
  snooze.onclick=async()=>{
   snooze.disabled=true;const error=banner.querySelector('.alarm-error');error.hidden=true;
   try{const result=await request('/api/alarms/'+encodeURIComponent(alarm.id),{action:'snooze',minutes:+minutes.value});if(!result)return;state.delivered.delete(alarm.id);render();await refresh()}
   catch(failure){if([404,410].includes(failure.status)){state.delivered.delete(alarm.id);render()}else{error.textContent=failure.message;error.hidden=false;snooze.disabled=false}}
  };
  banner.querySelector('[data-alarm-dismiss]').onclick=async event=>{
   event.currentTarget.disabled=true;const error=banner.querySelector('.alarm-error');error.hidden=true;
   try{const result=await request('/api/alarms/'+encodeURIComponent(alarm.id),{action:'dismiss'});if(!result)return;state.delivered.delete(alarm.id);render();await refresh()}
   catch(failure){if([404,410].includes(failure.status)){state.delivered.delete(alarm.id);render()}else{error.textContent=failure.message;error.hidden=false;banner.querySelector('[data-alarm-dismiss]').disabled=false}}
  };
 }
 async function fire(alarm){
  state.timers.delete(alarm.id);if(state.stopped||state.firing.has(alarm.id))return;
  state.firing.add(alarm.id);
  try{const value=await request('/api/alarms/'+encodeURIComponent(alarm.id),{action:'deliver'});if(value){state.delivered.set(value.id,value);render()}}
  catch(error){if(![401,403,404,410].includes(error.status)&&!state.stopped)state.timers.set(alarm.id,{timer:setTimeout(()=>fire(alarm),error.status===409?250:1000),trigger:alarm.trigger_at});}
  finally{state.firing.delete(alarm.id)}
 }
 async function refresh(){
  if(state.busy||state.stopped)return;state.busy=true;
  try{
   const data=await request('/api/alarms');if(!data)return;
   if(data.owner!==state.owner){stopAlarmDelivery();return}
   const keys=new Set(data.alarms.map(a=>a.id));
   for(const [key,pending] of state.timers)if(!keys.has(key)&&pending.trigger>data.now+1000){clearTimeout(pending.timer);state.timers.delete(key)}
   for(const key of state.delivered.keys())if(!keys.has(key)&&!state.firing.has(key))state.delivered.delete(key);
   for(const alarm of data.alarms){
    if(alarm.state!=='delivered'){state.delivered.delete(alarm.id);const old=state.timers.get(alarm.id);if(old&&old.trigger!==alarm.trigger_at){clearTimeout(old.timer);state.timers.delete(alarm.id)}}
    if(alarm.state==='delivered'){state.delivered.set(alarm.id,alarm);continue}
    if(!state.timers.has(alarm.id)&&!state.firing.has(alarm.id)&&!state.delivered.has(alarm.id))state.timers.set(alarm.id,{timer:setTimeout(()=>fire(alarm),Math.max(1,alarm.trigger_at-data.now)),trigger:alarm.trigger_at});
   }
   render();
  }catch(error){/* A failed refresh retains known banners; action failures are shown inline. */}
  finally{state.busy=false}
 }
 state.observer=new MutationObserver(render);state.observer.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['open']});
 state.refresh=refresh;state.interval=setInterval(refresh,5000);refresh();
}
function stopAlarmDelivery(){
 const state=alarmDelivery;if(!state)return;state.stopped=true;
 clearInterval(state.interval);state.timers.forEach(pending=>clearTimeout(pending.timer));state.observer?.disconnect();
 document.querySelector('#alarm-banner')?.remove();alarmDelivery=null;
}
window.addEventListener('pagehide',stopAlarmDelivery);
window.addEventListener('pageshow',()=>{if(session?.authenticated&&!alarmDelivery)startAlarmDelivery()});
window.addEventListener('focus',()=>alarmDelivery?.refresh());
