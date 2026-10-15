// Native menu/search/pagination use captured WordPress markup and local endpoints.
(()=>{
 document.querySelectorAll('[onclick]').forEach(el=>{
  const code=el.getAttribute('onclick');
  if(!/heateorSssPopup/.test(code))return;
  const match=code.match(/heateorSssPopup\(["'](https?:\/\/.*?)["']\)/);
  if(!match)return;
  el.removeAttribute('onclick');el.setAttribute('role','button');el.tabIndex=0;
  const open=()=>window.open('/external?target='+encodeURIComponent(match[1]),'_blank','noopener');
  el.addEventListener('click',open);el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open()}});
 });
})();
