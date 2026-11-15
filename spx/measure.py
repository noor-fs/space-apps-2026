"""Measure the target in every frame: position, brightness, saturation; then its motion.

Positions are measured on the cleaned frames in their own pixels (resampling smooths them)
and converted to the field grid through each frame's WCS. The real position error comes from
Gaia field stars measured the same way: their scatter around Gaia's prediction includes WCS
errors that the fit error alone misses.
"""
import warnings
from dataclasses import dataclass

import astropy.units as u
import numpy as np
from astropy.coordinates import GCRS, Distance, SkyCoord
from astropy.modeling import fitting, models
from astropy.table import Table
from astropy.time import Time
from astropy.utils.exceptions import AstropyUserWarning
from erfa import ErfaWarning

from spx.archive import gaia_query
from spx.clean import CLEAN, SATURATED
from spx.cutouts import field_dir, wavelength_at
from spx.field import PIXEL_SCALE_ARCSEC

STAMP_HALF = 3  # fit a 7 x 7 pixel stamp
APERTURE_R = 2.0  # px; aperture photometry radius
ANNULUS = (5.0, 9.0)  # px; local background ring
PSF_SIGMA_PX = 0.55  # starting guess: FWHM ~7.5" / 6.15"/px / 2.355
MAX_WANDER_PX = 1.5  # a fit that ends farther than this from the start is rejected
MIN_SNR = 5.0  # below this, no position or flux is reported

REF_MAX_G = 17.0  # Gaia reference stars: bright enough to measure well...
REF_MAX_RUWE = 1.4  # ...with clean Gaia astrometry...
REF_ISOLATION_ARCSEC = 15.0  # ...no other Gaia source this close...
REF_MIN_TARGET_SEP_ARCSEC = 20.0  # ...and not the target's neighbors
REF_MIN_SNR = 20.0
# A Gaia source this close to the target can't be told apart from it at SPHEREx resolution
# (RW Aur B: 0.24 px), so the identity check treats it as part of the target
BLEND_RADIUS_PX = 0.5
NEIGHBOR_MARGIN_PX = 1.0  # neighbors this far outside the fit stamp still spill light into it (PSF sigma ~0.55 px);
# farther out a neighbor has no pixels to pin its brightness, and its free Gaussian distorts the fit
# Only neighbors at most this much fainter than the target (Gaia G) are fitted. Fainter ones
# can't move a centroid, and a free Gaussian there soaks up the mismatch between a Gaussian and
# a bright star's real PSF instead (RW Aur, Barnard's Star got worse). Targets without a Gaia G
# (CatWISE-only, e.g. WISE 0855) keep every neighbor.
NEIGHBOR_MAX_DMAG = 3.0
SR_PER_PIXEL = ((PIXEL_SCALE_ARCSEC * u.arcsec) ** 2).to_value(u.sr)


@dataclass
class Point:
    x: float  # frame pixels, 0-based
    y: float
    x_err: float  # fit errors, px
    y_err: float
    flux_mjy: float  # aperture flux (r = APERTURE_R), not corrected for light outside it
    flux_err_mjy: float
    snr: float


