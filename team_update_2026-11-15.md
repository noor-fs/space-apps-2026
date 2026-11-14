---
title: Team update, final day plan (2026-11-15)
date: 2026-11-15
updated: 2026-11-15
tags:
  - current
  - nasa
  - team
---

# Team update: final day plan (Yara T, 2026-11-15)

Today is about making what we have solid, not adding much. Everything below either fixes something that is wrong now, connects pieces that already exist, or finishes a feature that is one step away.

> [!important] Rule for today
> Finish your top item before starting the next. If something you need is missing or broken, post it in the chat; don't change a shared file format to work around it.

## What changed overnight

- **Frame times are now whole seconds** (`2025-04-24T20:32:55Z`, was `…20:32:54.640Z`), matching the example in [[saturday_plan]]. This unblocks the asteroid layer. Nothing else in the files changed: the images are byte-identical.
- **New file: `objects.json`** for every target, with the expected and measured position of every measurable Gaia star in the field, not only the target. Format below. This is what the scoreboard and the "expected vs observed for every object" markers are built on.

## Who does what

| Who | Top priority | Then |
|---|---|---|
| **Yara K** | Deploy the site on the real `data/` files and post the link | "How we measure" button; field-star markers; scoreboard panel; check the fingerprint on real data |
| **Amna** | Asteroid layer on the real times | Text fixes and new credits (below); add the "How we measure" text |
| **Noor** | Scoreboard on the real files (what is scored is defined below) | Per-object agreement for the site's field-star markers |
| **Yara T** | Push last night's files; `objects.json` for every target (done overnight) | Server for live lookup of any sky position |
| **Not assigned** | Demo video and write-up | Decide who in the morning. Start by early afternoon, not at the end |

### Who can start now, and who waits for what

Everything marked "after the push" needs Yara T's push first thing: it brings the new frame times and `objects.json` into the repo.

| Task | Can start | Waits for |
|---|---|---|
| Yara K: deploy | After the push | The push |
| Yara K: "How we measure" popup and verdict links | Now (the text is below) | Amna's `about.methodology` entry, only for the final text |
| Yara K: field-star layer | After the push | The push |
| Yara K: accuracy panel | Now, against the format of Noor's first scoreboard version (`headline`, `targets[]`) | Noor's real `scoreboard.json` |
| Yara K: live lookup hook | Later | Yara T's server address and response |
| Amna: asteroid layer | After the push | The push (new frame times) |
| Amna: text fixes, credits, methodology text, RW Aur check | Now | Nothing |
| Noor: checks 1 and 2 (target motion, target error bars) | Now (manifests are already in the repo) | Nothing |
| Noor: check 3 (field stars) and per-object agreement | After the push | The push (`objects.json`) |
| Yara T: server | Now | Nothing |
| Demo and write-up | The story now; recording after deploy | The deploy link |

---

## Yara K: the site

1. **Deploy** and post the link. Then open all five targets and check every mode. Note anything that breaks and tell the file's owner.
2. **"How we measure", where people need it.** It shows `about.methodology` from `explanations.json`, a new key in the format (agreed here); Amna adds the text. Three ways in:
   - **Clicking the verdict chip** opens it as a popup, with the rule for that verdict shown first. People who see "Moves as expected" want to know *why*, right there.
   - A small **"how is this measured?" link** beside the measured vs catalog motion numbers, and beside the brightness chart, opening the same popup.
   - The general **"How we measure" button** in the top bar, next to "How it works" and "Limits".
3. **Field-star layer** (`field_stars`) from `objects.json` (format below):
   - On **visit stacks only** (the file has one position per visit, not per single image).
   - For each object, on the current visit: the `expected_px` and `measured_px` markers, drawn like the target's but smaller, with the error ellipse from `measured_err_px`.
   - Hover: the label and type from the `overlays.json` entry with the same `name`, plus the object's agreement from the scoreboard (Noor), e.g. "matches Gaia" / "doesn't match Gaia".
   - Skip objects whose `measured_px` is `null` on that visit.
