# catalogs/: code behind the markers, explanation text, credits and reference spectra

This folder holds the code that produces **Amna's files in `data/`**, as defined in the Saturday plan (`saturday_plan.md`). The website only reads `data/`; nothing here is read by the site.

| Output (in `data/`) | What the site does with it | Made by |
|---|---|---|
| `<target_key>/overlays.json` (5 targets) | Draws catalog markers (stars, variable stars, galaxies, asteroids) on the images | `gaia_layer.py`, `simbad_layer.py`, `vsx_layer.py`, `asteroids.py` -> `build_overlays.py` |
| `explanations.json` | Text for the type, verdict, target and "about" panels | `explanations_src.yaml` -> `build_explanations.py` |
| `credits.json` | The credits panel (acknowledgement wording copied from each data provider) | `fetch_pages.py` -> `build_credits.py` |
| `spectra/*.csv` (5 files) | Reference curves for the infrared-fingerprint chart | `spectra.py` |
| `simbad_otype_map.csv` | Table showing how SIMBAD object codes became our types (open question: see "Open questions") | `simbad_map.py` |

The five targets are `epsilon_indi_b`, `barnards_star`, `r_draconis`, `rw_aurigae`, `wise_0855`. Their field centers are in `config.py`.

## How to run it

Install: `pip install astroquery astropy numpy pandas requests pyvo pyyaml pypdf`. Run commands from the repository root. Python 3.10+.

