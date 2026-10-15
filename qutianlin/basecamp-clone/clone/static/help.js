(() => {
  document.addEventListener('click', event => {
    if (event.target.closest('.printArticle')) { event.preventDefault(); window.print(); }
  });
  const root = document.querySelector('#local-help');
  if (!root) return;
  const panel = root.querySelector('#help-panel');
  const launcher = root.querySelector('#help-launcher');
  const form = root.querySelector('#help-contact-form');
  const error = root.querySelector('.help-error');
  const picker = root.querySelector('.help-emojis');
  const message = form.elements.message;
  const files = [];
  let returnFocus = launcher;
  function toggle(open, origin = launcher) {
    panel.hidden = !open;
    launcher.setAttribute('aria-expanded', String(open));
    launcher.setAttribute('aria-label', open ? 'Close Beacon popover' : launcher.dataset.label);
    launcher.textContent = open && root.dataset.version === '5' ? 'Close' : launcher.dataset.label;
    if (open) { returnFocus = origin; if (!form.hidden && !form.closest('[hidden]')) form.elements.name.focus(); }
    else returnFocus.focus();
  }
  launcher.addEventListener('click', () => toggle(panel.hidden));
  document.addEventListener('click', event => {
    const contact = event.target.closest('.contactUs');
    if (contact) { event.preventDefault(); toggle(true, contact); }
  });
  root.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !panel.hidden) { event.preventDefault(); toggle(false); }
    const tab = event.target.closest('[role=tab]');
    if (tab && ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
      event.preventDefault(); const tabs = [...root.querySelectorAll('[role=tab]')];
      const next = event.key === 'Home' ? tabs[0] : event.key === 'End' ? tabs[1] : tabs[1 - tabs.indexOf(tab)]; next.click(); next.focus();
    }
  });
  for (const tab of root.querySelectorAll('[role=tab]')) tab.addEventListener('click', () => {
    for (const item of root.querySelectorAll('[role=tab]')) {
      const selected = item === tab; item.setAttribute('aria-selected', String(selected)); item.tabIndex = selected ? 0 : -1;
      root.querySelector('#' + item.getAttribute('aria-controls')).hidden = !selected;
    }
  });
  const emojiToggle = root.querySelector('[data-emoji-toggle]');
  emojiToggle.addEventListener('click', () => { picker.hidden = !picker.hidden; emojiToggle.setAttribute('aria-expanded', String(!picker.hidden)); });
  for (const button of picker.querySelectorAll('button')) button.addEventListener('click', () => {
    const emoji = button.dataset.emoji;
    if (message.value.length - (message.selectionEnd - message.selectionStart) + emoji.length > message.maxLength) return;
    message.setRangeText(emoji, message.selectionStart, message.selectionEnd, 'end'); message.dispatchEvent(new Event('input', {bubbles:true})); message.focus();
  });
  function showError(text) { error.textContent = text; error.hidden = !text; }
  function drawFiles() {
    const list = root.querySelector('.help-files'); list.replaceChildren();
    files.forEach((file, index) => {
      const row = document.createElement('li'); const name = document.createElement('span'); name.textContent = file.name;
      const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = '×'; remove.setAttribute('aria-label', 'Remove ' + file.name);
      remove.addEventListener('click', () => { files.splice(index, 1); drawFiles(); }); row.append(name, remove); list.append(row);
    });
  }
  root.querySelector('[data-attach]').addEventListener('click', () => form.elements.file.click());
  form.elements.file.addEventListener('change', () => {
    for (const file of form.elements.file.files) {
      if (file.size > 10 * 1024 * 1024) { showError('Attachments may be no larger than 10MB'); continue; }
      files.push(file); showError('');
    }
    form.elements.file.value = ''; drawFiles();
  });
  for (const field of [form.elements.name, form.elements.email, message]) field.addEventListener('input', () => {
    if (field.validity.valid && field.value.trim()) field.removeAttribute('aria-invalid');
  });
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (form.dataset.sending) return;
    showError(''); let firstInvalid;
    for (const field of [form.elements.name, form.elements.email, message]) {
      if (!field.validity.valid || !field.value.trim()) { field.setAttribute('aria-invalid', 'true'); firstInvalid ||= field; }
      else field.removeAttribute('aria-invalid');
    }
    if (firstInvalid) { firstInvalid.focus(); return; }
    const data = new FormData(form); data.delete('file'); files.forEach(file => data.append('file', file));
    data.set('version', root.dataset.version); data.set('page', location.pathname);
    data.set('_csrf', document.querySelector('meta[name=local-csrf]').content);
    const submit = form.querySelector('[type=submit]'); form.dataset.sending = 'true'; submit.disabled = true;
    try {
      const response = await fetch('/api/help/contact', {method:'POST', body:data});
      const result = await response.json();
      if (!response.ok) {
        if (result.detail && typeof result.detail === 'object') {
          for (const name of Object.keys(result.detail)) form.elements[name]?.setAttribute('aria-invalid','true');
          if (result.detail.email) showError(result.detail.email);
        } else showError(result.detail || 'There was a problem sending your message. Please try again.');
        return;
      }
      form.hidden = true; root.querySelector('.help-confirmation').hidden = false;
    } catch { showError('There was a problem sending your message. Please try again.'); }
    finally { delete form.dataset.sending; submit.disabled = false; }
  });
  const search = root.querySelector('#help-answer-search');
  const results = root.querySelector('.help-search-results');
  const back = root.querySelector('.help-search-back');
  const touch = root.querySelector('.help-get-in-touch');
  const reader = root.querySelector('#help-reader');
  const readerBody = reader.querySelector('.help-reader-body');
  const readerError = reader.querySelector('.help-reader-error');
  const feedback = reader.querySelector('footer');
  const feedbackLabel = reader.querySelector('.help-feedback-label');
  let searchSequence = 0, articleSequence = 0, activeArticle = '', articleOpener;
  const ratings = new Map();
  const csrf = () => document.querySelector('meta[name=local-csrf]').content;
  function renderRating(rating) {
    feedbackLabel.textContent = rating ? 'Thanks for the feedback' : 'Did this answer your question?';
    for (const button of reader.querySelectorAll('[data-rating]')) { button.hidden = !!rating; button.disabled = false; }
  }
  async function openArticle(path, opener) {
    if (!/^\/help\/2\/article\/[a-z0-9-]+$/.test(path)) { location.href = path; return; }
    const sequence = ++articleSequence;
    if (opener) articleOpener = opener;
    readerError.hidden = true;
    try {
      const response = await fetch(path);
      if (!response.ok) throw new Error('Article unavailable');
      const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
      if (sequence !== articleSequence) return;
      if (doc.querySelector('[data-boundary-page]')) { location.href = path; return; }
      const article = doc.querySelector('#fullArticle');
      if (!article) throw new Error('Article unavailable');
      const title = article.querySelector('h1')?.textContent || doc.title;
      const titleLink = reader.querySelector('#help-reader-link'); titleLink.href = path;
      reader.querySelector('#help-reader-title').textContent = title;
      article.querySelectorAll('script, .printArticle').forEach(node => node.remove());
      readerBody.replaceChildren(...article.childNodes); activeArticle = path;
      feedback.hidden = false; renderRating(ratings.get(path));
      if (!reader.open) reader.showModal();
      reader.scrollTop = 0;
      const state = await fetch('/api/help/2/feedback?article=' + encodeURIComponent(path));
      if (state.ok) {
        const data = await state.json();
        if (sequence === articleSequence) { ratings.set(path, data.rating); renderRating(data.rating); }
      }
    } catch {
      if (sequence !== articleSequence) return;
      readerError.textContent = 'There was a problem retrieving this article. Please double-check your internet connection and try again.';
      readerError.hidden = false; if (!reader.open) { readerBody.replaceChildren(); feedback.hidden = true; reader.showModal(); }
    }
  }
  for (const button of reader.querySelectorAll('[data-rating]')) button.addEventListener('click', async () => {
    const article = activeArticle;
    for (const control of reader.querySelectorAll('[data-rating]')) control.disabled = true;
    readerError.hidden = true;
    try {
      const response = await fetch('/api/help/2/feedback', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({_csrf:csrf(), article, rating:button.dataset.rating})});
      if (!response.ok) throw new Error('Feedback failed');
      const data = await response.json(); ratings.set(article, data.rating);
      if (activeArticle === article) renderRating(data.rating);
    } catch {
      if (activeArticle === article) { renderRating(null); readerError.textContent = 'There was a problem saving your feedback. Please try again.'; readerError.hidden = false; }
    }
  });
  reader.querySelector('[data-reader-close]').addEventListener('click', () => reader.close());
  reader.addEventListener('close', () => { ++articleSequence; articleOpener?.focus(); });
  reader.addEventListener('keydown', event => { if (event.key === 'Escape') event.stopPropagation(); });
  reader.querySelector('[data-reader-size]').addEventListener('click', event => {
    const collapsed = reader.classList.toggle('collapsed'); event.currentTarget.setAttribute('aria-label', collapsed ? 'Expand' : 'Collapse'); event.currentTarget.textContent = collapsed ? '↗' : '↙';
  });
  readerBody.addEventListener('click', event => {
    const link = event.target.closest('a');
    if (link && link.getAttribute('href')?.startsWith('/help/2/article/')) { event.preventDefault(); openArticle(link.getAttribute('href')); }
  });
  results.addEventListener('click', event => {
    const link = event.target.closest('a'); if (!link) return;
    event.preventDefault(); openArticle(link.getAttribute('href'), link);
  });
  back.addEventListener('click', () => {
    ++searchSequence; results.replaceChildren(); search.querySelector('input').value = ''; back.hidden = touch.hidden = true;
    root.querySelector('#help-answers h2').hidden = false; search.querySelector('input').focus();
  });
  touch.querySelector('button').addEventListener('click', () => { root.querySelector('#help-ask-tab').click(); form.elements.name.focus(); });
  search.addEventListener('submit', async event => {
    event.preventDefault(); const term = search.querySelector('input').value.trim();
    const sequence = ++searchSequence; results.replaceChildren(); if (!term) { back.click(); return; }
    back.hidden = touch.hidden = false; root.querySelector('#help-answers h2').hidden = true;
    try {
      const response = await fetch('/api/help/2/answers?query=' + encodeURIComponent(term));
      if (!response.ok) throw new Error('Search failed');
      const data = await response.json(); if (sequence !== searchSequence) return;
      for (const result of data.items) {
        const item = document.createElement('a'); item.href = result.route;
        const title = document.createElement('strong'); title.textContent = result.label;
        const summary = document.createElement('small'); summary.textContent = result.snippet;
        item.append(title, summary); results.append(item);
      }
      if (!results.children.length) {
        touch.hidden = true;
        const heading = document.createElement('h2'); heading.textContent = 'Hmm…';
        const explanation = document.createElement('p'); explanation.textContent = 'We couldn’t find any articles that match your search. Try searching a broader term, or ';
        const contact = document.createElement('button'); contact.type = 'button'; contact.textContent = 'Get in touch';
        contact.addEventListener('click', () => touch.querySelector('button').click()); explanation.append(contact); results.append(heading, explanation);
      }
    } catch { if (sequence === searchSequence) results.textContent = 'There was a problem retrieving articles. Please double-check your internet connection and try again.'; }
  });
})();
