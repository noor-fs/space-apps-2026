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

/**
 * A field star's result in words, from the scoreboard (Noor): role says whether it was scored,
 * agreement is the motion test against Gaia (each star's constant offset removed first).
 */
function fieldStarResult(score) {
  if (!score) return "not scored";
  if (score.role === "blended") return "blended with a neighbor, so measured as one light center (not scored)";
  if (score.role === "not_scored" || !score.agreement) return "measured in too few visits to test (not scored)";
  const said = { agrees: "moves as Gaia predicts", tension: "slight tension with Gaia", disagrees: "doesn't move as Gaia predicts" }[score.agreement]
    || score.agreement;
  return score.role === "reference" ? `${said} (reference star: it sets the error bars, so it isn't scored)` : said;
}

/** One-line hover text for any marker. */
export function tipText(info, explanations) {
  switch (info.kind) {
    case "field_star": {
      const o = info.overlay;
      const g = typeof info.star.g_mag === "number" ? ` · G ${fmt(info.star.g_mag, 1)}` : "";
      const name = o?.label || info.star.name;
      return `${name} · ${o ? typeTitle(explanations, o.type) : "star"}${g} · SPHEREx vs Gaia: ${fieldStarResult(info.score)} (click for details)`;
    }
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

/** A link that opens an "about" entry in the dialog; app.js handles clicks on [data-about]. */
export function aboutLink(key, label, section) {
  const a = h("a", { href: "#", class: "about-link", "data-about": key }, label);
  if (section) a.dataset.section = section;
  return a;
}

function sourcesLine(sources) {
  const items = (sources || []).map((src) => {
    // "#about.<key>" points at another explanations.json entry, shown in the same dialog.
    const internal = typeof src.url === "string" && src.url.match(/^#about\.(\w+)$/);
    if (internal) return aboutLink(internal[1], src.label || internal[1]);
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

/**
 * Split a methodology text into sections. A section starts with a short heading sentence of at most
 * four words and no digits ("Images.", "Error bars."); text before the first heading has no title.
 */
function methodSections(text) {
  const sentences = text.split(/(?<=\.)\s+(?=[A-Z])/);
  const sections = [];
  for (const s of sentences) {
    const isHeading = /^[A-Z][A-Za-z' -]*\.$/.test(s) && s.split(/\s+/).length <= 4;
    if (isHeading) sections.push({ title: s.slice(0, -1), body: [] });
    else if (sections.length) sections[sections.length - 1].body.push(s);
    else sections.push({ title: null, body: [s] });
  }
  return sections;
}

const SIGMA_TIP = "Sigma (σ) is the measurement's uncertainty. A difference of more than 3σ has about "
  + "a 1 in 370 chance of being random noise, so we treat it as real.";

/** "sigma" as a hoverable term; focusable so a tap on a phone shows the note too. */
const sigmaTerm = (word = "sigma") => h("span", { class: "term", tabindex: "0", "data-tip": SIGMA_TIP }, word);

/** A sentence with its numbers in bold and every "sigma" as a hoverable term. */
function richText(text) {
  const p = h("p", {});
  const re = /\d+(?:\.\d+)?%?(?:[- ](?:sigma|pixels?))?|\bsigma\b/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    p.append(text.slice(last, m.index));
    const unitAt = m[0].search(/[- ](?:sigma|pixels?)$/);
    if (m[0] === "sigma") p.append(sigmaTerm());
    else if (unitAt > 0 && m[0].endsWith("sigma")) p.append(h("strong", {}, m[0].slice(0, unitAt + 1), sigmaTerm()));
    else p.append(h("strong", {}, m[0]));
    last = m.index + m[0].length;
  }
  p.append(text.slice(last));
  return p;
}

/** Split a verdict's text into its description and its rule (after "How this is decided:"). */
function splitVerdictText(text) {
  const m = (text || "").match(/^(.*?)\s*How this is decided:\s*(.+)$/s);
  return m ? { description: m[1].trim(), rule: m[2].trim() } : { description: (text || "").trim(), rule: null };
}

/**
 * This target's numbers against the verdict rules (manifest.verdict_evidence): one line per test,
 * each with what it needs. Values of 10 sigma and more are shown as "more than 10": the conversion
 * assumes Gaussian errors, which nobody should trust that far into the tail.
 */
function evidenceLines(verdict, ev) {
  if (!ev) return [];
  const sig = (x) => (x >= 10 ? "more than 10" : x.toFixed(1));
  // ✓ = the test is met; – = not met. Neither is a failure: the verdict follows from both kinds
  // (RW Aur's motion tests aren't met, which is why it is a brightness change, not motion).
  const line = (met, ...parts) => h("li", { class: met ? "met" : "not-met" },
    h("span", { class: "mark", "aria-hidden": "true" }, met ? "✓" : "–"), ...parts);
  const sigmaVal = (x) => h("strong", {}, `${sig(x)} `, sigmaTerm());
  const lines = [];
  if (!ev.motion_measurable) {
    lines.push(line(false, "These images couldn't detect a 1-pixel shift, so motion can't be measured."));
  } else {
    const detected = ev.motion_sigma > 3 && ev.shift_px >= 0.25;
    lines.push(line(ev.motion_sigma > 3, "Motion signal: ", sigmaVal(ev.motion_sigma), " (counts as motion above 3)."));
    lines.push(line(ev.shift_px >= 0.25, "Total shift over the data: ",
      h("strong", {}, `${ev.shift_px.toFixed(2)} pixel`), " (counts as motion from 0.25)."));
    if (detected && ev.catalog_difference_sigma != null) {
      lines.push(line(ev.catalog_difference_sigma < 3, "Difference from the catalog motion: ",
        sigmaVal(ev.catalog_difference_sigma), " (matches the catalog below 3)."));
    }
  }
  if ((verdict === "brightness_changes" || verdict === "no_motion_detected") && ev.brightness_change_sigma != null) {
    lines.push(line(ev.brightness_change_sigma > 3, "Brightness change between visits: ",
      sigmaVal(ev.brightness_change_sigma), " (counts as a change above 3)."));
  }
  if ((verdict === "saturated" || verdict === "too_faint") && ev.saturated_share != null) {
    lines.push(line(ev.saturated_share > 0.5, "Saturated in ", h("strong", {}, `${Math.round(ev.saturated_share * 100)}%`),
      " of images (counts as saturated above half)."));
  }
  return lines;
}

const pmText = (o, withErr) => {
  if (!o) return "—";
  const e = (k) => (withErr && o[`${k}_err`] != null ? ` ± ${Math.round(o[`${k}_err`])}` : "");
  return `RA ${Math.round(o.ra)}${e("ra")}, Dec ${Math.round(o.dec)}${e("dec")}`;
};

/**
 * Verdict block: chip, plain description, then "Evidence" (the rule with this target's numbers and
 * the motion values), one link to the full method, and the verdict's outside sources.
 * Used in the target panel and in the popup the verdict chip opens.
 */
export function renderVerdict(container, manifest, explanations) {
  const verdict = manifest?.verdict;
  if (!verdict) return;
  const v = explanations?.verdicts?.[verdict];
  const { description, rule } = splitVerdictText(v?.text);
  container.append(h("div", { class: "verdict-head" },
    h("span", { class: "muted" }, "Verdict "),
    h("span", { class: `chip verdict-${verdict}` }, v?.title || verdict.replace(/_/g, " "))));
  container.append(description ? h("p", {}, description) : h("p", { class: "muted" }, "No text for this verdict yet."));

  const ev = h("div", { class: "evidence" }, h("h4", {}, "Evidence"));
  if (rule) ev.append(richText(rule));
  const lines = evidenceLines(verdict, manifest.verdict_evidence);
  // Fields typed as coordinates (server keys "c_...") have no named object at the center.
  const subject = String(manifest.target_key || "").startsWith("c_") ? "This position:" : "This target:";
  if (lines.length) ev.append(h("p", { class: "evidence-sub muted small" }, subject), h("ul", { class: "evidence-list" }, ...lines));

  const mm = manifest.measured_motion_mas_yr, cm = manifest.catalog_motion_mas_yr;
  if (mm || cm) {
    const dl = h("dl", { class: "info-rows" });
    dl.append(h("dt", {}, "Measured motion"), h("dd", {}, mm ? `${pmText(mm, true)} mas/yr (SPHEREx)` : "Not measurable"));
    dl.append(h("dt", {}, "Catalog motion"), h("dd", {}, cm ? `${pmText(cm, false)} mas/yr (${cm.source || "catalog"})` : "—"));
    ev.append(dl);
  }
  ev.append(h("p", { class: "small" },
    aboutLink("methodology", "How is this measured?", verdict === "brightness_changes" ? "Brightness" : "Motion")));
  container.append(ev);

  // The "How is this measured?" link replaces the internal "How we measure" source; outside sources stay.
  const vsrc = sourcesLine((v?.sources || []).filter((x) => !/^#about\./.test(x.url || "")));
  if (vsrc) container.append(vsrc);
}

/** "How we measure" dialog: the method text split into titled sections. */
export function renderMethodology(container, explanations) {
  container.replaceChildren();
  const entry = explanations?.about?.methodology;
  container.append(h("h3", { class: "entry-title" }, entry?.title || "How we measure"));
  if (!entry?.text) {
    container.append(h("p", { class: "muted" }, "This text hasn't been written yet."));
    return;
  }
  for (const sec of methodSections(entry.text)) {
    const div = h("section", { class: "method-section" });
    if (sec.title) div.append(h("h4", {}, sec.title));
    div.append(h("p", {}, sec.body.join(" ")));
    container.append(div);
  }
  const src = sourcesLine(entry.sources);
  if (src) container.append(src);
}

/** Popup the verdict chip opens: the verdict block under the target's name. */
export function renderVerdictPopup(container, manifest, explanations) {
  container.replaceChildren();
  container.append(h("h3", { class: "entry-title" }, manifest?.name || "Verdict"));
  const box = h("div", { class: "verdict verdict-popup" });
  renderVerdict(box, manifest, explanations);
  container.append(box);
}

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
  if (!manifest?.verdict) return;
  const box = h("div", { class: "verdict" });
  renderVerdict(box, manifest, explanations);
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

/** Plain-language result of a field star's motion test, for the bright box. */
function fieldStarStory(score, nVisits) {
  const visits = `${nVisits} visit${nVisits === 1 ? "" : "s"}`;
  if (!score) {
    return { cls: "none", mark: "–", head: "Not tested",
      text: "The accuracy test covers the five challenge targets' fields; this field isn't one of them." };
  }
  if (score.role === "blended") {
    return { cls: score.agreement || "none", mark: "–", head: "Blended with a neighbor",
      text: "Another Gaia star sits within half a pixel, so SPHEREx sees the two as one light center. Not counted in the accuracy score." };
  }
  if (score.role === "not_scored" || !score.agreement) {
    return { cls: "none", mark: "–", head: "Too few visits to test",
      text: "The motion test needs this star measured in at least two visits without saturation." };
  }
  const stories = {
    agrees: { mark: "✓", head: "Moves as Gaia predicts",
      text: `Across ${visits}, SPHEREx's positions follow Gaia's prediction within the error bars.` },
    tension: { mark: "~", head: "Slight tension with Gaia",
      text: `Across ${visits}, SPHEREx's positions mostly follow Gaia, but change between visits a little more than the error bars allow.` },
    disagrees: { mark: "✗", head: "Doesn't move as Gaia predicts",
      text: `Across ${visits}, SPHEREx's position changes between visits by more than Gaia's motion and the error bars allow.` },
  };
  const s = { cls: score.agreement, ...(stories[score.agreement] || { mark: "?", head: score.agreement, text: "" }) };
  if (score.role === "reference") {
    s.text += " This is a reference star: it helps set the error bars, so it isn't counted in the accuracy score.";
  }
  return s;
}

/**
 * Offset from Gaia per visit, one row each: distance in pixels as a bar with its error.
 * Equal bars = a steady offset (allowed); bars that change = what the motion test looks at.
 */
function offsetChart(star, currentN, visitDates) {
  const rows = (star.visits || []).map((v) => {
    if (!Array.isArray(v.measured_px) || !Array.isArray(v.expected_px)) return { n: v.n, d: null };
    const dx = v.measured_px[0] - v.expected_px[0], dy = v.measured_px[1] - v.expected_px[1];
    const d = Math.hypot(dx, dy);
    const e = Array.isArray(v.measured_err_px) ? v.measured_err_px : [0, 0];
    const err = d > 0 ? Math.hypot(dx * e[0], dy * e[1]) / d : Math.hypot(e[0], e[1]);
    return { n: v.n, d, err, saturated: v.saturated };
  });
  const max = Math.max(0.3, ...rows.filter((r) => r.d != null).map((r) => r.d + r.err));
  const wrap = h("div", { class: "offset-chart" });
  for (const r of rows) {
    const date = visitDates.get(r.n);
    const row = h("div", { class: `offset-row${r.n === currentN ? " current" : ""}` },
      h("span", { class: "offset-label" }, `Visit ${r.n}`, date ? h("small", {}, ` ${date}`) : null));
    const track = h("span", { class: "offset-track" });
    if (r.d != null) {
      const pct = (x) => `${Math.max(0, Math.min(100, (x / max) * 100))}%`;
      track.append(h("span", { class: "offset-bar", style: `width:${pct(r.d)}` }));
      track.append(h("span", { class: "offset-err", style: `left:${pct(r.d - r.err)};width:${pct(2 * r.err)}` }));
    }
    row.append(track, h("span", { class: "offset-value" },
      r.d == null ? "not measured" : `${fmt(r.d)} px${r.saturated ? " (saturated)" : ""}`));
    wrap.append(row);
  }
  return wrap;
}

/** "What am I looking at?" panel for a clicked catalog object or field star. */
export function renderInfo(body, info, explanations, manifest) {
  const o = info.obj;
  const entry = typeEntry(explanations, o.type);
  const fs = info.fieldStar;
  body.replaceChildren();

  // ---- header: name, chips, brightness
  body.append(h("h4", { class: "info-title" }, o.label || o.name || "Unnamed object"));
  if (o.name && o.name !== o.label) body.append(h("div", { class: "muted info-sub" }, o.name));
  const chips = h("div", { class: "info-chips" }, h("span", { class: "chip" }, typeTitle(explanations, o.type)));
  if (fs) chips.append(h("span", { class: "chip chip-accent" }, "Field star"));
  if (typeof o.g_mag === "number") chips.append(h("span", { class: "muted small" }, `G ${fmt(o.g_mag, 1)}`));
  body.append(chips);

  // ---- SPHEREx vs Gaia: the result first, in a box colored like the marker
  if (fs) {
    const visitDates = new Map((manifest?.visits || []).map((v) => [v.n, v.date_mid]));
    const nVisits = fs.score?.n_visits ?? (fs.star.visits || []).filter((v) => Array.isArray(v.measured_px)).length;
    const story = fieldStarStory(fs.score, nVisits);
    const box = h("div", { class: `result-box result-${story.cls}` });
    box.append(h("div", { class: "result-label" }, "SPHEREx vs Gaia"));
    const head = h("div", { class: "result-head" }, h("span", { class: "result-mark", "aria-hidden": "true" }, story.mark), story.head);
    if (fs.score?.chi2 != null) head.title = `χ² = ${fmt(fs.score.chi2, 1)} for ${fs.score.dof} degrees of freedom (p = ${fs.score.p_value})`;
    box.append(head, h("p", {}, story.text));

    box.append(h("div", { class: "result-sub" }, "Distance from Gaia's prediction, per visit"));
    box.append(offsetChart(fs.star, fs.visit?.n ?? null, visitDates));
    box.append(h("p", { class: "muted small" },
      "A steady distance in every visit is normal (a nearby star or the star's color can cause it). Only changes between visits count against the star."));

    const v = fs.visit;
    if (v?.n_frames != null) {
      box.append(h("p", { class: "small" }, `This visit: measured in ${v.n_measured} of ${v.n_frames} single images.`));
    } else if (!v) {
      box.append(h("p", { class: "small muted" }, "Open a visit stack to highlight its row."));
    }
    const crowd = fs.star.crowded_by || [];
    if (crowd.length) {
      box.append(h("p", { class: "callout-warn small" },
        `⚠ Crowded: ${crowd.length} other Gaia star${crowd.length > 1 ? "s sit" : " sits"} within 2 px of this star and may pull its measured position.`));
    }
    body.append(box);
  }

  // ---- what the catalog says (the expected side)
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
    if (typeof o.ra === "number") rows.push(["Catalog position", `RA ${fmt(o.ra, 5)}°, Dec ${fmt(o.dec, 5)}° (epoch ${o.epoch ?? "?"})`]);
  }
  if (Array.isArray(info.px)) rows.push(["In this field", `column ${fmt(info.px[0], 1)}, row ${fmt(info.px[1], 1)}`]);
  const cat = h("div", { class: "catalog-box" }, h("div", { class: "result-label" }, fs ? "Expected (catalog)" : "Catalog"));
  const dl = h("dl", { class: "info-rows" });
  for (const [k, v] of rows) dl.append(h("dt", {}, k), h("dd", {}, v));
  cat.append(dl);
  const url = safeUrl(o.url);
  if (url) cat.append(h("a", { class: "info-link", href: url, target: "_blank", rel: "noopener" }, "Open catalog page ↗"));
  body.append(cat);

  // ---- what this type of object is: open when there's no measurement to lead with
  const about = h("details", { class: "type-about" });
  if (!fs) about.open = true;
  about.append(h("summary", {}, `What is a ${typeTitle(explanations, o.type).toLowerCase()}?`));
  about.append(entry?.text ? h("p", {}, entry.text) : h("p", { class: "muted" }, "No explanation for this type yet."));
  const src = sourcesLine(entry?.sources);
  if (src) about.append(src);
  body.append(about);
}
