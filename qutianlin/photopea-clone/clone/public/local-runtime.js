'use strict';
(() => {
 // Use the editor's native HTML file input / download fallback on every local browser.
 window.showOpenFilePicker=undefined;window.showSaveFilePicker=undefined;window.showDirectoryPicker=undefined;
 const local=url=>{
  if(typeof url!=='string'||/^(data:|blob:|#)/.test(url))return url;
  let u;try{u=new URL(url,location.href)}catch{return url}
  if(u.origin===location.origin)return url;
  if(['www.photopea.com','photopea.com'].includes(u.hostname))return u.pathname+u.search+u.hash;
  return '/offline/resource?url='+encodeURIComponent(u.href);
 };
 const inner=Object.getOwnPropertyDescriptor(Element.prototype,'innerHTML');
 Object.defineProperty(Element.prototype,'innerHTML',{...inner,set(value){if(typeof value==='string')value=value.replace(/(<(?:img|script|iframe|video|audio|source|link)\b[^>]*?\b(?:src|href|poster)=["'])([^"']+)(["'])/gi,(all,a,url,z)=>a+local(url)+z);inner.set.call(this,value)}});
 const fetchOriginal=window.fetch;window.fetch=(input,init)=>fetchOriginal(typeof input==='string'?local(input):input instanceof Request?new Request(local(input.url),input):input,init);
 const open=XMLHttpRequest.prototype.open;XMLHttpRequest.prototype.open=function(method,url,...rest){return open.call(this,method,local(String(url)),...rest)};
 const attr=Element.prototype.setAttribute;Element.prototype.setAttribute=function(name,value){if(['src','href'].includes(name.toLowerCase())&&/^(SCRIPT|LINK|IMG|IFRAME|VIDEO|AUDIO|SOURCE)$/.test(this.tagName))value=local(String(value));return attr.call(this,name,value)};
 for(const [Type,property] of [[HTMLScriptElement,'src'],[HTMLLinkElement,'href'],[HTMLImageElement,'src'],[HTMLIFrameElement,'src'],[HTMLMediaElement,'src'],[HTMLSourceElement,'src']]){
  const descriptor=Object.getOwnPropertyDescriptor(Type.prototype,property);if(descriptor?.set)Object.defineProperty(Type.prototype,property,{...descriptor,set(value){descriptor.set.call(this,local(String(value)))}});
 }
 const beacon=navigator.sendBeacon?.bind(navigator);if(beacon)navigator.sendBeacon=(url,data)=>beacon(local(String(url)),data);
 const nativeOpen=window.open.bind(window);
 window.open=(url,target,features)=>{const value=String(url||'');if(!value||value.startsWith('blob:')||value.startsWith('data:'))return nativeOpen(value,target,features);
 const u=new URL(value,location.href);if(u.pathname==='/papi/login.php')return nativeOpen('/account',target,features);
 if(['www.photopea.com','photopea.com',location.hostname].includes(u.hostname)&&['/learn/','/learn/opening-saving','/learn/layers','/account'].includes(u.pathname))return nativeOpen(u.pathname+u.hash,target,features);
 return nativeOpen('/boundary?url='+encodeURIComponent(u.href),target,features)};

 document.addEventListener('click',e=>{const a=e.target.closest('a[href]');if(!a)return;const u=new URL(a.href,location.href);if(['www.photopea.com','photopea.com'].includes(u.hostname)&&['/learn','/learn/','/learn/opening-saving','/learn/layers'].includes(u.pathname)){e.preventDefault();e.stopImmediatePropagation();nativeOpen(u.pathname==='/learn'?'/learn/':u.pathname,a.target||'_self');return;}if(u.origin!==location.origin&&!['blob:','data:'].includes(u.protocol)){e.preventDefault();e.stopImmediatePropagation();location.assign('/boundary?url='+encodeURIComponent(u.href))}},true);

 const rewriteAnchors=()=>{for(const a of document.querySelectorAll('a[href]')){
  const href=a.getAttribute('href');if(!href||href.startsWith('#')||/^(blob:|data:|javascript:)/.test(href)||a.dataset.localHref===href)continue;
  const u=new URL(href,location.href),core=['/','/learn','/learn/','/learn/opening-saving','/learn/layers','/account'];
  if(u.origin===location.origin&&(core.includes(u.pathname)||u.pathname.startsWith('/boundary')||u.pathname.startsWith('/api/projects')))continue;
  let value;if(['www.photopea.com','photopea.com'].includes(u.hostname)&&core.includes(u.pathname))value=(u.pathname==='/learn'?'/learn/':u.pathname)+u.search+u.hash;
  else {const original=u.origin===location.origin?'https://www.photopea.com'+u.pathname+u.search+u.hash:u.href;value='/boundary?url='+encodeURIComponent(original)}
  a.setAttribute('href',value);a.dataset.localHref=value;
 }};
 document.addEventListener('DOMContentLoaded',()=>{rewriteAnchors();new MutationObserver(rewriteAnchors).observe(document.body,{childList:true,subtree:true})});
 window.PhotopeaLocal={local};
})();
