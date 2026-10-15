function ready() {

  const themeButton = document.querySelector('.theme button');

  if(themeButton) {

    const stored = parseInt(sessionStorage.getItem('theme'));
    let themeValue = stored >= 1 && stored <= 5 ? stored : Number(document.documentElement.className.match(/theme-(\d)/)?.[1]) || 1;
    [...document.documentElement.classList].filter(c => /^theme-\d$/.test(c)).forEach(c => document.documentElement.classList.remove(c));
    document.documentElement.classList.add(`theme-${themeValue}`);

    themeButton.addEventListener('click', () => {

      const themeNext = (themeValue % 5) + 1;

      sessionStorage.setItem('theme', themeNext);

      document.documentElement.classList.replace(`theme-${themeValue}`, `theme-${themeNext}`);

      themeValue = themeNext;

    });

  }

}

export { ready };
