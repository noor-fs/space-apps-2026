"""From per-frame measurements to answers: does the target move, does its brightness change?

Motion: a straight line through the measured positions over time, in RA and Dec separately,
after removing the parallax wobble the catalog predicts. Errors per frame are the fit error plus
the field-star floor (measure.position_floor).

Brightness: frames are at different wavelengths, so raw fluxes mix color with change. The model
is log(flux) = wavelength-bin effect + visit effect. The bin effects absorb the spectrum; the
visit effects are the brightness changes. Gaia reference stars run through the same model give
the calibration floor between visits.
"""
from dataclasses import dataclass

import astropy.units as u
import numpy as np
from astropy.time import Time
from scipy import stats

from spx.field import CENTER_DATE, PIXEL_SCALE_ARCSEC
from spx.measure import apparent_positions, frame_position_error, position_floor, robust_sigma
from spx.visits import visit_of

THREE_SIGMA_P = 0.0027  # two-sided p-value of a 3-sigma result
# A smaller shift is not called motion, however significant: the light center of an unresolved
# blend moves when the stars' brightness ratio changes (RW Aur: 0.07 px), and visits seen with
# different detector mixes put the center of a colored source in slightly different places.
MIN_SHIFT_PX = 0.25
# "No motion" is only a result if the fit could have seen a shift this large (3 sigma)
MAX_UNDETECTABLE_SHIFT_PX = 1.0
CLIP_SIGMA = 5.0  # positions this far off the fitted line (after error scaling) are dropped
MIN_FRAMES = 3
BIN_FRACTION = 0.5  # wavelength bins are this share of the local bandwidth
MIN_REFERENCE_FRAMES = 10


@dataclass
class MotionFit:
    pmra: float  # mas/yr, includes cos(dec)
    pmra_err: float
    pmdec: float
    pmdec_err: float
    n_used: int
    n_rejected: int
    baseline_yr: float
    error_scale: tuple  # (RA, Dec) factor the errors were inflated by when the line didn't fit
    detection_chi2: float  # measured motion vs zero, 2 degrees of freedom
    catalog_chi2: float | None  # measured motion vs the catalog's; None without a catalog motion

    @property
    def shift_px(self):
        """Distance moved over the measured time span, in pixels."""
        return float(np.hypot(self.pmra, self.pmdec) / 1000 * self.baseline_yr / PIXEL_SCALE_ARCSEC)

    @property
    def constrained(self):
        """True if a shift of MAX_UNDETECTABLE_SHIFT_PX over the time span would be detected."""
        error_px = max(self.pmra_err, self.pmdec_err) / 1000 * self.baseline_yr / PIXEL_SCALE_ARCSEC
        return 3 * error_px <= MAX_UNDETECTABLE_SHIFT_PX

    @property
    def detected(self):
        return stats.chi2.sf(self.detection_chi2, 2) < THREE_SIGMA_P and self.shift_px >= MIN_SHIFT_PX

    @property
    def matches_catalog(self):
        return self.catalog_chi2 is not None and stats.chi2.sf(self.catalog_chi2, 2) >= THREE_SIGMA_P


def measure_motion(frame_measurements, stack_measurements, field, target):
    """Motion from single frames; from visit stacks when frames can't constrain it.

    Returns (MotionFit or None, "frames" or "stacks"). Each set uses its own position floor
    (reference stars measured the same way). stack_measurements may be None (not built yet).
    """
    from_frames = fit_motion(frame_measurements, field, target, position_floor(frame_measurements))
    if (from_frames is not None and from_frames.constrained) or not stack_measurements:
        return from_frames, "frames"
    from_stacks = fit_motion(stack_measurements, field, target, position_floor(stack_measurements))
    if from_stacks is not None and (from_frames is None or from_stacks.constrained):
        return from_stacks, "stacks"
    return from_frames, "frames"


def fit_motion(measurements, field, target, floor):
    """Proper motion from the measured positions; None if fewer than MIN_FRAMES are measured."""
    used = [m for m in measurements if m.measured is not None]
    if len(used) < MIN_FRAMES or floor is None:
        return None
    grid = field.wcs()
    when = Time([m.mjd for m in used], format="mjd")
    sky = grid.pixel_to_world(*np.array([m.measured for m in used]).T)
    dra, ddec = field.center.spherical_offsets_to(sky)
    offsets = np.column_stack([dra.to_value(u.arcsec), ddec.to_value(u.arcsec)])
    if target is not None and target.parallax > 0:
        offsets -= _parallax_shift(field, target.parallax, when)
    # Grid x runs along -RA and y along Dec, and grid pixels are PIXEL_SCALE_ARCSEC wide
    errors = np.array([frame_position_error(m, floor) for m in used]) * PIXEL_SCALE_ARCSEC
    years = (when - Time(CENTER_DATE)).to_value(u.yr)

    keep = np.ones(len(used), bool)
    for _ in range(5):
        fits = [_line(years[keep], offsets[keep, a], errors[keep, a]) for a in (0, 1)]
        outliers = np.zeros(len(used), bool)
        for axis, (beta, cov, scale) in enumerate(fits):
            predicted = beta[0] + beta[1] * years
            outliers |= np.abs(offsets[:, axis] - predicted) / (errors[:, axis] * scale) > CLIP_SIGMA
        if np.array_equal(~outliers, keep) or (~outliers).sum() < MIN_FRAMES:
            break
        keep = ~outliers

    (ra_beta, ra_cov, ra_scale), (dec_beta, dec_cov, dec_scale) = fits
    pm = np.array([ra_beta[1], dec_beta[1]]) * 1000
    pm_err = np.sqrt([ra_cov[1, 1], dec_cov[1, 1]]) * 1000
    catalog_chi2 = None
    if target is not None:
        catalog_chi2 = float(np.sum(((pm - [target.pmra, target.pmdec]) / pm_err) ** 2))
    return MotionFit(float(pm[0]), float(pm_err[0]), float(pm[1]), float(pm_err[1]), int(keep.sum()),
                     int((~keep).sum()), float(np.ptp(years[keep])), (float(ra_scale), float(dec_scale)),
                     float(np.sum((pm / pm_err) ** 2)), catalog_chi2)


