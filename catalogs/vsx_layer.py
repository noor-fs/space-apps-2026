"""Step 4: VSX layer -> layers/<key>/vsx.json
Primary: official AAVSO VSX API (live data, https://www.aavso.org/vsx/index.php?view=api.list ... format=json; radius in degrees).
Fallback: VizieR B/vsx/vsx (CfA Harvard mirror; CDS Strasbourg was down on 2026-11-14). The VizieR copy is OLDER than live VSX
(e.g. it still lists RW Aur as CTTS/ROT+CTTS; live VSX says CTTS/ROT+WTTS), so the API is preferred.
VSX positions are J2000 (epoch 2000.0). Proper motions are written as null, as the project format instructs."""
import io, math, os, sys, warnings, re
from collections import Counter
warnings.filterwarnings("ignore")
from astropy.io.votable import parse_single_table
from config import *
from common import *

VIZIER_VOTABLE = [
    "https://vizier.cds.unistra.fr/viz-bin/votable",
    "https://vizier.cfa.harvard.edu/viz-bin/votable",
]

def query(key):
    ra, dec = center(key)
    params = {"-source": "B/vsx/vsx", "-c": f"{ra} {dec}", "-c.r": str(QUERY_RADIUS_DEG), "-c.u": "deg",
              "-out.max": "unlimited", "-out.all": "1", "-sort": "_r"}
    last = None
    for url in VIZIER_VOTABLE:
        try:
            text = http("GET", url, f"vsx_{key}", params=params)
            if "<VOTABLE" not in text:
                raise RuntimeError("not a VOTable")
            log_service("VizieR (VSX B/vsx/vsx)", url)
            return text
        except Exception as e:
            last = f"{url}: {e}"
    raise RuntimeError(last)

def clean(v):
    if v is None or (hasattr(v, "mask") and v.mask):
        return ""
    s = str(v).strip()
    return "" if s in ("--", "nan") else s

def period_text(row):
    p = row["Period"]
    if p is None or (hasattr(p, "mask") and p.mask) or not math.isfinite(float(p)):
        return ""
    lim, unc = clean(row["l_Period"]), clean(row["u_Period"])
    s = f"{float(p):.6g}"
    return f"{lim}{s}{unc} d"

VSX_API = "https://www.aavso.org/vsx/index.php"

def build_api(key):
    import json as _j
    ra, dec = center(key)
    params = {"view": "api.list", "ra": ra, "dec": dec, "radius": QUERY_RADIUS_DEG, "format": "json"}
    text = http("GET", VSX_API, f"vsxapi_{key}", params=params)
    objs = _j.loads(text)["VSXObjects"].get("VSXObject", [])
    objs = objs if isinstance(objs, list) else [objs]
    out, seen = [], set()
    for o in objs:
        name = (o.get("Name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        vtype, per = (o.get("VariabilityType") or "").strip(), (o.get("Period") or "").strip()
        extra = ", ".join(x for x in (vtype, (f"period {per} d" if per else "")) if x)
        out.append({"name": name, "label": f"{name} ({extra})" if extra else name,
                    "type": "variable_star", "layer": "vsx",
                    "ra": round(float(o["RA2000"]), 6), "dec": round(float(o["Declination2000"]), 6), "epoch": 2000.0,
                    "pmra_mas_yr": None, "pmdec_mas_yr": None, "source": "AAVSO VSX",
                    "url": f"https://www.aavso.org/vsx/index.php?view=detail.top&oid={int(o['OID'])}"})
    out.sort(key=lambda e: e["name"])
    log_service("AAVSO VSX API", VSX_API)
    write_json(os.path.join(LAYERS, key, "vsx.json"), out)
    print(f"{key}: VSX API rows={len(objs)} written={len(out)}")

def build(key):
    try:
        return build_api(key)
    except Exception as e:
        print(f"{key}: VSX API failed ({e}); falling back to VizieR")
    text = query(key)
    tb = parse_single_table(io.BytesIO(text.encode())).to_table()
    out, seen = [], set()
    flags = Counter()
    for row in tb:
        name = clean(row["Name"])
        oid = int(row["OID"])
        ra, dec = float(row["RAJ2000"]), float(row["DEJ2000"])
        if not name or not (math.isfinite(ra) and math.isfinite(dec)):
            continue
        if name in seen:
            raise RuntimeError(f"duplicate VSX name {name}")
        seen.add(name)
        vtype, per = clean(row["Type"]), period_text(row)
        flags[(clean(row["l_Period"]), clean(row["u_Period"]))] += 1
        extra = ", ".join(x for x in ((f"{vtype}" if vtype else ""), (f"period {per}" if per else "")) if x)
        out.append({
            "name": name, "label": f"{name} ({extra})" if extra else name,
            "type": "variable_star", "layer": "vsx",
            "ra": round(ra, 6), "dec": round(dec, 6), "epoch": 2000.0,
            "pmra_mas_yr": None, "pmdec_mas_yr": None,
            "source": "AAVSO VSX",
            "url": f"https://www.aavso.org/vsx/index.php?view=detail.top&oid={oid}",
        })
    out.sort(key=lambda e: e["name"])
    path = os.path.join(LAYERS, key, "vsx.json")
    write_json(path, out)
    print(f"{key}: rows={len(tb)} written={len(out)} period-flag-combos={dict(flags)}")

if __name__ == "__main__":
    for k in (sys.argv[1:] or list(TARGETS)):
        build(k)
