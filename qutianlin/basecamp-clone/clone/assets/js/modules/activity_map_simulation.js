// Live world activity map — projection, day/night solar math, and the particle
// simulation that makes the map feel alive. Rendering is decoupled from the data:
// snapshots set slow-changing *targets*; this runs a continuous animation toward
// them, so the map stays alive between (and even without) data refreshes.
//
// Used by controllers/activity_map_controller.js, which owns the DOM, fetching,
// and visibility handling. Base continents come from modules/world_land.js.

import { WORLD_LAND } from './world_land.js';

// --- Projection (equirectangular / plate carree) ---------------------------
// Normalised coordinates: x in [0,1] for lon -180..180, y in [0,1] for the
// visible latitude window below. We crop only the empty band south of Antarctica
// (whose land data ends ~-80) so it sits flush with the bottom of the canvas.
// The frame's aspect-ratio in activity-map.css MUST equal 360 / LAT_SPAN.
const LAT_NORTH = 90;
const LAT_SOUTH = -82;
const LAT_SPAN = LAT_NORTH - LAT_SOUTH; // 172 → aspect-ratio 360/172 ≈ 2.093

export function projectNorm(lon, lat) {
  return { x: (lon + 180) / 360, y: (LAT_NORTH - lat) / LAT_SPAN };
}

// --- Day / night ------------------------------------------------------------
// Subsolar point: the lat/lon where the sun is directly overhead right now.

export function subsolarPoint(date) {
  const dayMs = 24 * 60 * 60 * 1000;
  const startOfYear = Date.UTC(date.getUTCFullYear(), 0, 0);
  const dayOfYear = (date - startOfYear) / dayMs;

  // Solar declination (deg) — simple, accurate to ~1 degree.
  const decl = 23.44 * Math.sin((2 * Math.PI * (dayOfYear - 81)) / 365);

  // Subsolar longitude tracks UTC time of day.
  const utcHours =
    date.getUTCHours() + date.getUTCMinutes() / 60 + date.getUTCSeconds() / 3600;
  let lon = -15 * (utcHours - 12);
  lon = ((lon + 540) % 360) - 180; // wrap to -180..180

  return { lat: decl, lon };
}

const DEG = Math.PI / 180;

// Illumination at a lon/lat: 1 = full day, 0 = full night, with a soft
// terminator. `sunVec` is the subsolar point's precomputed unit vector. Takes
// lon/lat (not normalised coords) so it's independent of the projection window.
export function dayFactor(lon, lat, sunVec) {
  const cl = Math.cos(lat * DEG);
  const px = cl * Math.cos(lon * DEG);
  const py = Math.sin(lat * DEG);
  const pz = cl * Math.sin(lon * DEG);
  const cos = px * sunVec.x + py * sunVec.y + pz * sunVec.z; // -1..1
  // Smooth the terminator over a few degrees of cosine either side of 0.
  const t = (cos + 0.12) / 0.24;
  return t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t);
}

function sunVector(sub) {
  const cl = Math.cos(sub.lat * DEG);
  return {
    x: cl * Math.cos(sub.lon * DEG),
    y: Math.sin(sub.lat * DEG),
    z: cl * Math.sin(sub.lon * DEG),
  };
}

// --- Helpers ----------------------------------------------------------------

const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const cellKey = (c) => `${c.lat.toFixed(3)},${c.lon.toFixed(3)}`;

// Deterministic-ish jitter seed per particle so each one animates on its own
// phase (no global flicker), without needing to store extra randomness.
function hashPhase(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 10000) / 10000; // 0..1
}

// --- The map ----------------------------------------------------------------

export class WorldActivityMap {
  constructor(canvas, options = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.reducedMotion = !!options.reducedMotion;

    // Colors are read from CSS custom properties on the canvas so the map themes
    // with the rest of the site. Solid colors only — alpha is applied at draw time.
    const styles = getComputedStyle(canvas);
    this.colors = {
      dot: (styles.getPropertyValue('--activity-dot') || '#1f7aec').trim(),
      land: (styles.getPropertyValue('--activity-land') || '#8aa0b8').trim(),
      night: (styles.getPropertyValue('--activity-night') || '#0b1f33').trim(),
    };

    // Radius mapping from a cell's active-user count `n`.
    this.minR = options.minRadius ?? 1.1;
    this.maxR = options.maxRadius ?? 7;
    this.radiusScale = options.radiusScale ?? 1.6; // px per log10(n)

    // Activity dots render at half size on narrow phones (30em is the
    // framework's phone breakpoint). Refreshed in resize() as the viewport
    // crosses the breakpoint; applied at draw time.
    this.mobileQuery = window.matchMedia('(max-width: 30em)');
    this.dotScale = 1;

    this.particles = new Map(); // key -> particle
    this.ripples = [];
    this.totalActive = 0;
    this.generatedAt = null;

    this.running = false;
    this.lastFrame = 0;
    this.lastRippleAt = 0;
    this.nightMinute = -1;

    // Offscreen layers (rebuilt on resize / time change, not every frame).
    this.baseLayer = document.createElement('canvas');
    this.nightLayer = document.createElement('canvas');

    // Low-res illumination buffer for a soft, correctly-curved terminator.
    this.illumW = 128;
    this.illumH = 64;

    this.resize();
  }

