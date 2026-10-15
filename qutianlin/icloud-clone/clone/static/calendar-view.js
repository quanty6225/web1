let calendarSidebarHidden=false;
function calendarDateKey(date){return date.getFullYear()+'-'+String(date.getMonth()+1).padStart(2,'0')+'-'+String(date.getDate()).padStart(2,'0')}
function calendarGroup(calendar){return calendar._sharing&&!calendar._sharing.owner?'shared':'owned'}
function orderedCalendars(calendars){
 const ranks=new Map((calendarPreferences.calendar_order||[]).map((id,index)=>[id,index]));
 return [...calendars].sort((a,b)=>calendarGroup(a).localeCompare(calendarGroup(b))||(ranks.get(a.id)??99999)-(ranks.get(b.id)??99999));
}
function monthDays(date){
 const first=new Date(date);first.setDate(1);first.setDate(first.getDate()-first.getDay());
 return Array.from({length:42},(_,index)=>{const day=new Date(first);day.setDate(day.getDate()+index);return day});
}
function birthdayEvents(contacts){
 return contacts.flatMap(contact=>{
  const match=/^(?:(\d{4})-?|--)(\d{2})-?(\d{2})$/.exec(contact.birthday||'');if(!match)return [];
  const start=(match[1]||'2000')+'-'+match[2]+'-'+match[3],date=new Date(start+'T12:00:00Z');
  if(isNaN(date)||date.toISOString().slice(0,10)!==start)return [];
  return [{id:'birthday:'+contact.id,title:contact.name+'’s Birthday',calendar:'birthdays',start,end:start,allDay:true,repeat:'Every Year',_birthday:contact.id}];
 });
}
function alternateCalendarDate(day){
 if(!calendarPreferences.alternate_calendar)return '';
 return new Intl.DateTimeFormat('en-US-u-ca-'+calendarPreferences.alternate_calendar,{month:'short',day:'numeric'}).format(day);
}
async function calendarPage(){
 clearInterval(calendarPoll);
 const events=await items('events'),calendars=await items('calendars');
 calendarInboxState=await api('/api/calendar-inbox');calendarPreferences=await api('/api/calendar-preferences');calendarHidden.clear();(calendarPreferences.hidden_calendars||[]).forEach(id=>calendarHidden.add(id));
 calendarTimeSettings=await api('/api/calendar-time-settings');
 const range=monthDays(calendarDate);calendarViewDays=(await api('/api/calendar-view?start='+calendarDateKey(range[0])+'&end='+calendarDateKey(range[41])+'&time_zone_support='+timezoneSupport())).days;
 const birthdays=calendarPreferences.show_birthdays?birthdayEvents(await items('contacts')):[];
 const shownEvents=[...events,...birthdays],ordered=orderedCalendars(calendars);
 const mode=location.pathname.includes('month')?'month':location.pathname.includes('day')?'day':'week';
 const title=calendarDate.toLocaleDateString('en-US',{month:'long',year:'numeric'});
 let side='<h2>Calendars</h2>'+ordered.map(c=>`<div class="calendar-sidebar-row" data-calendar-row="${esc(c.id)}" data-selected="${c.id===calendarPreferences.selected_calendar}" data-calendar-group="${calendarGroup(c)}" draggable="${innerWidth>1024}"><label class="calendar-toggle"><input type="checkbox" aria-label="Show ${esc(c.name)}" ${calendarHidden.has(c.id)?'':'checked'} data-calendar-toggle="${esc(c.id)}"></label><button class="calendar-select" data-calendar-action="select" data-id="${esc(c.id)}" aria-label="Select ${esc(c.name)}" aria-pressed="${c.id===calendarPreferences.selected_calendar}"><span style="color:${esc(c.color)}">●</span> ${esc(c.name)}</button><button data-calendar-share="manage" data-id="${esc(c.id)}" aria-label="Sharing ${esc(c.name)}">${c._sharing?'♧':'＋'}</button><button data-calendar-action="menu" data-id="${esc(c.id)}" aria-label="Options for ${esc(c.name)}">•••</button></div>`).join('');
 if(calendarPreferences.show_birthdays)side+='<label class="calendar-toggle"><input type="checkbox" data-calendar-toggle="birthdays" '+(calendarHidden.has('birthdays')?'':'checked')+'>Birthdays</label>';
 side+='<button data-op="calendar-settings">Settings</button><button data-calendar-action="go-date">Go to Date</button><button data-op="new-calendar">＋ New Calendar</button><button data-op="calendar-inbox">Inbox'+((calendarInboxState.invitations.length+(calendarInboxState.events||[]).length)?' ('+(calendarInboxState.invitations.length+(calendarInboxState.events||[]).length)+')':'')+'</button>';
 if(mode==='day')side+=`<section class="calendar-mini-month" aria-label="Month overview"><h3>${title}</h3><div>${monthDays(calendarDate).map(day=>{const key=calendarDateKey(day),hasEvents=shownEvents.some(e=>!calendarHidden.has(e.calendar)&&eventOccurrencesOnDate(e,key).length);return `<button data-calendar-action="date" data-date="${key}" aria-label="${key}${hasEvents?', has events':''}" ${key===calendarDateKey(calendarDate)?'aria-current="date"':''}>${day.getDate()}${hasEvents?'<span aria-hidden="true">•</span>':''}</button>`}).join('')}</div></section>`;
 const toolbar=`<button data-calendar-action="sidebar" aria-label="${calendarSidebarHidden?'Show':'Hide'} Calendars" aria-expanded="${!calendarSidebarHidden}">☰</button><button data-op="calendar-prev" aria-label="Previous">‹</button><button data-op="calendar-today">Today</button><button data-op="calendar-next" aria-label="Next">›</button><h1>${title}</h1><span class="spacer"></span><a href="/calendar/day/">Day</a><a href="/calendar/">Week</a><a href="/calendar/month/">Month</a><button data-op="new-event" aria-label="New event">＋</button>`;
 let days;if(mode==='month')days=monthDays(calendarDate);else if(mode==='day')days=[new Date(calendarDate)];else{const first=new Date(calendarDate);first.setDate(first.getDate()-first.getDay());days=Array.from({length:7},(_,index)=>{const day=new Date(first);day.setDate(day.getDate()+index);return day})}
 const allDayRows=Math.max(1,...days.map(day=>shownEvents.flatMap(e=>eventOccurrencesOnDate(e,calendarDateKey(day))).filter(e=>e.allDay&&!calendarHidden.has(e.calendar)).length));
 appFrame('Calendar',side,`<div class="calendar-grid ${mode}" style="--days:${mode==='day'?1:7};--all-day-height:${Math.max(38,allDayRows*32)}px">${mode==='month'?'':calendarTimeAxis()}${days.map(day=>`<section class="calendar-day" data-day="${calendarDateKey(day)}">${calendarDayContents(day,shownEvents,calendars,mode)}</section>`).join('')}</div>`,toolbar);
 applyCalendarSidebar();
 document.querySelectorAll('[data-calendar-toggle]').forEach(control=>control.onchange=async()=>{control.checked?calendarHidden.delete(control.dataset.calendarToggle):calendarHidden.add(control.dataset.calendarToggle);try{await api('/api/calendar-preferences',{hidden_calendars:[...calendarHidden]},'PUT');await calendarPage()}catch(error){control.checked=!control.checked;showDialog('Calendar',`<p role="alert">${esc(error.message)}</p><button data-action="close">Done</button>`)}});
 setupCalendarOrdering();startCalendarPoll();
}
function applyCalendarSidebar(){const layout=document.querySelector('.app-layout');layout?.classList.toggle('calendar-sidebar-hidden',calendarSidebarHidden);const aside=layout?.querySelector('aside');if(aside)aside.hidden=calendarSidebarHidden}
function calendarEventEditable(event){return !event._birthday&&(!event._invitation||event._sharing?.permission==='write')&&(!event._sharing||event._sharing.permission==='write')}
async function moveCalendarEvent(dragged,target){
 if(calendarMovePending)return;
 calendarMovePending=true;
 try{
  const existing=await api('/api/event-occurrence/'+encodeURIComponent(dragged.id)+'?occurrence='+encodeURIComponent(dragged.occurrence));
  if(existing.calendar===target)return;
  if(!calendarEventEditable(existing))throw Error('This event is read-only.');
  const payload={...existing,calendar:target};
  if(existing.repeat&&existing.repeat!=='Never'){
   showDialog('Move Repeating Event',`<form id="edit-form"><p>${esc(existing.title)}</p><p>${esc(calendarDateTimeLabel(existing.start))}</p></form>`);
   modal.querySelector('form').onsubmit=event=>event.preventDefault();
   const scope=await chooseEventEditScope(existing,payload);if(!scope){closeDialog();return}
   payload.scope=scope;payload.occurrence=existing._edit_occurrence;
  }
  if(!await confirmEventUpdate(existing,payload,{moving:true})){closeDialog();return}
  closeDialog();
  await storeItem('events',payload);await calendarPage();
 }catch(error){showDialog('Calendar',`<p role="alert">${esc(error.message)}</p><button data-action="close">Done</button>`)}
 finally{calendarMovePending=false}
}
function setupCalendarOrdering(){
 if(innerWidth<=1024)return;
 let dragging=null,eventMove=null;
 const finish=()=>{dragging=null;eventMove=null;calendarDragActive=false};
 document.querySelectorAll('.calendar-event[draggable="true"]').forEach(button=>{
  button.ondragstart=event=>{
   if(calendarMovePending||modal.open){event.preventDefault();return}
   eventMove={id:button.dataset.id,occurrence:button.dataset.occurrence};calendarDragActive=true;
   event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('application/x-icloud-event',button.dataset.id);
  };
  button.ondragend=finish;
 });
 document.querySelectorAll('[data-calendar-row]').forEach(row=>{
  const acceptsEvent=()=>eventMove&&writableCalendars().some(c=>c.id===row.dataset.calendarRow)&&appData.events.find(e=>e.id===eventMove.id)?.calendar!==row.dataset.calendarRow;
  row.ondragstart=event=>{if(calendarMovePending||modal.open||event.target.closest('input,button:not(.calendar-select)')){event.preventDefault();return}dragging=row;calendarDragActive=true;event.dataTransfer.setData('text/plain',row.dataset.calendarRow)};
  row.ondragover=event=>{if(acceptsEvent()||dragging&&dragging!==row&&dragging.dataset.calendarGroup===row.dataset.calendarGroup){event.preventDefault();event.dataTransfer.dropEffect='move'}};
  row.ondrop=async event=>{
   if(acceptsEvent()){event.preventDefault();const selected=eventMove;finish();await moveCalendarEvent(selected,row.dataset.calendarRow);return}
   if(!dragging||dragging===row||dragging.dataset.calendarGroup!==row.dataset.calendarGroup)return;
   event.preventDefault();const order=orderedCalendars(appData.calendars).map(c=>c.id),from=order.indexOf(dragging.dataset.calendarRow),target=order.indexOf(row.dataset.calendarRow);
   order.splice(from,1);order.splice(target,0,dragging.dataset.calendarRow);finish();
   try{await api('/api/calendar-preferences',{calendar_order:order},'PUT');await calendarPage()}catch(error){showDialog('Calendar',`<p role="alert">${esc(error.message)}</p><button data-action="close">Done</button>`)}
  };
  row.ondragend=finish;
 });
}
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-calendar-action]');if(!button)return;
 const action=button.dataset.calendarAction,calendar=appData.calendars?.find(c=>c.id===button.dataset.id);
 try{
  if(action==='time-slot'){if(event.detail===0)newEventAt(button.dataset.date,button.dataset.time);else{document.querySelector('.calendar-time-slot.selected')?.classList.remove('selected');button.classList.add('selected')}return}
  if(action==='sidebar'){calendarSidebarHidden=!calendarSidebarHidden;applyCalendarSidebar();button.setAttribute('aria-label',(calendarSidebarHidden?'Show':'Hide')+' Calendars');button.setAttribute('aria-expanded',String(!calendarSidebarHidden));return}
  if(action==='go-date'){formDialog('Go to Date',field('date','Date',calendarDateLabel(calendarDateKey(calendarDate))),async data=>{const iso=calendarParseDate(data.date),day=new Date(iso+'T12:00:00');if(isNaN(day)||calendarDateKey(day)!==iso)throw Error('Choose a valid date.');calendarDate=day;await calendarPage()});document.querySelector('#edit-form [type=submit]').textContent='OK';return}
  if(action==='date'){calendarDate=new Date(button.dataset.date+'T12:00:00');return await calendarPage()}
  if(action==='birthday'){const contact=appData.contacts.find(c=>c.id===button.dataset.contact);return showDialog(contact.name+'’s Birthday',`<p>${esc(contact.birthday)}</p><a href="/contacts/?item=${encodeURIComponent(contact.id)}">Edit in Contacts</a><button data-action="close">Done</button>`)}
  if(!calendar)return;
  if(action==='select'){await api('/api/calendar-preferences',{selected_calendar:calendar.id},'PUT');await calendarPage();return}
  const received=calendar._sharing&&!calendar._sharing.owner;
  if(action==='menu'){showDialog(calendar.name,received?`<button data-calendar-share="manage" data-id="${esc(calendar.id)}">Sharing Information</button><button data-action="close">Done</button>`:`<button data-calendar-action="edit" data-id="${esc(calendar.id)}">Edit Calendar</button><button data-calendar-action="delete" data-id="${esc(calendar.id)}">Delete Calendar</button><button data-action="close">Done</button>`);return}
  if(received)return;
  if(action==='edit')return formDialog('Edit Calendar',field('name','Name',calendar.name)+field('color','Color',calendar.color,'color'),async data=>{await storeItem('calendars',{...calendar,...data});await calendarPage()});
  if(action==='delete')return showDialog('Delete Calendar?',`<p>Deleting ${esc(calendar.name)} also deletes all of its events.</p><div class="error" role="alert"></div><button data-action="close">Cancel</button><button data-calendar-action="confirm-delete" data-id="${esc(calendar.id)}">Delete</button>`);
  if(action==='confirm-delete'){button.disabled=true;try{await removeItem('calendars',calendar.id);closeDialog();await calendarPage()}catch(error){modal.querySelector('.error').textContent=error.message;button.disabled=false}}
 }catch(error){showDialog('Calendar',`<p role="alert">${esc(error.message)}</p><button data-action="close">Done</button>`)}
});
