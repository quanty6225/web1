function ready() {

  const unlimitedRadio = document.querySelector('#pricing-unlimited');
  const unlimitedPackage = document.querySelector('.pricing__package--unlimited');

  if(!unlimitedRadio || !unlimitedPackage || matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const random = (min, max) => min + Math.random() * (max - min);

  const visibleCenter = element => {

    if(!element) return null;

    const rect = element.getBoundingClientRect();

    const left = Math.max(rect.left, 0);
    const right = Math.min(rect.right, innerWidth);
    const top = Math.max(rect.top, 0);
    const bottom = Math.min(rect.bottom, innerHeight);

    if(right <= left || bottom <= top) return null;

    return { x: (left + right) / 2, y: (top + bottom) / 2 };

  };

  const confettiBurst = 90;
  const confettiLimit = 360;
  const confettiColors = ['blue', 'green', 'orange', 'red', 'yellow'];
  const confettiParticles = [];
  const confettiVisibility = 0.5;

  let confettiContainer = null;
  let confettiObserver = null;
  let confettiRunning = false;
  let confettiLastTime = 0;

  const watchConfetti = () => {

    if(confettiObserver) confettiObserver.disconnect();

    confettiObserver = new IntersectionObserver(entries => {

      const entry = entries[entries.length - 1];

      if(!unlimitedRadio.checked) return;

      if(entry.intersectionRatio < confettiVisibility && entry.intersectionRect.height < innerHeight * confettiVisibility) return;

      confettiObserver.disconnect();

      confettiObserver = null;

      burstConfetti(visibleCenter(unlimitedPackage) || { x: innerWidth / 2, y: innerHeight / 2 });

    }, { threshold: [0, 0.25, 0.5, 0.75, 1] });

    confettiObserver.observe(unlimitedPackage);

  };

  const burstConfetti = confettiOrigin => {

    if(!confettiContainer) {

      confettiContainer = document.createElement('div');

      confettiContainer.className = 'pricing__confetti';
      confettiContainer.setAttribute('aria-hidden', 'true');

      document.body.appendChild(confettiContainer);

    }

    for(const particle of confettiParticles.splice(0, confettiParticles.length + confettiBurst - confettiLimit)) {

      particle.element.remove();

    }

    for(let i = 0; i < confettiBurst; i++) {

      const width = random(2, 10);
      const height = random(2, 4);
      const dx = random(-0.6, 0.6);
      const dy = random(-1, -0.3);
      const length = Math.hypot(dx, dy);
      const color = confettiColors[Math.floor(Math.random() * confettiColors.length)];

      const particleElement = document.createElement('i');

      particleElement.style.cssText = `width:${width}px;height:${height}px;background:var(--color-${color});border-radius:${Math.random() > 0.5 ? '50%' : '1px'}`;

      confettiContainer.appendChild(particleElement);

      confettiParticles.push({
        element: particleElement, width, height,
        x: confettiOrigin.x,
        y: confettiOrigin.y,
        vx: dx / length * random(150, 750),
        vy: dy / length * random(300, 800),
        rotation: random(0, 360),
        rotationSpeed: random(-250, 250)
      });

    }

    if(!confettiRunning) {

      confettiRunning = true;
      confettiLastTime = 0;

      requestAnimationFrame(confettiLoop);

    }

  };

  unlimitedRadio.addEventListener('change', () => {

    if(!unlimitedRadio.checked) return;

    watchConfetti();

  });

  if(unlimitedRadio.checked) unlimitedRadio.dispatchEvent(new Event('change'));

  function confettiLoop(time) {

    const delta = confettiLastTime ? Math.min((time - confettiLastTime) / 1000, 0.064) : 0;
    const damping = 0.98 ** (delta * 60);
    const viewportFloor = innerHeight;

    confettiLastTime = time;

    for(let i = confettiParticles.length - 1; i >= 0; i--) {

      const particle = confettiParticles[i];

      particle.vx = (particle.vx + random(-350, 350) * delta) * damping;
      particle.vy = (particle.vy + 180 * particle.height * delta) * damping;
      particle.x += particle.vx * delta;
      particle.y += particle.vy * delta;
      particle.rotation += particle.rotationSpeed * delta;

      if(particle.vy > 0 && particle.y > viewportFloor + Math.max(particle.width, particle.height) * 2) {

        particle.element.remove();

        confettiParticles.splice(i, 1);

      } else {

        particle.element.style.transform = `translate3d(${particle.x}px, ${particle.y}px, 0) rotate(${particle.rotation}deg)`;

      }

    }

    if(confettiParticles.length) {

      requestAnimationFrame(confettiLoop);

    } else {

      confettiRunning = false;

      confettiContainer.remove();

      confettiContainer = null;

    }

  }

}

export { ready };