  // --- Sizing ---------------------------------------------------------------

  resize() {
    const rect = this.canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.cssW = Math.max(1, rect.width);
    this.cssH = Math.max(1, rect.height || rect.width / 2);
    this.dpr = dpr;

    for (const c of [this.canvas, this.baseLayer]) {
      c.width = Math.round(this.cssW * dpr);
      c.height = Math.round(this.cssH * dpr);
    }
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    this.dotScale = this.mobileQuery.matches ? 0.5 : 1;

    this.renderBaseLayer();
    this.nightMinute = -1; // force night layer rebuild
  }

  // Static dotted continents, drawn once per size into an offscreen layer.
  renderBaseLayer() {
    const { gw, gh, points } = WORLD_LAND;
    const ctx = this.baseLayer.getContext('2d');
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, this.cssW, this.cssH);
    ctx.fillStyle = this.colors.land;
    ctx.globalAlpha = 0.62;

    const r = clamp(Math.min(this.cssW / gw, this.cssH / gh) * 0.36, 0.6, 2.4);
    for (let i = 0; i < points.length; i += 2) {
      const lat = 90 - (points[i + 1] / gh) * 180;
      const ny = (LAT_NORTH - lat) / LAT_SPAN;
      if (ny > 1) continue; // below the visible crop (Antarctica / deep south)
      const x = (points[i] / gw) * this.cssW;
      const y = ny * this.cssH;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // Soft day/night wash, rebuilt at most once per minute.
  renderNightLayer(date) {
    const minute = Math.floor(date.getTime() / 60000);
    if (minute === this.nightMinute) return;
    this.nightMinute = minute;

    const W = this.illumW;
    const H = this.illumH;
    const buf = document.createElement('canvas');
    buf.width = W;
    buf.height = H;
    const bctx = buf.getContext('2d');
    const img = bctx.createImageData(W, H);
    const sun = sunVector(subsolarPoint(date));

    // Night color channels.
    const c = this.colors.night;
    const rgb = parseColorToRgb(c) || { r: 11, g: 31, b: 51 };

    for (let y = 0; y < H; y++) {
      const lat = LAT_NORTH - ((y + 0.5) / H) * LAT_SPAN;
      for (let x = 0; x < W; x++) {
        const lon = ((x + 0.5) / W) * 360 - 180;
        const day = dayFactor(lon, lat, sun);
        const night = 1 - day;
        const a = Math.round(night * 140); // max night darkness (0..255)
        const o = (y * W + x) * 4;
        img.data[o] = rgb.r;
        img.data[o + 1] = rgb.g;
        img.data[o + 2] = rgb.b;
        img.data[o + 3] = a;
      }
    }
    bctx.putImageData(img, 0, 0);

    // Scale up smoothly into a full-size layer for a feathered terminator.
    this.nightLayer.width = Math.round(this.cssW * this.dpr);
    this.nightLayer.height = Math.round(this.cssH * this.dpr);
    const nctx = this.nightLayer.getContext('2d');
    nctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    nctx.clearRect(0, 0, this.cssW, this.cssH);
    nctx.imageSmoothingEnabled = true;
    nctx.drawImage(buf, 0, 0, W, H, 0, 0, this.cssW, this.cssH);
  }

  // --- Data -----------------------------------------------------------------

  setSnapshot(snapshot) {
    if (!snapshot || !Array.isArray(snapshot.cells)) return;
    this.totalActive = snapshot.total_active ?? null;
    this.generatedAt = snapshot.generated_at ?? null;

    const seen = new Set();
    for (const cell of snapshot.cells) {
      if (typeof cell.lat !== 'number' || typeof cell.lon !== 'number') continue;
      const key = cellKey(cell);
      seen.add(key);
      const { x, y } = projectNorm(cell.lon, cell.lat);
      const targetR = clamp(
        this.minR + Math.log10(Math.max(1, cell.n || 1)) * this.radiusScale,
        this.minR,
        this.maxR
      );

      let p = this.particles.get(key);
      if (p) {
        p.targetR = targetR;
        p.n = cell.n;
        p.targetAlpha = 1;
        p.dying = false;
      } else {
        // New place: spawn from nothing so additions fade/grow in.
        const ph = hashPhase(key);
        this.particles.set(key, {
          key,
          nx: x,
          ny: y,
          n: cell.n,
          r: 0,
          targetR,
          alpha: 0,
          targetAlpha: 1,
          dying: false,
          phase: ph * Math.PI * 2,
          pulseRate: 0.8 + ph * 1.6, // rad/s, desynchronised per place
          pulseAmp: 0.12 + ph * 0.12,
          jitterPhase: hashPhase(key + 'j') * Math.PI * 2,
        });
      }
    }

    // Places no longer present fade out, then get removed.
    for (const [key, p] of this.particles) {
      if (!seen.has(key)) {
        p.dying = true;
        p.targetAlpha = 0;
        p.targetR = 0;
      }
    }
  }

  // --- Animation loop -------------------------------------------------------

  start() {
    if (this.running) return;
    this.running = true;
    this.lastFrame = 0;
    this._tick = (t) => {
      if (!this.running) return;
      this.frame(t);
      this._raf = requestAnimationFrame(this._tick);
    };
    this._raf = requestAnimationFrame(this._tick);
  }

  stop() {
    this.running = false;
    if (this._raf) cancelAnimationFrame(this._raf);
  }

  frame(timeMs) {
    const now = timeMs || 0;
    let dt = this.lastFrame ? (now - this.lastFrame) / 1000 : 0;
    this.lastFrame = now;
    dt = clamp(dt, 0, 0.05); // guard against tab-resume jumps
    const tSec = now / 1000;

    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.cssW, this.cssH);

    // Layer 1: continents.
    ctx.drawImage(this.baseLayer, 0, 0, this.cssW, this.cssH);

    // Layer 2: day/night wash.
    this.renderNightLayer(new Date());
    ctx.drawImage(this.nightLayer, 0, 0, this.cssW, this.cssH);

    // Layer 3: activity.
    this.drawParticles(ctx, tSec, dt);
    this.drawRipples(ctx, dt, now);
  }

