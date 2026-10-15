const calendarFormatOptions={date_format:['MM/DD/YYYY','DD/MM/YYYY','YYYY/MM/DD'],date_separator:['/','-','.'],time_format:['12 Hour','24 Hour'],time_separator:[':','.']};
function calendarFormatSettings(data){
 return '<fieldset><legend>Date &amp; Time Formats</legend>'+Object.entries(calendarFormatOptions).map(([name,options])=>{const label=name.split('_').map(word=>word[0].toUpperCase()+word.slice(1)).join(' ');return `<label>${label}<select name="${name}" aria-label="${label}">${options.map(value=>`<option ${value===(data[name]||options[0])?'selected':''}>${value}</option>`).join('')}</select></label>`}).join('')+'</fieldset>';
}
function calendarDateLabel(value){
 const parts=/^(\d{4})-(\d{2})-(\d{2})/.exec(value||'');if(!parts)return value||'';
 const tokens={YYYY:parts[1],MM:parts[2],DD:parts[3]};
 return (calendarPreferences.date_format||'MM/DD/YYYY').split('/').map(key=>tokens[key]).join(calendarPreferences.date_separator||'/');
}
function calendarClockLabel(value,compact=false){
 const parts=/^(\d{2}):(\d{2})/.exec(value||'');if(!parts)return value||'';
 const hour=Number(parts[1]),separator=calendarPreferences.time_separator||':';
 if(calendarPreferences.time_format==='24 Hour')return parts[1]+separator+parts[2];
 return (hour%12||12)+(compact&&parts[2]==='00'?'':separator+parts[2])+' '+(hour<12?'AM':'PM');
}
function calendarDateTimeLabel(value){return calendarDateLabel(value)+(value?.includes('T')?' '+calendarClockLabel(value.slice(11)):'')}
function calendarParseDate(value){
 const values=value.trim().split(calendarPreferences.date_separator||'/'),order=(calendarPreferences.date_format||'MM/DD/YYYY').split('/');
 if(values.length!==3||values.some((part,i)=>!/^\d+$/.test(part)||part.length>(order[i]==='YYYY'?4:2)))throw Error('Enter a valid date using the selected date format.');
 const parts=Object.fromEntries(order.map((key,index)=>[key,values[index].padStart(key==='YYYY'?4:2,'0')]));
 const iso=parts.YYYY+'-'+parts.MM+'-'+parts.DD,parsed=new Date(iso+'T12:00:00Z');
 if(Number(parts.YYYY)<1||isNaN(parsed)||parsed.toISOString().slice(0,10)!==iso)throw Error('Enter a valid date using the selected date format.');
 return iso;
}
function calendarParseClock(value){
 const parts=/^(\d{1,2})([:.])(\d{2})(?:\s*(AM|PM))?$/i.exec(value.trim());
 if(!parts||parts[2]!== (calendarPreferences.time_separator||':')||Number(parts[3])>59)throw Error('Enter a valid time using the selected time format.');
 let hour=Number(parts[1]);
 if(calendarPreferences.time_format==='24 Hour'){if(hour>23||parts[4])throw Error('Enter a valid 24-hour time.');}
 else{if(hour<1||hour>12||!parts[4])throw Error('Enter a time with AM or PM.');hour=hour%12+(parts[4].toUpperCase()==='PM'?12:0)}
 return String(hour).padStart(2,'0')+':'+parts[3];
}
function calendarDateTimeField(name,label,value,allDay){
 return `<div class="calendar-date-field">${calendarSegmentField(name,label,value)}<label data-calendar-clock="${name}" ${allDay?'hidden':''}>${label} time<input name="${name}_time" aria-label="${label} time" value="${esc(calendarClockLabel(value.slice(11)|| (name==='start'?'09:00':'10:00')))}" ${allDay?'disabled':'required'} autocomplete="off"></label></div>`;
}
function readCalendarDates(form){
 for(const name of ['start','end']){
  form[name]=calendarParseDate(form[name+'_date'])+(form.allDay?'':'T'+calendarParseClock(form[name+'_time']));
  delete form[name+'_date'];delete form[name+'_time'];
 }
 return form;
}
function setupCalendarDateFields(){
 const form=document.querySelector('#edit-form');
 form.querySelectorAll('[data-calendar-segments]').forEach(setupCalendarSegments);
 form.elements.allDay.onchange=event=>{
  document.querySelector('#event-timezone-field').hidden=!timezoneSupport()||event.target.checked;
  for(const name of ['start','end']){const input=form.elements[name+'_time'];input.disabled=event.target.checked;input.required=!event.target.checked;form.querySelector('[data-calendar-clock="'+name+'"]').hidden=event.target.checked}
 };
}
