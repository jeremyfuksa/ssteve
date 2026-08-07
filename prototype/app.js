/* =========================================================================
   SSTeVe prototype — behaviour layer

   ALL DATA HERE IS SYNTHETIC except the decoded images themselves, which are
   real reference captures from sstv_core/tests/reference/images/ariss/ (ISS
   SSTV events, Oct 2020) and .../mmsstv/. Callsigns, SNR figures, RMS levels
   and device names are AUTHORED DEMONSTRATION DATA — see PRODUCT.md
   "Absent — must not be fabricated". Nothing here talks to the real backend.
   ========================================================================= */

'use strict';

const $ = (id) => document.getElementById(id);
const app = $('app');

/* =========================================================================
   Mode geometry — the real roster, from backend-spec.md MODE_TIMINGS.
   Scottie/Martin/Robot are implemented today; the PD family is post-MVP
   (PRODUCT.md) but sizes the canvas problem, so the display rule must
   already handle it. Native width spans 320 to 640 and aspect spans
   4:3 to 5:4, which is why the canvas cannot carry a fixed aspect-ratio.
   ========================================================================= */
const MODES = {
  'Scottie S1': { w: 320, h: 256, secs: 110 },
  'Scottie S2': { w: 320, h: 256, secs: 71 },
  'Scottie DX': { w: 320, h: 256, secs: 269 },
  'Martin M1':  { w: 320, h: 256, secs: 114 },
  'Martin M2':  { w: 320, h: 256, secs: 58 },
  'Robot 36':   { w: 320, h: 240, secs: 36 },
  'Robot 72':   { w: 320, h: 240, secs: 72 },
  'PD90':       { w: 320, h: 256, secs: 90 },
  'PD120':      { w: 640, h: 496, secs: 126 },
  'PD180':      { w: 640, h: 496, secs: 187 },
  'PD240':      { w: 640, h: 496, secs: 248 }
};

/* ONE FIXED CANVAS BOX. Every mode centres inside it; the frame never moves.

   The box is sized to contain the whole roster. Normalised to a common scale,
   the widest-relative mode is Robot 36 (4:3) and the tallest-relative is
   Scottie/Martin/PD90 (5:4), so the box takes the max of both axes:
   320 wide x 256 tall at native, doubled for legibility.

   Robot 36 then sits in it with 16px bands above and below at 2x. That is a
   deliberate trade: a little unused canvas on the shorter modes buys a frame
   that does not resize when the mode changes, a layout with no circular
   dependency between canvas and column, and whole-number pixel scaling
   throughout — an SSTV capture is noisy, and interpolating it makes a
   marginal decode look better than it was. */
const CANVAS_SCALE = 2;
const CANVAS_BOX_W = 320 * CANVAS_SCALE;   // 640
const CANVAS_BOX_H = 256 * CANVAS_SCALE;   // 512

/* Where a mode's picture sits inside the fixed box. PD modes are natively
   640x496, so they render at 1x and still fit; everything else doubles. */
function placeInBox(mode) {
  const m = MODES[mode] || MODES['Scottie S1'];
  const scale = m.w > 320 ? 1 : CANVAS_SCALE;
  const w = m.w * scale;
  const h = m.h * scale;
  return {
    w, h, scale, native: m,
    x: Math.round((CANVAS_BOX_W - w) / 2),
    y: Math.round((CANVAS_BOX_H - h) / 2)
  };
}

/* --- reference captures (real files, real dates from their filenames) ---- */
const CAPTURES = [
  { src: 'assets/ariss-20201007-1858.jpg', utc: '18:58', date: '2020-10-07', mode: 'Scottie S1', lines: 256 },
  { src: 'assets/ariss-20201007-2033.jpg', utc: '20:33', date: '2020-10-07', mode: 'Scottie S1', lines: 256 },
  { src: 'assets/ariss-20201004-1620.jpg', utc: '16:20', date: '2020-10-04', mode: 'Martin M1',  lines: 256 },
  { src: 'assets/ariss-20201004-1445.jpg', utc: '14:45', date: '2020-10-04', mode: 'Scottie S1', lines: 256 },
  { src: 'assets/ariss-20201008-0124.jpg', utc: '01:24', date: '2020-10-08', mode: 'Robot 36',   lines: 240 },
  { src: 'assets/partial-ariss-20201004-1624.jpg', utc: '16:24', date: '2020-10-04', mode: 'Scottie S1', lines: 148, partial: true },
  { src: 'assets/shack.jpg', utc: '09:12', date: '2020-10-02', mode: 'Scottie S1', lines: 256 },
  { src: 'assets/tn_colour-bars.jpg', utc: '08:00', date: '2020-10-02', mode: 'Martin M1', lines: 256 }
];

/* synthetic callsigns — clearly demo material, not real logged contacts */
const DEMO_CALLS = ['DL2ABC', 'JA1XYZ', 'VK3QRS', 'G4MNO', 'PY2TUV', null, 'W0XYZ', null];

/* =========================================================================
   State
   ========================================================================= */

const S = {
  view: 'capture',
  conditions: 'standard',
  phase: 'idle',            // idle | listening | vis | decoding | locked | tx
  progress: 0,
  elapsed: 0,
  log: [],
  seq: 0,
  capIndex: 0,
  overrides: {},            // control key -> operator-set value
  txIndex: 0,
  reduced: window.matchMedia('(prefers-reduced-motion: reduce)').matches
};

/* =========================================================================
   Control definitions — the table IS the control surface
   ========================================================================= */

