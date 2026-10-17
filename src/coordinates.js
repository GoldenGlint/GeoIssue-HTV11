// Reading and writing locations: Google Maps links, decimal degrees, degrees-minutes and degrees-minutes-seconds.
// Pure functions with no DOM access, so they run in Node tests (tests/coordinates.test.mjs).

export const TORONTO_LIMITS = { west: -79.64, south: 43.58, east: -79.11, north: 43.86 };
const inside = ([lng, lat], b = TORONTO_LIMITS) => lng >= b.west && lng <= b.east && lat >= b.south && lat <= b.north;
const round = v => Number(v.toFixed(6));

export const googleStreetViewUrl = ([lng, lat]) => `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat.toFixed(6)},${lng.toFixed(6)}`;
export const googleMapsUrl = ([lng, lat]) => `https://www.google.com/maps/search/?api=1&query=${lat.toFixed(6)},${lng.toFixed(6)}`;

/** 43.645512, -79.395312 → 43°38′43.8″N 79°23′43.1″W */
export function formatDms([lng, lat]) {
  const part = (value, pos, neg) => {
    const abs = Math.abs(value);
    let d = Math.floor(abs), m = Math.floor((abs - d) * 60), s = Number(((abs - d - m / 60) * 3600).toFixed(1));
    if (s >= 60) { s = 0; m += 1; }
    if (m >= 60) { m = 0; d += 1; }
    return `${d}°${String(m).padStart(2, '0')}′${s.toFixed(1).padStart(4, '0')}″${value < 0 ? neg : pos}`;
  };
  return `${part(lat, 'N', 'S')} ${part(lng, 'E', 'W')}`;
}
export const formatDecimal = ([lng, lat]) => `${lat.toFixed(5)}, ${lng.toFixed(5)}`;

/** Metres between two [lng, lat] points (haversine). */
export function distanceMetres([lng1, lat1], [lng2, lat2]) {
  const r = Math.PI / 180, h = Math.sin((lat2 - lat1) * r / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin((lng2 - lng1) * r / 2) ** 2;
  return 2 * 6371008.8 * Math.asin(Math.sqrt(h));
}

// Google Maps links, most specific first: a place's own position (!3d…!4d…) beats the camera position (@lat,lng).
const LINK_PATTERNS = [
  /!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)/,
  /[?&](?:q|query|ll|viewpoint|destination|center)=(?:loc:)?(-?\d+(?:\.\d+)?)(?:,|%2C)\s*(?:\+|%20)?(-?\d+(?:\.\d+)?)/i,
  /@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/,
];

/**
 * Reads a location from a pasted Google Maps link or typed coordinates.
 * Returns { coordinates: [lng, lat], source, note? } or { error }.
 */
