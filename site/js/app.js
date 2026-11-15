// SPHEREx Motion Viewer: reads only static files from data/ (real) and fake_data/ (test), see below.
import { TARGETS, TEST_TARGETS, targetByKey, findTargetByName } from "./targets.js";
import { skyToPx, inField, parseCoords, fieldArcmin } from "./sky.js";
import { LAYERS, DEFAULT_LAYERS, drawMarkers } from "./markers.js";
import { tipText, renderInfo, renderEntry, renderTargetPanel, renderCredits, safeUrl } from "./panel.js";
import { loadF32, autoRange, drawData, COLORMAP_NAMES, defaultK, difference, diffLimit, drawDifference } from "./render.js";
import { drawChart, drawTable } from "./charts.js";

// Where the site reads files from, in order. Real files (data/) always win; fake test
// files (fake_data/) only fill in what hasn't been posted yet. No code change is needed
// when real files arrive: they simply take over.
//  - Image files (fields.json, fov<S>/...) are taken per target, all from one folder,
//    so a real manifest is never mixed with fake images.
//  - overlays.json, explanations.json, credits.json and spectra/*.csv are taken per file.
const REAL_DIR = "../data", FAKE_DIR = "../fake_data";
const DATA_DIRS = [REAL_DIR, FAKE_DIR];
// Live lookup: any other name or position is built on request by the server (server/app.py) and
// served in the same layout as data/. Its keys start with "n_" (names) or "c_" (coordinates).
const LIVE_SERVER = "https://34-121-237-4.sslip.io";
const LIVE_DATA = `${LIVE_SERVER}/data`;
const LIVE_POLL_MS = 10000; // the server pauses builds nobody has asked about for 5 minutes
const isLiveKey = (key) => /^[nc]_/.test(key || "");
const liveQueries = new Map(); // live key -> what the user typed (shown as its name, kept in the URL)
const LARGEST_FIELD = 201; // used for coordinate search when a target has no fields.json yet
const ZOOM_MIN = 1, ZOOM_MAX = 16;
const DAY = 86400000;
const WL_MIN = 0.75, WL_MAX = 5.0;
const DETECTORS = [
  { d: 1, lo: 0.75, hi: 1.1 }, { d: 2, lo: 1.1, hi: 1.6 }, { d: 3, lo: 1.6, hi: 2.4 },
  { d: 4, lo: 2.4, hi: 3.8 }, { d: 5, lo: 3.8, hi: 4.4 }, { d: 6, lo: 4.4, hi: 5.0 },
];
// Reference spectra (Amna's files). Missing files are skipped. Colors: validated categorical
// slots 1-6 (dark). Each file keeps its color; new files take the next slot.
const SPECTRA = [
  { file: "star_g.csv", label: "G star", color: "#3987e5" },
  { file: "star_m.csv", label: "M star", color: "#d95926" },
  { file: "brown_dwarf_l.csv", label: "L brown dwarf", color: "#199e70" },
  { file: "brown_dwarf_t.csv", label: "T brown dwarf", color: "#c98500" },
  { file: "galaxy.csv", label: "Galaxy", color: "#d55181" },
  { file: "star_k.csv", label: "K star", color: "#0ca30c" },
];
const TARGET_POINT_COLOR = "#e6ebf5";
const BRIGHTNESS_COLOR = "#3987e5";
const DIFF_NOTE = "A red/blue pair can appear on stars that don't move. Check the measured positions before calling something moving.";

const $ = (id) => document.getElementById(id);
const el = {
  targets: $("target-buttons"), searchForm: $("search-form"), searchInput: $("search-input"),
  searchMsg: $("search-message"), targetName: $("target-name"), fieldInfo: $("field-info"),
  viewport: $("viewport"), stage: $("stage"), canvas: $("image-canvas"), flagsCanvas: $("flags-canvas"),
  overlay: $("overlay"), badge: $("blink-badge"), diffLegend: $("diff-legend"), tooltip: $("tooltip"),
  viewerMsg: $("viewer-message"), zoomLabel: $("zoom-label"), label: $("image-label"),
  infoPanel: $("info-panel"), infoBody: $("info-body"),
  brightnessView: $("brightness-view"), brightnessNote: $("brightness-note"),
  brightnessChart: $("brightness-chart"), brightnessTable: $("brightness-table"),
  thumbsPanel: $("thumbs-panel"), thumbs: $("thumbs"), thumbsCount: $("thumbs-count"),
  intro: $("target-intro"), introTitle: $("target-intro-title"), introBody: $("target-intro-body"),
  fingerprint: $("fingerprint"), fpNote: $("fingerprint-note"), fpLegend: $("fingerprint-legend"),
  fpChart: $("fingerprint-chart"), fpTable: $("fingerprint-table"),
  controls: $("controls"), fovButtons: $("fov-buttons"), modeButtons: $("mode-buttons"), modeNote: $("mode-note"),
  timeRange: $("time-range"), timeOut: $("time-out"), dateFrom: $("date-from"), dateTo: $("date-to"),
  yearButtons: $("year-buttons"), wlRange: $("wl-range"), wlOut: $("wl-out"), wlPresets: $("wl-presets"),
  matchCount: $("match-count"), matchWarn: $("match-warn"),
  flipbook: $("flipbook-controls"), visitStrip: $("visit-strip"), backToStack: $("back-to-stack"),
  pair: $("pair-controls"), pairHeading: $("pair-heading"), pickA: $("pick-a"), pickB: $("pick-b"),
  showA: $("show-a"), showB: $("show-b"),
  diffControls: $("diff-controls"), kSlider: $("k-slider"), kOut: $("k-out"),
  playback: $("playback-controls"), play: $("play"), speed: $("speed"), speedOut: $("speed-out"),
  layerList: $("layer-list"),
  display: $("display-controls"), color: $("color-toggle"), cmap: $("cmap"),
  brightness: $("brightness"), brightOut: $("bright-out"), contrast: $("contrast"), contrastOut: $("contrast-out"),
  displayNote: $("display-note"),
  aboutDialog: $("about-dialog"), aboutBody: $("about-body"),
  modeBar: $("mode-bar"), modeHint: $("mode-hint"), filterChips: $("filter-chips"), player: $("player"),
  verdictChip: $("verdict-chip"), filtersSummary: $("filters-summary"),
  markers: null, // <g> inside the overlay, created by buildOverlay()
};

// ---------------------------------------------------------------- state
const state = {
  target: null, fov: null,
  mode: "flipbook",  // flipbook | blink | difference | brightness
  visit: 1,          // current visit n (flipbook, when no single image is open)
  frame: null,       // "v2_4" when a single image is open in flipbook
  a: null, b: null,  // blink / difference picks: "v1" (stack) or "v1_4" (single image)
  showB: false,
  zoom: 1, color: false, cmap: "grayscale",
  brightness: 0, contrast: 0, // contrast is log2 of the multiplier
  k: null,           // null = automatic k
  playing: false, speed: 2,
  layers: new Set(DEFAULT_LAYERS),
  from: null, to: null, // "YYYY-MM-DD" or null (open-ended)
  wl: null,             // [lo, hi] µm or null (no wavelength filter)
};
let fields = null, manifest = null, overlays = [], explanations = {}, credits = [];
let markerInfo = new Map();
const view = { cx: 0, cy: 0 }; // image point (pixel units, 0..S) at the viewport center
let loadToken = 0, drawSeq = 0, timer = null;
let diffAuto = { key: "", k: 1 };
const enabledSpectra = new Set(SPECTRA.map((s) => s.file));

// ---------------------------------------------------------------- loading
/** Fetch the first of `urls` that exists. Resolves to a Response, or null if none do. */
async function fetchFirst(urls) {
  for (const url of urls) {
    try {
      const r = await fetch(url);
      if (r.ok) return Object.assign(r, { fromUrl: url });
    } catch { /* try the next one */ }
  }
  return null;
}

// Which folder each target's image files come from (REAL_DIR or FAKE_DIR).
const targetBase = new Map();
const isFakeTarget = (key) => targetBase.get(key) === FAKE_DIR;

const fieldsCache = new Map();
function loadFields(key) {
  if (!fieldsCache.has(key)) {
    fieldsCache.set(key, (async () => {
      for (const dir of isLiveKey(key) ? [LIVE_DATA] : DATA_DIRS) {
        const r = await fetchFirst([`${dir}/${key}/fields.json`]);
        if (!r) continue;
        const j = await r.json().catch(() => null);
        if (j && Array.isArray(j.sizes_px) && j.sizes_px.length) {
          targetBase.set(key, dir);
          return [...j.sizes_px].map(Number).sort((x, y) => x - y);
        }
      }
      return null;
    })());
  }
  return fieldsCache.get(key);
}

/** A shared file (overlays, explanations, credits): real copy if posted, else the fake one. */
const jsonFirstCache = new Map();
function fetchJSONFirst(relPath) {
  if (!jsonFirstCache.has(relPath)) {
    const p = fetchFirst(DATA_DIRS.map((d) => `${d}/${relPath}`)).then((r) => {
      if (!r) throw new Error(`not found: ${relPath}`);
      return r.json();
    });
    p.catch(() => jsonFirstCache.delete(relPath));
    jsonFirstCache.set(relPath, p);
  }
  return jsonFirstCache.get(relPath);
}

