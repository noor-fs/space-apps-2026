// Sky <-> pixel maths, exactly as written in the shared data format.

export const PIX_ARCSEC = 6.15;
const S_DEG = PIX_ARCSEC / 3600; // degrees per pixel
const RAD = Math.PI / 180;

/**
 * RA/Dec (degrees) -> [column, row] in a field of `size` pixels centered on ra0/dec0.
 * Whole numbers are pixel centers; row 0 is north; east is left.
 * Returns null for positions on the far side of the sky.
 */
export function skyToPx(ra, dec, ra0, dec0, size) {
  const a = ra * RAD, d = dec * RAD, a0 = ra0 * RAD, d0 = dec0 * RAD;
  const D = Math.sin(d) * Math.sin(d0) + Math.cos(d) * Math.cos(d0) * Math.cos(a - a0);
  if (D <= 0) return null;
  const xi = (Math.cos(d) * Math.sin(a - a0)) / D / RAD;
  const eta = (Math.sin(d) * Math.cos(d0) - Math.cos(d) * Math.sin(d0) * Math.cos(a - a0)) / D / RAD;
  const c = (size - 1) / 2;
  return [c - xi / S_DEG, c - eta / S_DEG];
}

/** A position is visible if both column and row are between -0.5 and S - 0.5. */
export function inField(px, size) {
  return !!px && px[0] >= -0.5 && px[0] <= size - 0.5 && px[1] >= -0.5 && px[1] <= size - 0.5;
}

const YEAR_MS = 365.25 * 86400000;

/** Decimal year (e.g. 2016.0) -> milliseconds since 1970 (UTC). */
export function epochToMs(epoch) {
  const y = Math.floor(epoch);
  return Date.UTC(y, 0, 1) + (epoch - y) * YEAR_MS;
}

/**
 * Move a catalog object to time `tMs` using its proper motion (format doc rule;
 * pmra already includes cos dec). Unknown proper motion -> position unchanged.
 */
export function moveToTime(obj, tMs) {
  if (obj.pmra_mas_yr == null || obj.pmdec_mas_yr == null) return [obj.ra, obj.dec];
  const years = (tMs - epochToMs(obj.epoch ?? 2016.0)) / YEAR_MS;
  return [
    obj.ra + (obj.pmra_mas_yr * years) / 3.6e6 / Math.cos(obj.dec * RAD),
    obj.dec + (obj.pmdec_mas_yr * years) / 3.6e6,
  ];
}

/** Sky width of a field in arcminutes. */
export function fieldArcmin(size) {
  return (size * PIX_ARCSEC) / 60;
}

/**
 * Parse typed coordinates. Accepts decimal degrees ("269.45 4.77", "269.45, -4.77")
 * and sexagesimal ("17h57m48s +04d46m", "17 57 48 +04 46 00", "17:57:48 +04:46").
 * Returns {ra, dec} in degrees, or null.
 */
export function parseCoords(text) {
  const t = text.trim().replace(/[−–]/g, "-").replace(/,/g, " ").replace(/\s+/g, " ");

  const dec = /^([+-]?\d+(?:\.\d+)?)\s*(?:d|°)?\s+([+-]?\d+(?:\.\d+)?)\s*(?:d|°)?$/i.exec(t);
  if (dec) return valid(+dec[1], +dec[2]);

  let raStr, decStr, sign = 1;
  const signed = /^(.+?)\s*([+-])\s*(.+)$/.exec(t);
  if (signed) {
    [, raStr, , decStr] = signed;
    sign = signed[2] === "-" ? -1 : 1;
  } else {
    const parts = t.split(" ");
    if (parts.length === 2) [raStr, decStr] = parts;
    else if (parts.length === 6) [raStr, decStr] = [parts.slice(0, 3).join(" "), parts.slice(3).join(" ")];
    else return null;
  }
  if (!/^[\d\s.hms:]+$/i.test(raStr) || !/^[\d\s.dms:'"°]+$/i.test(decStr)) return null;
  const nums = (s) => (s.match(/\d+(?:\.\d+)?/g) || []).map(Number);
  const r = nums(raStr), d = nums(decStr);
  if (r.length < 2 || r.length > 3 || d.length < 1 || d.length > 3) return null;
  if (r[1] >= 60 || (r[2] ?? 0) >= 60 || (d[1] ?? 0) >= 60 || (d[2] ?? 0) >= 60) return null;
  const ra = 15 * (r[0] + r[1] / 60 + (r[2] ?? 0) / 3600);
  const de = sign * (d[0] + (d[1] ?? 0) / 60 + (d[2] ?? 0) / 3600);
  return valid(ra, de);
}

function valid(ra, dec) {
  if (!(ra >= 0 && ra < 360 && dec >= -90 && dec <= 90)) return null;
  return { ra, dec };
}
