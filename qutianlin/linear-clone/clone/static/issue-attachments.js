const $=(selector,root=document)=>root.querySelector(selector);
export function createIssueAttachments(env){
 const {api,toast,modal,closeDialog,refresh}=env;
 let commentFiles=[],commentIssue=null,commentPending=0;
 const size=bytes=>bytes<1024?bytes+' B':bytes<1048576?(bytes/1024).toFixed(1)+' KB':(bytes/1048576).toFixed(1)+' MB';
 function preview(file){
  const box=modal(file.filename,'<div class="issue-file-preview"></div>',null,null),body=$('.issue-file-preview',box);
  if(file.mime.startsWith('image/')){const image=document.createElement('img');image.src=file.url;image.alt=file.filename;body.append(image);}
  else if(file.mime.startsWith('video/')||file.mime.startsWith('audio/')){const media=document.createElement(file.mime.split('/')[0]);media.src=file.url;media.controls=true;body.append(media);}
  else if(file.mime==='application/pdf'){const frame=document.createElement('iframe');frame.src=file.url;frame.title=file.filename;body.append(frame);}
  const download=document.createElement('a');download.href=file.download_url;download.download=file.filename;download.textContent='Download '+file.filename;body.append(download);
 }
 function cards(files,remove){
  const list=document.createElement('div');list.className='issue-attachments';
  for(const file of files){const card=document.createElement('div');card.className='issue-attachment';card.dataset.uploadId=file.id;
   const open=document.createElement('button');open.type='button';open.setAttribute('aria-label','Preview '+file.filename);open.onclick=e=>{e.stopPropagation();preview(file);};
   if(file.mime.startsWith('image/')){const image=document.createElement('img');image.src=file.url;image.alt=file.filename;open.append(image);}
   const name=document.createElement('span');name.textContent=file.filename;const small=document.createElement('small');small.textContent=size(file.size);open.append(name,small);
   const download=document.createElement('a');download.href=file.download_url;download.download=file.filename;download.textContent='↓';download.setAttribute('aria-label','Download '+file.filename);card.append(open,download);
   if(remove){const button=document.createElement('button');button.type='button';button.textContent='×';button.setAttribute('aria-label','Remove attachment '+file.filename);button.onclick=e=>{e.stopPropagation();Promise.resolve(remove(file)).catch(e=>toast(e.message));};card.append(button);}list.append(card);
  }return list;
 }
 function uploader({getFiles,setFiles,after,pendingChanged=()=>{}}){
  let pending=0;
  async function upload(files){
   if(!files?.length)return;pending++;pendingChanged(pending);
   const status=document.createElement('p');status.role='status';status.className='document-upload-status';after.after(status);
   try{for(const file of files){status.textContent='Uploading '+file.name+'…';if(file.size>10*1024*1024)throw Error('File uploads for free workspaces are limited to 10MB');const session=await api('/api/session'),mode=/^(image|audio|video)\//.test(file.type)?'media':'attachment';const response=await fetch('/api/uploads?name='+encodeURIComponent(file.name)+'&mode='+mode,{method:'POST',headers:{'Content-Type':file.type||'application/octet-stream','X-Linear-CSRF':session.csrf},body:file});const result=await response.json();if(!response.ok)throw Error(result.detail||'File failed to upload');await setFiles([...getFiles(),result]);}}
   catch(error){toast(error.message);}finally{pending--;pendingChanged(pending);status.remove();}
  }
  function choose(){const input=document.createElement('input');input.type='file';input.multiple=true;input.hidden=true;document.body.append(input);input.onchange=()=>{upload([...input.files]);input.remove();};input.addEventListener('cancel',()=>input.remove(),{once:true});input.click();}
  function bind(area){if(!area||area.dataset.issueUploadBound)return;area.dataset.issueUploadBound='';area.addEventListener('dragover',e=>{if([...e.dataTransfer.types].includes('Files')){e.preventDefault();e.dataTransfer.dropEffect='copy';}});area.addEventListener('drop',e=>{if(e.dataTransfer.files.length){e.preventDefault();e.stopPropagation();upload([...e.dataTransfer.files]);}});area.addEventListener('paste',e=>{const files=[...e.clipboardData.files];if(files.length){e.preventDefault();upload(files);}});}
  return{choose,bind,pending:()=>pending};
 }
 function mountDraft(overlay,initial=[]){
  let files=[...initial];const editor=$('[name=description]',overlay),area=document.createElement('div'),button=document.createElement('button');button.type='button';button.textContent='Attach images, files, or videos';button.setAttribute('aria-label','Attach images, files, or videos');editor.after(area,button);
  const draw=()=>area.replaceChildren(cards(files,file=>{files=files.filter(f=>f.id!==file.id);draw();overlay.dispatchEvent(new Event('input'));}));
  const upload=uploader({getFiles:()=>files,setFiles:value=>{files=value;draw();overlay.dispatchEvent(new Event('input'));},after:area});button.onclick=e=>{e.stopPropagation();upload.choose();};upload.bind(editor);draw();
  return{files:()=>[...files],pending:upload.pending,clear:()=>{files=[];draw();}};
 }
 function submitState(){const editor=$('[data-local-comment-editor]'),button=$('[aria-label="Submit comment"]');if(button){button.disabled=commentPending>0||!editor?.innerText.trim()&&!commentFiles.length;button.setAttribute('aria-disabled',String(button.disabled));}}
 function render(){
  const issue=env.getIssue();if(!issue)return;
  if(commentIssue!==issue.id){commentFiles=[];commentIssue=issue.id;}
  const desc=$('[aria-label="Issue description"]'),editor=$('[data-local-comment-editor]');let area=$('[data-issue-files]');if(!area&&desc){area=document.createElement('section');area.dataset.issueFiles='';desc.parentElement.after(area);}
  if(area)area.replaceChildren(cards(issue.attachments||[],async file=>{await api('/api/entities/issues/'+issue.id,'PATCH',{attachments:env.getIssue().attachments.filter(f=>f.id!==file.id)});await refresh();}));
  let draft=$('[data-comment-files]');if(!draft&&editor){draft=document.createElement('div');draft.dataset.commentFiles='';editor.after(draft);}
  const drawComment=()=>{draft?.replaceChildren(cards(commentFiles,file=>{commentFiles=commentFiles.filter(f=>f.id!==file.id);drawComment();}));submitState();};drawComment();
  for(const article of document.querySelectorAll('[data-comment-id]')){const comment=issue.comments?.find(c=>c.id===article.dataset.commentId);if(comment?.attachments?.length)article.append(cards(comment.attachments));}
  const buttons=[...document.querySelectorAll('main button[aria-label="Attach images, files, or videos"]')];
  buttons.forEach((button,index)=>{const target=index===buttons.length-1&&buttons.length>1?'comment':'issue';if(button.dataset.attachmentBound)return;button.dataset.attachmentBound=target;
   const upload=uploader({getFiles:()=>target==='comment'?commentFiles:env.getIssue().attachments||[],setFiles:async files=>{if(target==='comment'){commentFiles=files;drawComment();}else{await api('/api/entities/issues/'+env.getIssue().id,'PATCH',{attachments:files});await refresh();}},after:target==='comment'?draft:area,pendingChanged:value=>{if(target==='comment'){commentPending=value;submitState();}}});button.onclick=e=>{e.preventDefault();e.stopPropagation();upload.choose();};upload.bind(target==='comment'?editor:desc);
  });
  if(editor&&!editor.dataset.attachmentInputBound){editor.dataset.attachmentInputBound='true';editor.addEventListener('input',submitState);}
 }
 async function submit(){if(commentPending)throw Error('Wait for the upload to finish.');const input=$('[data-local-comment-editor]'),body=input?.innerText.trim()||'';if(!body&&!commentFiles.length)return;const button=$('[aria-label="Submit comment"]');button.disabled=true;try{await api('/api/issues/'+env.getIssue().id+'/comments','POST',{body,attachments:commentFiles});commentFiles=[];input.textContent='';await refresh();}finally{submitState();}}
 return{render,submit,submitState,mountDraft};
}
