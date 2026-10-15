let reminderSharingTimer=null,reminderSharingContext=null;
function reminderWritableLists(){return (reminderContext?.lists||[]).filter(list=>!list._sharing||list._sharing.accepted)}
function stopReminderSharingPoll(){clearInterval(reminderSharingTimer);reminderSharingTimer=null}
function startReminderSharingPoll(){
 let busy=false;
 reminderSharingTimer=setInterval(async()=>{
  if(busy||modal.open||!location.pathname.startsWith('/reminders/')||location.pathname.startsWith('/reminders/share/'))return;
  busy=true;
  try{
   const [lists,reminders]=await Promise.all(['lists','reminders'].map(async kind=>(await api('/api/items/'+kind)).items));
   const removed=reminderContext.list?._sharing&&!lists.some(l=>l.id===reminderContext.list.id);
   if(!removed&&document.activeElement?.matches('input,textarea,select'))return;
   if(JSON.stringify([lists,reminders])!==JSON.stringify([reminderContext.lists,reminderContext.reminders]))await remindersPage();
  }catch(error){const panel=document.querySelector('#reminder-list');if(panel&&!panel.querySelector('.sharing-error'))panel.insertAdjacentHTML('beforeend','<p class="sharing-error" role="alert">'+esc(error.message)+'</p>')}
  finally{busy=false}
 },2000);
}
async function manageReminderSharing(list){
 if(!list)return;
 const data=list._sharing?await api('/api/reminder-shares/'+list._sharing.id):null;
 if(data&&!data.accepted){showDialog('Shared Reminder List','<div id="reminder-invitation"></div><button data-action="close">Cancel</button>');return reminderInvitationContent(data.id,document.querySelector('#reminder-invitation'))}
 reminderSharingContext={list,id:data?.id};
 let contacts=[];if(!data||data.owner)contacts=await items('contacts');
 const suggestions=contacts.flatMap(c=>(c.emails||[]).map(e=>({name:c.name,email:e.value}))).filter(c=>c.email);
 showDialog('Sharing '+list.name,`${data?'<p>'+esc(data.owner_name)+' — Owner</p>':''}<div class="reminder-participants">${(data?.participants||[]).map(p=>`<section><strong>${esc(p.email)}${p.self?' (You)':''}</strong><small>${p.status==='accepted'?'Joined':p.status==='declined'?'Declined':'Invited'}</small>${data.owner?`<button data-reminder-share="resend" data-email="${esc(p.email)}">Invite Again</button><button data-reminder-share="remove" data-email="${esc(p.email)}">Remove Person</button>`:''}</section>`).join('')}</div>${!data||data.owner?`<form id="reminder-sharing-form"><label>People<input name="recipients" aria-label="People" list="reminder-contact-suggestions" placeholder="Contact names or email addresses" ${data?'':'required'}></label><datalist id="reminder-contact-suggestions">${suggestions.map(c=>`<option value="${esc(c.email)}">${esc(c.name)}</option>`).join('')}</datalist><div class="error" role="alert"></div><div class="actions"><button type="button" data-action="close">Cancel</button><button type="submit" class="primary">Done</button></div></form>`:'<button data-reminder-share="leave">Leave List</button><button data-action="close">Done</button>'}<p role="status" id="reminder-sharing-status"></p>`);
 const form=document.querySelector('#reminder-sharing-form');if(form)form.onsubmit=async event=>{
  event.preventDefault();const submit=form.querySelector('[type=submit]');submit.disabled=true;
  try{
   const entries=new FormData(form).get('recipients').split(/[,;\n]/).map(v=>v.trim()).filter(Boolean);
   if(!entries.length&&data){closeDialog();return}
   const recipients=entries.map(value=>{if(value.includes('@'))return value;const matches=[...new Set(suggestions.filter(c=>String(c.name||'').toLocaleLowerCase()===value.toLocaleLowerCase()).map(c=>c.email))];if(matches.length!==1)throw Error('Choose an email address for '+value+'.');return matches[0]});
   await api('/api/reminder-shares',{list:list.id,share_id:data?.id,recipients});closeDialog();await remindersPage();
  }catch(error){form.querySelector('.error').textContent=error.message}finally{submit.disabled=false}
 };
}
async function reminderInvitationContent(id,target){
 try{
  const data=await api('/api/reminder-shares/'+id);calendarGeneration=data.generation;
  target.innerHTML=`<h2>${esc(data.name)}</h2><p>${esc(data.owner_name)} invited you to share this reminder list.</p><button data-reminder-share="join" data-share-id="${esc(id)}">Join</button><button data-reminder-share="decline" data-share-id="${esc(id)}">Decline</button>`;
 }catch(error){target.innerHTML='<h2>Unable to Open List</h2><p>'+esc(error.message)+'</p><a href="/reminders/">Back to Reminders</a>'}
}
async function reminderInvitationPage(){stopReminderSharingPoll();root.innerHTML=header('Reminders')+'<main class="settings-page" id="reminder-invitation"></main>';await reminderInvitationContent(location.pathname.split('/')[3],document.querySelector('#reminder-invitation'))}
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-reminder-share]');if(!button)return;
 try{
  const action=button.dataset.reminderShare;
  if(action==='manage')return manageReminderSharing(reminderContext.lists.find(l=>l.id===button.dataset.list));
  if(action==='join'||action==='decline'){
   const id=button.dataset.shareId,data=await api('/api/reminder-shares/'+id);button.disabled=true;
   await api('/api/reminder-shares/'+id,{action});if(modal.open)closeDialog();
   navigate(action==='join'?'/reminders/?list='+encodeURIComponent(data.owner?data.target:'rshared:'+id+':'+data.target):'/reminders/');return;
  }
  const context=reminderSharingContext;
  if(action==='leave'){showDialog('Leave List?','<p>To rejoin this shared list, ask the owner to invite you again.</p><button data-action="close">Cancel</button><button data-reminder-share="confirm-leave">Leave List</button>');return}
  button.disabled=true;
  await api('/api/reminder-shares/'+context.id,{action:action==='confirm-leave'?'leave':action,email:button.dataset.email});
  if(action==='confirm-leave'){closeDialog();history.replaceState(null,'','/reminders/');return remindersPage()}
  await remindersPage();const list=reminderContext.lists.find(l=>l.id===context.list.id);
  if(list?._sharing){await manageReminderSharing(list);if(action==='resend')document.querySelector('#reminder-sharing-status').textContent='Invitation sent.'}else closeDialog();
 }catch(error){showDialog('Unable to Share List','<p>'+esc(error.message)+'</p><button data-action="close">OK</button>')}
});
window.addEventListener('pagehide',stopReminderSharingPoll);
