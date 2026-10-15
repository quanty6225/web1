import { Controller } from './../packages/stimulus.js';
import { subscribeToCount } from './../modules/live_count_poll.js';
import './../packages/number-flow.js';

const FLOW_STYLES = `
  .digit__num,
  .symbol__value {
    text-decoration-color: var(--active-count-decoration-color, currentColor);
    text-decoration-line: var(--active-count-decoration-line, none);
    text-decoration-thickness: var(--active-count-decoration-thickness, auto);
    text-underline-offset: var(--active-count-underline-offset, auto);
    transition: text-decoration-color var(--transition, 0s);
  }
`;

// Replaces the fallback with NumberFlow once the shared poller returns a real
// total. Polling only runs while the element is on screen and the document is
// visible.

export default class extends Controller {
  static targets = ['count'];
  static values = {
    src: {
      type: String,
      default: '/static/live/live_usage_total.json',
    },
  };

  connect() {
    if (!this.hasCountTarget) return;

    this.element.classList.remove('live-ready');
    this.flow = document.createElement('number-flow');
    this.flow.trend = 0;
    this.flowStylesInstalled = false;
    this.countTarget.replaceChildren(
      this.flow,
      document.createTextNode(' people')
    );

    this.onScreen = false;

    this.intersectionObserver = new IntersectionObserver(([entry]) => {
      this.onScreen = entry.isIntersecting;
      this.updateRunning();
    });
    this.intersectionObserver.observe(this.element);

    this.onVisibility = () => this.updateRunning();
    document.addEventListener('visibilitychange', this.onVisibility);
  }

  disconnect() {
    this.stopPolling();
    this.intersectionObserver?.disconnect();
    document.removeEventListener('visibilitychange', this.onVisibility);
  }

  updateRunning() {
    if (this.onScreen && !document.hidden) {
      if (!this.unsubscribe) {
        this.unsubscribe = subscribeToCount(this.srcValue, (total) => this.onCount(total));
      }
    } else {
      this.stopPolling();
    }
  }

  stopPolling() {
    this.unsubscribe?.();
    this.unsubscribe = null;
  }

  onCount(total) {
    if (typeof total !== 'number') return;

    this.flow.update(total);
    this.installFlowStyles();
    this.element.classList.add('live-ready');
  }

  installFlowStyles() {
    if (this.flowStylesInstalled) return;

    const style = document.createElement('style');
    style.textContent = FLOW_STYLES;
    this.flow.shadowRoot.append(style);
    this.flowStylesInstalled = true;
  }
}
