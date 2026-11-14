"""Section 7 validator. Prints PASS/FAIL per check; exit code 1 if anything FAILs."""
import time, csv, glob, json, math, os, re, sys
import requests, yaml
from config import *
from geometry import *

FAILS = []
def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)
def info(msg): print("INFO  " + msg)

def load_json(path):
    def bad(c): raise ValueError(f"non-finite constant {c}")
    with open(path, encoding="utf-8") as f:
        return json.load(f, parse_constant=bad)

NUM = (int, float)
TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
BASE_KEYS = {"name", "label", "type", "layer", "ra", "dec", "epoch", "pmra_mas_yr", "pmdec_mas_yr", "source", "url"}
AST_KEYS = {"name", "label", "type", "layer", "positions", "source", "url"}

# ---------- explanations ----------
expl_path = os.path.join(DATA, "explanations.json")
try:
    E = load_json(expl_path); expl_ok = True
except Exception as e:
    E = {}; expl_ok = False
check("explanations.json exists and is valid JSON", expl_ok)

# ---------- overlays ----------
print("\n== overlays ==")
for key, (name, ra0, dec0, sid) in TARGETS.items():
    p = os.path.join(DATA, key, "overlays.json")
    try:
        O = load_json(p); ok = isinstance(O, list)
    except Exception as e:
        check(f"{key}: overlays.json valid JSON, no NaN", False, str(e)); continue
    check(f"{key}: overlays.json valid JSON, no NaN", ok)
    errs, far = [], []
    seen = {}
    for e in O:
        nm = e.get("name", "?")
        if e.get("layer") not in ALLOWED_LAYERS: errs.append(f"{nm}: layer {e.get('layer')}")
        if e.get("type") not in ALLOWED_TYPES: errs.append(f"{nm}: type {e.get('type')}")
        if E and e.get("type") not in E.get("types", {}): errs.append(f"{nm}: type not in explanations")
        for k in ("name", "label", "source", "url"):
            if not isinstance(e.get(k), str) or not e.get(k): errs.append(f"{nm}: bad {k}")
        seen.setdefault((e.get("layer"), nm), 0); seen[(e.get("layer"), nm)] += 1
        if e.get("layer") == "asteroids":
            if set(e) != AST_KEYS: errs.append(f"{nm}: asteroid keys {sorted(set(e) ^ AST_KEYS)}")
            if e.get("type") != "asteroid": errs.append(f"{nm}: asteroid type")
            ps = e.get("positions")
            if not isinstance(ps, list) or not ps: errs.append(f"{nm}: positions"); continue
            for q in ps:
                if set(q) != {"time", "ra", "dec"} or not TIME_RE.match(str(q.get("time"))) or not isinstance(q.get("ra"), NUM) or not isinstance(q.get("dec"), NUM):
                    errs.append(f"{nm}: bad position {q}")
            if [q["time"] for q in ps] != sorted(q["time"] for q in ps): errs.append(f"{nm}: positions not sorted")
            continue
        want = set(BASE_KEYS) | ({"g_mag"} if e.get("layer") == "gaia" else set())
        if set(e) != want: errs.append(f"{nm}: keys differ {sorted(set(e) ^ want)}")
        want_epoch = {"gaia": 2016.0, "simbad": 2000.0, "vsx": 2000.0}.get(e.get("layer"))
        if e.get("epoch") != want_epoch: errs.append(f"{nm}: epoch {e.get('epoch')}")
        for k in ("pmra_mas_yr", "pmdec_mas_yr"):
            if e.get(k) is not None and not isinstance(e.get(k), NUM): errs.append(f"{nm}: {k}")
        if e.get("layer") == "gaia" and not isinstance(e.get("g_mag"), NUM): errs.append(f"{nm}: g_mag")
        r, d = e.get("ra"), e.get("dec")
        if not (isinstance(r, NUM) and isinstance(d, NUM) and 0 <= r < 360 and -90 <= d <= 90):
            errs.append(f"{nm}: coordinates {r},{d}"); continue
        if angsep_deg(r, d, ra0, dec0) > QUERY_RADIUS_DEG + 1e-9:
            far.append((e["layer"], nm, e.get("pmra_mas_yr") is not None))
    check(f"{key}: required keys, allowed layer/type, epochs, pm, coordinates, asteroid format ({len(O)} entries)", not errs, "; ".join(errs[:5]) + f" (+{len(errs)-5} more)" if len(errs) > 5 else "; ".join(errs))
    dup_in_layer = [k for k, v in seen.items() if v > 1]
    check(f"{key}: name unique within each layer", not dup_in_layer, str(dup_in_layer[:3]))
    cross = len({n for (_, n) in seen}) != len(seen)
    info(f"{key}: same name appears in more than one layer for {len(seen) - len({n for (_, n) in seen})} objects (expected: same star in Gaia/SIMBAD/VSX) -> see Questions for the group")
    far_nopm = [f for f in far if not f[2]]
    check(f"{key}: all non-asteroid entries within {QUERY_RADIUS_DEG} deg of center (exceptions allowed only with proper motion)", not far_nopm, str(far_nopm[:3]))
    if far: info(f"{key}: {len(far)} entries beyond 0.3 deg of the center (with proper motion, kept): {far[:3]}")
    sz = os.path.getsize(p)
    info(f"{key}: overlays.json {sz/1e6:.2f} MB" + ("  (> 3 MB: report to group)" if sz > 3e6 else ""))

