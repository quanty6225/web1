const $=(q,r=document)=>r.querySelector(q),$$=(q,r=document)=>[...r.querySelectorAll(q)];
export async function bindSigningKeys({api,modal,closeDialog,toast}){
 const path=location.pathname.replace(/\/$/,'');
 if(path==='/qqq153/settings/account/security/commit-signing-key'){
  const name=$('#commit-signing-key-name'),material=$('#commit-signing-key-private-key'),form=material.closest('form'),submit=$('button[type=submit]',form);
  const error=document.createElement('div');error.className='local-inline-error';error.role='alert';form.append(error);let busy=false;
  name.required=true;material.required=true;name.autocomplete='off';material.autocomplete='off';
  const enable=()=>{submit.disabled=busy||!name.value.trim()||!material.value.trim();};
  name.addEventListener('input',enable);material.addEventListener('input',enable);
  const cancel=$$('button',form).find(b=>b.textContent.trim()==='Cancel');cancel.onclick=e=>{e.preventDefault();e.stopPropagation();material.value='';location.href='/qqq153/settings/account/security';};
  material.addEventListener('dragover',e=>{e.preventDefault();e.dataTransfer.dropEffect='copy';});
  material.addEventListener('drop',async e=>{e.preventDefault();error.textContent='';if(e.dataTransfer.files.length!==1){error.textContent='Drop one key file.';return;}const file=e.dataTransfer.files[0];if(file.size>100000){error.textContent='The key file is too large.';return;}material.value=await file.text();enable();material.focus();});
  form.onsubmit=async e=>{e.preventDefault();e.stopPropagation();if(busy)return;error.textContent='';if(!name.value.trim()||!material.value.trim()){error.textContent='Enter a key name and private key.';return;}busy=true;enable();try{await api('/api/commit-signing-keys','POST',{name:name.value.trim(),material:material.value});material.value='';location.href='/qqq153/settings/account/security';}catch(errorValue){error.textContent=errorValue.message;}finally{busy=false;enable();}};
  enable();return;
 }
 if(path!=='/qqq153/settings/account/security')return;
 let root=$('[data-local-signing-key]');
 if(!root){const empty=$$('main p,main div,main span').find(e=>!e.childElementCount&&e.textContent.trim()==='No signing key added');if(!empty)return;root=document.createElement('div');root.dataset.localSigningKey='true';empty.replaceWith(root);}
 const render=async()=>{const keys=await api('/api/commit-signing-keys');root.replaceChildren();const add=$('a[href="/qqq153/settings/account/security/commit-signing-key"]');if(add)add.hidden=keys.length>0;
  if(!keys.length){root.textContent='No signing key added';return;}
  for(const key of keys){const row=document.createElement('div');row.className='local-key-row';const text=document.createElement('span');text.textContent=key.name+' · '+(key.scheme==='ssh'?'SSH':'GPG');const fingerprint=document.createElement('small');fingerprint.textContent=key.fingerprint;fingerprint.style.overflowWrap='anywhere';text.append(document.createElement('br'),fingerprint);const remove=document.createElement('button');remove.type='button';remove.textContent='Remove key';remove.onclick=e=>{e.stopPropagation();modal('Remove commit signing key','<p>Coding sessions will no longer use this key to sign commits.</p>','Remove key',async()=>{await api('/api/commit-signing-keys/'+key.id,'DELETE');closeDialog();await render();toast('Signing key removed');},true);};row.append(text,remove);root.append(row);}
 };await render();
}
