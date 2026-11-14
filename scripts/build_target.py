"""Build one target's web files: find frames, download, clean, align, stack, measure, export.

Run from the repo root:
    python scripts/build_target.py epsilon_indi_b --name "Epsilon Indi B"
    python scripts/build_target.py my_field --coords "133.76 -7.24" --sizes 51 101
    python scripts/build_target.py epsilon_indi_b --name "Epsilon Indi B" --offline

Writes data/<target_key>/ (the web format) and results/<target_key>/ (measurement tables and
a build log). --offline skips the SPHEREx archive: it uses the cached frame
list and the downloaded cutouts only (a name not resolved before is still looked up).
"""
import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

from astropy.coordinates import SkyCoord
from astropy.table import Table
from astropy.time import Time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spx.align import align_frame  # noqa: E402
from spx.archive import find_frames  # noqa: E402
from spx.clean import clean_frame  # noqa: E402
from spx.cutouts import CACHE_DIR, download_frames, field_dir, wavelength_calibration_id, wavelength_table  # noqa: E402
from spx.export import export_field, frame_key, write_results  # noqa: E402
from spx.field import FIELD_SIZES_PX, Field, parse_coordinates  # noqa: E402
from spx.measure import gaia_sources, measure_frame, reference_stars  # noqa: E402
from spx.names import CatalogSource, resolve_name  # noqa: E402
from spx.psf import measure_visits  # noqa: E402
from spx.verdict import brightness_test, measure_motion, verdict  # noqa: E402
from spx.visits import build_visits, visit_ranges  # noqa: E402

DATA_DIR = Path("data")
RESULTS_DIR = Path("results")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target_key", help="folder name in data/: lowercase, underscores")
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--name", help="object name, resolved through Sesame, Gaia DR3 and CatWISE2020")
    where.add_argument("--coords", help="field center as typed, e.g. '133.76 -7.24' or '08h55m03s -07d14m31s'")
    parser.add_argument("--label", help="name shown on the site (default: --name or --coords)")
    parser.add_argument("--sizes", type=int, nargs="+", default=[51], choices=FIELD_SIZES_PX)
    parser.add_argument("--budget", type=int, help="download at most this many frames (default: all)")
    parser.add_argument("--offline", action="store_true", help="no SPHEREx archive queries or downloads: cached frames only")
    args = parser.parse_args()

    center, target = locate(args)
    label = args.label or args.name or args.coords
    for size in sorted(args.sizes):
        build(args.target_key, label, Field(center, size), target, args.budget, args.offline)


def locate(args):
    """Field center and catalog source (None for typed coordinates)."""
    if args.coords:
        return parse_coordinates(args.coords), None
    path = CACHE_DIR / "targets" / f"{args.target_key}.json"
    if path.exists():
        saved = json.loads(path.read_text())
        if saved["name"] == args.name:
            source = saved["source"] and CatalogSource(**{**saved["source"],
                                                          "ref_epoch": Time(saved["source"]["ref_epoch"], format="mjd")})
            return SkyCoord(saved["ra"], saved["dec"], unit="deg"), source
    match = resolve_name(args.name)
    source = None if match.source is None else {**match.source.__dict__, "ref_epoch": match.source.ref_epoch.mjd}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": args.name, "ra": match.center.ra.deg, "dec": match.center.dec.deg,
                                "source": source, "match_arcsec": match.match_arcsec}, indent=1))
    print(f"{args.name}: {match.source.catalog + ' ' + match.source.source_id if match.source else 'Sesame only'}, "
          f"center {match.center.ra.deg:.6f} {match.center.dec.deg:+.6f}")
    return match.center, match.source


def frame_list(field, offline):
    """(frames table, where it came from). Online queries are saved for offline runs."""
    path = field_dir(field) / "frames.ecsv"
    if not offline:
        frames = find_frames(field)
        path.parent.mkdir(parents=True, exist_ok=True)
        frames.write(path, overwrite=True)
        return frames, "archive"
    if path.exists():
        return Table.read(path), "cached list"
    # Visits must come from every frame that exists, not only the downloaded ones: with 120 of
    # ~490 frames, Epsilon Indi B's first visit split in two at a false gap
    sys.exit(f"--offline needs a frame list saved by an online run ({path} missing)")


