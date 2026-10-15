import * as body from './modules/body.js?v=1.6.5';
import * as button from './modules/button.js?v=1.6.5';
import * as cancel from './modules/cancel.js?v=1.6.5';
import * as classes from './modules/classes.js?v=1.6.5';
import * as codeblock from './modules/codeblock.js?v=1.6.5';
import * as dataDisplay from './modules/dataDisplay.js?v=1.6.5';
import * as details from './modules/details.js?v=1.6.5';
import * as menu from './modules/menu.js?v=1.6.5';
import * as modal from './modules/modal.js?v=1.6.5';
import * as newsletter from './modules/newsletter.js?v=1.6.5';
import * as paths from './modules/paths.js?v=1.6.5';
import * as pricing from './modules/pricing.js?v=1.6.5';
import * as project from './modules/project.js?v=1.6.5';
import * as scrollSnap from './modules/scrollSnap.js?v=1.6.5';
import * as signup from './modules/signup.js?v=1.6.5';
import * as theme from './modules/theme.js?v=1.6.5';

document.addEventListener('DOMContentLoaded', () => {

  body.ready();

  button.ready();

  cancel.ready();

  classes.ready();

  codeblock.ready();

  dataDisplay.ready();

  details.ready();

  menu.ready();

  modal.ready();

  newsletter.ready();

  paths.ready();

  pricing.ready();

  project.ready();

  signup.scroll();

  theme.ready();

});

addEventListener('scroll', () => {

  signup.scroll();

});

addEventListener('load', () => {

  scrollSnap.load();

});
