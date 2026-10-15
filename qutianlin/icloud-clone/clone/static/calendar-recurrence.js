/* Floating wall dates; timezone conversion is handled separately from recurrence. */
let eventEditorContext=null;
function eventValuesChanged(before,after){
 const keys=['title','location','calendar','allDay','start','end','repeat','alert','second_alert','invitees','url','notes','timezone'];
 return keys.some(key=>JSON.stringify(before[key]??'')!==JSON.stringify(after[key]??''))||JSON.stringify((before.attachments||[]).map(a=>a.id))!==JSON.stringify((after.attachments||[]).map(a=>a.id));
}
function chooseEventEditScope(existing,payload){
 return new Promise(resolve=>{
  const panel=document.createElement('section');panel.className='event-edit-scope';panel.setAttribute('role','group');panel.setAttribute('aria-label','Edit repeating event');
  panel.innerHTML=`<h3>Edit Repeating Event</h3><p>Apply changes to only this event, or this event and all future occurrences?</p><div class="actions"><button type="button" data-edit-scope="cancel">Cancel Changes</button><button type="button" data-edit-scope="one" ${payload.repeat!==existing.repeat&&payload.repeat!=='Never'?'disabled':''}>Only This Event</button><button type="button" data-edit-scope="future" ${existing._recurrence_parent&&!existing._parent_key?'disabled':''}>This and Future Events</button></div>`;
  modal.querySelector('#edit-form').append(panel);
  const finish=value=>{panel.remove();modal.removeEventListener('cancel',cancel);modal.removeEventListener('close',cancel);resolve(value)};
  const cancel=()=>finish(null);modal.addEventListener('cancel',cancel,{once:true});modal.addEventListener('close',cancel,{once:true});
  panel.querySelectorAll('[data-edit-scope]').forEach(button=>button.onclick=()=>finish(button.dataset.editScope==='cancel'?null:button.dataset.editScope));
  panel.querySelector('button').focus();
 });
}
const calendarDayMs=86400000;
function calendarUTC(value){return Date.parse(value.length===10?value+'T00:00:00Z':value+'Z')}
function eventStartsOn(event,key){
 const first=event.start.slice(0,10);
 if(key<first||(event._until&&key>event._until)||(event._excluded||[]).includes(key))return false;
 const base=new Date(calendarUTC(first)),day=new Date(calendarUTC(key));
 switch(event.repeat||'Never'){
  case 'Every Day':return true;
  case 'Every Week':return base.getUTCDay()===day.getUTCDay();
  case 'Every Month':return base.getUTCDate()===day.getUTCDate();
  case 'Every Year':return base.getUTCMonth()===day.getUTCMonth()&&base.getUTCDate()===day.getUTCDate();
  default:return key===first;
 }
}
function eventOccurrencesOnDate(event,key){
 if(calendarPreferences.hide_past&&new Date(key+'T23:59:59')<new Date(Date.now()-calendarPreferences.hide_days*calendarDayMs))return [];
 if(!event._birthday&&calendarViewDays)return (calendarViewDays[key]||[]).filter(value=>value.id===event.id).map(value=>({...event,...value}));
 if(!event.start||!event.end)return [];
 const baseDay=calendarUTC(event.start.slice(0,10)),viewDay=calendarUTC(key);
 const start=calendarUTC(event.start),end=calendarUTC(event.end)+(event.allDay?calendarDayMs:0);
 const span=Math.max(0,end-start),offset=start-baseDay,result=[];
 let candidate=Math.max(baseDay,viewDay-Math.ceil(span/calendarDayMs)*calendarDayMs);
 if(!event.repeat||event.repeat==='Never')candidate=baseDay;
 for(;candidate<=viewDay;candidate+=calendarDayMs){
  const occurrence=new Date(candidate).toISOString().slice(0,10),begin=candidate+offset;
  if(eventStartsOn(event,occurrence)&&begin<viewDay+calendarDayMs&&(span===0?begin>=viewDay:begin+span>viewDay))result.push({...event,_occurrence:occurrence});
  if(!event.repeat||event.repeat==='Never')break;
 }
 return result;
}
async function deleteEventOccurrence(){
 const context=eventEditorContext;if(!context?.existing.id)return;
 const {existing,occurrence}=context;
 const remove=async scope=>{
  if(modal.dataset.deleting)return;
  modal.dataset.deleting='true';const previous=document.activeElement,controls=[...modal.querySelectorAll('button')].filter(button=>!button.closest('#alarm-banner'));
  const states=controls.map(button=>button.disabled);controls.forEach(button=>button.disabled=true);
  const error=modal.querySelector('.error');if(error)error.textContent='';
  try{
   if(!await confirmEventDeletion(existing))return;
   await api('/api/items/events/'+encodeURIComponent(existing.id),{_revision:existing._revision,_parent_revision:existing._parent_revision,occurrence,scope},'DELETE');
   closeDialog();await calendarPage();
  }catch(failure){if(error)error.textContent=failure.message;else showDialog('Unable to delete event',`<p role="alert">${esc(failure.message)}</p><button data-action="close">Done</button>`)}
  finally{delete modal.dataset.deleting;controls.forEach((button,index)=>button.disabled=states[index]);if(modal.open&&previous?.isConnected)previous.focus()}
 };
 if(!existing.repeat||existing.repeat==='Never')return remove();
 showDialog('Delete Repeating Event',`<p>${esc(existing.title)}</p><p>${esc(calendarDateLabel(occurrence))}</p><p>Delete only this event, or this event and all future events?</p><div class="error" role="alert"></div><div class="actions"><button data-action="close">Cancel</button><button data-delete-occurrence="one">Only This Event</button><button data-delete-occurrence="future" ${existing._recurrence_parent&&!existing._parent_key?'disabled':''}>This and Future Events</button></div>`);
 modal.querySelectorAll('[data-delete-occurrence]').forEach(button=>button.onclick=()=>remove(button.dataset.deleteOccurrence));
}
