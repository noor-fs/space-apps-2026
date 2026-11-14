---
title: Saturday plan and shared data format
date: 2026-11-14
updated: 2026-11-14
tags:
  - current
  - nasa
  - plan
---

# Saturday plan and shared data format

This page has everything needed to start: who does what, what each person queries themselves, what they wait for, and the exact file format everyone writes and reads. Build against fake files in this format first. Real files go into the same slots during the day, with no code changes.

## Who does what

|                                        | Amna                                                                                                              | Yara K                                                                                            | Yara T                                                                                                                     |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| **Role**                               | Everything written or drawn *on top of* the images: catalog markers, explanation text, credits, reference spectra | The website                                                                                       | The images themselves and the measurements of the target                                                                   |
| **Queries external services herself?** | **Yes.** Gaia, SIMBAD, VSX, JPL, spectrum libraries                                                               | **No.** The site only reads files in `data/`                                                      | Yes, the SPHEREx archive at IRSA                                                                                           |
| **Waits for anything?**                | Only the exact image times (in `manifest.json`), and only for the asteroid layer                                  | Nothing to start: she makes her own fake files. Later she swaps in Amna's and Yara T's real files | Nothing                                                                                                                    |
| **Writes**                             | `overlays.json`, `explanations.json`, `credits.json`, `spectra/*.csv`                                             | The site, plus fake versions of every file for testing                                            | `fields.json`, and per field size: `manifest.json`, `visit_<N>.png`, `visit_<N>_rgb.png`, `.f32` data files, `frames/*.png` and flag overlays |
| **Reads**                              | This page                                                                                                         | This page, then everyone's files                                                                  | This page                                                                                                                  |


## The five targets and their field centers

Every image is centered on the target's position on **2026-01-01**. Use these exact centers for all queries. They come from Gaia DR3, moved forward from 2016 using the target's proper motion.

| target_key | Name | Field center RA (deg) | Field center Dec (deg) | Gaia DR3 source_id | Notes |
|---|---|---|---|---|---|
| `epsilon_indi_b` | Epsilon Indi B | 331.096653 | -56.800663 | 6412596012146801152 | Demo target. Moves about 1 pixel across the data |
| `barnards_star` | Barnard's Star | 269.446268 | 4.768204 | 4472832130942575872 | Fastest star in the sky. Saturated at short wavelengths |
| `r_draconis` | R Draconis | 248.167233 | 66.755024 | 1648328016354496384 | Variable star. Saturated in almost every image |
| `rw_aurigae` | RW Aurigae | 76.956560 | 30.401248 | 156430817820015232 | Irregular variable |
| `wise_0855` | WISE 0855 | 133.79 (provisional) | -7.245 (provisional) | not in Gaia | Too faint for Gaia; position from CatWISE2020. Yara T will confirm the exact center |

The site offers three field sizes (see "Field sizes" below). The largest is 201 × 201 pixels, 20.6 arcmin across. Query a **0.3 degree radius** around the center. That covers the corners of the largest field plus the distance stars have moved since their catalog date.

---

## Shared data format

> [!warning] Nobody changes this format without telling the group.

### Folder layout

The data are static files; there is no backend.

```
data/<target_key>/fields.json                     written by Yara T: which field sizes exist, e.g. {"sizes_px": [51, 101, 201]}
data/<target_key>/fov<S>/manifest.json            written by Yara T (one folder per field size S)
data/<target_key>/fov<S>/visit_<N>.png            written by Yara T (one per visit)
data/<target_key>/fov<S>/visit_<N>_rgb.png        written by Yara T (color composite per visit)
data/<target_key>/fov<S>/visit_<N>.f32            written by Yara T (real pixel values, for difference and brightness)
data/<target_key>/fov<S>/frames/v<N>_<i>.png      written by Yara T (every single image, i = 1, 2, ... within visit N)
data/<target_key>/fov<S>/frames/v<N>_<i>.f32      written by Yara T (real pixel values)
data/<target_key>/fov<S>/frames/v<N>_<i>_flags.png  written by Yara T (quality-flag overlay)
data/<target_key>/overlays.json                   written by Amna (one file covers all field sizes)
data/explanations.json               written by Amna (shared by all targets)
data/credits.json                    written by Amna
data/spectra/<type>.csv              written by Amna
```