4. **"How accurate is this?" panel** from Noor's `data/scoreboard.json`: the headline sentences and one line per target.
5. **Infrared fingerprint: already built** (the chart of brightness against wavelength with Amna's reference spectra). Check it on the real files. It works for Epsilon Indi B and RW Aurigae. Barnard's Star is saturated (all hollow points), and WISE 0855 and R Draconis have only 2–3 images with a measured brightness. In those cases the panel should say so instead of drawing a near-empty chart.
6. **Live lookup hook.** Keep "This part of the sky isn't processed yet" as the single place where live lookup will plug in. I'll send the server details when the server works; the files it returns use exactly the `data/` layout.

## Amna: overlays, text and credits

1. **Asteroid layer:** pull, then run your asteroid script on the real manifests. The times are now in the format your script checks for.
2. **RW Aurigae: please check the A/B labels.** Our files disagree. Your overlays (from SIMBAD) call Gaia DR3 156430822114424576 "A". I center on 156430817820015232 as A. My evidence:
   - ALMA positions in Rodriguez et al. (2018, ApJ 859, 150, Table 1) put **B 1.44″ west of A** (RA 05:07:49.461 vs 49.572).
   - In Gaia DR3, **…817 is 1.44″ east of …822**, separation 1.493″ (ALMA: 1.497″). So …817 is the eastern star, A.
   - Caveat: the paper's table is inconsistent in Dec (its coordinates give a position angle of 286°, while it states 254°, which matches Gaia). East-west, which decides the labels, is consistent everywhere.
   - If you agree, swap the two labels in `overlays.json` and the target in your config. If you have a source that says otherwise, tell me and I'll recheck mine.
3. **Text corrections in `explanations.json`.** The current text contradicts what the site shows:

| Entry | Now says | Change to (suggested) | Source |
|---|---|---|---|
| `about.limits` | Saturated stars: "their position and brightness cannot be measured" | "Bright stars saturate the detector. SPHEREx still estimates their brightness from readouts taken before saturation, so positions and brightness are shown, but they are less precise (hollow points in the charts)." | SPHEREx Explanatory Supplement, sections 3.2.1–3.2.3 |
| `about.limits` | (missing) | "Images at 4–5 µm are noisier, so the color images show faint red speckle that is not a real source." | Our images; no external source needed |
| `verdicts.saturated` | "No position or brightness is shown for it" | "The object saturates the detector in most images, so its motion can't be measured reliably. Any positions and brightness shown are less precise than for fainter objects." | Explanatory Supplement 3.2 |
| `targets.wise_0855` | Motion from CatWISE2020; "if the verdict says too faint…" | The catalog motion shown is from Kirkpatrick et al. (2021): −8124 mas/yr in RA, +673 in Dec. The verdict is `moves_as_expected`, so drop the "too faint" sentence | Kirkpatrick et al. 2021, ApJS 253, 7 |
| All six `verdicts` | No criteria, no sources | Add the criterion sentence from the table under "How we measure" below, and link to that entry | — |
| Barnard's Star overlays | SIMBAD's planets b–e sit on the star as type `unknown` | Drop SIMBAD planet entries, or give them a `planet` label. They can't be seen at 6″ pixels | — |

4. **Credits to add** (copy the exact wording each source asks for from its own page):
   - **Kirkpatrick et al. 2021**, ApJS 253, 7: the WISE 0855 motion shown on the site.
   - **Gaia DR3 papers:** Gaia Collaboration, Prusti et al. 2016 (A&A 595, A1) and Gaia Collaboration, Vallenari et al. 2023 (A&A 674, A1). The current Gaia entry has the acknowledgement sentence but not the papers. Check against Gaia's credit page.
   - **Sesame name resolver** (CDS): turns typed names into coordinates.
   - **Software:** Astropy (asks for an acknowledgement and its papers), photutils, reproject, astroquery, NumPy, SciPy. Each publishes its own citation on its website.
   - **Rodriguez et al. 2018**, ApJ 859, 150: which RW Aur star is A.
   - **Lupton et al. 2004**, PASP 116, 133: the color-image method.
5. **Add `about.methodology`** with the text below.

## Noor: scoring

**What we score:** whether SPHEREx, measured by our tool, agrees with what the catalogs predict, and whether our error bars are honest. Three checks, all from files in `data/`:

| Check | Question | Data | How |
|---|---|---|---|
| **1. Target motion** | Does the measured motion match the catalog? | `manifest.json`: `measured_motion_mas_yr`, `catalog_motion_mas_yr` | Your z per axis and agreement label, as in your first version. Targets whose motion is `null` (R Draconis) are listed as "not measurable: saturated", not as a failure |
| **2. Target error bars** | Are the target's error bars honest? | `manifest.json`: every single image and every visit with a measured position | Pull = (measured − expected) / error per axis. About 68% should be within 1 and 95% within 2. Report a constant offset separately (Epsilon Indi B is an unresolved binary, so Gaia's position for it may be off) |
| **3. Field stars (new)** | Does the tool work on stars nobody tuned it for? | `objects.json` | See below |

