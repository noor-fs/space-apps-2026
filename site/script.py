#!/usr/bin/env python3
"""
Makes the fake test files for the website, in the repo's fake_data/ folder
(next to site/). The site reads data/ first and uses fake_data/ only for files
that haven't been posted to data/ yet, so real files always win.

results
  fake_data/epsilon_indi_b/   sizes 51 + 101, 4 visits, 10-15 images each,
                              target drifts toward lower left (east + south),
                              a fake asteroid crossing 4 images of visit 2,
                              one image per visit with a no-data strip (NaN)
  fake_data/fake_saturated/   size 51 only, saturated target, nulls everywhere
                              (open it with ?target=fake_saturated)
  fake_data/explanations.json, fake_data/credits.json   placeholder text
  fake_data/spectra/*.csv     fake reference spectra for the fingerprint chart

fake_data/ is deleted and rebuilt on every run. The script refuses to write to
a folder called data/, so it can never touch the team's real files.
"""
import argparse
import json
import math
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image

PIX_ARCSEC = 6.15
S_DEG = PIX_ARCSEC / 3600.0
OMEGA_SR = (PIX_ARCSEC / 206264.806) ** 2  # pixel solid angle
PSF_SIGMA = 0.8  # pixels
RGB_TINT_GB = 0.05 # share of the moving dot put in G and B of visit_N_rgb.png (low = redder)
CENTER_DATE = datetime(2026, 1, 1, tzinfo=timezone.utc)

DETECTORS = [(1, 0.75, 1.1), (2, 1.1, 1.6), (3, 1.6, 2.4),
             (4, 2.4, 3.8), (5, 3.8, 4.4), (6, 4.4, 5.0)]
BASE_WL = [0.80, 0.95, 1.20, 1.45, 1.70, 2.05, 2.30,
           2.90, 3.40, 3.95, 4.25, 4.55, 4.80, 1.00, 3.00]

rng = np.random.default_rng(42)


# ---------------------------------------------------------------- helpers
def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def day(t):
    return t.strftime("%Y-%m-%d")


def epoch_dt(year):
    y = int(year)
    return datetime(y, 1, 1, tzinfo=timezone.utc) + timedelta(days=(year - y) * 365.25)


def years_between(t, epoch_year):
    return (t - epoch_dt(epoch_year)).total_seconds() / (365.25 * 86400)


def move(ra, dec, pmra, pmdec, years):
    """Exactly the format doc's rule (pmra already includes cos dec)."""
    if pmra is None or pmdec is None:
        return ra, dec
    return (ra + pmra * years / 3.6e6 / math.cos(math.radians(dec)),
            dec + pmdec * years / 3.6e6)


def sky_to_px(ra, dec, ra0, dec0, size):
    """The format doc's RA/Dec -> [column, row] formula."""
    a, d, a0, d0 = map(math.radians, (ra, dec, ra0, dec0))
    D = math.sin(d) * math.sin(d0) + math.cos(d) * math.cos(d0) * math.cos(a - a0)
    xi = math.degrees(math.cos(d) * math.sin(a - a0) / D)
    eta = math.degrees((math.sin(d) * math.cos(d0)
                        - math.cos(d) * math.sin(d0) * math.cos(a - a0)) / D)
    c = (size - 1) / 2
    return c - xi / S_DEG, c - eta / S_DEG


def offset_to_sky(xi_arcsec, eta_arcsec, ra0, dec0):
    """Inverse gnomonic: tangent-plane offsets (east +, north +) -> RA/Dec."""
    xi, eta = math.radians(xi_arcsec / 3600), math.radians(eta_arcsec / 3600)
    d0, a0 = math.radians(dec0), math.radians(ra0)
    den = math.cos(d0) - eta * math.sin(d0)
    ra = a0 + math.atan2(xi, den)
    dec = math.atan2(math.sin(d0) + eta * math.cos(d0), math.hypot(xi, den))
    return math.degrees(ra) % 360, math.degrees(dec)


def detector_for(wl):
    for d, lo, hi in DETECTORS:
        if lo <= wl < hi:
            return d
    return 6