def measure_point(image, variance, x0, y0, neighbors=()):
    """Centroid and aperture flux of a point source near (x0, y0); None if not measurable.

    neighbors: (x, y) pixel positions of known sources near it (from a catalog). Each gets its
    own Gaussian, fixed at that position with free brightness and the target's width, so a
    close neighbor neither pulls the centroid nor adds to the flux: the target's flux is the
    aperture sum minus the fitted neighbors' light inside the aperture.

    Not measurable: off the image, a NaN inside the aperture, local background unknown,
    S/N below MIN_SNR, or a fit that fails or wanders off.
    """
    ny, nx = image.shape
    xc, yc = int(round(x0)), int(round(y0))
    if not (STAMP_HALF <= xc < nx - STAMP_HALF and STAMP_HALF <= yc < ny - STAMP_HALF):
        return None
    yy, xx = np.mgrid[0:ny, 0:nx]
    r2 = (xx - x0) ** 2 + (yy - y0) ** 2
    aperture = r2 <= APERTURE_R ** 2
    if not (np.isfinite(image[aperture]).all() and np.isfinite(variance[aperture]).all()):
        return None
    ring = (r2 >= ANNULUS[0] ** 2) & (r2 <= ANNULUS[1] ** 2) & np.isfinite(image)
    if ring.sum() < 20:
        return None
    background = np.median(image[ring])
    net = np.sum(image[aperture] - background)
    noise = np.sqrt(np.sum(variance[aperture]))
    if net / noise < MIN_SNR:  # target and neighbors together: nothing worth fitting
        return None

    window = np.s_[yc - STAMP_HALF:yc + STAMP_HALF + 1, xc - STAMP_HALF:xc + STAMP_HALF + 1]
    usable = np.isfinite(image[window]) & np.isfinite(variance[window]) & (variance[window] > 0)
    sy, sx = np.mgrid[window]
    data = image[window] - background
    peak = max(data[usable].max(), 1e-6)
    model = models.Gaussian2D(amplitude=peak, x_mean=x0, y_mean=y0,
                              x_stddev=PSF_SIGMA_PX, y_stddev=PSF_SIGMA_PX)
    model.x_stddev.bounds = model.y_stddev.bounds = (0.2, 2.0)
    for nx_, ny_ in neighbors:
        neighbor = models.Gaussian2D(amplitude=peak / 2, x_mean=nx_, y_mean=ny_,
                                     x_stddev=PSF_SIGMA_PX, y_stddev=PSF_SIGMA_PX)
        neighbor.x_mean.fixed = neighbor.y_mean.fixed = True
        neighbor.amplitude.bounds = (0, None)
        model = model + neighbor
    if len(neighbors):
        for i in range(1, len(neighbors) + 1):
            getattr(model, f"x_stddev_{i}").tied = lambda m: m.x_stddev_0
            getattr(model, f"y_stddev_{i}").tied = lambda m: m.y_stddev_0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", AstropyUserWarning)
        try:
            fit = fitting.TRFLSQFitter(calc_uncertainties=True)(
                model, sx[usable], sy[usable], data[usable], weights=1 / np.sqrt(variance[window][usable]))
        except Exception:
            return None
    target = fit[0] if len(neighbors) else fit
    if fit.stds is None or np.hypot(target.x_mean.value - x0, target.y_mean.value - y0) > MAX_WANDER_PX:
        return None
    if len(neighbors):
        net -= sum(fit[i](xx[aperture], yy[aperture]).sum() for i in range(1, len(neighbors) + 1))
        if net / noise < MIN_SNR:
            return None
    suffix = "_0" if len(neighbors) else ""
    stds = dict(zip(fit.stds.param_names, fit.stds.stds))
    to_mjy = SR_PER_PIXEL * 1e9  # MJy/sr summed over pixels -> mJy
    return Point(float(target.x_mean.value), float(target.y_mean.value), float(stds["x_mean" + suffix]),
                 float(stds["y_mean" + suffix]), float(net * to_mjy), float(noise * to_mjy), float(net / noise))


def apparent_positions(ra, dec, pmra, pmdec, parallax, ref_epoch, when):
    """Where catalog stars appear at `when` from Earth: proper motion plus parallax.

    SPHEREx orbits Earth, so the Earth-centered (geocentric) view is close enough. Arrays in;
    unknown parallax (nan or <= 0) means "far away": proper motion only.
    """
    parallax = np.where(np.isfinite(parallax) & (parallax > 0), parallax, 1e-3)
    pmra, pmdec = np.nan_to_num(pmra), np.nan_to_num(pmdec)
    star = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, distance=Distance(parallax=parallax * u.mas),
                    pm_ra_cosdec=pmra * u.mas / u.yr, pm_dec=pmdec * u.mas / u.yr, obstime=ref_epoch)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ErfaWarning)
        moved = star.apply_space_motion(new_obstime=when)
        flat = SkyCoord(ra=moved.ra, dec=moved.dec)
        near = moved.transform_to(GCRS(obstime=when))
        far = flat.transform_to(GCRS(obstime=when))
    dlon, dlat = far.spherical_offsets_to(near)
    return flat.spherical_offsets_by(dlon, dlat)


def target_position(target, field, when):
    """Catalog position of the target at `when` (proper motion and parallax); the field center
    when there is no catalog target (typed coordinates)."""
    if target is None:
        return field.center
    return apparent_positions(np.array([target.ra]), np.array([target.dec]), np.array([target.pmra]),
                              np.array([target.pmdec]), np.array([target.parallax]), target.ref_epoch, when)[0]


def gaia_sources(field):
    """Every Gaia DR3 source brighter than G = 20 in and around the field (cached per field)."""
    path = field_dir(field) / "gaia_reference_stars.ecsv"
    if path.exists():
        return Table.read(path)
    radius = field.width_deg / np.sqrt(2) + 0.01
    table = gaia_query(f"""SELECT source_id, ra, dec, pmra, pmdec, parallax, phot_g_mean_mag, ruwe
        FROM gaiadr3.gaia_source WHERE phot_g_mean_mag < 20 AND 1 = CONTAINS(POINT(ra, dec),
        CIRCLE({field.center.ra.deg}, {field.center.dec.deg}, {radius}))""")
    path.parent.mkdir(parents=True, exist_ok=True)
    table.write(path, overwrite=True)
    return table


