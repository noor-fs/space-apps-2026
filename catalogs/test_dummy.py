"""Practice run with DUMMY manifests, so problems show up before Yara T's real files arrive.

    python catalogs/test_dummy.py

What it does (the real data/ and layers/ are never touched; everything happens in catalogs/test_output/sandbox/):
 1. copies the current data/ and layers/ into the sandbox;
 2. writes dummy fields.json + manifest.json files in the Saturday-plan format for RW Aurigae (two field sizes that
    share some image times, like the real files will) and none for the other targets;
 3. runs the real asteroid step (`asteroids.py --from-manifests`), the merge (`build_overlays.py`) and the validator,
    all pointed at the sandbox (environment variable CATALOGS_SANDBOX);
 4. plays the part of the website: reads the sandbox files and checks that every manifest time matches asteroid
    positions exactly, that markers land inside the image, and that moving stars can be placed for a visit date;
 5. checks that a badly written time string stops with a clear message.
Takes about 2 minutes the first time (JPL answers in ~50 s per image time); repeats are fast (answers are cached)."""
import json, os, shutil, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
SANDBOX = os.path.join(HERE, "test_output", "sandbox")
os.environ["CATALOGS_SANDBOX"] = SANDBOX
sys.path.insert(0, HERE)
from config import *            # DATA / LAYERS now point into the sandbox
from geometry import radec_to_pixel, propagate, in_field, jyear

REAL_DATA = os.path.join(ROOT, "data")
REAL_LAYERS = os.path.join(HERE, "layers")
KEY = "rw_aurigae"
T1, T2 = "2025-10-21T03:12:45Z", "2025-10-21T09:40:10Z"        # made-up image times
RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append(ok); print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail and not ok else ""))

def frame(i, t, wl):
    return {"i": i, "image": f"frames/v1_{i}.png", "time": t, "detector": 3, "wavelength_um": wl,
            "target_expected_px": None, "target_measured_px": None, "saturated": False, "bad_pixel_fraction": 0.0,
            "target_flux_mjy": None, "target_flux_err_mjy": None, "data": f"frames/v1_{i}.f32",
            "flags": f"frames/v1_{i}_flags.png", "archive_url": "https://irsa.ipac.caltech.edu/"}

def manifest(S, frames):
    return {"target_key": KEY, "name": "RW Aurigae",
            "grid": {"center_ra": TARGETS[KEY][1], "center_dec": TARGETS[KEY][2], "center_date": CENTER_DATE,
                     "pixel_scale_arcsec": 6.15, "size_px": S},
            "visits": [{"n": 1, "image": "visit_1.png", "image_rgb": "visit_1_rgb.png", "date_start": "2025-10-21",
                        "date_end": "2025-10-22", "date_mid": "2025-10-21", "n_images": len(frames),
                        "wavelength_um": [0.75, 5.0], "target_expected_px": None, "target_measured_px": None,
                        "saturated": False, "frames": frames}],
            "verdict": "no_motion_detected", "measured_motion_mas_yr": None, "catalog_motion_mas_yr": None}

def run(args):
    t = time.time()
    p = subprocess.run([sys.executable] + args, capture_output=True, text=True, cwd=HERE, env=os.environ)
    return p.returncode, p.stdout + p.stderr, time.time() - t

t0 = time.time()
print("== 1. sandbox ==")
shutil.rmtree(SANDBOX, ignore_errors=True)
shutil.copytree(REAL_DATA, DATA); shutil.copytree(REAL_LAYERS, LAYERS)
before = {p: os.path.getsize(p) for p in [os.path.join(REAL_DATA, KEY, "overlays.json")]}
print("sandbox at", SANDBOX)

print("\n== 2. dummy fields.json and manifests (RW Aurigae only) ==")
d = os.path.join(DATA, KEY)
json.dump({"sizes_px": [51, 201]}, open(os.path.join(d, "fields.json"), "w"))
for S, frames in ((51, [frame(1, T1, 1.1), frame(2, T2, 2.0)]), (201, [frame(1, T2, 2.0), frame(2, T1, 1.1)])):
    os.makedirs(os.path.join(d, f"fov{S}"), exist_ok=True)
    json.dump(manifest(S, frames), open(os.path.join(d, f"fov{S}", "manifest.json"), "w"), indent=1)
check("dummy manifests written (fov51, fov201; the two image times are shared between them)", True)

