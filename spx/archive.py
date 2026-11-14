"""Queries to the IRSA archive (SPHEREx images, CatWISE2020)."""
import io
import time

import requests
from astropy.table import Table

IRSA = "https://irsa.ipac.caltech.edu/"


def tap_query(adql, retries=5, timeout=(15, 180)):
    """Run a synchronous ADQL query on IRSA TAP and return an astropy Table.

    Uses requests directly so every call has a timeout (pyvo's default can hang forever),
    and retries transient 5xx errors, which IRSA returns as HTML pages.
    """
    last_error = None
    for attempt in range(retries):
        try:
            response = requests.post(IRSA + "TAP/sync", timeout=timeout,
                                     data={"LANG": "ADQL", "FORMAT": "csv", "QUERY": adql})
            if response.ok and not response.text.lstrip().startswith("<"):
                return Table.read(io.BytesIO(response.content), format="ascii.csv")
            last_error = f"HTTP {response.status_code}"
        except requests.RequestException as error:
            last_error = str(error)
        print(f"TAP attempt {attempt + 1}/{retries} failed: {last_error:.80}")
        time.sleep(5 * 2 ** attempt)
    raise ConnectionError(f"IRSA TAP unavailable after {retries} attempts: {last_error}")
