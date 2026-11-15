# Project Burhan

**Project Burhan** is the SPHEREx Motion Viewer: a public web tool for watching the sky change in NASA's SPHEREx images, and for checking what you see against the catalogs. Built for the NASA Space Apps Challenge 2026, challenge **"Planet X and SPHEREx"**.

**Live site:** <https://noor-fs.github.io/space-apps-2026/>

## Why this is harder than it looks

SPHEREx never takes the same picture twice. Every image records a different wavelength at each spot on the detector, so blinking two raw images shows changes in color, not motion. The tool is built around comparing like with like:

- **Visit stacks:** all images from one visit (SPHEREx covers the whole sky about every six months) are averaged into one clean, north-up picture.
- **A wavelength filter**, so you can blink only images taken at the same wavelength.
- **Difference views** that subtract one image from another and scale for brightness automatically.

## What you can do

| Feature | What it shows |
|---|---|
| **Flipbook** | Play the visits in order, like a short video |
| **Blink** | Flip between any two images (A and B). A moving star jumps |
| **Difference** | B minus A. Anything that moved leaves a dark and light pair |
| **Brightness** | The target's brightness over time, at one wavelength |
| **Single images** | Open any single exposure with its time, detector, wavelength and quality flags |
| **Catalog markers** | Gaia stars, SIMBAD objects, AAVSO variable stars and known asteroids (JPL predictions), each with an explanation panel |
| **Measured vs. expected** | Where SPHEREx measured each object, next to where the catalog predicts it on that date, with error bars |
| **Field stars** | The same comparison for every Gaia star in the field, colored by whether it matches |
| **Verdict** | One of six results per target (for example "moves as expected" or "brightness changes"), with the rule and this target's numbers |
| **Infrared fingerprint** | Brightness against wavelength, compared with reference shapes for stars, brown dwarfs and a galaxy |
| **Shareable links** | Every view is saved in the URL |

The five challenge targets are pre-built: **Epsilon Indi B, Barnard's Star, WISE 0855, RW Aurigae and R Draconis**, each as a 51-pixel field (about 5 arcminutes across).

## Results

The tool measures each object's position in every single image and tests it against the catalog prediction for that date.

- **Targets.** Epsilon Indi B, WISE 0855 and Barnard's Star show the motion their catalogs predict. Barnard's Star is the weakest match, 2.3 sigma off in RA. WISE 0855 is too faint for single images, so it is measured by fitting SPHEREx's own model of a star's image across each visit. RW Aurigae is correctly called a brightness change, not motion. R Draconis saturates the detector and is reported as not measurable, rather than "no motion".
- **Stars the tool was never tuned on.** In 4 of the 5 fields, 65 of 73 Gaia field stars move as Gaia predicts, and all the stars with no close neighbor pass. R Draconis's field is left out of these totals because the bright star's glow dominates it. The 8 that fail have close neighbors that blend their light, and they are listed in [`data/scoreboard.json`](data/scoreboard.json).
- **Honest error bars.** Our error bars are slightly too small: the real scatter is about 1.4 times the error bar.
- **No discoveries are claimed.** Every result is for a known object. The tool reproduces known motions and brightness changes, and measures how far to trust them.

## Run it locally

The site is plain HTML, JavaScript and CSS, with no build step. From the repository root:

```
python -m http.server
```

Then open <http://localhost:8000/site/>.

## How the data is made

```
SPHEREx archive (IRSA) ──> spx/ + scripts/ ──> data/<target>/   images, measurements, verdict
Gaia, SIMBAD, VSX, JPL ──> catalogs/       ──> data/<target>/overlays.json, explanations, credits
data/                  ──> scoring/        ──> data/scoreboard.json
data/                  ──> site/           (the website only reads data/)
```

1. **Images** (`spx/`, `scripts/`): find every SPHEREx image of the field, download only the cutout, subtract the zodiacal light and the leftover background, blank the pixels the quality flags mark as unusable, align everything to one north-up grid and stack each visit.
2. **Measurements**: measure every object in every single image, in that image's own pixels, fitting nearby catalog stars at the same time. Error bars include the scatter of isolated Gaia reference stars.
3. **Verdict**: a motion fit plus a wavelength-aware brightness test gives one of six verdicts, each with an explicit rule. The rules are in the site's "How we measure" panel.
4. **Catalogs and text** (`catalogs/`): catalog markers, explanation text, credits and reference spectra. See [`catalogs/README.md`](catalogs/README.md).
5. **Scoring** (`scoring/`): checks the measurements against the catalogs. See [`scoring/README.md`](scoring/README.md).

To rebuild a target (needs the Python packages in `requirements.txt`; the catalog scripts need a few more, listed in [`catalogs/README.md`](catalogs/README.md), and the server has its own `server/requirements.txt`):

```
python scripts/build_target.py epsilon_indi_b --name "Epsilon Indi B"
python scripts/build_demo_targets.py          # all five targets
python scoring/build_scoreboard.py            # then re-score
```

### Live lookup (experimental)

Type any name or sky position outside the five targets into the site's search box, and a hosted server builds that field from the SPHEREx archive on request. The site shows a quick preview first and the full build when it is ready. A new field takes several minutes, and builds run one at a time, so you may have to wait in line.

The server code is in `server/`. It runs the same pipeline and returns files in the same layout as `data/`. To run your own copy (needs `server/requirements.txt`): `python -m uvicorn server.app:app --port 8000`.

## Repository layout

| Folder | Contents |
|---|---|
| `site/` | The website (HTML, CSS, JavaScript) |
| `data/` | Everything the website reads: per-target images, `manifest.json`, `objects.json`, `overlays.json`, plus `explanations.json`, `credits.json`, `scoreboard.json` and reference spectra |
| `spx/` | The image pipeline: archive search, cutouts, cleaning, alignment, stacking, measurement, verdicts, export |
| `scripts/` | Command-line entry points for building targets |
| `catalogs/` | Catalog markers, explanation text, credits and spectra |
| `scoring/` | The accuracy checks and the scoreboard |
| `results/` | Measurement tables and build logs behind each target's numbers |
| `server/` | The live lookup server |
| `fake_data/` | Fake test files in the same layout as `data/`, made by `site/script.py`. The site uses them only where `data/` has no real file |

## Limits

- Pixels are 6.15 arcseconds, so close pairs of stars blur into one dot.
- Stars with close neighbors have a constant position offset, and some fail the motion test.
- Saturated targets give less precise positions and brightness (shown as hollow points).
- Only 51-pixel fields are pre-built.
- Objects that are in no catalog are not flagged yet.

## Data and credits

SPHEREx images from NASA/IPAC Infrared Science Archive (IRSA). Catalogs: Gaia DR3 (ESA), SIMBAD (CDS), AAVSO VSX, CatWISE2020, the JPL Small-Body Identification service, and Kirkpatrick et al. 2021 for WISE 0855. The full acknowledgements, in each provider's requested wording, are in the site's **Credits** panel and in [`data/credits.json`](data/credits.json).

Built with Python (Astropy, astroquery, photutils, reproject, NumPy, SciPy, FastAPI) and a static HTML/JavaScript/CSS site.

## The challenge

[Planet X and SPHEREx](https://www.spaceappschallenge.org/), NASA Space Apps Challenge 2026: build a public web tool that shows SPHEREx images of a patch of sky over time, so anyone can spot moving objects.
