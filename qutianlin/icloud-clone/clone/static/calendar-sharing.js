let calendarShareContext=null,calendarInboxState={invitations:[],messages:[]},calendarPoll=null,calendarDragActive=false,calendarMovePending=false;
const calendarHidden=new Set();
function writableCalendars(){return (appData.calendars||[]).filter(c=>!c._sharing||c._sharing.permission==='write')}
function startCalendarPoll(){
 clearInterval(calendarPoll);let busy=false;
 calendarPoll=setInterval(async()=>{
  if(busy||modal.open||calendarDragActive||calendarMovePending||!/^\/calendar\/(?:day\/|month\/)?$/.test(location.pathname)||document.activeElement?.matches('input,textarea,select'))return;
  busy=true;
  try{
   const [calendars,events,inbox,preferences,timeSettings]=await Promise.all([api('/api/items/calendars'),api('/api/items/events'),api('/api/calendar-inbox'),api('/api/calendar-preferences'),api('/api/calendar-time-settings?include_zones=false')]);
   if(!modal.open&&!calendarDragActive&&!calendarMovePending&&(timeSettings.timezone!==calendarTimeSettings.timezone||JSON.stringify([calendars.items,events.items,inbox,preferences])!==JSON.stringify([appData.calendars,appData.events,calendarInboxState,calendarPreferences])))await calendarPage();
  }catch(error){clearInterval(calendarPoll)}finally{busy=false}
 },2000);
}
window.addEventListener('pagehide',()=>clearInterval(calendarPoll));
async function calendarSharing(calendar){
 const data=calendar._sharing?await api('/api/calendar-shares/'+calendar._sharing.id):{owner:true,participants:[],revision:null,public_path:null};
 calendarShareContext={calendar,data,participants:structuredClone(data.participants||[])};
 if(!data.owner){
  showDialog(calendar.name,'<h3>Sharing With</h3><div class="calendar-people">'+data.participants.map(p=>`<p>${esc(p.email)} · ${p.permission==='write'?'Allow editing':'Read-Only'} · ${esc(p.status)}</p>`).join('')+'</div><button data-calendar-share="leave">Unsubscribe</button><button data-action="close">Done</button>');return;
 }
 showDialog('Calendar Sharing',`<h3>${esc(calendar.name)}</h3><form id="calendar-sharing-form"><h4>Sharing With</h4><div id="calendar-people"></div><label>Email address<input name="invitee" type="text" aria-label="Email address" placeholder="Email addresses"></label><button type="button" data-calendar-share="add">Add Person</button><label class="calendar-toggle"><input type="checkbox" name="public" ${data.public_path?'checked':''}>Public Calendar</label>${data.public_path?`<label>Calendar URL<input aria-label="Calendar URL" readonly value="${esc(location.origin+data.public_path)}"></label><button type="button" data-calendar-share="copy">Copy</button><button type="button" data-calendar-share="email">Email</button>`:''}<p role="status" id="calendar-share-status"></p><div class="error" role="alert"></div><div class="actions"><button type="button" data-calendar-share="stop">Stop Sharing</button><button type="button" data-action="close">Cancel</button><button type="submit" class="primary">Save</button></div></form>`);
 renderCalendarPeople();
 const form=document.querySelector('#calendar-sharing-form');
 form.elements.invitee.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();addCalendarPeople()}};
 form.onsubmit=async event=>{
  event.preventDefault();if(form.elements.invitee.value.trim()&&!addCalendarPeople())return;
  const buttons=[...form.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
  try{
   const result=await api('/api/calendar-shares',{calendar:calendar.id,revision:data.revision,participants:calendarShareContext.participants,public:form.elements.public.checked});
   closeDialog();await calendarPage();
   if(result.public_path&&!data.public_path)await calendarSharing(appData.calendars.find(c=>c.id===calendar.id));
  }catch(error){form.querySelector('.error').textContent=error.message}finally{buttons.forEach(b=>b.disabled=false)}
 };
}
function renderCalendarPeople(){
 document.querySelector('#calendar-people').innerHTML=calendarShareContext.participants.map((p,i)=>`<section class="calendar-person"><strong>${esc(p.email)}</strong><small>${esc(p.status||'Invited')}</small><select data-calendar-permission="${i}" aria-label="Access for ${esc(p.email)}"><option value="write" ${p.permission==='write'?'selected':''}>Allow editing</option><option value="read" ${p.permission==='read'?'selected':''}>Read-Only</option></select><button type="button" data-calendar-share="resend" data-index="${i}">Invite Again</button><button type="button" data-calendar-share="remove" data-index="${i}">Remove Person</button></section>`).join('');
 document.querySelectorAll('[data-calendar-permission]').forEach(select=>select.onchange=()=>calendarShareContext.participants[Number(select.dataset.calendarPermission)].permission=select.value);
}
function addCalendarPeople(){
 const form=document.querySelector('#calendar-sharing-form'),input=form.elements.invitee;
 const emails=input.value.split(/[,;\n]/).map(e=>e.trim().toLowerCase()).filter(Boolean);
 if(!emails.length){form.querySelector('.error').textContent='Enter an email address for each participant.';input.focus();return false}
 if(emails.some(e=>!/^\S+@\S+\.\S+$/.test(e))){form.querySelector('.error').textContent='Enter an email address for each participant.';return false}
 for(const email of emails)if(!calendarShareContext.participants.some(p=>p.email===email))calendarShareContext.participants.push({email,permission:'write',status:'invited'});
 input.value='';form.querySelector('.error').textContent='';renderCalendarPeople();return true;
}
async function calendarInbox(){
 calendarInboxState=await api('/api/calendar-inbox');calendarGeneration=calendarInboxState.generation;
 const {invitations,messages,events=[]}=calendarInboxState;
 showDialog('Calendar Inbox',invitations.map(v=>`<section class="calendar-invitation"><h3>${esc(v.name)}</h3><p>${esc(v.owner_name)} invited you.</p><button data-calendar-share="join" data-id="${esc(v.id)}">Join Calendar</button><button data-calendar-share="decline" data-id="${esc(v.id)}">Decline</button></section>`).join('')+events.map(v=>`<section class="calendar-invitation"><h3>${esc(v.event.title)}</h3><p>${esc(v.organizer)} invited you.</p><button data-event-reply="open" data-token="${esc(v.token)}">View Invitation</button></section>`).join('')+messages.map(v=>`<p>${esc(v.message)}</p>`).join('')+(!invitations.length&&!messages.length&&!events.length?'<p>No Invitations</p>':'')+'<button data-action="close">Done</button>');
}
async function calendarInvitationPage(){
 clearInterval(calendarPoll);root.innerHTML=header('Calendar')+'<main class="settings-page" id="calendar-invitation"></main>';
 const target=document.querySelector('#calendar-invitation');
 try{
  const data=await api('/api/calendar-shares/'+location.pathname.split('/')[3]);calendarGeneration=data.generation;
  target.innerHTML=`<h1>${esc(data.name)}</h1><p>${esc(data.owner_name)} invited you to share this calendar.</p>${data.accepted?'<a href="/calendar/">Open Calendar</a>':`<button data-calendar-share="join" data-id="${esc(data.id)}">Join Calendar</button><button data-calendar-share="decline" data-id="${esc(data.id)}">Decline</button>`}`;
 }catch(error){target.innerHTML='<h1>Unable to Open Calendar</h1><p>'+esc(error.message)+'</p><a href="/calendar/">Back to Calendar</a>'}
}
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-calendar-share]');if(!button)return;
 const action=button.dataset.calendarShare;
 try{
  if(action==='manage')return await calendarSharing(appData.calendars.find(c=>c.id===button.dataset.id));
  if(action==='add'){addCalendarPeople();return}
  if(action==='remove'){calendarShareContext.participants.splice(Number(button.dataset.index),1);renderCalendarPeople();return}
  if(action==='resend'){calendarShareContext.participants[Number(button.dataset.index)].resend=true;document.querySelector('#calendar-share-status').textContent='Invitation will be sent when you save.';return}
  if(action==='stop'){calendarShareContext.participants=[];document.querySelector('#calendar-sharing-form').elements.public.checked=false;renderCalendarPeople();document.querySelector('#calendar-share-status').textContent='Select Save to stop sharing.';return}
  if(action==='copy'){await navigator.clipboard.writeText(location.origin+calendarShareContext.data.public_path);document.querySelector('#calendar-share-status').textContent='Copied';return}
  if(action==='email'){
   const id=calendarShareContext.data.id;
   formDialog('Email Calendar',field('to','To'),async data=>{await api('/api/calendar-shares/'+id,{action:'email-public',recipients:data.to.split(/[,;\n]/).map(e=>e.trim()).filter(Boolean)})});
   document.querySelector('#edit-form [type=submit]').textContent='Send';return;
  }
  if(action==='join'||action==='decline'){
   button.disabled=true;await api('/api/calendar-shares/'+button.dataset.id,{action});
   if(location.pathname.includes('/share/'))navigate('/calendar/');else{closeDialog();await calendarPage()}return;
  }
  if(action==='leave'){showDialog('Unsubscribe from Calendar?','<p>This calendar will be removed from your calendar list.</p><button data-action="close">Cancel</button><button data-calendar-share="confirm-leave">Unsubscribe</button>');return}
  if(action==='confirm-leave'){await api('/api/calendar-shares/'+calendarShareContext.data.id,{action:'leave'});closeDialog();await calendarPage()}
 }catch(error){showDialog('Calendar',`<p role="alert">${esc(error.message)}</p><button data-action="close">Done</button>`)}
});
