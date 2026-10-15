// Shared poller for the live active-user count. Several active-count controllers
// can appear on one page (nav, headline, footer); rather than each polling the
// same endpoint, they subscribe here and share a single request per URL.
//
// The cadence is a single fixed constant — every count refreshes in lockstep and
// no caller can supply an interval, so there's nothing to validate or reconcile.
//
// Polling for a URL runs only while it has at least one subscriber. The last
// value and the time it was fetched are kept even after the count drops to zero
// subscribers, so visibility churn — e.g. scrolling between a top and a bottom
// count that are never on screen together — resumes on the existing schedule
// instead of firing a fresh request every time.

const POLL_INTERVAL_MS = 5000;

const feeds = new Map(); // src -> { timer, last, lastAt, subs:Set<fn> }

// Subscribe to a URL's total_active. `callback` fires with each new number (and
// immediately with the last known value, if any). Returns an unsubscribe fn.
export function subscribeToCount(src, callback) {
  let feed = feeds.get(src);
  if (!feed) {
    feed = { timer: null, last: undefined, lastAt: 0, subs: new Set() };
    feeds.set(src, feed);
  }
  feed.subs.add(callback);

  // Hand a late subscriber the latest value so it doesn't wait for a fetch.
  if (feed.last !== undefined) callback(feed.last);

  if (!feed.timer) schedule(src, feed);

  return () => {
    feed.subs.delete(callback);
    if (feed.subs.size === 0) {
      clearTimeout(feed.timer);
      feed.timer = null; // keep last/lastAt cached; just stop fetching
    }
  };
}

// Queue the next fetch. New URL fetches immediately; a resumed one waits out the
// remainder of its interval so churn doesn't trigger redundant requests.
function schedule(src, feed) {
  const delay =
    feed.last === undefined
      ? 0
      : Math.max(0, POLL_INTERVAL_MS - (performance.now() - feed.lastAt));
  feed.timer = setTimeout(() => tick(src, feed), delay);
}

async function tick(src, feed) {
  await poll(src, feed);
  feed.timer =
    feed.subs.size > 0 ? setTimeout(() => tick(src, feed), POLL_INTERVAL_MS) : null;
}

async function poll(src, feed) {
  try {
    const response = await fetch(src);
    if (!response.ok) return; // subscribers keep the last value
    const { total_active } = await response.json();
    if (typeof total_active !== 'number') return;
    feed.last = total_active;
    feed.lastAt = performance.now();
    for (const callback of feed.subs) callback(total_active);
  } catch {
    // Network hiccup — leave the last value in place.
  }
}
