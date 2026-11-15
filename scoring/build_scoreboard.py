"""Build data/scoreboard.json: does SPHEREx, measured by our tool, agree with what the catalogs
predict, and are our error bars honest?

Spec: team_update_2026-11-15.md, section "Noor: scoring". Reads only finished files in data/
(it never queries an archive), so re-run it whenever someone pushes new target files:

  data/<target>/fields.json
  data/<target>/fov<S>/manifest.json   (Yara T)  target: expected vs measured, motion, verdict
  data/<target>/fov<S>/objects.json    (Yara T)  every measurable Gaia star in the field

Writes:
  data/scoreboard.json                 read by the site ("How accurate is this?" panel and
                                       field-star hover text)
  scoring/figures/*.png                with --plot, for the demo

Check 1, target motion. Measured motion vs catalog motion, per axis:
  z = (measured - catalog) / error, error = sqrt(measured_err^2 + catalog_err^2)
  (the catalog error counts as 0 when the manifest doesn't give one; Gaia's is tiny).
  chi2 = z_ra^2 + z_dec^2 with 2 degrees of freedom gives p:
    agrees     p >= 0.05
    tension    0.0027 <= p < 0.05
    disagrees  p < 0.0027  (3 sigma, the threshold our verdicts use)
  Targets without a measured motion (R Draconis) are "not_measurable", not failures.

Check 2, target error bars. For every single image and every visit with a measured position:
  pull = (measured - expected) / error, per axis.
  Honest error bars put about 68% of pulls within 1 and 95% within 2. A constant offset
  (the same shift in every image: absolute registration, or an unresolved binary whose
  catalog position isn't its light center, like Epsilon Indi B) is reported separately,
  and the image pulls are also given with each visit's mean removed ("random part"),
  which isolates the error bars from that offset.

Check 3, field stars (objects.json). Stars nobody tuned the tool on:
  scored     reference false, blended_with empty, visits with saturated false and a
             measured position
  reference  scored the same way but reported separately: they set the error bars, so
             they agree by construction (a sanity check, not evidence)
  recovered  measured in at least one visit, split by Gaia G (<14, 14-16, 16-17)
  per object chi2 = sum of squared pulls over its usable visits, both axes, with
             2 x (number of visits) degrees of freedom, same three labels as check 1.
  Objects that disagree are listed by name: known stars not doing what Gaia predicts.

Not scored: field-star brightness, objects in no catalog, R Draconis motion (saturated).

Run from the repo root:
  python scoring/build_scoreboard.py
  python scoring/build_scoreboard.py --plot
"""

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FIGURES = Path(__file__).resolve().parent / "figures"

TARGET_ORDER = ["epsilon_indi_b", "barnards_star", "rw_aurigae", "wise_0855", "r_draconis"]

P_AGREE = 0.05
P_DISAGREE = 0.0027  # two-sided 3 sigma, the same threshold as the verdicts
G_BINS = [("G < 14", None, 14.0), ("G 14-16", 14.0, 16.0), ("G 16-17", 16.0, None)]


# ---------- helpers ----------

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def agreement_label(p):
    if p is None:
        return None
    if p >= P_AGREE:
        return "agrees"
    if p >= P_DISAGREE:
        return "tension"
    return "disagrees"


def chi2_p(chi2, dof):
    return float(stats.chi2.sf(chi2, dof))


def usable(e, m, s):
    """True if expected, measured and error are all present and the errors are positive."""
    return (e is not None and m is not None and s is not None
            and None not in (*e, *m, *s) and s[0] > 0 and s[1] > 0)


def pulls_of(e, m, s):
    return [(m[0] - e[0]) / s[0], (m[1] - e[1]) / s[1]]


def pull_summary(pulls):
    """Share of pulls within 1, 2 and 3 sigma, plus their mean and rms."""
    pulls = [p for p in pulls if math.isfinite(p)]
    n = len(pulls)
    if n == 0:
        return None
    share = lambda k: sum(1 for p in pulls if abs(p) <= k) / n
    rms = math.sqrt(sum(p * p for p in pulls) / n)
    return {
        "n": n,
        "within_1sigma": round(share(1), 3),
        "within_2sigma": round(share(2), 3),
        "within_3sigma": round(share(3), 3),
        "mean_pull": round(sum(pulls) / n, 3),   # near 0: no systematic shift
        "rms_pull": round(rms, 3),               # near 1: error bars the right size
    }