# ---------- explanations ----------
print("\n== explanations.json ==")
if E:
    check("exactly the 7 type keys", set(E.get("types", {})) == set(ALLOWED_TYPES))
    check("exactly the 6 verdict keys", set(E.get("verdicts", {})) == set(VERDICTS))
    check("exactly the 5 target keys", set(E.get("targets", {})) == set(TARGETS))
    check("both about keys", set(E.get("about", {})) == {"how_it_works", "limits"})
    check("top-level keys are types/verdicts/targets/about", set(E) == {"types", "verdicts", "targets", "about"})
    bad = []
    for sect in ("types", "verdicts", "targets", "about"):
        for k, v in E[sect].items():
            if not (isinstance(v.get("title"), str) and v["title"] and isinstance(v.get("text"), str) and v["text"] and isinstance(v.get("sources"), list)): bad.append(f"{sect}.{k}")
            for s in v.get("sources", []):
                if not (isinstance(s.get("label"), str) and s["label"] and isinstance(s.get("url"), str) and s["url"]): bad.append(f"{sect}.{k} source")
    check("every entry has title, text, sources[{label,url}]", not bad, str(bad[:4]))
    # simbad map source on relevant types
    rel = ["star", "brown_dwarf", "variable_star", "galaxy", "young_star", "unknown"]
    check("SIMBAD mapping source (data/simbad_otype_map.csv) on the SIMBAD-derived type entries",
          all(any(s["url"] == "data/simbad_otype_map.csv" and s["label"] == "How SIMBAD object types map to our types" for s in E["types"][t]["sources"]) for t in rel))
    # yaml: every factual sentence has a source
    y = yaml.safe_load(open(os.path.join(AMNA, "explanations_src.yaml"), encoding="utf-8"))
    miss, nf, nsent = [], 0, 0
    texts_match = True
    for sect in ("types", "verdicts", "targets", "about"):
        for k, ent in y[sect].items():
            for s in ent["sentences"]:
                nsent += 1
                if s["f"] and not s["s"]: miss.append(f"{sect}.{k}: {s['t'][:40]}")
                if not s["f"]: nf += 1
            if " ".join(s["t"].strip() for s in ent["sentences"]) != E[sect][k]["text"]: texts_match = False
    check(f"every factual sentence in explanations_src.yaml has >=1 source ({nsent} sentences, {nf} flagged non-factual)", not miss, str(miss[:3]))
    check("explanations.json text matches explanations_src.yaml (regenerate if not)", texts_match)
    nonfactual_with_sourceless_verdicts = all(not E["verdicts"][v]["sources"] for v in VERDICTS)
    check("verdict definitions only restate the table (sources [])", nonfactual_with_sourceless_verdicts)
    lim = E["about"]["limits"]["text"].lower()
    pts = {"pixels 6.15": "6.15" in lim and "pixel" in lim and "motion" in lim,
           "different wavelength": "different wavelength" in lim,
           "saturate": "saturate" in lim,
           "red/blue not proof": "red" in lim and "blue" in lim and "not proof" in lim}
    check("about.limits mentions all four required points", all(pts.values()), str(pts))
    # sentence-count sanity (type/target 2-4; verdict 1-3)
    def nsent_of(sect, k): return len(y[sect][k]["sentences"])
    sc = [f"types.{k}" for k in ALLOWED_TYPES if not 2 <= nsent_of("types", k) <= 4] + \
         [f"targets.{k}" for k in TARGETS if not 2 <= nsent_of("targets", k) <= 4] + \
         [f"verdicts.{k}" for k in VERDICTS if not 1 <= nsent_of("verdicts", k) <= 3]
    check("sentence counts: types/targets 2-4, verdicts 1-3", not sc, str(sc))
    # source URLs
    urls = sorted({s["url"] for sect in E.values() for v in sect.values() for s in v["sources"]})
    badurl = []
    H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
    for u in urls:
        if not u.startswith("http"):
            if not os.path.exists(os.path.join(ROOT, u)): badurl.append((u, "missing local file"))
            continue
        code = None
        for _ in range(3):
            try:
                code = requests.get(u, headers=H, timeout=45, stream=True).status_code
                if 200 <= code < 300: break
            except Exception as ex:
                code = type(ex).__name__
            time.sleep(4)          # busy or rate-limited server: wait and ask again
        if not (isinstance(code, int) and 200 <= code < 300): badurl.append((u, code))   # 2xx = page reachable (some sites answer 202 to scripts)
    check(f"every source URL returns HTTP 200 / local file exists ({len(urls)} urls)", not badurl, str(badurl))

