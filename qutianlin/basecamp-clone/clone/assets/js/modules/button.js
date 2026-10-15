function ready() {

  document.querySelectorAll('.button--glow').forEach((button) => {

    button.addEventListener('pointermove', (e) => {

      const rect = button.getBoundingClientRect();

      button.style.setProperty('--pointer-x', e.clientX - rect.left);
      button.style.setProperty('--pointer-y', e.clientY - rect.top);

    });

    button.addEventListener('pointerleave', () => {

      button.style.removeProperty('--pointer-x');
      button.style.removeProperty('--pointer-y');

    });

  });

}

export { ready };