def error_bar_assessment(summary):
    """One plain phrase about the error bars, from a pull summary."""
    if not summary or summary["n"] < 10:
        return None
    rms = summary["rms_pull"]
    if 0.9 <= rms <= 1.1:
        return "about right"
    if rms > 1.1:
        size = "slightly too small" if rms < 1.6 else "too small"
        return f"{size} (real scatter is about {rms:.1f}x the error bar)"
    return "slightly too large (conservative)"


def years_between(a, b):
    da = datetime.fromisoformat(a.replace("Z", "+00:00"))
    db = datetime.fromisoformat(b.replace("Z", "+00:00"))
    return abs((db - da).total_seconds()) / (365.25 * 86400)


# ---------- check 1: target motion ----------

def motion_check(manifest):
    meas = manifest.get("measured_motion_mas_yr")
    cat = manifest.get("catalog_motion_mas_yr")
    verdict = manifest.get("verdict")
    if not cat or not meas or meas.get("ra") is None or meas.get("dec") is None:
        reason = ("saturated" if verdict == "saturated" else
                  "too faint" if verdict == "too_faint" else
                  "no catalog motion" if not cat else "not measured")
        return {"agreement": "not_measurable", "reason": reason,
                "catalog_mas_yr": cat or None}

    z = {}
    for axis in ("ra", "dec"):
        err = math.hypot(meas[f"{axis}_err"], cat.get(f"{axis}_err") or 0.0)
        z[axis] = (meas[axis] - cat[axis]) / err
    chi2 = z["ra"] ** 2 + z["dec"] ** 2
    p = chi2_p(chi2, 2)
    out = {
        "measured_mas_yr": {k: meas.get(k) for k in ("ra", "ra_err", "dec", "dec_err")},
        "catalog_mas_yr": {k: cat.get(k) for k in ("ra", "ra_err", "dec", "dec_err", "source")},
        "catalog_error_included": bool(cat.get("ra_err") or cat.get("dec_err")),
        "z": {k: round(v, 2) for k, v in z.items()},
        "chi2_2dof": round(chi2, 2),
        "p_value": round(p, 3),
        "agreement": agreement_label(p),
    }

    speed_meas = math.hypot(meas["ra"], meas["dec"])
    speed_cat = math.hypot(cat["ra"], cat["dec"])
    out["speed_measured_mas_yr"] = round(speed_meas)
    out["speed_catalog_mas_yr"] = round(speed_cat)
    speed_err = math.hypot(meas["ra_err"], meas["dec_err"])
    # A percentage only means something for a target that clearly moves.
    out["speed_difference_percent"] = (round(100 * (speed_meas - speed_cat) / speed_cat, 1)
                                       if speed_cat > 5 * speed_err else None)

    dates = [v["date_mid"] for v in manifest.get("visits", []) if v.get("date_mid")]
    if len(dates) >= 2:
        baseline = years_between(min(dates), max(dates))
        out["baseline_years"] = round(baseline, 2)
        out["shift_over_baseline_px"] = round(
            speed_cat * baseline / (manifest["grid"]["pixel_scale_arcsec"] * 1000), 2)
    return out


# ---------- check 2: target error bars ----------