const RX_CONTROLS = [
  { key: 'mode',    name: 'SSTV mode', type: 'seg',   auto: 'Auto',     opts: ['Auto', 'Scottie S1', 'Martin M1', 'Robot 36'], range: 'VIS-detected' },
  { key: 'device',  name: 'Input',     type: 'seg',   auto: null,       opts: ['Digirig', 'SignaLink', 'Built-in'], set: 'Digirig', range: 'USB audio' },
  { key: 'gain',    name: 'Gain',      type: 'num',   auto: '112',      unit: '%',  range: '0–200', min: 0, max: 200 },
  { key: 'squelch', name: 'Squelch',   type: 'num',   auto: '-41',      unit: 'dB', range: '−60–0', min: -60, max: 0 },
  { key: 'afc',     name: 'AFC',       type: 'seg',   auto: '±100',     opts: ['Off', '±50', '±100', '±200'], range: 'Hz' },
  { key: 'offset',  name: 'Offset',    type: 'num',   auto: '0',        unit: 'Hz', range: '±500', min: -500, max: 500 },
  { key: 'slant',   name: 'Slant',     type: 'seg',   auto: 'Auto',     opts: ['Auto', 'Manual'], range: 'Hough' }
];

const TX_CONTROLS = [
  { key: 'txmode',  name: 'SSTV mode', type: 'seg', opts: ['Scottie S1', 'Martin M1', 'Robot 36'], set: 'Scottie S1', range: '110 / 114 / 36 s' },
  { key: 'txdev',   name: 'Output',    type: 'seg', opts: ['Digirig', 'SignaLink', 'Built-in'], set: 'Digirig', range: 'USB audio' },
  { key: 'ptt',     name: 'PTT',       type: 'seg', opts: ['Serial RTS', 'Serial DTR', 'VOX'], set: 'Serial RTS', range: 'pyserial' },
  { key: 'txgain',  name: 'Drive',     type: 'num', auto: '85', unit: '%', range: '0–100', min: 0, max: 100 },
  { key: 'fskid',   name: 'FSKID',     type: 'seg', opts: ['On', 'Off'], set: 'On', range: 'Part 97' }
];

const DEV_AUDIO = [
  { key: 'inDev',   name: 'Input device',  type: 'seg', opts: ['Digirig', 'SignaLink', 'Built-in'], set: 'Digirig', range: '48 kHz' },
  { key: 'outDev',  name: 'Output device', type: 'seg', opts: ['Digirig', 'SignaLink', 'Built-in'], set: 'Digirig', range: '48 kHz' },
  { key: 'sr',      name: 'Sample rate',   type: 'seg', opts: ['44100', '48000'], set: '48000', range: 'Hz' },
  { key: 'fft',     name: 'FFT size',      type: 'seg', opts: ['512', '1024', '2048'], set: '1024', range: 'bins' }
];

const DEV_PTT = [
  { key: 'pttMode', name: 'PTT method',  type: 'seg', opts: ['Serial RTS', 'Serial DTR', 'VOX'], set: 'Serial RTS', range: '' },
  { key: 'pttPort', name: 'Serial port', type: 'seg', opts: ['usbserial-A1', 'usbmodem14201'], set: 'usbserial-A1', range: 'tty' },
  { key: 'preD',    name: 'Pre-delay',   type: 'num', auto: '500', unit: 'ms', range: '0–2000', min: 0, max: 2000 },
  { key: 'postD',   name: 'Post-delay',  type: 'num', auto: '200', unit: 'ms', range: '0–2000', min: 0, max: 2000 },
  { key: 'call',    name: 'Callsign',    type: 'text', set: 'W0XYZ', range: 'Part 97' },
  { key: 'saveDir', name: 'Save to',     type: 'text', set: '~/sstv_images', range: 'path' }
];

/* =========================================================================
   Control table rendering
   ========================================================================= */

function ctlValue(c) {
  if (S.overrides[c.key] !== undefined) return S.overrides[c.key];
  if (c.set !== undefined) return c.set;
  return null;
}

function buildTable(tbody, defs) {
  tbody.replaceChildren();
  defs.forEach((c) => {
    const tr = document.createElement('tr');

    const th = document.createElement('td');
    th.className = 'name';
    th.textContent = c.name;
    tr.appendChild(th);

    const auto = document.createElement('td');
    auto.className = 'auto';
    auto.textContent = c.auto ? c.auto + (c.unit ? ' ' + c.unit : '') : '—';
    tr.appendChild(auto);

    const set = document.createElement('td');
    set.className = 'set';
    const v = ctlValue(c);
    if (v !== null && v !== undefined) set.dataset.overridden = '1';

    if (c.type === 'seg') {
      const g = document.createElement('div');
      g.className = 'segset';
      g.setAttribute('role', 'group');
      g.setAttribute('aria-label', c.name);
      c.opts.forEach((o) => {
        const b = document.createElement('button');
        b.type = 'button';
        b.textContent = o;
        b.setAttribute('aria-pressed', String(v === o || (v == null && c.auto === o)));
        b.addEventListener('click', () => {
          S.overrides[c.key] = o;
          if (c.key === 'mode') announce('Mode set to ' + o);
          if (c.key === 'txmode') { syncTxMeta(o); paintTx(S.txIndex); }
          if (c.key === 'call') {}
          rebuildAll();
        });
        g.appendChild(b);
      });
      set.appendChild(g);
      set.style.textAlign = 'left';
    } else if (c.type === 'num') {
      const i = document.createElement('input');
      i.type = 'number';
      i.value = v !== null && v !== undefined ? v : (c.auto ?? '');
      i.min = c.min; i.max = c.max;
      i.setAttribute('aria-label', c.name + (c.unit ? ' in ' + c.unit : ''));
      i.addEventListener('change', () => {
        S.overrides[c.key] = i.value;
        announce(c.name + ' set to ' + i.value + (c.unit ? ' ' + c.unit : ''));
        rebuildAll();
      });
      set.appendChild(i);
      if (c.unit) { const u = document.createElement('span'); u.className = 'dim'; u.textContent = ' ' + c.unit; set.appendChild(u); }
    } else {
      const i = document.createElement('input');
      i.type = 'text';
      i.value = v ?? '';
      i.style.width = '9em';
      i.setAttribute('aria-label', c.name);
      i.addEventListener('change', () => {
        S.overrides[c.key] = i.value;
        if (c.key === 'call') { $('myCall').textContent = i.value; $('txOverlay').textContent = i.value; }
        rebuildAll();
      });
      set.appendChild(i);
    }

    // revert-to-auto: only meaningful when the machine has an opinion
    if (c.auto && S.overrides[c.key] !== undefined) {
      const r = document.createElement('button');
      r.type = 'button'; r.className = 'revert'; r.textContent = 'auto';
      r.title = 'Revert to auto-detected value';
      r.addEventListener('click', () => { delete S.overrides[c.key]; announce(c.name + ' reverted to auto'); rebuildAll(); });
      set.appendChild(r);
    }

    tr.appendChild(set);

    const range = document.createElement('td');
    range.className = 'range';
    range.textContent = c.range || '';
    tr.appendChild(range);

    tbody.appendChild(tr);
  });
}

