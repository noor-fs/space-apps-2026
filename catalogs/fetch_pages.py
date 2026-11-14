"""Fetch the web pages whose wording/facts are quoted in credits.json and explanations_src.yaml into catalogs/cache/pages/.
build_credits.py refuses to run unless each acknowledgement string is found verbatim in these cached pages."""
import html, os, re, time
import requests
from config import CACHE

OUT = os.path.join(CACHE, "pages"); os.makedirs(OUT, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
PAGES = {
 "spherex": "https://irsa.ipac.caltech.edu/Missions/spherex.html",
 "spherex_qr": "https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_qr.html",
 "spherex_dr1": "https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_dr1.html",
 "doi_irsa652": "https://www.ipac.caltech.edu/doi/irsa/10.26131/IRSA652",
 "doi_irsa662": "https://www.ipac.caltech.edu/doi/irsa/10.26131/IRSA662",
 "doi_irsa678": "https://www.ipac.caltech.edu/doi/irsa/10.26131/IRSA678",
 "irsa_ack": "https://irsa.ipac.caltech.edu/ack.html",
 "gaia_ack": "https://gea.esac.esa.int/archive/documentation/GDR3/Miscellaneous/sec_credit_and_citation_instructions/",
 "simbad_home_h": "https://simbad.harvard.edu/simbad/",          # CDS Strasbourg hosts were down on 2026-11-14
 "spex_home": "https://cass.ucsd.edu/~ajb/browndwarfs/spexprism",
 "splat_readme": "https://raw.githubusercontent.com/aburgasser/splat/main/README.md",
 "calspec": "https://www.stsci.edu/hst/instrumentation/reference-data-for-calibration-and-tools/astronomical-catalogs/calspec",
 "jpl_spherex": "https://www.jpl.nasa.gov/missions/spherex/",
 "nasa_stars": "https://science.nasa.gov/universe/stars/",
 "nasa_galaxies": "https://science.nasa.gov/universe/galaxies/",
 "nasa_asteroids": "https://science.nasa.gov/solar-system/asteroids/",
 "nasa_spherex_bd": "https://www.nasa.gov/missions/spherex/nasas-spherex-telescope-sees-menagerie-of-brown-dwarfs/",
 "nasa_hubble_ttauri": "https://www.nasa.gov/image-article/hubble-observes-ghostly-cloud-alive-with-star-formation/",
 "aavso_varstars": "https://archive.aavso.org/variable-stars",
 "vsx_types": "https://www.aavso.org/vsx/index.php?view=about.vartypes",
 "vsx_rdra": "https://www.aavso.org/vsx/index.php?view=detail.top&oid=13673",
 "vsx_rwaur": "https://www.aavso.org/vsx/index.php?view=detail.top&oid=3777",
 "catwise_overview": "https://irsa.ipac.caltech.edu/data/WISE/CatWISE/overview.html",
 "wise_ack": "https://irsa.ipac.caltech.edu/data/WISE/docs/release/All-Sky/expsup/sec1_6b.html",
}
def text(raw):
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", raw)
    s = html.unescape(re.sub(r"<[^>]+>", "\n", s))
    return re.sub(r"[ \t\r\f\v​\xa0]+", " ", re.sub(r"\n\s*\n+", "\n", s))

for k, u in PAGES.items():
    r = requests.get(u, headers=H, timeout=60)
    open(os.path.join(OUT, k + ".txt"), "w", encoding="utf-8").write(r.text if k == "splat_readme" else text(r.text))
    print(r.status_code, k, u); time.sleep(1)
# arXiv abstract pages (cited peer-reviewed papers)
for k, u in {"arxiv_luhman2014": "https://arxiv.org/abs/1404.6501", "arxiv_ribas2018": "https://arxiv.org/abs/1811.05955",
             "arxiv_scholz2003": "https://arxiv.org/abs/astro-ph/0212487", "arxiv_sterzik2005": "https://arxiv.org/abs/astro-ph/0503297",
             "arxiv_bozhinova2016": "https://arxiv.org/abs/1609.05667", "arxiv_lamzin2017": "https://arxiv.org/abs/1707.09671"}.items():
    r = requests.get(u, headers=H, timeout=60)
    open(os.path.join(OUT, k + ".txt"), "w", encoding="utf-8").write(text(r.text))
    print(r.status_code, k, u); time.sleep(3)
# PDFs
import pypdf, io
for k, u in {"aavso_data_usage": "https://mintaka.aavso.org/sites/default/files/2025-10/Data_Usage_25-10-01.pdf",
             "spherex_expsupp": "https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp.pdf"}.items():
    r = requests.get(u, headers=H, timeout=180)
    open(os.path.join(OUT, k + ".pdf"), "wb").write(r.content)
    t = "\n".join((p.extract_text() or "") for p in pypdf.PdfReader(io.BytesIO(r.content)).pages)
    open(os.path.join(OUT, k + ".txt"), "w", encoding="utf-8").write(t)
    print(r.status_code, k, u)
