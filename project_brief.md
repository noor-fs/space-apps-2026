---
title: SPHEREx blink tool, team project brief
date: 2026-11-15
updated: 2026-11-15
tags:
  - current
  - nasa
  - brief
---

# SPHEREx blink tool: project brief

Shared context for the whole team's agents: project descriptions, the demo pitch, the write-up, and the case for why this project should win. It has the challenge, the product, every feature with its status, how it works, the results with numbers, the standout features, and what must not be claimed. Every number comes from the project's own files, with the source named so it can be checked.

> [!warning] Rules for any agent using this brief
> - **Write about the project and the team, not one person.** Credit features to the team; the owner table is there for coordination, not for the pitch.
> - **Don't claim anything marked "not built" or "unknown" as done.** Status labels are in the feature table. Check with the owner if a status may have changed.
> - **No discoveries.** The tool has not found a new object. It reproduces known motions and brightness changes and measures how trustworthy it is.
> - **Don't round results upward.** Use the numbers here with their error bars, including the weak ones under "Limits and honest caveats".
> - Use American English.

---

## 1. The challenge

**Event:** NASA Space Apps Challenge 2026, challenge "Planet X and SPHEREx". The full statement is in the team repo's `README.md`.

**SPHEREx** is a NASA all-sky survey telescope. Since May 2025 it has mapped the whole sky about every six months in 102 near-infrared bands (0.75–5 µm), with 6.15 arcsec pixels and six detectors (D1–D6). Data are public through NASA/IPAC IRSA.

**The ask:** a public web tool where a user enters a sky position (RA/Dec) and sees SPHEREx images of that patch over time, like a short video, so moving and changing objects are easy to spot. This is the method behind Pluto's discovery and citizen-science projects like Backyard Worlds (the statement credits volunteers with most known comets and brown dwarfs).

**Required test targets:**

| Target | What it is | Why it's a test |
|---|---|---|
| Barnard's Star | Fastest-moving star in the sky (~10″/yr) | Big motion, but very bright: saturates the detector |
| Epsilon Indi B | A pair of brown dwarfs orbiting a star | Moves only ~1 pixel across all the data |
| WISE 0855 | Coldest known brown dwarf, very fast | Too faint for Gaia; faint for SPHEREx too |
| RW Aurigae | Irregular variable star (a binary) | Brightness change, not motion |
| R Draconis | Variable star (Mira type) | Brightness change; saturated in almost every image |

**Suggested extras in the statement:** easy updates with new releases, creative use of the 102 bands (e.g. per-detector stacks), spectra on the fly, adding/subtracting frames, user-chosen field of view, Gaia/WISE overlays, coordinates in the URL, contamination flags.

## 2. The core problem (the "why it's hard" for the pitch)

1. **Every SPHEREx image is at a different wavelength at each spot.** The detectors use a linear variable filter. Blinking raw consecutive images shows *color*, not motion. The tool must compare like with like.
2. **Motions are tiny.** Epsilon Indi B moves ~1.1 pixel over 1.4 years. Our own early planning estimate put it below the measurement uncertainty.
3. **Bright stars saturate, faint ones vanish.** Barnard's Star and R Draconis saturate; WISE 0855 is barely visible in single images.
4. **The archive is huge and slow.** A field has 250–2,600 images. IRSA's servers return "server busy" errors and were down for hours during the event.
5. **Catalog positions are years old.** Barnard's Star moved ~4.5 arcmin since 2000; WISE 0855 is ~125″ (~20 px) from the challenge's coordinates by 2026. Every prediction must be moved to the image's date.

## 3. The product

**One-line description (draft):** Type any position or name in the sky; see every SPHEREx image of it as a flipbook, blink pair or difference image, with each object's measured position next to where catalogs predict it, and a verdict on whether it moves or changes.

**Product scope (decided 2026-11-14):** the tool works for *any* position, not a fixed list. The five targets are validation cases. Purpose is discovery: identify catalog objects in the field and, eventually, flag SPHEREx detections with no catalog counterpart. Data are fetched per request; nothing is stored in bulk.

### Features and status

