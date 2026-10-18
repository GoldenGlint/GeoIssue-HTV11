// Photo geolocation with Claude Code. scripts/serve.py runs each photo as a background job on the computer it runs on
// (research/geoloc_tests/claude_geoloc.py): the one serving this page, or, for the hosted app, the visitor's own once
// they turn on Settings → Claude on this computer. This module connects to it whenever it is up, polls the jobs, shows
// them in the page header and the Photo locations dialog, and tells listeners such as the upload dialog when they
// change. A job keeps running when the page closes, and the app picks it up again on the next load.
import { icon } from './icons.js';
import { esc, plural } from './format.js';
import { toast, showModal, modalHeader, closeModal } from './ui.js';
import { geolocationService, geoUrl, startGeolocation, geolocationJobs, geolocationJob, cancelGeolocation } from './api.js';
import { issueRepository } from './data.js';
import { formatDecimal, googleStreetViewUrl, googleMapsUrl } from './coordinates.js';
import { state, read, persist } from './state.js';
import { nav, render } from './app.js';
import { getMap } from './views/map-view.js';

const FINAL = ['done', 'no_answer', 'failed', 'cancelled'];
const POLL_MS = 3000, LATCH_MS = 30000;
let jobs = [], timer = null, service = null, failures = 0, latchTimer = null;
const cancelling = new Set(); // asked to stop, still running: their Cancel buttons stay disabled across polls
let seen = new Set(read('geoSeen', [])); // finished jobs already looked at, so the header stops announcing them
const listeners = new Set();

export const geolocationAvailable = () => !!service?.available;
export const geolocationModel = () => service?.model || 'opus';
export const findJob = id => jobs.find(j => j.id === id);
export const isActive = job => !!job && !FINAL.includes(job.state);
/** [lng, lat] of a finished job's answer, like every other coordinate in the app. */
export const jobCoords = job => job?.result?.final ? [job.result.final.lon, job.result.final.lat] : null;
export const zoomFor = radius => radius <= 50 ? 18 : radius <= 250 ? 16 : radius <= 1000 ? 14 : 13;
/** Calls fn(jobs) after every refresh; returns the unsubscribe function. */
export function onJobs(fn) { listeners.add(fn); return () => listeners.delete(fn); }

const clock = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const runSeconds = job => job.started_at && !FINAL.includes(job.state) ? (Date.now() - Date.parse(job.started_at)) / 1000 : job.elapsed_s || 0;
export const lastStep = job => job.steps?.at(-1);

export function jobHeadline(job) {
  const f = job.result?.final;
  switch (job.state) {
    case 'queued': return job.waiting_for?.length ? 'Waiting for another photo to finish' : 'Starting…';
    case 'running': return `Locating · ${clock(runSeconds(job))}`;
    case 'done': return f.verified ? `Placed within ${Math.round(f.radius_m)} m · verified by street imagery` : `Best guess within ${Math.round(f.radius_m).toLocaleString()} m · not verified`;
    case 'no_answer': return 'No location found';
    case 'cancelled': return 'Cancelled';
    default: return 'Couldn’t locate the photo';
  }
}

/** Whether this browser asked to use Claude on this computer from the hosted app. */
export const localClaudeOn = () => read('localClaude', false);
/** Whether that setting applies: the server this page came from can't run jobs itself. */
export const localClaudeOffered = () => !geolocationAvailable() || !!service?.local;

export async function initGeolocation(timeout) {
  clearTimeout(latchTimer);
  service = await geolocationService(localClaudeOn(), timeout);
  if (geolocationAvailable()) await refresh();
  // Latch on whenever this computer's Claude comes up, without a reload.
  else if (localClaudeOn()) latchTimer = setTimeout(latch, LATCH_MS);
}
async function latch() {
  await initGeolocation();
  if (!geolocationAvailable()) return;
  toast('Connected to Claude on this computer');
  if (!document.querySelector('.modal')) render();
}
/** Turns Settings → Claude on this computer on or off. Resolves to whether it is connected. */
export async function setLocalClaude(on) {
  persist('localClaude', on);
  clearTimeout(timer);
  if (service?.local) { service = null; jobs = []; }
  await initGeolocation(30000); // the browser may first ask to let this site reach apps on this device
  updateIndicator();
  return geolocationAvailable();
}

