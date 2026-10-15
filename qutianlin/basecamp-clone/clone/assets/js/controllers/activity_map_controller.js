import { Controller } from './../packages/stimulus.js';
import {
  WorldActivityMap,
  projectNorm,
} from './../modules/activity_map_simulation.js';

// Drives the live world activity map: owns the canvas element, plays the feed,
// pauses work when the map isn't visible, and shows a tooltip over one random
// place each refresh. All of the animation/projection/day-night logic lives in
// the simulation module.
//
// On load it pulls the last few snapshots in one request and cycles through
// them (an intro that plays the map "catching up"), then settles into polling a
// single fresh snapshot on a slower cadence. Snapshots are deduped by their
// generated_at, so neither phase renders the same one twice.
//
// Markup: see _includes/activity-map.html.
export default class extends Controller {
  static targets = [
    'canvas',
    'frame',
    'tooltip',
    'tooltipFlag',
    'tooltipCity',
    'tooltipCountry',
  ];
  static values = {
    src: {
      type: String,
      default: '/static/live/live_usage.json',
    },
    introCount: { type: Number, default: 4 }, // snapshots pulled in one request on load
    introInterval: { type: Number, default: 3000 }, // gap while cycling the intro
    interval: { type: Number, default: 5000 }, // steady single-snapshot poll
  };

  connect() {
    this.reducedMotion = window.matchMedia(
      '(prefers-reduced-motion: reduce)'
    ).matches;

    this.map = new WorldActivityMap(this.canvasTarget, {
      reducedMotion: this.reducedMotion,
    });

    this.resizeObserver = new ResizeObserver(() => {
      this.map.resize();
      this.positionTooltip(); // keep the callout pinned to its dot
    });
    this.resizeObserver.observe(this.canvasTarget);

    // Only animate while on screen and the tab is visible.
    this.intersectionObserver = new IntersectionObserver(
      (entries) => {
        this.onScreen = entries[0].isIntersecting;
        this.updateRunning();
      },
      { threshold: 0.01 }
    );
    this.intersectionObserver.observe(this.element);

    this.onVisibility = () => this.updateRunning();
    document.addEventListener('visibilitychange', this.onVisibility);

    this.shown = new Set(); // generated_at values already rendered
    this.onScreen = false;
    // Fetching and animation are kicked off by updateRunning() once the map is
    // actually visible, so a background tab never polls the feed.
  }

  disconnect() {
    this.map?.stop();
    clearInterval(this.polling);
    clearTimeout(this.introTimer);
    clearTimeout(this.tooltipTimer);
    clearTimeout(this.tooltipHideTimer);
    this.resizeObserver?.disconnect();
    this.intersectionObserver?.disconnect();
    document.removeEventListener('visibilitychange', this.onVisibility);
  }

  updateRunning() {
    const shouldRun = this.onScreen && !document.hidden;
    if (shouldRun === this.running) return;
    this.running = shouldRun;
    if (shouldRun) {
      this.map.start();
      this.startTooltipCycle();
      this.startFeed();
    } else {
      this.map.stop();
      this.stopTooltipCycle();
      this.stopFeed();
    }
  }

  // Start (or resume) pulling the feed. The first run plays the intro and then
  // settles into polling; later resumes skip the intro and just poll again.
  startFeed() {
    if (this.started) {
      if (!this.polling) this.poll();
    } else {
      this.started = true;
      this.playRecentThenPoll();
    }
  }

  // Stop all feed activity so a hidden/offscreen map makes no network requests.
  stopFeed() {
    clearTimeout(this.introTimer);
    clearInterval(this.polling);
    this.polling = null;
  }

  async playRecentThenPoll() {
    const oldestFirst = (await this.fetchSnapshots(this.introCountValue)).reverse();
    this.cycle(oldestFirst);
  }

  cycle(snapshots) {
    this.renderOnce(snapshots.shift());
    this.introTimer = setTimeout(
      () => (snapshots.length ? this.cycle(snapshots) : this.poll()),
      this.introIntervalValue
    );
  }

  poll() {
    this.refresh();
    this.polling = setInterval(() => this.refresh(), this.intervalValue);
  }

  async refresh() {
    const [latest] = await this.fetchSnapshots(1);
    this.renderOnce(latest);
  }

  async fetchSnapshots(count) {
    try {
      const url = new URL(this.srcValue, window.location.href);
      url.searchParams.set('snapshots', count);
      const response = await fetch(url);
      return response.ok ? (await response.json()).snapshots ?? [] : [];
    } catch {
      return []; // keep animating last-known data
    }
  }

  renderOnce(snapshot) {
    if (!snapshot || this.shown.has(snapshot.generated_at)) return;
    this.shown.add(snapshot.generated_at);

    this.map.setSnapshot(snapshot);
    this.labeledCells = (snapshot.cells || []).filter((c) => c.city && c.cc);
  }

