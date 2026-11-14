"""Clean one SPHEREx cutout, in its own detector pixels (alignment comes later).

Cleaning = subtract the zodiacal light model (ZODI) and any leftover smooth background, and set
unusable pixels to NaN. It also sorts the FLAGS into the classes shown by the site's
"quality flags" layer.
"""
from dataclasses import dataclass

import numpy as np
from astropy.io import fits
from astropy.stats import SigmaClip, sigma_clipped_stats
from astropy.wcs import WCS
from photutils.background import Background2D, MedianBackground
from scipy.ndimage import binary_dilation

from spx.cutouts import sky_wcs

# Bit numbers from the FLAGS header (MSKNnnnn keywords, verified 2026-11-14) and Table 16 of the
# SPHEREx Explanatory Supplement v2.0 (SATELLITE_HALO is newer than our files' headers).
FLAG_BITS = {
    "TRANSIENT": 0, "OVERFLOW": 1, "SUR_ERROR": 2, "NONFUNC": 6, "DICHROIC": 7, "MISSING_DATA": 9,
    "HOT": 10, "COLD": 11, "FULLSAMPLE": 12, "PHANMISS": 14, "NONLINEAR": 15, "PERSIST": 17,
    "OUTLIER": 19, "CROSSTALK": 20, "SOURCE": 21, "GHOST": 22, "GHOST_FPA": 23, "GHOST_EXT": 24,
    "STREAK": 25, "BLOOM": 26, "SNOWBALL": 27, "HALO": 28, "SATELLITE_HALO": 29,
}

# Pixels set to NaN whenever one of these is set: no usable value, a wrong value (persistence,
# halo excess, poor calibration), or a fake source (crosstalk, ghost, satellite).
ALWAYS_MASKED = ["NONFUNC", "MISSING_DATA", "HOT", "COLD", "NONLINEAR", "PERSIST", "DICHROIC",
                 "PHANMISS", "CROSSTALK", "GHOST", "GHOST_FPA", "GHOST_EXT", "STREAK", "SNOWBALL",
                 "HALO", "SATELLITE_HALO"]
# Kept on purpose:
# - OVERFLOW alone: the value is fitted from the reads taken before the pixel passed the overflow
#   threshold (half full well), so bright stars stay measurable.
# - TRANSIENT with BLOOM: a bright star's own spill-over, not a cosmic ray; the value is the
#   slope from the reads before the spill-over.
# - OUTLIER: also fires on real objects missing from the source catalog, which a discovery
#   tool must keep. Single-frame outliers are removed from stacks by outlier rejection.
# TRANSIENT without BLOOM is a cosmic ray. SUR_ERROR is an onboard error, or with OVERFLOW an
# overflow in the first seconds (no usable reads); with TRANSIENT + BLOOM it is early spill-over.

# Quality-flags layer: class number -> flags. A pixel takes the first class that matches.
# SOURCE and FULLSAMPLE are informational and never shown.
CLEAN, SATURATED, DEFECT, OTHER = 0, 1, 2, 3
FLAG_CLASSES = {
    SATURATED: ["OVERFLOW", "NONLINEAR", "BLOOM"],  # red
    DEFECT: ["TRANSIENT", "HOT", "COLD", "NONFUNC", "SNOWBALL", "PERSIST", "SUR_ERROR",
             "MISSING_DATA"],  # orange: cosmic rays and bad pixels
    OTHER: ["OUTLIER", "HALO", "DICHROIC", "CROSSTALK", "PHANMISS", "GHOST", "GHOST_FPA",
            "GHOST_EXT", "STREAK", "SATELLITE_HALO"],  # blue
}

BOX_PX = 16  # background mesh: smooth structure larger than a few stars
SOURCE_SIGMA = 3.0  # pixels this far above the first background estimate count as sources
SOURCE_GROW_PX = 2  # widen the source mask to cover the faint PSF wings


def bitmask(names):
    return sum(1 << FLAG_BITS[name] for name in names)


@dataclass
class CleanFrame:
    image: np.ndarray  # MJy/sr, background removed, NaN where unusable
    variance: np.ndarray  # (MJy/sr)^2, NaN where unusable
    flag_class: np.ndarray  # CLEAN / SATURATED / DEFECT / OTHER per pixel
    background: np.ndarray  # leftover background that was subtracted (after ZODI)
    header: fits.Header  # IMAGE header (time, detector, wavelength calibration id)
    wcs: WCS  # cutout pixel -> sky


def clean_frame(path):
    with fits.open(path) as hdul:
        header = hdul["IMAGE"].header.copy()
        image = hdul["IMAGE"].data.astype(float) - hdul["ZODI"].data
        variance = hdul["VARIANCE"].data.astype(float)
        flags = hdul["FLAGS"].data.astype(np.int64)
    unusable = unusable_pixels(flags) | ~np.isfinite(image) | ~np.isfinite(variance) | (variance <= 0)
    image[unusable] = np.nan
    variance[unusable] = np.nan
    background = leftover_background(image)
    return CleanFrame(image - background, variance, flag_classes(flags), background, header,
                      sky_wcs(header))


def unusable_pixels(flags):
    """True where the FLAGS make a pixel's value unusable (see ALWAYS_MASKED and the notes above it)."""
    def has(name):
        return (flags & (1 << FLAG_BITS[name])) != 0

    star_spillover = has("TRANSIENT") & has("BLOOM")
    unusable = (flags & bitmask(ALWAYS_MASKED)) != 0
    unusable |= has("TRANSIENT") & ~star_spillover
    unusable |= has("SUR_ERROR") & ~star_spillover
    return unusable


def flag_classes(flags):
    classes = np.full(flags.shape, CLEAN, dtype=np.uint8)
    for number in sorted(FLAG_CLASSES, reverse=True):  # lowest number painted last, so it wins
        classes[(flags & bitmask(FLAG_CLASSES[number])) != 0] = number
    return classes


def leftover_background(image):
    """Smooth background left after ZODI (scattered light, ZODI model error).

    Two passes: stars pull the box medians up and would leave dark rings around them, so the
    second estimate ignores pixels the first one finds clearly above the background.
    """
    first = _mesh_background(image, sources=None)
    residual = image - first
    _, median, noise = sigma_clipped_stats(residual, sigma=3)
    sources = binary_dilation(residual - median > SOURCE_SIGMA * noise, iterations=SOURCE_GROW_PX)
    return _mesh_background(image, sources=sources)


def _mesh_background(image, sources):
    """Sigma-clipped median in BOX_PX boxes, smoothed over neighboring boxes and interpolated.

    Falls back to one sigma-clipped median for the whole cutout when it is too small or too
    masked for a mesh.
    """
    empty = ~np.isfinite(image)
    try:
        # exclude_percentile: a box is skipped if more than this % of its pixels are masked.
        estimate = Background2D(image, BOX_PX, mask=sources, coverage_mask=empty, filter_size=3,
                                exclude_percentile=50, sigma_clip=SigmaClip(sigma=3),
                                bkg_estimator=MedianBackground())
        return np.where(empty, np.nan, estimate.background)
    except ValueError:
        usable = image if sources is None else np.where(sources, np.nan, image)
        return np.where(empty, np.nan, sigma_clipped_stats(usable, sigma=3)[1])
