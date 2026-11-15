// Marker layers drawn on the SVG overlay. Everything is in image pixel units
// (pixel [col, row] has its center at col + 0.5, row + 0.5), so markers scale
// with magnification. Lines carry data-stroke (screen px) and are thickened by app.js.
import { skyToPx, inField, moveToTime } from "./sky.js";

const NS = "http://www.w3.org/2000/svg";

// Layer groups, in the order the layer panel shows them.
export const LAYER_GROUPS = [
  { key: "target", label: "Target", note: "the object at the center" },
  { key: "field", label: "Measured vs expected", note: "SPHEREx vs Gaia" },
  { key: "catalogs", label: "Known objects", note: "type (source)" },
  { key: "quality", label: "Image quality" },
];
export const LAYERS = [
  { key: "measured", group: "target", label: "Measured position (SPHEREx)", swatch: "measured" },
  { key: "expected", group: "target", label: "Expected position (catalog)", swatch: "expected" },
  { key: "path", group: "target", label: "Path over visits", swatch: "path" },
  { key: "field_stars", group: "field", label: "Field stars", swatch: "field_stars", note: "visit stacks only" },
  { key: "gaia", group: "catalogs", label: "Stars (Gaia)", swatch: "gaia" },
  { key: "simbad", group: "catalogs", label: "Objects (SIMBAD)", swatch: "simbad" },
  { key: "vsx", group: "catalogs", label: "Variable stars (VSX)", swatch: "vsx" },
  { key: "asteroids", group: "catalogs", label: "Asteroids (JPL)", swatch: "asteroids", note: "single images only" },
  { key: "flags", group: "quality", label: "Quality flags", swatch: "flags", note: "single images only" },
];
// Only the target's own markers start on; everything else is one click away under "More layers".
export const DEFAULT_LAYERS = ["measured", "expected", "path"];
export const MAIN_LAYERS = ["measured", "expected", "path"];

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
export function drawMarkers({ group, item, manifest, overlays, layers, size, fieldStars = [], fieldScores = new Map() }) {
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
  const byName = new Map(overlays.filter((o) => o.name).map((o) => [o.name, o]));
  const starsByName = new Map(fieldStars.map((s) => [s.name, s]));
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
    // A catalog star that was also measured carries its SPHEREx result into the info panel.
    const star = starsByName.get(obj.name);
    const fieldStar = star ? { star, score: fieldScores.get(obj.name) || null,
      visit: item.kind !== "frame" ? (star.visits || []).find((x) => x.n === item.visit.n) || null : null } : null;
    add(g, { kind: "catalog", obj, px, ra: pos[0], dec: pos[1], fieldStar });
  }

  // ---- field stars (objects.json): expected and measured position per visit, so stacks only.
  // The cross is colored by the scoreboard's per-star agreement (agrees / tension / disagrees).
  if (layers.has("field_stars") && item.kind !== "frame") {
    for (const star of fieldStars) {
      const v = (star.visits || []).find((x) => x.n === item.visit.n);
      if (!v || !isPair(v.measured_px)) continue;
      const score = fieldScores.get(star.name) || null;
      const data = { kind: "field_star", star, visit: v, score, overlay: byName.get(star.name) || null };
      if (isPair(v.expected_px)) {
        const [ex, ey] = at(v.expected_px);
        const g = svg("g", { class: "marker fs-expected" }, group);
        svg("rect", { x: ex - 0.45, y: ey - 0.45, width: 0.9, height: 0.9, "data-stroke": 1.2 }, g);
        add(g, data);
      }
      const [x, y] = at(v.measured_px);
      const err = isPair(v.measured_err_px) ? v.measured_err_px : null;
      const g = svg("g", { class: `marker fs-measured fs-${score?.agreement || "none"}` }, group);
      svg("circle", { cx: x, cy: y, r: 0.8, class: "hit" }, g);
      if (err) svg("ellipse", { cx: x, cy: y, rx: err[0], ry: err[1], "data-stroke": 1 }, g);
      const a = 0.7, gap = 0.15;
      svg("path", {
        d: `M${x - a},${y}H${x - gap}M${x + gap},${y}H${x + a}M${x},${y - a}V${y - gap}M${x},${y + gap}V${y + a}`,
        "data-stroke": 1.5,
      }, g);
      add(g, data);
    }
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
