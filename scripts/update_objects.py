"""Add crowded_by and absolute_floor_px to existing objects.json files without rebuilding.

Uses the same functions as a build (spx.objects) and the cached Gaia list of each field.
Run from the repo root:
    python scripts/update_objects.py epsilon_indi_b barnards_star ...
"""
import json
import sys
from pathlib import Path

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.time import Time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spx.field import CENTER_DATE, Field  # noqa: E402
from spx.measure import gaia_positions, gaia_sources  # noqa: E402
from spx.objects import _g_mag, absolute_floor, crowding_neighbors  # noqa: E402


def update(path):
    document = json.loads(path.read_text())
    grid = json.loads((path.parent / "manifest.json").read_text())["grid"]
    field = Field(SkyCoord(grid["center_ra"], grid["center_dec"], unit="deg"), grid["size_px"])
    catalog = gaia_sources(field)
    xy = field.wcs().world_to_pixel(gaia_positions(catalog, Time(CENTER_DATE)))
    ids = np.array([str(i) for i in catalog["source_id"]])
    g_all = _g_mag(catalog)
    entries = []
    for entry in document["objects"]:
        own = ids == entry["name"].split()[-1]
        crowded = crowding_neighbors(xy, own, g_all, float(g_all[own][0]))
        fields = list(entry.items())
        at = [k for k, _ in fields].index("blended_with") + 1
        entries.append(dict(fields[:at] + [("crowded_by", [f"Gaia DR3 {i}" for i in ids[crowded]])]
                            + [(k, v) for k, v in fields[at:] if k != "crowded_by"]))
    keep = {k: v for k, v in document.items() if k not in ("objects", "absolute_floor_px", "absolute_floor_from")}
    path.write_text(json.dumps({**keep, **absolute_floor(entries), "objects": entries}, indent=1))
    crowded = sum(bool(e["crowded_by"]) for e in entries)
    print(f"{path.parent.parent.name}: floor {absolute_floor(entries)['absolute_floor_px']} px, "
          f"{crowded} of {len(entries)} stars crowded")


if __name__ == "__main__":
    for key in sys.argv[1:]:
        for path in sorted(Path("data", key).glob("fov*/objects.json")):
            update(path)