def target_position_check(manifest):
    scale = manifest["grid"]["pixel_scale_arcsec"]
    image_pulls, random_pulls, visit_pulls, offsets, visit_rows = [], [], [], [], []
    n_images = n_measured = n_saturated = 0
    for visit in manifest.get("visits", []):
        rows = []
        for frame in visit.get("frames", []):
            n_images += 1
            e, m, s = (frame.get("target_expected_px"), frame.get("target_measured_px"),
                       frame.get("target_measured_err_px"))
            if not usable(e, m, s):
                continue
            n_measured += 1
            n_saturated += bool(frame.get("saturated"))
            d = [m[0] - e[0], m[1] - e[1]]
            rows.append((d, s))
            offsets.append(d)
            image_pulls.extend(pulls_of(e, m, s))
        if len(rows) >= 2:
            mean = [sum(r[0][k] for r in rows) / len(rows) for k in (0, 1)]
            for d, s in rows:
                random_pulls.extend([(d[0] - mean[0]) / s[0], (d[1] - mean[1]) / s[1]])
        e, m, s = (visit.get("target_expected_px"), visit.get("target_measured_px"),
                   visit.get("target_measured_err_px"))
        if usable(e, m, s):
            visit_pulls.extend(pulls_of(e, m, s))
            visit_rows.append(([m[0] - e[0], m[1] - e[1]], s))
            if not rows:  # visit-only measurements (WISE 0855) still count toward the offset
                offsets.append([m[0] - e[0], m[1] - e[1]])

    constant = None
    if offsets:
        mx = sum(o[0] for o in offsets) / len(offsets)
        my = sum(o[1] for o in offsets) / len(offsets)
        constant = {"px": [round(mx, 3), round(my, 3)],
                    "arcsec": round(math.hypot(mx, my) * scale, 2),
                    "fraction_of_pixel": round(math.hypot(mx, my), 3)}
    visit_offset_removed = []
    if len(visit_rows) >= 2:
        vx = sum(r[0][0] for r in visit_rows) / len(visit_rows)
        vy = sum(r[0][1] for r in visit_rows) / len(visit_rows)
        for d, s_ in visit_rows:
            visit_offset_removed.extend([(d[0] - vx) / s_[0], (d[1] - vy) / s_[1]])
    random_summary = pull_summary(random_pulls)
    return {
        "n_images": n_images,
        "n_images_measured": n_measured,
        "n_images_measured_saturated": n_saturated,
        "image_pulls": pull_summary(image_pulls),
        "random_part": random_summary,
        "visit_pulls": pull_summary(visit_pulls),
        # Visit positions after removing the constant offset: tests the visit error bars
        # (which include the shared per-visit error) without the catalog/registration shift.
        "visit_pulls_offset_removed": pull_summary(visit_offset_removed),
        "constant_offset": constant,
        "error_bars": error_bar_assessment(random_summary),
    }, random_pulls


# ---------- check 3: field stars ----------

def g_bin(g):
    for label, lo, hi in G_BINS:
        if (lo is None or g >= lo) and (hi is None or g < hi):
            return label
    return G_BINS[-1][0]


def score_object(obj):
    """Usable visits, pulls and agreement for one object from objects.json."""
    pulls, n_visits, n_measured_any = [], 0, 0
    for v in obj.get("visits", []):
        e, m, s = v.get("expected_px"), v.get("measured_px"), v.get("measured_err_px")
        if m is not None:
            n_measured_any += 1
        if v.get("saturated") or not usable(e, m, s):
            continue
        n_visits += 1
        pulls.extend(pulls_of(e, m, s))
    chi2 = sum(p * p for p in pulls)
    p = chi2_p(chi2, 2 * n_visits) if n_visits else None
    return {
        "pulls": pulls,
        "n_visits": n_visits,
        "recovered": n_measured_any > 0,
        "chi2": round(chi2, 2) if n_visits else None,
        "dof": 2 * n_visits,
        "p_value": round(p, 4) if p is not None else None,
        "agreement": agreement_label(p),
    }


def field_star_check(objects_file):
    objects = objects_file.get("objects", [])
    scored_pulls, reference_pulls, rows = [], [], []
    recovered = {label: [0, 0] for label, _, _ in G_BINS}
    counts = {"in_file": len(objects), "scored": 0, "reference": 0, "blended": 0,
              "no_usable_visit": 0}

    for obj in objects:
        r = score_object(obj)
        b = g_bin(obj.get("g_mag", 99))
        recovered[b][1] += 1
        recovered[b][0] += r["recovered"]

        if obj.get("reference"):
            role = "reference"
            counts["reference"] += 1
            reference_pulls.extend(r["pulls"])
        elif obj.get("blended_with"):
            role = "blended"
            counts["blended"] += 1
        elif r["n_visits"] == 0:
            role = "not_scored"
            counts["no_usable_visit"] += 1
        else:
            role = "scored"
            counts["scored"] += 1
            scored_pulls.extend(r["pulls"])

        rows.append({
            "name": obj.get("name"),
            "agreement": r["agreement"],   # null if no usable visit
            "chi2": r["chi2"],
            "n_visits": r["n_visits"],
            "dof": r["dof"],
            "p_value": r["p_value"],
            "g_mag": obj.get("g_mag"),
            "role": role,                  # scored, reference, blended, not_scored
        })

    scored_summary = pull_summary(scored_pulls)
    scored_rows = [x for x in rows if x["role"] == "scored"]
    return {
        "counts": counts,
        "recovered_by_g": {k: {"recovered": v[0], "total": v[1]}
                           for k, v in recovered.items() if v[1]},
        "pulls_scored": scored_summary,
        "pulls_reference": pull_summary(reference_pulls),
        "error_bars": error_bar_assessment(scored_summary),
        "agreement_counts": {lab: sum(1 for x in scored_rows if x["agreement"] == lab)
                             for lab in ("agrees", "tension", "disagrees")},
        "disagreeing": [x["name"] for x in scored_rows if x["agreement"] == "disagrees"],
        "objects": rows,
    }, scored_pulls, rows


