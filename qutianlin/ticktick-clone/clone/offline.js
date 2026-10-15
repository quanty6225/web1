/* All source UI network operations terminate at this independent local server. */
(() => {
 const origin=location.origin;
 const boundedTasks=["1e7a2f5d58060c80e83f1230", "e778eecc52add3badbea1b98", "0d9e84e42ca3aa36208b7b36", "d6113334fc7d73c9560812a4"];
 const checkBoundary=()=>{const id=location.hash.split('/').pop();if(boundedTasks.includes(id))location.replace('/boundary/tasks/'+id)};window.addEventListener('hashchange',checkBoundary);checkBoundary();
 function local(raw){
  if(raw && String(raw).includes('/datacollect/'))return origin+String(raw).slice(String(raw).indexOf('/datacollect/'));
  if(raw && String(raw).includes('appleid.cdn-apple.com/'))return origin+'/local/apple-auth.js';
  if(raw && raw.startsWith('https://js.stripe.com'))return origin+'/local/stripe.js';
  if(!raw || /^(data:|blob:|#|mailto:)/.test(raw))return raw;
  let u;try{u=new URL(raw,origin)}catch{return raw}
  if(!/^https?:$/.test(u.protocol))return raw;
  if(u.host===location.host)return origin+u.pathname+u.search+u.hash;
  let p=u.pathname+u.search+u.hash,h=u.hostname;
  if(h==='blog.ticktick.com')p='/blog'+p;
  else if(h==='help.ticktick.com')p=u.pathname==='/'?'/help':p;
  else if(h==='help.dida365.com')p='/dida-help'+p;
  else if(['s3.cn-north-1.amazonaws.com.cn','cdn.dida365.cn','pull.dida365.com','pull.dida365.cn'].includes(h))p='/dida-assets/'+h+p;
  else if(h==='pull.ticktick.com')p='/media'+p;
  else if(h==='pull.ticktick.app')p='/media-app'+p;
  else if(h==='d107mjio2rjf74.cloudfront.net'){}
  else if(/(^|\.)(ticktick\.com|dida365\.com|365dida\.com)$/.test(h)){}
  else p='/external?target='+encodeURIComponent(u.href);
  return origin+p;
 }
 function navigation(raw){
  let url=local(raw);if(!url||/^(#|mailto:|javascript:|data:)/.test(url))return url;
  let u;try{u=new URL(url,origin)}catch{return raw}
  if(location.pathname.startsWith('/pub/templates/project/')&&u.origin===origin){if(u.pathname==='/home')return origin+'/';if(['/signin','/signup'].includes(u.pathname)){const d=u.searchParams.get('dest');if(d?.startsWith('https://dida365.com/')){u.searchParams.set('dest',new URL(d).pathname);return u.href}}}
  if(location.pathname.startsWith('/dida-help')&&u.origin===origin&&(u.pathname.startsWith('/articles/')||u.pathname.startsWith('/external/articles/')||u.pathname==='/help'||u.pathname==='/'))return origin+'/dida-help'+(u.pathname==='/help'||u.pathname==='/'?'':u.pathname)+u.search+u.hash;
  return url;
 }
 const repairLinks=()=>document.querySelectorAll('a[href]').forEach(a=>{const raw=a.getAttribute('href'),next=navigation(raw);if(next!==raw)a.setAttribute('href',next)});
 const beginLinks=()=>{repairLinks();new MutationObserver(repairLinks).observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['href']})};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',beginLinks,{once:true});else beginLinks();
 window.__localURL=local;
 const nativeFetch=window.fetch;
 window.fetch=(input,init)=>{
  if(input instanceof Request)return nativeFetch(new Request(local(input.url),input),init);
  return nativeFetch(local(String(input)),init);
 };
 const open=XMLHttpRequest.prototype.open;
 XMLHttpRequest.prototype.open=function(method,url,...args){return open.call(this,method,local(String(url)),...args)};
 const set=Element.prototype.setAttribute;
 Element.prototype.setAttribute=function(name,value){return set.call(this,name,['srcset','imagesrcset'].includes(name.toLowerCase())?String(value).split(',').map(x=>{let [url,...rest]=x.trim().split(/\s+/);return local(url)+' '+rest.join(' ')}).join(','):['src','href','action','poster'].includes(name.toLowerCase())?local(String(value)):value)};
 for(const [type,keys] of [[HTMLImageElement,['src','srcset']],[HTMLScriptElement,['src']],[HTMLLinkElement,['href','imageSrcset']],[HTMLMediaElement,['src']],[HTMLSourceElement,['src']],[HTMLIFrameElement,['src']]]){
  for(const key of keys){const d=Object.getOwnPropertyDescriptor(type.prototype,key);if(d?.set)Object.defineProperty(type.prototype,key,{...d,set(v){d.set.call(this,['srcset','imageSrcset'].includes(key)?String(v).split(',').map(x=>{let [url,...rest]=x.trim().split(/\s+/);return local(url)+' '+rest.join(' ')}).join(','):local(String(v)))}})}
 }
 const wo=window.open;window.open=(url,...args)=>wo.call(window,local(url),...args);
 if(window.EventSource){const E=window.EventSource;window.EventSource=function(url,args){return new E(local(url),args)}}
 const ws=window.WebSocket;window.WebSocket=function(url,protocols){let u=new URL(url,origin);u.host=location.host;u.protocol=location.protocol==='https:'?'wss:':'ws:';return protocols?new ws(u.href,protocols):new ws(u.href)};
 window.WebSocket.prototype=ws.prototype;Object.setPrototypeOf(window.WebSocket,ws);
 navigator.sendBeacon=(url,data)=>{nativeFetch(local(String(url)),{method:'POST',body:data,keepalive:true}).catch(()=>{});return true};
 document.addEventListener('click',e=>{const a=e.target.closest?.('a[href]');if(!a)return;const raw=a.getAttribute('href');if(!raw||raw.startsWith('#'))return;let url=local(raw);if(location.pathname.startsWith('/dida-help')){const u=new URL(url,origin);if(u.origin===origin&&(u.pathname.startsWith('/articles/')||u.pathname.startsWith('/external/articles/')||u.pathname==='/help'||u.pathname==='/'))url=origin+'/dida-help'+(u.pathname==='/help'||u.pathname==='/'?'':u.pathname)+u.search+u.hash}if(!location.pathname.startsWith('/webapp')||url.includes('/external?')){if(e.button===0&&!e.ctrlKey&&!e.metaKey){e.preventDefault();e.stopImmediatePropagation();location.assign(url)}}else if(url!==a.href)a.href=url},true);
 window.addEventListener('pageshow',e=>{if(e.persisted)location.reload()});
 if(location.pathname.startsWith('/webapp')){
  window.addEventListener('focus',()=>nativeFetch('/local/session',{cache:'no-store'}).then(r=>{if(r.status===401)location.replace('/signin?dest='+encodeURIComponent(location.pathname+location.hash))}));
 }
})();
