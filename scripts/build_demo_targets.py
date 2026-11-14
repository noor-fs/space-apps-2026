"""Build the five challenge targets into data/ as static files, one after another.

The tool works for any position; these five are the validation cases, pre-built so the site
works without any archive query. Each target runs in its own process (frees memory between
targets). Extra arguments are passed on, e.g. --offline to rebuild from the cache only.

    python scripts/build_demo_targets.py
    python scripts/build_demo_targets.py --offline
"""
import subprocess
import sys
from pathlib import Path

BUILD = Path(__file__).with_name("build_target.py")

# target_key, name Sesame knows, label shown on the site
TARGETS = [
    ("epsilon_indi_b", "Epsilon Indi B", "Epsilon Indi B"),
    ("barnards_star", "Barnard's Star", "Barnard's Star"),
    ("rw_aurigae", "RW Aurigae", "RW Aurigae"),
    ("wise_0855", "WISEA J085510.74-071442.5", "WISE 0855"),  # Sesame doesn't know "WISE 0855"
    ("r_draconis", "R Draconis", "R Draconis"),  # last: ~2,600 frames
]

failed = []
for key, name, label in TARGETS:
    result = subprocess.run([sys.executable, str(BUILD), key, "--name", name, "--label", label, *sys.argv[1:]])
    if result.returncode != 0:
        failed.append(key)
print("\nAll built." if not failed else f"\nFailed: {', '.join(failed)}")
sys.exit(1 if failed else 0)