# ---------- one target ----------

def field_sizes(key):
    path = DATA / key / "fields.json"
    return load_json(path).get("sizes_px", []) if path.exists() else []


def score_target(key):
    # Score the largest field that has a manifest.
    for size in sorted(field_sizes(key), reverse=True):
        folder = DATA / key / f"fov{size}"
        if not (folder / "manifest.json").exists():
            continue
        manifest = load_json(folder / "manifest.json")
        position, random_pulls = target_position_check(manifest)
        entry = {
            "target_key": key,
            "name": manifest.get("name", key),
            "field_size_px": size,
            "verdict": manifest.get("verdict"),
            "motion": motion_check(manifest),
            "target_position": position,
            "field_stars": None,
        }
        raw = {"random_pulls": random_pulls, "star_pulls": [], "star_rows": []}
        if (folder / "objects.json").exists():
            entry["field_stars"], raw["star_pulls"], raw["star_rows"] = \
                field_star_check(load_json(folder / "objects.json"))
        return entry, raw
    return None, None


# ---------- headline sentences for the site ----------

def pct(x):
    return f"{round(100 * x)}%"


def headline(targets, star_pulls, star_rows):
    lines = []

    measurable = [t for t in targets if t["motion"]["agreement"] != "not_measurable"]
    if measurable:
        agree = sum(1 for t in measurable if t["motion"]["agreement"] == "agrees")
        line = (f"Motion: {agree} of {len(measurable)} measurable targets move as the "
                f"catalogs predict.")
        skipped = [f'{t["name"]} ({t["motion"]["reason"]})' for t in targets
                   if t["motion"]["agreement"] == "not_measurable"]
        if skipped:
            line += " Not measurable: " + ", ".join(skipped) + "."
        lines.append(line)

    star_summary = pull_summary(star_pulls)
    scored = [r for r in star_rows if r["role"] == "scored"]
    if scored and star_summary:
        n_fields = sum(1 for t in targets if t["field_stars"])
        count = lambda lab: sum(1 for r in scored if r["agreement"] == lab)
        recovered = sum(1 for r in star_rows if r["n_visits"] > 0 or r["role"] == "blended")
        lines.append(
            f"Other stars: of {len(scored)} Gaia stars the tool was not tuned on, "
            f"{count('agrees')} agree with Gaia, {count('tension')} "
            f"{'shows' if count('tension') == 1 else 'show'} mild tension and "
            f"{count('disagrees')} disagree{'s' if count('disagrees') == 1 else ''} ({n_fields} field{'s' if n_fields != 1 else ''} "
            f"so far; {recovered} of {len(star_rows)} Gaia stars down to G = 17 recovered).")
        lines.append(
            f"Error bars: {pct(star_summary['within_1sigma'])} of their positions fall within "
            f"1 error bar and {pct(star_summary['within_2sigma'])} within 2 (honest error bars "
            f"give 68% and 95%), so our error bars are {error_bar_assessment(star_summary)}.")

    # Only targets whose motion is measurable: a few saturated images (R Draconis) don't
    # give a meaningful offset.
    offsets = [t["target_position"]["constant_offset"]["arcsec"] for t in targets
               if t["target_position"]["constant_offset"]
               and t["motion"]["agreement"] != "not_measurable"]
    if offsets:
        lines.append(f"Measured targets sit within {max(offsets)} arcsec of their catalog "
                     f"positions (at most {round(max(offsets) / 6.15, 2)} of a pixel), a constant "
                     f"shift that can't create motion.")
    return lines


# ---------- plots ----------

