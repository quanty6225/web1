const setup = project => {

  const screen = project.querySelector('.project__screen');
  const views = project.querySelectorAll('.project__view');
  const back = project.querySelector('.project__back .button');
  let opener = null;
  let pointer = false;

  views.forEach(view => view.inert = true);

  project.querySelectorAll('.project__open').forEach(tool => {

    tool.addEventListener('click', event => {

      const view = project.querySelector(`.project__view--${tool.dataset.view}`);

      if(view) {

        views.forEach(other => other.classList.remove('project__view--selected'));
        view.classList.add('project__view--selected');
        view.inert = false;
        project.classList.add('project--selected');
        screen.inert = true;
        opener = tool;
        pointer = event.detail > 0;
        back.focus({ preventScroll: true });

      }

    });

  });

  project.querySelectorAll('.project__extra').forEach(extra => {

    extra.addEventListener('click', event => {

      const view = project.querySelector(`.project__view--${extra.dataset.view}`);

      if(view) {

        extra.closest('.project__view').inert = true;
        view.classList.add('project__view--selected');
        view.inert = false;
        pointer = event.detail > 0;
        back.focus({ preventScroll: true });

      }

    });

  });

  const close = () => {

    views.forEach(view => {
      view.classList.remove('project__view--selected');
      view.inert = true;
    });
    project.classList.remove('project--selected');
    screen.inert = false;

  };

  back.addEventListener('click', () => {

    close();

    if(pointer) back.blur();
    else opener?.focus({ preventScroll: true });

  });

  document.addEventListener('keydown', event => {

    const inside = project.contains(event.target) || event.target === document.body;

    if(event.key === 'Escape' && inside && !document.querySelector(':modal') && project.classList.contains('project--selected')) back.click();

  }, { capture: true });

  return close;

};

function ready() {

  const pager = document.querySelector('.hero__pager');

  if(pager) {

    const hero = pager.closest('.hero__project');

    new IntersectionObserver(([entry]) => hero.classList.toggle('hero__project--offscreen', !entry.isIntersecting)).observe(hero);

    const dots = [...pager.querySelectorAll('.hero__pager-dot')];
    const toggle = pager.querySelector('.hero__pager-toggle');
    const projects = dots.map(dot => document.getElementById(dot.getAttribute('aria-controls')));
    const closers = new Map(projects.map(project => [project, setup(project)]));
    const screenOf = project => project.querySelector('.project__screen');
    const reduce = matchMedia('(prefers-reduced-motion: reduce)');
    let active = projects.findIndex(project => !project.hidden);
    let finish = null;

    const go = index => {

      dots.forEach((dot, i) => i === index ? dot.setAttribute('aria-current', 'true') : dot.removeAttribute('aria-current'));
      finish?.();

      if(index === active) return;

      const previous = projects[active];
      const next = projects[index];
      active = index;
      screenOf(next).querySelectorAll('img[loading="lazy"]').forEach(img => img.loading = 'eager');

      if(reduce.matches) {
        closers.get(previous)();
        previous.hidden = true;
        next.hidden = false;
        return;
      }

      const layers = previous.classList.contains('project--selected')
        ? previous.querySelectorAll('.project__views, .project__back')
        : [screenOf(previous)];

      previous.classList.add('project--leaving');
      next.classList.add('project--entering');
      next.hidden = false;

      const outs = [...layers].map(layer => layer.animate([
        { opacity: 1, transform: 'translateY(0)' },
        { opacity: 0, offset: 0.6 },
        { opacity: 0, transform: 'translateY(40%)' }
      ], { duration: 300, easing: 'cubic-bezier(0.65, 0, 0.35, 1)', fill: 'forwards' }));

      const into = screenOf(next).animate([
        { opacity: 0, transform: 'translateY(-40%)' },
        { opacity: 0, offset: 0.4 },
        { opacity: 1, transform: 'translateY(0)' }
      ], { duration: 300, easing: 'cubic-bezier(0.65, 0, 0.35, 1)' });

      const done = () => {
        outs.forEach(out => out.cancel());
        into.cancel();
        previous.hidden = true;
        closers.get(previous)();
        previous.classList.remove('project--leaving');
        next.classList.remove('project--entering');
        finish = null;
      };

      finish = done;
      into.finished.then(() => finish === done && done(), () => {});

    };

    dots.forEach((dot, index) => dot.addEventListener('click', () => go(index)));

    toggle.addEventListener('click', () => toggle.setAttribute('aria-pressed', toggle.getAttribute('aria-pressed') !== 'true'));

    pager.addEventListener('animationend', event => {

      if(event.animationName === 'hero-pill' && toggle.getAttribute('aria-pressed') !== 'true') go((active + 1) % projects.length);

    });

  }

}

export { ready };
