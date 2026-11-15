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
    h("span", { class: "verdict-kind kind-target" }, "Target"),
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
  renderSectioned(container, explanations?.about?.methodology, "How we measure", "doc-method");
}

/** "Limits" dialog: the same titled cards, with warm titles (these are caveats). */
export function renderLimits(container, explanations) {
  renderSectioned(container, explanations?.about?.limits, "What this tool can't tell you", "doc-limits");
}

/** A text split into titled sections (methodSections), each shown as a card. */
function renderSectioned(container, entry, fallbackTitle, tone) {
  container.replaceChildren();
  container.append(h("h3", { class: "entry-title" }, entry?.title || fallbackTitle));
  if (!entry?.text) {
    container.append(h("p", { class: "muted" }, "This text hasn't been written yet."));
    return;
  }
  const wrap = h("div", { class: `doc-cards ${tone}` });
  for (const sec of methodSections(entry.text)) {
    if (!sec.title) { wrap.append(h("p", { class: "doc-lead" }, sec.body.join(" "))); continue; }
    wrap.append(h("section", { class: "doc-card method-section" }, h("h4", {}, sec.title), h("p", {}, sec.body.join(" "))));
  }
  container.append(wrap);
  const src = sourcesLine(entry.sources);
  if (src) container.append(src);
}

/**
 * Welcome popup (shown on a first visit, and from "How it works"): what the tool is for, what it
 * does, and the accuracy numbers from the scoreboard, computed here so they never go stale.
 */
export function renderWelcome(container, explanations, board) {
  container.replaceChildren();
  const entry = explanations?.about?.how_it_works;
  container.append(h("p", { class: "welcome-kicker" }, "SPHEREx Motion Viewer"));
  container.append(h("h3", { class: "entry-title welcome-title" }, entry?.title || "How this works"));
  if (entry?.text) container.append(h("p", { class: "welcome-lead" }, entry.text));

  const stats = welcomeStats(board);
  if (stats.length) {
    container.append(h("div", { class: "welcome-stats" }, ...stats.map((s) =>
      h("div", { class: "welcome-stat" }, h("strong", {}, s.value), h("span", {}, s.label)))));
  }
  if (entry?.cards?.length) {
    container.append(h("div", { class: "welcome-cards" }, ...entry.cards.map((c, i) =>
      h("div", { class: "welcome-card" }, h("span", { class: "welcome-step" }, String(i + 1)),
        h("h4", {}, c.title), h("p", {}, c.text)))));
  }
  container.append(h("div", { class: "welcome-actions" },
    h("button", { type: "button", class: "primary", "data-close-dialog": "" }, "Start exploring"),
    h("a", { href: "#", class: "about-link", "data-about": "accuracy" }, "How accurate is it?"),
    h("a", { href: "#", class: "about-link", "data-about": "methodology" }, "How we measure")));
  const src = sourcesLine(entry?.sources);
  if (src) container.append(src);
}

