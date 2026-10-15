function moduleMenu(button){
 if(!scenario)return;const id=button.dataset.id,m=scenario.graph.find(item=>item.id===id);if(!m)return;
 const def=mods.find(item=>item.type===m.type),canClone=!['filter','basic-trigger','webhook'].includes(m.type)&&scenario.graph.length<50;
 const box=button.getBoundingClientRect();
 $('#overlay').innerHTML=`<div class="module-context-menu" role="menu" aria-label="${esc(def.name)} actions" style="left:${Math.max(8,Math.min(box.right+10,innerWidth-210))}px;top:${Math.max(8,Math.min(box.top,innerHeight-180))}px"><button role="menuitem" data-module-command="configure" data-id="${id}">Settings</button><button role="menuitem" data-module-command="clone" data-id="${id}" ${canClone?'':'disabled'}>Clone</button><button role="menuitem" data-module-command="delete" data-id="${id}" class="danger">Delete module</button></div>`;
 const menu=$('.module-context-menu');menu.querySelector('button').focus();
 menu.addEventListener('keydown',event=>{const buttons=[...menu.querySelectorAll('button:not(:disabled)')];const i=buttons.indexOf(document.activeElement);if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:(i+(event.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length;buttons[next].focus();}if(event.key==='Escape'){event.stopPropagation();close();button.focus();}});
 menu.querySelectorAll('[data-module-command]').forEach(control=>control.onclick=async()=>{try{
  const command=control.dataset.moduleCommand;close();
  if(command==='configure'){await configure(id);return;}
  const index=scenario.graph.findIndex(item=>item.id===id);if(index<0)return;
  if(command==='clone'){if(!canClone)return;snapshot();scenario.graph.splice(index+1,0,{...structuredClone(m),id:crypto.randomUUID()});drawEditor();toast('Module cloned');}
  else{snapshot();scenario.graph.splice(index,1);drawEditor();toast('Module deleted');}
 }catch(err){toast(err.message);}});
}
document.addEventListener('contextmenu',event=>{const button=event.target.closest('.module-circle[data-action="configure"]');if(button){event.preventDefault();moduleMenu(button);}});
document.addEventListener('keydown',event=>{if((event.shiftKey&&event.key==='F10')||event.key==='ContextMenu'){const button=event.target.closest('.module-circle[data-action="configure"]');if(button){event.preventDefault();moduleMenu(button);}}});
document.addEventListener('pointerdown',event=>{if($('.module-context-menu')&&!event.target.closest('.module-context-menu'))close();});
function importBlueprintDialog(){
 modal('Import blueprint','<form id="blueprint-import-form" class="config-form"><label for="blueprint-file">Blueprint JSON file</label><input id="blueprint-file" type="file" accept="application/json,.json"><p class="muted">Import replaces the modules in this editor. Review the file before applying it, then save the scenario to keep your changes.</p><div id="blueprint-preview" role="status"></div><p id="blueprint-error" class="error" role="alert"></p><div class="form-actions"><button type="button" data-action="close">Cancel</button><button class="primary" id="blueprint-apply" disabled>Import</button></div></form>');
 let candidate=null,revision=0;const expectedScenario=scenario,importForm=$('#blueprint-import-form');
 $('#blueprint-file').onchange=async event=>{
  const current=++revision;candidate=null;$('#blueprint-apply').disabled=true;$('#blueprint-error').textContent='';$('#blueprint-preview').textContent='';
  try{const file=event.target.files[0];if(!file)return;if(file.size>250000)throw Error('Blueprint must be smaller than 250 KB');const parsed=JSON.parse(await file.text());const result=await api('/blueprints/validate','POST',parsed);if(current!==revision||!importForm.isConnected)return;candidate=result;$('#blueprint-preview').textContent=`${result.name} — ${result.graph.length} module${result.graph.length===1?'':'s'}`;$('#blueprint-apply').disabled=false;}
  catch(err){if(current===revision&&importForm.isConnected)$('#blueprint-error').textContent=err.message;}
 };
 $('#blueprint-import-form').onsubmit=event=>{event.preventDefault();if(!candidate||scenario!==expectedScenario)return;snapshot();scenario.graph=structuredClone(candidate.graph);scenario.name=candidate.name;close();drawEditor();toast('Blueprint imported. Save to keep your changes.');};
}

async function configureJSONCreate(id,draft=null){
 const module=scenario.graph.find(item=>item.id===id);if(!module)return;
 const structures=await api('/resources/udts');let config=structuredClone(draft||module.config),currentStructure=config.structure||'';
 function valueObject(){try{const value=typeof config.value==='string'?JSON.parse(config.value):config.value;return value&&typeof value==='object'&&!Array.isArray(value)?value:{};}catch{return {};}}
 let values=valueObject();
 modal('JSON — Create JSON',`<form id="module-form" class="config-form"><label for="json-structure">Data structure</label><div class="json-structure-select"><select id="json-structure"><option value="">JSON input</option>${currentStructure&&!structures.some(s=>s.id===currentStructure)?`<option value="${esc(currentStructure)}" selected>Unavailable data structure</option>`:''}${structures.map(s=>`<option value="${s.id}" ${s.id===currentStructure?'selected':''}>${esc(s.name)}</option>`).join('')}</select><button type="button" id="json-add-structure">Add</button></div><div id="json-structured-fields"></div><div id="json-manual-fields"><label for="field-value">JSON data (optional)</label><textarea id="field-value">${esc(typeof config.value==='string'?config.value:config.value===undefined?'':JSON.stringify(config.value,null,2))}</textarea><p class="muted">Map values with {{data.field}}. Leave empty to serialize the current bundle.</p></div><label for="field-indent">Indentation</label><select id="field-indent">${['compact','2 spaces','4 spaces'].map(value=>`<option ${config.indent===value?'selected':''}>${value}</option>`).join('')}</select><div id="json-config-error" class="error" role="alert"></div><div class="form-actions"><button type="button" class="danger" data-action="delete-module" data-id="${id}">Delete module</button><button type="button" data-action="close">Cancel</button><button class="primary">Save</button></div></form>`);
 function readFields(){
  const result={};for(const input of $$('#json-structured-fields [data-json-field]')){
   const field=input.dataset.jsonField,type=input.dataset.jsonType,text=input.value;
   if(text===''&&!input.required)continue;
   if(/^\{\{\s*[\w.]+\s*\}\}$/.test(text)){Object.defineProperty(result,field,{value:text,enumerable:true,writable:true,configurable:true});continue;}
   let value=text;
   if(['number','integer'].includes(type)){if(!text.trim()||!Number.isFinite(Number(text))||(type==='integer'&&!Number.isInteger(Number(text))))throw Error('Enter a valid '+type+' for '+field);value=Number(text);}
   else if(type==='boolean'){if(text!=='true'&&text!=='false')throw Error('Enter true, false or a mapped value for '+field);value=text==='true';}
   else if(type==='object'||type==='array'||type==='null'){try{value=JSON.parse(text);}catch{throw Error('Enter valid JSON for '+field);}if(type==='array'&&!Array.isArray(value)||type==='object'&&(!value||typeof value!=='object'||Array.isArray(value))||type==='null'&&value!==null)throw Error('Enter a JSON '+type+' for '+field);}
   Object.defineProperty(result,field,{value,enumerable:true,writable:true,configurable:true});
  }return result;
 }
 function showFields(){
  const structure=structures.find(s=>s.id===currentStructure),schema=structure?.config.schema||{},properties=schema.properties||{};
  $('#json-manual-fields').hidden=!!currentStructure;$('#field-value').disabled=!!currentStructure;
  $('#json-structured-fields').innerHTML=currentStructure?(structure?Object.entries(properties).map(([field,spec],index)=>{const type=spec?.type||'string',value=Object.hasOwn(values,field)?values[field]:undefined,display=typeof value==='string'?value:value===undefined?'':JSON.stringify(value),required=Array.isArray(schema.required)&&schema.required.includes(field);return `<label for="json-property-${index}">${esc(spec?.title||field)}${required?' *':''}</label>${['object','array'].includes(type)?`<textarea id="json-property-${index}" data-json-field="${esc(field)}" data-json-type="${esc(type)}" ${required?'required':''}>${esc(display)}</textarea>`:`<input id="json-property-${index}" data-json-field="${esc(field)}" data-json-type="${esc(type)}" value="${esc(display)}" ${required?'required':''}>`}<small class="muted">${esc(type)} · ${esc(field)}</small>`;}).join('')+'<p class="muted">Exact mappings such as {{data.count}} keep the original type. The server checks the selected structure when the scenario runs.</p>':'<p class="error">This data structure is no longer available. Choose another structure or JSON input.</p>'):'';
 }
 $('#json-structure').onchange=()=>{try{if(currentStructure)values=readFields();else{config.value=$('#field-value').value;values=valueObject();}if(currentStructure&&!$('#json-structure').value)$('#field-value').value=JSON.stringify(values,null,2);currentStructure=$('#json-structure').value;$('#json-config-error').textContent='';showFields();}catch(err){$('#json-structure').value=currentStructure;$('#json-config-error').textContent=err.message;}};
 $('#json-add-structure').onclick=async()=>{try{config={structure:currentStructure,value:currentStructure?readFields():$('#field-value').value,indent:$('#field-indent').value};await resourceAdd('udts',created=>configureJSONCreate(id,{...config,structure:created.id}));}catch(err){$('#json-config-error').textContent=err.message;}};
 $('#module-form').onsubmit=event=>{event.preventDefault();try{if(currentStructure&&!structures.some(s=>s.id===currentStructure))throw Error('Select an available data structure');const saved={structure:currentStructure,value:currentStructure?readFields():$('#field-value').value,indent:$('#field-indent').value};snapshot();module.config=saved;close();drawEditor();}catch(err){$('#json-config-error').textContent=err.message;}};
 showFields();
}
