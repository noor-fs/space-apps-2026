"""Build data/scoreboard.json: how well our SPHEREx measurements agree with what catalogs predict.

Reads only finished files in data/ (it never queries an archive):
  data/<target>/fields.json
  data/<target>/fov<S>/manifest.json      (Yara T)  target expected vs measured, motion, verdict
  data/<target>/fov<S>/objects.json       (Yara T)  optional: every catalog star, expected vs measured
  data/<target>/fov<S>/candidates.json    (Sifna)   optional: detections with no catalog match

Writes:
  data/scoreboard.json                    read by the site
  scoring/figures/*.png                   optional plots for the demo (--plot)

Three checks, each answering "is the tool telling the truth?":

1. Motion check (per target). The measured proper motion is compared with the catalog
   motion. z = (measured - catalog) / measured_error on each axis, and the two axes are
   combined into one chi-square with 2 degrees of freedom. The catalog error is ignored
   because Gaia's is far smaller than ours.
     agrees     p > 0.05
     tension    0.003 < p <= 0.05
     disagrees  p <= 0.003   (the usual "3 sigma" line)

2. Position check (per single image of the target). For every image where the target was
   measured: offset = measured - expected, per axis, in pixels. It is split in two:
     constant offset  the mean offset over all images. A small fixed shift between SPHEREx
                      and catalog positions (absolute registration, or an unresolved
                      companion) moves every image equally, so it cannot fake motion.
     random part      each image's offset minus its visit's mean, divided by its error.
                      If our error bars are honest, about 68% fall within 1 and about 95%
                      within 2, and the rms is near 1.
   Raw pulls (without removing the constant offset) are kept too, for transparency.

3. Field-star check (only when objects.json exists). The same pull test on every catalog
   star in the field, skipping stars used to calibrate the errors ("reference": true),
   because testing on them would be circular, and stars with a close neighbour
   ("isolated": false), because a neighbour pulls the measurement.

Run from the repo root:
  python scoring/build_scoreboard.py            # all targets, all field sizes
  python scoring/build_scoreboard.py --plot     # also write PNGs to scoring/figures/
"""

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FIGURES = Path(__file__).resolve().parent / "figures"

# Order shown on the site; keys match the Saturday plan.
TARGET_ORDER = ["epsilon_indi_b", "barnards_star", "rw_aurigae", "wise_0855", "r_draconis"]

P_AGREE = 0.05
P_DISAGREE = 0.0027  # two-sided 3 sigma for one Gaussian variable


# ---------- small helpers ----------

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def chi2_p_2dof(chi2):
    """Probability of a chi-square at least this large with 2 degrees of freedom."""
    return math.exp(-chi2 / 2.0)


def agreement_label(p):
    if p is None:
        return None
    if p > P_AGREE:
        return "agrees"
    if p > P_DISAGREE:
        return "tension"
    return "disagrees"


def pull_summary(pulls):
    """Summarise a list of pulls (one number per axis per measurement)."""
    pulls = [p for p in pulls if p is not None and math.isfinite(p)]
    n = len(pulls)
    if n == 0:
        return None
    within = lambda k: sum(1 for p in pulls if abs(p) <= k) / n
    mean = sum(pulls) / n
    rms = math.sqrt(sum(p * p for p in pulls) / n)
    return {
        "n": n,
        "within_1sigma": round(within(1), 3),   # honest errors give about 0.683
        "within_2sigma": round(within(2), 3),   # about 0.954
        "within_3sigma": round(within(3), 3),   # about 0.997
        "mean_pull": round(mean, 3),            # near 0 means no systematic offset
        "rms_pull": round(rms, 3),              # near 1 means error bars are the right size
    }


def pulls_from(expected, measured, err):
    """Pulls on both axes for one measurement, or [] if anything is missing."""
    if not expected or not measured or not err:
        return []
    out = []
    for e, m, s in zip(expected, measured, err):
        if e is None or m is None or not s:
            continue
        out.append((m - e) / s)
    return out


def years_between(a, b):
    da = datetime.fromisoformat(a.replace("Z", "+00:00"))
    db = datetime.fromisoformat(b.replace("Z", "+00:00"))
    return abs((db - da).total_seconds()) / (365.25 * 86400)


# ---------- check 1: motion ----------

