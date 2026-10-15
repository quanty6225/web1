'use strict';
(async()=>{
 const root=document.querySelector('#account-content');let email='',user=null;
 root.addEventListener('invalid',e=>{const alert=root.querySelector('.error');if(alert)alert.textContent=e.target.validationMessage;e.target.setAttribute('aria-invalid','true')},true);
 root.addEventListener('input',e=>{if(e.target.validity?.valid)e.target.removeAttribute('aria-invalid')});
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 async function api(path,data,method='POST'){const r=await fetch('/api/'+path,{method,headers:{'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});const j=await r.json();if(!r.ok)throw Error(j.detail||'Request failed');return j}
 function field(name,label,type='text',extra=''){return '<label for="'+name+'">'+label+'</label><input id="'+name+'" name="'+name+'" type="'+type+'" '+extra+' required>'}
 function form(title,fields,submit,links){root.innerHTML='<h1>'+title+'</h1>'+(['Verify your email','Reset your password','Choose a new password','Create an account'].includes(title)?'<p>Verification codes expire after 10 minutes. Use the latest code sent to your email.</p>':'')+'<form>'+fields+'<p class="error" role="alert"></p><button class="primary" type="submit">'+submit+'</button></form><div class="links">'+links+'</div><p class="muted">Sign in to save projects to PeaDrive.</p>';root.querySelector('form').onsubmit=async e=>{e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;try{await action(Object.fromEntries(new FormData(e.target)))}catch(err){root.querySelector('.error').textContent=err.message}finally{b.disabled=false}}}
 let action;
 function render(){
  const state=location.hash.slice(1)||'login';
  if(user){root.innerHTML='<h1>Account</h1><p>'+esc(user.email)+'</p><form>'+field('name','Name','text','maxlength="100" value="'+esc(user.name)+'"')+'<p class="error" role="alert"></p><button type="submit">Save</button></form><p class="notice" role="status"></p><div class="actions"><a href="/#">Return to editor</a><button id="logout">Log out</button></div>';root.querySelector('form').onsubmit=async e=>{e.preventDefault();try{user=await api('me',{name:new FormData(e.target).get('name')},'PATCH');root.querySelector('.notice').textContent='Account updated.'}catch(err){root.querySelector('.error').textContent=err.message}};root.querySelector('#logout').onclick=async()=>{await api('logout');user=null;location.hash='login';render()};return}
  const mail=field('email','Email','email','autocomplete="email" value="'+esc(email)+'"');
  const pwd=field('password','Password','password','minlength="8" maxlength="128" autocomplete="'+(state==='login'?'current-password':'new-password')+'"');
  if(state==='register'){form('Create an account',field('name','Name','text','maxlength="100" autocomplete="name"')+mail+pwd,'Send verification code','<a href="#login">Log in</a>');action=async d=>{await api('register',d);email=d.email;location.hash='verify'}}
  else if(state==='verify'){form('Verify your email',mail+field('code','Verification code','text','inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code"'),'Verify','<a href="#register">Request another code</a>');action=async d=>{user=await api('verify',d);render()}}
  else if(state==='recover'){form('Reset your password',mail,'Send reset code','<a href="#login">Log in</a>');action=async d=>{await api('recover',d);email=d.email;location.hash='reset'}}
  else if(state==='reset'){form('Choose a new password',mail+field('code','Verification code','text','inputmode="numeric" pattern="[0-9]{6}" maxlength="6"')+pwd,'Reset password','<a href="#recover">Request another code</a>');action=async d=>{await api('reset',d);email=d.email;location.hash='login'}}
  else {form('Log in with email',mail+pwd,'Log In','<a href="#register">Create an account</a><a href="#recover">Forgot password?</a>');action=async d=>{user=await api('login',d);render()}}
 }
 try{user=(await api('session',null,'GET')).user}catch{}
 addEventListener('hashchange',render);addEventListener('pageshow',async e=>{if(e.persisted){try{user=(await api('session',null,'GET')).user}catch{user=null}render()}});render();
})();
