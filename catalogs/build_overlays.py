"""Step 8: merge catalogs/layers/<key>/<layer>.json (order gaia, simbad, vsx, asteroids) -> data/<key>/overlays.json,
then sanity-check geometry and print per-target/layer counts and in-field counts."""
import json, os
from config import *
from common import write_json
from geometry import *

def load(key, layer):
    p = os.path.join(LAYERS, key, f"{layer}.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []

def build(key):
    merged = []
    for layer in LAYER_ORDER:
        merged += load(key, layer)
    path = os.path.join(DATA, key, "overlays.json")
    write_json(path, merged)
    return merged, path

def inside_counts(entries, ra0, dec0):
    res = {}
    for S in FIELD_SIZES:
        n = 0
        for e in entries:
            if "positions" in e:
                continue
            r, d = propagate(e["ra"], e["dec"], e["epoch"], e["pmra_mas_yr"], e["pmdec_mas_yr"], CENTER_DATE)
            c, rw = radec_to_pixel(r, d, ra0, dec0, S)
            n += in_field(c, rw, S)
        res[S] = n
    return res

def main():
    print(f"{'target':16}{'layer':10}{'entries':>8}  in-field 51/101/201 on {CENTER_DATE}")
    for key, (name, ra0, dec0, sid) in TARGETS.items():
        merged, path = build(key)
        for layer in LAYER_ORDER:
            es = [e for e in merged if e["layer"] == layer]
            ic = inside_counts(es, ra0, dec0) if layer != "asteroids" else {}
            print(f"{key:16}{layer:10}{len(es):>8}  " + ("/".join(str(ic[s]) for s in FIELD_SIZES) if ic else "(positions per image)"))
        print(f"   -> {path}  {os.path.getsize(path)/1e6:.2f} MB, {len(merged)} entries")
    print("\nTarget-star centering check (Gaia row, or SIMBAD row for WISE 0855, moved to 2026-01-01, S=51, c=25; must be within 0.1 px of 25,25):")
    for key, (name, ra0, dec0, sid) in TARGETS.items():
        if sid:
            e = [x for x in load(key, "gaia") if x["name"] == f"Gaia DR3 {sid}"][0]
        else:
            e = [x for x in load(key, "simbad") if x["name"] == SIMBAD_TARGET[key]][0]
        r, d = propagate(e["ra"], e["dec"], e["epoch"], e["pmra_mas_yr"], e["pmdec_mas_yr"], CENTER_DATE)
        c, rw = radec_to_pixel(r, d, ra0, dec0, 51)
        off = ((c - 25) ** 2 + (rw - 25) ** 2) ** 0.5
        print(f"  {key}: pixel=({c:.3f},{rw:.3f}) offset={off:.3f} px  {'PASS' if off <= 0.1 else 'FAIL'}")

if __name__ == "__main__":
    main()
