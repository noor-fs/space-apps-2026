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
  Two tests per star, both with the same three labels as check 1:
  motion     (main test, the tool's claim) does the star MOVE as Gaia predicts? Each star's
             constant offset is removed (weighted mean over its visits) and the rest is
             tested: chi2 with 2 x (visits - 1) degrees of freedom, no floor.
  absolute   is the star WHERE Gaia predicts? Pulls use the error bar plus the field's
             absolute_floor_px in quadrature (the constant per-star offset that crowding
             causes, measured on the reference stars): chi2 with 2 x visits degrees of
             freedom. The same floor is applied to the target's absolute pulls (check 2).
  Stars with a Gaia neighbour within 2 px (crowded_by) are reported separately too.
  Fields with a crowding floor above 0.25 px (R Draconis, whose glow covers the field) are
  scored in their own entry but left out of the pooled totals and the headline.
  Stars that fail the motion test are listed by name: known stars not moving as Gaia says.

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
# Fields whose crowding floor is this large are dominated by a very bright target's glow
# (R Draconis: 0.14 / 0.40 px). They stay in their own target entry but are left out of
# the pooled field-star totals, because their stars aren't a fair test of the tool.
POOL_MAX_FLOOR_PX = 0.25
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


def with_floor(s, floor):
    """Error bar plus a constant floor, in quadrature, per axis."""
    return [math.hypot(s[0], floor[0]), math.hypot(s[1], floor[1])]


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

def target_position_check(manifest, floor=(0.0, 0.0)):
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
            image_pulls.extend(pulls_of(e, m, with_floor(s, floor)))
        if len(rows) >= 2:
            mean = [sum(r[0][k] for r in rows) / len(rows) for k in (0, 1)]
            for d, s in rows:
                random_pulls.extend([(d[0] - mean[0]) / s[0], (d[1] - mean[1]) / s[1]])
        e, m, s = (visit.get("target_expected_px"), visit.get("target_measured_px"),
                   visit.get("target_measured_err_px"))
        if usable(e, m, s):
            visit_pulls.extend(pulls_of(e, m, with_floor(s, floor)))
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
        "absolute_floor_px": list(floor),
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


def score_object(obj, floor):
    """Motion and absolute tests for one object from objects.json."""
    rows, n_measured_any = [], 0
    for v in obj.get("visits", []):
        e, m, s = v.get("expected_px"), v.get("measured_px"), v.get("measured_err_px")
        if m is not None:
            n_measured_any += 1
        if v.get("saturated") or not usable(e, m, s):
            continue
        rows.append(([m[0] - e[0], m[1] - e[1]], s))
    n = len(rows)

    # Absolute: is the star where Gaia predicts? Error bar plus the crowding floor.
    abs_pulls = []
    for d, s in rows:
        sf = with_floor(s, floor)
        abs_pulls += [d[0] / sf[0], d[1] / sf[1]]
    abs_chi2 = sum(p * p for p in abs_pulls)
    abs_p = chi2_p(abs_chi2, 2 * n) if n else None

    # Motion: does it move as Gaia predicts? Remove the star's own constant offset.
    mot_pulls, mot_p, mot_chi2 = [], None, None
    if n >= 2:
        mean = []
        for k in (0, 1):
            w = [1 / r[1][k] ** 2 for r in rows]
            mean.append(sum(r[0][k] * wk for r, wk in zip(rows, w)) / sum(w))
        mot_pulls = [x for d, s in rows for x in ((d[0] - mean[0]) / s[0], (d[1] - mean[1]) / s[1])]
        mot_chi2 = sum(p * p for p in mot_pulls)
        mot_p = chi2_p(mot_chi2, 2 * (n - 1))

    return {
        "n_visits": n,
        "recovered": n_measured_any > 0,
        "motion": {"pulls": mot_pulls, "chi2": mot_chi2, "dof": 2 * (n - 1) if n >= 2 else 0,
                   "p": mot_p, "agreement": agreement_label(mot_p)},
        "absolute": {"pulls": abs_pulls, "chi2": abs_chi2 if n else None, "dof": 2 * n,
                     "p": abs_p, "agreement": agreement_label(abs_p)},
    }


def counts_by(rows, key):
    return {lab: sum(1 for x in rows if x[key] == lab) for lab in ("agrees", "tension", "disagrees")}


def field_star_check(objects_file):
    objects = objects_file.get("objects", [])
    floor = tuple(objects_file.get("absolute_floor_px") or (0.0, 0.0))
    pools = {k: [] for k in ("motion", "absolute", "motion_uncrowded", "absolute_uncrowded",
                             "motion_crowded", "absolute_crowded",
                             "motion_reference", "absolute_reference")}
    rows = []
    recovered = {label: [0, 0] for label, _, _ in G_BINS}
    counts = {"in_file": len(objects), "scored": 0, "crowded": 0, "reference": 0,
              "blended": 0, "too_few_visits": 0}

    for obj in objects:
        r = score_object(obj, floor)
        b = g_bin(obj.get("g_mag", 99))
        recovered[b][1] += 1
        recovered[b][0] += r["recovered"]
        crowded = bool(obj.get("crowded_by"))

        if obj.get("reference"):
            role = "reference"
            counts["reference"] += 1
            pools["motion_reference"] += r["motion"]["pulls"]
            pools["absolute_reference"] += r["absolute"]["pulls"]
        elif obj.get("blended_with"):
            role = "blended"
            counts["blended"] += 1
        elif r["n_visits"] < 2:
            role = "not_scored"
            counts["too_few_visits"] += 1
        else:
            role = "scored"
            counts["scored"] += 1
            counts["crowded"] += crowded
            tag = "crowded" if crowded else "uncrowded"
            pools["motion"] += r["motion"]["pulls"]
            pools["absolute"] += r["absolute"]["pulls"]
            pools[f"motion_{tag}"] += r["motion"]["pulls"]
            pools[f"absolute_{tag}"] += r["absolute"]["pulls"]

        rows.append({
            "name": obj.get("name"),
            # Main label for the site: does it move as Gaia predicts?
            "agreement": r["motion"]["agreement"],
            "chi2": round(r["motion"]["chi2"], 2) if r["motion"]["chi2"] is not None else None,
            "dof": r["motion"]["dof"],
            "p_value": round(r["motion"]["p"], 4) if r["motion"]["p"] is not None else None,
            # Secondary: is it where Gaia predicts (with the crowding floor)?
            "agreement_absolute": r["absolute"]["agreement"],
            "chi2_absolute": round(r["absolute"]["chi2"], 2) if r["absolute"]["chi2"] is not None else None,
            "n_visits": r["n_visits"],
            "g_mag": obj.get("g_mag"),
            "crowded": crowded,
            "role": role,  # scored, reference, blended, not_scored
        })

    scored = [x for x in rows if x["role"] == "scored"]
    motion_summary = pull_summary(pools["motion"])
    return {
        "absolute_floor_px": list(floor),
        "counts": counts,
        "recovered_by_g": {k: {"recovered": v[0], "total": v[1]}
                           for k, v in recovered.items() if v[1]},
        "motion_test": {
            "pulls": motion_summary,
            "pulls_uncrowded": pull_summary(pools["motion_uncrowded"]),
            "pulls_crowded": pull_summary(pools["motion_crowded"]),
            "pulls_reference": pull_summary(pools["motion_reference"]),
            "agreement_counts": counts_by(scored, "agreement"),
            "disagreeing": [x["name"] for x in scored if x["agreement"] == "disagrees"],
        },
        "absolute_test": {
            "pulls": pull_summary(pools["absolute"]),
            "pulls_uncrowded": pull_summary(pools["absolute_uncrowded"]),
            "pulls_crowded": pull_summary(pools["absolute_crowded"]),
            "pulls_reference": pull_summary(pools["absolute_reference"]),
            "agreement_counts": counts_by(scored, "agreement_absolute"),
            "disagreeing": [x["name"] for x in scored if x["agreement_absolute"] == "disagrees"],
        },
        "error_bars": error_bar_assessment(motion_summary),
        "objects": rows,
    }, pools, rows


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
        objects_file = load_json(folder / "objects.json") if (folder / "objects.json").exists() else None
        floor = tuple((objects_file or {}).get("absolute_floor_px") or (0.0, 0.0))
        position, random_pulls = target_position_check(manifest, floor)
        entry = {
            "target_key": key,
            "name": manifest.get("name", key),
            "field_size_px": size,
            "verdict": manifest.get("verdict"),
            "motion": motion_check(manifest),
            "target_position": position,
            "field_stars": None,
        }
        raw = {"random_pulls": random_pulls, "pools": {}, "star_rows": []}
        if objects_file:
            entry["field_stars"], raw["pools"], raw["star_rows"] = field_star_check(objects_file)
            pooled = max(floor) <= POOL_MAX_FLOOR_PX
            entry["field_stars"]["in_pooled_totals"] = pooled
            if not pooled:
                entry["field_stars"]["excluded_reason"] = (
                    f"crowding floor {list(floor)} px is above {POOL_MAX_FLOOR_PX} px: the "
                    f"bright target's glow dominates this field")
                raw["pools"], raw["star_rows"] = {}, []
        return entry, raw
    return None, None


# ---------- headline sentences for the site ----------

def pct(x):
    return f"{round(100 * x)}%"


def headline(targets, pools, star_rows):
    lines = []

    measurable = [t for t in targets if t["motion"]["agreement"] != "not_measurable"]
    if measurable:
        agree = sum(1 for t in measurable if t["motion"]["agreement"] == "agrees")
        line = (f"Targets: {agree} of {len(measurable)} measurable targets move as the "
                f"catalogs predict.")
        skipped = [f'{t["name"]} ({t["motion"]["reason"]})' for t in targets
                   if t["motion"]["agreement"] == "not_measurable"]
        if skipped:
            line += " Not measurable: " + ", ".join(skipped) + "."
        lines.append(line)

    scored = [r for r in star_rows if r["role"] == "scored"]
    motion = pull_summary(pools.get("motion", []))
    if scored and motion:
        n_fields = sum(1 for t in targets if t["field_stars"] and t["field_stars"]["in_pooled_totals"])
        agree = sum(1 for r in scored if r["agreement"] == "agrees")
        lines.append(
            f"Other stars: {agree} of {len(scored)} Gaia stars the tool was never tuned on move "
            f"exactly as Gaia predicts ({n_fields} fields). {pct(motion['within_1sigma'])} of "
            f"their measurements fall within 1 error bar and {pct(motion['within_2sigma'])} "
            f"within 2, against 68% and 95% for honest error bars.")
    absolute = pull_summary(pools.get("absolute", []))
    unc = pull_summary(pools.get("absolute_uncrowded", []))
    n_crowded = sum(1 for r in scored if r["crowded"])
    if absolute:
        line = (f"Positions: allowing for crowding, {pct(absolute['within_1sigma'])} of star "
                f"positions fall within 1 error bar of Gaia and {pct(absolute['within_2sigma'])} "
                f"within 2")
        if unc:
            line += (f" ({pct(unc['within_1sigma'])} and {pct(unc['within_2sigma'])} for stars "
                     f"with no close neighbour)")
        line += (f". {n_crowded} of {len(scored)} stars have a neighbour within 2 pixels, "
                 f"which shifts their light centre slightly; this never fakes motion.")
        lines.append(line)

    offsets = [t["target_position"]["constant_offset"]["arcsec"] for t in targets
               if t["target_position"]["constant_offset"]
               and t["motion"]["agreement"] != "not_measurable"]
    if offsets:
        lines.append(f"Measured targets sit within {max(offsets)} arcsec of their catalog "
                     f"positions (at most {round(max(offsets) / 6.15, 2)} of a pixel), a constant "
                     f"shift that can't create motion.")
    return lines


# ---------- plots ----------

def write_plots(targets, all_random, pools):
    all_star_pulls = pools.get("motion", [])
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

    curves = [(all_star_pulls, "field stars, motion test"),
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

    targets, all_random, all_star_rows = [], [], []
    pools = {}
    for key in keys:
        entry, raw = score_target(key)
        if entry:
            targets.append(entry)
            all_random += raw["random_pulls"]
            all_star_rows += raw["star_rows"]
            for k, v in raw["pools"].items():
                pools.setdefault(k, []).extend(v)

    star_summary = pull_summary(pools.get("motion", []))
    scoreboard = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "headline": headline(targets, pools, all_star_rows),
        "method": {
            "motion": "Measured vs catalog motion per axis, z = difference / error; combined "
                      "chi-square with 2 degrees of freedom. Agrees if p >= 0.05, tension if "
                      "0.0027 <= p < 0.05, disagrees if p < 0.0027 (3 sigma).",
            "error_bars": "Pull = (measured - expected position) / error bar. Honest error "
                          "bars put 68% of pulls within 1 and 95% within 2.",
            "field_stars": "Gaia stars in the field, excluding stars used to set the error bars, "
                           "stars merged with a neighbour, and saturated visits. Motion test "
                           "(main): each star's constant offset is removed, then its visits "
                           "are tested against Gaia's predicted motion. Position test: "
                           "distance from Gaia's position, with an extra allowance for the "
                           "constant shift crowding causes (measured on the reference stars).",
            "not_scored": "Field-star brightness, objects in no catalog, and motion of "
                          "saturated targets.",
        },
        "summary": {
            "targets_scored": len(targets),
            "fields_left_out_of_totals": {t["target_key"]: t["field_stars"]["excluded_reason"]
                                          for t in targets if t["field_stars"]
                                          and not t["field_stars"]["in_pooled_totals"]},
            "field_stars_motion": star_summary,
            "field_stars_motion_uncrowded": pull_summary(pools.get("motion_uncrowded", [])),
            "field_stars_absolute": pull_summary(pools.get("absolute", [])),
            "field_stars_absolute_uncrowded": pull_summary(pools.get("absolute_uncrowded", [])),
            "field_star_error_bars": error_bar_assessment(star_summary),
            # Known stars that don't move as Gaia predicts: the "unexpected" output.
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
              f"field stars motion={fs['motion_test']['agreement_counts'] if fs else '-'} "
              f"absolute={fs['absolute_test']['agreement_counts'] if fs else '-'}")
    if args.plot:
        write_plots(targets, all_random, pools)
        print(f"wrote plots to {FIGURES.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
