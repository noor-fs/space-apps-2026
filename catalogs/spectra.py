"""Step 6: reference spectra -> data/spectra/*.csv   (columns wavelength_um,flux_norm,source)

Method (same for every file):
 * Read the library spectrum at native resolution; convert F_lambda -> F_nu (F_nu ~ F_lambda * lambda^2).
 * Output grid: 0.75, 0.76, ... 5.00 um in steps of 0.01 (contains 2.2 exactly). Each grid value is the MEAN of all native
   samples within +/-0.01 um of the grid wavelength (a 0.02-um boxcar; native pixels are 0.004-0.006 um, so this only
   reduces pixel noise and puts every spectrum on one grid).
 * A grid wavelength is written only if (a) there is >=1 native sample in its window, (b) native samples exist on both
   sides of it, closer together than 0.05 um (no interpolation across gaps), (c) the binned flux is > 0.
   Nothing beyond the source's real coverage is written, nothing is extrapolated.
 * flux_norm = binned F_nu / binned F_nu at 2.20 um, so the 2.2 um row is exactly 1.
"""
import csv, gzip, io, os, sys, warnings
import numpy as np
import requests
warnings.filterwarnings("ignore")
from astropy.io import fits
from config import *

SRC = os.path.join(CACHE, "spectra_src")
OUT = os.path.join(DATA, "spectra")
GRID = np.round(np.arange(75, 501) / 100.0, 2)        # 0.75 .. 5.00
HALF = 0.01
MAXGAP = 0.05
SPLAT_RAW = "https://raw.githubusercontent.com/aburgasser/splat/main/src/splat/resources/Spectra/Public/SPEX-PRISM/"
CALSPEC = "https://archive.stsci.edu/hlsps/reference-atlases/cdbs/current_calspec/"
SWIRE = "http://www.iasf-milano.inaf.it/~polletta/templates/data/swire_library.tar.gz"

def fetch(url, fn):
    os.makedirs(SRC, exist_ok=True)
    p = os.path.join(SRC, fn)
    if not os.path.exists(p):
        r = requests.get(url, timeout=120); r.raise_for_status(); open(p, "wb").write(r.content)
    return p

def load_spex(fn):
    a = fits.open(fetch(SPLAT_RAW + fn + ".gz", fn + ".gz"))[0].data.astype(float)
    w, f, e = a[0], a[1], a[2]            # um, erg/s/cm2/A, same
    return w, f * w**2, e * w**2

def load_calspec(fn, wmax_obs_um):
    h = fits.open(fetch(CALSPEC + fn, fn))[1].data
    w = h["WAVELENGTH"].astype(float) / 1e4
    f = h["FLUX"].astype(float) * w**2
    e = np.hypot(h["STATERROR"].astype(float), h["SYSERROR"].astype(float)) * w**2
    m = w <= wmax_obs_um                  # beyond this the file is a MODEL, not observations (see FITS HISTORY)
    return w[m], f[m], e[m]

def load_swire(member):
    import tarfile
    t = tarfile.open(fetch(SWIRE, "swire_library.tar.gz"))
    a = np.loadtxt(io.StringIO(t.extractfile(member).read().decode()))
    w = a[:, 0] / 1e4
    return w, a[:, 1] * w**2, np.full_like(w, np.nan)   # template: no errors

def rebin(w, f, e):
    ok = np.isfinite(w) & np.isfinite(f)
    w, f, e = w[ok], f[ok], e[ok]
    o = np.argsort(w); w, f, e = w[o], f[o], e[o]
    rows, snr = [], {}
    for g in GRID:
        sel = (w >= g - HALF - 1e-9) & (w <= g + HALF + 1e-9)
        if not sel.any():
            continue
        below = w[w <= g]; above = w[w >= g]
        if len(below) == 0 or len(above) == 0:
            continue
        if above.min() - below.max() > MAXGAP + 1e-9:
            continue
        v = float(np.mean(f[sel]))
        if not v > 0:
            continue
        rows.append((g, v))
        if np.isfinite(e[sel]).all():
            snr[g] = v / (np.sqrt(np.sum(e[sel] ** 2)) / sel.sum())
    return rows, snr

def write(name, source, w, f, e):
    rows, snr = rebin(w, f, e)
    d = dict(rows)
    if 2.2 not in d:
        raise SystemExit(f"{name}: no valid value at 2.2 um")
    norm = d[2.2]
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name + ".csv"), "w", encoding="utf-8", newline="") as fh:
        wr = csv.writer(fh, lineterminator="\n")
        wr.writerow(["wavelength_um", "flux_norm", "source"])
        for g, v in rows:
            x = 1.0 if g == 2.2 else float(f"{v / norm:.6g}")
            wr.writerow([f"{g:.2f}", repr(x), source])
    print(f"{name}.csv: {len(rows)} rows, {rows[0][0]:.2f}-{rows[-1][0]:.2f} um, S/N of 2.2-um bin = "
          f"{snr.get(2.2, float('nan')):.0f}; native coverage {np.nanmin(w):.3f}-{np.nanmax(w):.3f} um")

SPECS = {
    # name: (source text, loader)
    "star_g": ("CALSPEC (STScI): P330E (G2V) observed STIS+WFC3+NICMOS F_nu",
               lambda: load_calspec("p330e_stiswfcnic_008.fits", 2.452)),
    "star_m": ("SpeX Prism Library: GJ 4074 (M4) F_nu", lambda: load_spex("12125_11860.fits")),
    "brown_dwarf_l": ("SpeX Prism Library: G 203-50B (L5) F_nu", lambda: load_spex("11447_11308.fits")),
    "brown_dwarf_t": ("SpeX Prism Library: 2MASS J0415-0935 (T8) F_nu", lambda: load_spex("10126_10349.fits")),
    "galaxy": ("SWIRE template library (Polletta et al. 2007): Sb spiral template rest frame F_nu",
               lambda: load_swire("Sb_template_norm.sed")),
}

if __name__ == "__main__":
    for k, (src, ld) in SPECS.items():
        w, f, e = ld()
        write(k, src, w, f, e)
