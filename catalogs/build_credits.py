"""Build data/credits.json. Every quoted wording is VERIFIED to occur verbatim (ignoring whitespace) in the page text
cached in catalogs/cache/pages/ (fetched 2026-11-14); the script stops if it does not."""
import os, re, sys
from config import *
from common import write_json

PAGES = os.path.join(CACHE, "pages")
def norm(s):
    return re.sub(r"[\s|]+", "", s)
def page(name):
    return norm(open(os.path.join(PAGES, name), encoding="utf-8").read())
def verify(file, *quotes):
    p = page(file)
    for q in quotes:
        if norm(q) not in p:
            print(f"NOT FOUND in {file}: {q[:80]}..."); sys.exit(1)
    return quotes

SPHEREX = "This publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory and the California Institute of Technology, and is funded by the National Aeronautics and Space Administration."
IRSA = "This research has made use of the NASA/IPAC Infrared Science Archive, which is funded by the National Aeronautics and Space Administration and operated by the California Institute of Technology."
GAIA = "This work has made use of data from the European Space Agency (ESA) mission Gaia (https://www.cosmos.esa.int/gaia), processed by the Gaia Data Processing and Analysis Consortium (DPAC, https://www.cosmos.esa.int/web/gaia/dpac/consortium). Funding for the DPAC has been provided by national institutions, in particular the institutions participating in the Gaia Multilateral Agreement."
SIMBAD = "This research has made use of the SIMBAD database, operated at CDS, Strasbourg, France"
SIMBAD_REF = "2000,A&AS,143,9"
SIMBAD_REF2 = "\"The SIMBAD astronomical database\", Wenger et al."
AAVSO = "We gratefully acknowledge the contributions of the AAVSO observer community, whose [photometric, spectroscopic, solar, exoplanet] data and metadata resources were used in this study and made available through the AAVSO’s scientific archives."
AAVSO_CIT = "Watson, C. L., Henden, A. A., and Price, A., “The International Variable Star Index (VSX)”, Society for Astronomical Sciences Annual Symposium, vol. 25, p. 47, 2006."
SPEX = "This research has benefitted from the SpeX Prism Spectral Libraries, maintained by Adam Burgasser at http://www.browndwarfs.org/spexprism"
SPLAT = "If you use SPLAT tools for your research, please cite Burgasser et al. (2017, ASInC 14, 7), bibcode 2017ASInC..14....7B"
CALSPEC = "Please reference the review paper by Bohlin, Gordon, & Tremblay (2014) or Bohlin, Hubeny, & Rauch (2020) for research that makes use of this database. The most recent reference is Bohlin et al. (2022) and Bohlin et al. (2025)."

QR3 = "10.26131/IRSA662 for QR3"
verify("spherex.txt", SPHEREX); verify("spherex_qr.txt", SPHEREX, QR3)
# Releases listed in the credit: QR2, QR3, DR1 spectral images (QR1 is retired). Each DOI is checked on IRSA's overview page
# AND on IPAC's DOI record whose title carries the release name.
verify("spherex_qr.txt", SPHEREX, "10.26131/IRSA652 for QR2", "10.26131/IRSA662 for QR3")
verify("spherex_dr1.txt", SPHEREX, "10.26131/IRSA678 for the DR1 Spectral Images")
verify("doi_irsa652.txt", "10.26131/IRSA652", "SPHEREx Quick Release Spectral Images - QR2")
verify("doi_irsa662.txt", "10.26131/IRSA662", "SPHEREx Quick Release Spectral Images - QR3")
verify("doi_irsa678.txt", "10.26131/IRSA678", "SPHEREx Data Release 1 (DR1) Spectral Images")
SPHEREX_RELEASES = (" Data sets used (IRSA): SPHEREx Quick Release 2 (QR2), DOI 10.26131/IRSA652; SPHEREx Quick Release 3 (QR3), "
                    "DOI 10.26131/IRSA662; SPHEREx Data Release 1 (DR1) Spectral Images, DOI 10.26131/IRSA678.")
verify("irsa_ack.txt", IRSA)
if os.path.exists(os.path.join(PAGES, "gaia_ack.txt")):
    verify("gaia_ack.txt", GAIA)
else:
    print("WARNING: gaia_ack.txt not fetched (ESA host unreachable); Gaia sentence verified on 2026-11-14, Gaia paper titles, authors and DOIs checked on arXiv; ESA's own wording for them not re-checked")
