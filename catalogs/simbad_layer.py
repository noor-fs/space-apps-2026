"""Step 2: SIMBAD layer -> catalogs/layers/<key>/simbad.json (positions are epoch 2000.0)."""
import csv, io, math, os, sys
from urllib.parse import quote_plus
from config import *
from common import *

def load_map():
    with open(os.path.join(DATA, "simbad_otype_map.csv"), encoding="utf-8", newline="") as f:
        return {r["otype"]: r["our_type"] for r in csv.DictReader(f)}

def num(v, nd):
    if v is None or v == "" or v.lower() == "nan":
        return None
    f = float(v)
    return round(f, nd) if math.isfinite(f) else None

def fetch(key):
    ra, dec = center(key)
    adql = ("SELECT main_id, ra, dec, pmra, pmdec, otype FROM basic "
            f"WHERE 1 = CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra}, {dec}, {QUERY_RADIUS_DEG}))")
    return list(csv.DictReader(io.StringIO(simbad_query(adql, f"simbad_cone_{key}"))))

def build(key):
    omap = load_map()
    rows = fetch(key)
    out, skipped, seen = [], 0, set()
    for r in rows:
        if r["ra"] == "" or r["dec"] == "":
            skipped += 1
            continue
        mid = r["main_id"]
        if mid in seen:
            continue
        seen.add(mid)
        out.append({
            "name": mid, "label": mid,
            "type": omap.get(r["otype"].strip(), "unknown"), "layer": "simbad",
            "ra": num(r["ra"], 6), "dec": num(r["dec"], 6), "epoch": 2000.0,
            "pmra_mas_yr": num(r["pmra"], 2), "pmdec_mas_yr": num(r["pmdec"], 2),
            "source": "SIMBAD",
            "url": "https://simbad.cds.unistra.fr/simbad/sim-id?Ident=" + quote_plus(mid),
        })
    out.sort(key=lambda e: e["name"])
    path = os.path.join(LAYERS, key, "simbad.json")
    write_json(path, out)
    from collections import Counter
    print(f"{key}: rows={len(rows)} written={len(out)} skipped(no pos)={skipped} types={dict(Counter(e['type'] for e in out))}")

if __name__ == "__main__":
    for k in (sys.argv[1:] or list(TARGETS)):
        build(k)