async function refresh() {
  clearTimeout(timer);
  const latest = await geolocationJobs();
  if (!latest) { // server unreachable (restarting?): keep what we know, and try again more slowly
    failures++;
    if (service?.local && failures >= 3) { // this computer's Claude went away: unlatch, and wait for it again
      service = null; failures = 0;
      updateIndicator();
      latchTimer = setTimeout(latch, LATCH_MS);
      return;
    }
    timer = jobs.some(isActive) ? setTimeout(refresh, Math.min(30000, POLL_MS * 2 ** failures)) : null;
    return;
  }
  failures = 0;
  const before = new Map(jobs.map(j => [j.id, j.state]));
  jobs = latest;
  for (const id of cancelling) if (!isActive(findJob(id))) cancelling.delete(id);
  for (const job of jobs) {
    const was = before.get(job.id);
    if (was && !FINAL.includes(was) && FINAL.includes(job.state)) announce(job);
  }
  await resolveSubmissions();
  listeners.forEach(fn => fn(jobs));
  updateIndicator();
  timer = jobs.some(isActive) ? setTimeout(refresh, POLL_MS) : null;
}

// ---- Submissions sent without a location: Claude's answer becomes their location when the job ends ----
/** What a finished job gives a submission: coordinates rounded like every local submission (about 100 m),
 *  and whether street imagery verified them. Null while the job is still running. */
export function locationFromJob(job) {
  if (!job || isActive(job)) return null;
  const f = job.result?.final, base = { job_id: job.id, model: job.model };
  if (!f) return { coordinates: null, location_status: 'not_found', geolocation: { ...base, error: job.error || 'Claude ended without an answer' } };
  return {
    coordinates: [Number(f.lon.toFixed(3)), Number(f.lat.toFixed(3))],
    location_status: f.verified ? 'located' : 'unverified',
    geolocation: { ...base, verified: f.verified, radius_m: Math.round(f.radius_m), place_description: f.place_description || '' },
  };
}

// The submission waits in Tiger Data until this browser sends Claude's answer (only it holds the token). An answer
// that couldn't be sent yet is retried on the next refresh or page load.
async function resolveSubmissions() {
  const waiting = state.pending.filter(p => (p.location_status === 'locating' && p.geolocation?.job_id) || p.unsent_location);
  if (!waiting.length) return;
  let changed = 0;
  for (const entry of waiting) {
    if (entry.location_status === 'locating') {
      // a job that has dropped off the recent list is fetched on its own
      const job = findJob(entry.geolocation.job_id) || await geolocationJob(entry.geolocation.job_id);
      const found = locationFromJob(job);
      if (!found) continue;
      Object.assign(entry, found, { address: entry.address || found.geolocation.place_description || '', unsent_location: !!entry.token });
      changed++;
    }
    if (entry.unsent_location) {
      try { await issueRepository.locateSubmission(entry); entry.unsent_location = false; changed++; } catch { /* retried later */ }
    }
  }
  if (!changed) return;
  persist('pending', state.pending);
  const published = waiting.filter(p => !p.unsent_location && p.coordinates).length;
  toast(published ? `Claude finished locating ${published === 1 ? 'a submitted photo. The issue is now on the map' : `${published} submitted photos. They are now on the map`} under Collected.` : 'Claude finished with a submitted photo. See Saved → Your submissions.');
  if (['saved', 'verify'].includes(state.view) && !document.querySelector('.modal')) render();
}

/** Starts a job for a photo File and returns its first status. */
export async function locatePhoto(file) {
  const job = await startGeolocation(file);
  jobs = [job, ...jobs.filter(j => j.id !== job.id)];
  listeners.forEach(fn => fn(jobs));
  updateIndicator();
  clearTimeout(timer);
  timer = setTimeout(refresh, POLL_MS);
  return job;
}

export const isCancelling = id => cancelling.has(id);
/** Cancel button markup for a running job; disabled once asked, until the job stops. */
export const cancelButton = (id, attrs) => `<button type="button" class="button small" ${attrs} ${cancelling.has(id) ? 'disabled' : ''}>${icon('close')} ${cancelling.has(id) ? 'Cancelling…' : 'Cancel'}</button>`;

export async function cancelJob(id) {
  cancelling.add(id);
  listeners.forEach(fn => fn(jobs));
  try { await cancelGeolocation(id); } catch (error) { cancelling.delete(id); toast(`Couldn’t cancel: ${error.message}`); }
  refresh();
}