def motion_check(manifest):
    meas = manifest.get("measured_motion_mas_yr")
    cat = manifest.get("catalog_motion_mas_yr")
    if not meas or not cat:
        return None

    out = {
        "measured_mas_yr": {"ra": meas.get("ra"), "ra_err": meas.get("ra_err"),
                            "dec": meas.get("dec"), "dec_err": meas.get("dec_err")},
        "catalog_mas_yr": {"ra": cat.get("ra"), "dec": cat.get("dec"),
                           "source": cat.get("source")},
    }

    z = {}
    for axis in ("ra", "dec"):
        m, e, c = meas.get(axis), meas.get(f"{axis}_err"), cat.get(axis)
        z[axis] = (m - c) / e if None not in (m, e, c) and e > 0 else None
    out["z"] = {k: (round(v, 2) if v is not None else None) for k, v in z.items()}

    if None not in z.values():
        chi2 = z["ra"] ** 2 + z["dec"] ** 2
        p = chi2_p_2dof(chi2)
        out["chi2_2dof"] = round(chi2, 2)
        out["p_value"] = round(p, 3)
        out["agreement"] = agreement_label(p)
    else:
        out["chi2_2dof"] = out["p_value"] = out["agreement"] = None

    # Total speed on the sky, measured vs catalog, and how far that moves the star.
    if None not in (meas.get("ra"), meas.get("dec"), cat.get("ra"), cat.get("dec")):
        speed_meas = math.hypot(meas["ra"], meas["dec"])
        speed_cat = math.hypot(cat["ra"], cat["dec"])
        out["speed_measured_mas_yr"] = round(speed_meas)
        out["speed_catalog_mas_yr"] = round(speed_cat)
        # A percentage is meaningless for stars that barely move (e.g. RW Aurigae).
        err = math.hypot(meas.get("ra_err") or 0, meas.get("dec_err") or 0)
        if speed_cat > 5 * err:
            out["speed_difference_percent"] = round(100 * (speed_meas - speed_cat) / speed_cat, 1)
        else:
            out["speed_difference_percent"] = None

        visits = manifest.get("visits", [])
        dates = [v["date_mid"] for v in visits if v.get("date_mid")]
        if len(dates) >= 2:
            baseline = years_between(min(dates), max(dates))
            scale_mas = manifest["grid"]["pixel_scale_arcsec"] * 1000
            out["baseline_years"] = round(baseline, 2)
            out["shift_over_baseline_px"] = round(speed_cat * baseline / scale_mas, 2)
    return out


# ---------- check 2: target position in every image ----------

def position_check(manifest):
    scale = manifest["grid"]["pixel_scale_arcsec"]
    raw_pulls, random_pulls, offsets = [], [], []
    n_images = n_measured = n_saturated = 0
    for visit in manifest.get("visits", []):
        rows = []
        for frame in visit.get("frames", []):
            n_images += 1
            if frame.get("saturated"):
                n_saturated += 1
            e, m, s_ = (frame.get("target_expected_px"), frame.get("target_measured_px"),
                        frame.get("target_measured_err_px"))
            if not (e and m and s_) or None in (*e, *m) or not all(s_):
                continue
            n_measured += 1
            d = [m[0] - e[0], m[1] - e[1]]
            rows.append((d, s_))
            offsets.append(d)
            raw_pulls.extend([d[0] / s_[0], d[1] / s_[1]])
        if len(rows) >= 2:
            mean = [sum(r[0][k] for r in rows) / len(rows) for k in (0, 1)]
            for d, s_ in rows:
                random_pulls.extend([(d[0] - mean[0]) / s_[0], (d[1] - mean[1]) / s_[1]])

    constant = None
    if offsets:
        mx = sum(o[0] for o in offsets) / len(offsets)
        my = sum(o[1] for o in offsets) / len(offsets)
        constant = {
            "px": [round(mx, 3), round(my, 3)],
            "arcsec": round(math.hypot(mx, my) * scale, 2),
            "fraction_of_pixel": round(math.hypot(mx, my), 3),
        }
    return {
        "n_images": n_images,
        "n_measured": n_measured,
        "n_saturated": n_saturated,
        "constant_offset": constant,
        "random_pulls": pull_summary(random_pulls),
        "raw_pulls": pull_summary(raw_pulls),
    }, random_pulls


# ---------- check 3: every catalog star in the field ----------

