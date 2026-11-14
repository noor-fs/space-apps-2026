"""SPHEREx's own PSF model, and fits of a faint target together with its known neighbors.

Each full cutout carries an EPSF table: 441 PSFs on a 21 x 21 grid of zones over the detector,
each 33 x 33 samples at 5x the pixel resolution, normalized to sum to 1. It is a calibration
product (one per detector, named in the IMAGE header as '[CALIB] epsf <id>'), so like the
wavelength table it is downloaded once and kept.

Fitting follows forced photometry as in crowdsource (Schlafly et al. 2018) and Tractor (Lang,
Hogg & Schlegel 2016), which the SPHEREx pipeline also uses (Akeson et al., arXiv:2511.15823,
Sect. IV.3): every known source near the target is modeled with the PSF at its catalog position,
fluxes and a constant background are fitted together, so a neighbor's light can't pull the
target's position.
"""
import io
from dataclasses import dataclass
from functools import lru_cache

import astropy.units as u
import numpy as np
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from scipy.ndimage import map_coordinates
from scipy.optimize import minimize

from spx.cutouts import CACHE_DIR, _get, _without_distortion, cutout_url

OVERSAMPLE = 5
PSF_CENTER = 16  # middle sample of the 33 x 33 array
STAMP_RADIUS_PX = 3  # fit a 7 x 7 stamp (the PSF core is ~2 px wide)
NEIGHBOR_MARGIN_PX = 2  # catalog sources this far outside the stamp still put light in it
MIN_USABLE_SHARE = 0.6  # a frame needs this share of its stamp usable
MAX_OFFSET_ARCSEC = 9.0  # search the source this far (~1.5 px) from its predicted track
GRID_STEP_ARCSEC = 3.0  # coarse search before refining, so a neighbor's peak (>= 8" away) can't trap the fit
HESSIAN_STEP_ARCSEC = 0.3
# Injected copies of WISE 0855 next to its G = 16.3 neighbor were recovered with errors 1.2-1.4x
# the fit's (pulls); in blank sky 1.0x (decisions.md). Visit-fit errors are scaled by the blended value.
INJECTION_ERROR_SCALE = 1.4


def psf_calibration_id(header):
    for line in header.get("HISTORY", []):
        if "[CALIB] epsf" in line:
            return line.split()[-1]
    return None


def psf_table(header, frame_row, field):
    """Path to the EPSF table named in this frame's header, downloaded once (needs the frame's
    uri for that); None if not cached and no uri is given."""
    calibration_id = psf_calibration_id(header)
    if calibration_id is None:
        raise ValueError("no '[CALIB] epsf' line in the IMAGE header")
    path = CACHE_DIR / "psf" / f"{calibration_id}.fits"
    if not path.exists():
        if frame_row is None:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        with fits.open(io.BytesIO(_get(cutout_url(frame_row["uri"], field)).content)) as full:
            fits.HDUList([fits.PrimaryHDU(), full["EPSF"].copy()]).writeto(path)
    return path


class PSFModel:
    """The PSF for one frame: the zone nearest the given cutout position.

    Used as sampled values (times 25, the sub-samples per pixel). On 339 bright-star fits this
    fit best: median reduced chi2 1.75, against 2.43 transposed and 3.45 integrated over each
    pixel (decisions.md), as expected for an 'effective' PSF, which already includes the pixel.
    """

    def __init__(self, header, table_path, x, y):
        detector_x, detector_y = WCS(_without_distortion(header), key="A").pixel_to_world_values(x, y)
        centers, psfs = _load_table(str(table_path))
        self.psf = psfs[np.argmin(np.hypot(centers[:, 0] - detector_x, centers[:, 1] - detector_y))]

    def render(self, x0, y0, xx, yy):
        """Share of a source's light at (x0, y0) falling in each pixel (xx, yy), cutout pixels."""
        rows = PSF_CENTER + (np.asarray(yy) - y0) * OVERSAMPLE
        cols = PSF_CENTER + (np.asarray(xx) - x0) * OVERSAMPLE
        return map_coordinates(self.psf, [rows, cols], order=3, mode="constant", cval=0.0) * OVERSAMPLE ** 2


@lru_cache(maxsize=16)
def _load_table(path):
    """(zone centers, PSFs) of one EPSF table, read once per run."""
    with fits.open(path) as hdul:
        table = hdul["EPSF"].data
        return (np.column_stack([table["XCENTER"], table["YCENTER"]]).astype(float),
                np.array(table["EPSF"], dtype=float))


@dataclass
class _Prepared:
    """One frame, ready for fitting one source near a predicted position."""
    data: np.ndarray  # usable stamp pixels, flattened
    weight: np.ndarray  # 1 / sigma
    xx: np.ndarray
    yy: np.ndarray
    psf: PSFModel
    fixed: np.ndarray  # one column per neighbor (its PSF at its catalog position) plus background
    origin: np.ndarray  # predicted source position (cutout px)
    jacobian: np.ndarray  # cutout px per arcsec of (RA*, Dec) offset
    detector: int