def write_plots(targets, all_random, all_star_pulls):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURES.mkdir(parents=True, exist_ok=True)
    blue, orange = "#3987e5", "#d95926"

    moving = [t for t in targets if t["motion"].get("z")]
    if moving:
        fig, axes = plt.subplots(1, len(moving), figsize=(3.8 * len(moving), 3.9), squeeze=False)
        for ax, t in zip(axes[0], moving):
            m, c = t["motion"]["measured_mas_yr"], t["motion"]["catalog_mas_yr"]
            ax.errorbar([m["ra"]], [m["dec"]], xerr=[m["ra_err"]], yerr=[m["dec_err"]],
                        fmt="o", color=blue, label="SPHEREx, our tool")
            ax.errorbar([c["ra"]], [c["dec"]], xerr=[c.get("ra_err") or 0],
                        yerr=[c.get("dec_err") or 0], fmt="x", color=orange, markersize=10,
                        label=c.get("source") or "catalog")
            pad = 4 * max(m["ra_err"], m["dec_err"])
            ax.set_xlim(c["ra"] - pad, c["ra"] + pad)
            ax.set_ylim(c["dec"] - pad, c["dec"] + pad)
            ax.set_title(f'{t["name"]}: {t["motion"]["agreement"]}', fontsize=10)
            ax.set_xlabel("motion east (mas/yr)")
            ax.set_ylabel("motion north (mas/yr)")
            ax.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(FIGURES / "motion_vs_catalog.png", dpi=150)
        plt.close(fig)

    curves = [(all_star_pulls, "field stars (not used for tuning)"),
              (all_random, "targets, image-to-image")]
    curves = [(p, lab) for p, lab in curves if p]
    if curves:
        fig, ax = plt.subplots(figsize=(5.2, 3.9))
        for (pulls, label), color in zip(curves, [blue, "#8a8f99"]):
            vals = [p for p in pulls if math.isfinite(p) and abs(p) < 8]
            ax.hist(vals, bins=30, range=(-5, 5), density=True, alpha=0.55, color=color,
                    label=f"{label} (n={len(vals)})")
        xs = [x / 20 for x in range(-100, 101)]
        ax.plot(xs, [math.exp(-x * x / 2) / math.sqrt(2 * math.pi) for x in xs],
                color=orange, label="honest error bars")
        ax.set_xlabel("(measured - predicted) / error bar")
        ax.set_ylabel("share")
        ax.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(FIGURES / "position_pulls.png", dpi=150)
        plt.close(fig)


# ---------- main ----------

def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--plot", action="store_true", help="also write scoring/figures/*.png")
    args = parser.parse_args()

    keys = [k for k in TARGET_ORDER if (DATA / k).is_dir()]
    keys += sorted(p.name for p in DATA.iterdir()
                   if p.is_dir() and p.name not in TARGET_ORDER and p.name != "spectra")

    targets, all_random, all_star_pulls, all_star_rows = [], [], [], []
    for key in keys:
        entry, raw = score_target(key)
        if entry:
            targets.append(entry)
            all_random += raw["random_pulls"]
            all_star_pulls += raw["star_pulls"]
            all_star_rows += raw["star_rows"]

    star_summary = pull_summary(all_star_pulls)
    scoreboard = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "headline": headline(targets, all_star_pulls, all_star_rows),
        "method": {
            "motion": "Measured vs catalog motion per axis, z = difference / error; combined "
                      "chi-square with 2 degrees of freedom. Agrees if p >= 0.05, tension if "
                      "0.0027 <= p < 0.05, disagrees if p < 0.0027 (3 sigma).",
            "error_bars": "Pull = (measured - expected position) / error bar. Honest error "
                          "bars put 68% of pulls within 1 and 95% within 2.",
            "field_stars": "The same tests on Gaia stars in the field, excluding stars used to "
                           "set the error bars, stars blended with a neighbour, and saturated "
                           "visits. Per star: chi-square of its pulls over all its visits.",
            "not_scored": "Field-star brightness, objects in no catalog, and motion of "
                          "saturated targets.",
        },
        "summary": {
            "targets_scored": len(targets),
            "field_stars": star_summary,
            "field_star_error_bars": error_bar_assessment(star_summary),
            "disagreeing_objects": [r["name"] for r in all_star_rows
                                    if r["role"] == "scored" and r["agreement"] == "disagrees"],
        },
        "targets": targets,
    }

    out = DATA / "scoreboard.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(scoreboard, f, indent=1)
        f.write("\n")

    print(f"wrote {out.relative_to(ROOT)}")
    for line in scoreboard["headline"]:
        print("  " + line)
    for t in targets:
        m, p = t["motion"], t["target_position"]
        fs = t["field_stars"]
        print(f"  {t['name']:15s} {t['verdict']:19s} motion={m['agreement']:15s} "
              f"z={m.get('z')} offset={(p['constant_offset'] or {}).get('arcsec')}\" "
              f"target error bars={p['error_bars']} "
              f"field stars={fs['agreement_counts'] if fs else '-'}")
    if args.plot:
        write_plots(targets, all_random, all_star_pulls)
        print(f"wrote plots to {FIGURES.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
