"""RA/Dec <-> pixel and proper-motion propagation, exactly as in the shared format guide."""
import math
from astropy.time import Time
from config import PIXEL_SCALE_DEG

def center_pixel(S):
    return (S - 1) / 2.0

def radec_to_pixel(ra, dec, ra0, dec0, S):
    """Return (column, row), 0-based, row 0 north, east left. Inputs in degrees."""
    a, d, a0, d0 = map(math.radians, (ra, dec, ra0, dec0))
    D = math.sin(d) * math.sin(d0) + math.cos(d) * math.cos(d0) * math.cos(a - a0)
    xi = math.degrees(math.cos(d) * math.sin(a - a0) / D)
    eta = math.degrees((math.sin(d) * math.cos(d0) - math.cos(d) * math.sin(d0) * math.cos(a - a0)) / D)
    c = center_pixel(S)
    return c - xi / PIXEL_SCALE_DEG, c - eta / PIXEL_SCALE_DEG

def in_field(col, row, S):
    return -0.5 <= col <= S - 0.5 and -0.5 <= row <= S - 0.5

def jyear(date_str):
    """Julian year of an ISO date/time string (UTC)."""
    return float(Time(date_str, scale="utc").jyear)

def propagate(ra, dec, epoch, pmra_mas_yr, pmdec_mas_yr, date_str=None, jyear_value=None):
    """Move a star to a date. pmra already includes cos(dec). pm None -> position unchanged."""
    if pmra_mas_yr is None or pmdec_mas_yr is None:
        return ra, dec
    y = (jyear_value if jyear_value is not None else jyear(date_str)) - epoch
    ra_new = ra + pmra_mas_yr * y / 3_600_000.0 / math.cos(math.radians(dec))
    dec_new = dec + pmdec_mas_yr * y / 3_600_000.0
    return ra_new, dec_new

def angsep_deg(ra1, dec1, ra2, dec2):
    a1, d1, a2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    s = math.sin((d2 - d1) / 2) ** 2 + math.cos(d1) * math.cos(d2) * math.sin((a2 - a1) / 2) ** 2
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(s))))