const jsonCache = new Map();
function fetchJSON(url) {
  if (!jsonCache.has(url)) {
    const p = fetch(url).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${url}`);
      return r.json();
    });
    p.catch(() => jsonCache.delete(url));
    jsonCache.set(url, p);
  }
  return jsonCache.get(url);
}

const imgCache = new Map();
function loadImage(url) {
  if (!imgCache.has(url)) {
    imgCache.set(url, new Promise((resolve, reject) => {
      const im = new Image();
      im.onload = () => resolve(im);
      im.onerror = () => { imgCache.delete(url); reject(new Error(`Could not load ${url}`)); };
      im.src = url;
    }));
  }
  return imgCache.get(url);
}

const loadOverlays = (key) => fetchJSONFirst(`${key}/overlays.json`).then((a) => (Array.isArray(a) ? a : [])).catch(() => []);

/** One CSV line -> [wavelength, flux, source]. The source may be quoted and contain commas. */
function parseSpectrumLine(line) {
  const a = line.indexOf(","), b = line.indexOf(",", a + 1);
  if (a < 0 || b < 0) return null;
  let source = line.slice(b + 1).trim();
  if (source.startsWith('"') && source.endsWith('"')) source = source.slice(1, -1).replace(/""/g, '"');
  return [line.slice(0, a).trim(), line.slice(a + 1, b).trim(), source];
}

const spectraCache = new Map();
function loadSpectrum(spec) {
  if (!spectraCache.has(spec.file)) {
    spectraCache.set(spec.file, fetchFirst(DATA_DIRS.map((d) => `${d}/spectra/${spec.file}`))
      .then(async (r) => (r ? { text: await r.text(), fake: r.fromUrl.startsWith(FAKE_DIR) } : null))
      .then((res) => {
        if (!res) return null;
        const lines = res.text.trim().split(/\r?\n/).slice(1);
        const pts = [];
        let source = "";
        for (const line of lines) {
          const parts = parseSpectrumLine(line);
          if (!parts) continue;
          const [w, f, src] = parts;
          if (w !== "" && f !== "" && Number.isFinite(+w) && Number.isFinite(+f)) pts.push([+w, +f]);
          if (!source && src) source = src;
        }
        return pts.length ? { ...spec, points: pts.sort((p, q) => p[0] - q[0]), source, fake: res.fake } : null;
      })
      .catch(() => null));
  }
  return spectraCache.get(spec.file);
}

const fovDir = () => `${targetBase.get(state.target) || REAL_DIR}/${state.target}/fov${state.fov}/`;
const visits = () => (manifest ? [...manifest.visits].sort((x, y) => x.n - y.n) : []);

// ---------------------------------------------------------------- image refs and filters
function parseRef(ref) {
  const m = /^v(\d+)(?:_(\d+))?$/.exec(ref || "");
  return m ? { n: +m[1], i: m[2] ? +m[2] : null } : null;
}

/** "v2" -> visit 2's stack, "v2_4" -> image 4 of visit 2. */
function resolveRef(ref) {
  const p = parseRef(ref);
  if (!p || !manifest) return null;
  const visit = manifest.visits.find((v) => v.n === p.n);
  if (!visit) return null;
  if (p.i == null) return { kind: "visit", visit, ref: `v${visit.n}` };
  const frame = (visit.frames || []).find((f) => f.i === p.i);
  return frame ? { kind: "frame", visit, frame, ref: `v${visit.n}_${frame.i}` } : null;
}

const dayMs = (d) => Date.parse(`${d}T00:00:00Z`);
const isoDay = (ms) => new Date(ms).toISOString().slice(0, 10);

function passTime(ms) {
  if (state.from && ms < dayMs(state.from)) return false;
  if (state.to && ms >= dayMs(state.to) + DAY) return false;
  return true;
}
const passWl = (w) => !state.wl || (w >= state.wl[0] - 1e-9 && w <= state.wl[1] + 1e-9);
const visitPasses = (v) => passTime(dayMs(v.date_mid));

/** Every single image, oldest first. */
function allFrames() {
  const out = [];
  for (const v of visits()) for (const f of v.frames || []) out.push({ visit: v, frame: f, ref: `v${v.n}_${f.i}`, t: Date.parse(f.time) });
  return out.sort((x, y) => x.t - y.t);
}
const framesPassingTime = () => allFrames().filter((x) => passTime(x.t));
const filteredFrames = () => framesPassingTime().filter((x) => passWl(x.frame.wavelength_um));

/** What flipbook steps through. */
function sequence() {
  if (state.wl) return filteredFrames().map((x) => x.ref);
  if (state.frame) {
    const n = parseRef(state.frame).n;
    return framesPassingTime().filter((x) => x.visit.n === n).map((x) => x.ref);
  }
  return visits().filter(visitPasses).map((v) => `v${v.n}`);
}

/** What blink and difference may pick from. */
function pickable() {
  if (state.wl) return filteredFrames().map((x) => x.ref);
  return [...visits().filter(visitPasses).map((v) => `v${v.n}`), ...framesPassingTime().map((x) => x.ref)];
}

const flipRef = () => state.frame || `v${state.visit}`;

function currentItem() {
  if (state.mode === "blink") return resolveRef(state.showB ? state.b : state.a);
  if (state.mode === "difference") return resolveRef(state.b);
  if (state.mode === "brightness") return null;
  return resolveRef(flipRef());
}

/** Keep the current image and the A/B picks inside what the filters allow. */
function normalizeSelection() {
  if (state.wl && !state.frame) state.frame = filteredFrames()[0]?.ref || null;
  let seq = sequence();
  if (!state.wl && state.frame && !seq.length) { state.frame = null; seq = sequence(); }
  if (seq.length && !seq.includes(flipRef())) {
    const r = resolveRef(seq[0]);
    state.visit = r.visit.n;
    state.frame = r.kind === "frame" ? r.ref : null;
  }
  if (state.frame) state.visit = parseRef(state.frame).n;

  const pk = pickable();
  // Defaults: first and last visit stack; single images only when stacks aren't available.
  const stacks = pk.filter((r) => parseRef(r).i == null);
  const pool = stacks.length >= 2 ? stacks : pk;
  if (!pk.includes(state.a)) state.a = pool[0] || null;
  if (!pk.includes(state.b) || (state.b === state.a && pk.length > 1)) {
    state.b = [...pool].reverse().find((r) => r !== state.a) || [...pk].reverse().find((r) => r !== state.a) || null;
  }
  if ((state.mode === "blink" || state.mode === "difference") && pk.length < 2) {
    state.mode = "flipbook";
    setPlaying(false);
  }
}

// ---------------------------------------------------------------- drawing
let stackRangeCache = { key: "", promise: null };
function stackRange() {
  const key = `${state.target}/${state.fov}`;
  if (stackRangeCache.key !== key) {
    // Stacks share one stretch so blinking between visits is fair.
    const vs = visits().filter((v) => v.data);
    stackRangeCache = {
      key,
      promise: Promise.all(vs.map((v) => loadF32(fovDir() + v.data, state.fov))).then((arrs) => autoRange(arrs)),
    };
    stackRangeCache.promise.catch(() => { stackRangeCache = { key: "", promise: null }; });
  }
  return stackRangeCache.promise;
}
const frameRanges = new Map();
function frameRange(url, data) {
  // Single images are stretched per image (brightness differs a lot between wavelengths).
  if (!frameRanges.has(url)) frameRanges.set(url, autoRange(data));
  return frameRanges.get(url);
}

function clearCanvas(c) { c.getContext("2d").clearRect(0, 0, c.width, c.height); }

async function render() {
  syncUI();
  const brightness = state.mode === "brightness";
  el.viewport.hidden = brightness;
  el.brightnessView.hidden = !brightness;
  el.label.hidden = brightness;
  if (!manifest) return;
  if (brightness) { renderBrightness(); renderThumbs(); return; }
  renderThumbs();
  if (state.mode === "difference") return renderDifference();

  const item = currentItem();
  if (!item) { showEmpty(); return; }
  const seq = ++drawSeq;
  updateLabel(item);
  updateBadge(item);
  renderMarkers(item);
  drawFlags(item, seq);

  const ctx = el.canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  const useRgb = state.color && item.kind === "visit" && item.visit.image_rgb;
  const dataPath = item.kind === "visit" ? item.visit.data : item.frame.data;
  const pngPath = useRgb ? item.visit.image_rgb : item.kind === "visit" ? item.visit.image : item.frame.image;
  // Per the format: the PNG is for quick display; the .f32 is used once brightness,
  // contrast or a colormap changes how the pixel values are drawn.
  const needData = !useRgb && (state.brightness !== 0 || state.contrast !== 0 || state.cmap !== "grayscale");

  // Each returns "ok", "stale" (a newer draw started) or "fail".
  const drawF32 = async () => {
    if (!dataPath) return "fail";
    try {
      const url = fovDir() + dataPath;
      const data = await loadF32(url, state.fov);
      const range = item.kind === "visit" ? await stackRange() : frameRange(url, data);
      if (seq !== drawSeq) return "stale";
      drawData(ctx, data, state.fov, {
        ...range, brightness: state.brightness, contrast: 2 ** state.contrast, cmap: state.cmap,
      });
      return "ok";
    } catch {
      return "fail";
    }
  };
  const drawPng = async () => {
    if (!pngPath) return "fail";
    try {
      const im = await loadImage(fovDir() + pngPath);
      if (seq !== drawSeq) return "stale";
      ctx.clearRect(0, 0, el.canvas.width, el.canvas.height);
      ctx.drawImage(im, 0, 0, el.canvas.width, el.canvas.height);
      return "ok";
    } catch {
      return "fail";
    }
  };

  // Preferred source first, the other one as a fallback if a file is missing.
  const order = needData ? [drawF32, drawPng] : useRgb ? [drawPng] : [drawPng, drawF32];
  for (const draw of order) {
    const result = await draw();
    if (result === "stale") return;
    if (result === "ok") { hideViewerMessage(); return; }
  }
  if (seq === drawSeq) showViewerMessage("This image couldn't be loaded.");
}

function showEmpty(text = "No images match these filters. Widen the time or wavelength range.") {
  ++drawSeq;
  clearCanvas(el.canvas);
  clearCanvas(el.flagsCanvas);
  if (el.markers) el.markers.replaceChildren();
  el.label.replaceChildren();
  el.badge.hidden = true;
  showViewerMessage(text);
}

async function renderDifference() {
  const A = resolveRef(state.a), B = resolveRef(state.b);
  if (!A || !B) { showEmpty("Pick two images to compare."); return; }
  const seq = ++drawSeq;
  updateBadge(B);
  renderMarkers(B);
  clearCanvas(el.flagsCanvas);
  const pathOf = (x) => (x.kind === "visit" ? x.visit.data : x.frame.data);
  try {
    if (!pathOf(A) || !pathOf(B)) throw new Error("no data file");
    const [da, db] = await Promise.all([loadF32(fovDir() + pathOf(A), state.fov), loadF32(fovDir() + pathOf(B), state.fov)]);
    if (seq !== drawSeq) return;
    const key = `${state.target}|${state.fov}|${state.a}|${state.b}`;
    if (diffAuto.key !== key) diffAuto = { key, k: defaultK(da, db) };
    const k = state.k ?? diffAuto.k;
    const D = difference(da, db, k);
    drawDifference(el.canvas.getContext("2d"), D, state.fov, diffLimit(D));
    el.kSlider.max = Math.max(2, +(diffAuto.k * 3).toFixed(3));
    el.kSlider.value = k;
    el.kOut.textContent = k.toFixed(3);
    updateDiffLabel(A, B, k);
    hideViewerMessage();
  } catch {
    if (seq === drawSeq) showViewerMessage("The difference needs the .f32 data files of both images, and one of them couldn't be loaded.");
  }
}

function renderMarkers(item) {
  if (!item || !el.markers) return;
  markerInfo = drawMarkers({ group: el.markers, item, manifest, overlays, layers: state.layers, size: state.fov });
  updateStrokes();
  hideTooltip();
}

/** Quality-flag overlay: single images only. Loads first, then swaps, so blinking doesn't flicker. */
async function drawFlags(item, seq) {
  const ctx = el.flagsCanvas.getContext("2d");
  const clear = () => ctx.clearRect(0, 0, el.flagsCanvas.width, el.flagsCanvas.height);
  if (!state.layers.has("flags") || item.kind !== "frame" || !item.frame.flags) { clear(); return; }
  try {
    const im = await loadImage(fovDir() + item.frame.flags);
    if (seq !== drawSeq) return;
    clear();
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(im, 0, 0, el.flagsCanvas.width, el.flagsCanvas.height);
  } catch {
    if (seq === drawSeq) clear();
  }
}

function buildOverlay() {
  const S = state.fov;
  const c = (S - 1) / 2 + 0.5; // center of the center pixel, in overlay units
  const gap = 1.5;             // keep the target pixel itself uncovered
  el.overlay.setAttribute("viewBox", `0 0 ${S} ${S}`);
  el.overlay.innerHTML = `
    <g class="crosshair">
      <line data-stroke="1.5" x1="0" y1="${c}" x2="${c - gap}" y2="${c}"/>
      <line data-stroke="1.5" x1="${c + gap}" y1="${c}" x2="${S}" y2="${c}"/>
      <line data-stroke="1.5" x1="${c}" y1="0" x2="${c}" y2="${c - gap}"/>
      <line data-stroke="1.5" x1="${c}" y1="${c + gap}" x2="${c}" y2="${S}"/>
    </g>
    <g id="markers"></g>`;
  el.markers = el.overlay.querySelector("#markers");
}

/** Keep overlay lines a constant thickness on screen at any magnification. */
function updateStrokes() {
  if (!state.fov) return;
  const k = scale();
  for (const node of el.overlay.querySelectorAll("[data-stroke]")) node.setAttribute("stroke-width", node.dataset.stroke / k);
}

// ---------------------------------------------------------------- zoom and pan
let lastScale = 0;
function scale() {
  const W = el.viewport.clientWidth, H = el.viewport.clientHeight;
  return (Math.min(W, H) / state.fov) * state.zoom; // 1x = whole field fits the viewer
}

function applyTransform() {
  if (!state.fov || el.viewport.hidden) return;
  const W = el.viewport.clientWidth, H = el.viewport.clientHeight;
  const k = scale();
  el.stage.style.width = el.stage.style.height = `${state.fov}px`;
  el.stage.style.transform = `translate(${W / 2 - view.cx * k}px, ${H / 2 - view.cy * k}px) scale(${k})`;
  if (k !== lastScale) { lastScale = k; updateStrokes(); }
  el.zoomLabel.textContent = `${state.zoom < 10 ? state.zoom.toFixed(1).replace(/\.0$/, "") : Math.round(state.zoom)}×`;
}

function centerOnTarget() { view.cx = view.cy = state.fov / 2; }
function clampView() {
  view.cx = Math.min(Math.max(view.cx, 0), state.fov);
  view.cy = Math.min(Math.max(view.cy, 0), state.fov);
}

/** Zoom to `z`, keeping the image point under viewport position (mx, my) fixed. */
function zoomAt(mx, my, z) {
  const W = el.viewport.clientWidth, H = el.viewport.clientHeight;
  const k0 = scale();
  const px = view.cx + (mx - W / 2) / k0, py = view.cy + (my - H / 2) / k0;
  state.zoom = Math.min(Math.max(z, ZOOM_MIN), ZOOM_MAX);
  const k1 = scale();
  view.cx = px - (mx - W / 2) / k1;
  view.cy = py - (my - H / 2) / k1;
  clampView();
  applyTransform();
  scheduleUrl();
}
const zoomCenter = (f) => zoomAt(el.viewport.clientWidth / 2, el.viewport.clientHeight / 2, state.zoom * f);
function resetView() { state.zoom = 1; centerOnTarget(); applyTransform(); scheduleUrl(); }

function setupPanZoom() {
  const vp = el.viewport;
  const pointers = new Map();
  let last = null; // {x, y, dist} of the previous move
  let tap = null;  // a press that may turn out to be a click on a marker

  const local = (e) => { const r = vp.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  const gesture = () => {
    const pts = [...pointers.values()];
    if (pts.length === 1) return { x: pts[0].x, y: pts[0].y, dist: null };
    const [p, q] = pts;
    return { x: (p.x + q.x) / 2, y: (p.y + q.y) / 2, dist: Math.hypot(p.x - q.x, p.y - q.y) };
  };

  vp.addEventListener("wheel", (e) => {
    if (!state.fov) return;
    e.preventDefault();
    const p = local(e);
    zoomAt(p.x, p.y, state.zoom * Math.exp(-e.deltaY * 0.0015));
  }, { passive: false });

  vp.addEventListener("pointerdown", (e) => {
    if (!state.fov || e.target.closest("button")) return;
    const p = local(e);
    tap = pointers.size ? null : { marker: e.target.closest(".marker"), x: p.x, y: p.y, moved: 0 };
    vp.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId, p);
    last = gesture();
    vp.classList.add("dragging");
  });
  vp.addEventListener("pointermove", (e) => {
    if (!pointers.has(e.pointerId)) {
      if (e.pointerType === "mouse") hoverAt(e.target.closest(".marker"), local(e));
      return;
    }
    const p = local(e);
    if (tap) tap.moved = Math.max(tap.moved, Math.hypot(p.x - tap.x, p.y - tap.y));
    pointers.set(e.pointerId, p);
    const g = gesture();
    if (last && last.dist && g.dist) zoomAt(g.x, g.y, state.zoom * (g.dist / last.dist));
    if (last && (last.dist == null) === (g.dist == null)) {
      const k = scale();
      view.cx -= (g.x - last.x) / k;
      view.cy -= (g.y - last.y) / k;
      clampView();
      applyTransform();
    }
    last = g;
  });
  const end = (e) => {
    if (!pointers.has(e.pointerId)) return;
    pointers.delete(e.pointerId);
    last = pointers.size ? gesture() : null;
    if (!pointers.size) vp.classList.remove("dragging");
    if (e.type === "pointerup" && tap && !pointers.size && tap.moved < 5) markerTapped(tap.marker, local(e));
    if (!pointers.size) tap = null;
  };
  vp.addEventListener("pointerup", end);
  vp.addEventListener("pointercancel", end);
  vp.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse" && !pointers.size) hideTooltip(); });
  vp.addEventListener("dblclick", (e) => {
    if (!state.fov || e.target.closest("button")) return;
    const p = local(e);
    zoomAt(p.x, p.y, state.zoom * 2);
  });

  new ResizeObserver(applyTransform).observe(vp);
  $("zoom-in").addEventListener("click", () => zoomCenter(Math.SQRT2));
  $("zoom-out").addEventListener("click", () => zoomCenter(Math.SQRT1_2));
  $("zoom-reset").addEventListener("click", resetView);
}

// ---------------------------------------------------------------- labels
const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const timeFmt = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "UTC" });
const fmtDate = (d) => dateFmt.format(new Date(`${d}T00:00:00Z`));
const fmtTime = (t) => { const d = new Date(t); return `${dateFmt.format(d)}, ${timeFmt.format(d)} UTC`; };
const fmtUm = (x) => Number(x).toFixed(2);
const refName = (item) => (item.kind === "visit" ? `Visit ${item.visit.n} stack` : `Visit ${item.visit.n}, image ${item.frame.i}`);

function fillLabel({ badge, title, details, link, notes }) {
  el.label.replaceChildren();
  const t = document.createElement("div");
  t.className = "title";
  if (badge) {
    const ab = document.createElement("span");
    ab.className = `ab ab-${badge.toLowerCase()}`;
    ab.textContent = badge;
    t.append(ab, " ");
  }
  t.append(title);
  const d = document.createElement("div");
  d.className = "details";
  for (const s of details.filter(Boolean)) {
    const span = document.createElement("span");
    span.textContent = s;
    d.append(span);
  }
  if (link) {
    const span = document.createElement("span");
    const a = document.createElement("a");
    a.href = link.href; a.target = "_blank"; a.rel = "noopener";
    a.textContent = link.text;
    span.append(a);
    d.append(span);
  }
  el.label.append(t, d);
  for (const n of notes.filter(Boolean)) {
    const p = document.createElement("div");
    p.className = "note";
    p.textContent = n;
    el.label.append(p);
  }
}

function updateLabel(item) {
  const v = item.visit;
  const src = item.kind === "frame" ? item.frame : v;
  const notes = [];
  if (state.layers.has("measured") && !Array.isArray(src.target_measured_px)) {
    notes.push(src.saturated ? "No measured position: the target is saturated (too bright to measure) here." : "No measured position for this image.");
  }
  if (item.kind === "visit") {
    if (state.layers.has("flags")) {
      notes.push(state.mode === "blink"
        ? "Quality flags exist only for single images, not visit stacks. Pick single images as A and B to see them."
        : "Quality flags exist only for single images, not visit stacks. Open a single image to see them.");
    }
    const wl = Array.isArray(v.wavelength_um) ? `${fmtUm(v.wavelength_um[0])}–${fmtUm(v.wavelength_um[1])} µm` : "";
    fillLabel({
      badge: state.mode === "blink" ? (state.showB ? "B" : "A") : null,
      title: `Visit ${v.n} of ${visits().length} (stack)`,
      details: [`${fmtDate(v.date_start)} – ${fmtDate(v.date_end)}`, `${v.n_images} images`, wl],
      notes,
    });
    return;
  }
  const f = item.frame;
  let title = `Visit ${v.n}, image ${f.i} of ${(v.frames || []).length}`;
  if (state.mode === "flipbook" && state.wl) {
    const seq = sequence();
    title = `Image ${seq.indexOf(item.ref) + 1} of ${seq.length} in ${fmtUm(state.wl[0])}–${fmtUm(state.wl[1])} µm · ${title}`;
  } else if (state.mode === "flipbook") {
    notes.push("Each image in a visit is at a different wavelength, so some brightness change between them is expected.");
  }
  if (state.color) notes.push("Color is only available for visit stacks. A single image has one wavelength, so it is shown in grayscale.");
  const url = safeUrl(f.archive_url);
  fillLabel({
    badge: state.mode === "blink" ? (state.showB ? "B" : "A") : null,
    title,
    details: [
      fmtTime(f.time), `${fmtUm(f.wavelength_um)} µm`, `detector D${f.detector}`,
      f.bad_pixel_fraction != null ? `${(f.bad_pixel_fraction * 100).toFixed(1)}% bad pixels` : "",
    ],
    link: url ? { href: url, text: "Download original FITS file from IRSA (about 65 MB)" } : null,
    notes,
  });
}

function updateDiffLabel(A, B, k) {
  const wlA = A.kind === "frame" ? A.frame.wavelength_um : null;
  const wlB = B.kind === "frame" ? B.frame.wavelength_um : null;
  const notes = [];
  if (wlA != null && wlB != null && Math.abs(wlA - wlB) > 0.2) {
    notes.push(`A (${fmtUm(wlA)} µm) and B (${fmtUm(wlB)} µm) differ in wavelength by more than 0.2 µm, so some of the residue is color difference, not change.`);
  } else if ((wlA == null) !== (wlB == null)) {
    notes.push("A visit stack mixes many wavelengths, so comparing it with a single image leaves residue that is color difference, not change.");
  }
  notes.push(DIFF_NOTE);
  if (state.layers.has("flags")) notes.push("Quality flags aren't shown in difference mode. Use flipbook or blink with single images to see them.");
  fillLabel({
    title: `Difference: B − ${k.toFixed(3)} × A`,
    details: [`A: ${refName(A)} (${A.kind === "frame" ? fmtTime(A.frame.time) : fmtDate(A.visit.date_mid)})`,
      `B: ${refName(B)} (${B.kind === "frame" ? fmtTime(B.frame.time) : fmtDate(B.visit.date_mid)})`,
      "markers show B's date"],
    notes,
  });
}

function updateBadge(item) {
  el.diffLegend.hidden = state.mode !== "difference";
  el.overlay.classList.toggle("on-light", state.mode === "difference"); // difference image is mostly white
  if (state.mode === "blink" && item) {
    el.badge.hidden = false;
    el.badge.className = `badge ${state.showB ? "b" : "a"}`;
    el.badge.textContent = `${state.showB ? "B" : "A"} · ${refName(item)}`;
  } else if (state.mode === "difference") {
    el.badge.hidden = false;
    el.badge.className = "badge diff";
    el.badge.textContent = "B − k × A";
  } else {
    el.badge.hidden = true;
  }
}

function showViewerMessage(text) { el.viewerMsg.textContent = text; el.viewerMsg.hidden = false; }
function hideViewerMessage() { el.viewerMsg.hidden = true; }
function showSearchMessage(text, kind = "warn") {
  el.searchMsg.textContent = text;
  el.searchMsg.className = `search-message ${kind === "info" ? "info" : ""}`;
  el.searchMsg.hidden = false;
}
function hideSearchMessage() { el.searchMsg.hidden = true; }

/** Name to show for a target: the five targets' names, else what the user typed for a live field. */
function displayName(key) {
  return targetByKey(key)?.name || liveQueries.get(key) || manifest?.name || key;
}

// ---------------------------------------------------------------- hover text and "What am I looking at?"
function showTooltip(text, p) {
  el.tooltip.textContent = text;
  el.tooltip.hidden = false;
  const W = el.viewport.clientWidth, H = el.viewport.clientHeight;
  const w = el.tooltip.offsetWidth, h = el.tooltip.offsetHeight;
  el.tooltip.style.left = `${Math.max(6, Math.min(p.x + 14, W - w - 6))}px`;
  el.tooltip.style.top = `${p.y + 18 + h > H ? Math.max(6, p.y - h - 12) : p.y + 18}px`;
}
function hideTooltip() { el.tooltip.hidden = true; }
function hoverAt(markerEl, p) {
  const info = markerEl && markerInfo.get(markerEl.dataset.id);
  if (info) showTooltip(tipText(info, explanations), p); else hideTooltip();
}
function markerTapped(markerEl, p) {
  const info = markerEl && markerInfo.get(markerEl.dataset.id);
  if (!info) { hideTooltip(); return; }
  showTooltip(tipText(info, explanations), p); // also gives touch users the hover text
  if (info.kind === "catalog") openInfo(info);
}
function openInfo(info) {
  renderInfo(el.infoBody, info, explanations);
  el.infoPanel.hidden = false;
  el.infoPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
function closeInfo() { el.infoPanel.hidden = true; }

// ---------------------------------------------------------------- single-image thumbnails
let thumbsSig = "";
function renderThumbs() {
  if (!manifest) { el.thumbsPanel.hidden = true; thumbsSig = ""; return; }
  el.thumbsPanel.hidden = false;
  // Rebuild only when something shown here changed (not on every blink tick).
  const sig = JSON.stringify([state.target, state.fov, state.from, state.to, state.wl, state.mode, state.frame, state.a, state.b]);
  if (sig === thumbsSig) return;
  thumbsSig = sig;
  el.thumbs.replaceChildren();
  const total = allFrames().length;
  const shown = filteredFrames();
  el.thumbsCount.textContent = shown.length === total ? `${total} images` : `${shown.length} of ${total} images match the filters`;
  for (const v of visits()) {
    const frames = shown.filter((x) => x.visit.n === v.n);
    const row = document.createElement("div");
    row.className = "thumb-row";
    const head = document.createElement("div");
    head.className = "thumb-head";
    head.textContent = `Visit ${v.n} · ${fmtDate(v.date_mid)}`;
    row.append(head);
    if (!frames.length) {
      const none = document.createElement("div");
      none.className = "muted small";
      none.textContent = "No images in this range.";
      row.append(none);
    } else {
      const strip = document.createElement("div");
      strip.className = "thumb-strip";
      for (const x of frames) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "thumb";
        b.title = `${fmtTime(x.frame.time)} · ${fmtUm(x.frame.wavelength_um)} µm · D${x.frame.detector}`;
        b.setAttribute("aria-label", `Visit ${v.n}, image ${x.frame.i}, ${fmtUm(x.frame.wavelength_um)} micrometers`);
        const current = state.mode === "flipbook" && state.frame === x.ref;
        b.setAttribute("aria-pressed", String(current));
        const img = document.createElement("img");
        img.src = fovDir() + x.frame.image;
        img.alt = "";
        img.loading = "lazy";
        const cap = document.createElement("span");
        cap.textContent = `${fmtUm(x.frame.wavelength_um)} µm`;
        b.append(img, cap);
        if (state.mode === "blink" || state.mode === "difference") {
          for (const [ref, tag] of [[state.a, "A"], [state.b, "B"]]) {
            if (ref === x.ref) {
              const t = document.createElement("span");
              t.className = `ab ab-${tag.toLowerCase()} thumb-tag`;
              t.textContent = tag;
              b.append(t);
            }
          }
        }
        b.addEventListener("click", () => openFrame(x.ref));
        strip.append(b);
      }
      row.append(strip);
    }
    el.thumbs.append(row);
  }
}

/** Show one single image in the main viewer (flipbook). */
function openFrame(ref) {
  setPlaying(false);
  state.mode = "flipbook";
  state.frame = ref;
  state.visit = parseRef(ref).n;
  normalizeSelection();
  render();
  scheduleUrl();
  el.viewport.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ---------------------------------------------------------------- brightness mode
const detectorFor = (lo, hi) => DETECTORS.find((d) => lo >= d.lo - 1e-9 && hi <= d.hi + 1e-9);

function renderBrightness() {
  const note = (text) => { el.brightnessNote.textContent = text; el.brightnessNote.hidden = !text; };
  el.brightnessChart.replaceChildren();
  el.brightnessTable.replaceChildren();
  if (!state.wl) {
    note("Pick a wavelength range under Filters first, for example one detector. Brightness can only be compared at the same wavelength: comparing different wavelengths shows color, not change.");
    return;
  }
  const notes = [];
  if (!detectorFor(state.wl[0], state.wl[1])) {
    notes.push(`This range (${fmtUm(state.wl[0])}–${fmtUm(state.wl[1])} µm) is wider than one detector, so some differences may be color, not real change.`);
  }
  const rows = filteredFrames();
  const pts = rows.filter((x) => x.frame.target_flux_mjy != null);
  if (!pts.length) {
    const sat = rows.some((x) => x.frame.saturated);
    notes.push(rows.length
      ? (sat ? "No brightness measurements: the target is saturated (too bright to measure) in these images."
        : "No brightness measurements in these images (the target may be too faint).")
      : "No images match the filters.");
    note(notes.join(" "));
    return;
  }
  if (pts.some((x) => x.frame.saturated)) {
    notes.push("Hollow dots: the target is saturated (too bright) in that image, so its brightness is less precise.");
  }
  note(notes.join(" "));
  const ts = pts.map((x) => x.t);
  let tMin = Math.min(...ts), tMax = Math.max(...ts);
  const padT = Math.max((tMax - tMin) * 0.05, 15 * DAY);
  tMin -= padT; tMax += padT;
  const ys = pts.flatMap((x) => [x.frame.target_flux_mjy - (x.frame.target_flux_err_mjy || 0), x.frame.target_flux_mjy + (x.frame.target_flux_err_mjy || 0)]);
  let yMin = Math.min(...ys), yMax = Math.max(...ys);
  const padY = Math.max((yMax - yMin) * 0.12, Math.abs(yMax) * 0.05, 1e-3);
  yMin -= padY; yMax += padY;
  drawChart(el.brightnessChart, {
    ariaLabel: `Target brightness in mJy against time, ${pts.length} images`,
    x: { type: "time", min: tMin, max: tMax, label: "Time (UTC)" },
    y: { min: yMin, max: yMax, label: "Brightness (mJy)" },
    points: pts.map((x) => ({
      x: x.t, y: x.frame.target_flux_mjy, err: x.frame.target_flux_err_mjy, color: BRIGHTNESS_COLOR,
      hollow: !!x.frame.saturated,
      tip: `${fmtTime(x.frame.time)} · ${fmtUm(x.frame.wavelength_um)} µm · D${x.frame.detector} · ${x.frame.target_flux_mjy.toFixed(3)}${x.frame.target_flux_err_mjy != null ? ` ± ${x.frame.target_flux_err_mjy.toFixed(3)}` : ""} mJy${x.frame.saturated ? " · saturated, less precise" : ""} · click to open`,
      onClick: () => openFrame(x.ref),
    })),
  });
  drawTable(el.brightnessTable, ["Time (UTC)", "Visit, image", "Wavelength (µm)", "Detector", "Brightness (mJy)", "Error (mJy)", "Saturated"],
    pts.map((x) => [fmtTime(x.frame.time), `${x.visit.n}, ${x.frame.i}`, fmtUm(x.frame.wavelength_um), `D${x.frame.detector}`,
      x.frame.target_flux_mjy.toFixed(3), x.frame.target_flux_err_mjy != null ? x.frame.target_flux_err_mjy.toFixed(3) : "—",
      x.frame.saturated ? "yes" : "no"]));
}

// ---------------------------------------------------------------- infrared fingerprint
async function renderFingerprint() {
  if (!el.fingerprint.open || !manifest) return;
  const token = loadToken;
  const spectra = (await Promise.all(SPECTRA.map(loadSpectrum)));
  if (token !== loadToken || !manifest) return;

  // legend / toggles
  el.fpLegend.replaceChildren();
  const targetKey = document.createElement("span");
  targetKey.className = "legend-item";
  targetKey.innerHTML = `<svg width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="4.5" fill="${TARGET_POINT_COLOR}"/></svg>`;
  targetKey.append(" This target (one dot per single image)");
  el.fpLegend.append(targetKey);
  SPECTRA.forEach((spec, i) => {
    const loaded = spectra[i];
    const label = document.createElement("label");
    label.className = "legend-item check";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = !!loaded && enabledSpectra.has(spec.file);
    box.disabled = !loaded;
    box.addEventListener("change", () => {
      if (box.checked) enabledSpectra.add(spec.file); else enabledSpectra.delete(spec.file);
      renderFingerprint();
    });
    const sw = document.createElement("span");
    sw.className = "line-swatch";
    sw.style.background = spec.color;
    const text = document.createElement("span");
    text.textContent = !loaded ? `${spec.label} (file not posted yet)` : loaded.fake ? `${spec.label} (fake test curve)` : spec.label;
    if (loaded?.source) label.title = loaded.source;
    label.append(box, sw, text);
    el.fpLegend.append(label);
  });

  const rows = framesPassingTime().filter((x) => x.frame.target_flux_mjy != null);
  el.fpChart.replaceChildren();
  el.fpTable.replaceChildren();
  if (!rows.length) {
    const sat = framesPassingTime().some((x) => x.frame.saturated);
    el.fpNote.textContent = sat
      ? "No brightness measurements: the target is saturated (too bright to measure), so there is no fingerprint to draw."
      : "No brightness measurements in the selected time range.";
    return;
  }
  // Divide everything by the target's value nearest 2.2 µm, as the reference files already are.
  // Prefer a non-saturated image, but only if it is about as close to 2.2 µm (within 0.15 µm more);
  // a precise value far from 2.2 µm would misalign the dots with the reference curves more.
  const dist = (x) => Math.abs(x.frame.wavelength_um - 2.2);
  const nearest = (list) => list.reduce((best, x) => (dist(x) < dist(best) ? x : best));
  const closest = nearest(rows);
  const clean = rows.filter((x) => !x.frame.saturated && dist(x) <= dist(closest) + 0.15);
  const ref = clean.length ? nearest(clean) : closest;
  const norm = ref.frame.target_flux_mjy;
  const anySat = rows.some((x) => x.frame.saturated);
  if (anySat) {
    const k = document.createElement("span");
    k.className = "legend-item";
    k.innerHTML = `<svg width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="4" fill="none" stroke="${TARGET_POINT_COLOR}" stroke-width="2"/></svg>`;
    k.append(" Saturated image (less precise)");
    targetKey.after(k);
  }
  el.fpNote.textContent = `Each dot is one single image (time filter applies). All values are divided by the image nearest 2.2 µm (${fmtUm(ref.frame.wavelength_um)} µm, ${norm.toFixed(3)} mJy${ref.frame.saturated ? ", saturated, so the whole curve is less precise" : ""}), as the reference curves are.${anySat ? " Hollow dots are saturated images." : ""} Reference curves stop where their source stops.`;
  const pts = rows.map((x) => ({
    x: x.frame.wavelength_um,
    y: x.frame.target_flux_mjy / norm,
    err: x.frame.target_flux_err_mjy != null ? x.frame.target_flux_err_mjy / Math.abs(norm) : null,
    color: TARGET_POINT_COLOR,
    hollow: !!x.frame.saturated,
    tip: `${fmtUm(x.frame.wavelength_um)} µm · ${(x.frame.target_flux_mjy / norm).toFixed(3)} (relative) · ${x.frame.target_flux_mjy.toFixed(3)} mJy${x.frame.saturated ? " · saturated, less precise" : ""} · visit ${x.visit.n}, image ${x.frame.i} · click to open`,
    onClick: () => openFrame(x.ref),
  }));
  const lines = spectra.filter((sp) => sp && enabledSpectra.has(sp.file))
    .map((sp) => ({ label: sp.label, color: sp.color, points: sp.points.filter(([w]) => w >= WL_MIN && w <= WL_MAX) }));
  const yVals = [...pts.flatMap((p) => [p.y + (p.err || 0), p.y - (p.err || 0)]), ...lines.flatMap((l) => l.points.map((q) => q[1]))];
  const yMax = Math.max(...yVals) * 1.08;
  const yMin = Math.min(0, Math.min(...yVals) * 1.08);
  drawChart(el.fpChart, {
    ariaLabel: "Target brightness relative to 2.2 µm against wavelength, with reference spectra",
    x: { type: "linear", min: WL_MIN, max: WL_MAX, label: "Wavelength (µm)" },
    y: { min: yMin, max: yMax, label: "Brightness relative to 2.2 µm" },
    lines, points: pts,
  });
  drawTable(el.fpTable, ["Wavelength (µm)", "Relative to 2.2 µm", "Brightness (mJy)", "Visit, image", "Saturated"],
    [...rows].sort((p, q) => p.frame.wavelength_um - q.frame.wavelength_um)
      .map((x) => [fmtUm(x.frame.wavelength_um), (x.frame.target_flux_mjy / norm).toFixed(3), x.frame.target_flux_mjy.toFixed(3), `${x.visit.n}, ${x.frame.i}`,
        x.frame.saturated ? "yes" : "no"]));
}

// ---------------------------------------------------------------- panels
/**
 * "About <target>" box above the mode tabs: description, verdict and motion.
 * Shown even before a target's images exist (then without the verdict).
 */
function renderIntro() {
  const name = displayName(state.target);
  el.introTitle.textContent = `About ${explanations?.targets?.[state.target]?.title || name}`;
  renderTargetPanel(el.introBody, { key: state.target, manifest, explanations });
  el.intro.hidden = false;
}

function renderTargetInfo() {
  renderIntro();
  if (!manifest) { el.verdictChip.hidden = true; return; }
  const verdict = manifest.verdict;
  el.verdictChip.hidden = !verdict;
  if (verdict) {
    el.verdictChip.textContent = explanations?.verdicts?.[verdict]?.title || verdict.replace(/_/g, " ");
    el.verdictChip.className = `chip verdict-chip verdict-${verdict}`;
    el.verdictChip.title = "Verdict: open “About” below for details";
  }
}

function openAbout(which) {
  if (which === "credits") renderCredits(el.aboutBody, credits);
  else if (which === "limits") renderEntry(el.aboutBody, explanations?.about?.limits, "What this tool can't tell you");
  else renderEntry(el.aboutBody, explanations?.about?.how_it_works, "How this works");
  const h = el.aboutBody.querySelector("h3");
  if (h) h.id = "about-title";
  if (typeof el.aboutDialog.showModal === "function") el.aboutDialog.showModal();
  else el.aboutDialog.setAttribute("open", "");
}

// ---------------------------------------------------------------- layers
const SWATCHES = {
  measured: `<path d="M3 9h4M11 9h4M9 3v4M9 11v4" stroke="#ffd84d" stroke-width="2"/><circle cx="9" cy="9" r="3.5" stroke="#ffd84d" fill="none" stroke-width="1.2"/>`,
  expected: `<rect x="4.5" y="4.5" width="9" height="9" stroke="#5cc8ff" fill="none" stroke-width="2"/>`,
  path: `<path d="M2 14L8 9L16 4" stroke="#ffd84d" stroke-opacity=".7" fill="none" stroke-width="1.6"/><circle cx="8" cy="9" r="2.2" fill="#ffd84d"/>`,
  gaia: `<circle cx="9" cy="9" r="6" stroke="#e6ebf5" fill="none" stroke-width="1.6"/>`,
  simbad: `<path d="M9 2L16 9L9 16L2 9Z" stroke="#ffa64d" fill="none" stroke-width="1.6"/>`,
  vsx: `<circle cx="9" cy="9" r="6.5" stroke="#c792ff" fill="none" stroke-width="1.6" stroke-dasharray="3 2"/>`,
  asteroids: `<circle cx="9" cy="9" r="6" stroke="#ff6b6b" fill="none" stroke-width="1.6"/><path d="M6.5 6.5l5 5M11.5 6.5l-5 5" stroke="#ff6b6b" stroke-width="1.6"/>`,
  flags: `<rect x="2" y="2" width="6" height="6" fill="#ff0000"/><rect x="10" y="2" width="6" height="6" fill="#ff8c00"/><rect x="6" y="10" width="6" height="6" fill="#286eff"/>`,
};

function buildLayerControls() {
  el.layerList.replaceChildren();
  for (const L of LAYERS) {
    const label = document.createElement("label");
    label.className = "check layer";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.dataset.layer = L.key;
    box.addEventListener("change", () => {
      if (box.checked) state.layers.add(L.key); else state.layers.delete(L.key);
      render();
      scheduleUrl();
    });
    const sw = document.createElement("span");
    sw.className = "sw";
    sw.innerHTML = `<svg viewBox="0 0 18 18" width="18" height="18" aria-hidden="true">${SWATCHES[L.swatch]}</svg>`;
    const text = document.createElement("span");
    text.append(L.label);
    const count = document.createElement("span");
    count.className = "muted count";
    count.dataset.countFor = L.key;
    text.append(count);
    if (L.note) {
      const n = document.createElement("small");
      n.className = "muted";
      n.textContent = ` (${L.note})`;
      text.append(n);
    }
    label.append(box, sw, text);
    el.layerList.append(label);
    if (L.key === "flags") {
      const legend = document.createElement("div");
      legend.className = "flag-legend muted";
      legend.innerHTML = `<span><i style="background:#ff0000"></i>saturated</span>
        <span><i style="background:#ff8c00"></i>cosmic ray, hot or bad pixel</span>
        <span><i style="background:#286eff"></i>other flagged</span>`;
      el.layerList.append(legend);
    }
  }
}

// ---------------------------------------------------------------- filters UI
/** Two-handle slider made of two range inputs. */
function dualRange(container, { min, max, step, labelLo, labelHi, onInput }) {
  container.replaceChildren();
  const fill = document.createElement("div");
  fill.className = "dual-fill";
  const track = document.createElement("div");
  track.className = "dual-track";
  track.append(fill);
  const mk = (label) => {
    const i = document.createElement("input");
    i.type = "range"; i.min = min; i.max = max; i.step = step;
    i.setAttribute("aria-label", label);
    return i;
  };
  const lo = mk(labelLo), hi = mk(labelHi);
  const paint = () => {
    const a = (+lo.value - min) / (max - min) * 100, b = (+hi.value - min) / (max - min) * 100;
    fill.style.left = `${a}%`;
    fill.style.width = `${b - a}%`;
  };
  lo.addEventListener("input", () => { if (+lo.value > +hi.value) lo.value = hi.value; paint(); onInput(+lo.value, +hi.value); });
  hi.addEventListener("input", () => { if (+hi.value < +lo.value) hi.value = lo.value; paint(); onInput(+lo.value, +hi.value); });
  container.append(track, lo, hi);
  return {
    set(a, b) { lo.value = a; hi.value = b; paint(); },
    setBounds(a, b) { for (const i of [lo, hi]) { i.min = a; i.max = b; } min = a; max = b; paint(); },
  };
}

let timeSlider = null, wlSlider = null;
let timeBounds = { min: 0, max: 1 }; // in days since 1970

function dataTimeBounds() {
  const ms = [];
  for (const v of visits()) {
    ms.push(dayMs(v.date_start), dayMs(v.date_end), dayMs(v.date_mid));
    for (const f of v.frames || []) ms.push(Date.parse(f.time));
  }
  return { min: Math.floor(Math.min(...ms) / DAY), max: Math.floor(Math.max(...ms) / DAY) };
}

function setupFilters() {
  timeSlider = dualRange(el.timeRange, {
    min: 0, max: 1, step: 1, labelLo: "From date", labelHi: "To date",
    onInput: (a, b) => {
      const full = a <= timeBounds.min && b >= timeBounds.max;
      state.from = full ? null : isoDay(a * DAY);
      state.to = full ? null : isoDay(b * DAY);
      filtersChanged();
    },
  });
  el.dateFrom.addEventListener("change", () => { state.from = el.dateFrom.value || null; filtersChanged(); });
  el.dateTo.addEventListener("change", () => { state.to = el.dateTo.value || null; filtersChanged(); });

  wlSlider = dualRange(el.wlRange, {
    min: WL_MIN, max: WL_MAX, step: 0.01, labelLo: "Shortest wavelength", labelHi: "Longest wavelength",
    onInput: (a, b) => {
      state.wl = a <= WL_MIN && b >= WL_MAX ? null : [a, b];
      filtersChanged();
    },
  });
  el.wlPresets.replaceChildren();
  const preset = (text, title, range) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = text;
    b.title = title;
    b.dataset.wl = range ? range.join("-") : "";
    b.addEventListener("click", () => { state.wl = range; filtersChanged(); });
    el.wlPresets.append(b);
  };
  preset("All", "No wavelength filter", null);
  for (const d of DETECTORS) preset(`D${d.d}`, `Detector ${d.d}: ${d.lo}–${d.hi} µm`, [d.lo, d.hi]);
}

function buildTimeControls() {
  timeBounds = dataTimeBounds();
  timeSlider.setBounds(timeBounds.min, timeBounds.max);
  el.dateFrom.min = el.dateTo.min = isoDay(timeBounds.min * DAY);
  el.dateFrom.max = el.dateTo.max = isoDay(timeBounds.max * DAY);
  el.yearButtons.replaceChildren();
  const add = (text, from, to) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = text;
    b.dataset.range = `${from || ""}|${to || ""}`;
    b.addEventListener("click", () => { state.from = from; state.to = to; filtersChanged(); });
    el.yearButtons.append(b);
  };
  add("All", null, null);
  const y0 = new Date(timeBounds.min * DAY).getUTCFullYear(), y1 = new Date(timeBounds.max * DAY).getUTCFullYear();
  for (let y = y0; y <= y1; y++) add(String(y), `${y}-01-01`, `${y}-12-31`);
}

function syncFilterControls() {
  const fromDay = state.from ? Math.floor(dayMs(state.from) / DAY) : timeBounds.min;
  const toDay = state.to ? Math.floor(dayMs(state.to) / DAY) : timeBounds.max;
  timeSlider.set(Math.max(fromDay, timeBounds.min), Math.min(toDay, timeBounds.max));
  el.dateFrom.value = state.from || "";
  el.dateTo.value = state.to || "";
  el.timeOut.textContent = state.from || state.to
    ? `${state.from ? fmtDate(state.from) : "start"} – ${state.to ? fmtDate(state.to) : "end"}` : "all dates";
  for (const b of el.yearButtons.querySelectorAll("button")) {
    b.setAttribute("aria-pressed", String(b.dataset.range === `${state.from || ""}|${state.to || ""}`));
  }
  wlSlider.set(state.wl ? state.wl[0] : WL_MIN, state.wl ? state.wl[1] : WL_MAX);
  el.wlOut.textContent = state.wl ? `${fmtUm(state.wl[0])}–${fmtUm(state.wl[1])} µm` : "all wavelengths";
  for (const b of el.wlPresets.querySelectorAll("button")) {
    b.setAttribute("aria-pressed", String(b.dataset.wl === (state.wl ? state.wl.join("-") : "")));
  }

  // match count and warnings
  const warn = [];
  if (state.wl) {
    const ff = filteredFrames();
    const vs = new Set(ff.map((x) => x.visit.n));
    el.matchCount.textContent = `${ff.length} image${ff.length === 1 ? "" : "s"}, ${vs.size} visit${vs.size === 1 ? "" : "s"}`;
    const missing = visits().filter((v) => !vs.has(v.n) && v.frames?.some((f) => passTime(Date.parse(f.time)))).map((v) => v.n);
    if (missing.length) warn.push(`No images in this range for visit${missing.length > 1 ? "s" : ""} ${missing.join(", ")}.`);
  } else {
    const nv = visits().filter(visitPasses).length, nf = framesPassingTime().length;
    el.matchCount.textContent = `${nv} visit${nv === 1 ? "" : "s"}, ${nf} single image${nf === 1 ? "" : "s"}`;
  }
  el.matchWarn.textContent = warn.join(" ");
  el.matchWarn.hidden = !warn.length;
  renderFilterChips();
}

/** Chips above the image showing which filters are on, each with a ✕ to clear it. */
function renderFilterChips() {
  const chips = [];
  if (state.wl) chips.push({ text: `${fmtUm(state.wl[0])}–${fmtUm(state.wl[1])} µm`, clear: () => { state.wl = null; } });
  if (state.from || state.to) {
    chips.push({ text: `${state.from ? fmtDate(state.from) : "start"} – ${state.to ? fmtDate(state.to) : "end"}`, clear: () => { state.from = state.to = null; } });
  }
  el.filtersSummary.textContent = chips.length ? `${chips.length} on` : "";
  el.filterChips.hidden = !chips.length;
  el.filterChips.replaceChildren();
  if (!chips.length) return;
  const label = document.createElement("span");
  label.className = "muted small";
  label.textContent = "Filters on:";
  el.filterChips.append(label);
  for (const c of chips) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "filter-chip";
    b.title = "Remove this filter";
    b.setAttribute("aria-label", `Remove filter ${c.text}`);
    b.textContent = `${c.text} ✕`;
    b.addEventListener("click", () => { c.clear(); filtersChanged(); });
    el.filterChips.append(b);
  }
}

let lastWl = null;
function filtersChanged() {
  // Turning the wavelength filter off returns to the visit stacks it had replaced.
  if (lastWl && !state.wl && state.mode === "flipbook") state.frame = null;
  lastWl = state.wl;
  normalizeSelection();
  render();
  renderFingerprint();
  scheduleUrl();
}

// ---------------------------------------------------------------- controls UI
function buildTargetButtons() {
  el.targets.replaceChildren();
  const add = (t, extraClass) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = t.name;
    b.dataset.key = t.key;
    if (extraClass) b.classList.add(extraClass);
    b.addEventListener("click", () => { hideSearchMessage(); openTarget(t.key, { push: true }); });
    el.targets.append(b);
    loadFields(t.key).then((sizes) => {
      if (!sizes) { b.classList.add("unprocessed"); b.title = `${t.name} isn't processed yet`; }
    });
  };
  TARGETS.forEach((t) => add(t));
  TEST_TARGETS.forEach((t) => add(t, "test"));
}

