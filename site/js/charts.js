// Small SVG charts for brightness mode and the infrared fingerprint.
// One y-axis, thin marks, recessive grid, per-point hover tooltip, larger hit targets.

const NS = "http://www.w3.org/2000/svg";
const s = (tag, attrs = {}, parent) => {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.append(e);
  return e;
};

/** ~n "nice" ticks covering [min, max]. */
export function niceTicks(min, max, n = 5) {
  if (!(max > min)) return [min];
  const raw = (max - min) / n;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((x) => x >= raw);
  const out = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

function timeTicks(minMs, maxMs) {
  const months = (maxMs - minMs) / (30.44 * 86400000);
  const step = [1, 2, 3, 6, 12, 24].find((m) => months / m <= 7) || 24;
  const d = new Date(minMs);
  let y = d.getUTCFullYear(), m = d.getUTCMonth();
  m = Math.ceil(m / step) * step;
  const out = [];
  for (;;) {
    const t = Date.UTC(y + Math.floor(m / 12), m % 12, 1);
    if (t > maxMs) break;
    if (t >= minMs) out.push(t);
    m += step;
  }
  return out;
}

const monthFmt = new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });

/**
 * opts: {
 *   x: {type: "time"|"linear", min, max, label}, y: {min, max, label},
 *   lines: [{label, color, points: [[x, y], ...]}],
 *   points: [{x, y, err, color, hollow, tip, onClick}],  // hollow: ring instead of a filled dot
 *   ariaLabel
 * }
 */
export function drawChart(container, opts) {
  container.replaceChildren();
  const W = Math.max(container.clientWidth || 600, 280);
  const H = opts.height || Math.round(Math.min(360, Math.max(240, W * 0.5)));
  const m = { l: 58, r: 16, t: 14, b: 46 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const { x, y } = opts;
  const sx = (v) => m.l + ((v - x.min) / (x.max - x.min)) * iw;
  const sy = (v) => m.t + ih - ((v - y.min) / (y.max - y.min)) * ih;

  const svg = s("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", "aria-label": opts.ariaLabel || "" }, container);

  // grid + y ticks
  for (const t of niceTicks(y.min, y.max, 5)) {
    s("line", { class: "grid", x1: m.l, x2: m.l + iw, y1: sy(t), y2: sy(t) }, svg);
    s("text", { class: "tick", x: m.l - 8, y: sy(t), "text-anchor": "end", "dominant-baseline": "middle" }, svg).textContent = +t.toPrecision(6);
  }
  // x ticks
  const xt = x.type === "time" ? timeTicks(x.min, x.max) : niceTicks(x.min, x.max, Math.max(3, Math.round(iw / 90)));
  for (const t of xt) {
    s("line", { class: "tickmark", x1: sx(t), x2: sx(t), y1: m.t + ih, y2: m.t + ih + 5 }, svg);
    s("text", { class: "tick", x: sx(t), y: m.t + ih + 18, "text-anchor": "middle" }, svg).textContent =
      x.type === "time" ? monthFmt.format(new Date(t)) : +t.toPrecision(6);
  }
  s("line", { class: "axis", x1: m.l, x2: m.l + iw, y1: m.t + ih, y2: m.t + ih }, svg);
  s("text", { class: "axis-label", x: m.l + iw / 2, y: H - 6, "text-anchor": "middle" }, svg).textContent = x.label;
  const yl = s("text", { class: "axis-label", x: 0, y: 0, "text-anchor": "middle", transform: `translate(14 ${m.t + ih / 2}) rotate(-90)` }, svg);
  yl.textContent = y.label;

  const plot = s("g", {}, svg);
  const clipId = `clip${Math.random().toString(36).slice(2)}`;
  const defs = s("defs", {}, svg);
  s("rect", { x: m.l, y: m.t, width: iw, height: ih }, s("clipPath", { id: clipId }, defs));
  plot.setAttribute("clip-path", `url(#${clipId})`);

  for (const line of opts.lines || []) {
    if (line.points.length < 2) continue;
    s("path", {
      class: "series-line", stroke: line.color,
      d: line.points.map(([a, b], i) => `${i ? "L" : "M"}${sx(a).toFixed(1)},${sy(b).toFixed(1)}`).join(""),
    }, plot);
  }

  const tip = document.createElement("div");
  tip.className = "chart-tip";
  tip.hidden = true;
  container.append(tip);
  const showTip = (p, cx, cy) => {
    tip.textContent = p.tip;
    tip.hidden = false;
    const left = Math.min(Math.max(cx + 12, 4), W - tip.offsetWidth - 4);
    tip.style.left = `${left}px`;
    tip.style.top = `${Math.max(cy - tip.offsetHeight - 10, 4)}px`;
  };

  const marks = s("g", {}, svg);
  for (const p of opts.points || []) {
    const cx = sx(p.x), cy = sy(p.y);
    const g = s("g", { class: `pt${p.onClick ? " clickable" : ""}`, tabindex: p.onClick ? 0 : -1 }, marks);
    if (p.err != null && p.err > 0) {
      const y1 = sy(p.y - p.err), y2 = sy(p.y + p.err);
      s("path", { class: "errbar", stroke: p.color, d: `M${cx},${y1}V${y2}M${cx - 3},${y1}H${cx + 3}M${cx - 3},${y2}H${cx + 3}` }, g);
    }
    if (p.hollow) s("circle", { class: "dot hollow", cx, cy, r: 4, color: p.color }, g);
    else s("circle", { class: "dot", cx, cy, r: 4.5, fill: p.color }, g);
    s("circle", { class: "hit", cx, cy, r: 11 }, g);
    g.addEventListener("pointerenter", () => showTip(p, cx, cy));
    g.addEventListener("pointerleave", () => { tip.hidden = true; });
    g.addEventListener("focus", () => showTip(p, cx, cy));
    g.addEventListener("blur", () => { tip.hidden = true; });
    if (p.onClick) {
      g.addEventListener("click", p.onClick);
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); p.onClick(); } });
    }
  }
  return svg;
}

/** Simple table view of the same numbers (accessibility). */
export function drawTable(container, headers, rows) {
  container.replaceChildren();
  const table = document.createElement("table");
  table.className = "data-table";
  const tr = table.createTHead().insertRow();
  for (const h of headers) { const th = document.createElement("th"); th.textContent = h; tr.append(th); }
  const body = table.createTBody();
  for (const r of rows) {
    const row = body.insertRow();
    for (const c of r) row.insertCell().textContent = c;
  }
  container.append(table);
}