def reference_stars(field, target_coord):
    """Isolated Gaia DR3 stars with clean astrometry in and around the field."""
    table = gaia_sources(field)
    coords = SkyCoord(table["ra"], table["dec"], unit="deg")
    keep = [i for i, row in enumerate(table)
            if not np.ma.is_masked(row["pmra"]) and row["phot_g_mean_mag"] <= REF_MAX_G
            and row["ruwe"] <= REF_MAX_RUWE
            and coords[i].separation(target_coord).arcsec >= REF_MIN_TARGET_SEP_ARCSEC
            and np.sum(coords[i].separation(coords).arcsec < REF_ISOLATION_ARCSEC) == 1]
    return table[keep]


def gaia_positions(table, when):
    """Apparent positions of Gaia DR3 rows at `when`; missing motions or parallax count as zero."""
    def column(name):
        return np.ma.filled(np.ma.asarray(table[name], dtype=float), np.nan)
    return apparent_positions(column("ra"), column("dec"), column("pmra"), column("pmdec"),
                              column("parallax"), Time(2016.0, format="jyear"), when)


@dataclass
class FrameMeasurement:
    mjd: float  # mid-exposure
    detector: int | tuple  # a tuple of detectors for a visit fit (psf.measure_visits)
    expected: tuple  # (x, y) on the field grid (FITS orientation, 0-based)
    measured: tuple | None  # (x, y) on the field grid; None if not measurable
    measured_fit_err: tuple | None  # (x, y) fit error in px, before adding the field-star floor
    saturated: bool  # a saturated pixel within the aperture
    flux_mjy: float | None
    flux_err_mjy: float | None
    snr: float | None
    wavelength_um: float  # at the target's expected position; nan if off the detector
    bandwidth_um: float
    reference_residuals: list  # (dx, dy) grid px, measured minus Gaia, for each reference star
    reference_fluxes: dict  # Gaia source_id -> (flux_mjy, flux_err_mjy, wavelength_um), unsaturated only


def measure_frame(frame, field, target, references, wave_table, catalog=None):
    """Measure the target and the reference stars in one clean.CleanFrame.

    target: names.CatalogSource, or None to measure whatever sits at the field center.
    wave_table: path from cutouts.wavelength_table for this frame; None for a stack.
    catalog: gaia_sources(field). With a target, a fit that ends closer to another Gaia source
    than to the target measured that source, not the target, and is dropped. This happens when
    the target is too faint at a frame's wavelength (WISE 0855 below 3 um) and a neighbor isn't.
    """
    when = Time(frame.header["MJD-AVG"], format="mjd")
    grid = field.wcs()
    if target is None:
        expected_sky = field.center
    else:
        expected_sky = apparent_positions(np.array([target.ra]), np.array([target.dec]),
                                          np.array([target.pmra]), np.array([target.pmdec]),
                                          np.array([target.parallax]), target.ref_epoch, when)[0]
    expected = tuple(float(v) for v in grid.world_to_pixel(expected_sky))
    x0, y0 = (float(v) for v in frame.wcs.world_to_pixel(expected_sky))

    wavelength = bandwidth = np.nan
    if wave_table is not None:
        wavelength, bandwidth = (float(v) for v in wavelength_at(frame.header, wave_table, x0, y0))
    yy, xx = np.indices(frame.image.shape)

    def saturated_near(x, y):
        return bool((frame.flag_class[(xx - x) ** 2 + (yy - y) ** 2 <= APERTURE_R ** 2] == SATURATED).any())

    saturated = saturated_near(x0, y0)
    neighbors = []
    if target is not None and catalog is not None:
        neighbors = _neighbors_near(frame.wcs, x0, y0, expected_sky, catalog, target, when)
    point = measure_point(frame.image, frame.variance, x0, y0, neighbors)
    measured = fit_err = None
    if point is not None:
        measured = tuple(float(v) for v in grid.world_to_pixel(frame.wcs.pixel_to_world(point.x, point.y)))
        fit_err = (point.x_err, point.y_err)  # frame and grid pixels are the same size
        if target is not None and catalog is not None and _closer_to_neighbor(
                measured, expected, catalog, target, grid, when):
            point = measured = fit_err = None

    residuals, fluxes = [], {}
    if len(references):
        predicted = gaia_positions(references, when)
        for source_id, sky in zip(references["source_id"], predicted):
            rx, ry = (float(v) for v in frame.wcs.world_to_pixel(sky))
            star = measure_point(frame.image, frame.variance, rx, ry)
            if star is None or star.snr < REF_MIN_SNR:
                continue
            mx, my = grid.world_to_pixel(frame.wcs.pixel_to_world(star.x, star.y))
            px, py = grid.world_to_pixel(sky)
            residuals.append((float(mx - px), float(my - py)))
            if wave_table is not None and not saturated_near(rx, ry):
                star_um = float(wavelength_at(frame.header, wave_table, star.x, star.y)[0])
                fluxes[str(source_id)] = (star.flux_mjy, star.flux_err_mjy, star_um)
    return FrameMeasurement(when.mjd, _detector(frame.header["DETECTOR"]), expected, measured, fit_err,
                            saturated, point and point.flux_mjy, point and point.flux_err_mjy,
                            point and point.snr, wavelength, bandwidth, residuals, fluxes)