function buildFieldControls() {
  el.fovButtons.replaceChildren();
  for (const sz of fields) {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.fov = sz;
    b.innerHTML = `${sz} px <small class="muted">${fieldArcmin(sz).toFixed(1)}′</small>`;
    b.addEventListener("click", () => { if (sz !== state.fov) openFov(sz, { ...currentOpts() }, ++loadToken); });
    el.fovButtons.append(b);
  }
  el.visitStrip.replaceChildren();
  for (const v of visits()) {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.n = v.n;
    const mid = new Date(`${v.date_mid}T00:00:00Z`);
    b.innerHTML = `<span>Visit ${v.n}</span><small>${mid.toLocaleString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" })}</small>`;
    b.addEventListener("click", () => {
      setPlaying(false);
      if (state.wl) {
        const first = filteredFrames().find((x) => x.visit.n === v.n);
        if (first) state.frame = first.ref;
      } else {
        state.frame = null;
      }
      state.visit = v.n;
      normalizeSelection();
      render();
      scheduleUrl();
    });
    el.visitStrip.append(b);
  }
}

let pickersSig = "";
function fillPickers() {
  const pk = pickable();
  // Rebuilding a <select> closes it, so only rebuild when the choices change.
  const sig = `${state.target}|${state.fov}|${pk.join(",")}`;
  if (sig !== pickersSig) {
    pickersSig = sig;
    buildPickerOptions(pk);
  }
  el.pickA.value = state.a || "";
  el.pickB.value = state.b || "";
}

