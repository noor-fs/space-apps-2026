"""A field: the patch of sky the user asked for, and the pixel grid every image is placed on."""
from dataclasses import dataclass

import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS

PIXEL_SCALE_ARCSEC = 6.15
FIELD_SIZES_PX = (51, 101, 201)
CENTER_DATE = "2026-01-01"


def parse_coordinates(text):
    """Read typed coordinates as an ICRS position.

    Plain numbers are degrees ("133.795 -7.245"). Anything else is sexagesimal with RA in
    hours ("08h55m10.8s -07d14m42s", "08:55:10.8 -07:14:42", "08 55 10.8 -07 14 42").
    """
    cleaned = text.replace(",", " ").strip()
    tokens = cleaned.split()
    if len(tokens) == 2 and all(_is_number(token) for token in tokens):
        ra, dec = (float(token) for token in tokens)
        if not 0 <= ra < 360:
            raise ValueError(f"RA must be between 0 and 360 degrees, got {ra}")
        if not -90 <= dec <= 90:
            raise ValueError(f"Dec must be between -90 and +90 degrees, got {dec}")
        unit = (u.deg, u.deg)
    else:
        unit = (u.hourangle, u.deg)
    try:
        return SkyCoord(cleaned, unit=unit, frame="icrs")
    except ValueError:
        raise ValueError(f"Could not read {text!r} as coordinates. Examples: "
                         "'133.795 -7.245' (degrees) or '08h55m10.8s -07d14m42s'") from None


def _is_number(token):
    try:
        float(token)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class Field:
    """A square, north-up grid of size_px x size_px pixels centered on `center`."""

    center: SkyCoord
    size_px: int

    def __post_init__(self):
        if self.size_px not in FIELD_SIZES_PX:
            raise ValueError(f"size_px must be one of {FIELD_SIZES_PX}, got {self.size_px}")

    @property
    def center_px(self):
        return (self.size_px - 1) / 2

    @property
    def width_deg(self):
        return self.size_px * PIXEL_SCALE_ARCSEC / 3600

    def wcs(self):
        """TAN projection at the field center, north up, east left (standard FITS orientation).

        In FITS convention the first array row is the SOUTH edge. The web format wants
        north in row 0, so images are flipped once, at export.
        """
        scale_deg = PIXEL_SCALE_ARCSEC / 3600
        wcs = WCS(naxis=2)
        wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
        wcs.wcs.crval = [self.center.ra.deg, self.center.dec.deg]
        wcs.wcs.crpix = [self.center_px + 1, self.center_px + 1]  # FITS pixels count from 1
        wcs.wcs.cdelt = [-scale_deg, scale_deg]  # RA grows to the left (east)
        return wcs

    def web_pixel(self, coord):
        """(column, row) in the web format: from 0, row 0 at the north edge.

        Works for one position or many; returns numbers or arrays to match.
        """
        x, y = self.wcs().world_to_pixel(coord)
        return x, self.size_px - 1 - y
