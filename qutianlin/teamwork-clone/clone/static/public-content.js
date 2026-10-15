'use strict';
(()=>{
 if(!location.pathname.startsWith('/help/'))return;
 const images=[...document.querySelectorAll('.article-body img')];
 function open(image){const gallery=new PhotoSwipe(document.querySelector('.pswp'),PhotoSwipeUI_Default,images.map(img=>({src:img.src,w:img.naturalWidth,h:img.naturalHeight})),{index:images.indexOf(image),bgOpacity:.8,shareEl:false});gallery.listen('destroy',()=>image.focus());gallery.init()}
 for(const image of images){if(image.parentElement.tagName==='A')continue;image.tabIndex=0;image.setAttribute('role','button');image.setAttribute('aria-label','Open image '+(images.indexOf(image)+1)+' of '+images.length)}
 document.addEventListener('click',e=>{const image=e.target.closest('.article-body img');if(image&&image.parentElement.tagName!=='A'&&images.includes(image)){e.preventDefault();e.stopImmediatePropagation();open(image)}if(e.target.closest('.btn-print')){e.preventDefault();e.stopImmediatePropagation();window.print()}},true);
 document.addEventListener('keydown',e=>{if(images.includes(e.target)&&e.target.parentElement.tagName!=='A'&&['Enter',' '].includes(e.key)){e.preventDefault();e.stopImmediatePropagation();open(e.target)}},true);
})();
