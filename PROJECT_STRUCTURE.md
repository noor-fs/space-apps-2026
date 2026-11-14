---
title: Project structure
date: 2026-11-14
updated: 2026-11-14
tags:
  - current
  - nasa
  - plan
---

# Project structure

Who works in which folder, and which files belong where. The file formats themselves are defined in [[saturday_plan]]; this page only says where things live.

> [!warning] Two rules
> 1. **Only write in your own folders.** If you need a change in someone else's folder, ask them.
> 2. **Never change a file format in `data/` to get around a problem.** Raise it in the chat (same rule as [[saturday_plan]]).

## Overview

```
space-apps-2026/
├── README.md               the challenge statement
├── saturday_plan.md        who does what + the shared data format
├── PROJECT_STRUCTURE.md    this page
│
├── spx/                    Yara T   SPHEREx processing code (Python library)
├── scripts/                Yara T   commands that build a target's image files
├── cache/                  Yara T   downloads; NOT in git
├── results/                Yara T   measurements and checks behind the numbers
│
├── catalogs/               Amna     code that queries Gaia, SIMBAD, VSX, JPL, spectra (proposed)
├── site/                   Yara K   the website (proposed)
│
└── data/                   everyone  the files the website reads (each file has one owner, below)
```

`catalogs/` and `site/` don't exist yet. They are a suggestion; the owner creates them or picks another name and updates this page.

## Who owns what

| Folder | Owner | What goes in it | What does NOT go in it |
|---|---|---|---|
| `spx/` | Yara T | Reusable Python: archive queries, target positions, cutouts, alignment, stacking, measurements, writing the web files | One-off experiments, outputs |
| `scripts/` | Yara T | Commands that run the pipeline, e.g. "build everything for one target" | Library code (goes in `spx/`) |
| `cache/` | Yara T | Downloaded SPHEREx cutouts, frame lists, catalog query results. Can be deleted and re-downloaded at any time | Anything that can't be re-made by re-running the code |
| `results/<target_key>/` | Yara T | Measurement tables (positions, brightness, saturation checks), run logs, diagnostic plots. Lets anyone check where a number in the manifest came from | Files the website reads |
| `catalogs/` | Amna | Code and notes for the overlay, explanation, credits and spectra files | The output files themselves (they go in `data/`) |
| `site/` | Yara K | HTML, JS, CSS, the fake-data script | Real data files |
| `data/` | per file, see next table | Only the files listed in [[saturday_plan]], in exactly that format | Code, notes, intermediate files, anything not in the format |

## Who writes each file in `data/`

| File | Owner |
|---|---|
| `data/<target_key>/fields.json` | Yara T |
| `data/<target_key>/fov<S>/manifest.json` | Yara T |
| `data/<target_key>/fov<S>/visit_<N>.png`, `visit_<N>_rgb.png`, `visit_<N>.f32` | Yara T |
| `data/<target_key>/fov<S>/frames/v<N>_<i>.png`, `.f32`, `_flags.png` | Yara T |
| `data/<target_key>/overlays.json` | Amna |
| `data/explanations.json` | Amna |
| `data/credits.json` | Amna |
| `data/spectra/<type>.csv` | Amna |

`<target_key>` is one of: `epsilon_indi_b`, `barnards_star`, `r_draconis`, `rw_aurigae`, `wise_0855` (same keys as [[saturday_plan]]). Lowercase, underscores, no spaces.

### Fake files

Yara K's fake files go in `data/` under the real names, so the site never needs a code change. When the owner commits the real file, it replaces the fake one, and from then on only the owner edits it. Fake-only test targets (e.g. a saturated test case) use a key starting with `fake_`, e.g. `data/fake_saturated/`, so they can never be confused with a real target.

## Still open

- **Noor's matching work** (Sunday: verdicts per object, `objects.json`, scoreboard) has no folder yet. Proposed: `matching/` for code, with `objects.json` added to `data/<target_key>/` once its format is agreed.
- **Large files.** `cache/` is ignored by git. FITS files in `results/` can be large and are better kept out of git too (add `results/**/*.fits` to `.gitignore`). The `.f32` files in `data/` must be committed, because the site needs them.
