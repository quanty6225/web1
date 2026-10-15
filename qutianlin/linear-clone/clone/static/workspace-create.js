'use strict';
(async()=>{
 const session=await fetch('/api/session').then(r=>r.json());if(!session.authenticated){location.href='/login?redirectTo=/join';return;}
 const name=document.querySelector('[name=name]'),slug=document.querySelector('[name=urlKey]'),form=name?.closest('form'),buttons=[...document.querySelectorAll('button')],submit=buttons.find(b=>b.textContent.trim()==='Create workspace');if(!name||!slug||!submit)return;
 name.setAttribute('aria-label','Workspace name');slug.setAttribute('aria-label','Workspace URL');name.required=true;slug.required=true;slug.pattern='[a-z][a-z0-9-]{2,48}';submit.disabled=false;
 name.oninput=()=>{if(!slug.dataset.edited)slug.value=name.value.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,49);};slug.oninput=()=>slug.dataset.edited='true';
 let busy=false;const save=async e=>{e?.preventDefault();e?.stopImmediatePropagation();if(busy||!name.reportValidity()||!slug.reportValidity())return;busy=true;submit.disabled=true;try{const response=await fetch('/api/workspaces',{method:'POST',headers:{'Content-Type':'application/json','X-Linear-CSRF':session.csrf},body:JSON.stringify({name:name.value,slug:slug.value,team_name:name.value,identifier:'QQQ',region:'EU'})}),data=await response.json();if(!response.ok)throw Error(data.detail||'Unable to create workspace.');location.href=data.redirect;}catch(error){let alert=document.querySelector('[data-workspace-error]');if(!alert){alert=document.createElement('p');alert.dataset.workspaceError='';alert.role='alert';submit.before(alert);}alert.textContent=error.message;busy=false;submit.disabled=false;}};
 submit.onclick=save;if(form)form.onsubmit=save;
 for(const button of buttons)if(button.getAttribute('aria-label')==='Back to Linear')button.onclick=()=>location.href='/';
})();
