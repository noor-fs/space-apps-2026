"""Step 1: Gaia DR3 layer for every target -> catalogs/layers/<key>/gaia.json"""
import csv, io, json, math, os, sys, time
from urllib.parse import quote_plus
import requests
from config import *
from common import *

GAIA_SYNC = SERVICES["Gaia TAP"]
GAIA_ASYNC = "https://gea.esac.esa.int/tap-server/tap/async"

def adql_where(ra, dec):
    return (f"WHERE 1 = CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra}, {dec}, {QUERY_RADIUS_DEG})) "
            f"AND phot_g_mean_mag < {GAIA_MAG_LIMIT}")

def gaia_async(adql, tag):
    path = _cache_path(tag + "_async", {"q": adql})
    if os.path.exists(path):
        return open(path, encoding="utf-8").read()
    r = requests.post(GAIA_ASYNC, data={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "PHASE": "RUN", "QUERY": adql},
                      timeout=TIMEOUT, allow_redirects=False, headers=HEADERS)
    job = r.headers["Location"]
    while True:
        time.sleep(3)
        ph = requests.get(job + "/phase", timeout=TIMEOUT).text.strip()
        if ph == "COMPLETED":
            break
        if ph in ("ERROR", "ABORTED"):
            raise RuntimeError("async job " + ph + ": " + requests.get(job, timeout=TIMEOUT).text[:500])
    text = requests.get(job + "/results/result", timeout=TIMEOUT).text
    open(path, "w", encoding="utf-8").write(text)
    return text

def fetch(key, ra, dec):
    count_text = tap_sync(GAIA_SYNC, f"SELECT COUNT(*) AS n FROM gaiadr3.gaia_source {adql_where(ra, dec)}", f"gaia_count_{key}")
    n = int(list(csv.DictReader(io.StringIO(count_text)))[0]["n"])
    adql = (f"SELECT source_id, ra, dec, pmra, pmdec, parallax, phot_g_mean_mag FROM gaiadr3.gaia_source {adql_where(ra, dec)}")
    text = tap_sync(GAIA_SYNC, adql, f"gaia_rows_{key}")
    rows = list(csv.DictReader(io.StringIO(text)))
    method = "sync"
    if len(rows) != n:
        print(f"  {key}: sync returned {len(rows)} rows but COUNT = {n}; using async job")
        text = gaia_async(adql, f"gaia_rows_{key}")
        rows = list(csv.DictReader(io.StringIO(text)))
        method = "async"
    if len(rows) != n:
        raise RuntimeError(f"{key}: row count {len(rows)} != COUNT(*) {n}")
    return rows, n, method

def simbad_names(key, ra, dec):
    """gaia source_id (str) -> SIMBAD main_id, one TAP query per target. Returns {} if SIMBAD unreachable."""
    adql = ("SELECT i.id AS gaia_id, b.main_id AS main_id FROM ident AS i JOIN basic AS b ON i.oidref = b.oid "
            f"WHERE i.id LIKE 'Gaia DR3 %' AND 1 = CONTAINS(POINT('ICRS', b.ra, b.dec), CIRCLE('ICRS', {ra}, {dec}, {QUERY_RADIUS_DEG}))")
    try:
        text = simbad_query(adql, f"simbad_gaianames_{key}")
    except Exception as e:
        print(f"  {key}: SIMBAD names unavailable ({e}); labels repeat name")
        return {}
    out = {}
    for r in sorted(csv.DictReader(io.StringIO(text)), key=lambda r: (r["gaia_id"], r["main_id"])):
        out.setdefault(r["gaia_id"].replace("Gaia DR3 ", "").strip(), r["main_id"])
    return out

def num(v, nd):
    if v is None or v == "" or v.lower() == "nan":
        return None
    f = float(v)
    return round(f, nd) if math.isfinite(f) else None

def build(key):
    name, ra0, dec0, sid = TARGETS[key]
    rows, n, method = fetch(key, ra0, dec0)
    names = simbad_names(key, ra0, dec0)
    out = []
    for r in rows:
        s = r["source_id"].strip()
        nm = f"Gaia DR3 {s}"
        simbad = names.get(s)
        out.append({
            "name": nm,
            "label": simbad if simbad else nm,
            "type": "star", "layer": "gaia",
            "ra": num(r["ra"], 6), "dec": num(r["dec"], 6), "epoch": 2016.0,
            "pmra_mas_yr": num(r["pmra"], 2), "pmdec_mas_yr": num(r["pmdec"], 2),
            "g_mag": num(r["phot_g_mean_mag"], 2),
            "source": "Gaia DR3",
            "url": "https://simbad.cds.unistra.fr/simbad/sim-id?Ident=" + (quote_plus(simbad) if simbad else f"Gaia+DR3+{s}"),
        })
    out.sort(key=lambda e: (e["g_mag"], e["name"]))
    path = os.path.join(LAYERS, key, "gaia.json")
    write_json(path, out)
    log_service("Gaia TAP", GAIA_SYNC, f"{method}")
    named = sum(1 for e in out if e["label"] != e["name"])
    print(f"{key}: count={n} rows={len(out)} method={method} simbad-named={named} size={os.path.getsize(path)/1e6:.2f} MB")

if __name__ == "__main__":
    keys = sys.argv[1:] or list(TARGETS)
    for k in keys:
        build(k)
