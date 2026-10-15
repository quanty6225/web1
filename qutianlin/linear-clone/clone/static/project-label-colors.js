const palette={'Grey':'#bec2c8','Dark Grey':'#95a2b3','Purple':'#5e6ad2','Teal':'#26b5ce','Green':'#4cb782','Yellow':'#f2c94c','Orange':'#f2994a','Pink':'#f7c8c1','Red':'#eb5757'};
// The captured picker uses CIE LCH: lightness 0–100, chroma 0–132, hue 0–360.
function lch(hex){
 const rgb=hex.match(/[a-f\d]{2}/gi).map(x=>parseInt(x,16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4),[r,g,b]=rgb;
 const xyz=[.4360747*r+.3850649*g+.1430804*b,.2225045*r+.7168786*g+.0606169*b,.0139322*r+.0971045*g+.7141733*b];
 const [x,y,z]=xyz.map((v,i)=>{v/=[.96422,1,.82521][i];return v>.008856?v**(1/3):7.787*v+16/116;});
 const a=500*(x-y),bb=200*(y-z);return[116*y-16,Math.hypot(a,bb),(Math.atan2(bb,a)*180/Math.PI+360)%360];
}
export function openLabelColors({anchor,item,templates,menu,closeMenu,save,toast}){
 let value=item.color||'#4cb782',custom=!Object.values(palette).includes(value),committed=false,parts=lch(value);
 const popup=menu(anchor,[]);popup.setAttribute('aria-label','Label color');popup.style.width='390px';popup.style.maxWidth='calc(100vw - 16px)';popup.style.padding='12px';
 popup._cleanup=()=>{if(!committed&&value!==item.color){committed=true;save(item,{color:value}).catch(e=>toast(e.message));}};
 const element=s=>{const t=document.createElement('template');t.innerHTML=s;return t.content.firstElementChild;};
 const commit=()=>closeMenu();
 function paint(){
  popup.replaceChildren(element(templates[custom?'customPalette':'palette']));
  for(const b of popup.querySelectorAll('[role=button]')){
   const name=b.getAttribute('aria-label');b.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();b.click();}};
   if(name in palette){b.setAttribute('aria-pressed',String(value===palette[name]));const swatch=b.firstElementChild;if(swatch)swatch.style.backgroundImage=value===palette[name]?'':'none';b.onclick=()=>{value=palette[name];commit();};}
   else if(name==='Set custom color'||name==='Select default color')b.onclick=()=>{custom=!custom;paint();};
   else b.onclick=commit;
  }
  const input=popup.querySelector('input');if(!input){popup.querySelector('[role=button]')?.focus();return;}
  input.setAttribute('aria-label','HEX');input.value=value;input.oninput=()=>{const text=input.value.startsWith('#')?input.value:'#'+input.value;if(/^#[a-f\d]{6}$/i.test(text)){value=text.toLowerCase();parts=lch(value);draw();}input.setAttribute('aria-invalid',String(!/^#[a-f\d]{6}$/i.test(text)));};
  input.onkeydown=e=>{e.stopPropagation();if(e.key==='Escape'){e.preventDefault();commit();}if(e.key==='Enter'&&/^#?[a-f\d]{6}$/i.test(input.value)){e.preventDefault();commit();}};
  const [plane,hue]=popup.querySelectorAll('canvas'),sample=document.createElement('canvas');sample.width=sample.height=1;const sampler=sample.getContext('2d',{willReadFrequently:true});
  function selected(){sampler.fillStyle=`lch(${parts[0]}% ${parts[1]} ${parts[2]})`;sampler.fillRect(0,0,1,1);value='#'+[...sampler.getImageData(0,0,1,1).data].slice(0,3).map(x=>x.toString(16).padStart(2,'0')).join('');input.value=value;input.setAttribute('aria-invalid','false');}
  function draw(){
   const p=plane.getContext('2d'),h=hue.getContext('2d');for(let x=0;x<plane.width;x+=2)for(let y=0;y<plane.height;y+=2){p.fillStyle=`lch(${100*(1-y/plane.height)}% ${x*132/plane.width} ${parts[2]})`;p.fillRect(x,y,2,2);}for(let y=0;y<hue.height;y++){h.fillStyle=`lch(75% 132 ${y*360/hue.height})`;h.fillRect(0,y,hue.width,1);}
   const point=plane.nextElementSibling;point.style.setProperty('--x-left',(parts[1]*plane.width/132-7)+'px');point.style.setProperty('--x-top',((100-parts[0])*plane.height/100-7)+'px');point.style.setProperty('--x-backgroundColor',value);hue.nextElementSibling.style.setProperty('--x-top',(parts[2]*hue.height/360-3)+'px');const swatch=popup.querySelector('[role=button] > div');swatch?.style.setProperty('--x-backgroundColor',value);
  }
  for(const canvas of [plane,hue]){const surface=canvas.parentElement;surface.setAttribute('role','slider');surface.tabIndex=0;surface.setAttribute('aria-label',canvas===plane?'Chroma and lightness':'Hue');surface.style.touchAction='none';let dragging=false;
   const change=e=>{const r=canvas.getBoundingClientRect(),x=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),y=Math.max(0,Math.min(1,(e.clientY-r.top)/r.height));if(canvas===plane){parts[0]=100*(1-y);parts[1]=132*x;}else parts[2]=360*y;selected();draw();};
   surface.onpointerdown=e=>{e.preventDefault();surface.setPointerCapture(e.pointerId);dragging=true;change(e);};surface.onpointermove=e=>{if(dragging)change(e);};surface.onpointerup=e=>{dragging=false;surface.releasePointerCapture(e.pointerId);};surface.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();if(canvas===hue)parts[2]=(parts[2]+(['ArrowUp','ArrowLeft'].includes(e.key)?-1:1)+360)%360;else if(e.key==='ArrowLeft'||e.key==='ArrowRight')parts[1]=Math.max(0,Math.min(132,parts[1]+(e.key==='ArrowRight'?1:-1)));else parts[0]=Math.max(0,Math.min(100,parts[0]+(e.key==='ArrowUp'?1:-1)));selected();draw();};
  }
  draw();input.focus();input.select();
 }
 paint();return popup;
}
