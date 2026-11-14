"""Write a field's images and measurements in the web format (saturday_plan.md, "Shared data format").

Everything up to here uses the FITS orientation (array row 0 = south edge). The web format puts
north in row 0, so arrays are flipped and positions converted here, and nowhere else.
"""
import csv
import json
import shutil
import warnings
from pathlib import Path

import numpy as np
from astropy.stats import sigma_clipped_stats
from astropy.time import Time
from astropy.visualization import make_lupton_rgb
from PIL import Image
from scipy.ndimage import maximum_filter

from spx.archive import IRSA
from spx.clean import DEFECT, OTHER, SATURATED
from spx.field import CENTER_DATE, PIXEL_SCALE_ARCSEC
from spx.measure import apparent_positions, frame_position_error, position_floor, visit_shared_floor
from spx.visits import visit_of

# Grayscale PNGs: asinh stretch between the sky level minus SKY_SIGMAS_BELOW noise (black) and
# the WHITE_PERCENTILE of the pixels (white). asinh keeps faint sky visible while compressing
# bright star cores; ASINH_SOFTENING is where it turns from linear to logarithmic (share of range).
SKY_SIGMAS_BELOW = 2.0
WHITE_PERCENTILE = 99.7
ASINH_SOFTENING = 0.1
# RGB: each channel is divided by the median brightness of the field's stars in it, so a typical
# star comes out white and only sources redder or bluer than the field's stars show color. Then
# one asinh stretch for all channels (Lupton et al. 2004), which keeps colors in bright cores.
RGB_Q = 8
BALANCE_STARS = 30  # brightest peaks used for the color balance...
BALANCE_MIN_SIGMA = 10.0  # ...above this many sky noise...
BALANCE_TARGET_RADIUS_PX = 3.0  # ...and not the target (it would set its own color to white)
FLAG_COLORS = {SATURATED: (255, 0, 0), DEFECT: (255, 140, 0), OTHER: (0, 90, 255)}  # decisions.md


def frame_key(header):
    """Identifies a frame in this module's inputs: exposure and detector, from its IMAGE header."""
    return f"{header['OBSID']}_D{int(header['DETECTOR'])}"