| Feature | What it does | Owner | Status |
|---|---|---|---|
| Five pre-built targets | All five challenge targets processed at 51 px | Yara T | Done |
| Visit stacks | All images from one ~6-month visit averaged into one clean picture, north up | Yara T | Done |
| Flipbook / blink / difference | Play visits, alternate any two images, or subtract them (scaled so static stars cancel) | Yara K (site), Yara T (data) | Data done; site built per plan |
| Individual images | Every single exposure viewable, with its time, detector and wavelength | Yara T / Yara K | Done |
| Wavelength filter | User picks e.g. 1.5–1.7 µm; the tool blinks only images at that wavelength across all visits | Yara K (site) | Built per plan (in-browser) |
| Color composites | Per visit: blue 0.75–1.6, green 1.6–3.8, red 3.8–5.0 µm. Brown dwarfs look red | Yara T | Done |
| Quality-flag overlay | Saturated / cosmic ray / other flagged pixels per image | Yara T | Done |
| Measured vs expected markers | SPHEREx position of the target vs catalog prediction for that date, with error circle | Yara T / Yara K | Done |
| Verdict | One of six: moves as expected, moves unexpectedly, no motion, brightness changes, saturated, too faint | Yara T | Done |
| Catalog overlays | Gaia, SIMBAD, VSX markers; "What am I looking at?" panel | Amna | Done for five targets |
| Asteroid layer | Known asteroids on individual images | Amna | In progress (unblocked 2026-11-15) |
| Infrared fingerprint | Target brightness vs wavelength over reference spectra | Yara K / Amna | Built; thin for saturated or faint targets |
| Every star in the field measured | `objects.json`: expected and measured positions per visit for every Gaia star G ≤ 17 | Yara T | Done, all five targets |
| Scoreboard | "How accurate is this?": motion, error bars, field-star agreement | Noor | Built; see results |
| URL state | Every view is a shareable link | Yara K | Per plan |
| Field sizes 101 / 201 px | Wider fields | Yara T | Code supports it; only 51 px built |
| Live lookup of any position | Server runs the whole pipeline on demand; quick 120-image preview, then full build | Yara T | Works locally; **not deployed** (hosting undecided) |
| Objects in no catalog | Flag detections with no catalog match | — | **Not built** |
| Public deployment of the site | | Yara K | **Unknown** to this brief; check before claiming |

Sources: `saturday_plan.md` and `team_update_2026-11-15.md` in the repo.

## 4. Team

Five people. Who owns which part (for coordination; ask the owner before describing their part in detail):

| Part | Owner |
|---|---|
| Data layer and live-lookup server: archive search, images, measurements, verdicts, `objects.json` | Yara T |
| The website | Yara K |
| Overlays, explanation text, credits, reference spectra, asteroid layer | Amna |
| Scoring and matching: the accuracy scoreboard | Noor |
| _(fifth member: add name and part)_ | |

Repo: GitHub `noor-fs/space-apps-2026`.

## 5. How it works

The website reads static files in one shared format, so the five targets load instantly; the live-lookup server writes the same files for any new position. Behind the images, one field at a time:

1. **Resolve the target.** A name goes to Sesame (CDS) for coordinates, then Gaia DR3 for precise position and motion; CatWISE2020 for objects Gaia can't see. Position moved to 2026-01-01.
2. **Find every image** of the field across all releases (IRSA TAP; fallback IRSA SIA, then a saved list).
3. **Download small cutouts**, spread across visits and detectors first, so a partial download is already useful. A trick that stops the download before the large PSF table cut each image from ~4 MB/26 s to ~100 KB/2 s.
4. **Clean:** subtract the zodiacal light model and leftover background; blank unusable pixels using the quality flags. Saturated pixels are *kept*, after reading the SPHEREx Explanatory Supplement: their values come from readouts before saturation. This raised RW Aurigae from 9 to 127 measurable images out of 144.
5. **Align** every image onto one north-up grid.
6. **Group into visits** (gaps > 30 days) and stack, rejecting outliers (cosmic rays, asteroids).
7. **Measure** positions on each image's *own* pixels (resampling blurs positions), fitting nearby catalog stars at the same time so they can't pull the measurement. Error bars include the scatter of isolated reference stars and a shared per-visit error. For WISE 0855, too faint for single images, fit SPHEREx's own PSF model to all of a visit's images jointly.
8. **Verdict** from the motion fit and a brightness test that separates wavelength from real change.
9. **Export** the web files in the shared format; a server wraps all of it for live lookup.