function buildPickerOptions(pk) {
  for (const select of [el.pickA, el.pickB]) {
    select.replaceChildren();
    const stacks = pk.filter((r) => parseRef(r).i == null);
    if (stacks.length) {
      const g = document.createElement("optgroup");
      g.label = "Visit stacks";
      for (const r of stacks) { const it = resolveRef(r); g.append(new Option(`Visit ${it.visit.n} stack (${fmtDate(it.visit.date_mid)})`, r)); }
      select.append(g);
    }
    for (const v of visits()) {
      const refs = pk.filter((r) => { const p = parseRef(r); return p.i != null && p.n === v.n; });
      if (!refs.length) continue;
      const g = document.createElement("optgroup");
      g.label = `Visit ${v.n}: single images`;
      for (const r of refs) {
        const f = resolveRef(r).frame;
        g.append(new Option(`Image ${f.i} · ${fmtUm(f.wavelength_um)} µm · D${f.detector}`, r));
      }
      select.append(g);
    }
  }
}

function syncUI() {
  for (const b of el.targets.querySelectorAll("button")) b.setAttribute("aria-pressed", String(b.dataset.key === state.target));
  if (!manifest) return;
  for (const b of el.fovButtons.querySelectorAll("button")) b.setAttribute("aria-pressed", String(+b.dataset.fov === state.fov));

  const pairOk = pickable().length >= 2;
  for (const b of el.modeButtons.querySelectorAll("button")) {
    b.setAttribute("aria-pressed", String(b.dataset.mode === state.mode));
    b.disabled = (b.dataset.mode === "blink" || b.dataset.mode === "difference") && !pairOk;
  }
  el.modeNote.textContent = pairOk ? "" : `Blink and difference need at least two images; the filters leave ${pickable().length}.`;
  el.modeNote.hidden = pairOk;

  const seqNow = sequence();
  for (const b of el.visitStrip.querySelectorAll("button")) {
    const n = +b.dataset.n;
    b.setAttribute("aria-pressed", String(n === state.visit));
    b.disabled = state.wl
      ? !filteredFrames().some((x) => x.visit.n === n)
      : !visits().some((v) => v.n === n && visitPasses(v));
  }
  el.modeHint.textContent = modeHint();
  el.player.hidden = state.mode === "brightness";
  el.flipbook.hidden = state.mode !== "flipbook";
  el.backToStack.hidden = !(state.mode === "flipbook" && state.frame && !state.wl);
  el.pair.hidden = !(state.mode === "blink" || state.mode === "difference");
  el.pairHeading.textContent = state.mode === "difference" ? "Difference between" : "Blink between";
  el.showA.parentElement.hidden = state.mode !== "blink";
  el.diffControls.hidden = state.mode !== "difference";
  el.playback.hidden = !(state.mode === "flipbook" || state.mode === "blink");
  $("prev").disabled = $("next").disabled = el.play.disabled = state.mode === "flipbook" && seqNow.length < 2;
  // Display settings only apply to flipbook and blink images; keep the section in place but say so.
  const displayApplies = state.mode === "flipbook" || state.mode === "blink";
  for (const input of el.display.querySelectorAll("input, select, button")) input.disabled = !displayApplies;
  fillPickers();

  el.color.checked = state.color;
  el.cmap.value = state.cmap;
  el.brightness.value = state.brightness;
  el.brightOut.textContent = state.brightness.toFixed(2);
  el.contrast.value = state.contrast;
  el.contrastOut.textContent = `${(2 ** state.contrast).toFixed(2)}×`;
  const item = state.mode === "flipbook" || state.mode === "blink" ? currentItem() : null;
  const rgbShown = state.color && item?.kind === "visit";
  el.displayNote.textContent = !displayApplies
    ? `Display settings apply to Flipbook and Blink. ${state.mode === "difference" ? "Difference uses its own red/white/blue colors." : "Brightness mode shows a chart."}`
    : rgbShown ? "Brightness, contrast and color maps work on the grayscale pixel values (.f32). Turn off Color to use them on a stack." : "";
  el.displayNote.hidden = !el.displayNote.textContent;

  for (const box of el.layerList.querySelectorAll("input[data-layer]")) box.checked = state.layers.has(box.dataset.layer);
  for (const c of el.layerList.querySelectorAll("[data-count-for]")) {
    const key = c.dataset.countFor;
    c.textContent = ["gaia", "simbad", "vsx", "asteroids"].includes(key) ? ` (${overlays.filter((o) => o.layer === key).length})` : "";
  }
  el.play.textContent = state.playing ? "⏸ Pause" : state.mode === "blink" ? "▶ Blink" : "▶ Play";
  el.speed.value = state.speed;
  el.speedOut.textContent = state.speed;
  syncFilterControls();
}

