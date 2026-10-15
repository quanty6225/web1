/* Files stay in their current application and account. */
function uploadDriveFile(){
 const input=document.createElement('input');input.type='file';input.multiple=true;
 const destination={app:driveContext.app,parent:driveParent(),path:location.pathname};
 input.onchange=async()=>{
  const files=[...input.files];if(!files.length)return;
  showDialog('Upload Files','<p role="status" id="upload-status">Uploading…</p><p class="error" role="alert"></p><button data-action="close" disabled>Done</button>');
  const dialog=modal,status=dialog.querySelector('#upload-status'),done=dialog.querySelector('button'),error=dialog.querySelector('.error');
  let completed=0;
  try{
   for(const file of files){
    status.textContent=`Uploading ${file.name} (${completed+1} of ${files.length})…`;
    if(!file.size||file.size>20*1024*1024)throw Error(`${file.name}: Choose a nonempty file smaller than 20 MB.`);
    const bytes=new Uint8Array(await file.arrayBuffer());let binary='';
    for(let n=0;n<bytes.length;n+=8192)binary+=String.fromCharCode(...bytes.subarray(n,n+8192));
    await api('/api/files/upload',{name:file.name,type:file.type||'application/octet-stream',content:btoa(binary),parent:destination.parent,...(destination.app?{app:destination.app}:{})});
    completed++;
   }
   status.textContent=`${completed} ${completed===1?'file':'files'} uploaded.`;
  }catch(failure){status.textContent=`${completed} of ${files.length} files uploaded.`;error.textContent=failure.message}
  finally{done.disabled=false;if(completed===files.length)closeDialog();if(location.pathname===destination.path)await documentPage(destination.path)}
 };
 input.click();
}

async function restoreFiles(){
 const groups=await Promise.all(['files','documents'].map(async kind=>({kind,records:(await items(kind)).filter(file=>file.deleted)})));
 const deleted=groups.flatMap(group=>group.records.map(file=>({...file,kind:group.kind})));
 showDialog('Restore Files',deleted.length?`<p>Select files to restore to their original locations.</p><label><input type="checkbox" id="restore-all-files"> Select All</label><div class="restore-file-list">${deleted.map(file=>`<label><input type="checkbox" data-restore-kind="${file.kind}" value="${esc(file.id)}"> ${esc(file.name)} <small>${esc(file.app||'iCloud Drive')}</small></label>`).join('')}</div><p class="error" role="alert"></p><div class="actions"><button data-action="close">Cancel</button><button id="restore-selected-files" class="primary" disabled>Restore</button></div>`:'<p>No Files to Restore</p><button data-action="close">Done</button>');
 if(!deleted.length)return;
 const checkboxes=[...modal.querySelectorAll('[data-restore-kind]')],all=modal.querySelector('#restore-all-files'),restore=modal.querySelector('#restore-selected-files');
 const update=()=>{restore.disabled=!checkboxes.some(input=>input.checked);all.checked=checkboxes.every(input=>input.checked);all.indeterminate=!all.checked&&checkboxes.some(input=>input.checked)};
 all.onchange=()=>{checkboxes.forEach(input=>input.checked=all.checked);update()};checkboxes.forEach(input=>input.onchange=update);
 restore.onclick=async()=>{
  const selected=checkboxes.filter(input=>input.checked);modal.querySelectorAll('button,input').forEach(el=>el.disabled=true);
  try{
   for(const kind of ['files','documents']){
    const ids=selected.filter(input=>input.dataset.restoreKind===kind).map(input=>input.value);
    if(ids.length)await api('/api/files/trash',{kind,action:'recover',ids});
   }
   await restoreFiles();
  }catch(failure){modal.querySelector('.error').textContent=failure.message;modal.querySelectorAll('button,input').forEach(el=>el.disabled=false);update()}
 };
}

async function moveDriveFile(file){
 const kind=file.app?'documents':'files',all=appData[kind]||await items(kind),excluded=new Set([file.id]);
 let changed=true;
 while(changed){changed=false;for(const entry of all)if(excluded.has(entry.parent)&&!excluded.has(entry.id)){excluded.add(entry.id);changed=true}}
 const folders=all.filter(entry=>entry.folder&&!entry.deleted&&!excluded.has(entry.id)&&entry.app===file.app);
 formDialog('Move '+file.name,`<label>Location<select name="parent" aria-label="Location"><option value="">${esc(file.app?file.app[0].toUpperCase()+file.app.slice(1):'iCloud Drive')}</option>${folders.map(folder=>`<option value="${esc(folder.id)}" ${folder.id===file.parent?'selected':''}>${esc(folder.name)}</option>`).join('')}</select></label>`,async values=>{
  await storeItem(kind,{...file,parent:values.parent||null});await documentPage(location.pathname);
 });
}
document.addEventListener('click',event=>{const button=event.target.closest('[data-move-file]');if(button)moveDriveFile(activeEntity)});