Tools: Python, Astropy, astroquery, photutils, reproject, NumPy, SciPy, FastAPI. Every method choice and its measured effect is recorded in the data-layer decision log (ask Yara T).

## 6. Results (validation on the five targets)

Motion in milliarcseconds per year (mas/yr). Source: `data/<target>/fov51/manifest.json` in the repo.

| Target | Images | Visits | Verdict | Measured motion (RA, Dec) | Catalog motion | Agreement |
|---|---|---|---|---|---|---|
| Epsilon Indi B | 461 | 4 | moves as expected | +3895 ± 102, −2512 ± 76 | +3982, −2467 (Gaia DR3) | 0.9σ, 0.6σ |
| Barnard's Star | 359 | 3 | moves as expected | −1369 ± 248, +10322 ± 211 | −802, +10362 (Gaia DR3) | 2.3σ, 0.2σ |
| WISE 0855 | 258 | 3 | moves as expected | −8350 ± 1174, +1024 ± 570 | −8124, +673 (Kirkpatrick et al. 2021) | 0.2σ, 0.6σ |
| RW Aurigae | 335 | 3 | brightness changes | no significant motion | ~0 | — |
| R Draconis | 2493 | 9 | saturated | not measurable | ~0 | — |

**Highlights for the pitch:**
- **Epsilon Indi B:** motion detected even though our early estimate expected it to be undetectable. Total shift ~1.1 pixel. A non-moving model is ruled out (detection χ² 2533), and the fit agrees with Gaia (χ² 1.06).
- **WISE 0855:** the faintest target. Simple centroids gave "too faint"; the joint PSF fit turned it into a ~7σ motion detection matching the published value. Visits fitted at S/N 16–30.
- **RW Aurigae:** correctly called a brightness change, not motion. Its light center shifts 0.07 px because it's an unresolved binary, which is why a 0.25 px minimum shift is required before calling motion.
- **R Draconis:** honestly reported as saturated instead of a false "no motion" (an earlier version made that mistake; it was found and fixed).
- **Field stars:** in the Epsilon Indi B field, 9 of 9 Gaia stars down to G = 17 recovered; of 6 stars the tool was not tuned on, 5 agree with Gaia, 1 shows mild tension, 0 disagree. Across the other fields: Barnard's Star 42/42, RW Aur 21/21, WISE 0855 5/5 stars recovered in every visit.
- **Positions:** measured targets sit within 0.61″ (≤ 0.1 pixel) of catalog positions (scoreboard).
- **Self-correcting:** a test with 4× more images showed the error bars were too small (frames in one visit share an error). The fit was changed; the "moves unexpectedly" false alarm on Epsilon Indi B went away.
- **Resilience:** builds keep working when IRSA or the ESA Gaia archive is down (fallback services, checked to give identical values).

**Live lookup timing (local test, WISE 0855 field):** preview 5.4 min, full build (258 images) 5.0 min.

## 7. Limits and honest caveats