def export_field(data_dir, target_key, name, field, target, visits, ranges, frame_measurements,
                 visit_measurements, motion, motion_source, verdict, uris=None):
    """Write data/<target_key>/fields.json and the whole fov<S>/ folder for one field size.

    visits: visits.build_visits output. ranges: visit_ranges of ALL frames found.
    frame_measurements: {frame_key: FrameMeasurement} for single frames.
    visit_measurements: psf.measure_visits output, or None. motion, motion_source: measure_motion output.
    uris: {frame_key: archive uri} from archive.find_frames; archive_url is null without it.
    The fov<S>/ folder is rebuilt from scratch, so no file from an earlier run survives.
    """
    data_dir = Path(data_dir)
    fov = data_dir / f"fov{field.size_px}"
    if fov.exists():
        shutil.rmtree(fov)
    (fov / "frames").mkdir(parents=True)

    frame_floor = position_floor(list(frame_measurements.values()))
    visit_set = list(frame_measurements.values()) if motion_source == "frames" else (visit_measurements or [])
    visit_floor = position_floor(visit_set)
    visit_numbers = visit_of([m.mjd for m in visit_set], ranges) if visit_set else []
    shared_floor = visit_shared_floor(visit_set, visit_numbers)

    stack_limits = stretch_limits([v.combined.image for v in visits])
    rgb_scales = color_balance(visits, _expected_grid(field, target, Time(CENTER_DATE)))

    entries = []
    for visit in visits:
        n = visit.n
        _write_f32(fov / f"visit_{n}.f32", visit.combined.image)
        _write_gray(fov / f"visit_{n}.png", visit.combined.image, stack_limits)
        _write_rgb(fov / f"visit_{n}_rgb.png", visit.rgb, rgb_scales)

        frames = []
        for i, frame in enumerate(visit.blink_frames, start=1):
            key = frame_key(frame.header)
            stem = f"frames/v{n}_{i}"
            _write_f32(fov / f"{stem}.f32", frame.image)
            _write_gray(fov / f"{stem}.png", frame.image, stretch_limits([frame.image]))
            _write_flags(fov / f"{stem}_flags.png", frame.flag_class, frame.covered)
            m = frame_measurements.get(key)
            frames.append({
                "i": i,
                "image": f"{stem}.png",
                # whole seconds, as in the format example; the asteroid layer matches on this exact string
                "time": Time(frame.header["DATE-AVG"], format="isot", scale="utc", precision=0).isot + "Z",
                "detector": int(frame.header["DETECTOR"]),
                "wavelength_um": _number(m.wavelength_um, 4) if m else None,
                **_position_fields(m, frame_floor, field),
                "saturated": bool(m.saturated) if m else False,
                "bad_pixel_fraction": round(frame.bad_pixel_fraction, 4),
                "target_flux_mjy": _number(m and m.flux_mjy, 5),
                "target_flux_err_mjy": _number(m and m.flux_err_mjy, 5),
                "data": f"{stem}.f32",
                "flags": f"{stem}_flags.png",
                "archive_url": f"{IRSA}{uris[key]}" if uris and key in uris else None,
            })

        mid = Time(np.mean([f.header["MJD-AVG"] for f in visit.frames]), format="mjd")
        in_visit = [m for m, number in zip(visit_set, visit_numbers) if number == n]
        measured, error = _visit_position(in_visit, visit_floor, shared_floor, field)
        own = [m for m in (frame_measurements.get(frame_key(f.header)) for f in visit.frames) if m is not None]
        wavelengths = [m.wavelength_um for m in own if np.isfinite(m.wavelength_um)]
        entries.append({
            "n": n,
            "image": f"visit_{n}.png",
            "image_rgb": f"visit_{n}_rgb.png",
            "data": f"visit_{n}.f32",
            "date_start": _date(visit.mjd_start),
            "date_end": _date(visit.mjd_end),
            "date_mid": mid.isot[:10],
            "n_images": len(visit.frames),
            "wavelength_um": [round(min(wavelengths), 3), round(max(wavelengths), 3)] if wavelengths else None,
            "target_expected_px": _web_point(_expected_grid(field, target, mid), field),
            "target_measured_px": measured,
            "target_measured_err_px": error,
            "saturated": bool(np.mean([m.saturated for m in own] or [0]) > 0.5),
            "frames": frames,
        })

    center = field.center
    manifest = {
        "target_key": target_key,
        "name": name,
        "grid": {"center_ra": round(center.ra.deg, 6), "center_dec": round(center.dec.deg, 6),
                 "center_date": CENTER_DATE, "pixel_scale_arcsec": PIXEL_SCALE_ARCSEC,
                 "size_px": field.size_px},
        "visits": entries,
        "verdict": verdict,
        "measured_motion_mas_yr": None if motion is None or not motion.constrained else {
            "ra": round(motion.pmra), "ra_err": round(motion.pmra_err),
            "dec": round(motion.pmdec), "dec_err": round(motion.pmdec_err)},
        "catalog_motion_mas_yr": None if target is None else {
            "ra": round(target.pmra), "dec": round(target.pmdec), "source": target.catalog},
    }
    (fov / "manifest.json").write_text(json.dumps(manifest, indent=1))
    _add_field_size(data_dir / "fields.json", field.size_px)
    return manifest