/** The headline numbers for the welcome popup, from scoreboard.json. */
function welcomeStats(board) {
  const targets = board?.targets || [];
  const out = [];
  const measurable = targets.filter((t) => t.motion && t.motion.agreement !== "not_measurable");
  if (measurable.length) {
    const agree = measurable.filter((t) => t.motion.agreement === "agrees").length;
    out.push({ value: `${agree} of ${measurable.length}`, label: "measurable targets move as the catalogs predict" });
  }
  let agree = 0, n = 0;
  for (const t of targets) {
    if (!t.field_stars?.in_pooled_totals) continue;
    const c = t.field_stars.motion_test?.agreement_counts || {};
    agree += c.agrees || 0;
    n += (c.agrees || 0) + (c.tension || 0) + (c.disagrees || 0);
  }
  if (n) out.push({ value: `${agree} of ${n}`, label: "Gaia stars the tool was never tuned on move as Gaia predicts" });
  const p = board?.summary?.field_stars_motion;
  if (p?.n) out.push({ value: pctText(p.within_2sigma), label: "of their measurements fall within 2 error bars (honest: 95%)" });
  return out;
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
 * Details box under the title: three cards, About (description), Target and Field (the verdicts).
 * Card colors match the image markers: yellow = the target, green = field stars.
 */
export function renderTargetPanel(container, { key, manifest, explanations, fieldEntry }) {
  container.replaceChildren();
  const target = explanations?.targets?.[key];
  const about = h("section", { class: "detail-card card-about" },
    h("div", { class: "verdict-head" }, h("span", { class: "verdict-kind" }, "About")),
    target?.text ? h("p", {}, target.text) : h("p", { class: "muted" }, "No description of this target yet."));
  const src = sourcesLine(target?.sources);
  if (src) about.append(src);
  container.append(about);
  if (manifest?.verdict) {
    const box = h("section", { class: "detail-card card-target" });
    renderVerdict(box, manifest, explanations);
    container.append(box);
  }
  if (manifest) {
    const box = h("section", { class: "detail-card card-field" });
    renderFieldVerdict(box, fieldEntry);
    container.append(box);
  }
}

/** Credits panel from credits.json: [{what, text, url}]. */
export function renderCredits(container, credits) {
  container.replaceChildren();
  container.append(h("h3", { class: "entry-title" }, "Credits"));
  if (!Array.isArray(credits) || !credits.length) {
    container.append(h("p", { class: "muted" }, "Credits haven't been added yet."));
    return;
  }
  const list = h("ul", { class: "credits doc-cards" });
  for (const c of credits) {
    const url = safeUrl(c.url);
    list.append(h("li", { class: "doc-card" },
      h("h4", {}, c.what || ""),
      h("p", {}, c.text || ""),
      url ? h("a", { href: url, target: "_blank", rel: "noopener", class: "small" }, url) : null));
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

// ---------------------------------------------------------------- field check (Noor's scoring)

/**
 * The field's verdict from its scoring entry (a scoreboard.json targets[] entry, or a live field's
 * score.json target). Counts only "scored" stars: reference stars set the error bars, so they agree
 * by construction. Tension (2-3 sigma) is expected by chance in a few stars and doesn't count against
 * the field; it is shown in the details.
 */
export function fieldVerdict(entry) {
  const fs = entry?.field_stars;
  if (!entry) return { state: "none", title: "Not scored yet", sentence: "This field hasn't been scored yet." };
  if (!fs) return { state: "none", title: "Not scored yet", sentence: "This field has no field-star measurements to check." };
  const c = fs.motion_test?.agreement_counts || {};
  const agree = c.agrees || 0, tension = c.tension || 0, off = c.disagrees || 0;
  const n = agree + tension + off;
  const base = { agree, tension, off, n };
  if (fs.in_pooled_totals === false) {
    return { ...base, state: "glow", title: "Too bright to check",
      sentence: "The target is so bright that its glow covers the field, so these stars aren't a fair test. They are shown, but left out of the overall totals." };
  }
  if (n === 0) return { ...base, state: "none", title: "No stars to check", sentence: "No Gaia star in this field could be tested." };
  if (n < 3) {
    return { ...base, state: "few", title: "Too few stars to judge",
      sentence: `Only ${n} star${n === 1 ? "" : "s"} could be tested, too few to judge the field.` };
  }
  if (off === 0) return { ...base, state: "accurate", title: "Stars accurate", sentence: "Every star we could test moves the way Gaia predicts." };
  const sentence = `${off} of ${n} stars ${off === 1 ? "doesn't" : "don't"} move the way Gaia predicts; the other ${n - off} ${n - off === 1 ? "does" : "do"}.`;
  return off / n <= 0.2 ? { ...base, state: "mostly", title: "Stars mostly accurate", sentence }
    : { ...base, state: "off", title: "Some stars off", sentence };
}

const pctText = (x) => `${Math.round(100 * x)}%`;

/** A list that opens on click, with a count badge and an explicit "Show list" / "Hide" cue. */
function offList(label, count, items, note) {
  return h("details", { class: "off-list" },
    h("summary", {},
      h("span", { class: "off-count" }, String(count)),
      h("span", { class: "off-label" }, label, note ? h("span", { class: "muted" }, ` ${note}`) : null),
      h("span", { class: "off-cue", "aria-hidden": "true" })),
    h("ul", {}, ...items));
}

/** Plain text with its numbers ("34 of 41", "81%", "0.61 arcsec") in bold. */
function boldNumbers(text) {
  const p = h("p", {});
  const parts = String(text).split(/(\d+ of \d+|\d+(?:\.\d+)?%|\d+(?:\.\d+)? arcsec|\d+(?:\.\d+)? of a pixel)/);
  parts.forEach((part, i) => p.append(i % 2 ? h("strong", {}, part) : part));
  return p;
}

/** Shares of measurements within 1 and 2 error bars, each against the honest value (68%, 95%). */
function honestyBars(pulls, label) {
  if (!pulls?.n) return null;
  const wrap = h("div", { class: "honesty" });
  if (label) wrap.append(h("p", { class: "honesty-label small muted" }, label));
  for (const [k, honest, text] of [["within_1sigma", 0.68, "within 1 error bar"], ["within_2sigma", 0.95, "within 2 error bars"]]) {
    const v = pulls[k];
    const bar = h("span", { class: "honesty-bar", "aria-hidden": "true" },
      h("i", { class: "honesty-fill", style: `width:${Math.round(100 * v)}%` }),
      h("i", { class: "honesty-tick", style: `left:${Math.round(100 * honest)}%` }));
    wrap.append(h("div", { class: "honesty-row small" },
      h("span", { class: "honesty-name" }, text), bar,
      h("span", {}, h("strong", {}, pctText(v)), h("span", { class: "muted" }, ` (honest: ${pctText(honest)})`))));
  }
  return wrap;
}

/** Stacked bar: stars that match / are in slight tension / don't match. */
function agreementBar(fv) {
  if (!fv.n) return null;
  const seg = (count, cls) => (count ? h("i", { class: `agree-seg ${cls}`, style: `flex:${count}` }) : null);
  const legend = h("p", { class: "agree-legend small" },
    h("span", { class: "dot agree-yes" }), ` ${fv.agree} match`,
    fv.tension ? h("span", {}, " · ", h("span", { class: "dot agree-mid" }), ` ${fv.tension} slight tension`) : null,
    " · ", h("span", { class: "dot agree-no" }), ` ${fv.off} don't match`);
  return h("div", { class: "agree" },
    h("div", { class: "agree-bar", role: "img", "aria-label": `${fv.agree} match, ${fv.tension} in tension, ${fv.off} don't match` },
      seg(fv.agree, "agree-yes"), seg(fv.tension, "agree-mid"), seg(fv.off, "agree-no")),
    legend);
}

/** Field-check block: chip, description, then the evidence. Used in the About box and the field popup. */
export function renderFieldVerdict(container, entry) {
  const fv = fieldVerdict(entry);
  const fs = entry?.field_stars;
  container.append(h("div", { class: "verdict-head" },
    h("span", { class: "verdict-kind kind-field" }, "Field"),
    h("span", { class: `chip field-${fv.state}` }, fv.title)));
  container.append(h("p", {}, "Every Gaia star in the field (down to magnitude G = 17) is measured the same way as the target, and we check that it moves the way Gaia predicts. The tool was never tuned on these stars, so they are an independent test. ", fv.sentence));

  const ev = h("div", { class: "evidence" }, h("h4", {}, "Evidence"));
  if (fs) {
    const bar = agreementBar(fv);
    if (bar) ev.append(h("p", { class: "evidence-sub muted small" }, "Stars tested:"), bar);
    const c = fs.counts || {};
    const others = [
      c.reference ? `${c.reference} set the error bars` : null,
      c.blended ? `${c.blended} merged with a neighbor` : null,
      c.too_few_visits ? `${c.too_few_visits} seen in too few visits` : null,
    ].filter(Boolean);
    if (others.length) ev.append(h("p", { class: "small muted" }, `Not counted: ${others.join(", ")}.`));
    const pulls = fs.motion_test?.pulls;
    if (pulls?.n) {
      ev.append(h("p", { class: "evidence-sub muted small" }, "Are the error bars honest? Share of these stars' measurements within their error bars:"));
      ev.append(honestyBars(pulls));
      if (fs.error_bars) ev.append(h("p", { class: "small" }, `Error bars: ${fs.error_bars}.`));
    }
    if (c.scored && c.crowded) {
      ev.append(h("p", { class: "small" }, `${c.crowded} of ${c.scored} stars have another Gaia star within 2 pixels, which shifts their light center slightly.`));
    }
    const offNames = fs.motion_test?.disagreeing || [];
    if (offNames.length) {
      const g = new Map((fs.objects || []).map((o) => [o.name, o.g_mag]));
      ev.append(offList(`star${offNames.length === 1 ? "" : "s"} that don't match Gaia`, offNames.length,
        offNames.map((name) => h("li", {}, name,
          g.get(name) != null ? h("span", { class: "muted" }, ` · G ${Number(g.get(name)).toFixed(1)}`) : null))));
    }
  }
  ev.append(h("p", { class: "small" }, aboutLink("accuracy", "How these checks work", "How these checks work"),
    " · ", aboutLink("accuracy", "Compare with the suggested targets")));
  container.append(ev);
}

/** Popup the field chip opens: the field-check block under the target's name. */
export function renderFieldPopup(container, entry, manifest) {
  container.replaceChildren();
  container.append(h("h3", { class: "entry-title" }, manifest?.name || "Field check"));
  const box = h("div", { class: "verdict verdict-popup" });
  renderFieldVerdict(box, entry);
  container.append(box);
}

/**
 * "How accurate is this?" dialog: Noor's whole scoreboard. Headline sentences, one row per
 * suggested target (both verdicts and the motion check), pooled error-bar honesty, the stars that
 * don't match, and how the checks work.
 */
export function renderAccuracy(container, board, { explanations, liveName } = {}) {
  container.replaceChildren();
  container.append(h("h3", { class: "entry-title" }, "How accurate is this?"));
  if (!board) {
    container.append(h("p", { class: "muted" }, "The scoreboard couldn't be loaded."));
    return;
  }
  container.append(h("p", {}, "We test the tool on things whose answer is already known: the suggested targets, whose motion is in the catalogs, and every Gaia star around them, measured exactly the same way."));
  if (liveName) {
    container.append(h("p", { class: "small muted" }, `${liveName} is checked the same way: its own result is under the Field chip next to its name.`));
  }
  // Headline sentences as cards: the "Label:" that starts a sentence becomes its colored title.
  if (board.headline?.length) {
    const kinds = { targets: "kind-target", "other stars": "kind-field", positions: "kind-pos" };
    const cards = board.headline.map((s) => {
      const m = String(s).match(/^([A-Z][A-Za-z ]{2,20}):\s+(.*)$/);
      const label = m ? m[1] : "Target positions";
      return h("div", { class: `headline-card ${kinds[label.toLowerCase()] || "kind-pos"}` },
        h("span", { class: "verdict-kind" }, label), boldNumbers(m ? m[2].charAt(0).toUpperCase() + m[2].slice(1) : s));
    });
    container.append(h("div", { class: "headline-cards" }, ...cards));
  }

  const table = h("table", { class: "score-table small" },
    h("thead", {}, h("tr", {}, h("th", {}, "Target"), h("th", {}, "Target verdict"), h("th", {}, "Motion vs catalog"), h("th", {}, "Field"))));
  const body = h("tbody");
  for (const t of board.targets || []) {
    const vTitle = explanations?.verdicts?.[t.verdict]?.title || String(t.verdict || "").replace(/_/g, " ");
    const m = t.motion || {};
    const motion = m.agreement === "not_measurable" ? h("span", { class: "muted" }, `not measurable (${m.reason})`)
      : h("span", {}, m.speed_difference_percent != null ? `${m.speed_difference_percent > 0 ? "+" : ""}${m.speed_difference_percent}% speed · ` : "",
        h("span", { class: `agree-word agree-${m.agreement}` }, m.agreement));
    const fv = fieldVerdict(t);
    body.append(h("tr", {},
      h("td", {}, h("a", { href: `?target=${encodeURIComponent(t.target_key)}`, "data-open-target": t.target_key }, t.name)),
      h("td", {}, h("span", { class: `chip verdict-${t.verdict}` }, vTitle)),
      h("td", {}, motion),
      h("td", {}, h("span", { class: `chip field-${fv.state}` }, fv.title),
        fv.n ? h("span", { class: "muted" }, ` ${fv.agree + fv.tension} of ${fv.n}`) : null)));
  }
  table.append(body);
  container.append(h("div", { class: "table-wrap" }, table));

  const s = board.summary || {};
  if (s.field_stars_motion) {
    const sec = h("section", { class: "acc-card" }, h("h4", {}, "Are the error bars honest?"),
      h("p", { class: "small" }, "With honest error bars, 68% of measurements land within 1 error bar of the truth and 95% within 2 (the white ticks). Field stars, all fields together:"));
    sec.append(honestyBars(s.field_stars_motion, "All tested stars"));
    if (s.field_stars_motion_uncrowded) sec.append(honestyBars(s.field_stars_motion_uncrowded, "Stars with no close neighbor"));
    if (s.field_star_error_bars) sec.append(h("p", { class: "small acc-verdict" }, `Our error bars are ${s.field_star_error_bars}.`));
    container.append(sec);
  }

  const offRows = (board.targets || []).filter((t) => t.field_stars?.motion_test?.disagreeing?.length);
  if (offRows.length) {
    const sec = h("section", { class: "acc-card" }, h("h4", {}, "Stars that don't match Gaia"),
      h("p", { class: "small" }, "Known stars not doing what Gaia predicts are the interesting cases: either something real, or a limit of the tool. We list them rather than hide them."));
    for (const t of offRows) {
      const names = t.field_stars.motion_test.disagreeing;
      const note = t.field_stars.in_pooled_totals === false ? "(left out of the totals: the target's glow covers this field)" : null;
      sec.append(offList(`in ${t.name}`, names.length, names.map((n) => h("li", {}, n)), note));
    }
    container.append(sec);
  }

  const method = board.method || {};
  const sec = h("section", { class: "acc-card method-card" }, h("h4", {}, "How these checks work"));
  for (const [k, title] of [["motion", "Target motion"], ["error_bars", "Error bars"], ["field_stars", "Field stars"], ["not_scored", "Not scored"]]) {
    if (method[k]) sec.append(h("div", { class: "method-item" }, h("span", { class: "method-name" }, title), h("p", {}, method[k])));
  }
  container.append(sec);
}
