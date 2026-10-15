'use strict';
(() => {
 let dialogs;
 const loadDialogs=async()=>dialogs||=(await(await fetch('/static/account-dialogs.json')).json());
 const readConsent=()=>{try{return JSON.parse(localStorage.getItem('onedrive-cookie-categories'))||{}}catch{return {}}};
 window.refreshAccountLanguageSummary=async(settings,catalog)=>{
  if(!$('[data-account-language]'))return;
  settings||=await api('/api/account/language');catalog||=await api('/api/account/language-options');
  const values={display_label:settings.display_label,translation_mode:{Yes:'始终翻译',Ask:'翻译前询问我',No:'从不翻译'}[settings.translation_mode],regional_format:catalog.regional_formats.find(r=>r.value===settings.regional_format)?.label||''};
  for(const node of $$('[data-account-language]'))node.textContent=values[node.dataset.accountLanguage];
 };
 window.openAccountLanguage=async(kind='language')=>{
  const [catalog,settings]=await Promise.all([api('/api/account/language-options'),api('/api/account/language')]);
  const modeLabels={Yes:'始终翻译',Ask:'翻译前询问我',No:'从不翻译'};
  const choices=(rows,value)=>rows.map(r=>`<option value="${esc(r.value)}" ${r.value===value?'selected':''}>${esc(r.label)}</option>`).join('');
  const back='<button type="button" data-language-back aria-label="返回">←</button>';
  if(kind==='language'){
   modal('你的语言设置',`<div class="account-language"><p>你在此处选择的设置将在使用 Microsoft 帐户登录的设备和应用程序之间同步。</p><button data-language-open="display" aria-label="单击以编辑显示语言。">显示语言<span>${esc(settings.display_label)}</span></button><button data-language-open="preferred" aria-label="单击此处可编辑首选语言">首选语言<span>${settings.preferred_languages.map(esc).join('、')}</span></button><button data-language-open="translation" aria-label="单击以编辑翻译设置。">Translation<span>${modeLabels[settings.translation_mode]}</span></button></div>`);
  }else if(kind==='translation'){
   modal('Translation',`${back}<form id="account-language-form" class="account-language"><p>翻译你收到的用你不懂的语言发送的消息。</p><fieldset><legend>选择何时翻译消息</legend>${Object.entries(modeLabels).map(([v,t])=>`<label><input type="radio" name="translation_mode" value="${v}" ${settings.translation_mode===v?'checked':''}>${t}</label>`).join('')}</fieldset><label>将消息翻译为<select name="translation_language" aria-label="翻译语言"><option value=""></option>${choices(catalog.translation_languages.map(v=>({value:v,label:v})),settings.translation_language)}</select></label><p>不会翻译用你的首选语言编写的消息。</p><p class="error" role="alert" hidden></p><button class="primary" type="submit">保存</button></form>`);
  }else if(kind==='display'){
   const rows=catalog.display_languages;
   modal('显示语言',`${back}<form id="account-language-form" class="account-language"><p>此网站、OneDrive 和某些联机 Microsoft 365 应用将以你选择的语言显示。</p><input type="search" aria-label="查找语言"><label>显示语言<select name="display_language" size="8">${choices(rows,settings.display_language)}</select></label><p class="error" role="alert" hidden></p><button class="primary" type="submit">更改显示语言</button></form>`);
   const search=$('.account-language input[type=search]');search.oninput=()=>{for(const option of $('.account-language select').options)option.hidden=!option.textContent.toLocaleLowerCase().includes(search.value.toLocaleLowerCase())};
  }else if(kind.startsWith('preferred')){
   await window.openPreferredLanguage(kind,catalog,settings);return;
  }else if(kind==='region'){
   const text=catalog.labels.msaRegionalFormat;
   modal(text.dialogTitle,`<form id="account-language-form" class="account-language"><p>${esc(text.dialogDescription)}</p><label>${esc(text.regionalFormatDropdownPlaceholder)}<select name="regional_format" aria-label="${esc(text.regionalFormatDropdownAriaLabel)}"><option value="">${esc(text.regionalFormatDropdownPlaceholder)}</option>${choices(catalog.regional_formats,settings.regional_format)}</select></label><label>${esc(text.dateFormatLabel)}<select name="date_format" aria-label="${esc(text.dateFormatDropdownAriaLabel)}"></select></label><label>${esc(text.timeFormatLabel)}<select name="time_format" aria-label="${esc(text.timeFormatDropdownAriaLabel)}"></select></label><p class="error" role="alert" hidden></p><button class="primary" type="submit">${esc(text.doneButtonText)}</button></form>`);
   const region=$('[name=regional_format]'),updateFormats=(initial=false)=>{const formats=catalog.regional_format_details[region.value];for(const key of ['date','time']){const select=$('[name='+key+'_format]'),placeholder=text[key+'FormatDropdownPlaceholder'];select.innerHTML='<option value="">'+esc(placeholder)+'</option>'+choices((formats?.[key+'_formats']||[]).map(r=>({value:r.format,label:r.display})),initial?settings[key+'_format']:'');select.disabled=!formats}};updateFormats(true);region.onchange=()=>updateFormats();
  }
  $$('[data-language-open]').forEach(el=>el.onclick=()=>window.openAccountLanguage(el.dataset.languageOpen));
  $('[data-language-back]')?.addEventListener('click',()=>window.openAccountLanguage('language'));
  const form=$('#account-language-form');
  if(form)form.addEventListener('submit',async e=>{e.preventDefault();e.stopImmediatePropagation();try{const saved=await api('/api/account/language','POST',Object.fromEntries(new FormData(form)));await window.refreshAccountLanguageSummary(saved,catalog);if(kind==='region')closeOverlay();else await window.openAccountLanguage('language')}catch(err){const box=$('.error',form);box.hidden=false;box.textContent=err.message}});
 };
 window.showAccountCookiePreferences=async()=>{
  const doc=await loadDialogs();modal('管理 Cookie 首选项',doc.cookie_form,`<button class="primary" type="submit" form="account-cookie-form" disabled>保存更改</button><button type="reset" form="account-cookie-form" disabled>全部重置</button>`);
  const form=$('#account-cookie-form'),saved=readConsent(),fallback=localStorage.getItem('onedrive-cookie-choice');
  for(const input of form.querySelectorAll('input[type=radio]')){input.checked=input.value===(saved[input.name]||(fallback==='all'?'accept':fallback==='essential'?'reject':''));input.defaultChecked=input.checked}
  const update=()=>{const changed=[...form.elements].some(el=>el.type==='radio'&&el.checked!==el.defaultChecked);$$('[form=account-cookie-form]').forEach(el=>el.disabled=!changed)};
  form.addEventListener('change',update);form.addEventListener('reset',()=>queueMicrotask(update));
  form.addEventListener('submit',e=>{e.preventDefault();e.stopImmediatePropagation();const values=Object.fromEntries(new FormData(form));localStorage.setItem('onedrive-cookie-categories',JSON.stringify(values));localStorage.setItem('onedrive-cookie-choice','custom');$('.account-consent')?.remove();closeOverlay()});
 };
 window.decorateAccountPhoto=profile=>{
  if(!profile.has_photo)return;
  const target=$('[data-control$="edit-picture"]');if(!target)return;
  const img=document.createElement('img');img.className='account-profile-photo';img.alt=profile.display_name;img.src='/api/account/photo';target.before(img);
 };
 window.openAccountPhoto=async profile=>{
  modal('更改照片',`<div class="account-photo-editor"><canvas width="320" height="320" tabindex="0" role="img" aria-label="拖放区"></canvas><p>通过移动圆圈或调整圆圈大小来编辑图片。 可以使用鼠标或使用键盘上的方向键、加号和减号键。</p><input type="file" accept="image/*" aria-label="选择照片" hidden><p class="error" role="alert" hidden></p><div><button type="button" data-photo-add>添加照片</button><button type="button" data-photo-remove disabled>删除照片</button></div></div>`,`<button type="button" class="primary" data-photo-save disabled aria-label="保存照片">保存</button>${btn('取消','close','aria-label="取消“编辑照片”"','secondary')}`);
  const root=$('.account-photo-editor'),canvas=$('canvas',root),ctx=canvas.getContext('2d'),input=$('input',root),error=$('.error',root),save=$('[data-photo-save]');
  let bitmap=null,zoom=1,x=0,y=0,drag=null;
  function paint(changed=true){ctx.clearRect(0,0,320,320);if(bitmap){const scale=Math.max(320/bitmap.width,320/bitmap.height)*zoom,w=bitmap.width*scale,h=bitmap.height*scale;x=Math.max((320-w)/2,Math.min((w-320)/2,x));y=Math.max((320-h)/2,Math.min((h-320)/2,y));ctx.drawImage(bitmap,(320-w)/2+x,(320-h)/2+y,w,h)}$('[data-photo-remove]').disabled=!bitmap;if(changed)save.disabled=false}
  async function load(file,changed=true){if(!file)return;error.hidden=true;try{const next=await createImageBitmap(file);bitmap?.close();bitmap=next;zoom=1;x=0;y=0;paint(changed)}catch{error.textContent='请选择有效的图片';error.hidden=false}}
  $('[data-photo-add]').onclick=()=>input.click();input.onchange=()=>load(input.files[0]);
  $('[data-photo-remove]').onclick=()=>{bitmap?.close();bitmap=null;paint()};
  canvas.ondragover=e=>e.preventDefault();canvas.ondrop=e=>{e.preventDefault();load(e.dataTransfer.files[0])};
  canvas.onpointerdown=e=>{drag={x:e.clientX,y:e.clientY};canvas.setPointerCapture(e.pointerId);canvas.focus()};canvas.onpointerup=()=>drag=null;
  canvas.onpointermove=e=>{if(!drag||!bitmap)return;x+=(e.clientX-drag.x)*320/canvas.clientWidth;y+=(e.clientY-drag.y)*320/canvas.clientHeight;drag={x:e.clientX,y:e.clientY};paint()};
  canvas.onkeydown=e=>{if(!bitmap)return;if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','=','-'].includes(e.key))return;e.preventDefault();if(e.key==='ArrowLeft')x-=5;if(e.key==='ArrowRight')x+=5;if(e.key==='ArrowUp')y-=5;if(e.key==='ArrowDown')y+=5;if(e.key==='+'||e.key==='=')zoom=Math.min(8,zoom+.1);if(e.key==='-')zoom=Math.max(1,zoom-.1);paint()};
  save.onclick=async()=>{save.disabled=true;try{if(bitmap){const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!blob)throw Error('请选择有效的图片');const body=new FormData();body.append('file',blob,'photo.png');await api('/api/account/photo','POST',body)}else await api('/api/account/photo','DELETE');bitmap?.close();bitmap=null;closeOverlay();await window.renderAccountPage()}catch(err){error.textContent=err.message;error.hidden=false;save.disabled=false}};
  if(profile.has_photo){const response=await fetch('/api/account/photo');if(response.ok)await load(await response.blob(),false)}
 };
})();