def write_results(results_dir, field, frame_measurements, visit_measurements, motion, motion_source,
                  brightness, verdict):
    """Measurement table and test summaries behind the manifest numbers (results/<target_key>/)."""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    floor = position_floor(list(frame_measurements.values()))
    columns = ["frame", "mjd", "detector", "wavelength_um", "bandwidth_um", "expected_col", "expected_row",
               "measured_col", "measured_row", "error_col", "error_row", "flux_mjy", "flux_err_mjy", "snr",
               "saturated"]
    rows = [(key, m) for key, m in frame_measurements.items()]
    rows += [(f"visitfit_D{'+'.join(map(str, m.detector))}", m) for m in visit_measurements or []]
    visit_fit_floor = position_floor(visit_measurements or [])
    with (results_dir / f"measurements_fov{field.size_px}.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for key, m in sorted(rows, key=lambda row: row[1].mjd):
            position = _position_fields(m, visit_fit_floor if key.startswith("visitfit") else floor, field)
            writer.writerow([key, f"{m.mjd:.6f}", m.detector, _number(m.wavelength_um, 4),
                             _number(m.bandwidth_um, 4), *_web_point(m.expected, field),
                             *(position["target_measured_px"] or ["", ""]),
                             *(position["target_measured_err_px"] or ["", ""]),
                             _number(m.flux_mjy, 5), _number(m.flux_err_mjy, 5), _number(m.snr, 3),
                             m.saturated])
    summary = {"verdict": verdict, "motion_source": motion_source,
               "position_floor_px": floor, "visit_fit_position_floor_px": visit_fit_floor,
               "motion": None if motion is None else {**motion.__dict__, "shift_px": motion.shift_px,
                                                      "constrained": motion.constrained,
                                                      "detected": motion.detected,
                                                      "matches_catalog": motion.matches_catalog},
               "brightness": None if brightness is None else {
                   "changes": {str(d): {str(v): list(x) for v, x in c.items()} for d, c in brightness.changes.items()},
                   "chi2": brightness.chi2, "dof": brightness.dof, "significant": brightness.significant,
                   "extra_scatter": brightness.extra_scatter, "calibration_floor": brightness.calibration_floor,
                   "n_frames": brightness.n_frames}}
    (results_dir / f"verdict_fov{field.size_px}.json").write_text(json.dumps(summary, indent=1, default=float))


def stretch_limits(images):
    """(black, white) for a set of images that share one stretch."""
    values = np.concatenate([np.asarray(image)[np.isfinite(image)] for image in images])
    if values.size == 0:
        return 0.0, 1.0
    _, sky, noise = sigma_clipped_stats(values, sigma=3)
    black = sky - SKY_SIGMAS_BELOW * noise
    white = np.percentile(values, WHITE_PERCENTILE)
    return float(black), float(white if white > black else black + 1)


def _web(array):
    return np.flipud(array)


def _write_f32(path, image):
    np.ascontiguousarray(_web(image), dtype="<f4").tofile(path)


def _asinh(x):
    return np.arcsinh(x / ASINH_SOFTENING) / np.arcsinh(1 / ASINH_SOFTENING)


def _write_gray(path, image, limits):
    black, white = limits
    scaled = np.clip((np.nan_to_num(image, nan=black) - black) / (white - black), 0, 1)
    gray = np.round(_asinh(scaled) * 255).astype(np.uint8)
    alpha = np.where(np.isfinite(image), 255, 0).astype(np.uint8)
    Image.fromarray(_web(np.dstack([gray, alpha])), mode="LA").save(path, optimize=True)


def color_balance(visits, target_xy):
    """Scale per RGB channel: median value of the field's star peaks in that channel.

    Peaks are local maxima of the all-visit mean image, bright and away from the target. Falls
    back to each channel's WHITE_PERCENTILE level with fewer than 3 peaks.
    """
    colors = ("red", "green", "blue")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # pixels with no data in any visit
        mean = np.nanmean([v.combined.image for v in visits], axis=0)
        channels = {c: np.nanmean([v.rgb[c] for v in visits], axis=0) for c in colors}
    _, sky, noise = sigma_clipped_stats(mean[np.isfinite(mean)], sigma=3)
    filled = np.nan_to_num(mean, nan=-np.inf)
    yy, xx = np.indices(mean.shape)
    peaks = ((filled == maximum_filter(filled, size=3)) & (filled > sky + BALANCE_MIN_SIGMA * noise)
             & (np.hypot(xx - target_xy[0], yy - target_xy[1]) > BALANCE_TARGET_RADIUS_PX))
    peaks &= np.all([np.isfinite(channels[c]) & (channels[c] > 0) for c in colors], axis=0)
    order = np.argsort(filled[peaks])[::-1][:BALANCE_STARS]
    scales = {}
    for c in colors:
        values = channels[c][peaks][order]
        if len(values) >= 3:
            scales[c] = float(np.median(values))
        else:
            finite = channels[c][np.isfinite(channels[c])]
            level = np.percentile(finite, WHITE_PERCENTILE) if finite.size else 1.0
            scales[c] = float(level) if level > 0 else 1.0
    return scales


def _write_rgb(path, rgb, scales):
    channels = [np.nan_to_num(rgb[color] / scales[color], nan=0.0) for color in ("red", "green", "blue")]
    pixels = make_lupton_rgb(*channels, minimum=0, stretch=1, Q=RGB_Q)
    present = np.any([np.isfinite(rgb[color]) for color in ("red", "green", "blue")], axis=0)
    alpha = np.where(present, 255, 0).astype(np.uint8)
    Image.fromarray(_web(np.dstack([pixels, alpha])), mode="RGBA").save(path, optimize=True)


def _write_flags(path, flag_class, covered):
    pixels = np.zeros(flag_class.shape + (4,), np.uint8)
    for number, color in FLAG_COLORS.items():
        pixels[(flag_class == number) & covered] = (*color, 255)
    Image.fromarray(_web(pixels), mode="RGBA").save(path, optimize=True)


def _web_point(xy, field):
    """FITS-orientation grid (x, y) -> web [column, row], row 0 at the north edge."""
    return [round(float(xy[0]), 3), round(float(field.size_px - 1 - xy[1]), 3)]


def _position_fields(m, floor, field):
    """Measured position and its error (fit error + field-star floor); null when unmeasured or
    when there are too few reference stars to know the real error."""
    if m is None or m.measured is None or floor is None:
        return {"target_expected_px": _web_point(m.expected, field) if m else None,
                "target_measured_px": None, "target_measured_err_px": None}
    error = frame_position_error(m, floor)
    return {"target_expected_px": _web_point(m.expected, field),
            "target_measured_px": _web_point(m.measured, field),
            "target_measured_err_px": [round(error[0], 3), round(error[1], 3)]}


def _visit_position(measurements, floor, shared_floor, field):
    """Inverse-variance mean of one visit's measured positions, per axis. Its error adds the
    visit's shared error (visit_shared_floor), which averaging over frames doesn't reduce."""
    used = [m for m in measurements if m.measured is not None]
    if not used or floor is None:
        return None, None
    xy = np.array([m.measured for m in used])
    weights = 1 / np.array([frame_position_error(m, floor) for m in used]) ** 2
    mean = (xy * weights).sum(axis=0) / weights.sum(axis=0)
    error = np.hypot(1 / np.sqrt(weights.sum(axis=0)), shared_floor)
    return _web_point(mean, field), [round(float(e), 3) for e in error]


def _expected_grid(field, target, when):
    """Catalog position of the target at `when`, as FITS-orientation grid (x, y)."""
    if target is None:
        return field.center_px, field.center_px
    sky = apparent_positions(np.array([target.ra]), np.array([target.dec]), np.array([target.pmra]),
                             np.array([target.pmdec]), np.array([target.parallax]), target.ref_epoch, when)[0]
    return tuple(float(v) for v in field.wcs().world_to_pixel(sky))


def _add_field_size(path, size_px):
    sizes = set(json.loads(path.read_text())["sizes_px"]) if path.exists() else set()
    path.write_text(json.dumps({"sizes_px": sorted(sizes | {size_px})}))


def _date(mjd):
    return Time(mjd, format="mjd").isot[:10]


def _number(value, digits):
    """JSON-safe number with `digits` significant digits; None for missing or NaN."""
    if value is None or not np.isfinite(value):
        return None
    return float(f"{value:.{digits}g}")
