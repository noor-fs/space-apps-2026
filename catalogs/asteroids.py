"""Step 7: asteroid layer from the JPL Small-Body Identification API.

API facts (read from https://ssd-api.jpl.nasa.gov/doc/sb_ident.html and verified against live responses on 2026-11-14):
 * obs-time  YYYY-MM-DD_hh:mm:ss (UT); mpc-code=500 is accepted and reported as "Geocentric".
 * fov-ra-center  hh-mm-ss.ss ; fov-dec-center  dd-mm-ss.ss, minus sign written as 'M'.
 * fov-ra-hwidth is in RA COORDINATE degrees (verified: 0.18 -> fov_offset 00:00:43.20 = 43.2 s of RA),
   NOT degrees on the sky. So an on-sky half-width W needs fov-ra-hwidth = W / cos(dec).
 * The default first pass is a coarse two-body candidate list (errors of millions of arcsec); positions are only
   usable with two-pass=true, suppress-first-pass=true, which returns data_second_pass.
 * Response rows: [name, RA 'hh:mm:ss.ss', Dec "+dd mm'ss.s\"", dRA, dDec, dNorm, V mag, RA rate, Dec rate].
Usage:
   python catalogs/asteroids.py --test              # made-up times, Epsilon Indi B field -> catalogs/test_output/
   python catalogs/asteroids.py --from-manifests [target_key ...]   # real times from data/<key>/fov*/manifest.json -> asteroid layer + overlays.json
                                                  # (~50 s per time per request; cached, so safe to stop and re-run)
"""
import glob, json, math, os, re, sys
from urllib.parse import quote
from config import *
from common import http, write_json, log_service
from geometry import radec_to_pixel, in_field

API = SERVICES["JPL sb_ident"]
MAX_S = max(FIELD_SIZES)

def _time_param(t):
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})Z", t)
    if not m:
        raise ValueError(f"bad time string {t!r}")
    return f"{m.group(1)}_{m.group(2)}"

def _hms(ra_deg):
    s = round((ra_deg % 360) / 15 * 3600, 2)
    s = s % 86400
    h, rem = divmod(s, 3600); m, sec = divmod(rem, 60)
    return f"{int(h):02d}-{int(m):02d}-{sec:05.2f}"

def _dms(dec_deg):
    sign = "M" if dec_deg < 0 else ""
    s = round(abs(dec_deg) * 3600, 2)
    d, rem = divmod(s, 3600); m, sec = divmod(rem, 60)
    return f"{sign}{int(d):02d}-{int(m):02d}-{sec:05.2f}"

def parse_ra(s):
    h, m, sec = s.strip().split(":")
    return (float(h) + float(m) / 60 + float(sec) / 3600) * 15.0

def parse_dec(s):
    mm = re.fullmatch(r"\s*([+-]?)(\d+)\s+(\d+)'([\d.]+)\"\s*", s)
    if not mm:
        raise ValueError(f"unparseable Dec {s!r}")
    v = int(mm.group(2)) + int(mm.group(3)) / 60 + float(mm.group(4)) / 3600
    return -v if mm.group(1) == "-" else v

def _request(t, center_ra, center_dec, half_width):
    hw_ra = half_width / math.cos(math.radians(center_dec))   # RA half-width is in coordinate degrees
    params = {"sb-kind": "a", "mpc-code": "500", "obs-time": _time_param(t),
              "fov-ra-center": _hms(center_ra), "fov-dec-center": _dms(center_dec),
              "fov-ra-hwidth": f"{hw_ra:.5f}", "fov-dec-hwidth": f"{half_width:.5f}",
              "mag-required": "false", "two-pass": "true", "suppress-first-pass": "true", "req-elem": "false"}
    text = http("GET", API, "jpl_sbident", params=params)
    log_service("JPL sb_ident", API, "two-pass, mpc-code=500, sb-kind=a")
    return json.loads(text)

