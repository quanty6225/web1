let calendarTimeSettings={timezone:'America/Toronto',zones:[]},calendarViewDays=null;
function timezoneSupportKey(){return 'icloud-calendar-timezone:'+session.account.account_id}
function timezoneSupport(){try{return localStorage.getItem(timezoneSupportKey())==='true'}catch{return false}}
function saveTimezoneSupport(value){localStorage.setItem(timezoneSupportKey(),String(value))}
function eventTimezoneField(existing){
 const value=existing.timezone||calendarTimeSettings.timezone;
 return `<label id="event-timezone-field" ${!timezoneSupport()||existing.allDay?'hidden':''}>Time Zone<select name="timezone" aria-label="Time Zone">${['Floating',...calendarTimeSettings.zones].map(zone=>`<option value="${esc(zone)}" ${zone===value?'selected':''}>${esc(zone.replaceAll('_',' '))}</option>`).join('')}</select></label>`;
}
function calendarHourLabel(hour){return calendarClockLabel(String(hour).padStart(2,'0')+':00',true)}
function newEventAt(date,hour){
 const start=date+'T'+hour,end=new Date(Date.parse(start+'Z')+3600000).toISOString().slice(0,16);
 editEvent({start,end,timezone:calendarTimeSettings.timezone},date);
}
function timedEventLanes(events){
 const placed=events.filter(e=>!e.allDay).sort((a,b)=>a._minute_start-b._minute_start||a._minute_end-b._minute_end);
 let group=[],ends=[],groupEnd=-1;
 const finish=()=>{group.forEach(e=>e._lanes=ends.length);group=[];ends=[]};
 for(const event of placed){
  if(event._minute_start>=groupEnd){finish();groupEnd=-1}
  let lane=ends.findIndex(end=>end<=event._minute_start);if(lane<0)lane=ends.length;
  ends[lane]=Math.max(event._minute_end,event._minute_start+35);groupEnd=Math.max(groupEnd,ends[lane]);event._lane=lane;group.push(event);
 }
 finish();return placed;
}
function calendarEventButton(event,calendars,timed=false){
 const color=calendars.find(c=>c.id===event.calendar)?.color||'#777777';
 const position=timed?`;top:${event._minute_start*.8}px;height:${Math.max(28,(event._minute_end-event._minute_start)*.8)}px;left:${event._lane/event._lanes*100}%;width:${100/event._lanes}%`:'';
 return `<button class="calendar-event${timed?' timed-event':''}" draggable="${innerWidth>1024&&calendarEventEditable(event)}" style="border-left:4px solid ${esc(color)}${position}" aria-label="${esc(event.title)}" ${event._birthday?'data-calendar-action="birthday" data-contact="'+esc(event._birthday)+'"':'data-op="edit-event"'} data-id="${esc(event.id)}" data-calendar="${esc(event.calendar)}" data-occurrence="${event._occurrence}" ${calendarHidden.has(event.calendar)?'hidden':''}><span>${esc(event.title)}</span>${!event.allDay?'<small class="event-time">'+esc(event._start_label||event.start.slice(11))+' – '+esc(event._end_label||event.end.slice(11))+'</small>':''}${event.attachments?.length?'<span aria-label="Has attachments"> 📎</span>':''}</button>`;
}
function calendarDayContents(day,events,calendars,mode){
 const key=calendarDateKey(day),entries=events.flatMap(event=>eventOccurrencesOnDate(event,key));
 const heading=`<button class="calendar-day-heading" data-op="new-event" data-date="${key}"><small>${day.toLocaleDateString('en-US',{weekday:'short'})}</small><strong>${day.getDate()}</strong>${calendarPreferences.alternate_calendar?'<small class="alternate-date">'+esc(alternateCalendarDate(day))+'</small>':''}</button>`;
 if(mode==='month')return heading+entries.map(event=>calendarEventButton(event,calendars)).join('');
 const timed=timedEventLanes(entries.filter(e=>!calendarHidden.has(e.calendar)));
 return heading+'<div class="calendar-all-day">'+entries.filter(e=>e.allDay).map(event=>calendarEventButton(event,calendars)).join('')+'</div><div class="calendar-timeline">'+Array.from({length:24},(_,hour)=>`<button class="calendar-time-slot" data-calendar-action="time-slot" data-date="${key}" data-time="${String(hour).padStart(2,'0')}:00" aria-label="New event on ${key} at ${calendarHourLabel(hour)}" style="top:${hour*48}px"></button>`).join('')+timed.map(event=>calendarEventButton(event,calendars,true)).join('')+'</div>';
}
function calendarTimeAxis(){return '<section class="calendar-time-axis" aria-label="Time scale"><div class="calendar-day-heading"></div><div class="calendar-all-day">All Day</div><div class="calendar-timeline">'+Array.from({length:24},(_,hour)=>`<span style="top:${hour*48}px">${calendarHourLabel(hour)}</span>`).join('')+'</div></section>'}
document.addEventListener('dblclick',event=>{const slot=event.target.closest('.calendar-time-slot');if(slot)newEventAt(slot.dataset.date,slot.dataset.time)});
window.addEventListener('storage',event=>{if(session?.account&&event.key===timezoneSupportKey()&&location.pathname.startsWith('/calendar/')&&!modal.open)calendarPage()});