def _prepare(frame, psf_path, predicted, neighbors):
    """Stamp around the predicted position; None if it is off the cutout or mostly unusable."""
    x0, y0 = (float(v) for v in frame.wcs.world_to_pixel(predicted))
    cx, cy = int(round(x0)), int(round(y0))
    yy, xx = np.mgrid[cy - STAMP_RADIUS_PX:cy + STAMP_RADIUS_PX + 1, cx - STAMP_RADIUS_PX:cx + STAMP_RADIUS_PX + 1]
    inside = (yy >= 0) & (xx >= 0) & (yy < frame.image.shape[0]) & (xx < frame.image.shape[1])
    if inside.mean() < MIN_USABLE_SHARE:
        return None
    yy, xx = yy[inside], xx[inside]
    data, variance = frame.image[yy, xx], frame.variance[yy, xx]
    usable = np.isfinite(data) & np.isfinite(variance) & (variance > 0)
    if usable.sum() < MIN_USABLE_SHARE * (2 * STAMP_RADIUS_PX + 1) ** 2:
        return None
    xx, yy, data, variance = xx[usable], yy[usable], data[usable], variance[usable]
    psf = PSFModel(frame.header, psf_path, x0, y0)
    columns = []
    for sky in neighbors:
        nx, ny = (float(v) for v in frame.wcs.world_to_pixel(sky))
        if abs(nx - x0) <= STAMP_RADIUS_PX + NEIGHBOR_MARGIN_PX and abs(ny - y0) <= STAMP_RADIUS_PX + NEIGHBOR_MARGIN_PX:
            columns.append(psf.render(nx, ny, xx, yy))
    columns.append(np.ones_like(data))
    east = predicted.spherical_offsets_by(1 * u.arcsec, 0 * u.arcsec)
    north = predicted.spherical_offsets_by(0 * u.arcsec, 1 * u.arcsec)
    jacobian = np.column_stack([np.array(frame.wcs.world_to_pixel(east), dtype=float) - (x0, y0),
                                np.array(frame.wcs.world_to_pixel(north), dtype=float) - (x0, y0)])
    return _Prepared(data, 1 / np.sqrt(variance), xx, yy, psf, np.column_stack(columns),
                     np.array([x0, y0]), jacobian, int(frame.header["DETECTOR"]))


def _chi2(prepared, offset, with_source=True):
    """Total chi2 over frames with the source at predicted + offset (arcsec RA*, Dec); its flux,
    the neighbors' fluxes and the background are solved by weighted least squares in each frame."""
    total = 0.0
    for p in prepared:
        x, y = p.origin + p.jacobian @ offset
        design = np.column_stack([p.psf.render(x, y, p.xx, p.yy), p.fixed]) if with_source else p.fixed
        weighted = design * p.weight[:, None]
        coefficients, *_ = np.linalg.lstsq(weighted, p.data * p.weight, rcond=None)
        total += float(np.sum((p.data * p.weight - weighted @ coefficients) ** 2))
    return total


@dataclass
class VisitFit:
    offset: np.ndarray  # arcsec (RA*, Dec) from the predicted track
    offset_err: np.ndarray  # arcsec
    snr: float  # sqrt(chi2 without the source - chi2 with it)
    n_frames: int
    detectors: tuple
    at_edge: bool  # best offset on the search limit: not trustworthy


def fit_visit(frames, psf_paths, predicted, neighbors):
    """Position of one source in one visit, from all its frames at once.

    frames: clean.CleanFrame list; psf_paths: matching PSF table paths; predicted: the source's
    predicted SkyCoord at each frame's time; neighbors: per frame, SkyCoords of other catalog
    sources at that time. One offset from the predicted track is shared by all frames (the track
    already includes motion during the visit); fluxes are free per frame, so frames at
    wavelengths where the source is invisible add nothing. Errors from the chi2 curvature,
    scaled up when the fit is worse than the noise. None if no frame can be used.
    """
    prepared = [p for p in (_prepare(f, path, sky, near) for f, path, sky, near
                            in zip(frames, psf_paths, predicted, neighbors) if path is not None) if p is not None]
    if not prepared:
        return None
    grid = np.arange(-MAX_OFFSET_ARCSEC, MAX_OFFSET_ARCSEC + 1e-9, GRID_STEP_ARCSEC)
    start = min(((a, b) for a in grid for b in grid if np.hypot(a, b) <= MAX_OFFSET_ARCSEC),
                key=lambda o: _chi2(prepared, np.array(o)))
    start = np.array(start, dtype=float)
    # Explicit first steps: Nelder-Mead's default steps are 5% of the start, i.e. none at (0, 0)
    simplex = [start, start + (GRID_STEP_ARCSEC / 2, 0), start + (0, GRID_STEP_ARCSEC / 2)]
    best = minimize(lambda o: _chi2(prepared, o), start, method="Nelder-Mead",
                    options={"xatol": 0.01, "fatol": 0.01, "initial_simplex": simplex}).x
    chi2_best = _chi2(prepared, best)
    n_pixels = sum(len(p.data) for p in prepared)
    n_parameters = 2 + sum(p.fixed.shape[1] + 1 for p in prepared)
    scale = max(1.0, chi2_best / max(n_pixels - n_parameters, 1))
    try:
        err = np.sqrt(np.diag(2 * np.linalg.inv(_hessian(lambda o: _chi2(prepared, o), best)) * scale))
    except np.linalg.LinAlgError:
        err = np.array([np.inf, np.inf])
    if not np.all(np.isfinite(err)):
        err = np.array([np.inf, np.inf])
    snr = float(np.sqrt(max(_chi2(prepared, best, with_source=False) - chi2_best, 0.0)))
    return VisitFit(best, err, snr, len(prepared), tuple(sorted({p.detector for p in prepared})),
                    bool(np.hypot(*best) > MAX_OFFSET_ARCSEC - GRID_STEP_ARCSEC / 2))


