'use strict';
(() => {
  window.openSharing=async selection=>{
    const ids=Array.isArray(selection)?selection:[selection];
    if(ids.some(id=>S.files.find(f=>f.id===id)?.kind==='vault')){await vaultDialog();return}
    const files=await Promise.all(ids.map(id=>api('/api/files/'+id)));
    const title=ids.length>1?ids.length+' Items':files[0].name;
    const draft={mode:ids.length>1?'edit':'view',audience:'anyone',recipients:'',message:''};
    const sourceHelp='/help/article-241d28ea61ea';
    let shared=files.some(file=>file.shares.length);
    const recipientList=()=>draft.recipients.split(/[;,]/).map(value=>value.trim()).filter(Boolean);
    const remember=()=>{draft.recipients=$('#share-recipients')?.value??draft.recipients;draft.message=$('#share-message')?.value??draft.message;draft.mode=$('#share-mode')?.value??draft.mode};
    const error=text=>{const box=$('#sharing-error');if(box){box.hidden=false;box.textContent=text}};
    const summary=()=>draft.audience==='people'?'People you choose':`Anyone with the link can ${draft.mode}.`;
    async function create(send){
      remember();error('');
      const recipients=recipientList();
      if((send||draft.audience==='people')&&!recipients.length){error('请输入收件人的电子邮件地址');$('#share-recipients')?.focus();return}
      if(recipients.some(value=>!/^\S+@[^\s@,;<>]+\.[^\s@,;<>]+$/.test(value))){error('请输入有效的电子邮件地址');$('#share-recipients')?.focus();return}
      try{
        const result=await api('/api/shares','POST',{ids,mode:draft.mode,audience:draft.audience,recipients,message:draft.message,send});
        shared=true;$('#sharing-manage')?.setAttribute('aria-label','Manage access');
        if(send){closeOverlay();toast('已发送');return}
        $('#share-result').innerHTML=`<label>链接已创建</label><input readonly value="${esc(result.url)}" aria-label="共享链接">`;
        await clipboard(result.url);
      }catch(exc){error(exc.message)}
    }
    function show(){
      modal('Share "'+title+'"',`<button type="button" id="sharing-settings" aria-label="Sharing settings">${ico('settings')}</button><form id="sharing-form"><label for="share-recipients">Add a name, group, or email</label><input id="share-recipients" aria-label="Add a name, group, or email" value="${esc(draft.recipients)}"><label>Can ${draft.mode}<select id="share-mode" aria-label="链接权限"><option value="edit" ${draft.mode==='edit'?'selected':''}>Can edit</option><option value="view" ${draft.mode==='view'?'selected':''}>Can view</option></select></label><textarea id="share-message" aria-label="Add a message" placeholder="Add a message">${esc(draft.message)}</textarea><p id="share-scope-summary">${summary()}</p><p id="sharing-error" class="error" role="alert" hidden></p><div id="share-result"></div><footer><button id="sharing-copy" type="button" class="secondary">Copy link</button><button type="submit" class="primary">Send</button></footer></form>`);
      $('#sharing-settings').onclick=()=>{remember();settings()};
      const summaryButton=document.createElement('button');summaryButton.type='button';summaryButton.className='link';summaryButton.textContent=summary();summaryButton.onclick=()=>{remember();settings()};$('#share-scope-summary').replaceChildren(summaryButton);
      $('#share-mode').onchange=()=>{draft.mode=$('#share-mode').value;summaryButton.textContent=summary()};
      const manage=document.createElement('button');manage.type='button';manage.id='sharing-manage';manage.className='link';manage.textContent='Manage access';manage.setAttribute('aria-label',shared?'Manage access':"Manage access (This item hasn't been shared yet.)");
      const accessHint=document.createElement('p');accessHint.id='sharing-access-hint';accessHint.className='sharing-access-tooltip';accessHint.hidden=true;accessHint.setAttribute('role','tooltip');accessHint.textContent="Manage access (This item hasn't been shared yet.)";manage.setAttribute('aria-describedby',accessHint.id);
      manage.onclick=()=>{remember();if(shared)manageAccess();else accessHint.hidden=false};
      if(!shared){manage.onmouseenter=manage.onfocus=()=>{accessHint.hidden=false};manage.onmouseleave=manage.onblur=()=>{accessHint.hidden=true}};
      $('#share-result').before(manage,accessHint);
      $('.modal .close')?.setAttribute('aria-label','Close');
      $('#sharing-copy').onclick=()=>create(false);
      $('#sharing-form').onsubmit=event=>{event.preventDefault();event.stopPropagation();create(true)};
    }
    function settings(){
      modal('Link settings',`<p>${esc(title)}</p><form id="sharing-settings-form"><fieldset><legend>The link works for</legend><label><input type="radio" name="audience" value="anyone" ${draft.audience==='anyone'?'checked':''}>Anyone</label><p>Share with anyone, doesn't require sign-in</p><label><input type="radio" name="audience" value="people" ${draft.audience==='people'?'checked':''}>People you choose</label></fieldset><label>More settings<select name="mode" aria-label="链接权限"><option value="edit" ${draft.mode==='edit'?'selected':''}>Can edit</option><option value="view" ${draft.mode==='view'?'selected':''}>Can view</option></select></label><footer><button id="sharing-back" type="button">Back</button><button type="submit" class="primary">Apply</button></footer></form>`);
      $('#sharing-back').onclick=show;
      $('.modal .close')?.setAttribute('aria-label','Close');
      const advanced=document.createElement('div');advanced.className='sharing-advanced';
      advanced.innerHTML=`<button type="button" id="sharing-expiration" aria-label="Expiration date picker disabled, requires a Microsoft 365 subscription">Set expiration date (MM/DD/YYYY)</button><button type="button" id="sharing-password" aria-label="Password field disabled, requires a Microsoft 365 subscription">Set password</button><aside id="sharing-upsell" role="dialog" hidden></aside><a href="${sourceHelp}">Learn more</a>`;
      $('#sharing-settings-form footer').before(advanced);
      function upsell(password){const panel=$('#sharing-upsell');panel.hidden=false;panel.innerHTML=`<h3>${password?'Password protected sharing links':'Expiring links'}</h3><p>${password?'Password-protect shared OneDrive files to help prevent information from falling into the wrong hands.':'Keep your shared files and photos more secure by giving others access for a limited period of time.'}</p><a class="primary" href="/plans">Upgrade</a><button type="button" aria-label="Close">×</button>`;panel.querySelector('button').onclick=()=>{panel.hidden=true;(password?$('#sharing-password'):$('#sharing-expiration')).focus()}};
      $('#sharing-expiration').onclick=()=>upsell(false);$('#sharing-password').onclick=()=>upsell(true);
      $('#sharing-settings-form').onsubmit=event=>{event.preventDefault();event.stopPropagation();const data=new FormData(event.currentTarget);draft.audience=data.get('audience');draft.mode=data.get('mode');show()};
    }
    async function manageAccess(){
      const fresh=await Promise.all(ids.map(id=>api('/api/files/'+id)));
      const grants=new Map();for(const file of fresh)for(const share of file.shares)if(!grants.has(share.token))grants.set(share.token,{...share,id:file.id});
      modal('管理访问',grants.size?[...grants.values()].map(share=>`<p>具有链接的人员 · ${share.mode==='edit'?'可以编辑':'可以查看'} ${btn('删除链接','remove-share',`data-id="${share.id}" data-token="${share.token}"`,'danger')}</p>`).join(''):'<p>此项未共享</p>',btn('关闭','close','','secondary'));
    }
    show();
  };
})();
