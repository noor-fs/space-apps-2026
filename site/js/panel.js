// "What am I looking at?" panel and marker hover text.
// Text comes from data files written by others, so it is only ever set with textContent.

const h = (tag, props = {}, ...children) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") e.className = v;
    else e.setAttribute(k, v);
  }
  for (const c of children) if (c != null && c !== false) e.append(c);
  return e;
};

/** Only http(s) links are shown; anything else (e.g. javascript:) is dropped. */
export function safeUrl(u) {
  try {
    const x = new URL(u, location.href);
    return x.protocol === "http:" || x.protocol === "https:" ? x.href : null;
  } catch {
    return null;
  }
}

const fmt = (x, d = 2) => Number(x).toFixed(d);
const typeEntry = (explanations, type) => explanations?.types?.[type] || null;
const typeTitle = (explanations, type) => typeEntry(explanations, type)?.title || (type || "unknown").replace(/_/g, " ");

/** One-line hover text for any marker. */
export function tipText(info, explanations) {
  switch (info.kind) {
    case "catalog": {
      const o = info.obj;
      const g = typeof o.g_mag === "number" ? ` · G ${fmt(o.g_mag, 1)}` : "";
      return `${o.label || o.name} · ${typeTitle(explanations, o.type)}${g} (click for details)`;
    }
    case "measured": {
      const [c, r] = info.px;
      const e = info.err ? [` ± ${fmt(info.err[0])}`, ` ± ${fmt(info.err[1])}`] : ["", ""];
      let t = `Measured position (SPHEREx): column ${fmt(c)}${e[0]}, row ${fmt(r)}${e[1]}`;
      if (info.isFrame) {
        const f = info.src.target_flux_mjy;
        t += f == null ? " · flux not measured"
          : ` · flux ${fmt(f, 3)}${info.src.target_flux_err_mjy != null ? ` ± ${fmt(info.src.target_flux_err_mjy, 3)}` : ""} mJy`;
      }
      return t;
    }
    case "expected":
      return `Expected position (catalog prediction): column ${fmt(info.px[0])}, row ${fmt(info.px[1])}`;
    case "path":
      return `Measured path · visit ${info.visit.n} (${info.visit.date_mid})${info.current ? " · current visit" : ""}`;
    default:
      return "";
  }
}

function sourcesLine(sources) {
  const items = (sources || []).map((src) => {
    const url = safeUrl(src.url);
    return url ? h("a", { href: url, target: "_blank", rel: "noopener" }, src.label || url) : h("span", {}, src.label || "");
  });
  if (!items.length) return null;
  const p = h("p", { class: "info-sources muted" }, "Sources: ");
  items.forEach((s, i) => { if (i) p.append(", "); p.append(s); });
  return p;
}

/** An {title, text, sources} entry from explanations.json. */
export function renderEntry(container, entry, fallbackTitle) {
  container.replaceChildren();
  container.append(h("h3", { class: "entry-title" }, entry?.title || fallbackTitle));
  container.append(entry?.text ? h("p", {}, entry.text) : h("p", { class: "muted" }, "This text hasn't been written yet."));
  const src = sourcesLine(entry?.sources);
  if (src) container.append(src);
}

/** Explanation panel: target entry, verdict with text, measured vs catalog motion. */
/**
 * Target description + verdict, for the "About <target>" box above the mode tabs.
 * The box's summary line already shows the target's name, so no heading here.
 */