def _line(t, y, sigma):
    """Weighted straight-line fit. Errors are scaled up when the scatter exceeds them
    (reduced chi-square > 1): the line is then a worse description than the errors claim."""
    design = np.column_stack([np.ones_like(t), t])
    w = 1 / sigma ** 2
    cov = np.linalg.inv(design.T @ (design * w[:, None]))
    beta = cov @ design.T @ (w * y)
    dof = max(len(y) - 2, 1)
    scale = max(1.0, np.sqrt(np.sum(w * (y - design @ beta) ** 2) / dof))
    return beta, cov * scale ** 2, scale


def _parallax_shift(field, parallax, when):
    """(RA*, Dec) arcsec shift from parallax alone at each time, seen from Earth."""
    n = len(when)
    shifted = apparent_positions(np.full(n, field.center.ra.deg), np.full(n, field.center.dec.deg),
                                 np.zeros(n), np.zeros(n), np.full(n, parallax), when, when)
    dra, ddec = field.center.spherical_offsets_to(shifted)
    return np.column_stack([dra.to_value(u.arcsec), ddec.to_value(u.arcsec)])


@dataclass
class BrightnessTest:
    changes: dict  # detector -> {visit: (flux / mean over that detector's visits, relative error)}
    chi2: float  # all visit effects zero vs free
    dof: int
    extra_scatter: float  # relative scatter between frames beyond their noise
    calibration_floor: float  # relative, from reference stars; 0 without them
    n_frames: int

    @property
    def significant(self):
        return self.dof > 0 and stats.chi2.sf(self.chi2, self.dof) < THREE_SIGMA_P


def brightness_test(measurements, ranges, include_saturated=True):
    """Visit-to-visit brightness change of the target; None if no detector saw it in two visits."""
    usable = [m for m in measurements if m.flux_mjy is not None and m.flux_mjy > 0
              and np.isfinite(m.wavelength_um) and (include_saturated or not m.saturated)]
    rows = [(m.mjd, m.detector, m.wavelength_um, m.bandwidth_um, m.flux_mjy, m.flux_err_mjy) for m in usable]
    fitted = _visit_effects(rows, ranges)
    if fitted is None:
        return None
    floor = calibration_floor(measurements, ranges)
    groups, effect, cov, extra = fitted
    # Each (detector, visit) gets its own calibration error; effects are relative to the
    # detector's mean visit, so the floor is centered the same way within each detector
    floor_cov = floor ** 2 * _centering(groups)
    total = cov + floor_cov
    chi2 = float(effect @ np.linalg.pinv(total, hermitian=True) @ effect)
    dof = len(groups) - len({d for d, _ in groups})
    changes = {}
    for (d, v), e, var in zip(groups, effect, np.diag(total)):
        changes.setdefault(d, {})[v] = (float(np.exp(e)), float(np.sqrt(var)))
    return BrightnessTest(changes, chi2, dof, extra, floor, len(rows))


def calibration_floor(measurements, ranges):
    """Spread of visit effects of reference stars (constant, as far as we know): the share of
    visit-to-visit change that calibration alone produces. Robust, so a variable star among the
    references doesn't set it."""
    bandwidth_ratio = np.nanmedian([m.bandwidth_um / m.wavelength_um for m in measurements])
    per_star = {}
    for m in measurements:
        for source_id, (flux, flux_err, um) in m.reference_fluxes.items():
            if flux > 0 and np.isfinite(um):
                per_star.setdefault(source_id, []).append((m.mjd, m.detector, um, um * bandwidth_ratio,
                                                           flux, flux_err))
    effects = []
    for rows in per_star.values():
        if len(rows) >= MIN_REFERENCE_FRAMES:
            fitted = _visit_effects(rows, ranges)
            if fitted is not None:
                effects += list(fitted[1])
    return robust_sigma(effects) if len(effects) >= 5 else 0.0


