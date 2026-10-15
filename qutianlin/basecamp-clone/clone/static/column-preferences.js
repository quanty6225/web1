/* Keep native collapse/filter controls, persisting only explicit personal toggles. */
(() => {
  let pending = Promise.resolve();
  document.addEventListener('click', event => {
    const toggle = event.target.closest('[data-action~="kanban-column#toggle"]');
    if (!toggle) return;
    const column = toggle.closest('[data-kanban-column-id-value]');
    if (!column) return;
    // The native Stimulus handler runs before this deferred observation.
    setTimeout(() => {
      const id = column.dataset.kanbanColumnIdValue;
      const collapsed = column.classList.contains('kanban-column--collapsed');
      const csrf = document.querySelector('meta[name="local-csrf"]')?.content || '';
      pending = pending.then(async () => {
        const response = await fetch('/api/card-columns/' + encodeURIComponent(id) + '/view', {
          method:'POST', keepalive:true,
          headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
          body:JSON.stringify({collapsed})
        });
        if (!response.ok) throw new Error('Unable to save the column view. Please try again.');
        if (document.querySelector('meta[name="local-csrf"]')?.content === csrf) document.querySelector('#column-view-error')?.remove();
      }).catch(error => {
        if (document.querySelector('meta[name="local-csrf"]')?.content !== csrf) return;
        let status = document.querySelector('#column-view-error');
        if (!status) {
          status = document.createElement('p'); status.id = 'column-view-error'; status.setAttribute('role','alert');
          (document.querySelector('main') || document.body).prepend(status);
        }
        status.textContent = error.message;
      });
    }, 0);
  });
})();
