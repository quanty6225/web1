async function accountPage(){
 const {account:person,profile,pending_change}=await api('/api/account'),choices=await api('/static/auth-choices.json');
 const country=choices.countries.find(c=>c.value===profile.country)?.label||'';
 root.innerHTML=`<header><a href="/account/">Apple Account</a><a href="/account/faq/">FAQ</a><button data-action="logout">Sign Out</button></header><main class="settings-page account-page"><h1>Apple Account</h1><p>${esc(person.email_normalized)}</p><section class="settings-card"><h2>Personal Information</h2><dl><dt>Name</dt><dd>${esc(person.display_name)}</dd><dt>Birthday</dt><dd>${esc(profile.birthday||'—')}</dd><dt>Country / Region</dt><dd>${esc(country||'—')}</dd><dt>Phone Number</dt><dd>${esc(profile.phone||'—')}</dd></dl><button class="primary" id="edit-account-profile">Edit</button></section><section class="settings-card"><h2>Email &amp; Phone Numbers</h2><p>${esc(person.email_normalized)}</p><button id="change-account-email">Change Email Address</button><button id="change-account-phone">Change Phone Number</button>${pending_change?'<button id="resume-account-change">Continue Verification</button>':''}</section><section class="settings-card"><h2>Password</h2><button id="change-account-password">Change Password</button><a href="/account/recovery/">Forgot password?</a><button id="account-signout-all">Sign Out of All Browsers</button></section><p role="status" id="account-status"></p><a href="/home/">Back to iCloud</a></main>${footer()}`;
 document.querySelector('#change-account-email').onclick=()=>accountIdentityForm('email',profile,choices);
 document.querySelector('#change-account-phone').onclick=()=>accountIdentityForm('phone',profile,choices);
 if(pending_change){document.querySelector('#resume-account-change').onclick=()=>accountIdentityVerification(pending_change);accountIdentityVerification(pending_change)}
 document.querySelector('#edit-account-profile').onclick=()=>formDialog('Personal Information',
  field('first','First Name',profile.first??person.display_name.split(' ')[0])+field('last','Last Name',profile.last??person.display_name.split(' ').slice(1).join(' '))+field('birthday','Birthday',profile.birthday||'','date')+`<label>Country / Region<select name="country" aria-label="Country / Region"><option value="">—</option>${choices.countries.map(c=>`<option value="${esc(c.value)}" ${c.value===profile.country?'selected':''}>${esc(c.label)}</option>`).join('')}</select></label><label class="auth-check"><input type="checkbox" name="announcements" ${profile.announcements?'checked':''}>Announcements</label><label class="auth-check"><input type="checkbox" name="media_updates" ${profile.media_updates?'checked':''}>Apps, Music, TV, and More</label>`,
  async values=>{await api('/api/account/profile',values,'PUT');session=await api('/api/session');await accountPage();document.querySelector('#account-status').textContent='Your changes have been saved.'});
 document.querySelector('#change-account-password').onclick=()=>formDialog('Change Password',field('current_password','Current Password','','password')+field('password','New Password','','password')+field('confirm','Confirm Password','','password'),async values=>{await api('/api/auth/change-password',values);session=await api('/api/session');document.querySelector('#account-status').textContent='Your password has been changed.'});
 document.querySelector('#account-signout-all').onclick=()=>{showDialog('Sign Out of All Browsers','<p>Sign out of all browsers?</p><div class="actions"><button data-action="close">Cancel</button><button id="confirm-account-signout" class="primary">Sign Out</button></div>');document.querySelector('#confirm-account-signout').onclick=async()=>{try{await api('/api/auth/logout-all',{});navigate('/account/')}catch(err){modal.querySelector('p').textContent=err.message}}};
}