// A card already showing this job (upload dialog, jobs dialog) is enough; otherwise say so once.
function announce(job) {
  if (document.querySelector(`[data-geo-job="${job.id}"]`)) return;
  toast(job.state === 'done' ? `Claude finished locating a photo: ${jobHeadline(job).toLowerCase()}. See Photo locations in the header.` : `Claude couldn’t locate a photo (${job.error || job.state}).`);
}

// ---- Header indicator: re-rendered with the page, and updated in place between renders ----
export function geoIndicatorHtml() {
  if (!geolocationAvailable() || !jobs.length) return '';
  const active = jobs.filter(isActive).length, ready = jobs.filter(j => j.state === 'done' && !seen.has(j.id)).length;
  const label = active ? `Locating ${plural(active, 'photo')}` : ready ? `${plural(ready, 'location')} ready` : 'Photo locations';
  return `<button id="geo-jobs" class="geo-jobs ${active ? 'running' : ready ? 'ready' : ''}" data-geo-jobs title="Photos located by Claude" aria-label="${label}">${active ? '<span class="spinner"></span>' : icon('locate')}<span>${label}</span></button>`;
}
function updateIndicator() {
  const el = document.querySelector('#geo-jobs'), html = geoIndicatorHtml();
  if (el) { if (html) el.outerHTML = html; else el.remove(); }
  else if (html) document.querySelector('.header-right')?.insertAdjacentHTML('afterbegin', html);
}
document.addEventListener('click', e => { if (e.target.closest('[data-geo-jobs]')) geoJobsModal(); });

// ---- Photo locations dialog ----
function stepsHtml(steps, live) {
  return `<ol class="geo-steps">${steps.map((s, i) => `<li class="${live && i === steps.length - 1 && s.outcome == null ? 'current' : ''}"><span>${esc(s.label)}</span>${s.outcome ? `<small>${esc(s.outcome)}</small>` : ''}</li>`).join('')}</ol>`;
}
function resultHtml(job) {
  const f = job.result.final, coords = jobCoords(job);
  const sheets = (job.references || []).map((m, i) => `<a href="${geoUrl(`/api/geolocate/${job.id}/references/${esc(m)}`)}" target="_blank" rel="noopener"><img src="${geoUrl(`/api/geolocate/${job.id}/references/${esc(m)}`)}" alt="Street-level references compared in match ${i + 1}" loading="lazy"></a>`).join('');
  return `${f.place_description ? `<p class="geo-place">${esc(f.place_description)}</p>` : ''}<div class="geo-facts"><span>${formatDecimal(coords)}</span><span>±${Math.round(f.radius_m).toLocaleString()} m</span><span>${Math.round(f.confidence * 100)}% confident</span>${job.result.error_m != null ? `<span>${Math.round(job.result.error_m)} m from the known spot</span>` : ''}</div>
    <details class="geo-details"><summary>How Claude found it</summary><p>${esc(f.evidence)}</p>${stepsHtml(job.steps || [], false)}${sheets ? `<p class="fine-print">Street-level references compared (Mapillary, CC BY-SA):</p><div class="geo-sheets">${sheets}</div>` : ''}</details>`;
}
function jobHtml(job) {
  const when = new Date(job.created_at).toLocaleString('en-CA', { dateStyle: 'medium', timeStyle: 'short' });
  const took = job.state === 'running' ? '' : job.elapsed_s ? ` · took ${clock(job.elapsed_s)}` : '';
  const coords = jobCoords(job), radius = job.result?.final?.radius_m;
  let body = '', actions = '';
  if (isActive(job)) {
    body = job.steps?.length ? stepsHtml(job.steps.slice(-4), true) : '<p class="geo-place">Starting Claude…</p>';
    actions = cancelButton(job.id, `data-geo-cancel="${job.id}"`);
  } else if (coords) {
    body = resultHtml(job);
    actions = `<button class="button small primary" data-geo-map="${job.id}">${icon('map')} Show on map</button><a class="button small" href="${googleStreetViewUrl(coords)}" target="_blank" rel="noopener">${icon('external')} Street View</a><a class="button small" href="${googleMapsUrl(coords)}" target="_blank" rel="noopener">${icon('map')} Google Maps</a>`;
  } else {
    body = `<p class="geo-place">${esc(job.error || 'Claude ended without an answer.')}</p>${job.steps?.length ? `<details class="geo-details"><summary>What was tried</summary>${stepsHtml(job.steps, false)}</details>` : ''}`;
    actions = `<button class="button small" data-geo-retry="${job.id}">${icon('refresh')} Try again</button>`;
  }
  const kind = job.state === 'done' ? (job.result.final.verified ? 'verified' : 'unverified') : job.state;
  return `<article class="geo-job ${kind}" data-geo-job="${job.id}" data-sig="${esc(`${job.state}|${job.steps?.length}|${radius}`)}"><img class="geo-job-photo" src="${geoUrl(`/api/geolocate/${job.id}/photo`)}" alt="Photo being located"><div class="geo-job-body"><strong class="geo-job-title">${isActive(job) ? '<span class="spinner"></span>' : icon(kind === 'verified' ? 'check' : kind === 'unverified' ? 'warning' : 'locate')}${esc(jobHeadline(job))}</strong><small class="geo-job-meta">${when} · Claude ${esc(job.model)}${took}</small>${body}<div class="geo-job-actions">${actions}</div></div></article>`;
}