# ---------- credits ----------
print("\n== credits.json ==")
try:
    C = load_json(os.path.join(DATA, "credits.json")); ok = isinstance(C, list)
except Exception as e:
    C, ok = [], False
check("credits.json valid JSON list", ok)
check("each entry has non-empty what/text/url", all(isinstance(c, dict) and set(c) == {"what", "text", "url"} and all(isinstance(c[k], str) and c[k].strip() for k in c) for c in C))
need = ["SPHEREx", "Gaia", "SIMBAD", "VSX", "CatWISE", "JPL", "SpeX", "CALSPEC", "SWIRE"]
blob = [c["what"] for c in C]
check("one entry per source (SPHEREx/IRSA, Gaia, SIMBAD, VSX, CatWISE, JPL, SpeX, CALSPEC, SWIRE)",
      all(sum(n.lower() in w.lower() for w in blob) == 1 for n in need) and len(C) == len(need), str([n for n in need if sum(n.lower() in w.lower() for w in blob) != 1]))
todo = [c["what"] for c in C if "TODO" in c["text"]]
check("no TODO text in credits", not todo, str(todo))
info("credits: AAVSO text is copied verbatim and still contains the bracketed choice [photometric, spectroscopic, solar, exoplanet] -> manual_todo item")

# ---------- spectra ----------
print("\n== spectra ==")
import spectra as SP
import numpy as np
files = sorted(glob.glob(os.path.join(DATA, "spectra", "*.csv")))
need_files = {"star_g", "star_m", "brown_dwarf_l", "brown_dwarf_t", "galaxy"}
check("required spectra files exist", need_files <= {os.path.basename(f)[:-4] for f in files})
for f in files:
    nm = os.path.basename(f)[:-4]
    with open(f, encoding="utf-8", newline="") as fh:
        rdr = list(csv.reader(fh))
    hdr, rows = rdr[0], rdr[1:]
    errs = []
    if hdr != ["wavelength_um", "flux_norm", "source"]: errs.append("header")
    try:
        w = [float(r[0]) for r in rows]; fl = [float(r[1]) for r in rows]
    except Exception: errs.append("non-numeric"); w, fl = [], []
    if any(len(r) != 3 for r in rows): errs.append("column count")
    if any(not math.isfinite(x) for x in w + fl): errs.append("nan/inf")
    if any(b <= a for a, b in zip(w, w[1:])): errs.append("wavelengths not strictly increasing")
    if w and (w[0] < 0.75 - 1e-9 or w[-1] > 5.0 + 1e-9): errs.append("outside 0.75-5.0")
    if any(x <= 0 for x in fl): errs.append("flux not positive")
    at22 = [r for r in rows if abs(float(r[0]) - 2.2) < 1e-9]
    if len(at22) != 1 or float(at22[0][1]) != 1.0: errs.append("2.2 um value not exactly 1")
    if len({r[2] for r in rows}) != 1: errs.append("source not identical on all rows")
    if any("F_nu" not in r[2] for r in rows[:1]): errs.append("source text lacks F_nu")
    if nm in SP.SPECS:
        wn, fn, en = SP.SPECS[nm][1]()
        okn = np.isfinite(wn) & np.isfinite(fn)
        if w and (w[-1] > np.nanmax(wn[okn]) + 1e-9 or w[0] < np.nanmin(wn[okn]) - 1e-9): errs.append("row beyond native coverage")
    check(f"spectra/{nm}.csv ({len(rows)} rows, {w[0] if w else '?'}-{w[-1] if w else '?'} um)", not errs, "; ".join(errs))