  drawParticles(ctx, tSec, dt) {
    const ease = this.reducedMotion ? 1 : clamp(dt * 3.5, 0, 1);
    ctx.fillStyle = this.colors.dot;

    for (const [key, p] of this.particles) {
      // Ease radius/alpha toward targets (smooth snapshot transitions).
      p.r += (p.targetR - p.r) * ease;
      p.alpha += (p.targetAlpha - p.alpha) * ease;
      if (p.dying && p.alpha < 0.02) {
        this.particles.delete(key);
        continue;
      }

      let r = p.r * this.dotScale;
      let a = p.alpha;
      let x = p.nx * this.cssW;
      let y = p.ny * this.cssH;

      if (!this.reducedMotion) {
        const pulse = Math.sin(tSec * p.pulseRate + p.phase);
        r *= 1 + p.pulseAmp * pulse;
        a *= 0.75 + 0.25 * (0.5 + 0.5 * pulse);
        const j = 0.6;
        x += Math.sin(tSec * 0.6 + p.jitterPhase) * j;
        y += Math.cos(tSec * 0.5 + p.jitterPhase) * j;
      }
      if (r <= 0.05 || a <= 0.01) continue;

      // Soft halo + bright core, cheap (two arcs, no per-dot gradient).
      ctx.globalAlpha = a * 0.28;
      ctx.beginPath();
      ctx.arc(x, y, r * 2.1, 0, Math.PI * 2);
      ctx.fill();

      ctx.globalAlpha = a;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // Occasional expanding rings on busy places — reads as "new activity now".
  drawRipples(ctx, dt, nowMs) {
    if (!this.reducedMotion) {
      // Spawn rate scales gently with how many places are active.
      const interval = clamp(900 - this.particles.size * 1.5, 220, 900);
      if (nowMs - this.lastRippleAt > interval) {
        this.lastRippleAt = nowMs;
        this.spawnRipple();
      }
    }

    ctx.strokeStyle = this.colors.dot;
    for (let i = this.ripples.length - 1; i >= 0; i--) {
      const rp = this.ripples[i];
      rp.age += dt;
      const k = rp.age / rp.life;
      if (k >= 1) {
        this.ripples.splice(i, 1);
        continue;
      }
      ctx.globalAlpha = (1 - k) * 0.5;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.arc(
        rp.nx * this.cssW,
        rp.ny * this.cssH,
        (rp.baseR + k * rp.maxR) * this.dotScale,
        0,
        Math.PI * 2
      );
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  spawnRipple() {
    // Weight selection toward busier places.
    const live = [];
    let total = 0;
    for (const p of this.particles.values()) {
      if (p.dying || p.alpha < 0.5) continue;
      const w = Math.max(1, p.n || 1);
      total += w;
      live.push({ p, acc: total });
    }
    if (!live.length) return;
    const pick = Math.random() * total;
    const chosen = live.find((e) => e.acc >= pick) || live[live.length - 1];
    const p = chosen.p;
    this.ripples.push({
      nx: p.nx,
      ny: p.ny,
      age: 0,
      life: 1.6,
      baseR: p.r,
      maxR: 14,
    });
  }
}

// Parse "#rrggbb" / "rgb(...)" to channels for the night ImageData. Returns null
// for color spaces we can't read here (e.g. oklch); callers fall back to a default.
function parseColorToRgb(str) {
  if (!str) return null;
  str = str.trim();
  if (str[0] === '#') {
    let h = str.slice(1);
    if (h.length === 3) h = h.split('').map((c) => c + c).join('');
    if (h.length !== 6) return null;
    return {
      r: parseInt(h.slice(0, 2), 16),
      g: parseInt(h.slice(2, 4), 16),
      b: parseInt(h.slice(4, 6), 16),
    };
  }
  const m = str.match(/rgba?\(([^)]+)\)/);
  if (m) {
    const parts = m[1].split(/[ ,/]+/).map(Number);
    return { r: parts[0], g: parts[1], b: parts[2] };
  }
  return null;
}