def field_star_check(objects):
    """Pull test on catalog stars from objects.json (Yara T's draft shape)."""
    used, skipped_reference, skipped_blended, not_detected = 0, 0, 0, 0
    pulls = []
    for obj in objects:
        if obj.get("catalog") is None:
            continue  # unidentified detections belong to candidates.json, not here
        if obj.get("reference") is True:
            skipped_reference += 1
            continue
        if obj.get("isolated") is False:
            skipped_blended += 1
            continue
        if obj.get("detected") is False:
            not_detected += 1
            continue
        star_pulls = []
        for v in obj.get("visits", []):
            star_pulls.extend(pulls_from(v.get("expected_px"), v.get("measured_px"),
                                         v.get("measured_err_px")))
        if star_pulls:
            used += 1
            pulls.extend(star_pulls)
    has_reference_flag = any("reference" in o for o in objects)
    return {
        "n_stars_used": used,
        "n_skipped_reference": skipped_reference,
        "n_skipped_blended": skipped_blended,
        "n_not_detected": not_detected,
        "reference_flag_present": has_reference_flag,
        "pulls": pull_summary(pulls),
    }, pulls


def candidate_summary(candidates):
    labels = {}
    for c in candidates:
        label = c.get("label", "unlabelled")
        labels[label] = labels.get(label, 0) + 1
    return {"n_candidates": len(candidates), "by_label": labels}


# ---------- one target ----------

def score_field(target_key, size):
    folder = DATA / target_key / f"fov{size}"
    manifest_path = folder / "manifest.json"
    if not manifest_path.exists():
        return None, {}
    manifest = load_json(manifest_path)

    motion = motion_check(manifest)
    position, target_pulls = position_check(manifest)
    entry = {
        "target_key": target_key,
        "name": manifest.get("name", target_key),
        "field_size_px": size,
        "verdict": manifest.get("verdict"),
        "motion": motion,
        "target_position": position,
        "field_stars": None,
        "candidates": None,
    }
    raw = {"target_pulls": target_pulls}

    objects_path = folder / "objects.json"
    if objects_path.exists():
        entry["field_stars"], raw["star_pulls"] = field_star_check(load_json(objects_path))
    candidates_path = folder / "candidates.json"
    if candidates_path.exists():
        entry["candidates"] = candidate_summary(load_json(candidates_path))
    return entry, raw


def field_sizes(target_key):
    fields_path = DATA / target_key / "fields.json"
    if not fields_path.exists():
        return []
    return load_json(fields_path).get("sizes_px", [])


# ---------- headline ----------

def headline(targets, all_star_pulls):
    lines = []
    with_motion = [t for t in targets if t["motion"] and t["motion"].get("agreement")]
    if with_motion:
        agree = sum(1 for t in with_motion if t["motion"]["agreement"] == "agrees")
        lines.append(f"Measured motion agrees with the catalog for {agree} of "
                     f"{len(with_motion)} targets (95% level).")
    total_images = sum(t["target_position"]["n_measured"] for t in targets)
    if total_images:
        lines.append(f"Target position measured in {total_images} single SPHEREx images.")
    rnd = [t["target_position"]["random_pulls"] for t in targets if t["target_position"]["random_pulls"]]
    if rnd:
        n = sum(r["n"] for r in rnd)
        within2 = sum(r["within_2sigma"] * r["n"] for r in rnd) / n
        lines.append(f"Error bars: {round(100 * within2)}% of image-to-image scatter falls "
                     f"within 2 sigma (95% if the error bars are exactly right).")
    offs = [t["target_position"]["constant_offset"]["arcsec"] for t in targets
            if t["target_position"]["constant_offset"]]
    if offs:
        lines.append(f"Positions sit within {max(offs)} arcsec of the catalog "
                     f"(about {round(max(offs) / 6.15, 2)} of a pixel).")
    star_summary = pull_summary(all_star_pulls)
    if star_summary:
        lines.append(f"Field stars: {round(100 * star_summary['within_2sigma'])}% of "
                     f"{star_summary['n']} position checks fall within 2 sigma of the "
                     f"catalog prediction (95% expected).")
    return lines


# ---------- plots ----------

