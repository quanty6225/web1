const $=(q,r=document)=>r.querySelector(q);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const formTypes={text:'Text',long_text:'Long text',dropdown:'Dropdown',checkboxes:'Checkboxes',date:'Date',upload:'Upload file',instructions:'Instructions',title:'Title',label_group:'Label group',priority:'Priority',due_date:'Due date'};
const groups=state=>[...(state.label_groups||[]),...(state.labels||[]).filter(x=>x.is_group)].filter(x=>!x.archived);
const choices=(state,group,team)=>(state.labels||[]).filter(x=>x.group===group&&!x.is_group&&!x.archived&&(!team||!x.team||x.team===team));
export function createFormFields({get,set,menu,getState,getTeam=()=>null}){
 const root=document.createElement('section');root.dataset.formFields='';root.className='issue-form-fields';const add=$('main button[aria-label="Add field"]');const holder=add.closest('li');if(holder)holder.prepend(root);else add.before(root);
 // The captured empty-state animation has a fixed height; live fields must grow.
 for(let node=root.parentElement;node&&node.tagName!=='MAIN';node=node.parentElement)if(node.style.height&&node.style.overflow==='inherit')node.style.height='auto';
 const empty=[...document.querySelectorAll('main *')].find(e=>!e.children.length&&e.textContent.trim()==='No fields added yet');
 function draw(){root.replaceChildren();if(empty)empty.hidden=!!get().length;
  get().forEach((field,index)=>{const box=document.createElement('fieldset');box.dataset.formField=field.id;box.innerHTML='<div class="issue-field-tools"><button type="button" data-field-type>'+esc(formTypes[field.type])+'</button><label><input type="checkbox" aria-label="Required" '+(field.required?'checked':'')+'> Required</label><button type="button" data-field-up aria-label="Move field up" '+(index?'':'disabled')+'>↑</button><button type="button" data-field-down aria-label="Move field down" '+(index===get().length-1?'disabled':'')+'>↓</button><button type="button" data-field-remove aria-label="Remove field">×</button></div><textarea data-field-label aria-label="Field label" placeholder="Add label…">'+esc(field.label)+'</textarea><textarea data-field-description aria-label="Field description" placeholder="Add description…">'+esc(field.description)+'</textarea><div data-field-options></div>';
   const update=value=>{const fields=[...get()];fields[index]={...fields[index],...value};set(fields);};$('[data-field-label]',box).oninput=e=>update({label:e.target.value});$('[data-field-description]',box).oninput=e=>update({description:e.target.value});$('[aria-label=Required]',box).onchange=e=>update({required:e.target.checked});
   $('[data-field-type]',box).onclick=e=>{e.stopPropagation();typeMenu(e.currentTarget,index,value=>{update(value);draw();});};
   $('[data-field-remove]',box).onclick=e=>{e.stopPropagation();set(get().filter((_,i)=>i!==index));draw();};
   for(const [key,offset]of [['up',-1],['down',1]])$('[data-field-'+key+']',box).onclick=e=>{e.stopPropagation();const values=[...get()];[values[index],values[index+offset]]=[values[index+offset],values[index]];set(values);draw();};
   if(['dropdown','checkboxes'].includes(field.type)){const options=$('[data-field-options]',box);(field.options||[]).forEach((value,n)=>{const row=document.createElement('div');row.className='issue-field-tools';const input=document.createElement('input');input.value=value;input.placeholder='Add option…';input.setAttribute('aria-label','Option '+(n+1));input.oninput=()=>{const choices=[...(get()[index].options||[])];choices[n]=input.value;update({options:choices});};const remove=document.createElement('button');remove.type='button';remove.textContent='×';remove.setAttribute('aria-label','Remove option '+(n+1));remove.onclick=e=>{e.stopPropagation();update({options:get()[index].options.filter((_,i)=>i!==n)});draw();};row.append(input,remove);options.append(row);});const button=document.createElement('button');button.type='button';button.textContent='Add option';button.onclick=e=>{e.stopPropagation();update({options:[...(get()[index].options||[]),'']});draw();$('[data-form-field="'+field.id+'"] [data-field-options] input:last-of-type',root)?.focus();};options.append(button);}
   if(field.type==='label_group'){
    const options=$('[data-field-options]',box),select=document.createElement('select');select.setAttribute('aria-label','Label group');select.innerHTML='<option value="">Select a label group</option>'+availableGroups(index).map(g=>'<option value="'+esc(g.id)+'">'+esc(g.title)+'</option>').join('');select.value=field.label_group_id||'';select.onchange=()=>{update({label_group_id:select.value});draw();};options.append(select);
    const preview=document.createElement('p');preview.className='issue-form-help';preview.textContent=choices(getState(),field.label_group_id,getTeam()).map(x=>x.title).join(', ')||'No labels in this group';options.append(preview);
   }
   root.append(box);
  });
 }
 function availableGroups(index){return groups(getState()).filter(g=>(!getTeam()||!g.team||g.team===getTeam())&&!get().some((f,i)=>i!==index&&f.type==='label_group'&&f.label_group_id===g.id));}
 function typeMenu(anchor,index,choose){menu(anchor,Object.entries(formTypes).map(([type,text])=>({text,action:()=>{
  if(type==='label_group'){const available=availableGroups(index);const picker=menu(anchor,available.map(g=>({text:g.title,action:()=>choose({type,label:g.title,label_group_id:g.id,options:[]})})));if(!available.length){const empty=document.createElement('p');empty.textContent='No label groups remaining';picker.append(empty);}return;}
  choose({type,options:[],label_group_id:null});
 }})));}
 function addField(anchor){typeMenu(anchor,-1,value=>{set([...get(),{id:'field_'+crypto.randomUUID().replaceAll('-',''),label:['title','priority','due_date'].includes(value.type)?formTypes[value.type]:'',description:'',required:false,...value}]);draw();$('[data-form-field]:last-child [data-field-label]',root)?.focus();});}
 draw();return{add:addField,draw};
}
export function mountIssueForm({overlay,template,answers={},attachments,getState=()=>({})}){
 let values={...answers};const title=$('[name=title]',overlay),hasTitle=template?.form_fields?.some(f=>f.type==='title');if(title&&hasTitle){title.hidden=true;title.required=false;}const root=document.createElement('section');root.dataset.issueFormAnswers='';root.className='issue-form-fields';$('.dialog-body',overlay).append(root);const fileFields=[];
 for(const field of template?.form_fields||[]){const box=document.createElement('div');box.dataset.answerField=field.id;const label=document.createElement('label');label.textContent=field.label+(field.required?' *':'');const help=document.createElement('p');help.textContent=field.description;help.className='issue-form-help';box.append(label,help);root.append(box);if(field.type==='instructions')continue;
  const update=value=>{values[field.id]=value;overlay.dispatchEvent(new Event('input'));};
  if(field.type==='upload'){const holder=document.createElement('div');holder.innerHTML='<textarea name="description" hidden></textarea>';box.append(holder);const files=attachments?.mountDraft(holder,values[field.id]||[]);$('[name=description]',holder)?.removeAttribute('name');fileFields.push([field.id,files]);continue;}
  if(field.type==='checkboxes'){for(const option of field.options){const row=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.checked=(values[field.id]||[]).includes(option);input.setAttribute('aria-label',field.label+': '+option);input.onchange=()=>{const selected=new Set(values[field.id]||[]);input.checked?selected.add(option):selected.delete(option);update([...selected]);};row.append(input,document.createTextNode(option));box.append(row);}continue;}
  const input=document.createElement(['dropdown','priority','label_group'].includes(field.type)?'select':field.type==='long_text'?'textarea':'input');input.setAttribute('aria-label',field.label);input.required=field.required;if(['date','due_date'].includes(field.type))input.type='date';
  if(field.type==='label_group'){
   const state=getState(),team=template.team||document.body.dataset.activeTeam||'QQQ',group=groups(state).find(g=>g.id===field.label_group_id&&(!g.team||g.team===team)),labels=group?choices(state,group.id,team):[];
   input.innerHTML='<option value="">Select a label</option>'+labels.map(l=>'<option value="'+esc(l.id)+'">'+esc(l.title)+'</option>').join('');if(!labels.some(l=>l.id===values[field.id]))delete values[field.id];if(!labels.length)help.textContent=[field.description,'No labels available in this group'].filter(Boolean).join(' · ');
  }else if(input.tagName==='SELECT'){const options=field.type==='priority'?['No priority','Urgent','High','Medium','Low']:field.options;input.innerHTML='<option value="">Select an option</option>'+options.map(value=>'<option>'+esc(value)+'</option>').join('');}else input.placeholder=field.type==='long_text'?'Enter text…':'Enter text';
  input.value=values[field.id]||'';input.oninput=()=>update(input.value);label.append(input);
 }
 return{answers:()=>{for(const [key,files]of fileFields)values[key]=files?.files()||[];return{...values};},pending:()=>fileFields.some(([,files])=>files?.pending()),remove:()=>{root.remove();if(title){title.hidden=false;title.required=true;}}};
}