def star_shape(wl):
    """Ordinary star: brighter at short wavelengths (=1 at 2.2 um)."""
    return (wl / 2.2) ** -1.6


def bd_shape(wl):
    """Cold brown dwarf: methane dips, very bright near 4.3 um (=1 at 2.2 um)."""
    def raw(w):
        g = lambda mu, s, a: a * math.exp(-0.5 * ((w - mu) / s) ** 2)
        return (0.04 + g(1.27, 0.08, 1.0) + g(1.60, 0.08, 0.7) + g(2.10, 0.10, 0.45)
                + g(4.30, 0.35, 2.6) + g(3.9, 0.2, 0.6))
    return raw(wl) / raw(2.2)


def psf(size, col, row, flux_mjy):
    """Gaussian star in MJy/sr, background already subtracted."""
    y, x = np.mgrid[0:size, 0:size]
    amp = flux_mjy * 1e-9 / OMEGA_SR / (2 * math.pi * PSF_SIGMA ** 2)
    return amp * np.exp(-0.5 * ((x - col) ** 2 + (y - row) ** 2) / PSF_SIGMA ** 2)


def stretch(arr, lo, hi):
    a = np.clip((arr - lo) / (hi - lo), 0, 1)
    return np.arcsinh(a * 10) / np.arcsinh(10)


def write_f32(path, arr):
    arr.astype("<f4").tofile(path)  # little-endian, row 0 = north, no header


def write_gray_png(path, arr, lo, hi, alpha_nan=False):
    v = (stretch(np.nan_to_num(arr, nan=lo), lo, hi) * 255).astype(np.uint8)
    if alpha_nan:
        a = np.where(np.isfinite(arr), 255, 0).astype(np.uint8)
        Image.fromarray(np.dstack([v, a]), "LA").save(path)
    else:
        Image.fromarray(v, "L").save(path)


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2))


def r2(v):
    return None if v is None else round(float(v), 2)