- **Error bars are slightly too small:** 56% of field-star positions within 1σ and 92% within 2σ, against 68% and 95% for honest error bars (real scatter ~1.1× the error bar). After accounting for crowding, uncrowded stars reach 89% / 99%. Say "calibrated and checked", not "exact".
- **Barnard's Star RA motion is 2.3σ from Gaia.** Within the 3σ rule, but the weakest agreement.
- **Saturated targets** (R Draconis, partly Barnard's Star) give poor brightness and no R Dra motion.
- **SPHEREx pixels are 6.15″:** binaries like RW Aur A+B (1.5″ apart) are one blob.
- **Not built:** flagging objects with no catalog match; fields larger than 51 px for the targets.
- **Live lookup isn't public yet:** hosting not decided. A brand-new field from scratch is untested because IRSA was down.
- **A Gaia data-quality trap found:** SIMBAD (and Wikipedia) swap the Gaia IDs of RW Aur A and B; verified with ALMA positions (Rodriguez et al. 2018).

## 8. Standout features: why this project should win

Each point says what's special and the evidence for it. Lead with the first three.

1. **It solves the problem that makes SPHEREx hard to blink.** Every image is at a different wavelength, so naive blinking shows color, not motion. The tool compares like with like: visit stacks, a wavelength filter that blinks only images at the same wavelength across visits, and a difference view scaled so static stars cancel. This is the challenge's "creative use of the 102 bands", built into the core rather than added on.
2. **It doesn't just show motion, it measures it, and checks itself against catalogs.** For each object, the SPHEREx-measured position sits next to the catalog prediction for that date, with an error circle, and a verdict says what's going on. 4 of 4 measurable targets match their catalog motions (section 6).
3. **It tells you how far to trust it.** Every Gaia star in the field (down to G = 17) is measured the same way as the target and scored against Gaia, so accuracy is shown, not asserted. The scoreboard reports its own weak spots (error bars ~1.1× too small).
4. **It goes beyond what the challenge expected.** Our own early estimate put Epsilon Indi B's motion below the uncertainty; the tool detects it (~1.1 pixel over 1.4 years). WISE 0855, too faint for single images, is measured by fitting SPHEREx's own PSF model across a whole visit, and matches the published motion.
5. **It knows the difference between moving, changing and unmeasurable.** Six verdicts with explicit rules: RW Aurigae is called a brightness change (its light center wobbles 0.07 px because it's an unresolved binary, below the 0.25 px motion threshold); R Draconis is called saturated rather than given a false "no motion".
6. **Any point in the sky, not five demos.** The live-lookup server runs the full pipeline for a typed position or name, with a quick preview first (~5 min per new field in local tests). The five targets are the validation set. (Say "live" only if it's deployed at demo time.)
7. **Every image is inspectable.** Individual exposures with time, detector, wavelength and quality-flag overlays; color composites where brown dwarfs show up red; catalog overlays from Gaia, SIMBAD and VSX; shareable URLs for any view.
8. **Built for new data and bad days.** Pulls every public release automatically; keeps working when the archive or Gaia servers are down (fallbacks checked to give identical values). IRSA was down for hours during the event and builds continued.
9. **Careful science.** Catalog positions moved to each image's date (WISE 0855 is ~20 px from the challenge's 2010-epoch coordinates by 2026); caught that SIMBAD swaps RW Aur A and B, verified with ALMA positions; every method decision recorded with its measured effect.

**Citizen-science angle:** Backyard Worlds volunteers found most known brown dwarfs by blinking images (challenge statement). This tool makes SPHEREx's new data blinkable for anyone, with the measurements to back up what they see.

## 9. Pitch lines to try

- "Blink comparison, rebuilt for a telescope that never takes the same picture twice."
- "It doesn't just show you a star moving. It tells you whether that matches what Gaia predicts, and how much to trust the answer."
- "Five targets were the exam. The product is any point in the sky."

## 10. Sources to cite in written material

- SPHEREx Explanatory Supplement v2.0 (IRSA, 2026-08-25), sections 3.2.1–3.2.3: saturation and flags.
- Gaia Collaboration, Vallenari et al. 2023, A&A 674, A1 (Gaia DR3).
- Kirkpatrick et al. 2021, ApJS 253, 7 (WISE 0855 motion).
- Rodriguez et al. 2018, ApJ 859, 150 (RW Aur A/B positions).
- Lupton et al. 2004, PASP 116, 133 (color images).
- Crill et al., arXiv:2404.11017 (SPHEREx detectors).
- Akeson et al., arXiv:2511.15823 (SPHEREx pipeline); Schlafly et al. 2018, arXiv:1710.01309 (crowdsource); Lang, Hogg & Schlegel 2016, arXiv:1410.7397 (Tractor).
- IRSA SPHEREx: https://irsa.ipac.caltech.edu/Missions/spherex.html

## Project files (in the repo)

- `saturday_plan.md`: roles and the shared data format
- `team_update_2026-11-15.md`: final-day plan, verdict rules, "How we measure" text
- `README.md`: the challenge statement
- `data/<target>/fov51/manifest.json`: per-target results; `data/scoreboard.json`: accuracy scores
