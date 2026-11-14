"""HTTP helpers: timeouts, retries with backoff, polite delay, on-disk cache."""
import hashlib, json, os, time
import requests
from config import CACHE

TIMEOUT = 90
RETRIES = 3
DELAY = 1.0
HEADERS = {"User-Agent": "sky-flipbook-student-project/1.0"}
_last = [0.0]

def _cache_path(tag, payload):
    os.makedirs(CACHE, exist_ok=True)
    h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return os.path.join(CACHE, f"{tag}_{h}")

def http(method, url, tag, cache=True, **kw):
    """Return response text (cached). Raises on failure after retries."""
    key = {"m": method, "u": url, "p": kw.get("params"), "d": kw.get("data")}
    path = _cache_path(tag, key)
    if cache and os.path.exists(path):
        return open(path, encoding="utf-8").read()
    err = None
    for i in range(RETRIES):
        wait = DELAY - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.request(method, url, timeout=TIMEOUT, headers=HEADERS, **kw)
            _last[0] = time.time()
            r.raise_for_status()
            if cache:
                open(path, "w", encoding="utf-8").write(r.text)
            return r.text
        except Exception as e:  # noqa
            err = e
            _last[0] = time.time()
            time.sleep(2 ** (i + 1))
    raise RuntimeError(f"{url} failed after {RETRIES} tries: {err}")

def tap_sync(url, adql, tag, fmt="csv"):
    """Run a synchronous TAP query, return CSV text."""
    return http("POST", url, tag, data={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": fmt, "QUERY": adql})

def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False, allow_nan=False)

# ---- service log (which endpoint actually answered, and when) ----
import datetime
from config import AMNA
SERVICE_LOG = os.path.join(AMNA, "service_log.json")

def log_service(name, url, note=""):
    try:
        d = json.load(open(SERVICE_LOG))
    except Exception:
        d = {}
    d[name] = {"url": url, "date": datetime.date.today().isoformat(), "note": note}
    json.dump(d, open(SERVICE_LOG, "w"), indent=1, sort_keys=True)

# SIMBAD endpoints in order of preference. The CDS Strasbourg host answered "Page unavailable" (404)
# on 2026-11-14; the CfA Harvard mirror is an official SIMBAD mirror with the same TAP service.
SIMBAD_TAP = [
    "https://simbad.cds.unistra.fr/simbad/sim-tap/sync",
    "https://simbad.u-strasbg.fr/simbad/sim-tap/sync",
    "https://simbad.harvard.edu/simbad/sim-tap/sync",
]

def simbad_query(adql, tag):
    """Run on the first SIMBAD TAP endpoint that works; returns CSV text."""
    last = None
    for url in SIMBAD_TAP:
        try:
            # cache key is endpoint independent so re-runs reuse results
            path = _cache_path(tag, {"q": adql})
            if os.path.exists(path):
                return open(path, encoding="utf-8").read()
            r = None
            for i in range(RETRIES):
                try:
                    r = requests.post(url, data={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": adql},
                                      timeout=TIMEOUT, headers=HEADERS)
                    if r.status_code == 200 and not r.text.lstrip().startswith("<"):
                        break
                    if r.status_code == 404 or r.text.lstrip().startswith("<"):
                        raise RuntimeError(f"HTTP {r.status_code}")  # endpoint not serving TAP; no point retrying
                    r.raise_for_status()
                except RuntimeError:
                    raise
                except Exception as e:
                    time.sleep(2 ** (i + 1))
                    r = None
            if r is None or r.status_code != 200:
                raise RuntimeError("no valid response")
            open(path, "w", encoding="utf-8").write(r.text)
            log_service("SIMBAD TAP", url)
            time.sleep(DELAY)
            return r.text
        except Exception as e:
            last = f"{url}: {e}"
            continue
    raise RuntimeError(f"all SIMBAD endpoints failed; last: {last}")
