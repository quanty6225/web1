function ready() {

  const modal = document.querySelector('.modal');

  if(modal) {

    const modalTriggers = document.querySelectorAll('.modal-trigger');
    const modalBackground = modal.querySelector('.modal__background');
    const modalContent = modal.querySelector('.modal__content');

    function open(dataset, id, label) {

      const dataType = dataset.type;
      const dataSrc = dataset.src;
      const dataSrcset = dataset.srcset;
      const dataAlt = dataset.alt;
      const dataPoster = dataset.poster;
      const dataTrack = dataset.track;
      const dataTrackJSON = dataset.trackJson;
      const dataEvent = dataset.event;

      if(dataType === 'image') {

        modalContent.innerHTML = `
          <figure class="modal__image">
            <picture>
              ${dataSrcset ? `<source srcset="${dataSrcset}" type="image/webp">` : ''}
              <img src="${dataSrc}" alt="${dataAlt}">
            </picture>
          </figure>
        `;

        const modalFigure = modalContent.querySelector('.modal__image');

        modalFigure.addEventListener('click', close);

      } else if(dataType === 'video') {

        modalContent.innerHTML = `
          <div class="modal__video">
            <video ${dataPoster ? `poster="${dataPoster}"` : ''} src="${dataSrc}" ${dataEvent ? `data-event="${dataEvent}"` : ''} playsinline>
              ${dataTrack ? `<track src="${dataTrack}" kind="captions" label="English" srclang="en" default>` : dataTrackJSON ? JSON.parse(dataTrackJSON).map((track, index) => `<track src="${track.src}" kind="captions" label="${track.label}" srclang="${track.lang}" ${index === 0 ? 'default' : ''}>`).join('') : ''}
            </video>
            <button aria-label="Play video"></button>
          </div>
          <button class="modal__close" aria-label="Close"></button>
        `;

        const modalVideo = modalContent.querySelector('.modal__video');
        const modalVideoElement = modalVideo.querySelector('video');
        const modalVideoButton = modalVideo.querySelector('button');
        const modalVideoTracks = modalVideoElement.textTracks;
        const modalVideoEvent = modalVideoElement.dataset.event;
        const modalClose = modalContent.querySelector('.modal__close');

        if(modalVideoTracks[0]) modalVideoTracks[0].mode = 'hidden';

        if(modalClose) {

          modalClose.addEventListener('click', () => {

            close();

          });

        }

        modalVideoButton.addEventListener('click', () => {

          if(modalVideoElement.paused) {

            modalVideoElement.play().catch(() => {});

          } else {

            modalVideoElement.pause();

          }

        });

        modalVideoElement.addEventListener('play', (e) => {

          if(window.plausible && modalVideoEvent && e.target.currentTime === 0) {

            plausible('Video Start', {
              props: {
                title: modalVideoEvent
              }
            });

          }

          modalVideo.classList.add('modal__video--playing');

          e.target.setAttribute('controls', 'controls');

        });

        modalVideoElement.addEventListener('ended', (e) => {

          if(window.plausible && modalVideoEvent) {

            plausible('Video Finish', {
              props: {
                title: modalVideoEvent
              }
            });

          }

          modalVideo.classList.remove('modal__video--playing');

          e.target.removeAttribute('controls');
          e.target.load();

        });

        if(!location.hash || location.hash.substring(1) !== id) modalVideoElement.play().catch(() => {});

      }

      if(id) history.replaceState(null, '', `#${id}`);

      if(label) modal.setAttribute('aria-label', label);
      modal.setAttribute('aria-hidden', 'false');
      modal.focus();
      modal.showModal();

    }

    function name(trigger) {

      return trigger.getAttribute('aria-label') || trigger.textContent.replace(/\s+/g, ' ').trim();

    }

    function close() {

      modalContent.innerHTML = '';

      modal.scrollTo(0, 0);
      modal.close();
      modal.removeAttribute('aria-label');
      modal.setAttribute('aria-hidden', 'true');

      history.replaceState(null, '', location.pathname);

    }

    if(modalTriggers.length) {

      modalTriggers.forEach(trigger => {

        trigger.addEventListener('click', (e) => {

          open(e.currentTarget.dataset, e.currentTarget.id, name(e.currentTarget));

        });

      });

    }

    modalBackground.addEventListener('click', close);

    document.addEventListener('keydown', (e) => {

      if(e.key === 'Escape' && modalContent.hasChildNodes()) close();

    });

    const hash = location.hash.substring(1);

    if(hash) {

      const hashElement = document.getElementById(hash);

      if(hashElement && hashElement.classList.contains('modal-trigger')) open(hashElement.dataset, hash, name(hashElement));

    }

  }

}

export { ready };