def _hessian(function, x, step=HESSIAN_STEP_ARCSEC):
    n = len(x)
    hessian = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            ei, ej = np.eye(n)[i] * step, np.eye(n)[j] * step
            hessian[i, j] = (function(x + ei + ej) - function(x + ei - ej)
                             - function(x - ei + ej) + function(x - ei - ej)) / (4 * step ** 2)
    return hessian


def measure_visits(paths, frame_rows, field, target, ranges, catalog, references, min_snr=5.0):
    """One position per visit for the target (and, the same way, each reference star), from the
    joint PSF fit, as FrameMeasurements for verdict.measure_motion.

    For targets too faint to measure in single frames. Frames are loaded one visit at a time.
    paths: cutout paths; frame_rows: {path stem: frames-table row} (to fetch missing PSF tables).
    """
    from spx.clean import clean_frame
    from spx.measure import BLEND_RADIUS_PX, FrameMeasurement, gaia_positions, target_position
    from spx.field import PIXEL_SCALE_ARCSEC
    from spx.visits import visit_of

    headers = [fits.getheader(path, "IMAGE") for path in paths]
    visits = visit_of([h["MJD-AVG"] for h in headers], ranges)
    grid = field.wcs()
    measurements = []
    for n in np.unique(visits):
        members = np.flatnonzero(visits == n)
        frames = [clean_frame(paths[i]) for i in members]
        psf_paths = [psf_table(f.header, frame_rows.get(paths[i].stem), field) for f, i in zip(frames, members)]
        times = [Time(f.header["MJD-AVG"], format="mjd") for f in frames]
        mean_time = Time(np.mean([t.mjd for t in times]), format="mjd")
        catalog_at = [gaia_positions(catalog, t) for t in times]

        predicted = [target_position(target, field, t) for t in times]
        # Gaia sources that ARE the target (or blend with it) aren't neighbors
        neighbors = [near[near.separation(p).arcsec > BLEND_RADIUS_PX * PIXEL_SCALE_ARCSEC]
                     for near, p in zip(catalog_at, predicted)]
        fit = fit_visit(frames, psf_paths, predicted, neighbors)
        expected_sky = target_position(target, field, mean_time)
        expected = tuple(float(v) for v in grid.world_to_pixel(expected_sky))
        measured = error = None
        if fit is not None and fit.snr >= min_snr and not fit.at_edge and np.all(np.isfinite(fit.offset_err)):
            sky = expected_sky.spherical_offsets_by(fit.offset[0] * u.arcsec, fit.offset[1] * u.arcsec)
            measured = tuple(float(v) for v in grid.world_to_pixel(sky))
            error = tuple(float(e) * INJECTION_ERROR_SCALE / PIXEL_SCALE_ARCSEC for e in fit.offset_err)

        residuals = []
        for k in range(len(references)):
            one = references[k:k + 1]
            ref_predicted = [gaia_positions(one, t)[0] for t in times]
            others = [near[catalog["source_id"] != one["source_id"][0]] for near in catalog_at]
            ref_fit = fit_visit(frames, psf_paths, ref_predicted, others)
            if ref_fit is None or ref_fit.snr < 20 or ref_fit.at_edge:
                continue
            at_mean = gaia_positions(one, mean_time)[0]
            moved = at_mean.spherical_offsets_by(ref_fit.offset[0] * u.arcsec, ref_fit.offset[1] * u.arcsec)
            mx, my = grid.world_to_pixel(moved)
            px, py = grid.world_to_pixel(at_mean)
            residuals.append((float(mx - px), float(my - py)))
        measurements.append(FrameMeasurement(
            mean_time.mjd, fit.detectors if fit else (), expected, measured, error, False,
            None, None, fit.snr if fit else None, np.nan, np.nan, residuals, {}))
        print(f"  visit {n}: {len(frames)} frames, target S/N {fit.snr if fit else 0:.1f}, "
              f"offset {np.round(fit.offset, 2) if fit else None}\", {len(residuals)} reference stars")
    return measurements