function rebuildAll() {
  buildTable($('setAudio'), DEV_AUDIO);
  buildTable($('setPtt'), DEV_PTT);
}

function syncTxMeta(mode) {
  const dur = mode === 'Robot 36' ? '36 s' : mode === 'Martin M1' ? '114 s' : '110 s';
  $('txMode').textContent = mode;
  $('txDur').textContent = dur;
}

/* =========================================================================
   The signature move: a field typesets into its column.
   Fields flap briefly (split-flap character), then set at a confidence weight.
   ========================================================================= */

function typeset(el, text, conf, delay = 0) {
  return new Promise((resolve) => {
    setTimeout(() => {
      if (S.reduced) { el.textContent = text; el.dataset.conf = conf; resolve(); return; }
      el.dataset.flap = '1';
      const pool = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ·-';
      let ticks = 0;
      const total = 7;
      const iv = setInterval(() => {
        ticks++;
        el.textContent = text.split('').map((ch, i) =>
          (i < (ticks / total) * text.length || ch === ' ' || ch === ':')
            ? ch
            : pool[(Math.random() * pool.length) | 0]
        ).join('');
        if (ticks >= total) {
          clearInterval(iv);
          el.textContent = text;
          el.dataset.conf = conf;
          delete el.dataset.flap;
          resolve();
        }
      }, 55);
    }, delay);
  });
}

function resetArrival() {
  ['aTime', 'aMode', 'aCall', 'aSnr', 'aSlant', 'aLines'].forEach((id) => {
    const el = $(id);
    el.textContent = '—';
    el.dataset.conf = 'unknown';
    delete el.dataset.flap;
  });
}

/* =========================================================================
   Canvas — scanline reveal of a real reference capture
   ========================================================================= */

const cv = $('canvas');
const cx = cv.getContext('2d', { willReadFrequently: false });
let curImg = null;
let curMode = 'Scottie S1';
let curPlace = null;      // where the active mode sits inside the fixed box

/* The box is a constant, so this only records where the current mode sits
   inside it. No measuring, no feedback loop with the grid. */
function sizeCanvas(mode) {
  curMode = MODES[mode] ? mode : curMode;
  const d = placeInBox(curMode);

  // backing store is the fixed box; the picture is drawn into it at an offset
  if (cv.width !== CANVAS_BOX_W || cv.height !== CANVAS_BOX_H) {
    cv.width = CANVAS_BOX_W;
    cv.height = CANVAS_BOX_H;
  }
  curPlace = d;

  // say what the operator is looking at: native resolution and pixel scale
  const note = $('scaleNote');
  note.textContent = `${d.native.w}x${d.native.h} · ${d.scale}x`;
  note.hidden = false;
  return d;
}

/* The canvas is the largest light-emitting surface in the app, so it must
   follow Operating Conditions like everything else — Night Vision cannot
   suppress blue in the chrome and then paint a cool grey slab here. */
function themeColors() {
  const cs = getComputedStyle(app);
  return {
    board: cs.getPropertyValue('--board').trim(),
    rule: cs.getPropertyValue('--ink-3').trim(),
    head: cs.getPropertyValue('--alert').trim(),
    sweep: cs.getPropertyValue('--sig-2').trim()
  };
}

function paintIdle() {
  const t = themeColors();
  if (!curPlace) sizeCanvas(curMode);
  const p = curPlace;

  // the box's own ground, including the bands a shorter mode leaves
  cx.fillStyle = t.board;
  cx.fillRect(0, 0, cv.width, cv.height);

  // ruled placeholder inside the picture area — never a blank canvas (§20.4)
  cx.globalAlpha = 0.22;
  cx.strokeStyle = t.rule;
  cx.lineWidth = 1;
  for (let y = p.y + 8; y < p.y + p.h; y += 16) {
    cx.beginPath(); cx.moveTo(p.x, y + 0.5); cx.lineTo(p.x + p.w, y + 0.5); cx.stroke();
  }
  cx.globalAlpha = 1;

  // mark where the picture will land when the mode is shorter than the box,
  // so the bands read as frame rather than as missing scanlines
  if (p.h < cv.height) {
    cx.globalAlpha = 0.35;
    cx.strokeStyle = t.rule;
    cx.strokeRect(p.x + 0.5, p.y + 0.5, p.w - 1, p.h - 1);
    cx.globalAlpha = 1;
  }
}

/* Listening must look alive: a slow sweep tied to the live input level tells
   the operator the receiver is hot even when no signal has arrived yet. */
