// Calls to the server's API (scripts/serve.py): Gemini, and photo geolocation with Claude Code. The key never reaches the browser.
// Every call fails soft: a static server or a missing key simply turns the AI features off.
let statusPromise;
export const apiStatus = () => statusPromise ||= fetch('/api/status', { cache: 'no-store' })
  .then(r => r.ok ? r.json() : { gemini: false })
  .catch(() => ({ gemini: false }));

async function post(path, body) {
  const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

/** Downscales a photo (longest side ≤ maxSide) and returns { base64, mime }, so requests stay small. */
export async function photoForUpload(file, maxSide = 1280) {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const canvas = Object.assign(document.createElement('canvas'), { width: Math.round(bitmap.width * scale), height: Math.round(bitmap.height * scale) });
  canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close?.();
  return { base64: canvas.toDataURL('image/jpeg', 0.85).split(',')[1], mime: 'image/jpeg' };
}

/** Gemini suggestions for an issue photo: category, severity, description, privacy flags and face/plate boxes. */
export async function triagePhoto(file) {
  const { base64, mime } = await photoForUpload(file);
  return post('/api/triage', { image: base64, mime });
}

/** A short, neutral area summary written by Gemini from areas.json-style stats. */
export const writeDigest = (area, label = 'ward', trendDays = 7) => post('/api/digest', { area, label, trend_days: trendDays });

// ---- Photo geolocation: Claude Code jobs run in the background by the local server ----
// Jobs run where Claude Code is: on the server this page came from, or, for the hosted app, on the visitor's own
// computer (scripts/serve.py on its default port) once they turn on Settings → Claude on this computer.
export const LOCAL_CLAUDE = 'http://127.0.0.1:5173';
let geoBase = '';
/** A geolocation API path on whichever server runs the jobs. */
export const geoUrl = path => geoBase + path;
/** That server's geolocate status (with local: true for this computer's), or null when neither can run jobs. */
export async function geolocationService(useLocal, timeout = 3000) {
  geoBase = '';
  const own = (await apiStatus()).geolocate || null;
  if (own?.available || !useLocal || globalThis.location?.origin === LOCAL_CLAUDE) return own;
  // The first request may wait on the browser asking to let this site reach apps on this device.
  const local = await fetch(`${LOCAL_CLAUDE}/api/status`, { cache: 'no-store', signal: AbortSignal.timeout(timeout) })
    .then(r => r.ok ? r.json() : null).catch(() => null);
  if (!local?.geolocate?.available) return null;
  geoBase = LOCAL_CLAUDE;
  return { ...local.geolocate, local: true };
}
/** Starts a job for a photo and returns its status. Sent larger than for triage: small signs matter. */
export async function startGeolocation(file) {
  const { base64, mime } = await photoForUpload(file, 2048);
  return post(geoUrl('/api/geolocate'), { image: base64, mime });
}
/** The jobs, newest first, or null when the server can't be reached (it may be restarting). */
export const geolocationJobs = () => fetch(geoUrl('/api/geolocate'), { cache: 'no-store' })
  .then(r => r.ok ? r.json() : null).then(d => d && (d.jobs || [])).catch(() => null);
/** One job's status, or null when it can't be fetched. */
export const geolocationJob = id => fetch(geoUrl(`/api/geolocate/${encodeURIComponent(id)}`), { cache: 'no-store' })
  .then(r => r.ok ? r.json() : null).catch(() => null);
export const cancelGeolocation = id => post(geoUrl(`/api/geolocate/${encodeURIComponent(id)}/cancel`), {});
