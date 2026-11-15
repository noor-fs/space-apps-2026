"""Add verdict_evidence to existing manifests from results/<key>/, without rebuilding.

Uses the same function as a build (spx.export.verdict_evidence), fed from the build's saved
verdict_fov<S>.json and measurements_fov<S>.csv. Checks that the saved verdict still matches the
manifest, so evidence from a different build can't be attached. Run from the repo root:
    python scripts/update_evidence.py epsilon_indi_b barnards_star ...
"""
import csv
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spx.export import verdict_evidence  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def update(key, size_px=51):
    path = ROOT / "data" / key / f"fov{size_px}" / "manifest.json"
    manifest = json.loads(path.read_text())
    saved = json.loads((ROOT / "results" / key / f"verdict_fov{size_px}.json").read_text())
    if saved["verdict"] != manifest["verdict"]:
        raise SystemExit(f"{key}: results verdict {saved['verdict']} != manifest {manifest['verdict']}")

    m = saved["motion"]
    motion = None if m is None else SimpleNamespace(
        constrained=m["constrained"], detection_chi2=m["detection_chi2"],
        catalog_chi2=m["catalog_chi2"], shift_px=m["shift_px"])
    b = saved["brightness"]
    brightness = None if b is None else SimpleNamespace(chi2=b["chi2"], dof=b["dof"])
    with (ROOT / "results" / key / f"measurements_fov{size_px}.csv").open() as handle:
        flags = [row["saturated"] == "True" for row in csv.DictReader(handle)
                 if not row["frame"].startswith("visitfit")]
    evidence = verdict_evidence(motion, saved["motion_source"], brightness,
                                sum(flags) / len(flags) if flags else None)

    items = [(k, v) for k, v in manifest.items() if k != "verdict_evidence"]
    at = [k for k, _ in items].index("verdict") + 1
    path.write_text(json.dumps(dict(items[:at] + [("verdict_evidence", evidence)] + items[at:]), indent=1))
    print(key, manifest["verdict"], evidence)


if __name__ == "__main__":
    for target_key in sys.argv[1:]:
        update(target_key)