let sweepRAF = null;
function startListenSweep() {
  if (S.reduced) return;
  let p = 0;
  const step = () => {
    if (S.phase !== 'listening') { sweepRAF = null; return; }
    const t = themeColors();
    paintIdle();
    p = (p + 1.1) % (cv.height + 40);
    const grad = cx.createLinearGradient(0, p - 40, 0, p);
    grad.addColorStop(0, 'transparent');
    grad.addColorStop(1, t.sweep);
    cx.globalAlpha = 0.5;
    cx.fillStyle = grad;
    cx.fillRect(0, Math.max(0, p - 40), cv.width, Math.min(40, p));
    cx.globalAlpha = 1;
    cx.fillStyle = t.head;
    cx.fillRect(0, p, cv.width, 1);
    sweepRAF = requestAnimationFrame(step);
  };
  sweepRAF = requestAnimationFrame(step);
}
function stopListenSweep() {
  if (sweepRAF) { cancelAnimationFrame(sweepRAF); sweepRAF = null; }
}

function loadImage(src) {
  return new Promise((res, rej) => {
    const im = new Image();
    im.onload = () => res(im);
    im.onerror = () => rej(new Error('image unavailable: ' + src));
    im.src = src;
  });
}

async function revealScanlines(img, lines, onLine, mode) {
  // The canvas is a fixed box; the picture is drawn into it at an offset, so
  // a shorter mode leaves bands rather than resizing the frame.
  const p = sizeCanvas(mode);
  const native = p.native;
  paintIdle();
  const { head } = themeColors();
  const total = lines;
  const perTick = S.reduced ? total : Math.max(2, Math.round(native.h / 128));
  for (let y = 0; y < total; y += perTick) {
    const h = Math.min(perTick, total - y);
    const sy = (y / native.h) * img.height;
    const sh = (h / native.h) * img.height;
    const dy = p.y + y * p.scale;
    const dh = h * p.scale;
    cx.drawImage(img, 0, sy, img.width, sh, p.x, dy, p.w, dh);
    // the live scanline: a rule at the decode head, in the active palette
    if (y + h < total) {
      cx.fillStyle = head;
      cx.fillRect(p.x, dy + dh, p.w, 2);
    }
    onLine(y + h, total);
    if (!S.reduced) await sleep(14);
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* =========================================================================
   Waterfall — ruled measuring strip. Density and height, never hue.
   ========================================================================= */

const fc = $('fall');
const fx = fc.getContext('2d');
let fallRows = [];
const FALL_BINS = 96;

function sizeFall() {
  const r = fc.getBoundingClientRect();
  fc.width = Math.max(320, Math.floor(r.width));
  fc.height = Math.max(48, Math.floor(r.height));
}

/* Thresholds match the distribution pushFallRow actually produces:
   floor ~0.05-0.12, band shoulders ~0.20-0.45, band centre ~0.50-0.85,
   sync >0.90. Cached per draw — getComputedStyle per bin was 96 lookups a row. */
let toneCache = null;
function refreshTones() {
  const cs = getComputedStyle(app);
  toneCache = ['--sig-0', '--sig-1', '--sig-2', '--sig-3', '--sig-sync']
    .map((n) => cs.getPropertyValue(n).trim());
}
function tone(v) {
  if (!toneCache) refreshTones();
  if (v > 0.88) return toneCache[4];   // 1200 Hz sync
  if (v > 0.50) return toneCache[3];   // strong signal
  if (v > 0.26) return toneCache[2];   // weak signal
  if (v > 0.13) return toneCache[1];   // upper noise floor
  return toneCache[0];                 // noise floor
}

/* Four levels must actually appear in the data, not just exist as tokens:
   noise floor (sig-0/1), weak signal (sig-2), strong signal (sig-3), and the
   1200 Hz sync pulse (sig-sync). Band edges and QSB fading populate the weak
   tier — without them the strip jumps from floor straight to strong and the
   operator loses the distinction §20.4 requires. */
let qsb = 0;
function pushFallRow() {
  const row = new Array(FALL_BINS);
  const active = S.phase === 'listening' || S.phase === 'vis' || S.phase === 'decoding';
  qsb += 0.06;
  const fade = 0.72 + Math.sin(qsb) * 0.28;                  // slow QSB envelope
  for (let i = 0; i < FALL_BINS; i++) {
    const hz = 300 + (i / FALL_BINS) * 2700;
    let v = 0.05 + Math.random() * 0.07;                     // noise floor, sits in sig-0
    if (active) {
      // video band, with soft shoulders so the edges land in the weak tier
      if (hz > 1400 && hz < 2400) {
        const centre = 1900;
        const edge = 1 - Math.min(1, Math.abs(hz - centre) / 500);
        const shoulder = Math.pow(edge, 1.6);                // rolls off at the edges
        v += (0.18 + shoulder * 0.46) * fade + Math.random() * 0.07;
      }
      // 1200 Hz sync pulse — distinct treatment, not "just a strong bin"
      if (S.phase !== 'listening' && Math.abs(hz - 1200) < 45) v = 0.92 + Math.random() * 0.08;
      if (S.phase === 'vis' && Math.abs(hz - 1900) < 60) v += 0.3;
    }
    row[i] = Math.min(1, v);
  }
  fallRows.push(row);
  const maxRows = Math.ceil(fc.height / 4);
  while (fallRows.length > maxRows) fallRows.shift();
}

function drawFall() {
  const cs = getComputedStyle(app);
  fx.fillStyle = cs.getPropertyValue('--sig-0').trim();
  fx.fillRect(0, 0, fc.width, fc.height);

  const bw = fc.width / FALL_BINS;
  const rh = 4;
  fallRows.forEach((row, ri) => {
    const y = fc.height - (fallRows.length - ri) * rh;
    for (let i = 0; i < FALL_BINS; i++) {
      const v = row[i];
      if (v <= 0.02) continue;
      fx.fillStyle = tone(v);
      // density: stronger bins draw taller within their row band
      const h = Math.max(1, Math.round(rh * (0.45 + v * 0.55)));
      fx.fillRect(i * bw, y + (rh - h), Math.max(1, bw - 0.5), h);
    }
  });

  // printed reference rules: 1200 sync and 1900 centre
  const at = (hz) => ((hz - 300) / 2700) * fc.width;
  fx.strokeStyle = cs.getPropertyValue('--ink-3').trim();
  fx.setLineDash([3, 3]); fx.lineWidth = 1;
  fx.beginPath(); fx.moveTo(at(1900), 0); fx.lineTo(at(1900), fc.height); fx.stroke();
  fx.setLineDash([]);
  fx.strokeStyle = cs.getPropertyValue('--ink').trim();
  fx.lineWidth = 2;
  fx.beginPath(); fx.moveTo(at(1200), 0); fx.lineTo(at(1200), fc.height); fx.stroke();
}

/* =========================================================================
   Decode run — the whole story, end to end
   ========================================================================= */

let running = null;   // null | 'rx' | 'tx' — owner token, not a bare flag

/* Half-duplex has to be legible in the CONTROL SURFACE, not just the header:
   an operator editing PTT method on a transmitter that is locked out gets no
   feedback that the edit is inert. Lock the whole table, in the world's own
   grammar, and say which operation owns the radio. */
/* Half-duplex: whichever pipeline does not own the radio has its controls
   locked, in the world's own grammar, so an inert edit is never silent. */
function lockLive(viewSel, locked) {
  const scope = document.querySelector(viewSel);
  if (!scope) return;
  scope.querySelectorAll('.opcol .live input, .opcol .live button').forEach((el) => {
    el.disabled = locked;
    el.setAttribute('aria-disabled', String(locked));
  });
  scope.querySelector('.opcol .live')?.toggleAttribute('data-locked', locked);
}

function lockTable(tbody, locked) {
  tbody.querySelectorAll('input, button').forEach((el) => {
    el.disabled = locked;
    el.setAttribute('aria-disabled', String(locked));
  });
  tbody.closest('table')?.toggleAttribute('data-locked', locked);
}

function setPhase(p, label) {
  S.phase = p;
  $('lamp').dataset.on = p;
  $('statusText').textContent = label;
  const busy = p !== 'idle' && p !== 'locked';
  $('opLabel').hidden = !busy;
  $('opText').hidden = !busy;
  if (busy) $('opText').textContent = p === 'tx' ? 'Transmit (RX locked)' : 'Receive (TX locked)';
  // half-duplex made legible
  $('txBtn').disabled = busy && p !== 'tx';
  $('listenBtn').disabled = p === 'tx';
  lockLive('.capture', p === 'tx');
  lockLive('.txview', busy && p !== 'tx');
}

function announce(msg) { $('live').textContent = msg; }

function toast(what, next) {
  $('toastWhat').textContent = what;
  $('toastNext').textContent = next;
  $('toast').hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { $('toast').hidden = true; }, 6000);
}

async function runDecode({ sample = false } = {}) {
  if (running) {
    toast("I'm already busy with the radio.",
          running === 'tx' ? "Wait for the transmission to finish, or press Esc to abort it."
                           : "I'm still receiving — press F5 to stop listening first.");
    return;
  }
  running = 'rx';
  S.progress = 0;
  resetArrival();
  $('idleNote').hidden = true;
  $('detectCell').hidden = true;
  $('listenLabel').textContent = 'Stop listening';
  $('syncBtn').disabled = false;

  const cap = CAPTURES[S.capIndex % CAPTURES.length];
  const call = DEMO_CALLS[S.capIndex % DEMO_CALLS.length];
  // every 4th run, auto-detection fails — the documented 20-40% case
  const detectFails = !sample && S.capIndex % 4 === 3;
  S.capIndex++;

  // 1. LISTENING — the canvas must look alive, not merely non-blank (§20.4)
  setPhase('listening', 'Listening');
  announce('Listening for a signal.');
  $('tSync').textContent = 'searching';
  startListenSweep();
  await sleep(S.reduced ? 200 : 1900);
  stopListenSweep();
  if (running !== 'rx') return finishIdle();

  // 1b. DETECTION FAILURE — automation fails loudly and hands over control
  if (detectFails) {
    setPhase('listening', 'Mode unclear');
    $('detectCell').hidden = false;
    await typeset($('aDetect'), 'no VIS', 'guess');
    $('aMode').textContent = 'unknown';
    $('aMode').dataset.conf = 'guess';
    announce("I couldn't detect the mode. Choose one to decode anyway.");
    toast("I couldn't work out the mode from the signal.",
          "The VIS header was too noisy to read. Pick a mode above and I'll decode with it.");
    S.pendingCap = cap;
    S.pendingCall = call;
    return;
  }

  // 2. VIS — the field the machine learns first
  setPhase('vis', 'VIS detected');
  $('tSync').textContent = 'VIS';
  const now = new Date();
  const hh = String(now.getUTCHours()).padStart(2, '0');
  const mm = String(now.getUTCMinutes()).padStart(2, '0');
  await typeset($('aTime'), `${hh}:${mm}`, 'certain');
  await typeset($('aMode'), cap.mode, 'certain');
  announce(cap.mode + ' detected.');
  await sleep(S.reduced ? 60 : 340);
  if (running !== 'rx') return finishIdle();

  // 3. DECODING — scanlines land; SNR resolves as a guess, then firms up
  setPhase('decoding', 'Decoding');
  $('pct').hidden = false;
  $('tSync').textContent = 'locked';
  await decodeBody(cap, call, hh, mm, sample, cap.mode);
}

/* The decode itself, shared by the normal path and the manual-mode resume. */
async function decodeBody(cap, call, hh, mm, sample, mode) {
  let img;
  try {
    img = await loadImage(cap.src);
  } catch (err) {
    toast("I couldn't open that image file.",
          "The capture may have been moved or deleted. Check your save folder in Devices.");
    announce('Image could not be loaded.');
    return finishIdle();
  }
  curImg = img;

  // SNR arrives low-confidence first — automation failing loudly
  typeset($('aSnr'), '~9 dB', 'guess', 300);

  let firmed = false;
  await revealScanlines(img, cap.lines, (done, total) => {
    S.progress = Math.round((done / total) * 100);
    $('pct').textContent = S.progress + '%';
    const snr = 9 + (done / total) * 9;
    $('tSnr').textContent = snr.toFixed(1) + ' dB';
    $('mSnr').style.transform = `scaleX(${Math.min(1, snr / 24)})`;
    $('tRms').textContent = (-18 + Math.sin(done / 9) * 4).toFixed(1) + ' dB';
    $('mRms').style.transform = `scaleX(${(62 + Math.sin(done / 9) * 12) / 100})`;
    $('aLines').textContent = done + ' / ' + total;
    $('aLines').dataset.conf = 'certain';

    if (!firmed && done / total > 0.35) {
      firmed = true;
      typeset($('aSnr'), '17.4 dB', 'certain');
      if (call) typeset($('aCall'), call, 'certain', 260);
      else typeset($('aCall'), 'no FSKID', 'guess', 260);
      typeset($('aSlant'), '0.42°', 'certain', 520);
    }
  }, mode);
  if (running !== 'rx') return finishIdle();

  // 4. LOCKED — brief; the operator has waited long enough already
  setPhase('locked', 'Picture locked');
  $('pct').hidden = true;
  cv.setAttribute('aria-label', `Decoded image, ${mode}, ${cap.lines} lines.`);
  $('tSync').textContent = 'complete';
  $('tRms').textContent = '—';
  $('mRms').style.transform = 'scaleX(0)';
  announce(`Picture locked. ${mode}. ${call || 'No callsign'}. Saved to log.`);

  S.seq++;
  S.log.unshift({
    n: S.seq, utc: `${hh}:${mm}`, mode, call: call || '—',
    snr: cap.partial ? '11.2' : '17.4', lines: `${cap.lines}/${cap.lines === 148 ? 256 : cap.lines}`,
    src: sample ? 'Sample' : 'Radio', thumb: cap.src, changed: true
  });
  S.unseen = (S.unseen || 0) + 1;
  renderLog();
  renderSession();
  updateUnseen();

  if (cap.partial) {
    toast("I lost the signal partway through.",
          "I kept the 148 lines I got. Try raising gain, or check the antenna.");
  }

  running = null;
  $('listenLabel').textContent = 'Listen';
  $('syncBtn').disabled = true;
}

/* The changed-row highlight must survive until the operator LOOKS at the Log —
   a timer clears it while they are still watching the decode finish. */
function updateUnseen() {
  const b = document.querySelector('.rail button[data-goto="log"]');
  if (!b) return;
  b.dataset.badge = S.unseen ? String(S.unseen) : '';
  b.toggleAttribute('data-unseen', !!S.unseen);
}

function acknowledgeLog() {
  S.unseen = 0;
  S.log.forEach((e) => { e.changed = false; });
  updateUnseen();
  setTimeout(() => {
    document.querySelectorAll('#logBody tr[data-changed]').forEach((r) => delete r.dataset.changed);
  }, 2600);
}

function finishIdle() {
  running = null;
  stopListenSweep();
  setPhase('idle', 'Idle');
  $('pct').hidden = true;
  $('listenLabel').textContent = 'Listen';
  $('syncBtn').disabled = true;
  return null;
}

/* The operator resolves what the machine couldn't: picking a mode resumes the
   decode from the failure point, and the value is marked as human-set. */
function forceMode(mode) {
  if (!S.pendingCap) return;
  const cap = S.pendingCap, call = S.pendingCall;
  S.pendingCap = null; S.pendingCall = null;
  $('detectCell').hidden = true;
  $('aMode').textContent = mode;
  $('aMode').dataset.conf = 'manual';
  S.overrides.mode = mode;
  rebuildAll();
  announce('Mode forced to ' + mode + '. Decoding.');
  $('toast').hidden = true;
  resumeDecode(cap, call, mode);
}

async function resumeDecode(cap, call, mode) {
  running = 'rx';
  setPhase('decoding', 'Decoding');
  $('pct').hidden = false;
  $('tSync').textContent = 'locked';
  const now = new Date();
  const hh = String(now.getUTCHours()).padStart(2, '0');
  const mm = String(now.getUTCMinutes()).padStart(2, '0');
  await typeset($('aTime'), hh + ':' + mm, 'certain');
  await decodeBody(cap, call, hh, mm, false, mode);
}

/* =========================================================================
   Log board
   ========================================================================= */

/* The session strip mirrors the log, trimmed to what fits beside the canvas. */
function renderSession() {
  const list = $('sessionList');
  const empty = $('sessionEmpty');
  if (!list) return;
  list.replaceChildren();
  empty.hidden = S.log.length > 0;

  S.log.slice(0, 6).forEach((e) => {
    const li = document.createElement('li');
    const im = document.createElement('img');
    im.src = e.thumb;
    im.alt = '';
    const meta = document.createElement('div');
    meta.className = 'meta';
    const when = document.createElement('span');
    when.className = 'when';
    when.textContent = e.utc;
    const who = document.createElement('span');
    who.className = 'who';
    who.textContent = e.call === '—' ? e.mode : e.call;
    meta.append(when, who);
    li.append(im, meta);
    li.title = `${e.utc} · ${e.mode} · ${e.call} · ${e.snr} dB`;
    list.appendChild(li);
  });
}

function renderLog() {
  const body = $('logBody');
  body.replaceChildren();
  $('logEmpty').style.display = S.log.length ? 'none' : 'grid';
  $('logCount').textContent = S.log.length + (S.log.length === 1 ? ' entry' : ' entries');

  S.log.forEach((e) => {
    const tr = document.createElement('tr');
    if (e.changed) { tr.dataset.changed = '1'; e.changed = false; }
    const cells = [
      String(e.n).padStart(2, '0'), e.utc, e.mode, e.call, e.snr + ' dB', e.lines, e.src
    ];
    cells.forEach((c) => { const td = document.createElement('td'); td.textContent = c; tr.appendChild(td); });
    const td = document.createElement('td');
    const im = document.createElement('img');
    im.className = 'thumb'; im.src = e.thumb; im.alt = `Capture ${e.n}, ${e.mode}`;
    td.appendChild(im); tr.appendChild(td);
    body.appendChild(tr);
  });
}

/* =========================================================================
   Transmit
   ========================================================================= */

const txcv = $('txCanvas');
const txcx = txcv.getContext('2d');

/* The TX preview shows the image about to be sent, so it obeys the same mode
   geometry as the decode canvas — the TX mode selector offers Robot 36 (4:3)
   alongside the 5:4 modes, and a preview at the wrong aspect would misrepresent
   what the radio is going to transmit. */
async function paintTx(i) {
  S.txIndex = i;
  const cap = CAPTURES[i];
  const mode = S.overrides.txmode || 'Scottie S1';
  const p = placeInBox(mode);
  let img;
  try {
    img = await loadImage(cap.src);
  } catch {
    toast("I couldn't open that image.",
          "Pick another from the strip, or check your image folder in Devices.");
    return;
  }
  // same fixed box as the decode canvas, so the preview is a true likeness of
  // what will be sent and the frame does not move when the mode changes
  txcv.width = CANVAS_BOX_W; txcv.height = CANVAS_BOX_H;
  const cs = getComputedStyle(app);
  txcx.fillStyle = cs.getPropertyValue('--board').trim();
  txcx.fillRect(0, 0, txcv.width, txcv.height);
  txcx.drawImage(img, p.x, p.y, p.w, p.h);

  document.querySelectorAll('#txGrid button').forEach((b, bi) =>
    b.setAttribute('aria-pressed', String(bi === i)));
}

function buildTxGrid() {
  const g = $('txGrid');
  g.replaceChildren();
  CAPTURES.forEach((c, i) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.setAttribute('aria-pressed', String(i === 0));
    const im = document.createElement('img');
    im.src = c.src; im.alt = `${c.mode} capture from ${c.date}`;
    b.appendChild(im);
    b.addEventListener('click', () => paintTx(i));
    g.appendChild(b);
  });
}