def asteroid_positions(times_utc, center_ra, center_dec, half_width=0.18):
    """For each UTC time string return a list of {'name','ra','dec'} (decimal degrees) for asteroids found in the
    box (geocentric prediction), KEPT ONLY IF inside the largest (201 px) field. One request per time, sequential."""
    results = []
    for t in times_utc:
        j = _request(t, center_ra, center_dec, half_width)
        if j.get("signature", {}).get("version") != "1.1":
            print("WARNING: sb_ident version", j.get("signature"))
        rows = j.get("data_second_pass") or []
        found, seen = [], set()
        for r in rows:
            ra, dec = parse_ra(r[1]), parse_dec(r[2])
            c, rw = radec_to_pixel(ra, dec, center_ra, center_dec, MAX_S)
            if in_field(c, rw, MAX_S) and r[0] not in seen:
                seen.add(r[0])
                found.append({"name": r[0], "ra": round(ra, 6), "dec": round(dec, 6)})
        results.append(found)
    return results

def asteroid_entries(times_utc, results):
    """Group per-time results into overlay entries (positions use the given time strings unchanged)."""
    by = {}
    for t, found in zip(times_utc, results):
        for a in found:
            by.setdefault(a["name"], []).append({"time": t, "ra": a["ra"], "dec": a["dec"]})
    out = []
    for name in sorted(by):
        out.append({"name": name, "label": name, "type": "asteroid", "layer": "asteroids",
                    "positions": sorted(by[name], key=lambda p: p["time"]),
                    "source": "JPL Small-Body Identification API",
                    "url": "https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr=" + quote(name, safe="")})
    return out

def run(key, times):
    ra, dec = center(key)
    res = asteroid_positions(times, ra, dec)
    return asteroid_entries(times, res), res

def _spread(times, n):
    """n evenly spaced items of the sorted list (always includes first and last)."""
    if not n or len(times) <= n:
        return times
    return [times[round(i * (len(times) - 1) / (n - 1))] for i in range(n)]

