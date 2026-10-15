function ready() {

  const menuToggle = document.querySelector('.menu-toggle');
  const menu = document.getElementById('menu');

  if(!menuToggle || !menu) return;

  function inert(value) {

    document.querySelectorAll('main.main, footer.footer, .signup').forEach((el) => el.inert = value);

  }

  function open() {

    document.documentElement.classList.add('menu-open');
    menuToggle.setAttribute('aria-expanded', 'true');
    menuToggle.setAttribute('aria-label', 'Close navigation');

    inert(true);

  }

  function close() {

    const wasOpen = document.documentElement.classList.contains('menu-open');
    const hadFocus = menu.contains(document.activeElement);

    document.documentElement.classList.remove('menu-open');
    menuToggle.setAttribute('aria-expanded', 'false');
    menuToggle.setAttribute('aria-label', 'Open navigation');

    inert(false);

    if(wasOpen && hadFocus) menuToggle.focus();

  }

  menuToggle.addEventListener('click', () => {

    document.documentElement.classList.contains('menu-open') ? close() : open();

  });

  menu.addEventListener('click', (e) => {

    if(e.target !== menu) return;

    close();

    menuToggle.focus();

  });

  document.addEventListener('focusin', (e) => {

    if(menu.contains(e.target) || menuToggle.contains(e.target)) return;

    close();

  });

  addEventListener('pageshow', close);

  matchMedia('(min-width: 64em)').addEventListener('change', (e) => {

    if(e.matches) close();

  });

  document.addEventListener('keydown', (e) => {

    if(e.key === 'Escape') close();

  });

}

export { ready };