### What a "visit" is

SPHEREx scans each part of the sky about every 6 months. Each visit produces several images over a few days. Each image is taken at a **different wavelength**, so flipping through single images shows color changes, not motion. Yara T stacks all the images from one visit into one picture.

The site shows both:
- **Visit stacks**, used for the flipbook, blink and difference views. These show motion over months.
- **Individual images**, clickable inside each visit. These show what one exposure saw at one wavelength and one moment. They are where asteroids appear, since asteroids move during a visit and are removed from the stacks.
- **Wavelength-filtered images.** The user picks a wavelength range, for example 1.5 to 1.7 µm, and the site keeps only the individual images whose `wavelength_um` falls inside it, from all visits, in time order. Because every remaining image is at nearly the same wavelength, blinking them is a fair comparison: changes are motion or real brightness change, not color. This is how the tool uses SPHEREx's many wavelengths. A narrow range may leave only one image per visit, or none, so the site shows how many images match.

### Field sizes and zoom

There are two different kinds of zoom, and the site needs both:

| | What it changes | Who handles it |
|---|---|---|
| **Field size** | How much sky the image covers | Yara T makes separate files for each size |
| **Magnification** | How large the same pixels are drawn on screen | The site, in the browser; no extra files |

Field sizes are always **odd**, so the target sits exactly on the center pixel:

| `S` (pixels) | Sky width | Use |
|---|---|---|
| 51 | 5.2 arcmin | Default. Close-up on the target |
| 101 | 10.4 arcmin | Neighborhood |
| 201 | 20.6 arcmin | Wide context |

- The site reads `fields.json` to know which sizes exist for a target, and offers only those.
- Magnification is a zoom control from 1× to 16× plus panning, applied to whichever field is loaded. Always draw with `image-rendering: pixelated`. Fast targets move only about **1 pixel** across all visits, and smoothing hides that.
- Larger fields mean bigger downloads for Yara T, so 201 may arrive later than 51 for some targets.

### Images

- Each pixel is 6.15 arcsec on the sky. An image in folder `fov<S>` is `S × S` pixels.
- **North is up, east is left.** Row 0 of the PNG is the northern edge.
- **Every image in one `fov<S>` folder lines up pixel for pixel.** The site never re-aligns anything.
- `visit_<N>.png`: one visit stack. N starts at 1, oldest visit first.
- `visit_<N>_rgb.png`: the same visit as a color composite (see "Why grayscale, and where color comes from").
- `frames/v<N>_<i>.png`: one individual image, on the same grid as the stacks, stretched **per image** (brightness differs a lot between wavelengths, so a shared stretch would make some images black). Pixels with no data (image edge, bad pixels) are transparent.
- `visit_<N>.f32` and `frames/v<N>_<i>.f32`: the **real pixel values** behind each PNG. The PNG is for quick display. The `.f32` file is what the site uses for anything that compares or measures: difference images, brightness and contrast controls.
  - Raw little-endian 32-bit floats, `S × S` values, row 0 first (north), no header.
  - Units: MJy/sr, background already subtracted.
  - Pixels with no data are `NaN`.
  - In JavaScript: `new Float32Array(await (await fetch(url)).arrayBuffer())`.
  - Size: 10 KB per image at S = 51, 160 KB at S = 201.
- `frames/v<N>_<i>_flags.png`: quality flags for one individual image, as an RGBA overlay with transparent where clean:
  - red = saturated
  - orange = cosmic ray, hot or bad pixel
  - blue = other flagged
  - The site shows it as a switchable "quality flags" layer.

### Why grayscale, and where color comes from

Each SPHEREx image records **one brightness value per pixel at one wavelength**. There is no color in a single image, so it is stored as one grayscale channel. Color comes from two places:

