let findMapView={scale:1,x:0,y:0,hidden:false,compact:false};
async function findPage(){
 const states=(await api('/api/find/state')).devices;
 const devices=(await items('devices')).filter(device=>!states[device.id]?.removed).sort((a,b)=>a.order-b.order),id=new URLSearchParams(location.search).get('device'),device=devices.find(d=>d.id===id);activeEntity=device;
 const capability=device?.capabilities||{},state=states[device?.id]||{};
 const action=(name,label)=>`<button data-op="device-action" data-action-name="${name}">${label}</button>`;
 root.innerHTML=header('Find Devices')+`<main class="find-map"><img draggable="false" class="map-image" src="/static/find/map-redacted.png" alt="Map with private location information removed"><section class="find-panel ${findMapView.compact?'compact':''}" ${findMapView.hidden?'hidden':''}><button data-find="compact" aria-label="Expand or compress devices" aria-expanded="${!findMapView.compact}">⌃</button><div class="find-panel-content">${device?`<button data-op="find-back">‹ Devices</button><img class="device-icon" src="/static/find/${device.id}.png" alt="${esc(device.model)}"><h1>${esc(device.name)}</h1><p>${esc(device.model)}</p><p>${device.status==='200'?'Online':'Offline'}</p>${device.status==='200'&&typeof device.battery==='number'?`<p aria-label="Battery level">${Math.round(device.battery*100)}%</p>`:''}<p class="hint">Location information has been removed for privacy.</p><p class="hint">Local simulation · physical devices are not connected.</p>${findDeviceStatus(state)}<div class="device-actions">${capability.play_sound?action('Play Sound','Play Sound'):''}${capability.lost_mode?action('Lost iPhone','Lost iPhone'):''}</div>${capability.erase?action('Erase','Erase'):''}${capability.remove?action('Remove','Remove'):''}`:`<h1>All Devices</h1>${devices.length?devices.map(d=>`<button class="device-row" data-op="find-device" data-id="${esc(d.id)}"><img src="/static/find/${d.id}-list.png" alt="${esc(d.model)}"><span>${esc(d.name)}<small>${esc(d.model)} · ${d.status==='200'?'Online':'Offline'}</small></span></button>`).join(''):'<p>No Devices</p>'}`}</div></section><button class="find-sidebar-toggle" data-find="sidebar" aria-label="${findMapView.hidden?'Show':'Hide'} device list" aria-expanded="${!findMapView.hidden}">${findMapView.hidden?'›':'‹'}</button><div class="map-controls"><button data-find="zoom-in" aria-label="Zoom in">＋</button><button data-find="zoom-out" aria-label="Zoom out">−</button><button data-op="map-type">Map</button></div></main>`;
 const map=document.querySelector('.find-map'),image=map.querySelector('.map-image');const pointers=new Map();let lastPinch=null;
 const render=()=>{const xLimit=(findMapView.scale-1)*map.clientWidth/2,yLimit=(findMapView.scale-1)*map.clientHeight/2;findMapView.x=Math.max(-xLimit,Math.min(xLimit,findMapView.x));findMapView.y=Math.max(-yLimit,Math.min(yLimit,findMapView.y));image.style.transform=`translate(${findMapView.x}px,${findMapView.y}px) scale(${findMapView.scale})`;map.querySelector('[data-find="zoom-in"]').disabled=findMapView.scale>=8;map.querySelector('[data-find="zoom-out"]').disabled=findMapView.scale<=1};
 const zoom=amount=>{findMapView.scale=Math.max(1,Math.min(8,findMapView.scale+amount));render()};render();
 map.querySelector('[data-find="zoom-in"]').onclick=()=>zoom(.5);map.querySelector('[data-find="zoom-out"]').onclick=()=>zoom(-.5);
 map.querySelector('[data-find="sidebar"]').onclick=event=>{findMapView.hidden=!findMapView.hidden;map.querySelector('.find-panel').hidden=findMapView.hidden;event.currentTarget.setAttribute('aria-expanded',String(!findMapView.hidden));event.currentTarget.setAttribute('aria-label',(findMapView.hidden?'Show':'Hide')+' device list');event.currentTarget.textContent=findMapView.hidden?'›':'‹'};
 map.querySelector('[data-find="compact"]').onclick=event=>{findMapView.compact=!findMapView.compact;map.querySelector('.find-panel').classList.toggle('compact',findMapView.compact);event.currentTarget.setAttribute('aria-expanded',String(!findMapView.compact))};
 image.onpointerdown=event=>{pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});image.setPointerCapture(event.pointerId);if(pointers.size===2){const values=[...pointers.values()];lastPinch=Math.hypot(values[0].x-values[1].x,values[0].y-values[1].y)}};
 image.onpointermove=event=>{const previous=pointers.get(event.pointerId);if(!previous)return;pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});if(pointers.size===2){const points=[...pointers.values()],distance=Math.hypot(points[0].x-points[1].x,points[0].y-points[1].y);if(lastPinch)zoom((distance-lastPinch)/160);lastPinch=distance}else{findMapView.x+=event.clientX-previous.x;findMapView.y+=event.clientY-previous.y;render()}};
 const release=event=>{pointers.delete(event.pointerId);lastPinch=null};image.onpointerup=release;image.onpointercancel=release;
 image.ondblclick=()=>zoom(.5);image.addEventListener('wheel',event=>{event.preventDefault();zoom(event.deltaY<0?.25:-.25)},{passive:false});
}

