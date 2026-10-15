'use strict';
(() => {
  window.initializeCommunity = async root => {
    const question=root.querySelector('#question-vote-button');if(!question&&!root.querySelector('form[data-follow-question-id],form[data-follow-tag-id],form[data-follow-user-id]'))return;
    root.querySelectorAll('.authenticated').forEach(e=>e.hidden=!S.account);root.querySelectorAll('.not-authenticated').forEach(e=>e.hidden=Boolean(S.account));
    root.addEventListener('click',event=>{const sign=event.target.closest('.docs-sign-in');if(sign){event.preventDefault();event.stopPropagation();go('/login?next='+encodeURIComponent(location.pathname+location.search+location.hash))}});
    if(S.account){
      const followLabels=await(await fetch('/static/community-follow-labels.json')).json();
      const forms=[...root.querySelectorAll('form[data-follow-question-id],form[data-follow-tag-id],form[data-follow-user-id]')].map(form=>{
        const kind=['question','tag','user'].find(k=>form.hasAttribute('data-follow-'+k+'-id')),button=form.querySelector('button'),label=kind==='question'?button.querySelector('#follow-question-label'):button;
        return {form,kind,button,label,target:kind+':'+form.getAttribute('data-follow-'+kind+'-id'),originalLabel:label.textContent,originalTitle:button.getAttribute('title')};
      });let followed=new Set();
      const updateFollows=data=>{followed=new Set(data.following);for(const item of forms){const selected=followed.has(item.target);item.label.textContent=selected?followLabels.following:item.originalLabel;item.button.classList.toggle('is-selected',selected);if(selected)item.button.title=item.kind==='question'?followLabels.following_question:followLabels.following;else if(item.originalTitle!==null)item.button.title=item.originalTitle;else item.button.removeAttribute('title');const bell=item.button.querySelector('.docon-alert-regular,.docon-alert-on-regular');if(bell){bell.classList.toggle('docon-alert-regular',!selected);bell.classList.toggle('docon-alert-on-regular',selected)}}root.dataset.communityFollowsReady='true'};
      updateFollows(await api('/api/community/follows'));
      for(const item of forms)item.form.addEventListener('submit',async event=>{event.preventDefault();event.stopImmediatePropagation();const peers=forms.filter(f=>f.target===item.target);peers.forEach(f=>f.button.disabled=true);try{updateFollows(await api('/api/community/follows','POST',{target:item.target,following:!followed.has(item.target)}))}catch(e){showError(e)}finally{peers.forEach(f=>f.button.disabled=false)}});
    }
    if(!question){root.dataset.communityReady='true';return;}
    const qid=question.dataset.id,labels=await(await fetch('/static/community-vote-labels.json')).json();
    let current;
    function update(data){
      current=data;
      for(const [key,v] of Object.entries(data.votes)){
        if(v.kind==='answer'){
          const form=root.querySelector('#answer-rating-form-'+v.id);if(!form)continue;
          for(const value of ['yes','no']){const b=form.querySelector('[data-answer-vote-'+value+']');b?.setAttribute('aria-pressed',String(v.selected===value));b?.classList.toggle('is-selected',v.selected===value)}
          const count=root.querySelector('#answer-helpful-text-'+v.id);
          if(count){count.textContent=v.selected==='yes'?(v.count===1?labels.you_helpful:'You and '+(v.count-1)+' other'+(v.count===2?' person':' people')+' found this answer helpful.'):(v.count?(v.count+' '+(v.count===1?'person':'people')+' found this answer helpful.'):'');count.dataset.helpfulCount=v.count}
        }else{
          const b=v.kind==='question'?question:root.querySelector('[data-comment-vote][data-id="'+v.id+'"]');if(!b)continue;
          b.dataset.voteCount=v.count;b.setAttribute('aria-pressed',String(v.selected==='yes'));b.classList.toggle('voted',v.selected==='yes');b.classList.toggle('is-selected',v.selected==='yes');
          const count=b.querySelector(v.kind==='question'?'[data-vote-count-wrapper]':'.vote-text');if(count){count.textContent=v.kind==='question'?' ('+v.count+')':v.count+' '+(v.count===1?'vote':'votes');count.hidden=v.kind==='question'&&v.count===0}
        }
      }
      root.dataset.communityReady='true';
    }
    update(await api('/api/community/'+qid+'/votes'));
    window.initializeCommunityEditor(root,qid).catch(showError);
    root.addEventListener('click',async event=>{
      const button=event.target.closest('button');if(!button)return;
      let target,value;
      if(button===question){target='question:'+qid;value=current.votes[target].selected?null:'yes'}
      else if(button.hasAttribute('data-comment-vote')){target='comment:'+button.dataset.id;value=current.votes[target].selected?null:'yes'}
      else if(button.hasAttribute('data-answer-rating-button')){target='answer:'+button.closest('form').dataset.answerId;value=button.hasAttribute('data-answer-vote-yes')?'yes':'no';if(current.votes[target].selected===value)value=null}
      else return;
      event.preventDefault();event.stopPropagation();button.disabled=true;
      try{const state=await api('/api/community/'+qid+'/votes','POST',{target,value});update(state);if(state.repeated_anonymous_vote)modal(labels.thank_you,'<p>'+esc(labels.feedback_description)+'</p>')}
      catch(e){showError(e)}finally{button.disabled=false}
    });
  };
})();