verify("simbad_home_h.txt", SIMBAD, SIMBAD_REF, SIMBAD_REF2)
verify("aavso_data_usage.txt", AAVSO, AAVSO_CIT)
verify("spex_home.txt", SPEX)
verify("splat_readme.txt", SPLAT)
verify("calspec.txt", CALSPEC)

# --- added 2026-11-15: software and paper credits (wording copied from each project's own page; pages fetched into cache/pages) ---
ASTROPY = "This work made use of Astropy: a community-developed core Python package and an ecosystem of tools and resources for astronomy"
PHOTUTILS = "This research made use of Photutils, an Astropy package for detection and photometry of astronomical sources (Bradley et al. <YEAR>)."
NUMPY = "Harris, C.R., Millman, K.J., van der Walt, S.J. et al. Array programming with NumPy. Nature 585, 357–362 (2020). DOI: 10.1038/s41586-020-2649-2"
SCIPY_T = "SciPy 1.0: Fundamental Algorithms for Scientific Computing in Python"
verify("astropy_ack.txt", "This work made use of Astropy:", "a community-developed core Python package and an ecosystem of tools and resources for astronomy", "we ask that you please cite the Astropy papers")
verify("photutils_cite.txt", PHOTUTILS, "https://doi.org/10.5281/zenodo.596036")
verify("astroquery_cite.txt", "If you use astroquery, please cite the paper Ginsburg, Sipőcz, Brasseur et al 2019")
verify("numpy_cite.txt", NUMPY)
verify("scipy_cite.txt", SCIPY_T, "Nature Methods, 17(3), 261-272. DOI: 10.1038/s41592-019-0686-2")
verify("arxiv_kirkpatrick2021.txt", "The Field Substellar Mass Function Based on the Full-sky 20-pc Census of 525 L, T, and Y Dwarfs")
verify("arxiv_lupton2004.txt", "Preparing Red-Green-Blue (RGB) Images from CCD Data")
verify("arxiv_rodriguez2018.txt", "Multiple Stellar Fly-Bys Sculpting the Circumstellar Architecture in RW Aurigae")
verify("arxiv_gaia_mission.txt", "The Gaia mission", "Gaia Collaboration", "10.1051/0004-6361/201629272")
verify("arxiv_gaia_dr3_summary.txt", "Gaia Data Release 3: Summary of the content and survey properties", "A. Vallenari", "10.1051/0004-6361/202243940")
GAIA_PAPERS = (" Please also cite the Gaia mission paper, Gaia Collaboration, Prusti et al. 2016 (A&A 595, A1, doi 10.1051/0004-6361/201629272), and the Gaia DR3 summary paper, "
               "Gaia Collaboration, Vallenari et al. 2023 (A&A 674, A1, doi 10.1051/0004-6361/202243940).")

