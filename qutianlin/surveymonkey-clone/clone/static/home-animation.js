import {DotLottie} from './vendor/dotlottie.js';
const poster=document.querySelector('img[src="/static/homepage-canvas.png"]');
if(poster&&!matchMedia('(prefers-reduced-motion: reduce)').matches){
 const canvas=document.createElement('canvas');canvas.width=1336;canvas.height=668;canvas.setAttribute('aria-label','Employee engagement survey insights animation');canvas.style.cssText='position:absolute;inset:0;width:100%;height:100%';poster.parentElement.style.position='relative';poster.parentElement.append(canvas);
 DotLottie.setWasmUrl('/static/vendor/dotlottie-player.wasm');
 const player=new DotLottie({canvas,src:'/static/homepage-animation.lottie',autoplay:true,loop:true,renderConfig:{autoResize:true}});
 player.addEventListener('load',()=>{poster.style.opacity='0';canvas.dataset.animationLoaded='true'});
 player.addEventListener('loadError',()=>{canvas.remove();poster.style.opacity='1'});
 const observer=new IntersectionObserver(entries=>{for(const entry of entries){if(entry.isIntersecting)player.play();else player.pause()}},{threshold:.01});observer.observe(canvas);
 window.addEventListener('pagehide',()=>{observer.disconnect();player.destroy()},{once:true});
}