  // --- Tooltip --------------------------------------------------------------
  //
  // The tooltip runs on its own rhythm, independent of the data refresh: show a
  // city, hold it for 1.5s, fade out, wait 0.5s, then show another.
  // (See the TOOLTIP_* constants below.)

  static TOOLTIP_HOLD = 1500; // visible duration
  static TOOLTIP_GAP = 500; // pause between cities
  static TOOLTIP_FADE = 300; // must match the CSS opacity transition

  startTooltipCycle() {
    if (this.tooltipCycleActive) return;
    this.tooltipCycleActive = true;
    this.queueTooltip(this.constructor.TOOLTIP_GAP);
  }

  stopTooltipCycle() {
    this.tooltipCycleActive = false;
    clearTimeout(this.tooltipTimer);
    this.hideTooltip();
  }

  queueTooltip(delay) {
    clearTimeout(this.tooltipTimer);
    this.tooltipTimer = setTimeout(() => this.runTooltipCycle(), delay);
  }

  runTooltipCycle() {
    if (!this.tooltipCycleActive) return;
    if (!this.showRandomTooltip()) {
      this.queueTooltip(this.constructor.TOOLTIP_GAP); // no data yet, retry
      return;
    }
    this.tooltipTimer = setTimeout(() => {
      this.hideTooltip();
      this.queueTooltip(this.constructor.TOOLTIP_GAP);
    }, this.constructor.TOOLTIP_HOLD);
  }

  // Pick one labeled place (weighted toward busier ones so the callout tends to
  // land on a prominent dot) and surface it. Returns false if there's nothing
  // to show yet.
  showRandomTooltip() {
    if (!this.hasTooltipTarget) return false;
    const labeled = this.labeledCells;
    if (!labeled || !labeled.length) return false;

    let total = 0;
    const weighted = labeled.map((c) => {
      total += Math.max(1, c.n || 1);
      return { c, acc: total };
    });
    const pick = Math.random() * total;
    const cell = (weighted.find((e) => e.acc >= pick) || weighted.at(-1)).c;

    this.activeCell = cell;
    this.tooltipFlagTarget.textContent = flagEmoji(cell.cc);
    this.tooltipCityTarget.textContent = cell.city;
    this.tooltipCountryTarget.textContent = cell.country || '';

    clearTimeout(this.tooltipHideTimer);
    this.tooltipTarget.hidden = false;
    this.positionTooltip();
    // Force a reflow before adding the class so the fade-in transition runs.
    void this.tooltipTarget.offsetWidth;
    this.tooltipTarget.classList.add('is-visible');
    return true;
  }

  hideTooltip() {
    if (!this.hasTooltipTarget) return;
    this.tooltipTarget.classList.remove('is-visible'); // fade out
    this.activeCell = null;
    // Pull it from the a11y tree only after the fade completes.
    clearTimeout(this.tooltipHideTimer);
    this.tooltipHideTimer = setTimeout(() => {
      this.tooltipTarget.hidden = true;
    }, this.constructor.TOOLTIP_FADE);
  }

  // Anchor the tooltip to its dot's pixel position, clamped inside the frame.
  // The pointer (an ::after element) is offset via --arrow-left so it keeps
  // aiming at the dot even when the box is nudged away from an edge.
  positionTooltip() {
    if (!this.activeCell || !this.hasFrameTarget || this.tooltipTarget.hidden) {
      return;
    }
    const frameW = this.frameTarget.clientWidth;
    const frameH = this.frameTarget.clientHeight;
    if (frameW < 10 || frameH < 10) return;

    const { x, y } = projectNorm(this.activeCell.lon, this.activeCell.lat);
    const dotX = x * frameW;
    const dotY = y * frameH;

    const pad = 8;
    const gap = 12;
    const tip = this.tooltipTarget;
    const tipW = tip.offsetWidth;
    const tipH = tip.offsetHeight;

    let left = Math.round(dotX - tipW / 2);
    left = Math.max(pad, Math.min(left, frameW - tipW - pad));

    // Prefer above the dot; flip below when there's no room.
    const below = dotY - tipH - gap < pad;
    let top = below ? Math.round(dotY + gap) : Math.round(dotY - tipH - gap);
    top = Math.max(pad, Math.min(top, frameH - tipH - pad));

    tip.classList.toggle('activity-map__tooltip--below', below);
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
    const arrowLeft = Math.max(12, Math.min(dotX - left, tipW - 12));
    tip.style.setProperty('--arrow-left', `${arrowLeft}px`);
  }
}

// ISO 3166-1 alpha-2 -> regional-indicator flag emoji (e.g. "US" -> 🇺🇸).
function flagEmoji(cc) {
  if (typeof cc !== 'string' || cc.length !== 2) return '';
  const base = 0x1f1e6;
  const A = 'A'.charCodeAt(0);
  const up = cc.toUpperCase();
  return String.fromCodePoint(
    base + (up.charCodeAt(0) - A),
    base + (up.charCodeAt(1) - A)
  );
}