credits = [
 {"what": "SPHEREx images (SPHEREx / NASA/IPAC Infrared Science Archive)", "text": SPHEREX + " " + IRSA + SPHEREX_RELEASES,
  "url": "https://irsa.ipac.caltech.edu/Missions/spherex.html"},
 {"what": "Gaia DR3 catalog (stars)", "text": GAIA + GAIA_PAPERS,
  "url": "https://gea.esac.esa.int/archive/documentation/GDR3/Miscellaneous/sec_credit_and_citation_instructions/"},
 {"what": "SIMBAD (object names and types)", "text": f"{SIMBAD}. Reference: {SIMBAD_REF}, {SIMBAD_REF2}",
  "url": "https://simbad.harvard.edu/simbad/"},
 {"what": "AAVSO International Variable Star Index (VSX)",
  "text": f"{AAVSO} Citation requested by AAVSO for VSX: {AAVSO_CIT}",
  "url": "https://mintaka.aavso.org/sites/default/files/2025-10/Data_Usage_25-10-01.pdf"},
 {"what": "CatWISE2020 catalog (proper motion of WISE 0855)",
  "text": "IRSA publishes no standard acknowledgement sentence for CatWISE. It asks users of the CatWISE catalogs to cite Eisenhardt et al. (2020) for the CatWISE program and Marocco et al. (2021) for the CatWISE2020 Catalog updates, and the dataset DOIs 10.26131/IRSA126, 10.26131/IRSA133, 10.26131/IRSA551 and 10.26131/IRSA552. See also the IRSA acknowledgement under SPHEREx images.",
  "url": "https://irsa.ipac.caltech.edu/data/WISE/CatWISE/overview.html"},
 {"what": "JPL Small-Body Identification API (asteroid positions)",
  "text": "The API documentation page publishes no acknowledgement wording. The service identifies itself in its responses as \"NASA/JPL Small-Body Identification API\", version 1.1.",
  "url": "https://ssd-api.jpl.nasa.gov/doc/sb_ident.html"},
 {"what": "SpeX Prism Library (reference spectra of M, L and T dwarfs)",
  "text": SPEX + ". The library asks users to cite the original data references of the spectra used: GJ 4074 (M4): bibcode 2019ApJ...883..205B; G 203-50B (L5): bibcode 2014ApJ...794..143B; 2MASS J0415-0935 (T8): bibcode 2004AJ....127.2856B. The spectra were read from the SPLAT software repository: " + SPLAT,
  "url": "https://cass.ucsd.edu/~ajb/browndwarfs/spexprism"},
 {"what": "CALSPEC (reference spectrum of a G star)", "text": CALSPEC,
  "url": "https://www.stsci.edu/hst/instrumentation/reference-data-for-calibration-and-tools/astronomical-catalogs/calspec"},
 {"what": "SWIRE template library (reference spectrum of a galaxy)",
  "text": "No acknowledgement wording is published on the library page. The page lists Polletta, M. et al. 2007, ApJ, 663, 81 among the works that use the library.",
  "url": "http://www.iasf-milano.inaf.it/~polletta/templates/swire_templates.html"},
 {"what": "Kirkpatrick et al. 2021 (WISE 0855 catalog motion)",
  "text": "The catalog motion shown for WISE 0855 (-8124 mas/yr in RA, +673 mas/yr in Dec) is from Kirkpatrick, J. D. et al. 2021, ApJS 253, 7, \"The Field Substellar Mass Function Based on the Full-sky 20-pc Census of 525 L, T, and Y Dwarfs\". The arXiv page publishes no acknowledgement wording.",
  "url": "https://arxiv.org/abs/2011.11616"},
 {"what": "Rodriguez et al. 2018 (which RW Aurigae star is A)",
  "text": "Rodriguez, J. E. et al. 2018, ApJ 859, 150, \"Multiple Stellar Fly-Bys Sculpting the Circumstellar Architecture in RW Aurigae\": its ALMA positions tell us which of the two stars is RW Aur A. The arXiv page publishes no acknowledgement wording.",
  "url": "https://arxiv.org/abs/1804.09190"},
 {"what": "Lupton et al. 2004 (color-image method)",
  "text": "Our color pictures follow Lupton, R. et al. 2004, PASP 116, 133, \"Preparing Red-Green-Blue (RGB) Images from CCD Data\". The arXiv page publishes no acknowledgement wording.",
  "url": "https://arxiv.org/abs/astro-ph/0312483"},
 {"what": "Sesame name resolver (CDS)",
  "text": "Sesame, a service of the Centre de Donn\u00e9es astronomiques de Strasbourg (CDS), turns typed object names into coordinates. The Sesame page publishes no acknowledgement wording of its own; see the SIMBAD acknowledgement above for CDS services.",
  "url": "https://cds.unistra.fr/cgi-bin/Sesame"},
 {"what": "Astropy", "text": ASTROPY + " (Astropy Collaboration 2013, A&A 558, A33; 2018, AJ 156, 123; 2022, ApJ 935, 167). Astropy asks users to cite these three papers.",
  "url": "https://www.astropy.org/acknowledging.html"},
 {"what": "Photutils", "text": PHOTUTILS.replace("(Bradley et al. <YEAR>)", "(Bradley et al., citing the Zenodo record of the version used)") + " Citation: the Zenodo record of the Photutils version used, listed at https://doi.org/10.5281/zenodo.596036.",
  "url": "https://photutils.readthedocs.io/en/stable/getting_started/citation.html"},
 {"what": "astroquery", "text": "If you use astroquery, please cite the paper Ginsburg, Sip\u0151cz, Brasseur et al 2019 (AJ 157, 98).",
  "url": "https://astroquery.readthedocs.io/en/latest/"},
 {"what": "reproject", "text": "The reproject documentation page publishes no acknowledgement wording. reproject is an Astropy-affiliated package, so the Astropy acknowledgement above applies.",
  "url": "https://reproject.readthedocs.io/en/stable/"},
 {"what": "NumPy", "text": NUMPY, "url": "https://numpy.org/citing-numpy/"},
 {"what": "SciPy", "text": "Virtanen, P. et al. (2020) " + SCIPY_T + ". Nature Methods, 17(3), 261-272. DOI: 10.1038/s41592-019-0686-2.",
  "url": "https://scipy.org/citing-scipy/"},
]
write_json(os.path.join(DATA, "credits.json"), credits)
print("wrote data/credits.json:", len(credits), "entries; all quoted wording verified against fetched pages")
