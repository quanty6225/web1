let calendarGeneration;
async function calendarArchives(){
 const state=await api('/api/calendars/archives');
 showDialog('Restore Calendars',state.archives.length?'<div class="contact-archives">'+state.archives.map(version=>`<div class="contact-archive-row"><time datetime="${new Date(version.created_at).toISOString()}">${esc(new Date(version.created_at).toLocaleString())}</time><button data-calendar-archive="choose" data-id="${esc(version.id)}" data-generation="${state.generation}">Restore</button></div>`).join('')+'</div><button data-action="close">Done</button>':'<p>No Archives Available</p><button data-action="close">Done</button>');
}
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-calendar-archive]');if(!button)return;
 const id=button.dataset.id,generation=button.dataset.generation;
 if(button.dataset.calendarArchive==='choose'){
  showDialog('Restore Calendars and Reminders',`<p>Your current calendars, events, reminders, and reminder lists will be archived before this version is restored.</p><p>All sharing information will be removed. Share your lists again and ask other people to reinvite you.</p><p>Wait until the restore is complete before making changes.</p><div class="error" role="alert"></div><button data-action="close">Cancel</button><button data-calendar-archive="confirm" data-id="${esc(id)}" data-generation="${esc(generation)}">Restore</button>`);return;
 }
 if(button.dataset.calendarArchive==='confirm'){
  modal.querySelectorAll('button').forEach(b=>b.disabled=true);
  try{
   const result=await api('/api/calendars/restore',{id},'POST',{'X-Calendar-Generation':generation});
   calendarGeneration=result.generation;
   showDialog('Restore Complete','<p>Your calendars and reminders have been restored.</p><a href="/calendar/">Go to Calendar</a><a href="/reminders/">Go to Reminders</a><button data-action="close">Done</button>');
  }catch(error){modal.querySelector('.error').textContent=error.message;modal.querySelectorAll('button').forEach(b=>b.disabled=false)}
 }
});