export function renderTargetPanel(container, { key, manifest, explanations }) {
  container.replaceChildren();
  const target = explanations?.targets?.[key];
  container.append(target?.text ? h("p", {}, target.text) : h("p", { class: "muted" }, "No description of this target yet."));
  const src = sourcesLine(target?.sources);
  if (src) container.append(src);

  const verdict = manifest?.verdict;
  if (!verdict) return;
  const v = explanations?.verdicts?.[verdict];
  const box = h("div", { class: "verdict" });
  box.append(h("div", { class: "verdict-head" },
    h("span", { class: "muted" }, "Verdict "),
    h("span", { class: `chip verdict-${verdict}` }, v?.title || verdict.replace(/_/g, " "))));
  box.append(v?.text ? h("p", {}, v.text) : h("p", { class: "muted" }, "No text for this verdict yet."));
  const vsrc = sourcesLine(v?.sources);
  if (vsrc) box.append(vsrc);

  // Saturated / too faint: show the verdict text instead of empty measurement numbers.
  const noMeasure = verdict === "saturated" || verdict === "too_faint";
  const mm = manifest.measured_motion_mas_yr, cm = manifest.catalog_motion_mas_yr;
  if (!noMeasure && (mm || cm)) {
    const pm = (o, withErr) => {
      if (!o) return "—";
      const e = (k) => (withErr && o[`${k}_err`] != null ? ` ± ${Math.round(o[`${k}_err`])}` : "");
      return `RA ${Math.round(o.ra)}${e("ra")}, Dec ${Math.round(o.dec)}${e("dec")}`;
    };
    const dl = h("dl", { class: "info-rows" });
    dl.append(h("dt", {}, "Measured motion"), h("dd", {}, mm ? `${pm(mm, true)} mas/yr (SPHEREx)` : "Not measured"));
    dl.append(h("dt", {}, "Catalog motion"), h("dd", {}, cm ? `${pm(cm, false)} mas/yr (${cm.source || "catalog"})` : "—"));
    box.append(dl);
  }
  container.append(box);
}

/** Credits panel from credits.json: [{what, text, url}]. */
export function renderCredits(container, credits) {
  container.replaceChildren();
  container.append(h("h3", { class: "entry-title" }, "Credits"));
  if (!Array.isArray(credits) || !credits.length) {
    container.append(h("p", { class: "muted" }, "Credits haven't been added yet."));
    return;
  }
  const list = h("ul", { class: "credits" });
  for (const c of credits) {
    const url = safeUrl(c.url);
    list.append(h("li", {},
      h("strong", {}, c.what || ""),
      h("p", {}, c.text || ""),
      url ? h("a", { href: url, target: "_blank", rel: "noopener" }, url) : null));
  }
  container.append(list);
}

/** Fill the panel body for a clicked catalog marker. */
export function renderInfo(body, info, explanations) {
  const o = info.obj;
  const entry = typeEntry(explanations, o.type);
  body.replaceChildren();

  body.append(h("h4", { class: "info-title" }, o.label || o.name || "Unnamed object"));
  if (o.name && o.name !== o.label) body.append(h("div", { class: "muted info-sub" }, o.name));

  body.append(h("div", { class: "chip" }, typeTitle(explanations, o.type)));
  body.append(entry?.text
    ? h("p", {}, entry.text)
    : h("p", { class: "muted" }, "No explanation for this type yet."));

  const sources = (entry?.sources || []).map((s) => {
    const url = safeUrl(s.url);
    return url ? h("a", { href: url, target: "_blank", rel: "noopener" }, s.label || url) : h("span", {}, s.label || "");
  });
  if (sources.length) {
    const p = h("p", { class: "info-sources muted" }, "Sources: ");
    sources.forEach((s, i) => { if (i) p.append(", "); p.append(s); });
    body.append(p);
  }

  const rows = [];
  rows.push(["Catalog", o.source || "—"]);
  if (typeof o.g_mag === "number") rows.push(["Brightness", `G = ${fmt(o.g_mag, 2)} mag`]);
  if (Array.isArray(o.positions)) {
    rows.push(["Position", `RA ${fmt(info.ra, 5)}°, Dec ${fmt(info.dec, 5)}° at this image's time`]);
    rows.push(["Seen on", `${o.positions.length} single images`]);
  } else {
    rows.push(["Proper motion", o.pmra_mas_yr == null || o.pmdec_mas_yr == null
      ? "Unknown, so the marker stays fixed"
      : `${fmt(o.pmra_mas_yr, 1)} (RA), ${fmt(o.pmdec_mas_yr, 1)} (Dec) mas/yr`]);
    rows.push(["Catalog position", `RA ${fmt(o.ra, 5)}°, Dec ${fmt(o.dec, 5)}° (epoch ${o.epoch ?? "?"})`]);
  }
  rows.push(["In this field", `column ${fmt(info.px[0], 1)}, row ${fmt(info.px[1], 1)}`]);
  const dl = h("dl", { class: "info-rows" });
  for (const [k, v] of rows) dl.append(h("dt", {}, k), h("dd", {}, v));
  body.append(dl);

  const url = safeUrl(o.url);
  if (url) body.append(h("a", { class: "info-link", href: url, target: "_blank", rel: "noopener" }, `Open catalog page ↗`));
}
