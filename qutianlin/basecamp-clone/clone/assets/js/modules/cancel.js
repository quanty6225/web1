function ready() {

  const PRODUCTS = {
    bc3: { name: 'Basecamp', survey: true },
    bcx: { name: 'Basecamp', survey: true },
    basecamp: { name: 'Basecamp', survey: true },
    campfire: { name: 'Campfire' },
    backpack: { name: 'Backpack' },
    highrise: { name: 'Highrise' },
    skybox: { name: 'the 37signals Suite' }
  };

  const SURVEY_URL = '/external?target=https%3A%2F%2F37signals.typeform.com%2Fto%2FM4eDXjbW%23id%3D:accountId:';

  function setProductName(name) {

    const element = document.querySelector('[data-behavior="cancel_product"]');

    if(element) element.textContent = name;

  }

  function showSurvey(accountId) {

    const element = document.querySelector('[data-behavior="cancel_survey"]');

    if(element) {

      const link = element.querySelector('a');

      if(link) link.href = SURVEY_URL.replace(/:accountId:/, accountId);

      element.style.display = 'block';

    }

  }

  function params(name) {

    const url = new URL(document.location);

    return url.searchParams.get(name);

  }

  let product;

  if(product = PRODUCTS[params('product')]) {

    setProductName(product.name);

    if(product.survey) showSurvey(params('id'));

  }

}

export { ready };