function setupControls() {
  for (const b of el.modeButtons.querySelectorAll("button")) b.addEventListener("click", () => setMode(b.dataset.mode));
  el.pickA.addEventListener("change", () => { state.a = el.pickA.value; state.showB = false; state.k = null; render(); scheduleUrl(); });
  el.pickB.addEventListener("change", () => { state.b = el.pickB.value; state.showB = true; state.k = null; render(); scheduleUrl(); });
  el.showA.addEventListener("click", () => { setPlaying(false); state.showB = false; render(); });
  el.showB.addEventListener("click", () => { setPlaying(false); state.showB = true; render(); });
  $("swap-ab").addEventListener("click", () => { [state.a, state.b] = [state.b, state.a]; state.k = null; render(); scheduleUrl(); });
  el.kSlider.addEventListener("input", () => { state.k = +el.kSlider.value; render(); });
  $("k-auto").addEventListener("click", () => { state.k = null; render(); });
  el.backToStack.addEventListener("click", () => { setPlaying(false); state.frame = null; normalizeSelection(); render(); scheduleUrl(); });
  $("prev").addEventListener("click", () => { setPlaying(false); step(-1); });
  $("next").addEventListener("click", () => { setPlaying(false); step(1); });
  el.play.addEventListener("click", () => setPlaying(!state.playing));
  el.speed.addEventListener("input", () => {
    state.speed = +el.speed.value;
    el.speedOut.textContent = state.speed;
    if (state.playing) setPlaying(true);
  });

  el.color.addEventListener("change", () => { state.color = el.color.checked; render(); scheduleUrl(); });
  for (const name of COLORMAP_NAMES) el.cmap.append(new Option(name[0].toUpperCase() + name.slice(1), name));
  el.cmap.addEventListener("change", () => { state.cmap = el.cmap.value; render(); scheduleUrl(); });
  el.brightness.addEventListener("input", () => { state.brightness = +el.brightness.value; render(); });
  el.contrast.addEventListener("input", () => { state.contrast = +el.contrast.value; render(); });
  $("display-reset").addEventListener("click", () => { state.brightness = 0; state.contrast = 0; render(); });

  el.searchForm.addEventListener("submit", (e) => { e.preventDefault(); search(el.searchInput.value); });
  $("info-close").addEventListener("click", closeInfo);
  for (const b of document.querySelectorAll("[data-dialog]")) b.addEventListener("click", () => openAbout(b.dataset.dialog));
  el.fingerprint.addEventListener("toggle", renderFingerprint);

  let resizeTimer = null;
  new ResizeObserver(() => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (state.mode === "brightness") renderBrightness();
      renderFingerprint();
    }, 150);
  }).observe(document.querySelector(".viewer-col"));

  document.addEventListener("keydown", (e) => {
    if (!manifest || e.target.closest("input, select, textarea, dialog") || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "ArrowRight") { setPlaying(false); step(1); }
    else if (e.key === "ArrowLeft") { setPlaying(false); step(-1); }
    else if (e.key === " " && !e.target.closest("button")) setPlaying(!state.playing);
    else if (e.key === "+" || e.key === "=") zoomCenter(Math.SQRT2);
    else if (e.key === "-") zoomCenter(Math.SQRT1_2);
    else if (e.key === "0") resetView();
    else if (e.key === "Escape") { closeInfo(); hideTooltip(); }
    else return;
    e.preventDefault();
  });
}

