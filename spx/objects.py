"""Measure every measurable Gaia star in the field, not only the target, and write objects.json.

Same method as the target (measure.measure_point on each frame's own pixels, brighter Gaia
neighbors as fixed Gaussians, the same error floors), so the field stars test the tool on objects
nobody tuned it for. Reference stars set those error floors, so they are flagged: a fair accuracy
test uses the others. Format and reasoning: decisions.md "objects.json".
"""
import json

import numpy as np
from astropy.time import Time

from spx.clean import SATURATED
from spx.export import _web_point
from spx.field import CENTER_DATE
from spx.measure import (APERTURE_R, BLEND_RADIUS_PX, NEIGHBOR_MARGIN_PX, NEIGHBOR_MAX_DMAG, REF_MAX_G, STAMP_HALF,
                         frame_position_error, gaia_positions, measure_point, position_floor, target_position,
                         visit_shared_floor)
from spx.visits import visit_of

OBJECT_MAX_G = REF_MAX_G  # fainter Gaia stars rarely reach S/N 5 in a single SPHEREx frame
# Crowding: a Gaia neighbor this close and at most this much fainter shifts the measured position by a
# constant amount. Measured 2026-11-15 on 83 non-reference stars, absolute test with the field floor:
# stars without such a neighbor 89% / 99% within 1 / 2 sigma, with one 71% / 86%.
CROWDED_RADIUS_PX = 2.0
CROWDED_MAX_DMAG = 5.0


def _g_mag(table):
    return np.ma.filled(np.ma.asarray(table["phot_g_mean_mag"], dtype=float), np.nan)


def field_objects(field, catalog, target):
    """Gaia rows inside the field on the center date with G <= OBJECT_MAX_G, without the target
    and anything blended with it (within BLEND_RADIUS_PX: that light is part of the target's)."""
    grid = field.wcs()
    when = Time(CENTER_DATE)
    x, y = grid.world_to_pixel(gaia_positions(catalog, when))
    edge = field.size_px - 0.5
    keep = (x >= -0.5) & (x <= edge) & (y >= -0.5) & (y <= edge) & (_g_mag(catalog) <= OBJECT_MAX_G)
    tx, ty = grid.world_to_pixel(target_position(target, field, when))
    keep &= np.hypot(x - tx, y - ty) > BLEND_RADIUS_PX
    if target is not None:
        keep &= np.array([str(i) != target.source_id for i in catalog["source_id"]])
    return catalog[keep]


def measure_objects(frame, field, objects, catalog):
    """{source_id: (measured grid xy or None, fit error xy or None, saturated)} for one clean frame.

    A fit that ends closer to another Gaia source than to the object's own prediction measured
    that source instead, and is dropped (same identity check as the target).
    """
    when = Time(frame.header["MJD-AVG"], format="mjd")
    grid = field.wcs()
    all_sky = gaia_positions(catalog, when)
    fx, fy = (np.atleast_1d(v) for v in frame.wcs.world_to_pixel(all_sky))
    gx, gy = (np.atleast_1d(v) for v in grid.world_to_pixel(all_sky))
    ids = np.array([str(i) for i in catalog["source_id"]])
    g_all = _g_mag(catalog)
    yy, xx = np.indices(frame.image.shape)
    results = {}
    for row in objects:
        source_id = str(row["source_id"])
        own = ids == source_id
        x0, y0, ex, ey = fx[own][0], fy[own][0], gx[own][0], gy[own][0]
        if not (np.isfinite(x0) and np.isfinite(y0)):
            results[source_id] = (None, None, False)
            continue
        saturated = bool((frame.flag_class[(xx - x0) ** 2 + (yy - y0) ** 2 <= APERTURE_R ** 2] == SATURATED).any())
        separation = np.hypot(fx - x0, fy - y0)  # frame and grid pixels are the same size
        neighbors = (~own & (separation > BLEND_RADIUS_PX)
                     & (np.maximum(np.abs(fx - x0), np.abs(fy - y0)) <= STAMP_HALF + NEIGHBOR_MARGIN_PX)
                     & (g_all <= float(row["phot_g_mean_mag"]) + NEIGHBOR_MAX_DMAG))
        point = measure_point(frame.image, frame.variance, x0, y0, list(zip(fx[neighbors], fy[neighbors])))
        if point is None:
            results[source_id] = (None, None, saturated)
            continue
        mx, my = (float(v) for v in grid.world_to_pixel(frame.wcs.pixel_to_world(point.x, point.y)))
        resolved = ~own & (np.hypot(gx - ex, gy - ey) > BLEND_RADIUS_PX)
        if resolved.any() and np.nanmin(np.hypot(gx[resolved] - mx, gy[resolved] - my)) < np.hypot(mx - ex, my - ey):
            results[source_id] = (None, None, saturated)
            continue
        results[source_id] = ((mx, my), (point.x_err, point.y_err), saturated)
    return results


class _Fit:
    """The two fields frame_position_error reads, for one object in one frame."""
    def __init__(self, measured, fit_err):
        self.measured, self.measured_fit_err = measured, fit_err


