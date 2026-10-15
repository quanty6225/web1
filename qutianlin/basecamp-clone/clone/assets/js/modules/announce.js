function announce(message) {

  const announcer = document.getElementById('announcer');

  if(!announcer) return;

  announcer.textContent = '';

  requestAnimationFrame(() => announcer.textContent = message.replace(/\s+/g, ' ').trim());

}

export { announce };