def _visit_effects(rows, ranges):
    """Fit log(flux) = bin effect + (detector, visit) effect by weighted least squares.

    rows: (mjd, detector, wavelength_um, bandwidth_um, flux, flux_err). A bin is one detector and
    BIN_FRACTION of a bandwidth in wavelength. Each detector gets its own visit effects, because
    a star can change differently at different wavelengths (dust dims blue light more than red).
    Only bins seen in two or more visits say anything about change. Per detector, visits not
    linked to the others through shared bins are dropped.

    Returns ((detector, visit) groups, effects relative to the detector's mean visit, their
    covariance, extra relative scatter), or None if no detector has two linked visits.
    """
    if len(rows) < MIN_FRAMES:
        return None
    mjd, detector, um, bandwidth, flux, flux_err = (np.array(c, dtype=float) for c in zip(*rows))
    detector = detector.astype(int)
    visit = visit_of(mjd, ranges)
    width = BIN_FRACTION * np.median(bandwidth / um)
    bins = np.array([f"{d}:{int(np.floor(np.log(w) / width))}" for d, w in zip(detector, um)])

    keep = np.zeros(len(rows), bool)
    for d in np.unique(detector):
        on = detector == d
        linked = _linked_visits(visit[on], bins[on])
        if linked is not None:
            keep[np.flatnonzero(on)[linked]] = True
    if not keep.any():
        return None
    detector, visit, bins, flux, flux_err = detector[keep], visit[keep], bins[keep], flux[keep], flux_err[keep]

    groups = sorted({(int(d), int(v)) for d, v in zip(detector, visit)})
    references = {d: min(v for dd, v in groups if dd == d) for d, _ in groups}  # effect fixed at 0
    free = [g for g in groups if g[1] != references[g[0]]]
    bin_ids = sorted(set(bins))
    design = np.zeros((len(flux), len(bin_ids) + len(free)))
    for i, (b, d, v) in enumerate(zip(bins, detector, visit)):
        design[i, bin_ids.index(b)] = 1
        if (d, v) in free:
            design[i, len(bin_ids) + free.index((d, v))] = 1
    y = np.log(flux)
    noise = flux_err / flux

    extra = _extra_scatter(design, y, noise, len(y) - design.shape[1])
    beta, cov = _wls(design, y, np.hypot(noise, extra))
    # From "relative to the first visit" to "relative to the detector's mean visit"
    to_groups = np.zeros((len(groups), len(free)))
    for i, g in enumerate(groups):
        if g in free:
            to_groups[i, free.index(g)] = 1
    to_groups = (np.eye(len(groups)) - _centering(groups, mean_only=True)) @ to_groups
    effect = to_groups @ beta[len(bin_ids):]
    return groups, effect, to_groups @ cov[len(bin_ids):, len(bin_ids):] @ to_groups.T, float(extra)


def _centering(groups, mean_only=False):
    """Matrix that takes each detector's mean over its visits (mean_only) or subtracts it."""
    detectors = np.array([d for d, _ in groups])
    same = (detectors[:, None] == detectors[None, :]).astype(float)
    mean = same / same.sum(axis=1, keepdims=True)
    return mean if mean_only else np.eye(len(groups)) - mean


def _linked_visits(visit, bins):
    """Mask of rows in the largest group of visits linked by shared bins; None if under two visits."""
    groups = {v: {v} for v in set(visit)}
    by_bin = {}
    for b, v in zip(bins, visit):
        by_bin.setdefault(b, set()).add(v)
    for members in by_bin.values():
        merged = set().union(*(groups[v] for v in members))
        for v in merged:
            groups[v] = merged
    largest = max(groups.values(), key=len)
    if len(largest) < 2:
        return None
    return np.array([v in largest for v in visit])


def _wls(design, y, sigma):
    w = 1 / sigma ** 2
    cov = np.linalg.pinv(design.T @ (design * w[:, None]), hermitian=True)
    return cov @ design.T @ (w * y), cov


def _extra_scatter(design, y, noise, dof):
    """Relative scatter to add to every frame so the model fits (reduced chi-square = 1).

    Covers what the pixel noise misses: where the star falls within a pixel changes how much of
    its light lands in the aperture, and wavelength still changes a little within a bin.
    """
    if dof <= 0:
        return 0.0

    def reduced_chi2(extra):
        sigma = np.hypot(noise, extra)
        beta, _ = _wls(design, y, sigma)
        return np.sum(((y - design @ beta) / sigma) ** 2) / dof

    if reduced_chi2(0.0) <= 1:
        return 0.0
    low, high = 0.0, 1.0
    for _ in range(40):
        mid = (low + high) / 2
        low, high = (mid, high) if reduced_chi2(mid) > 1 else (low, mid)
    return high


def verdict(measurements, motion, brightness):
    """One of the six verdict values in the web format (saturday_plan.md).

    measurements: the single-frame ones (saturation share); motion: from measure_motion.
    """
    if motion is None or not motion.constrained:
        saturated = np.mean([m.saturated for m in measurements]) > 0.5 if measurements else False
        return "saturated" if saturated else "too_faint"
    if motion.detected:
        return "moves_as_expected" if motion.matches_catalog else "moves_unexpected"
    if brightness is not None and brightness.significant:
        return "brightness_changes"
    return "no_motion_detected"
