"""Single place for targets, field centers and constants. Edit WISE 0855 here and re-run."""
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AMNA = os.path.dirname(os.path.abspath(__file__))   # this folder, whatever it is called
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(AMNA, "cache")
LAYERS = os.path.join(AMNA, "layers")
# Practice runs (test_dummy.py): CATALOGS_SANDBOX=<dir> redirects every output to <dir>/data and <dir>/layers.
if os.environ.get("CATALOGS_SANDBOX"):
    DATA = os.path.join(os.environ["CATALOGS_SANDBOX"], "data")
    LAYERS = os.path.join(os.environ["CATALOGS_SANDBOX"], "layers")

PIXEL_SCALE_DEG = 6.15 / 3600.0
FIELD_SIZES = (51, 101, 201)
QUERY_RADIUS_DEG = 0.3
GAIA_MAG_LIMIT = 19
CENTER_DATE = "2026-01-01"

# key: (name, center_ra, center_dec, gaia_source_id or None)
TARGETS = {
    "epsilon_indi_b": ("Epsilon Indi B", 331.096653, -56.800663, 6412596012146801152),
    "barnards_star":  ("Barnard's Star", 269.446268, 4.768204, 4472832130942575872),
    "r_draconis":     ("R Draconis", 248.167233, 66.755024, 1648328016354496384),
    "rw_aurigae":     ("RW Aurigae", 76.956090, 30.401128, 156430817820015232),
    "wise_0855":      ("WISE 0855", 133.759765, -7.242186, None),
}

# Targets that are not in Gaia: the SIMBAD main_id of the target, used for the centering check.
SIMBAD_TARGET = {"wise_0855": "WISEA J085510.74-071442.5"}

LAYER_ORDER = ["gaia", "simbad", "vsx", "asteroids"]
ALLOWED_LAYERS = set(LAYER_ORDER)
ALLOWED_TYPES = ["star", "brown_dwarf", "variable_star", "galaxy", "asteroid", "young_star", "unknown"]
VERDICTS = ["moves_as_expected", "moves_unexpected", "no_motion_detected",
            "brightness_changes", "saturated", "too_faint"]

SERVICES = {
    "Gaia TAP": "https://gea.esac.esa.int/tap-server/tap/sync",
    "SIMBAD TAP": "https://simbad.cds.unistra.fr/simbad/sim-tap/sync",
    "SIMBAD TAP (mirror)": "https://simbad.u-strasbg.fr/simbad/sim-tap/sync",
    "VizieR TAP": "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync",
    "JPL sb_ident": "https://ssd-api.jpl.nasa.gov/sb_ident.api",
}

def center(key):
    n, ra, dec, sid = TARGETS[key]
    return ra, dec