def write_plots(targets, raw_by_target):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURES.mkdir(parents=True, exist_ok=True)

    # 1. Measured vs catalog motion, one panel per target.
    with_motion = [t for t in targets if t["motion"] and t["motion"].get("z")]
    if with_motion:
        fig, axes = plt.subplots(1, len(with_motion), figsize=(4 * len(with_motion), 4),
                                 squeeze=False)
        for ax, t in zip(axes[0], with_motion):
            m, c = t["motion"]["measured_mas_yr"], t["motion"]["catalog_mas_yr"]
            ax.errorbar([m["ra"]], [m["dec"]], xerr=[m["ra_err"]], yerr=[m["dec_err"]],
                        fmt="o", color="#3987e5", label="SPHEREx (ours)")
            ax.plot([c["ra"]], [c["dec"]], "x", color="#d95926", markersize=10,
                    label=c.get("source") or "catalog")
            pad = 4 * max(m["ra_err"], m["dec_err"])
            ax.set_xlim(c["ra"] - pad, c["ra"] + pad)
            ax.set_ylim(c["dec"] - pad, c["dec"] + pad)
            ax.set_title(f'{t["name"]}\n{t["motion"]["agreement"]} (p = {t["motion"]["p_value"]})')
            ax.set_xlabel("motion east (mas/yr)")
            ax.set_ylabel("motion north (mas/yr)")
            ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(FIGURES / "motion_vs_catalog.png", dpi=150)
        plt.close(fig)

    # 2. Pull histogram against the bell curve honest errors should give.
    pulls = [p for raw in raw_by_target.values() for p in raw.get("star_pulls", []) or raw["target_pulls"]]
    pulls = [p for p in pulls if math.isfinite(p) and abs(p) < 8]
    if pulls:
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.hist(pulls, bins=40, range=(-6, 6), density=True, color="#3987e5", alpha=0.7,
                label="our measurements")
        xs = [x / 20 for x in range(-120, 121)]
        ax.plot(xs, [math.exp(-x * x / 2) / math.sqrt(2 * math.pi) for x in xs],
                color="#d95926", label="expected if errors are honest")
        ax.set_xlabel("image-to-image scatter / error")
        ax.set_ylabel("fraction")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(FIGURES / "position_pulls.png", dpi=150)
        plt.close(fig)


# ---------- main ----------

def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--plot", action="store_true", help="also write PNGs to scoring/figures/")
    args = parser.parse_args()

    keys = [k for k in TARGET_ORDER if (DATA / k).is_dir()]
    keys += sorted(p.name for p in DATA.iterdir()
                   if p.is_dir() and p.name not in TARGET_ORDER and p.name != "spectra")

    targets, raw_by_target, all_star_pulls = [], {}, []
    for key in keys:
        sizes = field_sizes(key)
        # Score the largest field that has a manifest: more stars, same target.
        for size in sorted(sizes, reverse=True):
            entry, raw = score_field(key, size)
            if entry:
                targets.append(entry)
                raw_by_target[key] = raw
                all_star_pulls.extend(raw.get("star_pulls", []))
                break

    scoreboard = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": {
            "motion": "z = (measured - catalog) / measured error per axis; chi-square with 2 "
                      "degrees of freedom; agrees if p > 0.05, disagrees if p <= 0.0027.",
            "position": "offset = measured - expected per image, split into a constant "
                        "offset (mean over all images) and a random part (offset minus its "
                        "visit's mean, divided by its error); honest errors put 68% of the "
                        "random part within 1 and 95% within 2.",
            "field_stars": "same pull test on catalog stars, excluding calibration "
                           "(reference) stars and stars with close neighbours.",
        },
        "headline": headline(targets, all_star_pulls),
        "targets": targets,
        "field_stars_all": pull_summary(all_star_pulls),
    }

    out = DATA / "scoreboard.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(scoreboard, f, indent=1)
        f.write("\n")
    print(f"wrote {out.relative_to(ROOT)}")
    for line in scoreboard["headline"]:
        print("  " + line)
    for t in targets:
        m = t["motion"] or {}
        p = t["target_position"]["random_pulls"] or {}
        c = t["target_position"]["constant_offset"] or {}
        print(f"  {t['name']:16s} verdict={t['verdict']:20s} motion={m.get('agreement')} "
              f"z={m.get('z')} speed_diff={m.get('speed_difference_percent')}% "
              f"random within 2 sigma={p.get('within_2sigma')} rms={p.get('rms_pull')} "
              f"offset={c.get('arcsec')}\"")

    if args.plot:
        write_plots(targets, raw_by_target)
        print(f"wrote plots to {FIGURES.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