async function runTx() {
  if (running) {
    toast("I can't transmit while I'm receiving.",
          "Press F5 to stop listening, then try again.");
    return;
  }
  running = 'tx';
  setPhase('tx', 'Transmitting');
  $('txAbort').disabled = false;
  const steps = [
    ['PTT keyed', 500], ['VIS header', 700], ['Scanlines', 2600], ['FSKID', 600], ['PTT released', 300]
  ];
  for (const [label, ms] of steps) {
    if (running !== 'tx') break;
    $('txState').textContent = label;
    $('txState').dataset.conf = 'certain';
    announce('Transmit: ' + label);
    await sleep(S.reduced ? 80 : ms);
  }
  $('txState').textContent = running === 'tx' ? 'Sent' : 'Aborted';
  $('txAbort').disabled = true;
  running = null;
  setPhase('idle', 'Idle');
}

/* =========================================================================
   Operating Conditions
   ========================================================================= */

const CONDS = [
  ['standard', 'Standard'],
  ['night', 'Night Vision'],
  ['sun', 'Sunlight']
];

/* Single writer of conditions state: the rail label is derived, never set
   independently, so it can't drift out of sync with the palette. */
function applyConditions(key) {
  const entry = CONDS.find((c) => c[0] === key) || CONDS[0];
  S.conditions = entry[0];
  app.dataset.conditions = entry[0];
  document.querySelectorAll('#cCond button').forEach((b) =>
    b.setAttribute('aria-pressed', String(b.dataset.cond === entry[0])));
  refreshTones();                 // palette changed; the ramp must follow
  drawFall();
  if (S.phase === 'idle' || S.phase === 'locked') paintIdle();
  announce('Operating conditions: ' + entry[1]);
}