def _detector(value):
    return value if isinstance(value, tuple) else int(value)


def _neighbors_near(wcs, x0, y0, expected_sky, catalog, target, when):
    """Pixel positions of Gaia sources (not the target, not blended with it) near (x0, y0)."""
    is_target = np.array([str(i) == target.source_id for i in catalog["source_id"]])
    others = catalog[~is_target]
    if is_target.any():
        target_g = float(catalog["phot_g_mean_mag"][is_target][0])
        others = others[np.asarray(others["phot_g_mean_mag"], dtype=float) <= target_g + NEIGHBOR_MAX_DMAG]
    if not len(others):
        return []
    sky = gaia_positions(others, when)
    resolved = sky.separation(expected_sky).arcsec > BLEND_RADIUS_PX * PIXEL_SCALE_ARCSEC
    x, y = (np.atleast_1d(v) for v in wcs.world_to_pixel(sky))
    near = resolved & (np.maximum(np.abs(x - x0), np.abs(y - y0)) <= STAMP_HALF + NEIGHBOR_MARGIN_PX)
    return [(float(a), float(b)) for a, b in zip(x[near], y[near])]


def _closer_to_neighbor(measured, expected, catalog, target, grid, when):
    others = catalog[[str(i) != target.source_id for i in catalog["source_id"]]]
    if not len(others):
        return False
    x, y = grid.world_to_pixel(gaia_positions(others, when))
    resolved = np.hypot(x - expected[0], y - expected[1]) > BLEND_RADIUS_PX
    if not resolved.any():
        return False
    to_neighbor = np.min(np.hypot(x[resolved] - measured[0], y[resolved] - measured[1]))
    return bool(to_neighbor < np.hypot(measured[0] - expected[0], measured[1] - expected[1]))


def robust_sigma(values):
    values = np.asarray(values, dtype=float)
    return float(1.4826 * np.median(np.abs(values - np.median(values))))


def position_floor(measurements):
    """Real per-frame position error (x, y) in px: scatter of reference stars around Gaia."""
    residuals = np.array([r for m in measurements for r in m.reference_residuals])
    if len(residuals) < 10:
        return None
    return robust_sigma(residuals[:, 0]), robust_sigma(residuals[:, 1])


# Positions within one visit share part of their error: reference stars' mean residual shifts by
# ~0.02 px from visit to visit (Eps Indi B 0.017/0.016, Barnard's Star 0.021/0.031, RW Aur 0.025/0.007).
# Used when fewer than MIN_FLOOR_VISITS visits have reference stars to measure it.
DEFAULT_VISIT_FLOOR_PX = (0.02, 0.02)
MIN_FLOOR_VISITS = 3


def visit_shared_floor(measurements, visit_numbers):
    """(x, y) px error shared by all positions in one visit, which averaging frames can't reduce:
    scatter between visits of the reference stars' mean residual (DEFAULT_VISIT_FLOOR_PX if too
    few visits to measure it)."""
    means = []
    for n in np.unique(visit_numbers):
        residuals = [r for m, v in zip(measurements, visit_numbers) if v == n for r in m.reference_residuals]
        if residuals:
            means.append(np.mean(residuals, axis=0))
    if len(means) < MIN_FLOOR_VISITS:
        return DEFAULT_VISIT_FLOOR_PX
    return tuple(float(s) for s in np.std(means, axis=0, ddof=1))


def frame_position_error(measurement, floor):
    """Fit error and field-star floor added in quadrature, per axis."""
    return tuple(float(np.hypot(e, f)) for e, f in zip(measurement.measured_fit_err, floor))
