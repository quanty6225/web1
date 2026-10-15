'use strict';
(()=>{
const fields=[['email','Email','Insert value here'],['firstName','First name',''],['lastName','Last name',''],['title','Title','Senior Developer'],['handle','Handle',''],['mobilePhoneNumber','Mobile','+1 123 456 7890'],['website','Website','https://www.teamwork.com'],['twitter','Twitter','Twitter handle'],['linkedin','LinkedIn','https://www.linkedin.com/in/username/'],['facebook','Facebook','https://facebook.com/username']];
async function render(view,state){
 const C=window.TeamworkChat,{api,esc}=C;
 let profile=await api('/profile');
 if(!view.isConnected)return;
 view.innerHTML=`<h1>Settings</h1><nav class=chat-tabs><a href="/workspace/chat/settings/profile">Profile</a><a href="/workspace/chat/settings/notifications">Notifications</a><a href="/workspace/chat/settings/preferences">Preferences</a><a href="/workspace/chat/settings/localization">Localization</a></nav><form class=chat-profile><h2>Profile</h2><div class=chat-profile-photo-row><label>Profile photo <span title="Upload your profile photo here. The photo can be a GIF, PNG or JPG file. We will resize it for you to a width and height of 200px.">ⓘ</span></label><button type=button data-profile-photo aria-label="Upload profile photo"></button><input type=file accept="image/gif,image/png,image/jpeg" aria-label="Profile photo file" hidden><button type=button data-profile-upload>Upload new</button><button type=button data-profile-camera>Take a photo</button></div>${fields.map(([key,label,placeholder])=>`<label>${label}<input name="${key}" aria-label="${label}" placeholder="${placeholder}" value="${esc(profile[key])}" ${['email','firstName','lastName','handle'].includes(key)?'required':''} ${key==='handle'?'maxlength=255':''}></label>`).join('')}<button type=submit>Save</button></form>`;
 const form=view.querySelector('form'),file=form.querySelector('[type=file]');
 function paintPhoto(){const button=form.querySelector('[data-profile-photo]');button.innerHTML=profile.avatar_url?`<img src="${esc(profile.avatar_url)}" alt="Profile photo" width=80 height=80>`:esc((profile.firstName[0]||'')+(profile.lastName[0]||''));const p=state.people.find(p=>p.id===state.actor);if(p)p.avatar_url=profile.avatar_url;const avatar=document.querySelector('.s-user-dropdown__main-avatar');if(avatar&&profile.avatar_url)avatar.innerHTML=`<img src="${esc(profile.avatar_url)}" alt="" width=30 height=30>`}
 async function upload(photo){
  const controls=form.querySelectorAll('[data-profile-upload],[data-profile-photo],[data-profile-camera]');controls.forEach(b=>b.disabled=true);C.status('');
  try{const data=new FormData();data.append('file',photo,'avatar.png');const response=await fetch('/api/chat/profile/avatar',{method:'POST',body:data}),result=await response.json();if(!response.ok)throw Error(result.detail||'Failed to update profile picture.');profile.avatar_url=result.avatar_url;paintPhoto();C.status('Your profile picture has been updated.')}
  finally{controls.forEach(b=>b.disabled=false);file.value=''}
 }
 file.addEventListener('change',async()=>{if(file.files[0])try{await upload(file.files[0])}catch(e){C.status(e.message)}});
 for(const button of form.querySelectorAll('[data-profile-upload],[data-profile-photo]'))button.addEventListener('click',()=>file.click());
 form.querySelector('[data-profile-camera]').addEventListener('click',()=>camera(upload));
 async function apply(data){const result=await api('/profile','PATCH',data);if(result.pending_email){emailVerification(result.pending_email,data);return}await C.render();C.status('Your profile has been updated.')}
 function emailVerification(email,data){
  const d=C.dialog('Verify your email',`<p>Enter the code sent to ${esc(email)}. Your profile and login email will change after verification.</p><form data-profile-email><label>Verification code<input name=code aria-label="Verification code" inputmode=numeric autocomplete=one-time-code pattern="[0-9]{6}" required></label><button type=submit>Verify</button><button type=button data-profile-resend>Resend code</button></form>`),f=d.querySelector('form'),error=d.querySelector('[data-dialog-error]');
  f.addEventListener('submit',async e=>{e.preventDefault();const submit=f.querySelector('[type=submit]');submit.disabled=true;try{await api('/profile/email/verify','POST',{code:f.elements.code.value});d.close();await C.render();C.status('Your profile has been updated.')}catch(e){error.hidden=false;error.textContent=e.message}finally{submit.disabled=false}});
  f.querySelector('[data-profile-resend]').addEventListener('click',async e=>{e.target.disabled=true;try{await api('/profile','PATCH',data);error.hidden=false;error.textContent='Email sent.'}catch(e){error.hidden=false;error.textContent=e.message}finally{e.target.disabled=false}});
 }
 form.addEventListener('submit',async e=>{e.preventDefault();const submit=form.querySelector('[type=submit]');submit.disabled=true;C.status('');try{await apply(Object.fromEntries(new FormData(form)))}catch(e){C.status(e.message)}finally{submit.disabled=false}});
 paintPhoto();
}
function camera(upload){
 const C=window.TeamworkChat,d=document.createElement('dialog');d.className='chat-camera';d.innerHTML=`<h2>Take a photo</h2><p role=alert hidden></p><video autoplay playsinline muted></video><canvas hidden></canvas><div><button type=button data-take disabled>Take a photo</button><button type=button data-retake hidden>Take another</button><button type=button data-save hidden>Save</button><button type=button data-close>Close</button></div>`;document.body.append(d);d.showModal();
 const video=d.querySelector('video'),canvas=d.querySelector('canvas'),error=d.querySelector('[role=alert]'),take=d.querySelector('[data-take]'),retake=d.querySelector('[data-retake]'),save=d.querySelector('[data-save]');let stream;
 const stop=()=>{stream?.getTracks().forEach(t=>t.stop());stream=null;video.srcObject=null};
 async function start(){
  stop();error.hidden=true;video.hidden=false;canvas.hidden=true;take.hidden=false;take.disabled=true;retake.hidden=true;save.hidden=true;
  try{const media=await navigator.mediaDevices.getUserMedia({audio:false,video:{width:{ideal:600},height:{ideal:600},facingMode:'user'}});if(!d.open){media.getTracks().forEach(t=>t.stop());return}stream=media;video.srcObject=stream;await video.play();take.disabled=false}
  catch(e){stop();video.hidden=true;take.hidden=true;error.hidden=false;error.textContent="Sorry, it looks like we can't use your webcam."}
 }
 take.addEventListener('click',()=>{canvas.width=video.videoWidth;canvas.height=video.videoHeight;const context=canvas.getContext('2d');context.setTransform(-1,0,0,1,canvas.width,0);context.drawImage(video,0,0);stop();video.hidden=true;canvas.hidden=false;take.hidden=true;retake.hidden=false;save.hidden=false});
 retake.addEventListener('click',start);
 save.addEventListener('click',async()=>{save.disabled=true;retake.disabled=true;try{const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!blob)throw Error('Unable to process image.');await upload(blob);d.close()}catch(e){error.hidden=false;error.textContent=e.message}finally{save.disabled=false;retake.disabled=false}});
 d.querySelector('[data-close]').addEventListener('click',()=>d.close());d.addEventListener('close',()=>{stop();d.remove()});start();
}
window.ChatProfile={render};
})();