/* =========================================================================
   Navigation
   ========================================================================= */

function goto(view) {
  S.view = view;
  document.querySelectorAll('.view').forEach((v) =>
    v.toggleAttribute('data-active', v.dataset.view === view));
  document.querySelectorAll('.rail button[data-goto]').forEach((b) =>
    b.setAttribute('aria-current', b.dataset.goto === view ? 'page' : 'false'));
  if (view === 'transmit' && !txcv.width) paintTx(0);
  if (view === 'log') acknowledgeLog();
}

/* =========================================================================
   Wiring
   ========================================================================= */

function clock() {
  const d = new Date();
  $('clock').textContent = [d.getUTCHours(), d.getUTCMinutes(), d.getUTCSeconds()]
    .map((n) => String(n).padStart(2, '0')).join(':');
}

function init() {
  rebuildAll();
  buildTxGrid();
  refreshTones();
  sizeCanvas('Scottie S1');
  paintIdle();
  renderLog();
  renderSession();
  requestAnimationFrame(() => {
    sizeFall();
    for (let i = 0; i < 60; i++) pushFallRow();
    drawFall();
  });
  clock();
  setInterval(clock, 1000);
  setInterval(() => { pushFallRow(); drawFall(); }, 90);

  document.querySelectorAll('.rail button[data-goto]').forEach((b) =>
    b.addEventListener('click', () => goto(b.dataset.goto)));

  // live controls: gain, squelch, AFC — the three that fail often enough to
  // need correcting while an image is still arriving
  const liveNum = (inputId, revertId, key, unit, auto) => {
    const i = $(inputId), r = $(revertId);
    const sync = () => {
      const overridden = S.overrides[key] !== undefined;
      i.closest('.livectl').toggleAttribute('data-overridden', overridden);
      r.hidden = !overridden;
    };
    i.addEventListener('change', () => {
      S.overrides[key] = i.value;
      announce(key + ' set to ' + i.value + ' ' + unit);
      sync();
    });
    r.addEventListener('click', () => {
      delete S.overrides[key];
      i.value = auto;
      announce(key + ' reverted to auto');
      sync();
    });
    sync();
  };
  liveNum('cGain', 'rGain', 'gain', '%', '112');
  liveNum('cSquelch', 'rSquelch', 'squelch', 'dB', '-41');

  document.querySelectorAll('#cAfc button').forEach((b) =>
    b.addEventListener('click', () => {
      document.querySelectorAll('#cAfc button').forEach((o) =>
        o.setAttribute('aria-pressed', String(o === b)));
      S.overrides.afc = b.dataset.afc;
      announce('AFC set to ' + b.dataset.afc);
    }));

  // tray: the per-signal choices
  document.querySelectorAll('#cMode button').forEach((b) =>
    b.addEventListener('click', () => {
      document.querySelectorAll('#cMode button').forEach((o) =>
        o.setAttribute('aria-pressed', String(o === b)));
      S.overrides.mode = b.dataset.mode;
      announce('Mode set to ' + b.dataset.mode);
    }));

  document.querySelectorAll('#cInput button').forEach((b) =>
    b.addEventListener('click', () => {
      document.querySelectorAll('#cInput button').forEach((o) =>
        o.setAttribute('aria-pressed', String(o === b)));
      S.overrides.device = b.dataset.input;
      announce('Input set to ' + b.dataset.input);
    }));

  document.querySelectorAll('#cCond button').forEach((b) =>
    b.addEventListener('click', () => applyConditions(b.dataset.cond)));

  // Transmit: same segset grammar as Capture
  const bindSeg = (sel, attr, key, onPick) => {
    document.querySelectorAll(sel + ' button').forEach((b) =>
      b.addEventListener('click', () => {
        document.querySelectorAll(sel + ' button').forEach((o) =>
          o.setAttribute('aria-pressed', String(o === b)));
        const v = b.dataset[attr];
        if (key) S.overrides[key] = v;
        announce(b.closest('.trayitem, .livectl')
          ?.querySelector('.lbl')?.textContent + ' set to ' + v);
        if (onPick) onPick(v);
      }));
  };

  bindSeg('#cTxMode', 'txmode', 'txmode', (v) => { syncTxMeta(v); paintTx(S.txIndex); });
  bindSeg('#cTxOut', 'txout', 'txdev');
  bindSeg('#cTxPtt', 'txptt', 'ptt', (v) => { $('txPtt').textContent = v; });
  bindSeg('#cFskid', 'fskid', 'fskid');

  $('cDrive').addEventListener('change', (e) => {
    S.overrides.txgain = e.target.value;
    announce('Drive set to ' + e.target.value + ' percent');
  });

  // settings sheet
  const openSettings = () => {
    $('settings').hidden = false;
    $('setClose').focus();
  };
  const closeSettings = () => {
    $('settings').hidden = true;
    $('railSettings').focus();
  };
  $('railSettings').addEventListener('click', openSettings);
  $('setClose').addEventListener('click', closeSettings);
  $('setDone').addEventListener('click', closeSettings);
  $('settings').addEventListener('click', (e) => {
    if (e.target === $('settings')) closeSettings();
  });

  document.querySelectorAll('#modeFallback button').forEach((b) =>
    b.addEventListener('click', () => forceMode(b.dataset.force)));

  $('listenBtn').addEventListener('click', () => {
    if (running === 'rx') { finishIdle(); announce('Stopped listening.'); }
    else runDecode();
  });
  $('sampleBtn').addEventListener('click', () => runDecode({ sample: true }));
  $('syncBtn').addEventListener('click', () => announce('Manual sync applied.'));

  $('txBtn').addEventListener('click', runTx);
  $('txAbort').addEventListener('click', () => { if (running === 'tx') running = null; });

  $('frSample').addEventListener('click', () => { $('firstRun').hidden = true; runDecode({ sample: true }); });
  $('frDevices').addEventListener('click', () => {
    $('firstRun').hidden = true;
    $('settings').hidden = false;
    $('setClose').focus();
  });
  $('frClose').addEventListener('click', () => { $('firstRun').hidden = true; });

  window.addEventListener('resize', () => { sizeFall(); drawFall(); });
  new ResizeObserver(() => { sizeFall(); drawFall(); }).observe(fc);
  // the canvas re-derives its display size whenever its cell changes
  // The canvas box is a constant, so it needs no resize observer: only the
  // waterfall, which genuinely spans the shell's width, tracks its container.

  document.addEventListener('keydown', (e) => {
    // e.target is `document` when nothing is focused, and document has no
    // .matches — this threw on every keypress and killed all shortcuts on load
    if (e.target instanceof Element && e.target.matches('input')) return;
    if (e.key === 'F5') { e.preventDefault(); $('listenBtn').click(); }
    // guard BEFORE navigating: don't yank the operator off a live decode and
    // then tell them they can't transmit
    if (e.key === 'F6') {
      e.preventDefault();
      if (running === 'rx') {
        toast("I can't transmit while I'm receiving.",
              "Press F5 to stop listening, then try again.");
      } else { goto('transmit'); runTx(); }
    }
    if (e.key === 'F9') { e.preventDefault(); $('sampleBtn').click(); }
    if (e.key === ' ' && !$('syncBtn').disabled) { e.preventDefault(); $('syncBtn').click(); }
    if (e.key === ',') { e.preventDefault(); $('railSettings').click(); }
    if (e.key === 'Escape') {
      if (!$('settings').hidden) { $('settings').hidden = true; $('railSettings').focus(); return; }
      if (!$('txAbort').disabled) $('txAbort').click();
      $('firstRun').hidden = true;
    }
  });

  // first run: empty log, no prior captures
  if (!S.log.length) $('firstRun').hidden = false;
  paintTx(0);
}

document.addEventListener('DOMContentLoaded', init);
