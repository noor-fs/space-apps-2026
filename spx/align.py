"""Place a cleaned frame on the field's grid, so a pixel means the same sky spot in every frame.

Each frame comes in its detector's own orientation; the field grid is north-up (Field.wcs()).
Both have 6.15" pixels, so this is mostly a shift and a rotation. Positions are measured on the
original frames (resampling smooths them); aligned frames are for display and stacking.
"""
from dataclasses import dataclass

import numpy as np
from astropy.io import fits
from reproject import reproject_interp

from spx.clean import CLEAN

# A grid pixel is kept if at least this share of its interpolation weight comes from usable
# pixels. Plain bilinear interpolation would turn each masked pixel into up to four masked
# grid pixels.
MIN_USABLE_WEIGHT = 0.5


@dataclass
class AlignedFrame:
    image: np.ndarray  # MJy/sr on the field grid (FITS orientation: row 0 = south), NaN = no data
    variance: np.ndarray
    flag_class: np.ndarray  # from clean.FLAG_CLASSES, nearest pixel; CLEAN where off the cutout
    covered: np.ndarray  # True where the field pixel lies inside this cutout
    header: fits.Header  # the frame's IMAGE header

    @property
    def coverage(self):
        """Share of the field this frame covers (cutouts at a detector edge are clipped)."""
        return float(self.covered.mean())

    @property
    def bad_pixel_fraction(self):
        """Share of the covered field pixels that are unusable."""
        if not self.covered.any():
            return 1.0
        return float(np.isnan(self.image[self.covered]).mean())


def align_frame(frame, field):
    """Resample a clean.CleanFrame onto field.wcs()."""
    grid, shape = field.wcs(), (field.size_px, field.size_px)

    def resample(data, order="bilinear"):
        return reproject_interp((data, frame.wcs), grid, shape_out=shape, order=order)

    usable = np.isfinite(frame.image)
    weight, footprint = resample(usable.astype(float))
    covered = footprint > 0
    keep = covered & (np.nan_to_num(weight) >= MIN_USABLE_WEIGHT)
    with np.errstate(invalid="ignore", divide="ignore"):
        # Interpolate with masked pixels set to 0, then divide by the usable weight: each grid
        # pixel becomes the weighted mean of its usable neighbors only.
        image = resample(np.where(usable, frame.image, 0.0))[0] / weight
        variance = resample(np.where(usable, frame.variance, 0.0))[0] / weight
    image[~keep] = np.nan
    variance[~keep] = np.nan
    image, variance = image.astype(np.float32), variance.astype(np.float32)  # half the memory (R Dra: ~2,600 frames)
    flag_class = resample(frame.flag_class.astype(float), order="nearest-neighbor")[0]
    flag_class = np.where(covered & np.isfinite(flag_class), flag_class, CLEAN).astype(np.uint8)
    return AlignedFrame(image, variance, flag_class, covered, frame.header)