def build(target_key, label, field, target, budget, offline):
    started = time.time()
    print(f"\n== {target_key}, {field.size_px} px")
    frames, frames_from = frame_list(field, offline)
    print(f"{len(frames)} frames ({frames_from})")

    failures = []
    if offline:
        paths = [p for p in sorted(field_dir(field).glob("*.fits"))]
    else:
        paths = []
        for done, (frame, path, error) in enumerate(download_frames(field, frames, budget), start=1):
            if error:
                failures.append({"frame": str(frame["exposure"]), "detector": int(frame["detector"]), "error": error})
            else:
                paths.append(path)
            if done % 50 == 0:
                print(f"  downloaded {done}")
    rows_by_id = {f"{r['exposure']}_D{r['detector']}_{r['release']}": r for r in frames}
    print(f"{len(paths)} cutouts, {len(failures)} failed downloads")

    references = reference_stars(field, field.center)
    catalog = gaia_sources(field)
    measurements, aligned, missing_wave = {}, [], 0
    for k, path in enumerate(paths, start=1):
        frame = clean_frame(path)
        wave = _wave_table(frame.header, rows_by_id.get(path.stem), field)
        missing_wave += wave is None
        measurements[frame_key(frame.header)] = measure_frame(frame, field, target, references, wave, catalog)
        aligned.append(align_frame(frame, field))
        if k % 100 == 0:
            print(f"  measured {k}")
    if missing_wave:
        print(f"{missing_wave} frames without a wavelength table (not cached, no archive path to fetch it)")

    ranges = visit_ranges(frames["mjd_start"])
    visits = build_visits(aligned, ranges)
    frame_measurements = list(measurements.values())
    motion, motion_source = measure_motion(frame_measurements, None, field, target, ranges)
    visit_fits = None
    # The PSF can't describe a saturated core, so a mostly saturated target isn't refitted
    mostly_saturated = np.mean([m.saturated for m in frame_measurements]) > 0.5
    if target is not None and not mostly_saturated and (motion is None or not motion.constrained):
        print("Single frames can't constrain the motion: fitting each visit with the PSF")
        visit_fits = measure_visits(paths, rows_by_id, field, target, ranges, catalog, references)
        motion, motion_source = measure_motion(frame_measurements, visit_fits, field, target, ranges)
    brightness = brightness_test(frame_measurements, ranges)
    result = verdict(frame_measurements, motion, brightness)

    uris = {f"{r['exposure']}_D{r['detector']}": str(r["uri"]) for r in frames} if "uri" in frames.colnames else None
    export_field(DATA_DIR / target_key, target_key, label, field, target, visits, ranges, measurements,
                 visit_fits, motion, motion_source, result, uris)
    results = RESULTS_DIR / target_key
    write_results(results, field, measurements, visit_fits, motion, motion_source, brightness, result)
    log = {"built": Time.now().isot[:19] + "Z", "size_px": field.size_px, "offline": offline,
           "frames_found": len(frames), "frames_from": frames_from, "budget": budget,
           "cutouts_used": len(paths), "failed_downloads": failures, "frames_without_wavelength": missing_wave,
           "visits": len(visits), "reference_stars": len(references), "verdict": result,
           "minutes": round((time.time() - started) / 60, 1)}
    (results / f"build_log_fov{field.size_px}.json").write_text(json.dumps(log, indent=1))
    motion_text = (f"{motion.pmra:+.0f} ± {motion.pmra_err:.0f}, {motion.pmdec:+.0f} ± {motion.pmdec_err:.0f} mas/yr "
                   f"from {motion_source}") if motion else "no motion fit"
    print(f"{result}: {motion_text}; {len(visits)} visits; {log['minutes']} min")


def _wave_table(header, frame_row, field):
    """Cached wavelength table for this frame; fetched once per calibration when online."""
    cached = CACHE_DIR / "wave" / f"{wavelength_calibration_id(header)}.fits"
    if cached.exists():
        return cached
    if frame_row is None or "uri" not in frame_row.colnames:
        return None
    return wavelength_table(frame_row, header, field)


if __name__ == "__main__":
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*breaking changes.*")
        main()
