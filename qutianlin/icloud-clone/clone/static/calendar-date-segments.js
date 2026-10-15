const calendarSegmentNames={MM:'month',DD:'day',YYYY:'year'};
function calendarMonthLength(year,month){return new Date(Date.UTC(year,month,0)).getUTCDate()}
function calendarISODate(parts){return String(parts.year).padStart(4,'0')+'-'+String(parts.month).padStart(2,'0')+'-'+String(parts.day).padStart(2,'0')}
function calendarDateParts(iso){const [year,month,day]=iso.slice(0,10).split('-').map(Number);return {year,month,day}}
function calendarSegmentField(name,label,iso){
 const parts=calendarDateParts(iso),separator=calendarPreferences.date_separator||'/';
 return `<div class="calendar-segment-field"><span>${label}</span><div role="group" aria-label="${label}" class="calendar-date-segments" data-calendar-segments="${name}" data-date="${iso.slice(0,10)}">${(calendarPreferences.date_format||'MM/DD/YYYY').split('/').map(token=>{const part=calendarSegmentNames[token];return `<div role="spinbutton" tabindex="0" contenteditable="true" spellcheck="false" inputmode="numeric" enterkeyhint="next" aria-label="${part}, ${label}" aria-valuemin="1" aria-valuemax="${part==='month'?12:part==='year'?9999:calendarMonthLength(parts.year,parts.month)}" aria-valuenow="${parts[part]}" data-segment="${part}">${String(parts[part]).padStart(part==='year'?4:2,'0')}</div>`}).join('<span aria-hidden="true">'+separator+'</span>')}</div><input type="hidden" name="${name}_date" value="${esc(calendarDateLabel(iso))}"></div>`;
}
function setCalendarSegmentDate(group,iso,notify=true){
 const previous=group.dataset.date,parts=calendarDateParts(iso);
 parts.day=Math.min(parts.day,calendarMonthLength(parts.year,parts.month));iso=calendarISODate(parts);
 group.dataset.date=iso;group.closest('form').elements[group.dataset.calendarSegments+'_date'].value=calendarDateLabel(iso);
 group.querySelectorAll('[data-segment]').forEach(segment=>{
  const key=segment.dataset.segment,value=parts[key];segment.textContent=String(value).padStart(key==='year'?4:2,'0');
  segment.setAttribute('aria-valuenow',value);segment.setAttribute('aria-valuemax',key==='month'?12:key==='year'?9999:calendarMonthLength(parts.year,parts.month));
  segment.setAttribute('aria-valuetext',key==='month'?value+' – '+new Intl.DateTimeFormat('en-US',{month:'long',timeZone:'UTC'}).format(new Date('2000-'+String(value).padStart(2,'0')+'-01T12:00:00Z')):String(value));
 });
 if(notify&&previous!==iso&&group.dataset.calendarSegments==='start'){
  const end=group.closest('form').querySelector('[data-calendar-segments="end"]');
  const delta=Date.parse(iso+'T12:00:00Z')-Date.parse(previous+'T12:00:00Z');
  const shifted=new Date(Date.parse(end.dataset.date+'T12:00:00Z')+delta),year=shifted.getUTCFullYear();
  setCalendarSegmentDate(end,year>=1&&year<=9999?shifted.toISOString().slice(0,10):iso,false);
 }
}
function setupCalendarSegments(group){
 setCalendarSegmentDate(group,group.dataset.date,false);group._pickerMonth=group.dataset.date.slice(0,7);
 const segments=[...group.querySelectorAll('[data-segment]')];
 for(const segment of segments){
  let buffer='',last=0;
  segment.onfocus=()=>{buffer='';last=0};
  segment.onbeforeinput=event=>{
   event.preventDefault();
   if(event.inputType==='insertText'&&/^\d+$/.test(event.data||''))for(const key of event.data)segment.onkeydown({key,preventDefault(){}});
   if(event.inputType==='deleteContentBackward')segment.onkeydown({key:'Backspace',preventDefault(){}});
  };
  segment.onpaste=event=>event.preventDefault();
  segment.onkeydown=event=>{
   const part=segment.dataset.segment,parts=calendarDateParts(group.dataset.date),max=Number(segment.getAttribute('aria-valuemax'));
   let value=parts[part],advance=false;
   if(event.ctrlKey||event.metaKey){if(event.key.toLowerCase()==='a')buffer='';return}
   if(['ArrowUp','ArrowDown','Home','End','Backspace','Delete'].includes(event.key)){
    event.preventDefault();buffer='';last=0;
    if(event.key==='ArrowUp')value=value>=max?1:value+1;
    else if(event.key==='ArrowDown')value=value<=1?max:value-1;
    else if(event.key==='Home')value=1;
    else if(event.key==='End')value=max;
    else value=Math.floor(value/10)||value;
   }else if(/^\d$/.test(event.key)){
    event.preventDefault();if(Date.now()-last>1000)buffer='';last=Date.now();
    buffer+=event.key;if(Number(buffer)>max||buffer.length>(part==='year'?4:2))buffer=event.key;
    value=Number(buffer);if(!value)return;
    advance=value>Math.floor(max/10)||buffer.length===(part==='year'?4:2);
    // The observed source maps typed one/two-digit years through JavaScript's 1900 offset.
    if(part==='year'&&value<100)value+=1900;
   }else if(event.key==='Enter'||event.key===' '){event.preventDefault();openCalendarDatePicker(group,true);return}
   else return;
   parts[part]=value;parts.day=Math.min(parts.day,calendarMonthLength(parts.year,parts.month));setCalendarSegmentDate(group,calendarISODate(parts));
   if(advance){const next=segments[segments.indexOf(segment)+1]||group.closest('form').elements[group.dataset.calendarSegments+'_time'];next?.focus();buffer=''}
  };
 }
 group.onclick=()=>openCalendarDatePicker(group);
}
function closeCalendarDatePicker(focus=false){
 const panel=document.querySelector('.calendar-date-picker');if(!panel)return;
 const group=panel._group;panel.remove();group.setAttribute('aria-expanded','false');
 if(focus&&group.isConnected)group.querySelector('[data-segment]').focus();
}
function openCalendarDatePicker(group,focus=false){
 if(document.querySelector('.calendar-date-picker')?._group===group)return;
 closeCalendarDatePicker();
 const panel=document.createElement('section');panel.className='calendar-date-picker';panel._group=group;
 panel.setAttribute('role','dialog');panel.setAttribute('aria-label','Choose '+group.getAttribute('aria-label')+' date');group.setAttribute('aria-expanded','true');
 group.closest('.calendar-date-field').append(panel);
 function render(focusDate){
  const first=new Date(group._pickerMonth+'-01T12:00:00Z'),year=first.getUTCFullYear(),month=first.getUTCMonth()+1;
  const offset=first.getUTCDay(),count=Math.ceil((offset+calendarMonthLength(year,month))/7)*7;
  const title=first.toLocaleDateString('en-US',{year:'numeric',month:'long',timeZone:'UTC'});
  panel.innerHTML=`<header><button type="button" data-picker-month="-1" aria-label="Previous Month" ${year===1&&month===1?'disabled':''}>‹</button><h3>${title}</h3><button type="button" data-picker-month="1" aria-label="Next Month" ${year===9999&&month===12?'disabled':''}>›</button></header><div class="calendar-picker-weekdays" aria-hidden="true">${'SMTWTFS'.split('').map(day=>'<span>'+day+'</span>').join('')}</div><div class="calendar-picker-days">${Array.from({length:count},(_,index)=>{
   const day=new Date(first);day.setUTCDate(index-offset+1);if(day.getUTCFullYear()<1||day.getUTCFullYear()>9999)return '<span></span>';
   const iso=day.toISOString().slice(0,10),label=day.toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric',timeZone:'UTC'});
   return `<button type="button" data-picker-date="${iso}" aria-label="${label}" aria-selected="${iso===group.dataset.date}" ${iso===calendarDateKey(new Date())?'aria-current="date"':''} class="${day.getUTCMonth()+1===month?'':'other-month'}">${day.getUTCDate()}</button>`;
  }).join('')}</div>`;
  panel.querySelectorAll('[data-picker-month]').forEach(button=>button.onclick=()=>{first.setUTCMonth(first.getUTCMonth()+Number(button.dataset.pickerMonth));group._pickerMonth=first.toISOString().slice(0,7);render();panel.querySelector('[data-picker-month="'+button.dataset.pickerMonth+'"]').focus()});
  panel.querySelectorAll('[data-picker-date]').forEach(button=>{
   button.onclick=()=>{setCalendarSegmentDate(group,button.dataset.pickerDate);group._pickerMonth=button.dataset.pickerDate.slice(0,7);closeCalendarDatePicker(true)};
   button.onkeydown=event=>{
    const delta={ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7}[event.key];if(delta===undefined)return;
    event.preventDefault();const day=new Date(button.dataset.pickerDate+'T12:00:00Z');day.setUTCDate(day.getUTCDate()+delta);
    if(day.getUTCFullYear()<1||day.getUTCFullYear()>9999)return;
    const iso=day.toISOString().slice(0,10);group._pickerMonth=iso.slice(0,7);render(iso);
   };
  });
  if(focusDate)panel.querySelector('[data-picker-date="'+focusDate+'"]')?.focus();
 }
 render(focus?group.dataset.date:null);
}
document.addEventListener('pointerdown',event=>{const panel=document.querySelector('.calendar-date-picker');if(panel&&!panel.contains(event.target)&&!panel._group.contains(event.target))closeCalendarDatePicker()},true);
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.querySelector('.calendar-date-picker')){event.preventDefault();event.stopPropagation();closeCalendarDatePicker(true)}},true);
