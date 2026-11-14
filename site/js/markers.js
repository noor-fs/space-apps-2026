// Marker layers drawn on the SVG overlay. Everything is in image pixel units
// (pixel [col, row] has its center at col + 0.5, row + 0.5), so markers scale
// with magnification. Lines carry data-stroke (screen px) and are thickened by app.js.
import { skyToPx, inField, moveToTime } from "./sky.js";

const NS = "http://www.w3.org/2000/svg";

export const LAYERS = [
  { key: "measured", label: "Measured (SPHEREx)", swatch: "measured" },
  { key: "expected", label: "Expected (catalog)", swatch: "expected" },
  { key: "path", label: "Measured path", swatch: "path" },
  { key: "gaia", label: "Gaia", swatch: "gaia" },
  { key: "simbad", label: "SIMBAD", swatch: "simbad" },
  { key: "vsx", label: "Variable stars (VSX)", swatch: "vsx" },
  { key: "asteroids", label: "Asteroids", swatch: "asteroids", note: "single images only" },
  { key: "flags", label: "Quality flags", swatch: "flags", note: "single images only" },
];
export const DEFAULT_LAYERS = ["measured", "expected", "path", "gaia", "simbad", "vsx", "asteroids"];

function svg(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.append(e);
  return e;
}

/** The time a stack or single image stands for: date_mid for visits, time for images. */
export function itemTimeMs(item) {
  return item.kind === "frame" ? Date.parse(item.frame.time) : Date.parse(`${item.visit.date_mid}T00:00:00Z`);
}

const isPair = (p) => Array.isArray(p) && p.length === 2 && p.every((x) => typeof x === "number");

/**
 * Draw all enabled layers for `item` into `group`.
 * Returns a Map of marker id -> {kind, ...} used for hover text and clicks.
 */
export function drawMarkers({ group, item, manifest, overlays, layers, size }) {
  group.replaceChildren();
  const info = new Map();
  const add = (g, data) => {
    const id = String(info.size);
    g.dataset.id = id;
    info.set(id, data);
  };
  const at = (px) => [px[0] + 0.5, px[1] + 0.5];
  const src = item.kind === "frame" ? item.frame : item.visit;

  // ---- path: measured positions of every visit, in time order
  if (layers.has("path")) {
    const pts = [...manifest.visits].sort((a, b) => a.n - b.n).filter((v) => isPair(v.target_measured_px));
    if (pts.length >= 2) {
      svg("polyline", {
        class: "path-line", "data-stroke": 1.5,
        points: pts.map((v) => at(v.target_measured_px).join(",")).join(" "),
      }, group);
    }
    for (const v of pts) {
      const current = v.n === item.visit.n;
      const [x, y] = at(v.target_measured_px);
      const g = svg("g", { class: `marker path-pt${current ? " current" : ""}` }, group);
      svg("circle", { cx: x, cy: y, r: current ? 0.28 : 0.2, "data-stroke": 1 }, g);
      add(g, { kind: "path", visit: v, current });
    }
  }

  // ---- catalog layers (gaia, simbad, vsx, asteroids)
  const t = itemTimeMs(item);
  const { center_ra: ra0, center_dec: dec0 } = manifest.grid;
  for (const obj of overlays) {
    if (!layers.has(obj.layer)) continue;
    let pos;
    if (Array.isArray(obj.positions)) {
      // Asteroids: one position per single image, matched on exact time; never on stacks.
      if (item.kind !== "frame") continue;
      const p = obj.positions.find((q) => Date.parse(q.time) === t);
      if (!p) continue;
      pos = [p.ra, p.dec];
    } else {
      if (typeof obj.ra !== "number" || typeof obj.dec !== "number") continue;
      pos = moveToTime(obj, t);
    }
    const px = skyToPx(pos[0], pos[1], ra0, dec0, size);
    if (!inField(px, size)) continue;
    const [x, y] = at(px);
    const g = svg("g", { class: `marker cat cat-${obj.layer}` }, group);
    if (obj.layer === "simbad") {
      const r = 2.4;
      svg("path", { d: `M${x},${y - r}L${x + r},${y}L${x},${y + r}L${x - r},${y}Z`, "data-stroke": 1.5 }, g);
    } else if (obj.layer === "vsx") {
      svg("circle", { cx: x, cy: y, r: 2.7, "data-stroke": 1.5, class: "dashed" }, g);
    } else if (obj.layer === "asteroids") {
      svg("circle", { cx: x, cy: y, r: 2.2, "data-stroke": 1.5 }, g);
      svg("path", { d: `M${x - 0.8},${y - 0.8}L${x + 0.8},${y + 0.8}M${x + 0.8},${y - 0.8}L${x - 0.8},${y + 0.8}`, "data-stroke": 1.5 }, g);
    } else {
      svg("circle", { cx: x, cy: y, r: 2, "data-stroke": 1.5 }, g);
    }
    add(g, { kind: "catalog", obj, px, ra: pos[0], dec: pos[1] });
  }

  // ---- expected: catalog prediction for this date (outline of a pixel-sized square)
  if (layers.has("expected") && isPair(src.target_expected_px)) {
    const [x, y] = at(src.target_expected_px);
    const g = svg("g", { class: "marker expected" }, group);
    svg("rect", { x: x - 0.7, y: y - 0.7, width: 1.4, height: 1.4, "data-stroke": 2 }, g);
    add(g, { kind: "expected", px: src.target_expected_px });
  }

  // ---- measured: cross plus a circle whose radius is the error
  if (layers.has("measured") && isPair(src.target_measured_px)) {
    const [x, y] = at(src.target_measured_px);
    const err = isPair(src.target_measured_err_px) ? src.target_measured_err_px : null;
    const g = svg("g", { class: "marker measured" }, group);
    svg("circle", { cx: x, cy: y, r: 1.3, class: "hit" }, g);
    if (err) svg("ellipse", { cx: x, cy: y, rx: err[0], ry: err[1], "data-stroke": 1.5 }, g);
    const a = 1.1, gap = 0.25;
    svg("path", {
      d: `M${x - a},${y}H${x - gap}M${x + gap},${y}H${x + a}M${x},${y - a}V${y - gap}M${x},${y + gap}V${y + a}`,
      "data-stroke": 2,
    }, g);
    add(g, { kind: "measured", px: src.target_measured_px, err, src, isFrame: item.kind === "frame" });
  }

  return info;
}
