let reminderContext=null,reminderWrites=Promise.resolve();
function reminderQuery(change){const query=new URLSearchParams(location.search);for(const [key,value] of Object.entries(change))value?query.set(key,value):query.delete(key);history.replaceState(null,'',location.pathname+(query.size?'?'+query:''))}
async function remindersPage(){
 stopReminderSharingPoll();
 const [lists,reminders]=await Promise.all([items('lists'),items('reminders')]);
 const query=new URLSearchParams(location.search),scheduled=location.pathname.includes('scheduled'),list=lists.find(l=>l.id===query.get('list'))||lists[0]||null;
 activeEntity=list;reminderContext={lists,reminders,list,scheduled,query:query.get('q')||'',showCompleted:query.get('completed')==='1'};
 const side='<h2>Reminders</h2><div class="reminder-search"><input type="search" id="reminder-search" placeholder="Search all reminders" aria-label="Search all reminders" value="'+esc(reminderContext.query)+'"><button id="clear-reminder-search" aria-label="Clear search" '+(!reminderContext.query?'hidden':'')+'>×</button></div><a href="/reminders/scheduled/" '+(scheduled?'class="active"':'')+'>Scheduled</a>'+lists.map(l=>`<div class="reminder-sidebar-list"><a href="/reminders/?list=${encodeURIComponent(l.id)}" class="${!scheduled&&list?.id===l.id?'active':''}"><span class="reminder-list-color" style="background:${esc(l.color)}"></span>${esc(l.name)} <span>${l._sharing&&!l._sharing.accepted?'Invited':reminders.filter(r=>r.list===l.id&&!r.completed).length}</span></a><button data-reminder-share="manage" data-list="${esc(l.id)}" aria-label="${l._sharing?'Participants for':'Share'} ${esc(l.name)}">♧</button></div>`).join('')+'<button data-reminder-action="new-list" data-op="new-list">＋ New Reminder List</button><button data-reminder-action="notifications">Notification Settings</button>';
 appFrame('Reminders',side,`<section class="reminder-content"><div class="reminder-heading"><h1 style="color:${esc(list?.color||'#e7763b')}">${esc(scheduled?'Scheduled':list?.name||'Reminders')}</h1>${!scheduled&&list&&(!list._sharing||list._sharing.owner)?'<button data-reminder-action="options" aria-label="Options">Options</button>':''}</div><div id="reminder-list"></div><button data-reminder-action="new" data-op="new-reminder" ${reminderWritableLists().length&&(!list?._sharing||list._sharing.accepted)?'':'disabled'}>＋ New Item...</button></section>`);
 const search=document.querySelector('#reminder-search');search.oninput=()=>{reminderContext.query=search.value;reminderQuery({q:search.value});renderReminders()};
 document.querySelector('#clear-reminder-search').onclick=()=>{search.value='';reminderContext.query='';reminderQuery({q:''});renderReminders();search.focus()};if(list?._sharing&&!list._sharing.accepted&&!scheduled&&!reminderContext.query){await reminderInvitationContent(list._sharing.id,document.querySelector('#reminder-list'))}else renderReminders();startReminderSharingPoll();
}
function reminderScope(){
 const c=reminderContext,q=c.query.trim().toLocaleLowerCase();
 return c.reminders.filter(r=>q?r.title.toLocaleLowerCase().includes(q):c.scheduled?!!r.due:r.list===c.list?.id).sort((a,b)=>c.scheduled&&!q?(a.due+' '+(a.due_time||'')).localeCompare(b.due+' '+(b.due_time||''))||(a.order||0)-(b.order||0):(a.order||0)-(b.order||0));
}
function renderReminders(){
 const c=reminderContext,list=reminderScope(),complete=list.filter(r=>r.completed),active=list.filter(r=>!r.completed),searching=!!c.query.trim(),show=c.showCompleted||searching;
 document.querySelector('#clear-reminder-search').hidden=!c.query;
 document.querySelector('.reminder-heading h1').textContent=searching?'Search Results':c.scheduled?'Scheduled':c.list?.name||'Reminders';
 const row=r=>`<div class="reminder-row" data-reminder-row="${esc(r.id)}" tabindex="0"><input type="checkbox" data-reminder-complete="${esc(r.id)}" ${r.completed?'checked':''} aria-label="${r.completed?'Mark not completed':'Complete'} ${esc(r.title)}"><div class="reminder-text"><input class="reminder-title ${r.completed?'completed':''}" data-reminder-title="${esc(r.id)}" aria-label="Reminder title: ${esc(r.title)}" value="${esc(r.title)}">${r.priority&&r.priority!=='None'?'<span class="reminder-priority" aria-label="'+esc(r.priority)+' priority">'+({Low:'!',Medium:'!!',High:'!!!'})[r.priority]+'</span>':''}${r.notes?'<small>'+esc(r.notes)+'</small>':''}${r.due?'<small>'+esc(r.due+' '+(r.due_time||''))+(r.repeat&&r.repeat!=='Never Repeat'?' · '+esc(r.repeat):'')+'</small>':''}${searching||c.scheduled?'<small>'+esc(c.lists.find(l=>l.id===r.list)?.name||'List unavailable')+'</small>':''}</div><button data-reminder-action="details" data-id="${esc(r.id)}" aria-label="Details for ${esc(r.title)}">ⓘ</button><button data-reminder-action="delete" data-id="${esc(r.id)}" aria-label="Delete ${esc(r.title)}">×</button></div>`;
 document.querySelector('#reminder-list').innerHTML=(!c.lists.length?'<h2>No Reminder Lists</h2>':'')+(complete.length?`<div class="completed-reminders-heading"><button data-reminder-action="completed" aria-expanded="${show}">${complete.length} Completed</button>${!searching&&!c.scheduled?'<button data-reminder-action="clear">Clear All</button>':''}</div>`:'')+active.map(row).join('')+(show?'<section aria-label="Completed reminders">'+complete.map(row).join('')+'</section>':'')+(!list.length?'<p class="hint">'+(searching?'No Results':'No Reminders')+'</p>':'');
 document.querySelectorAll('[data-reminder-complete]').forEach(input=>input.onchange=async()=>{input.disabled=true;try{await saveReminder(input.dataset.reminderComplete,{completed:input.checked})}catch(error){input.checked=!input.checked;reminderError(error)}finally{input.disabled=false}});
 document.querySelectorAll('[data-reminder-title]').forEach(input=>{
  const save=()=>{const original=reminderContext.reminders.find(r=>r.id===input.dataset.reminderTitle);return input.value===original?.title?Promise.resolve():saveReminder(input.dataset.reminderTitle,{title:input.value})};
  input.onchange=()=>save().catch(reminderError);
  input.onkeydown=async event=>{if(event.key==='Enter'){event.preventDefault();try{await save();beginReminder(input.dataset.reminderTitle)}catch(error){reminderError(error)}}};
 });
 document.querySelectorAll('[data-reminder-row]').forEach(row=>row.onkeydown=async event=>{if(!['Delete','Backspace'].includes(event.key)||event.target.matches('input,textarea,button,select'))return;event.preventDefault();try{await removeItem('reminders',row.dataset.reminderRow);await remindersPage()}catch(error){reminderError(error)}});
}
function reminderError(error){showDialog('Unable to Save Reminder','<p>'+esc(error.message)+'</p><button data-action="close">OK</button>')}
async function saveReminder(id,patch){
 const task=reminderWrites.catch(()=>{}).then(async()=>{const current=await api('/api/items/reminders/'+encodeURIComponent(id));const result=await storeItem('reminders',{...current,...patch});await remindersPage();return result});reminderWrites=task;return task;
}
function beginReminder(after){
 if(!reminderWritableLists().length||reminderContext.list?._sharing&&!reminderContext.list._sharing.accepted)return;
 document.querySelector('#new-reminder-form')?.remove();
 const previous=reminderContext.reminders.find(r=>r.id===after),list=previous?.list||reminderContext.list?.id||reminderWritableLists()[0].id;
 const form=document.createElement('form');form.id='new-reminder-form';form.className='reminder-row';form.innerHTML='<input name="title" aria-label="Reminder" placeholder="New Reminder" required autocomplete="off"><button type="submit">Add</button><button type="button" aria-label="Cancel new reminder">Cancel</button><span class="error" role="alert"></span>';
 if(reminderContext.scheduled){const now=new Date();if(now.getHours()>=23){now.setDate(now.getDate()+1);now.setHours(9,0)}else now.setHours(now.getHours()<17?17:now.getHours()+1,0);const day=now.getFullYear()+'-'+String(now.getMonth()+1).padStart(2,'0')+'-'+String(now.getDate()).padStart(2,'0');form.insertAdjacentHTML('beforeend',`<label>Date<input type="date" name="due" aria-label="Date" value="${day}" required></label><label>Time<input type="time" name="due_time" aria-label="Time" value="${String(now.getHours()).padStart(2,'0')}:00" required></label><label>List<select name="list" aria-label="List">${reminderWritableLists().map(l=>`<option value="${esc(l.id)}" ${l.id===list?'selected':''}>${esc(l.name)}</option>`).join('')}</select></label>`)}
 const anchor=[...document.querySelectorAll('[data-reminder-row]')].find(row=>row.dataset.reminderRow===after);if(anchor)anchor.after(form);else document.querySelector('#reminder-list').append(form);
 form.querySelector('[type=button]').onclick=()=>form.remove();form.onkeydown=event=>{if(event.key==='Escape'){event.preventDefault();form.remove()}};
 form.onsubmit=async event=>{event.preventDefault();const button=form.querySelector('[type=submit]'),data=Object.fromEntries(new FormData(form));const controls=[...form.querySelectorAll('input,select,button')];controls.forEach(control=>control.disabled=true);try{const value=await storeItem('reminders',{list,...data,completed:false,...(after?{after}:{})});await remindersPage();beginReminder(value.id)}catch(error){form.querySelector('.error').textContent=error.message}finally{controls.forEach(control=>control.disabled=false)}};form.querySelector('input').focus();
}
function editReminder(existing={}){
 if(!reminderWritableLists().length)return;
 formDialog('Reminder Details',field('title','Reminder',existing.title)+`<label>Notes<textarea name="notes" aria-label="Notes">${esc(existing.notes)}</textarea></label><label class="reminder-day-toggle"><input type="checkbox" name="on_day" ${existing.due?'checked':''}>On a day</label>`+field('due','Date',existing.due,'date')+field('due_time','Time',existing.due_time||'','time')+`<label>Repeat<select name="repeat" aria-label="Repeat">${['Never Repeat','Every Day','Every Week','Every 2 Weeks','Every Month','Every Year'].map(value=>`<option ${value===(existing.repeat||'Never Repeat')?'selected':''}>${value}</option>`).join('')}</select></label><label>Priority<select name="priority" aria-label="Priority">${['None','Low','Medium','High'].map(value=>`<option ${value===(existing.priority||'None')?'selected':''}>${value}</option>`).join('')}</select></label><label>List<select name="list" aria-label="List">${reminderWritableLists().map(l=>`<option value="${esc(l.id)}" ${l.id===(existing.list||reminderContext.list?.id)?'selected':''}>${esc(l.name)}</option>`).join('')}</select></label>`,async data=>{const on=data.on_day==='on';delete data.on_day;if(!on){data.due='';data.due_time='';data.repeat='Never Repeat'}await saveReminder(existing.id,data)},'<button type="button" data-reminder-action="delete" data-id="'+esc(existing.id)+'">Delete</button>');
 const toggle=()=>{const enabled=document.querySelector('[name=on_day]').checked;for(const name of ['due','due_time','repeat']){const input=document.querySelector('#edit-form [name='+name+']');input.disabled=!enabled;if(name==='due')input.required=enabled}};document.querySelector('[name=on_day]').onchange=toggle;toggle();
}
function editReminderList(list){formDialog(list?'Options':'New Reminder List',field('name','Name',list?.name)+field('color','Color',list?.color||'#ed7846','color'),async data=>{const saved=await storeItem('lists',{...list,...data});if(!list){history.replaceState(null,'','/reminders/?list='+encodeURIComponent(saved.id))}await remindersPage()},list?'<button type="button" data-reminder-action="delete-list">Delete List</button>':'')}
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-reminder-action]');if(!button)return;
 try{
  const action=button.dataset.reminderAction,id=button.dataset.id;
  if(action==='notifications')return reminderNotificationSettings();if(action==='new')return beginReminder();if(action==='details')return editReminder(reminderContext.reminders.find(r=>r.id===id));
  if(action==='new-list')return editReminderList();if(action==='options')return editReminderList(reminderContext.list);
  if(action==='delete'){await removeItem('reminders',id);if(modal.open)closeDialog();return remindersPage()}
  if(action==='completed'){reminderContext.showCompleted=!reminderContext.showCompleted;reminderQuery({completed:reminderContext.showCompleted?'1':''});renderReminders();return}
  if(action==='delete-list'){showDialog('Delete List?',`<p>All reminders in ${esc(reminderContext.list.name)} will also be deleted.</p><button data-action="close">Cancel</button><button data-reminder-action="confirm-delete-list">Delete</button>`);return}
  if(action==='confirm-delete-list'){await removeItem('lists',reminderContext.list.id);closeDialog();history.replaceState(null,'','/reminders/');return remindersPage()}
  if(action==='clear'){showDialog('Clear all completed reminders?','<p>All completed reminders will be permanently deleted. You cannot undo this action.</p><button data-action="close">Cancel</button><button data-reminder-action="confirm-clear">Clear All</button>');return}
  if(action==='confirm-clear'){await api('/api/reminders/clear-completed',{list:reminderContext.list.id});closeDialog();return remindersPage()}
 }catch(error){reminderError(error)}
});

async function reminderNotificationSettings(){
 const settings=await api('/api/reminder-preferences');
 formDialog('Notification Settings','<p>For reminders with a date and no time. Leave the time blank to turn off date-only notifications.</p><p>Time zone: '+esc(settings.timezone)+'</p>'+field('all_day_time','Date-only notification time',settings.all_day_time,'time'),async values=>{await api('/api/reminder-preferences',{all_day_time:values.all_day_time},'PUT');await alarmDelivery?.refresh()});
}
