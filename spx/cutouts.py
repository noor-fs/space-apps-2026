"""Download SPHEREx cutouts from IRSA's cutout service.

A cutout is a square block of one detector image, cut by IRSA around a sky position. We keep
only the layers we use (IMAGE, FLAGS, VARIANCE, ZODI): the file continues with a large EPSF
table, so we stop reading at the first table header ("slim cutout", ~120 KB instead of ~4 MB).
"""
import io
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import requests
from astropy.io import fits
from astropy.wcs import WCS

from spx.archive import IRSA
from spx.field import PIXEL_SCALE_ARCSEC

CACHE_DIR = Path("cache")
EDGE_MARGIN_PX = 4  # extra pixels so reprojection has neighbors at the field edge
WORKERS = 6
RETRIES = 6
TABLE_MARKER = b"XTENSION= 'BINTABLE'"


def cutout_size_deg(field):
    """Width that covers the whole north-up field at any detector rotation."""
    return field.width_deg * np.sqrt(2) + 2 * EDGE_MARGIN_PX * PIXEL_SCALE_ARCSEC / 3600


def cutout_url(uri, field):
    return (f"{IRSA}{uri}?center={field.center.ra.deg:.6f},{field.center.dec.deg:.6f}d"
            f"&size={cutout_size_deg(field):.4f}")


def frame_id(frame):
    return f"{frame['exposure']}_D{frame['detector']}_{frame['release']}"


def field_dir(field):
    key = f"{field.center.ra.deg:.5f}_{field.center.dec.deg:+.5f}_{field.size_px}"
    return CACHE_DIR / "fields" / key


def download_order(frames):
    """Order frames so that any first N are spread over time and detectors.

    Within each detector, frames are put in van der Corput order (first, middle, quarters,
    eighths...) so a prefix covers the whole time range. Detectors then take turns.
    """
    per_detector = []
    for detector in sorted(set(frames["detector"])):
        rows = np.flatnonzero(frames["detector"] == detector)
        rows = rows[np.argsort(frames["mjd_start"][rows])]
        per_detector.append([rows[i] for i in _spread(len(rows))])
    order = []
    for turn in range(max(len(rows) for rows in per_detector)):
        order += [rows[turn] for rows in per_detector if turn < len(rows)]
    return frames[order]


def _spread(n):
    """Indices 0..n-1 in an order whose every prefix is spread evenly over the range."""
    order, seen = [], set()
    bits = max(1, int(np.ceil(np.log2(max(n, 2)))))
    for k in range(2 ** bits):
        fraction = int(format(k, f"0{bits}b")[::-1], 2) / 2 ** bits  # bit-reversed k
        index = int(fraction * n)
        if index not in seen:
            seen.add(index)
            order.append(index)
    return order + [i for i in range(n) if i not in seen]


def fetch_slim(url):
    """The cutout's bytes up to the first table (IMAGE, FLAGS, VARIANCE, ZODI)."""
    content = b""
    with _get(url, stream=True) as response:
        for chunk in response.iter_content(16384):
            content += chunk
            cut = content.find(TABLE_MARKER)
            if cut != -1:
                return content[:cut]
    return content


def _get(url, stream=False):
    """GET with retries. IRSA answers 503 'Server busy' under load: wait and try again."""
    last_error = None
    for attempt in range(RETRIES):
        try:
            response = requests.get(url, stream=stream, timeout=(15, 120))
            if response.status_code == 200:
                return response
            last_error = f"HTTP {response.status_code}: {response.text[:100]}"
            response.close()
            if response.status_code < 500:  # a bad request: retrying won't help
                break
        except requests.RequestException as error:
            last_error = str(error)
        time.sleep(2 ** attempt + random.uniform(0, 1))  # back off; jitter spreads out the retries
    raise ConnectionError(f"{url}: {last_error}")


