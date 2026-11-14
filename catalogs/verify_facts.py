"""Check that the key phrase behind each factual sentence in explanations_src.yaml occurs in the cached source page
(catalogs/cache/pages/, produced by fetch_pages.py). Whitespace/quote-insensitive. Run: python catalogs/verify_facts.py"""
import os, re, sys
from config import CACHE
P = os.path.join(CACHE, "pages")
def norm(s): return re.sub(r"[\s|]+", "", s.replace("’", "'").replace("“", '"').replace("”", '"')).lower()
CHECKS = [
 ("jpl_spherex", "Every six months, SPHEREx will survey the entire sky"), ("jpl_spherex", "102 different color bands"),
 ("spherex_expsupp", "Pixel scale 6.15"), ("spherex_expsupp", "saturated pixels displayed in white"),
 ("spherex_expsupp", "wavelength varies continuously with position"),
 ("nasa_spherex_bd", "aren't hefty enough to sustain hydrogen fusion in their cores"), ("nasa_spherex_bd", "heated entirely from within"),
 ("nasa_spherex_bd", "finding thousands of brown dwarfs"), ("nasa_spherex_bd", "an infrared space telescope"),
 ("nasa_spherex_bd", "brightness in 102 different colors, from the deepest red"),
 ("nasa_stars", "Nuclear fusion releases energy, which heats the star"), ("nasa_stars", "Our Sun, a main sequence star"),
 ("nasa_stars", "most of the protostar's energy comes from heat released by its initial collapse"),
 ("nasa_galaxies", "Galaxies consist of stars, planets, and vast clouds of gas and dust, all bound together by gravity"),
 ("nasa_galaxies", "mostly spirals and ellipticals"),
 ("nasa_asteroids", "rocky, airless remnants left over from the early formation of our solar system about 4.6 billion years ago"),
 ("nasa_asteroids", "between Mars and Jupiter"),
 ("nasa_hubble_ttauri", "typically less than 10 million years old and vary in brightness both randomly and periodically"),
 ("aavso_varstars", "A star is a variable star if we can measure its brightness changing over time"),
 ("vsx_types", "long-period variable giants"), ("vsx_types", "periods lie in the range between 80 and 1000 days"),
 ("vsx_rdra", "Variability type M"), ("vsx_rdra", "Period 246.12 d"), ("vsx_rdra", "Mag. range 6.7 - 13.2"),
 ("catwise_overview", "please cite the journal articles"),
 ("arxiv_luhman2014", "coldest known brown dwarf"), ("arxiv_luhman2014", "225-260 K"), ("arxiv_luhman2014", "8.1+/-0.1"),
 ("arxiv_luhman2014", "third highest proper motion"), ("arxiv_luhman2014", "2.20+0.24/-0.20 pc"),
 ("arxiv_ribas2018", "closest single star to the Sun"), ("arxiv_ribas2018", "largest apparent motion of any known stellar object"),
 ("arxiv_ribas2018", "At a distance of 1.8 parsecs"), ("arxiv_ribas2018", "is a red dwarf"),
 ("arxiv_scholz2003", "common proper motion companion"), ("arxiv_scholz2003", "~4.7 arcsec/yr"),
 ("arxiv_sterzik2005", "spatially resolve both components"), ("arxiv_sterzik2005", "brown dwarf binary"),
 ("arxiv_bozhinova2016", "young binary star"), ("arxiv_bozhinova2016", "deep dimming in 2010-11 in component A"),
 ("arxiv_bozhinova2016", "from summer 2014 to summer 2016"), ("arxiv_bozhinova2016", "A dusty wind eclipsing RW Aur"),
 ("arxiv_lamzin2017", "eclipses of the star by dust screen"),
]
bad = 0
for page, phrase in CHECKS:
    ok = norm(phrase) in norm(open(os.path.join(P, page + ".txt"), encoding="utf-8").read())
    print(("PASS " if ok else "FAIL ") + f"{page}: {phrase}")
    bad += not ok
print("RESULT:", "all phrases found" if not bad else f"{bad} phrase(s) NOT found")
sys.exit(1 if bad else 0)
