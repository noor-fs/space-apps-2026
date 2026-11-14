"""Queries to the IRSA archive (SPHEREx images, CatWISE2020)."""
import io
import re
import time
import warnings

import numpy as np
import requests
from astropy.table import Table
from astropy.time import Time

IRSA = "https://irsa.ipac.caltech.edu/"

# Pipeline versions whose file format (extensions, FLAGS bits, wavelength table) we have checked.
VALIDATED_PIPELINES = {"v27"}


def tap_query(adql, retries=5, timeout=(15, 180)):
    """Run a synchronous ADQL query on IRSA TAP and return an astropy Table.

    Uses requests directly so every call has a timeout (pyvo's default can hang forever),
    and retries transient 5xx errors, which IRSA returns as HTML pages.
    """
    last_error = None
    for attempt in range(retries):
        try:
            response = requests.post(IRSA + "TAP/sync", timeout=timeout,
                                     data={"LANG": "ADQL", "FORMAT": "csv", "QUERY": adql})
            if response.ok and not response.text.lstrip().startswith("<"):
                return Table.read(io.BytesIO(response.content), format="ascii.csv")
            query_error = re.search(r'name="QUERY_STATUS" value="ERROR">(.*?)</INFO>', response.text, re.S)
            if query_error:  # a mistake in the query: retrying won't help
                raise ValueError(f"IRSA rejected the query: {query_error.group(1).strip()}")
            last_error = f"HTTP {response.status_code}"
        except requests.RequestException as error:
            last_error = str(error)
        print(f"TAP attempt {attempt + 1}/{retries} failed: {last_error:.80}")
        time.sleep(5 * 2 ** attempt)
    raise ConnectionError(f"IRSA TAP unavailable after {retries} attempts: {last_error}")


def find_frames(field):
    """Every SPHEREx image that overlaps any part of the field, one row per (exposure, detector).

    Columns: exposure, detector (1-6), mjd_start, mjd_end, wave_min_um, wave_max_um (the
    detector's whole range; the wavelength at a given pixel comes from the wavelength table),
    release, pipeline, uri. Sorted by time.
    """
    radius_deg = field.width_deg / 2 * np.sqrt(2)  # circle through the field's corners
    rows = tap_query(f"""SELECT o.observationid AS exposure, p.energy_bandpassname AS band,
            p.time_bounds_lower AS mjd_start, p.time_bounds_upper AS mjd_end,
            p.energy_bounds_lower AS wave_min_m, p.energy_bounds_upper AS wave_max_m, a.uri
        FROM spherex.artifact a
        JOIN spherex.plane p ON a.planeid = p.planeid
        JOIN spherex.observation o ON p.obsid = o.obsid
        WHERE INTERSECTS(p.poly, CIRCLE('ICRS', {field.center.ra.deg}, {field.center.dec.deg},
            {radius_deg})) = 1""")
    frames = Table()
    frames["exposure"] = [str(e) for e in rows["exposure"]]
    frames["detector"] = [int(str(b).split("-D")[1]) for b in rows["band"]]
    frames["mjd_start"] = rows["mjd_start"]
    frames["mjd_end"] = rows["mjd_end"]
    frames["wave_min_um"] = rows["wave_min_m"] * 1e6
    frames["wave_max_um"] = rows["wave_max_m"] * 1e6
    paths = [_parse_path(str(u)) for u in rows["uri"]]
    frames["release"] = [p["release"] for p in paths]
    frames["pipeline"] = [p["pipeline"] for p in paths]
    frames["processed"] = [p["processed"] for p in paths]
    frames["uri"] = [str(u) for u in rows["uri"]]
    frames = _keep_best_release(frames)
    _warn_unvalidated(frames)
    frames.sort("mjd_start")
    return frames


def _parse_path(uri):
    """ibe/data/spherex/<release>/level2/<week>/l2b-<pipeline>-<year>-<day of year>/<detector>/<file>"""
    parts = uri.split("/")
    _, pipeline, year, day = parts[6].split("-")
    return {"release": parts[3], "pipeline": pipeline, "processed": f"{year}-{day}"}


def release_rank(release):
    """Order releases: any data release (dr) beats any quick release (qr); higher number wins.

    Works for future names (dr2, qr4) without code changes. Unknown names rank lowest.
    """
    match = re.fullmatch(r"(dr|qr)(\d+)", release)
    if not match:
        warnings.warn(f"Unknown SPHEREx release name {release!r}: ranked below all known releases")
        return (-1, 0)
    return (1 if match.group(1) == "dr" else 0, int(match.group(2)))


def _keep_best_release(frames):
    """If the same (exposure, detector) is in several releases, keep the best-ranked copy."""
    ranks = [release_rank(r) + (p,) for r, p in zip(frames["release"], frames["processed"])]
    order = sorted(range(len(frames)), key=lambda i: ranks[i], reverse=True)
    seen, keep = set(), []
    for i in order:
        key = (frames["exposure"][i], frames["detector"][i])
        if key not in seen:
            seen.add(key)
            keep.append(i)
    return frames[sorted(keep)]


def _warn_unvalidated(frames):
    unknown = set(frames["pipeline"]) - VALIDATED_PIPELINES
    if unknown:
        warnings.warn(f"Frames from pipeline version(s) {sorted(unknown)} have not been checked: "
                      "extension names, FLAGS bits or the wavelength table may have changed")


def data_summary(frames):
    """How current the data are: releases, pipeline versions, date range."""
    return {
        "n_frames": len(frames),
        "releases": sorted({str(r) for r in frames["release"]}, key=release_rank),
        "pipelines": sorted({str(p) for p in frames["pipeline"]}),
        "first_date": Time(np.min(frames["mjd_start"]), format="mjd").iso[:10],
        "last_date": Time(np.max(frames["mjd_start"]), format="mjd").iso[:10],
    }