// Re-renders only the cards that changed, so open details and scroll position survive polling.
function renderJobs(root) {
  if (!jobs.length) { root.innerHTML = '<p class="modal-intro">No photos located yet. Add a photo in Upload new issue and choose Locate with Claude.</p>'; return; }
  const cards = new Map([...root.querySelectorAll('[data-geo-job]')].map(el => [el.dataset.geoJob, el]));
  if (jobs.some(j => !cards.has(j.id)) || cards.size !== jobs.length) root.innerHTML = jobs.map(jobHtml).join('');
  else for (const job of jobs) {
    const el = cards.get(job.id), html = jobHtml(job), sig = html.match(/data-sig="([^"]*)"/)[1];
    if (el.dataset.sig !== sig || isActive(job)) el.outerHTML = html;
  }
  root.querySelectorAll('[data-geo-cancel]').forEach(b => b.onclick = () => cancelJob(b.dataset.geoCancel));
  root.querySelectorAll('[data-geo-map]').forEach(b => b.onclick = () => showOnMap(findJob(b.dataset.geoMap)));
  root.querySelectorAll('[data-geo-retry]').forEach(b => b.onclick = () => retry(b.dataset.geoRetry, b));
}

export function geoJobsModal() {
  seen = new Set([...seen, ...jobs.filter(j => FINAL.includes(j.state)).map(j => j.id)]);
  persist('geoSeen', [...seen].slice(-200));
  let stop = null;
  showModal(`${modalHeader('', 'Photo locations')}<div class="modal-body"><p class="modal-intro">Claude reads each photo for signs and landmarks, searches maps and City street furniture, and checks candidate spots against street-level imagery. Only an image match counts as verified; other answers are leads with a wide radius.</p><div id="geo-job-list" class="geo-job-list"></div></div><div class="modal-footer"><span class="subtle-label">Jobs keep running when this dialog or the page is closed</span><label class="button">${icon('upload')} Locate a photo<input id="geo-new-photo" type="file" accept="image/jpeg,image/png,image/webp" hidden></label><button class="button primary" data-close>Done</button></div>`, { wide: true, label: 'Photo locations', onClose: () => stop?.() });
  const list = document.querySelector('#geo-job-list');
  document.querySelector('#geo-new-photo').onchange = async e => {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024) { toast('Use a JPEG, PNG or WebP photo smaller than 10 MB.'); return; }
    try { await locatePhoto(file); list.scrollTop = 0; } catch (error) { toast(`Couldn’t start Claude: ${error.message}`); }
  };
  renderJobs(list);
  stop = onJobs(() => renderJobs(list));
  updateIndicator();
}

export function showOnMap(job) {
  const coords = jobCoords(job);
  if (!coords) return;
  closeModal(); nav('map');
  requestAnimationFrame(() => getMap()?.flyTo(coords, zoomFor(job.result.final.radius_m)));
  toast(`Map centred on Claude’s estimate (±${Math.round(job.result.final.radius_m).toLocaleString()} m)`);
}

async function retry(id, button) {
  button.disabled = true;
  try {
    const blob = await fetch(geoUrl(`/api/geolocate/${id}/photo`)).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.blob(); });
    await locatePhoto(new File([blob], 'photo', { type: blob.type || 'image/jpeg' }));
  } catch (error) {
    button.disabled = false;
    toast(`Couldn’t start again: ${error.message}`);
  }
}
