// Port of @madeinhaus/nextjs-page-transition's useNextCssRemovalPrevention as a
// synchronous script. Runs before React hydrates to eliminate the race condition
// where Next.js removes stylesheets during page transitions.
//
// How it works:
// - Renames data-n-p -> data-n-p-perm and data-n-href -> data-n-href-perm
//   so Next.js no longer recognizes or removes them
// - Tracks which CSS hashes belong to which route (current + previous)
// - On route change complete, expires styles from routes older than previous
// - Exposes window.__raiCssGuard for Next router integration (routeChangeStart/Complete)
(function () {
  var cssHashMap = {};
  var currentUrl = location.pathname + location.search;
  var previousUrl = null;

  function getHash(url) {
    if (!url) return null;
    var match = url.match(/([a-z0-9]+)\.css$/);
    return match ? match[1] : null;
  }

  function getPathname(url) {
    if (!url) return '';
    return new URL(url, location.origin).pathname;
  }

  function getReferenceNode() {
    return document.querySelector('noscript[data-n-css]');
  }

  function moveNodeBelowReference(node) {
    var ref = getReferenceNode();
    if (ref && ref.parentNode) {
      ref.parentNode.insertBefore(node, ref.nextSibling);
    }
  }

  function registerCssHash(pageUrl, href) {
    if (!pageUrl || !href) return;
    var hash = getHash(href);
    if (!hash) return;
    if (!cssHashMap[pageUrl]) cssHashMap[pageUrl] = {};
    cssHashMap[pageUrl][hash] = true;
  }

  function removeExpiredStyles() {
    var activeHashes = {};
    var currentHashes = currentUrl && cssHashMap[currentUrl] ? cssHashMap[currentUrl] : {};
    var previousHashes = previousUrl && cssHashMap[previousUrl] ? cssHashMap[previousUrl] : {};
    var key;
    for (key in currentHashes) activeHashes[key] = true;
    for (key in previousHashes) activeHashes[key] = true;

    var nodes = document.querySelectorAll(
      'head > link[data-n-p-perm], head > style[data-n-href-perm]'
    );
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      var href = node.nodeName === 'LINK'
        ? node.getAttribute('href')
        : node.getAttribute('data-n-href-perm');
      var hash = getHash(href);
      if (hash && !activeHashes[hash]) {
        node.parentNode.removeChild(node);
      }
    }
  }

  // Observe styles as they appear in the DOM and rename their attributes
  // so Next.js no longer targets them for removal.
  new MutationObserver(function (mutations) {
    for (var i = 0; i < mutations.length; i++) {
      var mutation = mutations[i];
      if (mutation.target.nodeName !== 'HEAD') continue;
      for (var j = 0; j < mutation.addedNodes.length; j++) {
        var el = mutation.addedNodes[j];
        // SSR-rendered page stylesheets
        if (el.nodeName === 'LINK' && el.hasAttribute('data-n-p')) {
          el.removeAttribute('data-n-p');
          el.setAttribute('data-n-p-perm', '');
          registerCssHash(currentUrl, el.getAttribute('href'));
        }
        // Client-side navigated page styles
        if (el.nodeName === 'STYLE' && el.hasAttribute('data-n-href')) {
          var href = el.getAttribute('data-n-href') || '';
          el.setAttribute('data-n-href-perm', href);
          el.removeAttribute('data-n-href');
          if (el.getAttribute('media') === 'x') {
            el.removeAttribute('media');
          }
          registerCssHash(currentUrl, href);
          moveNodeBelowReference(el);
        }
      }
    }
  }).observe(document.head, { childList: true, subtree: true });

  // Expose hooks for Next router integration
  window.__raiCssGuard = {
    onRouteChangeStart: function (url) {
      previousUrl = currentUrl;
      currentUrl = url;
    },
    onRouteChangeComplete: function () {
      if (getPathname(previousUrl) !== getPathname(currentUrl)) {
        removeExpiredStyles();
      }
      previousUrl = null;
    }
  };
})();
