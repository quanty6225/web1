'use strict';
(() => {
  let routes, markdown;
  const copyTimers = new WeakMap();
  const copyState = (button, state) => {
    button.dataset.copyState = state;
    for (const icon of button.querySelectorAll('[data-show-when]')) icon.hidden = icon.dataset.showWhen !== state;
  };
  const copyMarkdown = async button => {
    clearTimeout(copyTimers.get(button));
    copyState(button, 'loading');
    try {
      markdown ||= fetch('/static/learn-markdown.json').then(r => r.json());
      const entry = (await markdown)[location.pathname];
      if (!entry) throw Error('This article’s source Markdown has not been captured.');
      const response = await fetch(entry.url);
      if (!response.ok) throw Error('Unable to load the article Markdown.');
      await navigator.clipboard.writeText(await response.text());
      copyState(button, 'success');
      copyTimers.set(button, setTimeout(() => copyState(button, 'idle'), 1000));
    } catch (error) {
      copyState(button, 'idle');
      showError(error);
    }
  };
  window.initializeLearnDocument = async root => {
    routes ||= fetch('/static/learn-document-routes.json').then(r => r.json());
    if (!(await routes).includes(location.pathname) || !root.isConnected) return;
    root.classList.add('learn-document');
    const platform = new URLSearchParams(location.search).get('tabs');
    const selected = [...root.querySelectorAll('[role="tab"][data-tab]')].find(tab => tab.dataset.tab === platform);
    if (selected) window.selectHelpTab?.(selected, false);
    for (const details of root.querySelectorAll('details')) {
      const summary = details.querySelector(':scope > summary[aria-expanded]');
      if (summary) details.addEventListener('toggle', () => summary.setAttribute('aria-expanded', String(details.open)));
    }
  };
  document.addEventListener('click', event => {
    const control = event.target.closest('.learn-document button');
    if (!control) return;
    const root = control.closest('.learn-document');
    let handled = false;
    if (control.matches('[data-focus-mode]')) {
      const active = root.classList.toggle('learn-reading-mode');
      control.setAttribute('aria-pressed', String(active));
      handled = true;
    } else if (control.matches('[data-copy-markdown]')) {
      copyMarkdown(control);
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    } else if (control.matches('[data-print-page]')) {
      window.print();
      handled = true;
    } else if (control.textContent.trim() === 'Expand table') {
      const table = control.parentElement.nextElementSibling?.querySelector('table') || control.closest('.table-wrapper')?.querySelector('table');
      if (table) {
        const dialog = document.createElement('dialog');
        dialog.className = 'learn-expanded-table learn-document';
        const close = document.createElement('button');
        close.type = 'button';
        close.textContent = 'Collapse table';
        close.addEventListener('click', () => dialog.close());
        dialog.append(close, table.cloneNode(true));
        document.body.append(dialog);
        dialog.addEventListener('close', () => { dialog.remove(); control.focus(); });
        dialog.showModal();
        handled = true;
      }
    }
    if (handled) {
      const details = control.closest('details.popover');
      if (details) details.open = false;
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
})();