def download_frames(field, frames, budget=None, workers=WORKERS):
    """Download frames in download_order, yielding (frame, path or None, error or None) as each finishes.

    Cached cutouts are reused. Use budget to stop after the first N frames of the order;
    run again without a budget to fill in the rest.
    """
    ordered = download_order(frames)
    if budget is not None:
        ordered = ordered[:budget]
    folder = field_dir(field)
    folder.mkdir(parents=True, exist_ok=True)

    def fetch(frame):
        path = folder / f"{frame_id(frame)}.fits"
        if not path.exists():
            content = fetch_slim(cutout_url(frame["uri"], field))
            fits.open(io.BytesIO(content))["IMAGE"]  # raises if IRSA sent something that isn't a cutout
            path.write_bytes(content)
        return path

    with ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(fetch, frame): frame for frame in ordered}
        for future in as_completed(futures):
            frame = futures[future]
            try:
                yield frame, future.result(), None
            except Exception as error:
                yield frame, None, str(error)


def wavelength_calibration_id(header):
    """The IMAGE header names its wavelength calibration in a HISTORY line: '[CALIB] spectral_wcs <id>'."""
    for line in header.get("HISTORY", []):
        if "[CALIB] spectral_wcs" in line:
            return line.split()[-1]
    return None


def wavelength_table(frame, header, field):
    """Path to the WCS-WAVE table for this frame's calibration, downloaded once and kept.

    Slim cutouts stop before WCS-WAVE (it comes after the large EPSF table), so the first frame
    with a new calibration id is fetched in full and only its WCS-WAVE layer is saved.
    """
    calibration_id = wavelength_calibration_id(header)
    if calibration_id is None:
        raise ValueError(f"{frame_id(frame)}: no '[CALIB] spectral_wcs' line in the IMAGE header")
    path = CACHE_DIR / "wave" / f"{calibration_id}.fits"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        content = _get(cutout_url(frame["uri"], field)).content
        with fits.open(io.BytesIO(content)) as full:
            fits.HDUList([fits.PrimaryHDU(), full["WCS-WAVE"].copy()]).writeto(path)
    return path


DISTORTION_KEY = re.compile(r"(A|B|AP|BP)_(\d+_\d+|ORDER|DMAX)")


def sky_wcs(header):
    """Pixel <-> RA/Dec for a cutout, including the optical distortion (SIP) terms.

    The headers carry SIP terms but their CTYPE lacks the '-SIP' label; astropy applies the
    terms anyway and prints a long notice. Adding the label gives the same result, quietly.
    """
    header = header.copy()
    if any(DISTORTION_KEY.fullmatch(key) for key in header):
        for key in ("CTYPE1", "CTYPE2"):
            if not header[key].endswith("-SIP"):
                header[key] += "-SIP"
    return WCS(header)


def _without_distortion(header):
    """The SIP terms describe the optics (pixel -> sky) only. astropy also applies them to the
    alternate WCSs (A: detector pixel, W: wavelength), which shifts lookups by up to ~40 px near
    detector edges, so those must be built from a header without them."""
    header = header.copy()
    for key in [k for k in header if DISTORTION_KEY.fullmatch(k)]:
        del header[key]
    return header


def wavelength_at(header, table_path, x, y):
    """Wavelength and bandwidth (um) at cutout pixel(s) x, y; NaN where off the cutout.

    Cutouts are clipped at the detector edge, so "off the cutout" also means "off the detector".
    """
    header = _without_distortion(header)
    with fits.open(table_path) as table:
        hdul = fits.HDUList([fits.ImageHDU(header=header), table["WCS-WAVE"]])
        um, bandwidth = WCS(header, fobj=hdul, key="W").pixel_to_world_values(x, y)
    off = (np.asarray(x) < -0.5) | (np.asarray(x) > header["NAXIS1"] - 0.5) | \
          (np.asarray(y) < -0.5) | (np.asarray(y) > header["NAXIS2"] - 0.5)
    return np.where(off, np.nan, um), np.where(off, np.nan, bandwidth)