# ---------- asteroid module ----------
print("\n== asteroid module ==")
leak = [p for p in glob.glob(os.path.join(DATA, "**", "*"), recursive=True) if "TEST" in os.path.basename(p)]
check("no test output inside data/", not leak, str(leak))
import asteroids
check("asteroids.py exposes asteroid_positions(), asteroid_entries(), --from-manifests", all(hasattr(asteroids, n) for n in ("asteroid_positions", "asteroid_entries", "from_manifests")))
# parse/format self-test without network
check("asteroid sexagesimal parsing", abs(asteroids.parse_ra("05:07:58.87") - 76.99529) < 1e-4 and abs(asteroids.parse_dec("-03 53'38.5\"") + 3.894028) < 1e-5)
ex = asteroids.asteroid_entries(["2025-04-18T03:12:45Z"], [[{"name": "(1 Test)", "ra": 1.0, "dec": 2.0}]])[0]
check("asteroid entry format", set(ex) == AST_KEYS and ex["positions"][0]["time"] == "2025-04-18T03:12:45Z")

# ---------- geometry ----------
print("\n== geometry sanity (Gaia row of each target moved to 2026-01-01, S=51) ==")
for key, (name, ra0, dec0, sid) in TARGETS.items():
    if not sid: continue
    O = load_json(os.path.join(DATA, key, "overlays.json"))
    e = [x for x in O if x["name"] == f"Gaia DR3 {sid}" and x["layer"] == "gaia"]
    if not e: check(f"{key}: target Gaia row present", False); continue
    e = e[0]
    r, d = propagate(e["ra"], e["dec"], e["epoch"], e["pmra_mas_yr"], e["pmdec_mas_yr"], CENTER_DATE)
    c, rw = radec_to_pixel(r, d, ra0, dec0, 51)
    off = math.hypot(c - 25, rw - 25)
    check(f"{key}: lands at ({c:.3f},{rw:.3f}), offset {off:.3f} px (<=0.1)", off <= 0.1)
    sims = [x for x in O if x["layer"] == "simbad" and x["label"] == e["label"]]
    check(f"{key}: target star present in SIMBAD layer ({e['label']})", bool(sims))
wise = [x for x in load_json(os.path.join(DATA, "wise_0855", "overlays.json")) if x["layer"] == "simbad" and SIMBAD_TARGET["wise_0855"] in x["name"]]
check("wise_0855: target present in SIMBAD layer (WISEA J085510.74-071442.5)", bool(wise))
if wise:
    _, ra0w, dec0w, _ = TARGETS["wise_0855"]
    e = wise[0]
    r, d = propagate(e["ra"], e["dec"], e["epoch"], e["pmra_mas_yr"], e["pmdec_mas_yr"], CENTER_DATE)
    c, rw = radec_to_pixel(r, d, ra0w, dec0w, 51)
    off = math.hypot(c - 25, rw - 25)
    check(f"wise_0855: SIMBAD position lands at ({c:.3f},{rw:.3f}), offset {off:.3f} px (<=0.1)", off <= 0.1)

print("\nRESULT:", "ALL CHECKS PASSED" if not FAILS else f"{len(FAILS)} FAILED: {FAILS}")
sys.exit(1 if FAILS else 0)
