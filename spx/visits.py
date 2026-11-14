"""Group frames into visits and stack each visit.

A visit is the set of frames SPHEREx took of the field in one pass (about every 6 months).
A pass is several scans spread over weeks, and each scan sees the field with only some
detectors, so a visit stack combines all of them. Near the ecliptic poles there are no gaps
between passes, so long stretches are cut into pieces of at most MAX_VISIT_DAYS.
"""
import warnings
from dataclasses import dataclass, field as dataclass_field

import numpy as np

VISIT_GAP_DAYS = 30.0  # a longer pause starts a new visit
MAX_VISIT_DAYS = 60.0  # longer groups (dense coverage near the poles) are split into equal pieces
MIN_BLINK_COVERAGE = 0.5  # frames covering less of the field are stacked but not shown one by one
CLIP_SIGMA = 4.0
CLIP_MIN_FRAMES = 3  # fewer frames: plain weighted mean, no outlier rejection
# A star's brightness changes with wavelength, and frames of one detector are at different
# wavelengths. Allow this share of the pixel's median value on top of the noise before
# rejecting, so bright stars aren't clipped.
CLIP_RELATIVE_TOLERANCE = 0.2
RGB_DETECTORS = {"blue": (1, 2), "green": (3, 4), "red": (5, 6)}


def visit_ranges(mjd):
    """(first, last) MJD of each visit, oldest first.

    Pass the times of ALL frames found for the field, not only the downloaded ones: frames
    still missing would otherwise leave false gaps, and visits would change as downloads fill in.
    """
    mjd = np.sort(np.asarray(mjd, dtype=float))
    ranges = []
    for times in np.split(mjd, np.flatnonzero(np.diff(mjd) > VISIT_GAP_DAYS) + 1):
        pieces = int(np.ceil((times[-1] - times[0]) / MAX_VISIT_DAYS)) or 1
        piece = np.minimum(((times - times[0]) / (times[-1] - times[0] + 1e-9) * pieces).astype(int),
                           pieces - 1)
        ranges += [(times[piece == p][0], times[piece == p][-1]) for p in np.unique(piece)]
    return ranges


def visit_of(mjd, ranges):
    """Visit number (from 1) of each time: the visit containing it, else the nearest one."""
    starts, ends = np.array(ranges).T
    mjd = np.asarray(mjd, dtype=float)[:, None]
    distance = np.maximum(starts - mjd, 0) + np.maximum(mjd - ends, 0)  # 0 inside a visit
    return distance.argmin(axis=1) + 1


@dataclass
class Stack:
    image: np.ndarray  # MJy/sr, NaN where no frame has data
    variance: np.ndarray
    n_frames: np.ndarray  # frames used per pixel (after rejection)


@dataclass
class VisitStack:
    n: int
    mjd_start: float
    mjd_end: float
    frames: list  # AlignedFrame, in time order
    combined: Stack  # equal-weight mean of the detector stacks
    detectors: dict = dataclass_field(default_factory=dict)  # detector number -> Stack
    rgb: dict = dataclass_field(default_factory=dict)  # "blue"/"green"/"red" -> image (NaN if no data)

    @property
    def blink_frames(self):
        """Frames shown one by one: those that cover enough of the field."""
        return [frame for frame in self.frames if frame.coverage >= MIN_BLINK_COVERAGE]


def build_visits(aligned_frames, ranges):
    """Assign aligned frames to visits (ranges from visit_ranges) and stack each visit.

    Returns VisitStacks, oldest first; visits with no downloaded frame yet are left out.
    """
    mjd = np.array([frame.header["MJD-OBS"] for frame in aligned_frames])
    numbers = visit_of(mjd, ranges)
    visits = []
    for n in np.unique(numbers):
        members = sorted(np.flatnonzero(numbers == n), key=lambda i: mjd[i])
        frames = [aligned_frames[i] for i in members]
        visits.append(stack_visit(int(n), frames, mjd[members]))
    return visits


def stack_visit(n, frames, mjd):
    by_detector = {}
    for frame in frames:
        by_detector.setdefault(int(frame.header["DETECTOR"]), []).append(frame)
    detectors = {d: stack([f.image for f in fs], [f.variance for f in fs])
                 for d, fs in sorted(by_detector.items())}
    combined = equal_weight_mean(list(detectors.values()))
    rgb = {}
    for color, pair in RGB_DETECTORS.items():
        present = [detectors[d] for d in pair if d in detectors]
        rgb[color] = equal_weight_mean(present).image if present else np.full(combined.image.shape, np.nan)
    return VisitStack(n, float(mjd.min()), float(mjd.max()), frames, combined, detectors, rgb)


def stack(images, variances):
    """Inverse-variance mean of frames from one detector, rejecting outliers per pixel.

    A value is rejected if it is more than CLIP_SIGMA noise from the per-pixel median, where
    noise = max(robust scatter across frames, typical frame noise) + a relative tolerance.
    This removes cosmic rays and asteroids present in only a few frames.
    """
    cube, var = np.array(images, dtype=float), np.array(variances, dtype=float)
    usable = np.isfinite(cube) & np.isfinite(var) & (var > 0)
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="All-NaN slice")  # pixels with no data stay NaN
        if len(cube) >= CLIP_MIN_FRAMES:
            median = np.nanmedian(cube, axis=0)
            scatter = 1.4826 * np.nanmedian(np.abs(cube - median), axis=0)
            noise = np.fmax(scatter, np.sqrt(np.nanmedian(var, axis=0)))
            noise = noise + CLIP_RELATIVE_TOLERANCE * np.abs(median)
            usable &= np.abs(cube - median) <= CLIP_SIGMA * noise
    weights = np.where(usable, 1 / np.where(usable, var, 1), 0)
    total = weights.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        image = np.where(total > 0, (np.where(usable, cube, 0) * weights).sum(axis=0) / total, np.nan)
        variance = np.where(total > 0, 1 / total, np.nan)
    return Stack(image, variance, usable.sum(axis=0))


def equal_weight_mean(stacks):
    """Mean of several stacks with equal weight per stack, using those with data at each pixel."""
    images = np.array([s.image for s in stacks])
    variances = np.array([s.variance for s in stacks])
    present = np.isfinite(images)
    count = present.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        image = np.where(count > 0, np.where(present, images, 0).sum(axis=0) / count, np.nan)
        variance = np.where(count > 0, np.where(present, variances, 0).sum(axis=0) / count ** 2, np.nan)
    return Stack(image, variance, sum(s.n_frames for s in stacks))

