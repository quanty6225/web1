function ready() {

  const summaries = document.querySelectorAll('.faqs details summary');

  if(summaries.length) {

    summaries.forEach(summary => {

      const details = summary.closest('details');

      summary.addEventListener('click', (e) => {

        e.preventDefault();

        if(details.open) {

          details.open = false;

        } else {

          details.open = true;

        }

      });

    });

  }

}

export { ready };