/** One line under the mode tabs saying what the current mode does. */
function modeHint() {
  switch (state.mode) {
    case "blink": return "Flips between two pictures, A and B (pick them below the image). Motion makes a dot jump.";
    case "difference": return "Shows B − k × A. White = no change, blue = brighter in A, red = brighter in B. A moving object leaves a blue/red pair.";
    case "brightness": return "Charts the target's brightness over time. Pick one wavelength range under Filters first.";
    default:
      if (state.wl) return "Plays the single images in your wavelength range, from all visits, in time order.";
      if (state.frame) return "Showing one single image. Step through this visit's images below, or go back to the visit stack.";
      return "Plays the visits in order, like a slideshow. Watch the center dot move against the crosshair.";
  }
}

function setMode(mode) {
  if (mode === state.mode) return;
  setPlaying(false);
  state.mode = ["blink", "difference", "brightness"].includes(mode) ? mode : "flipbook";
  state.showB = false;
  normalizeSelection();
  render().then(() => applyTransform());
  scheduleUrl();
  if (state.mode === "blink") setPlaying(true); // blink starts alternating straight away
}

function step(d) {
  if (state.mode === "blink") {
    state.showB = !state.showB;
  } else if (state.mode === "flipbook") {
    const seq = sequence();
    if (!seq.length) return;
    const i = seq.indexOf(flipRef());
    const r = resolveRef(seq[(i + d + seq.length) % seq.length]);
    state.visit = r.visit.n;
    state.frame = r.kind === "frame" ? r.ref : null;
    scheduleUrl();
  } else {
    return;
  }
  render();
}

