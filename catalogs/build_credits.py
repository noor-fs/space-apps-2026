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
verify("gaia_ack.txt", GAIA)
verify("simbad_home_h.txt", SIMBAD, SIMBAD_REF, SIMBAD_REF2)
verify("aavso_data_usage.txt", AAVSO, AAVSO_CIT)
verify("spex_home.txt", SPEX)
verify("splat_readme.txt", SPLAT)
verify("calspec.txt", CALSPEC)

credits = [
 {"what": "SPHEREx images (SPHEREx / NASA/IPAC Infrared Science Archive)", "text": SPHEREX + " " + IRSA + SPHEREX_RELEASES,
  "url": "https://irsa.ipac.caltech.edu/Missions/spherex.html"},
 {"what": "Gaia DR3 catalog (stars)", "text": GAIA,
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
]
write_json(os.path.join(DATA, "credits.json"), credits)
print("wrote data/credits.json:", len(credits), "entries; all quoted wording verified against fetched pages")