**Field stars, exactly:**
- **Use** only objects with `reference: false` and an empty `blended_with`, and only visits with `saturated: false`.
  - Reference stars set the error bars, so they agree by construction.
  - Blended stars are measured as one light center.
  - Report reference stars separately, as a sanity check.
- **Recovered:** an object measured in at least one visit. Report "recovered X of Y" split by brightness (G < 14, 14–16, 16–17), because faint stars are expected to drop out.
- **Pulls:** same definition as check 2, pooled over all objects and targets: share within 1 and 2.
- **Per-object agreement:** χ² = sum of squared pulls over that object's measured visits, both axes, with 2 × (number of visits) degrees of freedom.
  - `agrees`: p ≥ 0.05
  - `tension`: 0.0027 ≤ p < 0.05
  - `disagrees`: p < 0.0027 (3σ, the same threshold as our verdicts)
- **Objects that disagree are the interesting ones:** a known star not doing what Gaia predicts. List them by name in the scoreboard; that list is our "unexpected" output.

**What is not scored:** brightness changes (no field-star brightness yet), objects in no catalog (not built), and R Draconis motion (saturated).

**How it gets to the site:** keep your `data/scoreboard.json`, and add to each target's `field_stars` an `objects` list of `{name, agreement, chi2, n_visits}`. The site joins it to `objects.json` and `overlays.json` by `name`, and uses it for the field-star hover text and the accuracy panel. Re-run whenever someone pushes new target files.

## Yara T: data layer and server

1. **Push first thing:**
   - Frame times in whole seconds, all five targets rebuilt. Only the time strings changed; the images are byte-identical.
   - `objects.json` for all five targets.
   - This update.
2. **`objects.json` (built overnight).**
   - **Method:** every Gaia star with G ≤ 17 in the field is measured with the same code and the same error model as the target, then averaged per visit (format below).
   - **First result, Epsilon Indi B:** 9 of 9 stars measured in all 4 visits. On the 6 stars that don't set the error bars, 56% of positions are within 1σ of Gaia and 92% within 2σ, against 68% and 95% for perfect error bars. So our error bars are slightly too small, and the scoreboard should say so.
   - **Next:** stars Gaia doesn't have (from CatWISE), in the same format, if time allows.
3. **Server for live lookup.** Today the site only opens the five pre-built fields. The server makes any typed position work:
   - **How it works:** the site sends a position or name. The server runs the same pipeline (find the images, download, clean, align, stack, measure, write files) and returns files in exactly the `data/` layout, plus a "still processing" status while it works. The five targets stay pre-built as the fallback.
   - **Time per field:** the five targets took 2.5–15 minutes each from downloaded images. Downloads add time: IRSA's cutout service gives about 2–3 images per second and sometimes answers "server busy". Plan for a few minutes per new field, and show progress on the site.
   - **Quick first look:** download a limited number of images spread over all visits and detectors first, then fill in the rest. The pipeline already supports this.
   - **Storage:** files are fetched per request. Only small reusable things are kept (wavelength tables). Per-field results go in a temporary cache with a size cap.
   - **Memory:** builds run one at a time. Two at once ran out of memory on a laptop, so the server needs a queue.
   - **Start at 51 px only.** Larger fields need more memory and download time.
   - **What Yara K gets:** the server's address, the request it accepts and the response it returns, as soon as it runs.

---

## `objects.json` format (new, agreed here)

One file per target and field size, next to the manifest: `data/<target_key>/fov<S>/objects.json`. Positions use the manifest's pixel convention (`[column, row]`, row 0 at the north edge). Values in the example are illustrative.