function setPlaying(on) {
  clearInterval(timer);
  timer = null;
  state.playing = !!on && !!manifest && (state.mode === "flipbook" || state.mode === "blink");
  if (state.playing) timer = setInterval(() => step(1), 1000 / state.speed);
  el.play.textContent = state.playing ? "⏸ Pause" : state.mode === "blink" ? "▶ Blink" : "▶ Play";
}

// ---------------------------------------------------------------- opening targets and fields
function currentOpts() {
  return { mode: state.mode, visit: state.visit, frame: state.frame, a: state.a, b: state.b, zoom: state.zoom };
}

async function openTarget(key, opts = {}) {
  if (live.key && live.key !== key) stopLive(true); // the user moved on from a field being built
  const token = ++loadToken;
  setPlaying(false);
  const t = targetByKey(key);
  state.target = key;
  manifest = null; fields = null; overlays = [];
  markerInfo = new Map();
  if (el.markers) el.markers.replaceChildren();
  closeInfo();
  hideTooltip();
  if (opts.layers) state.layers = new Set(opts.layers);
  for (const k of ["from", "to", "wl", "cmap", "color"]) if (k in opts) state[k] = opts[k];
  if (!("from" in opts)) state.from = state.to = null; // dates differ per target; keep wavelength and display choices
  el.targetName.textContent = displayName(key);
  renderIntro();
  el.fieldInfo.textContent = "";
  el.label.replaceChildren();
  el.badge.hidden = true;
  el.thumbsPanel.hidden = true;
  syncUI();

  const sizes = await loadFields(key);
  if (token !== loadToken) return;
  if (!sizes) {
    state.fov = null;
    el.controls.hidden = true;
    el.modeBar.hidden = el.player.hidden = el.verdictChip.hidden = true;
    el.fovButtons.replaceChildren();
    el.fieldInfo.textContent = "";
    el.viewport.hidden = false;
    el.brightnessView.hidden = true;
    clearCanvas(el.canvas); clearCanvas(el.flagsCanvas);
    el.overlay.innerHTML = "";
    if (isLiveKey(key) && liveQueries.has(key)) {
      // A shared link to a live field the server no longer has (or hasn't built yet): build it
      showViewerMessage(`Building ${displayName(key)}…`);
      writeUrl(opts.push);
      if (live.key !== key) liveLookup(liveQueries.get(key));
      return;
    }
    showViewerMessage(`${t ? t.name : key} isn't processed yet.`);
    writeUrl(opts.push);
    return;
  }
  fields = sizes;
  const ov = isLiveKey(key) ? [] : await loadOverlays(key); // live fields have no overlays.json
  if (token !== loadToken) return;
  overlays = ov;
  const fov = sizes.includes(+opts.fov) ? +opts.fov : sizes.includes(51) ? 51 : sizes[0];
  await openFov(fov, opts, token);
}