def from_manifests(keys=None, max_times=None):
    import build_overlays
    for key in (keys or TARGETS):
        build_overlays.require_catalog_layers(key)   # fail now, not after hours of JPL requests
        files = sorted(glob.glob(os.path.join(DATA, key, "fov*", "manifest.json")))
        if not files:
            print(f"{key}: no manifest yet - asteroid layer left unchanged/absent"); continue
        times = set()
        for f in files:
            for v in json.load(open(f, encoding="utf-8")).get("visits", []):
                times.update(fr["time"] for fr in v.get("frames", []))
        times = sorted(times)
        bad = [t for t in times if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", str(t))]
        if bad:
            raise SystemExit(f"{key}: manifest time strings must look like YYYY-MM-DDTHH:MM:SSZ; found {bad[:3]}")
        total = len(times)
        times = _spread(times, max_times)
        entries, res = run(key, times)
        write_json(os.path.join(LAYERS, key, "asteroids.json"), entries)
        build_overlays.build(key)
        print(f"{key}: {len(files)} manifests, {len(times)} of {total} times, {len(entries)} asteroids")

# ---- windowed mode: one JPL request per ~1-day window, positions at each frame time by straight-line motion ----
# Checked on cached JPL answers (2026-11-15): returned rates are on-sky ("/h, RA rate already includes cos Dec);
# a straight-line move from the query time is within ~0.25 px for |dt| <= 10 h and ~0.4 px at 13 h, so windows span <= 24 h
# and are queried at their middle (max |dt| = 12 h).
WINDOW_H = 24.0
BOX_EXTRA_DEG = 0.15          # main-belt asteroids move up to ~0.1-0.15 deg in 12 h

def _parse_t(t):
    import datetime as dt
    return dt.datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ")

def _fmt_t(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")

def make_windows(times, hours=WINDOW_H):
    """Greedy windows of at most `hours`; returns [(query_time_str, [frame times])], query time = middle of the window."""
    ts = sorted(times); out = []; i = 0
    while i < len(ts):
        t0 = _parse_t(ts[i]); j = i
        while j + 1 < len(ts) and (_parse_t(ts[j + 1]) - t0).total_seconds() <= hours * 3600:
            j += 1
        mid = t0 + (_parse_t(ts[j]) - t0) / 2
        out.append((_fmt_t(mid.replace(microsecond=0)), ts[i:j + 1])); i = j + 1
    return out

def windowed_entries(times, center_ra, center_dec):
    by = {}
    for q, frames in make_windows(times):
        j = _request(q, center_ra, center_dec, 0.18 + BOX_EXTRA_DEG)
        qd = _parse_t(q)
        for r in j.get("data_second_pass") or []:
            ra0, dec0 = parse_ra(r[1]), parse_dec(r[2])
            rra, rdec = float(r[7]), float(r[8])               # "/h on the sky
            v = float(r[6]) if r[6].strip() else None
            for t in frames:
                h = (_parse_t(t) - qd).total_seconds() / 3600
                dec = dec0 + rdec * h / 3600
                ra = ra0 + rra * h / math.cos(math.radians(dec0)) / 3600
                c, rw = radec_to_pixel(ra, dec, center_ra, center_dec, MAX_S)
                if in_field(c, rw, MAX_S):
                    e = by.setdefault(r[0], {"mag": v, "positions": {}})
                    e["positions"][t] = {"time": t, "ra": round(ra, 6), "dec": round(dec, 6)}
    out = []
    for name in sorted(by):
        out.append({"name": name, "label": name, "type": "asteroid", "layer": "asteroids",
                    "positions": sorted(by[name]["positions"].values(), key=lambda p: p["time"]),
                    "v_mag": by[name]["mag"],
                    "source": "JPL Small-Body Identification API",
                    "url": "https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr=" + quote(name, safe="")})
    return out

def from_manifests_windowed(keys=None):
    import build_overlays
    for key in (keys or TARGETS):
        build_overlays.require_catalog_layers(key)   # fail now, not after hours of JPL requests
        files = sorted(glob.glob(os.path.join(DATA, key, "fov*", "manifest.json")))
        if not files:
            print(f"{key}: no manifest yet"); continue
        times = set()
        for f in files:
            for v in json.load(open(f, encoding="utf-8")).get("visits", []):
                times.update(fr["time"] for fr in v.get("frames", []))
        times = sorted(times)
        ra, dec = center(key)
        entries = windowed_entries(times, ra, dec)
        write_json(os.path.join(LAYERS, key, "asteroids.json"), entries)
        build_overlays.build(key)
        print(f"{key}: {len(make_windows(times))} windows for {len(times)} times, {len(entries)} asteroids")

def test():
    times = ["2025-04-18T03:12:45Z", "2025-04-18T03:15:10Z", "2025-04-18T03:19:30Z", "2025-04-18T03:24:02Z"]
    entries, res = run("epsilon_indi_b", times)
    os.makedirs(os.path.join(AMNA, "test_output"), exist_ok=True)
    write_json(os.path.join(AMNA, "test_output", "epsilon_indi_b_asteroids_TEST.json"),
               {"NOTE": "made-up times; never copy to data/", "times": times, "per_time": res, "entries": entries})
    print("times:", times); print("found per time:", [len(r) for r in res]); print("entries:", len(entries))

if __name__ == "__main__":
    if "--windowed" in sys.argv:
        rest = [a for a in sys.argv[sys.argv.index("--windowed") + 1:] if not a.startswith("--")]
        from_manifests_windowed(rest or None)
    elif "--from-manifests" in sys.argv:
        # optional target keys after the flag, e.g.  --from-manifests barnards_star r_draconis
        args = sys.argv[sys.argv.index("--from-manifests") + 1:]
        mt = int(args[args.index("--max-times") + 1]) if "--max-times" in args else None
        rest = [a for a in args if not a.startswith("--") and not a.isdigit()]
        from_manifests(rest or None, mt)
    elif "--test" in sys.argv:
        test()
    else:
        print(__doc__)