```json
{
  "target_key": "epsilon_indi_b",
  "size_px": 51,
  "selection": "Gaia DR3 stars inside the field on 2026-01-01 with G <= 17, except the target and anything within 0.5 px of it",
  "objects": [
    {
      "name": "Gaia DR3 6412595290592307840",
      "catalog": "Gaia DR3",
      "g_mag": 14.21,
      "reference": false,
      "blended_with": [],
      "visits": [
        {"n": 1, "expected_px": [12.41, 30.12], "measured_px": [12.47, 30.05], "measured_err_px": [0.05, 0.06],
         "n_measured": 118, "n_frames": 135, "saturated": false}
      ]
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `name` | Same as the `name` of this star in `overlays.json`: get the label, type and link from there |
| `g_mag` | Gaia G magnitude (smaller = brighter) |
| `reference` | `true` if this star was used to calibrate the error bars. Exclude it from accuracy scores |
| `blended_with` | Gaia stars within 0.5 px that SPHEREx can't separate from this one. Non-empty means the measured position is a combined light center |
| `visits[].expected_px` | Gaia position moved to the visit's mean date (proper motion and parallax) |
| `visits[].measured_px`, `measured_err_px` | SPHEREx position and its error, as for the target in the manifest. `null` if not measured in that visit |
| `n_measured`, `n_frames` | Images in that visit where the star was measured / where it was on the image |
| `saturated` | More than half of that visit's images are saturated at the star |

Stars are sorted brightest first. Only Gaia for now. Stars Gaia lacks (from CatWISE) may be added later in the same shape, with `"catalog": "CatWISE2020"`.

---

## "How we measure" text (for `about.methodology`)

**Title:** How we measure

**Text:**

> **Images.** For each field we take every SPHEREx image that covers it, from every public release, and cut out the field. Each image records one wavelength at each point on the detector, so we record the exact wavelength at the target in every image.
>
> **Cleaning.** We subtract the model of zodiacal light (sunlight scattered by interplanetary dust) supplied with each image, then any remaining smooth background, and blank the pixels the quality flags mark as unusable. Saturated pixels are kept: SPHEREx estimates their brightness from readouts taken before the detector filled up, so they are usable but less precise.
>
> **Visits and pictures.** Images more than 30 days apart belong to different visits. All images are placed on one grid with north up, and each visit's images are averaged into one picture, rejecting values far from the rest (cosmic rays, asteroids). These pictures are for looking at; we don't measure on them. Color pictures combine 0.75–1.6 µm (blue), 1.6–3.8 µm (green) and 3.8–5.0 µm (red).
>
> **Positions.** We measure each object in every single image, in that image's own pixels, because resampling blurs positions. A brighter catalog star close by is fitted at the same time at its known position, so it can't pull the measurement. The expected position comes from Gaia DR3, moved to the image's date using the star's motion and parallax (for WISE 0855, which Gaia can't see, from Kirkpatrick et al. 2021).
>
> **Error bars.** Each field contains isolated stars with very precise Gaia positions. Their scatter around those positions is added to every error bar, so the errors include everything that affects real measurements, not only the fit. Images from the same visit also share a small error (about 0.02 pixel) that averaging can't remove, and we include it.
>
> **Motion.** We fit a straight line through the measured positions over time, after removing the yearly parallax wobble the catalog predicts.
>
> **Brightness.** Because each image is at a different wavelength, we compare brightness between visits only after accounting for wavelength, and against how much the isolated stars' brightness changes from visit to visit.
>
> **Very faint objects.** When a target is too faint to measure in single images (WISE 0855), we fit SPHEREx's own model of a star's image to all of a visit's images at once.

**How each verdict is decided** (one sentence each for the verdict entries; σ is the measurement error):

| Verdict | Rule |
|---|---|
| `moves_as_expected` | The measured motion differs from zero by more than 3σ, adds up to at least 0.25 pixel over the data, and agrees with the catalog motion within 3σ |
| `moves_unexpected` | Motion detected as above, but more than 3σ away from the catalog motion |
| `no_motion_detected` | The data could have detected a 1-pixel shift, but no motion was found, and brightness doesn't change significantly |
| `brightness_changes` | No motion found, but brightness differs between visits by more than 3σ after accounting for wavelength and for the isolated stars' variation |
| `saturated` | Motion can't be measured (a 1-pixel shift wouldn't be detectable), and the object is saturated in more than half of its images |
| `too_faint` | Motion can't be measured, and the object is mostly not saturated: too faint |

The 0.25 pixel minimum exists because an unresolved pair's light center shifts when one star changes brightness (RW Aurigae: 0.07 pixel), which isn't motion.

**Sources:**
- SPHEREx Explanatory Supplement (IRSA), sections 3.2.1–3.2.3: saturation and flags
- Gaia Collaboration, Vallenari et al. 2023 (A&A 674, A1)
- Kirkpatrick et al. 2021 (ApJS 253, 7)
- Lupton et al. 2004 (PASP 116, 133): color images