def export_objects(path, target_key, field, visits, ranges, object_results, frame_measurements, objects,
                   catalog, references):
    """Write objects.json: per object and visit, expected and measured position with errors.

    object_results: [(mjd, measure_objects output)] for every measured frame.
    frame_measurements: the target's FrameMeasurements; their reference-star residuals give the
    error floors, exactly as for the target in manifest.json.
    """
    floor = position_floor(frame_measurements)
    shared = visit_shared_floor(frame_measurements, visit_of([m.mjd for m in frame_measurements], ranges))
    frame_visits = visit_of([mjd for mjd, _ in object_results], ranges) if object_results else []
    grid = field.wcs()
    reference_ids = {str(i) for i in references["source_id"]}
    center_xy = grid.world_to_pixel(gaia_positions(catalog, Time(CENTER_DATE)))
    ids = np.array([str(i) for i in catalog["source_id"]])
    g_all = _g_mag(catalog)

    entries = []
    for row in objects:
        source_id = str(row["source_id"])
        own = ids == source_id
        ox, oy = center_xy[0][own][0], center_xy[1][own][0]
        blended = (~own & (np.hypot(center_xy[0] - ox, center_xy[1] - oy) <= BLEND_RADIUS_PX)
                   & (g_all <= float(row["phot_g_mean_mag"]) + NEIGHBOR_MAX_DMAG))
        crowded = crowding_neighbors(center_xy, own, g_all, float(row["phot_g_mean_mag"]))
        visit_entries = []
        for visit in visits:
            mid = Time(np.mean([f.header["MJD-AVG"] for f in visit.frames]), format="mjd")
            expected = grid.world_to_pixel(gaia_positions(catalog[own], mid))
            rows = [r[source_id] for (_, r), n in zip(object_results, frame_visits) if n == visit.n]
            fits = [_Fit(m, e) for m, e, _ in rows if m is not None]
            measured = error = None
            if fits and floor is not None:
                xy = np.array([f.measured for f in fits])
                weights = 1 / np.array([frame_position_error(f, floor) for f in fits]) ** 2
                mean = (xy * weights).sum(axis=0) / weights.sum(axis=0)
                measured = _web_point(mean, field)
                error = [round(float(e), 3) for e in np.hypot(1 / np.sqrt(weights.sum(axis=0)), shared)]
            visit_entries.append({
                "n": visit.n,
                "expected_px": _web_point((float(expected[0][0]), float(expected[1][0])), field),
                "measured_px": measured,
                "measured_err_px": error,
                "n_measured": len(fits),
                "n_frames": len(rows),
                "saturated": bool(np.mean([s for _, _, s in rows] or [0]) > 0.5),
            })
        entries.append({
            "name": f"Gaia DR3 {source_id}",
            "catalog": "Gaia DR3",
            "g_mag": round(float(row["phot_g_mean_mag"]), 2),
            "reference": source_id in reference_ids,
            "blended_with": [f"Gaia DR3 {i}" for i in ids[blended]],
            "crowded_by": [f"Gaia DR3 {i}" for i in ids[crowded]],
            "visits": visit_entries,
        })
    entries.sort(key=lambda e: e["g_mag"])
    document = {
        "target_key": target_key,
        "size_px": field.size_px,
        "selection": (f"Gaia DR3 stars inside the field on {CENTER_DATE} with G <= {OBJECT_MAX_G:g}, "
                      f"except the target and anything within {BLEND_RADIUS_PX:g} px of it"),
        **absolute_floor(entries),
        "objects": entries,
    }
    path.write_text(json.dumps(document, indent=1))
    return document


def crowding_neighbors(xy, own, g_all, g):
    """Gaia neighbors close and bright enough to shift a star's measured position (not merged with it:
    those are blended_with)."""
    separation = np.hypot(xy[0] - xy[0][own][0], xy[1] - xy[1][own][0])
    return (~own & (separation > BLEND_RADIUS_PX) & (separation <= CROWDED_RADIUS_PX)
            & (g_all <= g + CROWDED_MAX_DMAG))


def absolute_floor(entries):
    """Error to add (in quadrature) when comparing a position with Gaia's, not when testing motion.

    Each star's measured position sits a constant amount off Gaia's in every visit (crowding,
    color-dependent PSF), which the per-visit errors don't include. The reference stars measure it:
    the RMS over stars of their offset averaged over visits. With it, 74% / 88% of non-reference
    field-star positions fall within 1 / 2 sigma (38% / 59% without), 2026-11-15.
    """
    means = []
    for entry in entries:
        offsets = [np.subtract(v["measured_px"], v["expected_px"]) for v in entry["visits"]
                   if entry["reference"] and v["measured_px"] is not None]
        if offsets:
            means.append(np.mean(offsets, axis=0))
    if len(means) < 2:
        return {"absolute_floor_px": None, "absolute_floor_from": "fewer than 2 reference stars measured"}
    rms = np.sqrt(np.mean(np.square(means), axis=0))
    return {"absolute_floor_px": [round(float(v), 3) for v in rms],
            "absolute_floor_from": f"{len(means)} reference stars: RMS of each star's offset from Gaia, averaged over visits"}
