import { announce } from './announce.js';

function ready() {

  document.querySelectorAll('.codeblock__code').forEach(codeblock => {

    var codeblock_code = codeblock.querySelector('code');
    var codeblock_button = codeblock.querySelector('button');
    var codeblock_timeout;

    if(!codeblock_button || !codeblock_code) return;

    if(!navigator.clipboard) {

      codeblock_button.hidden = true;

      return;

    }

    function copied(state) {

      codeblock_button.toggleAttribute('data-copied', state);
      codeblock_button.setAttribute('aria-label', state ? 'Copied' : 'Copy');

      if(state) announce('Copied');

    }

    codeblock_button.addEventListener('click', () => {

      navigator.clipboard.writeText(codeblock_code.innerText.trim()).then(() => {

        copied(true);

        clearTimeout(codeblock_timeout);

        codeblock_timeout = setTimeout(() => copied(false), 1500);

      }).catch(() => {});

    });

  });

}

export { ready };
