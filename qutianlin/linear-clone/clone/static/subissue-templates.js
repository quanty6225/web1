const $=(selector,root=document)=>root.querySelector(selector);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function subissueTemplates({get,set,getState,getAccount,modal,closeDialog,menu,attachments}){
 const root=document.createElement('section');root.dataset.subissueTemplates='';root.className='issue-subissues';
 function edit(index=null){
  const item=index===null?{title:'',description:'',status:'Backlog',priority:'No priority',assignee:null,labels:[]}:get()[index];
  const options=(values,current)=>values.map(([label,value])=>'<option value="'+esc(value)+'" '+(current===value?'selected':'')+'>'+esc(label)+'</option>').join('');
  const overlay=modal(index===null?'Create sub-issue':'Edit sub-issue','<input name="title" aria-label="Sub-issue title" class="issue-title" placeholder="Issue title" value="'+esc(item.title)+'" required><textarea name="description" aria-label="Sub-issue description" class="issue-description" placeholder="Add description…">'+esc(item.description)+'</textarea><div class="row"><select name="status" aria-label="Sub-issue status">'+options(getState().workflow_states.map(s=>[s.title,s.title]),item.status)+'</select><select name="priority" aria-label="Sub-issue priority">'+options(['No priority','Urgent','High','Medium','Low'].map(p=>[p,p]),item.priority)+'</select><select name="assignee" aria-label="Sub-issue assignee">'+options([['Assignee',''],[getAccount().display_name,getAccount().email_normalized]],item.assignee||'')+'</select></div><label>Labels<select name="labels" multiple aria-label="Sub-issue labels">'+getState().labels.map(l=>'<option '+(item.labels?.includes(l.title)?'selected':'')+'>'+esc(l.title)+'</option>').join('')+'</select></label>'+(index===null?'<label><input type="checkbox" name="more"> Create more</label>':''),index===null?'Add sub-issue':'Save sub-issue',async form=>{
   if(files?.pending())throw Error('Wait for the upload to finish.');const value={...item,title:form.get('title').trim(),description:form.get('description'),status:form.get('status'),priority:form.get('priority'),assignee:form.get('assignee')||null,labels:form.getAll('labels'),attachments:files?.files()||[]},items=[...get()];if(index===null)items.push(value);else items[index]=value;set(items);draw();const more=form.has('more');closeDialog();if(more)edit();
  });const files=attachments?.mountDraft(overlay,item.attachments||[]);
 }
 function draw(){root.replaceChildren();if(!get().length)return;const title=document.createElement('h3');title.textContent='Sub-issues';root.append(title);
  get().forEach((item,index)=>{const row=document.createElement('div');row.className='issue-relation-row';const button=document.createElement('button');button.type='button';button.textContent=item.title;button.onclick=e=>{e.stopPropagation();edit(index);};const remove=document.createElement('button');remove.type='button';remove.textContent='×';remove.setAttribute('aria-label','Remove sub-issue '+item.title);remove.onclick=e=>{e.stopPropagation();set(get().filter((_,i)=>i!==index));draw();};row.append(button,remove);root.append(row);});
 }
 const anchor=$('main [aria-label="Issue description"]')||$('main [aria-label="Template description"]');anchor?.parentElement.after(root);draw();
 return{add:()=>edit(),draw};
}