function findDeviceStatus(state){
 const statuses=[];
 if(state.sound)statuses.push(`<p>${state.sound==='pending'?'Play Sound Pending…':'Playing Sound (local simulation)'}</p><button data-find-command="stop_sound">Stop Sound</button>`);
 if(state.lost_mode)statuses.push(`<p>${state.lost_mode.status==='pending'?'Lost Mode Pending…':'Lost Mode (local simulation)'}</p><button data-find-command="stop_lost_mode">Stop Lost Mode</button>`);
 if(state.erase)statuses.push(`<p>${state.erase==='pending'?'Erase Pending (local simulation)':'Erased (local simulation)'}</p>${state.erase==='pending'?'<button data-find-command="cancel_erase">Cancel Erase</button>':''}`);
 return statuses.join('');
}
let findCommandPending=false;
async function findDeviceCommand(action,values={}){
 if(!activeEntity)throw Error('Choose a device.');
 if(findCommandPending)return;
 const id=activeEntity.id;findCommandPending=true;root.inert=true;
 const controls=[...modal.querySelectorAll('button,input,textarea')].map(control=>[control,control.disabled]);
 controls.forEach(([control])=>control.disabled=true);
 try{
  await api('/api/find/'+encodeURIComponent(id)+'/action',{action,...values});
  closeDialog();if(location.pathname==='/find/')await findPage();
 }finally{
  findCommandPending=false;root.inert=false;
  controls.forEach(([control,disabled])=>{if(control.isConnected)control.disabled=disabled});
 }
}
async function openDeviceAction(label){
 const name=activeEntity?.name;if(!name)return;
 const notice='<p class="hint">This changes only the local simulation. No command will be sent to a physical device.</p>';
 if(label==='Lost iPhone'){
  const current=(await api('/api/find/state')).devices[activeEntity.id]?.lost_mode||{};
  return formDialog('Lost Mode',notice+field('phone','Phone Number',current.phone||'','tel')+`<label>Message<textarea name="message" maxlength="250" aria-label="Message">${esc(current.message||'')}</textarea></label>`,async values=>{await findDeviceCommand('lost_mode',values)});
 }
 const action={'Play Sound':'play_sound','Erase':'erase','Remove':'remove'}[label];if(!action)return;
 const explanation=action==='remove'?'Remove this device from the local device list?':action==='erase'?'Simulate erasing this device? Offline devices will show a pending request.':'Simulate playing a sound on this device?';
 showDialog(label+' '+name,`<p>${explanation}</p>${notice}<p class="error" role="alert"></p><div class="actions"><button data-action="close">Cancel</button><button class="primary" id="confirm-device-command">${esc(label)}</button></div>`);
 modal.querySelector('#confirm-device-command').onclick=async event=>{event.currentTarget.disabled=true;try{await findDeviceCommand(action,{confirmed:true})}catch(error){modal.querySelector('.error').textContent=error.message;event.currentTarget.disabled=false}};
}
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-find-command]');if(!button)return;
 button.disabled=true;
 try{await findDeviceCommand(button.dataset.findCommand)}catch(error){showDialog('Unable to complete request',`<p>${esc(error.message)}</p><button data-action="close">OK</button>`);button.disabled=false}
});
