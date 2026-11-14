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

# Bit numbers, verified against the FLAGS header (MSKNnnnn keywords) on 2026-11-14.
FLAG_BITS = {
    "TRANSIENT": 0, "OVERFLOW": 1, "SUR_ERROR": 2, "NONFUNC": 6, "DICHROIC": 7, "MISSING_DATA": 9,
    "HOT": 10, "COLD": 11, "FULLSAMPLE": 12, "PHANMISS": 14, "NONLINEAR": 15, "PERSIST": 17,
    "OUTLIER": 19, "CROSSTALK": 20, "SOURCE": 21, "STREAK": 25, "BLOOM": 26, "SNOWBALL": 27, "HALO": 28,
}

# Pixels set to NaN. TRANSIENT and OUTLIER are included so a cosmic ray in a single frame
# isn't mistaken for a new object. HALO, DICHROIC, CROSSTALK and PHANMISS are kept (shown only).
MASKED = ["OVERFLOW", "SUR_ERROR", "NONFUNC", "MISSING_DATA", "HOT", "COLD", "NONLINEAR",
          "PERSIST", "STREAK", "BLOOM", "SNOWBALL", "TRANSIENT", "OUTLIER"]

# Quality-flags layer: class number -> flags. A pixel takes the first class that matches.
# SOURCE and FULLSAMPLE are informational and never shown.
CLEAN, SATURATED, DEFECT, OTHER = 0, 1, 2, 3
FLAG_CLASSES = {
    SATURATED: ["OVERFLOW", "NONLINEAR", "BLOOM"],  # red
    DEFECT: ["TRANSIENT", "OUTLIER", "HOT", "COLD", "NONFUNC", "SNOWBALL", "PERSIST",
             "SUR_ERROR", "MISSING_DATA"],  # orange
    OTHER: ["HALO", "DICHROIC", "CROSSTALK", "PHANMISS", "STREAK"],  # blue
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
    unusable = (flags & bitmask(MASKED)) != 0
    unusable |= ~np.isfinite(image) | ~np.isfinite(variance) | (variance <= 0)
    image[unusable] = np.nan
    variance[unusable] = np.nan
    background = leftover_background(image)
    return CleanFrame(image - background, variance, flag_classes(flags), background, header,
                      sky_wcs(header))


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
