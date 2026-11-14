// Drawing from the .f32 files: brightness/contrast, colormaps and the difference image.
// .f32 = raw little-endian float32, S x S values, row 0 first (north), NaN = no data.

const f32Cache = new Map();

/** Fetch an .f32 file as a Float32Array of S*S values. */
export function loadF32(url, S) {
  if (!f32Cache.has(url)) {
    const p = fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${url}`);
        return r.arrayBuffer();
      })
      .then((buf) => {
        if (buf.byteLength !== S * S * 4) throw new Error(`${url} has ${buf.byteLength} bytes, expected ${S * S * 4}`);
        // Float32Array uses the machine's byte order; read explicitly as little-endian to be safe.
        const dv = new DataView(buf);
        const out = new Float32Array(S * S);
        for (let i = 0; i < out.length; i++) out[i] = dv.getFloat32(i * 4, true);
        return out;
      });
    p.catch(() => f32Cache.delete(url));
    f32Cache.set(url, p);
  }
  return f32Cache.get(url);
}

/** q-th percentile (0..100) of the finite values in one or more arrays. */
export function percentile(arrays, q) {
  const list = Array.isArray(arrays) ? arrays : [arrays];
  let n = 0;
  for (const a of list) for (const v of a) if (Number.isFinite(v)) n++;
  if (!n) return NaN;
  const vals = new Float32Array(n);
  let j = 0;
  for (const a of list) for (const v of a) if (Number.isFinite(v)) vals[j++] = v;
  vals.sort();
  const pos = (q / 100) * (n - 1);
  const lo = Math.floor(pos), hi = Math.ceil(pos);
  return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo);
}

/** Default display range: median (sky) to 99.9th percentile, the same idea as the PNGs. */
export function autoRange(arrays) {
  const lo = percentile(arrays, 50), hi = percentile(arrays, 99.9);
  return { lo, hi: hi > lo ? hi : lo + 1e-6 };
}

// ---------------------------------------------------------------- colormaps
// Ten evenly spaced stops sampled from the matplotlib maps, interpolated to 256 entries.
const STOPS = {
  grayscale: ["#000000", "#ffffff"],
  inferno: ["#000004", "#1b0c41", "#4a0c6b", "#781c6d", "#a52c60", "#cf4446", "#ed6925", "#fb9b06", "#f7d13d", "#fcffa4"],
  viridis: ["#440154", "#482878", "#3e4989", "#31688e", "#26828e", "#1f9e89", "#35b779", "#6ece58", "#b5de2b", "#fde725"],
  magma: ["#000004", "#180f3d", "#440f76", "#721f81", "#9e2f7f", "#cd4071", "#f1605d", "#fd9668", "#feca8d", "#fcfdbf"],
};
export const COLORMAP_NAMES = Object.keys(STOPS);

const hexRgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const luts = {};
function lut(name) {
  if (!luts[name]) {
    const stops = (STOPS[name] || STOPS.grayscale).map(hexRgb);
    const t = new Uint8ClampedArray(256 * 3);
    for (let i = 0; i < 256; i++) {
      const x = (i / 255) * (stops.length - 1);
      const a = Math.min(Math.floor(x), stops.length - 2), f = x - a;
      for (let c = 0; c < 3; c++) t[i * 3 + c] = stops[a][c] + (stops[a + 1][c] - stops[a][c]) * f;
    }
    luts[name] = t;
  }
  return luts[name];
}

const ASINH10 = Math.asinh(10);

/**
 * Draw one grayscale data image onto ctx (canvas is S x S).
 * brightness: -0.5..0.5 shift; contrast: multiplier around the middle of the range.
 */
export function drawData(ctx, data, S, { lo, hi, brightness = 0, contrast = 1, cmap = "grayscale" }) {
  const img = ctx.createImageData(S, S);
  const px = img.data, table = lut(cmap), span = hi - lo;
  for (let i = 0; i < data.length; i++) {
    const v = data[i];
    const o = i * 4;
    if (!Number.isFinite(v)) { px[o + 3] = 0; continue; } // no data -> transparent
    let t = ((v - lo) / span - 0.5) * contrast + 0.5 + brightness;
    t = t <= 0 ? 0 : t >= 1 ? 1 : t;
    const k = Math.round((Math.asinh(10 * t) / ASINH10) * 255) * 3;
    px[o] = table[k]; px[o + 1] = table[k + 1]; px[o + 2] = table[k + 2]; px[o + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
}

// ---------------------------------------------------------------- difference image
/**
 * Default k: median of B / A over pixels where both images are bright
 * (above their own 99th percentile), ignoring NaN. Falls back to 1.
 */
export function defaultK(A, B) {
  const pa = percentile(A, 99), pb = percentile(B, 99);
  const ratios = [];
  for (let i = 0; i < A.length; i++) {
    const a = A[i], b = B[i];
    if (Number.isFinite(a) && Number.isFinite(b) && a > pa && b > pb && a !== 0) ratios.push(b / a);
  }
  if (!ratios.length) return 1;
  ratios.sort((x, y) => x - y);
  const m = ratios.length >> 1;
  const k = ratios.length % 2 ? ratios[m] : (ratios[m - 1] + ratios[m]) / 2;
  return Number.isFinite(k) && k > 0 ? k : 1;
}

/** B - k*A as a new array (NaN where either is NaN). */
export function difference(A, B, k) {
  const D = new Float32Array(A.length);
  for (let i = 0; i < A.length; i++) D[i] = B[i] - k * A[i];
  return D;
}

/** Symmetric color limit: 99.5th percentile of |D|. */
export function diffLimit(D) {
  const abs = D.map(Math.abs);
  const L = percentile(abs, 99.5);
  return L > 0 ? L : 1e-6;
}

// Diverging: blue (brighter in A) <- white (no change) -> red (brighter in B), as the plan specifies.
const BLUE = [57, 135, 229], RED = [230, 103, 103], WHITE = [255, 255, 255];

export function diffColor(t) { // t in -1..1
  const c = t < 0 ? BLUE : RED, f = Math.min(Math.abs(t), 1);
  return WHITE.map((w, i) => Math.round(w + (c[i] - w) * f));
}

export function drawDifference(ctx, D, S, limit) {
  const img = ctx.createImageData(S, S);
  const px = img.data;
  for (let i = 0; i < D.length; i++) {
    const o = i * 4, v = D[i];
    if (!Number.isFinite(v)) { px[o + 3] = 0; continue; }
    const [r, g, b] = diffColor(v / limit);
    px[o] = r; px[o + 1] = g; px[o + 2] = b; px[o + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
}