| Step | Command | Result |
|---|---|---|
| 1 | `python catalogs/gaia_layer.py` | Gaia DR3 stars (G < 19, 0.3 deg radius) -> `layers/<key>/gaia.json` |
| 2 | `python catalogs/simbad_map.py` | SIMBAD object codes -> our types -> `data/simbad_otype_map.csv` |
| 3 | `python catalogs/simbad_layer.py` | SIMBAD objects -> `layers/<key>/simbad.json` |
| 4 | `python catalogs/vsx_layer.py` | Known variable stars (AAVSO VSX) -> `layers/<key>/vsx.json` |
| 5 | `python catalogs/asteroids.py --windowed [target_key ...]` | Asteroid layer for the real image times (needs Yara T's `manifest.json` files). One JPL request per window of at most 24 h, then each frame's position from JPL's rates; see "Asteroids" below. 20-175 requests per target, each 1-2.5 min. Cached, so safe to stop and re-run; JPL rate-limits (HTTP 429), so run at most 3 targets at once |
| 6 | `python catalogs/build_overlays.py` | Merges the layers into the five `overlays.json` files and runs a sanity check |
| 7 | `python catalogs/spectra.py` | Writes `data/spectra/*.csv` |
| 8 | `python catalogs/fetch_pages.py` then `build_credits.py` | Writes `data/credits.json` (stops if a quoted sentence is not found word for word on the provider's page) |
| 9 | `python catalogs/build_explanations.py` | Writes `data/explanations.json` from `explanations_src.yaml` |
| 10 | `python catalogs/verify_facts.py` | Checks each factual sentence's key phrase against its fetched source page |
| 11 | `python catalogs/validate.py` | Runs 58 checks on all files. Needs the network. Expect `ALL CHECKS PASSED` |
| practice | `python catalogs/test_dummy.py` | Dry run with dummy manifests (see "Practice run"). Touches nothing in `data/` |

`layers/` (one partial file per target and catalog) and `cache/` (raw service answers) are created when you run the steps. They are not committed (`.gitignore`), so a fresh clone needs steps 1-4 before steps 5 and 6. `asteroids.py` and `build_overlays.py` stop with a message if a target's gaia, simbad or vsx layer is missing, because building without them would drop those catalogs from `overlays.json`. To re-run after something changes: edit `config.py` (a field center) or `explanations_src.yaml` (text), re-run only the affected steps, then `build_overlays.py` and `validate.py`.

## Files here

| File | Purpose |
|---|---|
| `config.py` | The five targets and their centers, constants, allowed types and verdicts |
| `geometry.py` | The plan's two formulas, written once: sky position -> pixel `[column, row]`, and moving a star with its proper motion |
| `common.py` | Web requests with timeouts, retries and caching; SIMBAD host fallback |
| `explanations_src.yaml` | Every explanation sentence with its sources and a flag: factual (must have a source) or "how our tool works" |
| `validate.py`, `verify_facts.py` | The checkers |
| `test_dummy.py` | Practice run with dummy manifests, so errors show up before the real ones arrive |

## Method in short

* **Pixel and epoch.** One pixel is 6.15 arcsec. Gaia positions are for epoch 2016.0; SIMBAD and VSX positions for epoch 2000.0. Gaia's proper motion in RA already includes the cos(dec) factor, so it is copied unchanged. Coordinates are rounded to 6 decimals, proper motion to 2, magnitude to 2.
* **Layer vs type.** `layer` says which catalog an entry came from (gaia, simbad, vsx, asteroids). `type` says what it is (star, brown_dwarf, variable_star, galaxy, asteroid, young_star, unknown). They are independent.
* **Gaia.** The plan's exact query; the row count is checked against `SELECT COUNT(*)` so truncation cannot go unnoticed.
* **SIMBAD type map.** Built from SIMBAD's own object-type table (226 codes). Planets, clusters, gas clouds and radio/X-ray sources are `unknown`; eclipsing binaries and novae are `star`.
* **VSX.** Proper motion is written as `null`.
* **Asteroids.** JPL Small-Body Identification API, observer code 500 (Earth's center). These are predictions of known asteroids, not detections. Image times are grouped into windows of at most 24 h; JPL is asked once per window, at its middle, with a box of 0.33 deg (a request takes about the same time for any box size). Each asteroid's position at every frame time in the window is its JPL position moved in a straight line with JPL's own rates (on the sky, "/h; the RA rate already includes cos dec, so divide by cos dec). Checked on cached JPL answers (2026-11-15): within about 0.25 px up to 10 h from the query time, about 0.4 px at 13 h, 2+ px beyond 29 h, which is why windows stay within 12 h of the query time. Positions use the manifest's `frames[].time` strings exactly. Entries carry `v_mag` (JPL's visual magnitude; almost all are above 18.7 and most above 21, probably too faint for SPHEREx in a single image) as an extra field. The older `--from-manifests [target_key ...] [--max-times N]` mode (one request per frame time, optionally N evenly spaced times) still exists but needs about 1,980 requests for all five targets.
* **Spectra.** One method for all five: convert to F_nu, average in 0.02 um windows on a 0.01 um grid, divide by the 2.2 um value so that row is exactly 1, and stop where the source stops (no extension). G star: CALSPEC P330E (real data end at 2.452 um, a model follows, so the file ends at 2.44). M, L, T dwarfs: SpeX Prism Library. Galaxy: SWIRE Sb template.
* **Credits and explanations.** Wording is copied from the providers' pages and machine-checked. Where a provider publishes no wording (CatWISE, JPL, SWIRE) the entry says so and names the citation.

## Where this differs from the plan (needs the group)

1. **JPL box.** The plan says half-width 0.15 deg. The largest field (201 px) is 0.343 deg wide, so 0.15 would cut off its edges. The per-frame mode uses 0.18 deg and the windowed mode 0.33 deg (the field plus how far a main-belt asteroid moves in 12 h), sent as width/cos(dec) because the API measures RA in coordinate degrees, with `two-pass=true`; then only asteroids inside the 201 px image are kept. The plan has one position per image time; the windowed mode computes it from JPL's rates instead of asking per time.
2. **Repeated names.** The same star keeps the same `name` in the gaia, simbad and vsx layers, so a name can repeat across layers. Inside one layer names are unique. If the site uses `name` as a key for the whole file, tell Yara K.
3. **Mirror and API.** SIMBAD was unreachable at CDS, so the Harvard mirror (same data) was used. The AAVSO API answered from scripts and is newer than VizieR's copy of VSX, so it is the VSX source. The plan is silent on both.
4. **Extra file** `data/simbad_otype_map.csv` is not in the plan's folder list. The plan (p14) asks for the mapping to be written down.

## Practice run (dummy data)

`python catalogs/test_dummy.py` takes about 2 minutes the first time (JPL needs ~50 s per image time) and a few seconds after that. It works in `catalogs/test_output/sandbox/`, never in `data/`. It writes dummy `fields.json` and `manifest.json` files for RW Aurigae (51 and 201 px, sharing two made-up image times), then runs the real asteroid step, `build_overlays.py` and `validate.py` on that copy, and finally behaves like the website: every asteroid time must equal a manifest `frames[].time` exactly, asteroid markers must land inside the 201 px image, star markers must be placeable on a visit date, and a badly written time string must stop with a clear message. Expect `15/15 checks passed`. When the real manifests arrive, run the same three commands on `data/` (steps 5, 6, 11).

## Current centers (latest information)

* **RW Aurigae** uses component **A**, which is **Gaia DR3 156430817820015232**, the eastern star (changed 2026-11-15 on Yara T's evidence, confirmed against our Gaia positions: …817 is 1.44 arcsec east of …822, and Rodriguez et al. 2018 puts B west of A). SIMBAD's labels are the other way round; the Gaia and SIMBAD layers here have the two labels swapped. `config.py` still has the field center RA 76.956090, Dec 30.401128; the manifest's grid center is 76.95656, 30.401248 (0.24 px apart in RA), so `build_overlays.py`'s centering check reports about 0.26 px for this target. Overlays are stored in RA/Dec, so nothing on the site moves. Waiting on Yara T whether to sync the config center to the manifest.
* **WISE 0855** (config center, same caveat as above: the manifest grid is 0.34 px away in RA and 0.21 px in Dec) uses RA 133.759765, Dec -7.242186: SIMBAD's position and proper motion for `WISEA J085510.74-071442.5`, moved to 2026-01-01 with the plan's formula. The plan's provisional center was 108 arcsec away. Yara T's images must use the same centers, so both changes **need her confirmation**; if she disagrees, edit the two lines in `config.py` and re-run the Gaia, SIMBAD and VSX steps for that target, then steps 6 and 11.

## Open questions

* **RW Aurigae and WISE 0855 centers:** applied as described above; waiting for Yara T to confirm that her images use them.
* **SPHEREx credit:** the entry lists QR2, QR3 and DR1 spectral images (DOIs 10.26131/IRSA652, IRSA662, IRSA678) with IRSA's wording. QR1 is retired. Which releases the images really use needs Yara T's confirmation; edit the list in `build_credits.py`.
* **AAVSO credit:** AAVSO's wording contains a bracket to choose from, `[photometric, spectroscopic, solar, exoplanet]`. Keep it as is, or pick words.
* **Asteroid layer:** done for Epsilon Indi B, Barnard's Star, WISE 0855 and RW Aurigae (windowed mode, 2026-11-15); R Draconis was still running. The `--max-times` sampling mode was only a fallback.
* **Public text:** every explanation and credit sentence still needs a human proofread. All sentences with their sources are in `explanations_src.yaml`.
* **VSX proper motion:** the AAVSO API has proper motions for some stars; the task said to write `null`.
* **Spectra units:** the plan does not state units; all five are F_nu normalised at 2.2 um, and each `source` text says F_nu.