async function openFov(fov, opts, token) {
  setPlaying(false);
  let m;
  try {
    m = await fetchJSON(`${targetBase.get(state.target) || REAL_DIR}/${state.target}/fov${fov}/manifest.json`);
  } catch {
    if (token === loadToken) {
      showViewerMessage(`The ${fov} px field couldn't be loaded (${targetBase.get(state.target) || REAL_DIR}/${state.target}/fov${fov}/manifest.json). If files were just moved or renamed, reload the page with Ctrl+Shift+R.`);
    }
    return;
  }
  if (token !== loadToken) return;

  manifest = m;
  state.fov = fov;
  const vs = visits();
  state.mode = ["blink", "difference", "brightness"].includes(opts.mode) ? opts.mode : "flipbook";
  state.visit = vs.some((v) => v.n === +opts.visit) ? +opts.visit : vs[0]?.n ?? 1;
  state.frame = resolveRef(opts.frame)?.kind === "frame" ? resolveRef(opts.frame).ref : null;
  state.a = resolveRef(opts.a)?.ref || null;
  state.b = resolveRef(opts.b)?.ref || null;
  state.showB = false;
  state.k = null;
  if (opts.zoom != null && !Number.isNaN(+opts.zoom)) state.zoom = Math.min(Math.max(+opts.zoom, ZOOM_MIN), ZOOM_MAX);

  el.canvas.width = el.canvas.height = fov;
  el.flagsCanvas.width = el.flagsCanvas.height = fov;
  closeInfo(); // pixel positions in the panel belong to the old field size
  el.fieldInfo.textContent = `${fov} × ${fov} px · ${fieldArcmin(fov).toFixed(1)}′ across · north up, east left`;
  if (isFakeTarget(state.target)) {
    // Never let fake test images pass for real ones.
    const tag = document.createElement("span");
    tag.className = "fake-tag";
    tag.title = "These images come from fake_data/ and will be replaced automatically when the real files are posted to data/.";
    tag.textContent = "FAKE TEST IMAGES";
    el.fieldInfo.append(" ", tag);
  }
  el.controls.hidden = false;
  el.modeBar.hidden = false;
  lastWl = state.wl;
  buildOverlay();
  buildFieldControls();
  buildTimeControls();
  normalizeSelection();
  centerOnTarget();
  hideViewerMessage();
  renderTargetInfo();
  await render();
  applyTransform();
  for (const v of visits()) if (v.image) loadImage(fovDir() + v.image).catch(() => {}); // smooth first flipbook play
  renderFingerprint();
  writeUrl(opts.push);
  if (state.mode === "blink") setPlaying(true);
}

// ---------------------------------------------------------------- search
async function search(text) {
  const q = text.trim();
  if (!q) return;
  const named = findTargetByName(q);
  if (named) { hideSearchMessage(); return openTarget(named.key, { push: true }); }
  const c = parseCoords(q);
  if (!c) return liveLookup(q); // the server resolves names (Sesame, Gaia, CatWISE)
  for (const t of TARGETS) {
    const sizes = await loadFields(t.key);
    const big = sizes ? sizes[sizes.length - 1] : LARGEST_FIELD;
    if (!inField(skyToPx(c.ra, c.dec, t.ra, t.dec, big), big)) continue;
    if (!sizes) {
      showSearchMessage(`That position is in the ${t.name} field, but it isn't processed yet.`);
      return openTarget(t.key, { push: true });
    }
    const fov = sizes.find((sz) => inField(skyToPx(c.ra, c.dec, t.ra, t.dec, sz), sz));
    const [col, row] = skyToPx(c.ra, c.dec, t.ra, t.dec, fov);
    showSearchMessage(`Opened the ${t.name} field (${fov} px). That position is at column ${col.toFixed(1)}, row ${row.toFixed(1)}.`, "info");
    return openTarget(t.key, { fov, push: true });
  }
  return liveLookup(q);
}

// ---------------------------------------------------------------- live lookup
// Ask the server to build the field, poll its status every 10 s while the user waits, open the
// quick preview as soon as it exists, and offer the full build when it is done.
const live = { key: null, timer: null, showedPreview: false };

function stopLive(leave) {
  clearTimeout(live.timer);
  // Tell the server nobody here is waiting any more, so another search can run sooner
  if (leave && live.key) fetch(`${LIVE_SERVER}/api/leave/${encodeURIComponent(live.key)}`).catch(() => {});
  live.key = live.timer = null;
}

async function liveLookup(q) {
  stopLive(true);
  showSearchMessage(`Looking up “${q}”…`, "info");
  let s;
  try {
    const r = await fetch(`${LIVE_SERVER}/api/lookup?q=${encodeURIComponent(q)}&size=51`);
    const body = await r.json().catch(() => ({}));
    if (r.status === 503) return showSearchMessage("The server is busy. Try again in a few minutes.");
    if (!r.ok) return showSearchMessage(typeof body.detail === "string" ? body.detail : `“${q}” couldn't be looked up.`);
    s = body;
  } catch {
    return showSearchMessage("Live lookup is unavailable right now. The five targets above still work.");
  }
  liveQueries.set(s.key, q);
  Object.assign(live, { key: s.key, showedPreview: false });
  if (!state.target) { // nothing open yet (a ?q= link): say what is being built
    el.targetName.textContent = q;
    showViewerMessage(`Building ${q}…`);
  }
  handleLiveStatus(s);
}

function liveStatusText(s) {
  if (s.queue_position) return `“${liveQueries.get(s.key)}”: in line (${s.queue_position}). Another field is being built first.`;
  const { done, total } = s.progress || {};
  const count = total ? ` (${done} / ${total})` : "";
  const which = s.files_ready ? "Showing the quick preview. Full build" : "Building a quick preview";
  return `${which}: ${s.stage}${count}. A new field takes about 5–15 minutes.`;
}

function handleLiveStatus(s) {
  if (s.key !== live.key) return;
  const finished = s.stage === "done";
  if (s.files_ready) fieldsCache.delete(s.key); // an earlier "not built yet" answer may be cached
  if (s.files_ready && state.target !== s.key) {
    live.showedPreview = !finished;
    openTarget(s.key, { push: true });
  } else if (s.files_ready && !manifest) {
    // A shared link was waiting on this field ("Building …"): show it now
    live.showedPreview = !finished;
    openTarget(s.key);
  }
  if (finished) {
    stopLive(false);
    if (!live.showedPreview) return hideSearchMessage();
    showSearchMessage("The full build is ready (all images). ", "info");
    const load = document.createElement("button");
    load.type = "button";
    load.textContent = "Load it";
    load.addEventListener("click", () => location.reload()); // the URL keeps the field; files are revalidated
    el.searchMsg.append(load);
    return;
  }
  if (s.error) {
    stopLive(false);
    return showSearchMessage(s.files_ready ? `Showing the quick preview; the full build failed: ${s.error}` : s.error);
  }
  showSearchMessage(liveStatusText(s), "info");
  live.timer = setTimeout(pollLive, LIVE_POLL_MS);
}

async function pollLive() {
  const key = live.key;
  if (!key) return;
  try {
    const r = await fetch(`${LIVE_SERVER}/api/status/${encodeURIComponent(key)}`);
    if (live.key !== key) return;
    if (r.status === 404) { // the server restarted and forgot this build: ask again
      stopLive(false);
      return liveLookup(liveQueries.get(key));
    }
    handleLiveStatus(await r.json());
  } catch {
    if (live.key === key) live.timer = setTimeout(pollLive, LIVE_POLL_MS); // network hiccup: keep trying
  }
}

// ---------------------------------------------------------------- URL state
function writeUrl(push = false) {
  const p = new URLSearchParams();
  if (state.target) p.set("target", state.target);
  if (liveQueries.has(state.target)) p.set("q", liveQueries.get(state.target)); // rebuilds the field if needed
  if (manifest) {
    p.set("fov", state.fov);
    if (state.mode !== "flipbook") p.set("mode", state.mode);
    if (state.mode === "flipbook") {
      p.set("visit", state.visit);
      if (state.frame) p.set("frame", state.frame);
    }
    if ((state.mode === "blink" || state.mode === "difference") && state.a && state.b) { p.set("a", state.a); p.set("b", state.b); }
    if (state.zoom !== 1) p.set("zoom", +state.zoom.toFixed(2));
    if (state.color) p.set("color", "rgb");
    if (state.cmap !== "grayscale") p.set("cmap", state.cmap);
    p.set("layers", LAYERS.map((L) => L.key).filter((k) => state.layers.has(k)).join(","));
    if (state.from) p.set("from", state.from);
    if (state.to) p.set("to", state.to);
    if (state.wl) p.set("wl", `${state.wl[0]}-${state.wl[1]}`);
  }
  const url = `${location.pathname}?${p.toString().replace(/%2C/g, ",")}`;
  if (url === `${location.pathname}${location.search}`) return;
  history[push ? "pushState" : "replaceState"](null, "", url);
}

let urlTimer = null;
function scheduleUrl() {
  clearTimeout(urlTimer);
  urlTimer = setTimeout(() => writeUrl(false), 150);
}

function openFromUrl() {
  const p = new URLSearchParams(location.search);
  const wl = /^(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$/.exec(p.get("wl") || "");
  const date = (v) => (/^\d{4}-\d{2}-\d{2}$/.test(v || "") ? v : null);
  // ?q=<name or coordinates> alone searches, so other sites can link to any position
  if (p.get("q") && !p.get("target")) return search(p.get("q"));
  if (p.get("q") && isLiveKey(p.get("target"))) liveQueries.set(p.get("target"), p.get("q"));
  openTarget(p.get("target") || TARGETS[0].key, {
    fov: p.get("fov"),
    mode: p.get("mode"),
    visit: p.get("visit"),
    frame: p.get("frame"),
    a: p.get("a"),
    b: p.get("b"),
    zoom: p.get("zoom") ?? 1,
    color: p.get("color") === "rgb",
    cmap: COLORMAP_NAMES.includes(p.get("cmap")) ? p.get("cmap") : "grayscale",
    layers: p.has("layers") ? p.get("layers").split(",").filter((k) => LAYERS.some((L) => L.key === k)) : DEFAULT_LAYERS,
    from: date(p.get("from")),
    to: date(p.get("to")),
    wl: wl && +wl[1] <= +wl[2] && (+wl[1] > WL_MIN || +wl[2] < WL_MAX)
      ? [Math.max(WL_MIN, +wl[1]), Math.min(WL_MAX, +wl[2])] : null, // full range = no filter
  });
}

// ---------------------------------------------------------------- start
fetchJSONFirst("explanations.json").then((j) => { explanations = j || {}; renderTargetInfo(); }).catch(() => {});
fetchJSONFirst("credits.json").then((j) => { credits = Array.isArray(j) ? j : []; }).catch(() => {});
buildLayerControls();
buildTargetButtons();
setupFilters();
setupPanZoom();
setupControls();
window.addEventListener("popstate", openFromUrl);
openFromUrl();