# ---------------------------------------------------------------- one target
def make_target(out, key, name, ra0, dec0, pm, target_flux_22, sizes,
                saturated=False, asteroid=False):
    """pm = (pmra, pmdec) mas/yr of the target. Center = position on 2026-01-01."""
    tdir = out / key
    tdir.mkdir(parents=True, exist_ok=True)
    write_json(tdir / "fields.json", {"sizes_px": sizes})

    # Target catalogue position at Gaia epoch 2016.0 (moved back from the center).
    t_ra16, t_dec16 = move(ra0, dec0, pm[0], pm[1], -10.0)

    # Field stars (epoch 2016, inside the largest field), one fast mover.
    half = (max(sizes) - 1) / 2 * PIX_ARCSEC * 0.95
    stars = []
    for k in range(24):
        xi, eta = rng.uniform(-half, half, 2)
        ra, dec = offset_to_sky(xi, eta, ra0, dec0)
        g = float(rng.uniform(11, 17.5))
        pmra, pmdec = (float(rng.normal(0, 15)), float(rng.normal(0, 15)))
        stars.append(dict(ra=ra, dec=dec, pmra=pmra, pmdec=pmdec, g=g, fast=False))
    ra, dec = offset_to_sky(-half * 0.45, half * 0.35, ra0, dec0)
    stars.append(dict(ra=ra, dec=dec, pmra=-2500.0, pmdec=1800.0, g=12.0, fast=True))

    # Four visits ~6 months apart, Apr 2025 -> Oct 2026, 10-15 images each.
    visit_starts = [datetime(2025, 4, 18, 2, tzinfo=timezone.utc),
                    datetime(2025, 10, 17, 5, tzinfo=timezone.utc),
                    datetime(2026, 4, 19, 1, tzinfo=timezone.utc),
                    datetime(2026, 10, 16, 4, tzinfo=timezone.utc)]
    visits_meta = []
    for n, t0 in enumerate(visit_starts, start=1):
        n_img = int(rng.integers(10, 16))
        wls = sorted(rng.choice(BASE_WL, n_img, replace=False))
        times = sorted(t0 + timedelta(hours=float(h)) for h in rng.uniform(0, 6 * 24, n_img))
        if asteroid and n == 2:  # images 4-7 taken 40 min apart so an asteroid crosses them
            for j in range(3, 7):
                times[j] = times[3] + timedelta(minutes=40 * (j - 3))
            times = sorted(times)
        frames = []
        for i, (t, wl) in enumerate(zip(times, rng.permutation(wls)), start=1):
            wl = float(round(wl + rng.normal(0, 0.02), 3))
            frames.append(dict(i=i, time=t.replace(microsecond=0), wl=wl,
                               det=detector_for(wl),
                               nan_strip=(i == 2)))
        frames.sort(key=lambda f: f["time"])
        for i, f in enumerate(frames, start=1):
            f["i"] = i
        mid = frames[0]["time"] + (frames[-1]["time"] - frames[0]["time"]) / 2
        visits_meta.append(dict(n=n, frames=frames, start=frames[0]["time"],
                                end=frames[-1]["time"], mid=mid))

    # Fake asteroid: sky positions at the exact times of 4 images in visit 2.
    asteroid_obj = None
    if asteroid:
        v2 = visits_meta[1]["frames"]
        t_ref = v2[3]["time"]
        positions = []
        for f in v2[3:7]:
            dt_min = (f["time"] - t_ref).total_seconds() / 60
            ra, dec = offset_to_sky(-60 + 1.5 * dt_min, 90 - 0.6 * dt_min, ra0, dec0)
            positions.append({"time": iso(f["time"]), "ra": round(ra, 6), "dec": round(dec, 6)})
        asteroid_obj = {"name": "(99999) Fakeasteroid", "label": "(99999) Fakeasteroid (FAKE)",
                        "type": "asteroid", "layer": "asteroids", "positions": positions,
                        "source": "FAKE (JPL SB Ident format)",
                        "url": "https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html"}

    # Per-visit measurement noise, shared by both field sizes (same images).
    meas_noise = {v["n"]: rng.normal(0, 0.08, 2) for v in visits_meta}
    frame_noise = {(v["n"], f["i"]): rng.normal(0, 0.18, 2)
                   for v in visits_meta for f in v["frames"]}
    flux_jitter = {(v["n"], f["i"]): float(rng.normal(1, 0.04))
                   for v in visits_meta for f in v["frames"]}

    def target_px(t, size):
        ra, dec = move(t_ra16, t_dec16, pm[0], pm[1], years_between(t, 2016.0))
        return sky_to_px(ra, dec, ra0, dec0, size)

    def render(size, t, wl_shape_star, wl_shape_bd, noise, extra_flux=1.0):
        img = rng.normal(0, noise, (size, size))
        for s in stars:
            ra, dec = move(s["ra"], s["dec"], s["pmra"], s["pmdec"], years_between(t, 2016.0))
            col, row = sky_to_px(ra, dec, ra0, dec0, size)
            if -3 < col < size + 3 and -3 < row < size + 3:
                img += psf(size, col, row, 10 ** (-0.4 * (s["g"] - 12)) * 0.6 * wl_shape_star)
        col, row = target_px(t, size)
        img += psf(size, col, row, target_flux_22 * wl_shape_bd * extra_flux)
        return img

    for size in sizes:
        fdir = tdir / f"fov{size}"
        (fdir / "frames").mkdir(parents=True, exist_ok=True)
        stacks, stacks_rgb = [], []
        manifest_visits = []
        for v in visits_meta:
            n = v["n"]
            wls = [f["wl"] for f in v["frames"]]
            mean_star = float(np.mean([star_shape(w) for w in wls]))
            mean_bd = float(np.mean([bd_shape(w) for w in wls]))
            stack = render(size, v["mid"], mean_star, mean_bd, 0.004)
            stacks.append(stack)
            # RGB composite: stars identical in all channels (neutral white/gray),
            # the moving dot mostly in red so it shows up with a red tint.
            base = render(size, v["mid"], mean_star, 0.0, 0.004)  # stars + noise, no target
            dot = psf(size, *target_px(v["mid"], size), target_flux_22 * mean_bd)
            stacks_rgb.append(np.stack([base + dot,
                                        base + RGB_TINT_GB * dot,
                                        base + RGB_TINT_GB * dot]))

            ex = target_px(v["mid"], size)
            me = None if saturated else (ex[0] + meas_noise[n][0], ex[1] + meas_noise[n][1])

            frames_out = []
            for f in v["frames"]:
                i = f["i"]
                img = render(size, f["time"], star_shape(f["wl"]), bd_shape(f["wl"]),
                             0.008, flux_jitter[(n, i)])
                flags = np.zeros((size, size, 4), np.uint8)
                # cosmic rays / hot pixels -> orange, blanked to NaN
                hits = rng.random((size, size)) < 0.006
                flags[hits] = (255, 140, 0, 220)
                img[hits] = np.nan
                # "other flagged" -> blue little block
                r0, c0 = rng.integers(2, size - 4, 2)
                flags[r0:r0 + 2, c0:c0 + 3] = (40, 110, 255, 200)
                # saturation -> red on the target when saturated
                if saturated:
                    cc, rr = (int(round(x)) for x in target_px(f["time"], size))
                    flags[max(rr - 1, 0):rr + 2, max(cc - 1, 0):cc + 2] = (255, 0, 0, 230)
                # asteroid only on its individual images
                if asteroid_obj:
                    for p in asteroid_obj["positions"]:
                        if p["time"] == iso(f["time"]):
                            col, row = sky_to_px(p["ra"], p["dec"], ra0, dec0, size)
                            img += psf(size, col, row, 1.2)
                # no-data strip on one image per visit (image edge)
                if f["nan_strip"]:
                    img[:, : max(2, size // 8)] = np.nan
                bad_frac = float(np.mean(flags[..., 3] > 0))

                base = f"frames/v{n}_{i}"
                write_f32(fdir / f"{base}.f32", img)
                finite = img[np.isfinite(img)]
                lo, hi = np.percentile(finite, 50), np.percentile(finite, 99.9)
                write_gray_png(fdir / f"{base}.png", img, lo, hi, alpha_nan=True)
                Image.fromarray(flags, "RGBA").save(fdir / f"{base}_flags.png")

                fex = target_px(f["time"], size)
                fme = None if saturated else (fex[0] + frame_noise[(n, i)][0],
                                              fex[1] + frame_noise[(n, i)][1])
                flux = None if saturated else round(
                    target_flux_22 * bd_shape(f["wl"]) * flux_jitter[(n, i)], 4)
                frames_out.append({
                    "i": i,
                    "image": f"{base}.png",
                    "time": iso(f["time"]),
                    "detector": f["det"],
                    "wavelength_um": f["wl"],
                    "target_expected_px": [r2(fex[0]), r2(fex[1])],
                    "target_measured_px": None if fme is None else [r2(fme[0]), r2(fme[1])],
                    "target_measured_err_px": None if fme is None else [0.2, 0.2],
                    "saturated": saturated,
                    "bad_pixel_fraction": round(bad_frac, 3),
                    "target_flux_mjy": flux,
                    "target_flux_err_mjy": None if flux is None else round(abs(flux) * 0.05 + 0.005, 4),
                    "data": f"{base}.f32",
                    "flags": f"{base}_flags.png",
                    "archive_url": f"https://irsa.ipac.caltech.edu/FAKE/{key}/v{n}_{i}.fits",
                })

            write_f32(fdir / f"visit_{n}.f32", stack)
            manifest_visits.append({
                "n": n,
                "image": f"visit_{n}.png",
                "image_rgb": f"visit_{n}_rgb.png",
                "data": f"visit_{n}.f32",
                "date_start": day(v["start"]), "date_end": day(v["end"]), "date_mid": day(v["mid"]),
                "n_images": len(frames_out),
                "wavelength_um": [0.75, 5.0],
                "target_expected_px": [r2(ex[0]), r2(ex[1])],
                "target_measured_px": None if me is None else [r2(me[0]), r2(me[1])],
                "target_measured_err_px": None if me is None else [0.12, 0.12],
                "saturated": saturated,
                "frames": frames_out,
            })

        # Stacks share one stretch so the blink is fair.
        allv = np.concatenate([s.ravel() for s in stacks])
        lo, hi = np.percentile(allv, 50), np.percentile(allv, 99.9)
        for n, s in enumerate(stacks, start=1):
            write_gray_png(fdir / f"visit_{n}.png", s, lo, hi)
        # RGB composites: same stretch for all channels (and as the gray stacks),
        # so stars stay neutral and the moving dot stays red.
        for n, s in enumerate(stacks_rgb, start=1):
            rgb = np.dstack([(stretch(s[c], lo, hi) * 255).astype(np.uint8) for c in range(3)])
            Image.fromarray(rgb, "RGB").save(fdir / f"visit_{n}_rgb.png")

        if saturated:
            verdict, measured = "saturated", None
        else:
            verdict = "moves_as_expected"
            measured = {"ra": round(pm[0] + float(rng.normal(0, 40))), "ra_err": 90,
                        "dec": round(pm[1] + float(rng.normal(0, 40))), "dec_err": 87}
        write_json(fdir / "manifest.json", {
            "target_key": key,
            "name": name,
            "grid": {"center_ra": ra0, "center_dec": dec0, "center_date": day(CENTER_DATE),
                     "pixel_scale_arcsec": PIX_ARCSEC, "size_px": size},
            "visits": manifest_visits,
            "verdict": verdict,
            "measured_motion_mas_yr": measured,
            "catalog_motion_mas_yr": {"ra": pm[0], "dec": pm[1], "source": "Gaia DR3 (FAKE)"},
        })

    # overlays.json: one file for all field sizes.
    overlays = [{
        "name": f"Gaia DR3 FAKE-{key}", "label": f"{name} (FAKE)", "type": "brown_dwarf",
        "layer": "gaia", "ra": round(t_ra16, 6), "dec": round(t_dec16, 6), "epoch": 2016.0,
        "pmra_mas_yr": pm[0], "pmdec_mas_yr": pm[1], "g_mag": 19.0,
        "source": "Gaia DR3 (FAKE)", "url": "https://simbad.cds.unistra.fr/simbad/",
    }]
    for k, s in enumerate(stars):
        overlays.append({
            "name": f"Gaia DR3 FAKE{k:04d}",
            "label": "Fast fake star (test marker motion)" if s["fast"] else f"Fake star {k}",
            "type": "star", "layer": "gaia",
            "ra": round(s["ra"], 6), "dec": round(s["dec"], 6), "epoch": 2016.0,
            "pmra_mas_yr": round(s["pmra"], 1), "pmdec_mas_yr": round(s["pmdec"], 1),
            "g_mag": round(s["g"], 2), "source": "Gaia DR3 (FAKE)",
            "url": "https://gea.esac.esa.int/archive/",
        })
    # A SIMBAD and a VSX entry to test those toggles (fixed position, epoch 2000).
    ra, dec = offset_to_sky(half * 0.3, -half * 0.4, ra0, dec0)
    overlays.append({"name": "FAKE SIMBAD galaxy", "label": "FAKE G 1", "type": "galaxy",
                     "layer": "simbad", "ra": round(ra, 6), "dec": round(dec, 6), "epoch": 2000.0,
                     "pmra_mas_yr": None, "pmdec_mas_yr": None, "g_mag": None,
                     "source": "SIMBAD (FAKE)", "url": "https://simbad.cds.unistra.fr/simbad/"})
    s = stars[3]
    overlays.append({"name": "FAKE VSX variable", "label": "FAKE V1 (Mira, P=245 d)",
                     "type": "variable_star", "layer": "vsx", "ra": round(s["ra"], 6),
                     "dec": round(s["dec"], 6), "epoch": 2016.0, "pmra_mas_yr": round(s["pmra"], 1),
                     "pmdec_mas_yr": round(s["pmdec"], 1), "g_mag": round(s["g"], 2),
                     "source": "VSX (FAKE)", "url": "https://vsx.aavso.org"})
    if asteroid_obj:
        overlays.append(asteroid_obj)
    write_json(tdir / "overlays.json", overlays)


# ---------------------------------------------------------------- shared files
TYPES = ["star", "brown_dwarf", "variable_star", "galaxy", "asteroid", "young_star", "unknown"]
VERDICTS = ["moves_as_expected", "moves_unexpected", "no_motion_detected",
            "brightness_changes", "saturated", "too_faint"]
TARGETS = {"epsilon_indi_b": "Epsilon Indi B", "barnards_star": "Barnard's Star",
           "r_draconis": "R Draconis", "rw_aurigae": "RW Aurigae", "wise_0855": "WISE 0855",
           "fake_saturated": "Fake: saturated star"}


def make_shared(out):
    ph = lambda title: {"title": title,
                        "text": f"PLACEHOLDER text about {title.lower()}. Amna replaces this with "
                                "two to four sourced sentences.",
                        "sources": [{"label": "FAKE source", "url": "https://example.org"}]}
    write_json(out / "explanations.json", {
        "types": {t: ph(t.replace("_", " ").capitalize()) for t in TYPES},
        "verdicts": {v: ph(v.replace("_", " ").capitalize()) for v in VERDICTS},
        "targets": {k: ph(n) for k, n in TARGETS.items()},
        "about": {"how_it_works": ph("How this works"),
                  "limits": ph("What this tool can't tell you")},
    })
    write_json(out / "credits.json", [
        {"what": w, "text": f"PLACEHOLDER: exact acknowledgement wording requested by {w}.",
         "url": "https://example.org"}
        for w in ["SPHEREx images (IRSA)", "Gaia DR3", "SIMBAD", "VSX (AAVSO)",
                  "CatWISE2020", "JPL Small-Body Identification"]])

    sp = out / "spectra"
    sp.mkdir(parents=True, exist_ok=True)
    grid = np.round(np.arange(0.75, 5.001, 0.05), 3)
    for fname, fn, src, stop in [("star_g.csv", star_shape, "FAKE G star", 5.0),
                                 ("star_m.csv", lambda w: (w / 2.2) ** -1.0, "FAKE M star", 5.0),
                                 ("brown_dwarf_t.csv", bd_shape, "FAKE T dwarf", 5.0),
                                 ("brown_dwarf_l.csv", lambda w: (w / 2.2) ** -0.3, "FAKE L dwarf", 2.5),
                                 ("galaxy.csv", lambda w: (w / 2.2) ** -0.6, "FAKE galaxy", 5.0)]:
        rows = ["wavelength_um,flux_norm,source"]
        rows += [f"{w},{fn(w):.4f},{src}" for w in grid if w <= stop]  # L file stops early on purpose
        (sp / fname).write_text("\n".join(rows) + "\n")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    default_out = Path(__file__).resolve().parent.parent / "fake_data"  # repo/fake_data, next to site/
    ap.add_argument("--out", default=str(default_out))
    args = ap.parse_args()
    out = Path(args.out).resolve()
    # The output folder is deleted and rebuilt, so refuse anything that holds real work:
    # the team's data/ folder, a folder containing it (the repo), or the site itself.
    if out.name == "data" or (out / "data").is_dir() or (out / ".git").exists() or (out / "index.html").exists():
        raise SystemExit(f"Refusing to write to {out}: it is (or contains) real files. Use the default fake_data/.")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # Epsilon Indi B: real field center from the plan, Gaia-like motion (east + south).
    make_target(out, "epsilon_indi_b", "Epsilon Indi B", 331.096653, -56.800663,
                (3982.0, -2467.0), target_flux_22=2.0, sizes=[51, 101], asteroid=True)
    # Saturated test target: Barnard's Star center, only size 51 (tests fields.json).
    # Fake-only targets start with "fake_" (team rule in PROJECT_STRUCTURE.md).
    make_target(out, "fake_saturated", "Fake: saturated star", 269.446268, 4.768204,
                (-802.8, 10362.4), target_flux_22=400.0, sizes=[51], saturated=True)
    make_shared(out)
    n_files = sum(1 for p in out.rglob("*") if p.is_file())
    print(f"Wrote {n_files} fake files to {out.resolve()}")


if __name__ == "__main__":
    main()