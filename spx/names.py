"""Turn an object name into a field center at CENTER_DATE.

Sesame gives a position for the name, but from whatever epoch its source catalog used, so
fast-moving objects can be far from where they are now. We find the same object in Gaia DR3
(epoch 2016.0), or in CatWISE2020 (epoch 2015.4) if Gaia lacks it, by moving every nearby
catalog source back to J2000 and keeping the closest. Its proper motion then moves it to
CENTER_DATE. Names that match neither catalog (e.g. galaxies) keep Sesame's position.
"""
import warnings
from dataclasses import dataclass

import astropy.units as u
import numpy as np
from astropy.coordinates import Distance, SkyCoord
from astropy.time import Time
from astroquery.gaia import Gaia
from erfa import ErfaWarning

from spx.archive import tap_query
from spx.field import CENTER_DATE

SEARCH_RADIUS_DEG = 5 / 60
MATCH_TOLERANCE_ARCSEC = 5.0
J2000 = Time("J2000.0")


@dataclass
class CatalogSource:
    catalog: str
    source_id: str
    ra: float  # deg, at ref_epoch
    dec: float
    pmra: float  # mas/yr, includes cos(dec)
    pmdec: float  # mas/yr
    parallax: float  # mas, nan if unknown
    ref_epoch: Time

    def position_at(self, when):
        """Position at a Time, from proper motion. Ignores the yearly parallax wobble."""
        distance = Distance(parallax=self.parallax * u.mas) if self.parallax > 0 else 1 * u.Mpc
        coord = SkyCoord(ra=self.ra * u.deg, dec=self.dec * u.deg, distance=distance,
                         pm_ra_cosdec=self.pmra * u.mas / u.yr, pm_dec=self.pmdec * u.mas / u.yr,
                         obstime=self.ref_epoch)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ErfaWarning)
            moved = coord.apply_space_motion(new_obstime=when)
        return SkyCoord(ra=moved.ra, dec=moved.dec)


# Published astrometry better than the catalog's, for objects whose motion we measure. Keyed by
# the catalog source that identifies the object; the field center still comes from that catalog
# match, the motion model (position, proper motion, parallax) from here.
PUBLISHED_ASTROMETRY = {
    # WISE 0855: CatWISE2020's motion (-7950 +/- 190, +812 +/- 265 mas/yr, no parallax) puts it 2-3"
    # off by 2026. Kirkpatrick et al. 2021, ApJS 253, 7, Table 5 (19 Spitzer epochs, Gaia DR2 frame).
    "J085508.34-071439.2": CatalogSource("Kirkpatrick et al. 2021 (Spitzer)", "WISE J085510.83-071442.5",
                                         133.780984, -7.243932, -8123.7, 673.2, 439.0,
                                         Time(57633.39, format="mjd")),
}


@dataclass
class NameMatch:
    name: str
    center: SkyCoord  # where to center the field
    source: CatalogSource | None  # None when no catalog match: center is Sesame's position
    match_arcsec: float  # catalog source at J2000 vs Sesame; nan without a match


def resolve_name(name):
    """Field center for an object name, at CENTER_DATE."""
    sesame = SkyCoord.from_name(name)
    for fetch in (_gaia_sources, _catwise_sources):
        source, separation = _closest_at_j2000(sesame, fetch(sesame))
        if source is not None and separation <= MATCH_TOLERANCE_ARCSEC:
            motion_model = PUBLISHED_ASTROMETRY.get(source.source_id, source)
            return NameMatch(name, source.position_at(Time(CENTER_DATE)), motion_model, separation)
    return NameMatch(name, sesame, None, np.nan)


def _closest_at_j2000(sesame, sources):
    best, best_separation = None, np.inf
    for source in sources:
        separation = source.position_at(J2000).separation(sesame).arcsec
        if separation < best_separation:
            best, best_separation = source, float(separation)
    return best, best_separation


def _gaia_sources(around):
    query = f"""SELECT source_id, ra, dec, pmra, pmdec, parallax FROM gaiadr3.gaia_source
        WHERE pmra IS NOT NULL AND 1 = CONTAINS(POINT(ra, dec),
        CIRCLE({around.ra.deg}, {around.dec.deg}, {SEARCH_RADIUS_DEG}))"""
    table = Gaia.launch_job(query).get_results()
    return [CatalogSource("Gaia DR3", str(r["source_id"]), float(r["ra"]), float(r["dec"]),
                          float(r["pmra"]), float(r["pmdec"]), float(r["parallax"]),
                          Time(2016.0, format="jyear"))
            for r in table]


def _catwise_sources(around):
    query = f"""SELECT source_name, ra_pm, dec_pm, pmra, pmdec FROM catwise_2020
        WHERE CONTAINS(POINT('ICRS', ra, dec),
        CIRCLE('ICRS', {around.ra.deg}, {around.dec.deg}, {SEARCH_RADIUS_DEG})) = 1"""
    table = tap_query(query)
    # CatWISE proper motions are in arcsec/yr; positions ra_pm/dec_pm are at MJD 57170 (2015.4)
    return [CatalogSource("CatWISE2020", str(r["source_name"]), float(r["ra_pm"]), float(r["dec_pm"]),
                          float(r["pmra"]) * 1000, float(r["pmdec"]) * 1000, np.nan,
                          Time(57170, format="mjd"))
            for r in table]