1. **False-color maps (the site).**
   - The site can paint any grayscale image with a color map (for example "inferno" or "viridis") using a canvas or WebGL shader.
   - A dropdown lets the user choose; grayscale is one option.
   - This is display only, so no extra files are needed. It is also why the data stay grayscale: the site can recolor them freely.
2. **True multi-wavelength color (Yara T's `visit_<N>_rgb.png`).**
   - Three wavelength ranges are stacked separately and combined as red, green and blue:

| Channel | Detectors | Wavelength  |
| ------- | --------- | ----------- |
| Blue    | D1 + D2   | 0.75–1.6 µm |
| Green   | D3 + D4   | 1.6–3.8 µm  |
| Red     | D5 + D6   | 3.8–5.0 µm  |

   - Objects that are much brighter at long wavelengths, such as cool brown dwarfs, look red. Ordinary stars look blue-white.
   - WiseView uses the same idea with two WISE bands.
   - The site offers a "color" toggle that swaps `visit_<N>.png` for `visit_<N>_rgb.png`. Flipbook and blink work the same way in color.

The format stays the same either way: grayscale PNGs for single-wavelength data, RGB PNGs only for the composites and the difference image.

### Pixel coordinates

Every position in the JSON files is written as `[column, row]`:
- counted from 0
- row 0 at the top (north)
- whole numbers are pixel *centers*
- the center pixel is `c = (S − 1) / 2`: 25 for S = 51, 50 for S = 101, 100 for S = 201

### Converting a sky position (RA, Dec) to a pixel

The site uses this to draw catalog markers; Amna uses it to sanity-check. Inputs:
- `α, δ`: the object's RA and Dec
- `α0, δ0`: the field center from the table
- all angles in radians
- `s = 6.15 / 3600`: degrees per pixel
- `c`: the center pixel for the field size

```
D      = sin δ · sin δ0 + cos δ · cos δ0 · cos(α − α0)
ξ      = cos δ · sin(α − α0) / D                         then convert radians to degrees
η      = (sin δ · cos δ0 − cos δ · sin δ0 · cos(α − α0)) / D   then convert radians to degrees
column = c − ξ / s          (east is left, so RA increases to the left)
row    = c − η / s          (north is up, row 0 at the top)
```

A marker is visible if both column and row are between -0.5 and S − 0.5.

### `manifest.json` (Yara T writes, site reads)

```json
{
  "target_key": "epsilon_indi_b",
  "name": "Epsilon Indi B",
  "grid": {
    "center_ra": 331.096653, "center_dec": -56.800663,
    "center_date": "2026-01-01",
    "pixel_scale_arcsec": 6.15, "size_px": 51
  },
  "visits": [
    {
      "n": 1,
      "image": "visit_1.png", "image_rgb": "visit_1_rgb.png",
      "date_start": "2025-04-18", "date_end": "2025-04-24", "date_mid": "2025-04-21",
      "n_images": 12,
      "wavelength_um": [0.75, 5.0],
      "target_expected_px": [25.6, 24.8],
      "target_measured_px": [25.5, 24.9],
      "saturated": false,
      "frames": [
        {
          "i": 1,
          "image": "frames/v1_1.png",
          "time": "2025-04-18T03:12:45Z",
          "detector": 3,
          "wavelength_um": 1.62,
          "target_expected_px": [25.6, 24.8],
          "target_measured_px": [25.4, 24.9],
          "saturated": false,
          "bad_pixel_fraction": 0.02,
          "target_flux_mjy": 0.84, "target_flux_err_mjy": 0.007,
          "data": "frames/v1_1.f32", "flags": "frames/v1_1_flags.png",
          "archive_url": "https://irsa.ipac.caltech.edu/..."
        }
      ]
    }
  ],
  "verdict": "moves_as_expected",
  "measured_motion_mas_yr": {"ra": 3948, "ra_err": 90, "dec": -2467, "dec_err": 87},
  "catalog_motion_mas_yr": {"ra": 3982, "dec": -2467, "source": "Gaia DR3"}
}
```

- `target_expected_px`: where the catalog says the target should be on that visit's date.
- `target_measured_px`: where SPHEREx actually shows it. `null` when it can't be measured, for example when it's saturated.
- `target_measured_err_px`: the uncertainty of that measurement in pixels, `[column_err, row_err]`, for each visit and each individual image (not shown in the example above). It includes the scatter measured on stars that don't move, not only the fit error. `null` when the measurement is `null`.
- `verdict` is one of the six values in the verdict list below.
- `measured_motion_mas_yr` is `null` when no motion could be measured.
- `target_flux_mjy` is the target's brightness in that image, in millijansky, with its error. It is `null` when saturated or too faint. The site uses it for brightness mode and the infrared fingerprint.
- Each visit also has `"data": "visit_1.f32"` for its real pixel values (not shown in the example above).
- In `frames`:
  - `time` is the exact UTC time of the exposure.
  - `wavelength_um` is the wavelength at the target's position in that image.
  - `detector` is 1 to 6. Each detector covers a different wavelength range.
  - `bad_pixel_fraction` is the share of pixels flagged as unusable.
  - `archive_url` opens the original file at IRSA.

### Verdict values (shared by the manifest and Amna's text)

| Value | Meaning |
|---|---|
| `moves_as_expected` | SPHEREx shows motion that matches the catalog |
| `moves_unexpected` | SPHEREx shows motion the catalog doesn't predict |
| `no_motion_detected` | No motion larger than the measurement error |
| `brightness_changes` | Brightness changes between visits |
| `saturated` | Too bright to measure: the detector maxed out |
| `too_faint` | Too faint to measure in these images |

### `overlays.json` (Amna writes, site reads)

One file per target, a list of objects (values below are illustrative, not real):

```json
[
  {
    "name": "Gaia DR3 6412595290592307840",
    "label": "HD 209100",
    "type": "star",
    "layer": "gaia",
    "ra": 330.84, "dec": -56.79, "epoch": 2016.0,
    "pmra_mas_yr": 3966.7, "pmdec_mas_yr": -2536.2,
    "g_mag": 4.5,
    "source": "Gaia DR3",
    "url": "https://simbad.cds.unistra.fr/simbad/sim-id?Ident=HD+209100"
  }
]
```

- `layer` is one of `gaia`, `simbad`, `vsx`, `asteroids`. The site makes one toggle per layer.
- `type` is a short word matching a key in `explanations.json`: `star`, `brown_dwarf`, `variable_star`, `galaxy`, `asteroid`, `young_star`, `unknown`.
- `label` is the human-readable name shown on hover. Use the SIMBAD name if there is one; otherwise repeat `name`.
- **Stars carry one position plus proper motion.** The site moves each star to each visit's `date_mid`:
  - `years = (date_mid − epoch)`, in years
  - `ra_new = ra + pmra_mas_yr × years / 3,600,000 / cos(dec)`
  - `dec_new = dec + pmdec_mas_yr × years / 3,600,000`
  - If proper motion is unknown, write `null` and the site leaves the marker fixed.
- **Asteroids carry one position per individual image** instead: `"positions": [{"time": "2025-04-18T03:12:45Z", "ra": ..., "dec": ...}]`, with no `ra`, `dec` or `pm` fields. The `time` values match the `frames[].time` values in the manifest exactly. The site draws asteroid markers only on individual images, never on stacks.

### `explanations.json` (Amna writes, site reads)

```json
{
  "types": {
    "brown_dwarf": {
      "title": "Brown dwarf",
      "text": "Two to four sentences in plain language.",
      "sources": [{"label": "Author et al. 2020", "url": "https://..."}]
    }
  },
  "verdicts": {
    "moves_as_expected": {"title": "...", "text": "...", "sources": []}
  },
  "targets": {
    "epsilon_indi_b": {"title": "...", "text": "Why this object is interesting and what to look for.", "sources": []}
  },
  "about": {
    "how_it_works": {"title": "How this works", "text": "...", "sources": []},
    "limits": {"title": "What this tool can't tell you", "text": "...", "sources": []}
  }
}
```

There must be one entry for every `type` and `verdict` value, every target_key above, and both `about` entries. The "limits" text must cover at least these points:
- Pixels are 6.15″, so only fast-moving objects show motion.
- Single images are each at a different wavelength.
- Bright stars saturate.
- A red/blue pair in a difference image is not proof of motion.

### `credits.json` (Amna writes, site reads)

```json
[{"what": "SPHEREx images", "text": "The exact acknowledgement wording the data provider asks for", "url": "https://..."}]
```

There must be one entry per data source: SPHEREx/IRSA, Gaia, SIMBAD, VSX, CatWISE, JPL, and each spectrum library used. Most of these archives publish the exact wording they want; copy it, don't paraphrase it.

### `spectra/<type>.csv` (Amna writes, site reads later)

```
wavelength_um,flux_norm,source
0.75,0.42,SpeX Prism Library: 2MASS J0415-0935 (T8)
...
```

- One file per type: `star_g.csv`, `star_m.csv`, `brown_dwarf_l.csv`, `brown_dwarf_t.csv`, `galaxy.csv`, plus any others she judges useful.
- `flux_norm` is scaled so the value at 2.2 µm is 1.
- Cover 0.75 to 5.0 µm where possible. If a source stops early (many stop at 2.5 µm), end the file there. Don't extend the curve.

---

## Amna: step by step

Amna **runs these queries herself**, from Python (`astroquery` or `requests`) or a browser. She does not receive query results from anyone. For each target, use the field center from the table and a 0.3 degree radius (covers the largest field).

### 1. Gaia layer (start here: tested and working on 2026-11-14)

Service: Gaia archive, `https://gea.esac.esa.int/tap-server/tap/sync` (or `astroquery.gaia.Gaia.launch_job`).

```sql
SELECT source_id, ra, dec, pmra, pmdec, parallax, phot_g_mean_mag
FROM gaiadr3.gaia_source
WHERE 1 = CONTAINS(POINT('ICRS', ra, dec),
                   CIRCLE('ICRS', <center_ra>, <center_dec>, 0.3))
  AND phot_g_mean_mag < 19
```

- Each row becomes one `overlays.json` entry with `layer: "gaia"`, `type: "star"` and `epoch: 2016.0`.
- Gaia's `pmra` already includes the cos(dec) factor, which is what the format expects.
- Done when `overlays.json` exists for all four Gaia targets. WISE 0855 gets a Gaia layer for its field stars too, but the target itself isn't in Gaia.

### 2. SIMBAD layer (names and object types)

Service: SIMBAD TAP, `https://simbad.cds.unistra.fr/simbad/sim-tap/sync`, or `astroquery.simbad`.

```sql
SELECT main_id, ra, dec, pmra, pmdec, otype
FROM basic
WHERE 1 = CONTAINS(POINT('ICRS', ra, dec),
                   CIRCLE('ICRS', <center_ra>, <center_dec>, 0.3))
```

- Map SIMBAD's `otype` codes to the `type` words above (for example `BD*` → `brown_dwarf`, `V*` → `variable_star`, `G` → `galaxy`). Write the mapping table down; it goes in the explanation panel's sources.
- SIMBAD positions are for epoch 2000.0, so write `epoch: 2000.0`.
- **Test this first thing.** On 2026-11-14 SIMBAD returned 404 errors to Yara T's machine, both through astroquery and the TAP address above. If it still fails, fill `label` and `type` for the five targets by hand from the SIMBAD website in a browser, and skip the layer for other stars.

### 3. VSX layer (known variable stars)

- Options:
  - VizieR TAP, `https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync`, catalog `"B/vsx/vsx"`.
  - The AAVSO website (`https://vsx.aavso.org`) in a browser.
- On 2026-11-14 VizieR timed out from Yara T's machine, and the AAVSO site blocks scripts (it shows a "Just a moment" bot check), so a browser search per target may be the practical route. Only five fields are needed.
- Entries get `layer: "vsx"` and `type: "variable_star"`. Add the variability type and period to `label` if known.

### 4. Explanation text and credits

- Write the explanation text and credits in the `explanations.json` and `credits.json` formats above.
- Every factual sentence needs a source in `sources`.
- Start with the five target entries, the six verdicts and the two `about` entries. The demo depends on those.

### 5. Reference spectra

Find spectra for the types listed and write them in the CSV format above. Check wavelength coverage before choosing a source. The SpeX Prism Library is a good start for brown dwarfs and cool stars, but it stops near 2.5 µm.

### 6. Asteroid layer (for the individual-image view)

Service: JPL Small-Body Identification API, `https://ssd-api.jpl.nasa.gov/sb_ident.api`, documented at `https://ssd-api.jpl.nasa.gov/doc/sb_ident.html`. Tested and reachable on 2026-11-14.

- Use observer `mpc-code=500` (Earth's center), the field center, and a half-width of 0.15 degrees (covers the largest field).
- **This layer needs the exact image times, which only Yara T has.** Write the function to take a list of UTC times (the `frames[].time` values) and return one position per time. Test it with made-up times now, and run it on the real times when `manifest.json` arrives.
- Asteroids appear only in individual images. They move during a visit, so the stacking removes them. The site draws these markers only in the individual-image view.
- SPHEREx orbits Earth, not at Earth's center, so a nearby asteroid's real position can differ from the geocentric prediction by up to about a pixel. That's fine for a marker.

**Amna is done when:** `overlays.json` exists for all five targets with at least the Gaia layer, and `explanations.json` covers every target, type, verdict and `about` entry.

---

## Yara K: step by step

Yara K **does not query any external service**. The site reads only the files in `data/`. Until the real files arrive she makes her own fake ones in exactly the formats above.

### 1. Make fake data (first hour)

- Write a small script (Python or JS) that makes `data/epsilon_indi_b/` with a `fields.json` listing 51 and 101, and a `fov51/` and `fov101/` folder, each with:
  - `manifest.json` describing 4 visits, about 6 months apart from April 2025 to October 2026, with `n_images` around 10 to 15 each.
  - Four `visit_<N>.png` files (S × S grayscale) and four `visit_<N>_rgb.png` files (give the moving dot a red tint), with a few fixed dots (stars) plus one dot that moves about 0.3 pixels per visit toward the lower left (Epsilon Indi B moves east and south: east is left, south is down).
  - A matching `.f32` file for every PNG (the same fake pixels as floats), so the difference view and brightness controls can be tested.
  - 10 to 15 fake individual images per visit in `frames/`, each with its own `time`, `detector`, `wavelength_um`, `target_flux_mjy` and a `_flags.png` with a few colored pixels. Spread the wavelengths across 0.75 to 5 µm and give each visit a few images in the same ranges, so the wavelength filter has something to match. Make them noisier than the stacks and vary their brightness. Add a fake asteroid to `overlays.json` that crosses a few images in one visit.
  - An `overlays.json` with a few made-up stars, including one with large proper motion, so the moving marker can be tested.
  - An `explanations.json` and `credits.json` with placeholder text.
- Also make a second fake target with `"verdict": "saturated"`, `"saturated": true`, `target_measured_px: null` and `target_flux_mjy: null` everywhere, to test the saturated display.

### 2. Build the site

**Picking the sky**
- Buttons for the five targets.
- A search box that accepts a name ("Barnard's Star") or coordinates ("269.45 4.77" or "17h57m48s +04d46m").
- Until live lookup exists (spare-time tier), search can only open fields that are already processed:
  - A name opens the matching target.
  - Coordinates open the field that contains them, using the RA/Dec-to-pixel formula with the largest field size.
  - Anything else shows "This part of the sky isn't processed yet" instead of an error.
- The URL holds the state, for example `?target=epsilon_indi_b&visit=2&mode=blink&layers=gaia,simbad`. Opening a link restores exactly that view.

**Image player**
- Shows `visit_<N>.png` with `image-rendering: pixelated`.
- **Field size** selector from `fields.json` (51 / 101 / 201), loading the matching `fov<S>` folder. Goes in the URL as `fov=101`.
- **Magnification** 1× to 16× with panning (mouse wheel, pinch, buttons), kept centered on the target by default. Goes in the URL as `zoom=8`. Markers scale with it.
- **Color**: a "color" toggle that swaps in `visit_<N>_rgb.png`, and a color-map dropdown (grayscale, inferno, viridis...) for grayscale images, applied in the browser. Goes in the URL as `cmap=inferno` or `color=rgb`.
- **Brightness and contrast** sliders, applied to the `.f32` values in the browser. This is also how false-color maps get drawn.
- Modes:
  - `flipbook`: play through every image currently selected (see "Filters"), with speed control and step forward/back.
  - `blink`: alternate between **any two images** the user picks: two visits, two individual images, or one of each. Goes in the URL as `a=v1&b=v3`, or `a=v1_4&b=v3_2` for individual images.
  - `difference`: the same two picked images, shown as `B − k × A` (see "Difference view").
- Under the image: the date (or date range for a visit), `n_images`, and the wavelength (or range).
- A fixed crosshair at the center pixel, so motion is easy to see against it.

**Difference view**
- The site computes the difference in the browser from the two `.f32` files. There is no precomputed difference file.
- `k` scales image A so stars that don't change cancel out. Images at different wavelengths have different brightness, so without `k` every star would leave a residue.
  - Default `k`: the median of `B / A` over pixels where both images are bright (above their 99th percentile), ignoring `NaN`.
  - A slider lets the user adjust `k` by hand.
- Colors: red = brighter in B, blue = brighter in A, white = no change. The color scale is symmetric around zero.
- If A and B differ in wavelength by more than 0.2 µm, show a note that some residue is color difference, not change.
- Always show this note: "A red/blue pair can appear on stars that don't move. Check the measured positions before calling something moving."

**Filters (time and wavelength)**
Both filters decide which images exist for every mode: flipbook, blink and difference pickers, thumbnails, and brightness mode.
- **Time:** a date range control (two-handle slider plus "from" and "to" date inputs), with quick buttons per year ("2025", "2026") and "all".
  - A visit is kept if its `date_mid` is inside the range.
  - An individual image is kept if its `time` is inside the range.
  - Goes in the URL as `from=2026-01-01&to=2026-12-31`.
- **Wavelength:** see "Wavelength filter" below.
- When a filter leaves fewer than two images, blink and difference are disabled with a short note explaining why.

**Individual images**
- Each visit has a strip of thumbnails, one per entry in its `frames` list, ordered by `time`. Clicking one shows that image in the main viewer, with its time, detector, wavelength and bad-pixel share, and a link to `archive_url`.
- Step forward and back through a visit's images, and return to the stack.
- When stepping through a visit's images unfiltered, a visible note says each one is at a different wavelength, so some brightness change between them is expected.
- Asteroid markers appear only on individual images, on images whose `time` matches the asteroid's `positions`.
- A "quality flags" layer toggle overlays `frames/v<N>_<i>_flags.png`, with a small legend of its colors.
- Add `frame=v<N>_<i>` to the URL so a link can open one specific image.

**Wavelength filter**
- A wavelength range control (two-handle slider, 0.75 to 5.0 µm), with quick presets per detector:
  - D1 0.75–1.1
  - D2 1.1–1.6
  - D3 1.6–2.4
  - D4 2.4–3.8
  - D5 3.8–4.4
  - D6 4.4–5.0 µm
- When a range is set:
  - The filtered images from all visits play as a flipbook and blink set, in time order, each labeled with its date and exact wavelength.
  - The site shows the match count ("7 images, 4 visits") and warns when a visit has none.
  - All filtering happens in the browser from `frames[].wavelength_um` in the manifest. No extra files are needed.
- The range goes in the URL: `wl=1.5-1.7`.

**Brightness mode**
- Switches the main panel from images to a chart of the target's `target_flux_mjy` (with error bars) against `time`, for the images that pass both filters.
- **It only plots when a wavelength range is set, and warns if the range is wider than one detector.** Comparing brightness at different wavelengths shows color, not change, which is the Friday rule: only compare photos at the same wavelength.
- Clicking a point opens that individual image.
- Goes in the URL as `mode=brightness`.

**Infrared fingerprint**
- A chart of `target_flux_mjy` against `wavelength_um` for all of the target's individual images (time filter applies), on top of Amna's reference shapes from `spectra/`.
- To compare shapes, divide everything by the target's value nearest 2.2 µm, as the reference files already are.
- If no reference covers a wavelength, don't draw that part of the reference.

**Layers**

Every marker type is its own layer with an on/off toggle, saved in the URL (`layers=measured,expected,gaia`):

| Layer | Source | What it draws |
|---|---|---|
| `measured` | Manifest: `target_measured_px` and `target_measured_err_px` | The SPHEREx measurement of the target on the current visit or image. A cross plus a circle whose radius is the error. Missing when the measurement is `null` |
| `expected` | Manifest: `target_expected_px` | The catalog prediction for the same date, in a different color from `measured`, so the two can be compared directly |
| `path` | Manifest: `target_measured_px` of every visit | A line through the measured positions in time order, with the current visit highlighted |
| `gaia`, `simbad`, `vsx`, `asteroids` | `overlays.json` | Catalog markers, placed with the RA/Dec-to-pixel formula after moving stars by proper motion to the visit's `date_mid` (or the image's `time`) |
| `flags` | `frames/v<N>_<i>_flags.png` | Quality flags (individual images only) |

- Hovering over any marker shows its label. For `measured` this includes the position error and, on individual images, `target_flux_mjy`.
- Clicking a catalog marker opens the "What am I looking at?" panel: name, type (with the `types` text from `explanations.json`), source, catalog link.

**Panels**
- An explanation panel showing the target's `targets` entry, its verdict with text, and `measured_motion_mas_yr` next to `catalog_motion_mas_yr`, all from `explanations.json`.
- When the verdict is `saturated` or `too_faint`, show that text instead of empty measurement numbers.
- "How it works" and "Limits" panels from `about` in `explanations.json`.
- A credits panel built from `credits.json`.

**Deploy**
- Deploy it anywhere that serves static files (GitHub Pages, Netlify, Vercel) and post the link.

### 3. Swap in real files

- When Amna posts `overlays.json` or `explanations.json`, or Yara T posts a target folder, replace the fake file.
- If anything breaks, the file doesn't match this page. Tell the person who wrote it; don't change the site to fit.

**Yara K is done when:** the deployed site plays the fake Epsilon Indi B in flipbook, blink and difference modes between any two images, filters by time and wavelength, opens every individual image, and has markers, toggles, panels and working links.

Build order if time runs short (must-haves first, as agreed Friday):
1. Picking the sky.
2. Flipbook and blink.
3. Labels under the image.
4. "What am I looking at?"
5. Overlays and flags.
6. URL state.
7. Credits and limits.
8. Then difference, filters, brightness mode and fingerprint.

---

## Not covered by this plan yet

These Friday features need work beyond Saturday. They're listed so nobody thinks they're handled:
- **Expected vs observed for *every* object, not just the target.** This needs Yara T to measure the position of every catalog object in the field, plus the matching step (Noor, Sunday) to give each object a verdict. Once they agree an `objects.json` format, the site draws two markers per object, the same way it does for the target.
- **Detections that are in no catalog.** This needs a source-finding step on the images (Yara T) and matching (Noor).
- **Scoreboard** ("recovered X of Y known objects"). This is built from the matching results (Noor).
- **Live lookup for any sky position** (spare-time tier).

---

## When blocked

1. Post what you're waiting on.
2. Switch to the next step that doesn't need it. Everyone has fake-data or text work available.
3. Never change the format to get around a problem. Raise it in the chat.
