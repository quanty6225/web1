import {condition,readPath} from './filter-expression.js';
const periods=[['1 day','P1D'],['3 days','P3D'],['1 week','P1W'],['1 month','P1M'],['3 months','P3M'],['6 months','P6M'],['1 year','P1Y']];
export function dateFilterFields(){
 return [['Due date','dueDate'],['Created date','createdAt'],['Updated date','updatedAt'],['Started date','startedAt'],['Completed date','completedAt'],['Auto-closed date','autoClosedAt'],['Triaged date','triagedAt'],['Time in current status','accumulatedStateUpdatedAt']].map(([label,key])=>{
  const due=key==='dueDate',elapsed=key==='accumulatedStateUpdatedAt',operator=due||elapsed?'lte':'gte';
  const choices=elapsed?[['1 day','P1D'],['1 week','P1W'],['2 weeks','P2W'],['1 month','P1M'],['3 months','P3M'],['6 months','P6M']]:due?periods.slice(0,5):periods;
  const options=choices.map(([text,value])=>({label:text+(elapsed?'':due?' from now':' ago'),value:(due?'':'-')+value,operator}));
  if(due)options.unshift({label:'Overdue',value:'P0D',operator:'lt'});
  if(due)options.push({label:'No due date',value:true,operator:'null'});
  const field={label,key,path:[key],menuGroup:'Dates',type:'date',defaultOperator:operator,options,custom:!elapsed,
   read(node){const value=readPath(node,[key]);return value&&Object.keys(value).length>1?{range:value}:value;},
   build(op,value){return {[key]:op==='range'?value:{[op]:value}};},
   operatorLabel(op){return op==='range'?'in':op==='null'?'is':op==='lt'||op==='lte'?'before':'after';},
   format(value,op){if(op==='range')return value.gte+' – '+value.lt;return options.find(x=>x.value===value&&x.operator===op)?.label??options.find(x=>x.value===value)?.label??String(value);},
   operatorsFor(op){return op==='range'?['range']:op==='null'?['null']:['gte','lte'];}
  };return field;
 });
}
const months=Array.from({length:12},(_,m)=>new Date(2026,m,1).toLocaleString('en-US',{month:'long'}));
const dateString=d=>[d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');
export function parseFilterPeriod(text,year=new Date().getFullYear()){
 let d,precision='day',match;const value=text.trim();
 if((match=/^(\d{4})-(\d{2})-(\d{2})$/.exec(value))){d=new Date(+match[1],+match[2]-1,+match[3]);if(dateString(d)!==value)d=null;}
 else if((match=/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(value))){d=new Date(+match[3],+match[1]-1,+match[2]);if(d.getFullYear()!==+match[3]||d.getMonth()!==+match[1]-1||d.getDate()!==+match[2])d=null;}
 else if((match=/^Q([1-4])(?:\s+(\d{4}))?$/i.exec(value))){d=new Date(+(match[2]||year),(+match[1]-1)*3,1);precision='quarter';}
 else if((match=/^H([12])(?:\s+(\d{4}))?$/i.exec(value))){d=new Date(+(match[2]||year),(+match[1]-1)*6,1);precision='half-year';}
 else if(/^\d{4}$/.test(value)){d=new Date(+value,0,1);precision='year';}
 else if((match=/^([a-z]+)\s+(\d{4})$/i.exec(value))){const month=months.findIndex(m=>m.toLowerCase().startsWith(match[1].toLowerCase()));if(month>=0){d=new Date(+match[2],month,1);precision='month';}}
 if(!d||Number.isNaN(+d))throw Error('Enter a valid date.');return {date:dateString(d),precision};
}
export function periodFilterValue(date,precision,operator='gte'){
 const start=new Date(date+'T12:00:00'),months={month:1,quarter:3,'half-year':6,year:12}[precision];
 if(!months)return {[operator]:date};
 const end=new Date(start.getFullYear(),start.getMonth()+months,1);return {gte:date,lt:dateString(end)};
}
export function openFilterDatePicker({field,modal,closeDialog,onPick}){
 let focus=new Date(),precision='day',selection=null,input;
 const root=modal(field.label,'<input name="date" aria-label="'+field.label+'" placeholder="Try: May 2027, Q4, 05/20/2027"><div class="local-project-date-modes" role="tablist"></div><div data-filter-calendar></div>','Apply',async()=>{
  const chosen=input.value.trim()?parseFilterPeriod(input.value,focus.getFullYear()):selection;
  if(!chosen)throw Error('Enter a valid date.');await onPick(periodFilterValue(chosen.date,chosen.precision,field.defaultOperator));closeDialog();
 },true);
 input=root.querySelector('input[name=date]');const modes=root.querySelector('[role=tablist]'),calendar=root.querySelector('[data-filter-calendar]');
 function choose(date,p=precision){selection={date:dateString(date),precision:p};input.value=p==='day'?selection.date:p==='month'?months[date.getMonth()]+' '+date.getFullYear():p==='quarter'?'Q'+(Math.floor(date.getMonth()/3)+1)+' '+date.getFullYear():p==='half-year'?'H'+(Math.floor(date.getMonth()/6)+1)+' '+date.getFullYear():String(date.getFullYear());paint();}
 function paint(){
  modes.replaceChildren();for(const p of ['day','month','quarter','half-year','year']){const button=document.createElement('button');button.type='button';button.role='tab';button.textContent=p[0].toUpperCase()+p.slice(1);button.setAttribute('aria-selected',String(p===precision));button.onclick=()=>{precision=p;paint();};modes.append(button);}
  calendar.replaceChildren();calendar.className='';
  const add=(grid,text,date)=>{const b=document.createElement('button');b.type='button';b.textContent=text;b.setAttribute('aria-label',dateString(date));b.setAttribute('aria-pressed',String(selection?.date===dateString(date)&&selection?.precision===precision));b.onclick=()=>choose(date);grid.append(b);};
  if(precision==='day'){
   const nav=document.createElement('div');nav.className='local-project-calendar-nav';nav.innerHTML='<button type="button" aria-label="Previous month">‹</button><strong>'+months[focus.getMonth()]+' '+focus.getFullYear()+'</strong><button type="button" aria-label="Next month">›</button>';const buttons=nav.querySelectorAll('button');buttons[0].onclick=()=>{focus=new Date(focus.getFullYear(),focus.getMonth()-1,1);paint();};buttons[1].onclick=()=>{focus=new Date(focus.getFullYear(),focus.getMonth()+1,1);paint();};calendar.append(nav);
   const grid=document.createElement('div');grid.className='local-project-calendar-grid days';calendar.append(grid);for(const label of ['Su','Mo','Tu','We','Th','Fr','Sa']){const day=document.createElement('small');day.textContent=label;grid.append(day);}const first=new Date(focus.getFullYear(),focus.getMonth(),1).getDay();for(let i=0;i<42;i++){const date=new Date(focus.getFullYear(),focus.getMonth(),i-first+1);add(grid,date.getDate(),date);}
  }else{
   calendar.className='local-project-year-groups';const current=new Date().getFullYear();for(let year=current-4;year<=current+5;year++){const section=document.createElement('section'),title=document.createElement('strong');title.textContent=year;section.append(title);const grid=document.createElement('div');grid.className='local-project-calendar-grid periods';section.append(grid);calendar.append(section);if(precision==='month')for(let m=0;m<12;m++)add(grid,months[m].slice(0,3),new Date(year,m,1));else if(precision==='quarter')for(let m=0;m<4;m++)add(grid,'Q'+(m+1),new Date(year,m*3,1));else if(precision==='half-year')for(let m=0;m<2;m++)add(grid,'H'+(m+1),new Date(year,m*6,1));else add(grid,String(year),new Date(year,0,1));}
  }
 }
 paint();return root;
}
export function dateFilterMenu({anchor,field,value,menu,modal,closeDialog,onPick}){
 const choices=field.options.map(option=>({text:option.label,action:()=>onPick({[option.operator]:option.value})}));
 if(field.custom)choices.splice(field.key==='dueDate'?choices.length-1:choices.length,0,{text:'Custom date or timeframe…',action:()=>openFilterDatePicker({field,modal,closeDialog,onPick})});
 return menu(anchor,choices);
}
