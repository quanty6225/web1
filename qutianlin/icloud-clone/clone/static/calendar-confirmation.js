/* Source Save & Send confirmation; no event mutation is made before approval. */
function eventUpdateNeedsConfirmation(existing,payload){
 if(!existing.id||!(payload.invitees||[]).length)return false;
 const fields=['title','start','end','location','notes','url','repeat','allDay','timezone','invitees'];
 return fields.some(key=>JSON.stringify(existing[key]??'')!==JSON.stringify(payload[key]??''))||JSON.stringify((existing.attachments||[]).map(a=>a.id))!==JSON.stringify((payload.attachments||[]).map(a=>a.id));
}
async function confirmEventUpdate(existing,payload,{moving=false}={}){
 if(!eventUpdateNeedsConfirmation(existing,payload)&&!(moving&&(payload.invitees||[]).length))return true;
 const preferences=await api('/api/calendar-preferences');
 if(!preferences.prompt_event_updates)return true;
 return calendarEventNotification({title:'Send event update to invitees?',description:'You have made changes to an event with invitees. Saving this event will send an update letting them know that the event has changed.',action:'Save & Send',ask:true,onConfirm:checked=>{payload._prompt_event_updates=checked}});
}
function confirmEventDeletion(existing){
 if(!(existing.invitees||[]).length||existing._end_timestamp!=null&&existing._end_timestamp<Date.now())return Promise.resolve(true);
 return calendarEventNotification({title:'Delete event and notify invitees?',description:`If you delete “${existing.title}”, its invitees will be notified that this event has been cancelled.`,action:'Delete and Notify'});
}
function calendarEventNotification({title,description,action,ask=false,onConfirm=()=>{}}){
 return new Promise(resolve=>{
  const panel=document.createElement('dialog');panel.className='calendar-send-confirmation';panel.setAttribute('aria-labelledby','calendar-send-title');
  panel.innerHTML=`<img src="/static/icons/calendar.png" alt=""><h2 id="calendar-send-title">${esc(title)}</h2><p>${esc(description)}</p>${ask?'<label><input type="checkbox" checked>Ask before sending updates to events with invitees.</label>':''}<div class="actions"><button type="button" data-send="cancel">Cancel</button><button type="button" class="primary" data-send="confirm">${esc(action)}</button></div>`;
  const previous=document.activeElement;let settled=false;
  const finish=confirmed=>{
   if(settled)return;settled=true;
   if(confirmed)onConfirm(panel.querySelector('input')?.checked);
   modal.removeEventListener('close',cancel);panel.remove();previous?.focus();resolve(confirmed);
  };
  const cancel=()=>finish(false);
  panel.addEventListener('cancel',event=>{event.preventDefault();cancel()});
  panel.addEventListener('close',cancel);modal.addEventListener('close',cancel,{once:true});
  panel.querySelector('[data-send=cancel]').onclick=cancel;
  panel.querySelector('[data-send=confirm]').onclick=()=>finish(true);
  document.body.append(panel);panel.showModal();panel.querySelector('[data-send=confirm]').focus();
 });
}