export function parseLocation(input, bounds = TORONTO_LIMITS) {
  const text = String(input ?? '').trim();
  if (!text) return { error: 'Paste a Google Maps link or type coordinates.' };
  if (/^(https?:\/\/)?(www\.)?(google\.[a-z.]+\/maps|maps\.google\.|maps\.app\.goo\.gl|goo\.gl\/maps)/i.test(text)) return fromLink(text, bounds);
  if (/^https?:\/\//i.test(text)) return { error: 'That link isn’t from Google Maps. Paste a Google Maps link, or type the coordinates.' };
  return fromText(text, bounds);
}

function fromLink(link, bounds) {
  if (/maps\.app\.goo\.gl|goo\.gl\/maps/i.test(link)) {
    return { error: 'Short share links hide the coordinates. Open the link, then copy the full address from the browser bar, or right-click the spot in Google Maps and copy its coordinates.' };
  }
  let decoded = link;
  try { decoded = decodeURIComponent(link); } catch { /* keep the raw link */ }
  for (const pattern of LINK_PATTERNS) {
    const match = decoded.match(pattern);
    if (match) return check([Number(match[2]), Number(match[1])], 'google_maps_link', bounds);
  }
  return { error: 'This link names a place without coordinates. In Google Maps, right-click the exact spot and copy the coordinates shown at the top of the menu.' };
}

// One coordinate: optional hemisphere letter before or after, degrees with optional minutes and seconds.
// Letter units (d, m, s) are not accepted: "S" could mean seconds or south.
const PART = /^([NSEW])?\s*([-+])?\s*(\d+(?:\.\d+)?)\s*°?\s*(?:(\d+(?:\.\d+)?)\s*'?\s*)?(?:(\d+(?:\.\d+)?)\s*"?\s*)?([NSEW])?$/;

function fromText(raw, bounds) {
  const text = raw.toUpperCase()
    .replace(/[′’‘`´]/g, "'").replace(/[″“”]/g, '"').replace(/''/g, '"').replace(/º/g, '°')
    .replace(/\s+/g, ' ').trim();
  const halves = split(text);
  if (!halves) return { error: 'Couldn’t read two coordinates. Try 43.6455, -79.3953 or 43°38′43.8″N 79°23′43.1″W.' };
  const parts = halves.map(h => readPart(h.trim()));
  if (parts.some(p => p.error)) return { error: parts.find(p => p.error).error };
  let lat, lng;
  const [a, b] = parts;
  if (a.axis && b.axis && a.axis === b.axis) return { error: 'Both values are latitudes or both are longitudes. Use one N/S value and one E/W value.' };
  if (a.axis === 'lng' || b.axis === 'lat') [lng, lat] = [a.value, b.value];
  else [lat, lng] = [a.value, b.value];
  if (Math.abs(lat) > 90 || Math.abs(lng) > 180) {
    if (Math.abs(lng) <= 90 && Math.abs(lat) <= 180 && !a.axis && !b.axis) [lat, lng] = [lng, lat];
    else return { error: 'Latitude must be between -90 and 90, and longitude between -180 and 180.' };
  }
  // Toronto longitudes are west (negative). "43.65, 79.39" almost always means 79.39 W.
  if (!a.axis && !b.axis && lng > 0 && inside([-lng, lat], bounds)) return check([-lng, lat], 'coordinates', bounds, 'Read as west longitude.');
  // Typed longitude first ("-79.39, 43.65"): swap when only the swapped order lands in the area.
  if (!a.axis && !b.axis && !inside([lng, lat], bounds) && inside([lat, lng], bounds)) return check([lat, lng], 'coordinates', bounds, 'Read as longitude, latitude.');
  return check([lng, lat], 'coordinates', bounds);
}

function split(text) {
  const byComma = text.split(/\s*[,;]\s*/);
  if (byComma.length === 2) return byComma;
  const letters = [...text.matchAll(/[NSEW]/g)].map(m => m.index);
  if (letters.length === 2) {
    // "N 43 38 W 79 23" (prefix) or "43 38 N 79 23 W" (suffix).
    return /^[NSEW]/.test(text) ? [text.slice(0, letters[1]), text.slice(letters[1])] : [text.slice(0, letters[0] + 1), text.slice(letters[0] + 1)];
  }
  const tokens = text.split(' ');
  // "43°38'43.8" 79°23'43.1"" or "43° 38' 79° 23'": the second value starts at the second degree sign.
  const degreeTokens = tokens.flatMap((t, j) => t.includes('°') ? [j] : []);
  if (degreeTokens.length === 2 && degreeTokens[0] === 0) return [tokens.slice(0, degreeTokens[1]).join(' '), tokens.slice(degreeTokens[1]).join(' ')];
  // "43.6455 -79.3953", "43 38.73 79 23.72" or "43 38 43.8 79 23 43.1": split the numbers evenly.
  const numbers = text.match(/-?\d+(?:\.\d+)?/g) || [];
  if ([2, 4, 6].includes(numbers.length) && tokens.length === numbers.length) {
    const per = numbers.length / 2;
    return [tokens.slice(0, per).join(' '), tokens.slice(per).join(' ')];
  }
  return null;
}

function readPart(text) {
  const m = text.match(PART);
  if (!m) return { error: `Couldn’t read “${text}”. Use decimal degrees (43.6455) or degrees, minutes and seconds (43°38′43.8″N).` };
  const [, before, sign, d, min, sec, after] = m;
  if (before && after) return { error: `“${text}” has two direction letters.` };
  if ((min && Number(min) >= 60) || (sec && Number(sec) >= 60)) return { error: 'Minutes and seconds must be less than 60.' };
  if ((min || sec) && d.includes('.')) return { error: `“${text}” has decimal degrees and minutes. Use one or the other.` };
  const hemisphere = before || after;
  let value = Number(d) + Number(min || 0) / 60 + Number(sec || 0) / 3600;
  if (sign === '-' || hemisphere === 'S' || hemisphere === 'W') value = -value;
  if (sign === '-' && (hemisphere === 'S' || hemisphere === 'W')) value = -Math.abs(value);
  return { value, axis: hemisphere ? ('NS'.includes(hemisphere) ? 'lat' : 'lng') : null };
}

function check(coordinates, source, bounds, note) {
  const [lng, lat] = coordinates.map(round);
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) return { error: 'Couldn’t read coordinates from that.' };
  if (!inside([lng, lat], bounds)) return { error: `That point (${lat.toFixed(4)}, ${lng.toFixed(4)}) is outside Toronto. Check the order and the minus sign on the longitude.` };
  return note ? { coordinates: [lng, lat], source, note } : { coordinates: [lng, lat], source };
}