print("\n== 3. real scripts, pointed at the sandbox ==")
rc, out, secs = run(["asteroids.py", "--from-manifests"])
print(out.strip()[-600:])
check(f"asteroids.py --from-manifests finished ({secs:.0f} s)", rc == 0, out[-300:])
check("only the target with a manifest was processed; the others were skipped", out.count("no manifest yet") == len(TARGETS) - 1)
check("2 shared times were queried once each (union, no repeats)", f"{KEY}: 2 manifests, 2 times" in out, out[-300:])
rc, out, secs = run(["build_overlays.py"])
check("build_overlays.py finished and all centering checks PASS", rc == 0 and "FAIL" not in out and out.count("PASS") == 5, out[-300:])
rc, out, secs = run(["validate.py"])
tail = [l for l in out.splitlines() if l.startswith("RESULT")]
check("validate.py: " + (tail[0] if tail else "no result line"), rc == 0, out[-400:])

print("\n== 4. the website's point of view ==")
ov = json.load(open(os.path.join(DATA, KEY, "overlays.json"), encoding="utf-8"))
ast = [e for e in ov if e["layer"] == "asteroids"]
print(f"   {len(ast)} asteroid entries, {sum(len(e['positions']) for e in ast)} positions")
check("overlays.json is valid JSON and has asteroid entries for the dummy times", len(ast) > 0)
check("asteroid entries have 'positions' and no ra/dec/epoch/pm keys",
      all("positions" in e and not ({"ra", "dec", "epoch", "pmra_mas_yr", "pmdec_mas_yr"} & set(e)) for e in ast))
manifest_times = set()
for S in (51, 201):
    for v in json.load(open(os.path.join(d, f"fov{S}", "manifest.json")))["visits"]:
        manifest_times |= {f["time"] for f in v["frames"]}
pos_times = {p["time"] for e in ast for p in e["positions"]}
check("every asteroid time string equals a manifest frames[].time exactly", pos_times <= manifest_times, str(pos_times - manifest_times))
_, ra0, dec0, _ = TARGETS[KEY]
inside = [in_field(*radec_to_pixel(p["ra"], p["dec"], ra0, dec0, 201), 201) for e in ast for p in e["positions"]]
check("every asteroid position lands inside the 201 px image", all(inside))
# placing a star the way the site does, on the dummy visit date (date_mid 2025-10-21)
visible = {S: 0 for S in (51, 101, 201)}
for e in ov:
    if "positions" in e: continue
    r, dd = propagate(e["ra"], e["dec"], e["epoch"], e["pmra_mas_yr"], e["pmdec_mas_yr"], "2025-10-21")
    for S in visible:
        visible[S] += in_field(*radec_to_pixel(r, dd, ra0, dec0, S), S)
print("   markers visible on the dummy visit date (51/101/201):", visible)
check("star markers can be placed on a visit date and the counts grow with field size", visible[51] <= visible[101] <= visible[201] and visible[51] > 0)
tgt = [e for e in ov if e["name"] == "Gaia DR3 156430822114424576"]
px = radec_to_pixel(*propagate(tgt[0]["ra"], tgt[0]["dec"], 2016.0, tgt[0]["pmra_mas_yr"], tgt[0]["pmdec_mas_yr"], "2026-01-01"), ra0, dec0, 51)
check(f"target (RW Aur A) sits on the center pixel on 2026-01-01: ({px[0]:.2f}, {px[1]:.2f})", abs(px[0] - 25) < 0.1 and abs(px[1] - 25) < 0.1)

print("\n== 5. a badly written time must stop with a clear message ==")
bad = manifest(51, [frame(1, "2025-10-21 03:12:45", 1.1)])
shutil.rmtree(os.path.join(d, "fov201")); json.dump(bad, open(os.path.join(d, "fov51", "manifest.json"), "w"))
rc, out, _ = run(["asteroids.py", "--from-manifests", KEY])
check("bad time string -> stops with 'YYYY-MM-DDTHH:MM:SSZ' message, no JPL call", rc != 0 and "YYYY-MM-DDTHH:MM:SSZ" in out, out[-200:])

print("\n== 6. the real files were not touched ==")
check("real data/rw_aurigae/overlays.json unchanged in size", os.path.getsize(os.path.join(REAL_DATA, KEY, "overlays.json")) == before[os.path.join(REAL_DATA, KEY, "overlays.json")])
check("no fields.json / fov folders created in the real data/", not os.path.exists(os.path.join(REAL_DATA, KEY, "fields.json")))
print(f"\n{sum(RESULTS)}/{len(RESULTS)} checks passed in {time.time() - t0:.0f} s")
sys.exit(0 if all(RESULTS) else 1)
