"""Step 3: build data/simbad_otype_map.csv from SIMBAD's own otypedef table (otype, description, path)."""
import csv, io, os
from config import DATA
from common import simbad_query

BROWN = {"BD*", "BD?"}
# Under the Y*O (young stellar object) branch but NOT stars: outflows and Herbig-Haro objects.
YOUNG_EXCLUDE = {"out", "of?", "HH"}
# Under the '* >' branch but not a star (or not one star): planets, planetary nebulae, supernovae.
NOT_STAR = {"Pl", "Pl?", "PN", "PN?", "SN?", "SN*"}
# Extragalactic codes outside the 'G' branch of SIMBAD's hierarchy.
GALAXY_EXTRA_PATH_ROOTS = {"ClG", "GrG", "IG", "PaG", "PCG", "SCG", "PoG"}
GALAXY_EXTRA_CODES = {"PoG", "LeG", "LeQ"}

def classify(code, desc, path):
    root = path.split(" > ")[0] if path else ""
    parts = path.split(" > ") if path else []
    if code in BROWN:
        return "brown_dwarf"
    if "Y*O" in parts and code not in YOUNG_EXCLUDE:
        return "young_star"
    if root == "*" and code not in NOT_STAR and "Variable" in desc:
        return "variable_star"
    if root == "G" or root in GALAXY_EXTRA_PATH_ROOTS or code in GALAXY_EXTRA_CODES:
        return "galaxy"
    if root == "*" and code not in NOT_STAR and code not in YOUNG_EXCLUDE:
        return "star"
    return "unknown"

def build():
    text = simbad_query("SELECT otype, description, path FROM otypedef", "simbad_otypedef_3col")
    rows = list(csv.DictReader(io.StringIO(text)))
    seen = set()
    out = []
    for r in rows:
        code = r["otype"].strip()
        if code in seen:
            raise SystemExit(f"duplicate otype {code}")
        seen.add(code)
        out.append((code, classify(code, r["description"], r["path"] or ""), r["description"].strip()))
    out.sort(key=lambda t: (t[1], t[0]))
    path = os.path.join(DATA, "simbad_otype_map.csv")
    os.makedirs(DATA, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["otype", "our_type", "description"])
        w.writerows(out)
    from collections import Counter
    print(len(out), "codes;", dict(Counter(t[1] for t in out)))

if __name__ == "__main__":
    build()