function accountIdentityForm(purpose,profile,choices){
 const title=purpose==='email'?'Change Email Address':'Change Phone Number';
 const fields=purpose==='email'?field('email','New Email Address','','email'):`<label>Country Code<select name="phone_code" aria-label="Country Code">${choices.phone_codes.map(c=>`<option value="${esc(c.value)}" ${c.value===(profile.phone_code||'CN')?'selected':''}>${esc(c.label)}</option>`).join('')}</select></label>${field('phone','New Phone Number','','tel')}`;
 showDialog(title,`<form id="identity-change-form">${fields}${field('current_password','Current Password','','password')}<p>${purpose==='email'?'A verification code will be sent to your new email address.':'Confirm this phone number change with a code sent to your current email address.'}</p><p class="error" role="alert"></p><div class="actions"><button type="button" data-action="close">Cancel</button><button class="primary" type="submit">Continue</button></div></form>`);
 const form=document.querySelector('#identity-change-form');form.querySelectorAll('input').forEach(input=>input.required=true);
 form.onsubmit=async event=>{
  event.preventDefault();const button=form.querySelector('[type="submit"]');button.disabled=true;
  try{await api('/api/account/change/start',{purpose,...Object.fromEntries(new FormData(form))});closeDialog();await accountPage()}
  catch(error){
   const current=await api('/api/account').catch(()=>null);
   if(current?.pending_change){closeDialog();await accountPage()}
   else{form.querySelector('[role="alert"]').textContent=error.message;button.disabled=false}
  }
 };
}
function accountIdentityVerification(change){
 const blocked=change.state!=='challenge'||change.mail_status!=='SMTP_SENT';
 const message=change.mail_status!=='SMTP_SENT'?'Email has not been sent. Please try again.':change.state==='expired'?'The verification code has expired. Request a new code.':change.state==='locked'?'Too many incorrect codes. Request a new code.':'Enter the verification code sent to '+change.recipient+'.';
 showDialog('Verify Email Address',`<form id="identity-verification-form"><p>${esc(message)}</p>${field('code','Verification Code')}<p class="error" role="alert"></p><p role="status" id="identity-resend-status"></p><div class="actions"><button type="button" id="identity-cancel">Cancel</button><button type="button" id="identity-resend">Resend Code</button><button type="submit" class="primary" ${blocked?'disabled':''}>Verify</button></div></form>`);
 const form=document.querySelector('#identity-verification-form'),input=form.elements.code,resend=document.querySelector('#identity-resend'),status=document.querySelector('#identity-resend-status');
 input.required=true;input.pattern='[0-9]{6}';input.maxLength=6;input.inputMode='numeric';input.autocomplete='one-time-code';input.disabled=blocked;
 const until=Date.now()+(change.retry_after||0)*1000;
 const update=()=>{const seconds=Math.max(0,Math.ceil((until-Date.now())/1000));resend.disabled=seconds>0;status.textContent=seconds?'You can request another code in '+seconds+' seconds.':''};update();
 const timer=setInterval(()=>{if(!resend.isConnected||!modal.open){clearInterval(timer);return}update()},1000);
 form.onsubmit=async event=>{
  event.preventDefault();const button=form.querySelector('[type="submit"]');button.disabled=true;
  try{await api('/api/account/change/verify',{code:input.value});clearInterval(timer);closeDialog();session=await api('/api/session');await accountPage();document.querySelector('#account-status').textContent='Your changes have been saved.'}
  catch(error){form.querySelector('[role="alert"]').textContent=error.message;button.disabled=false}
 };
 resend.onclick=async()=>{
  resend.disabled=true;
  try{const response=await api('/api/account/change/resend',{});clearInterval(timer);accountIdentityVerification(response.pending_change)}
  catch(error){form.querySelector('[role="alert"]').textContent=error.message;const current=await api('/api/account').catch(()=>null);if(current?.pending_change){clearInterval(timer);accountIdentityVerification(current.pending_change)}}
 };
 document.querySelector('#identity-cancel').onclick=async()=>{
  try{await api('/api/account/change/cancel',{});clearInterval(timer);closeDialog();await accountPage()}
  catch(error){form.querySelector('[role="alert"]').textContent=error.message}
 };
}
