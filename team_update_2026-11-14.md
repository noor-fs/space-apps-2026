---
title: Team update, images and measurements (2026-11-14)
date: 2026-11-14
updated: 2026-11-14
tags:
  - current
  - nasa
  - team
---

# Team update: images and measurements (Yara T, 2026-11-14)

The data layer now works from start to finish. Give it any sky position (a name or coordinates) and it produces every file I own in [[nasa_repo/space-apps-2026/saturday_plan|the Saturday format]]. The five challenge targets are being built now as static files at 51 px. Once they're pushed to `data/`, the site needs no archive queries for them.

## What the pipeline does

| Service / library | What it's used for |
|---|---|
| IRSA SIA and TAP (SPHEREx archive) | Find every SPHEREx image that overlaps the field. SIA is a second IRSA search service that is still up when TAP is down, as it was most of today |
| IRSA cutout service | Download only the small square of each image around the field, not the full 65 MB file |
| Gaia DR3, CatWISE2020, Sesame | Turn a name into a position and move it to each image's date (proper motion and parallax) |
| astropy, reproject, photutils | Sky coordinates, placing every image on one north-up grid, background removal, measurements |

1. Find all images of the field, from every release (DR1 and QR3 so far; future releases are picked up automatically).
2. Clean each image: subtract the zodiacal-light model and leftover background, and blank unusable pixels using the quality flags.
3. Place every image on the shared north-up grid so pixels line up between images.
4. Group images into visits (one SPHEREx pass, about every 6 months) and stack each visit.
5. Measure the target in every single image: position on the original pixels, brightness, saturation, and the wavelength it was seen at.
6. Test for motion and brightness change against the scatter of non-moving reference stars, and give one of the six verdicts.
7. Write the web files.

## Current results

| Target | Verdict | Note |
|---|---|---|
| Epsilon Indi B | `moves_as_expected` | Matches Gaia within the errors |
| Barnard's Star | `moves_as_expected` | Flagged saturated in every image; positions still measurable in about a third |
| RW Aurigae | `brightness_changes` | Brighter at 1 µm and fainter at 4–5 µm between visits |
| WISE 0855 | provisional | Measurement being fixed (see below). Its files will be replaced, same format |
| R Draconis | not yet built | About 2,600 images; built last |

## What to update in your code

The format is unchanged. These are rules about how fields are filled that weren't in the example.

**Everyone**
- **Field sizes.** `fields.json` lists only 51 for now; 101 and 201 come later. 201 px for R Draconis would be several hundred MB, so we need to decide on hosting before adding it.
- **WISE 0855 field center:** RA 133.760346, Dec −7.241822 (the plan said "133.79, −7.245, provisional"). For the RA/Dec-to-pixel formula, always take the center from `grid` in `manifest.json`, not from the table in the plan.
- **RW Aurigae is a binary.** We center on component A (Gaia DR3 156430817820015232), confirmed against ALMA positions (Rodriguez et al. 2018, ApJ 859, 150). SIMBAD has the Gaia IDs of A and B swapped, so don't take the A/B labels from SIMBAD.

**Yara K (site)**
- **Saturated images now have a brightness.** `target_flux_mjy` is filled when `saturated: true` (agreed with me during step 7; earlier it was null). The values are usable but less precise. The brightness chart and fingerprint should mark these points differently, e.g. hollow, or let the user hide them.
- **Saturated images also keep their measured position.** Barnard's Star's motion depends on them, so don't hide the `measured` marker when `saturated` is true.
- **`n_images` can be larger than the `frames` list.** `n_images` counts every image stacked into the visit. `frames` lists only images covering at least half the field (edge-clipped images go into the stack but aren't shown on their own).
- **A visit's `saturated`** is true when more than half its images are saturated at the target.
- **`time`** is the exposure mid-point in UTC, to the millisecond, e.g. `2025-04-24T20:32:54.640Z`.
- **Errors** (`target_measured_err_px`) already include the measured scatter of non-moving stars, so they can be drawn as-is.
- **Images with no data** have transparent PNG pixels and `NaN` in the `.f32` files, as in the format.
- **Data source.** The site should pick up the real `data/` folders automatically, replacing the fake files. If something breaks, tell me; the files should match the format exactly.

**Amna (overlays and text)**
- **Asteroid layer:** the real image times are now in `manifest.json` (`frames[].time`), so the asteroid query can run on them.
- **WISE 0855 marker:** CatWISE2020's motion for it is too uncertain, and by 2026 its predicted position is 2–3″ off. Please use Kirkpatrick et al. (2021, ApJS 253, 7, Table 5): RA 133.780984, Dec −7.243932 at MJD 57633.39, pmRA −8123.7, pmDec +673.2 mas/yr, parallax 439.0 mas. I'm switching to the same values.
- **Quality-flag legend:** red = saturated; orange = cosmic ray, hot, bad or missing pixel; blue = other flags (halo, ghost, crosstalk). This matches the format.
- **Limits text:** worth adding that 4–5 µm images are noisier, so the color composites show faint red speckle that isn't a source.

## Noor: connecting a scoring feature

The Saturday plan doesn't cover scoring yet. Here is what my side provides now and what it can provide next. Tell me what scoring needs and I'll match it.

**Available now, per target**
- **Target position:** expected (from the catalog) and measured (from SPHEREx), in every visit and every single image, with errors in pixels. These are `target_expected_px`, `target_measured_px` and `target_measured_err_px` in `manifest.json`.
- **Verdict and motion:** the verdict, the measured motion, and the catalog motion.
- **Brightness:** per image, with wavelength and a saturation flag.
- **The images themselves:** real pixel values (`.f32`) for every visit stack and every single image, on one shared grid. Use these if you want to run your own source detection.

**Not built yet, but the method already exists**
- I already measure isolated Gaia reference stars in each field internally (8 at Epsilon Indi B) to calibrate the errors. The same measurement can run on every catalog object in the field (Gaia, plus CatWISE for objects Gaia lacks), giving expected vs. measured position and brightness per object per visit. That would be the `objects.json` the plan mentions.
- Detections with no catalog counterpart ("unidentified") need a source-finding step on the stacks. Not started.

**Draft for `objects.json`, to agree on together** (one file per target and field size, in the same folder as `manifest.json`):

```json
[
  {
    "id": "Gaia DR3 6412595290592307840",
    "catalog": "Gaia DR3",
    "g_mag": 14.2,
    "visits": [
      {"n": 1, "expected_px": [12.4, 30.1], "measured_px": [12.5, 30.0], "measured_err_px": [0.05, 0.05],
       "flux_mjy": 1.8, "flux_err_mjy": 0.04, "saturated": false}
    ],
    "detected": true
  }
]
```

Unidentified detections would use the same shape, with `"catalog": null` and no `expected_px`. This is a proposal only; nobody should build on it until we agree.

## Not done yet

- **WISE 0855:** two problems. The catalog position we predicted from was off by about half a pixel, and a nearby star pulls the measurement. The fix uses better published astrometry and fits the target and its neighbor together with SPHEREx's own PSF model. Same file format; the files get replaced.
- **R Draconis:** still to be built (saturated in nearly every image).
- **Field sizes 101 and 201 px:** pending the hosting decision above.
