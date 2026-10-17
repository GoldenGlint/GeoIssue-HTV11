// Dialogs: upload, infrastructure & proximity, export, settings, help, street-level and issue details.
import { categories, infrastructure, issueRepository, TORONTO_BOUNDS, TORONTO_CENTER } from './data.js';
import { CivicMap } from './map.js';
import { icon } from './icons.js';
import { esc, badge, typeIcon, countBy } from './format.js';
import { state, scopedRows, persist, remember } from './state.js';
import { toast, showModal, closeModal, modalHeader, detailHtml } from './ui.js';
import { render, nav, toggleSave } from './app.js';
import { getMap, openIssue, frameIssues } from './views/map-view.js';

const freshDraft = () => ({ photos: [], category: '', description: '', address: '', confirmed: false, coordinates: null });
let uploadDraft = freshDraft(), picker = null;
const insideToronto = ([lng, lat]) => lng >= TORONTO_BOUNDS.west && lng <= TORONTO_BOUNDS.east && lat >= TORONTO_BOUNDS.south && lat <= TORONTO_BOUNDS.north;
const coordinateText = ([lng, lat]) => `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
const steps = review => `<div class="step-indicator"><span class="${!review ? 'active' : ''}">1 <b>Issue details</b></span><i></i><span class="${review ? 'active' : ''}">2 <b>Review & submit</b></span></div>`;

// The pin stays fixed in the middle of a small map; dragging the map underneath places it.
function initPicker() {
  picker = new CivicMap(document.querySelector('#picker-map'), { onSelect() {}, onEmpty() {}, onMove: updatePicker, icon: typeIcon, home: TORONTO_CENTER });
  picker.center = uploadDraft.coordinates || getMap()?.center || state.center;
  picker.zoom = 15;
  picker.setData([]);
  updatePicker();
}
function updatePicker() {
  if (!picker) return;
  uploadDraft.coordinates = picker.center.map(v => Number(v.toFixed(5)));
  const readout = document.querySelector('#picker-readout'), inside = insideToronto(uploadDraft.coordinates);
  readout.textContent = inside ? `${coordinateText(uploadDraft.coordinates)} · approximate` : 'Outside Toronto. Move the pin.';
  readout.classList.toggle('outside', !inside);
}
function destroyPicker() { picker?.destroy(); picker = null; }

export function uploadModal(review = false) {
  if (review) { uploadReview(); return; }
  showModal(`${modalHeader('COMMUNITY SUBMISSION', 'Upload new issue')}${steps(false)}<form id="upload-form"><div class="modal-body">
    <p class="modal-intro">Noticed something that needs attention? Give it a little context.</p>
    <label class="upload-zone">${icon('upload')}<strong>Choose photos of the issue</strong><span>JPEG, PNG, or WebP · up to 3 photos · 10 MB each</span><input id="photo-input" type="file" accept="image/jpeg,image/png,image/webp" multiple ${uploadDraft.photos.length ? '' : 'required'}></label>
    <div id="photo-previews" class="photo-previews"></div>
    <div id="upload-error" class="form-error" role="alert"></div>
    <label class="form-label">Issue category <span>*</span><select name="category" required><option value="">Choose a category</option>${Object.keys(categories).map(t => `<option ${uploadDraft.category === t ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
    <label class="form-label">What did you notice? <span>*</span><textarea name="description" placeholder="Describe the issue and how it affects the public space…" minlength="10" maxlength="1000" required>${esc(uploadDraft.description)}</textarea></label>
    <div class="picker-field"><span class="form-label">Location <span>*</span></span><div class="picker-map-wrap"><div id="picker-map" class="city-map" aria-label="Drag the map to place the issue pin"></div><span class="picker-pin">${icon('pin')}</span><span id="picker-readout" class="picker-readout"></span></div><small class="picker-hint">Drag the map so the pin sits on the issue. Approximate is fine.</small></div>
    <label class="form-label">Nearest address or intersection <span>*</span><div class="input-with-icon">${icon('pin')}<input name="address" placeholder="e.g. King St W & Spadina Ave, Toronto" value="${esc(uploadDraft.address)}" minlength="5" maxlength="200" required></div><small>Helps reviewers find the spot. Address search connects here when geocoding is ready.</small></label>
    <label class="checkbox-label"><input name="confirmed" type="checkbox" ${uploadDraft.confirmed ? 'checked' : ''} required> I confirm this approximate location is in Toronto.</label>
    <p class="fine-print">Your photos stay on this device in this demo. Please avoid faces, plates, and private interiors.</p>
  </div><div class="modal-footer"><span class="subtle-label">* Required information</span><button class="button primary" type="submit">Review issue ${icon('arrow')}</button></div></form>`, { label: 'Upload new issue', onClose: destroyPicker });
  const form = document.querySelector('#upload-form'), error = document.querySelector('#upload-error'), input = document.querySelector('#photo-input');
  const saveDraft = () => { uploadDraft.category = form.category.value; uploadDraft.description = form.description.value; uploadDraft.address = form.address.value; uploadDraft.confirmed = form.confirmed.checked; };
  form.oninput = saveDraft;
  const previews = () => {
    document.querySelector('#photo-previews').innerHTML = uploadDraft.photos.map((p, j) => `<div><img src="${p.url}" alt="Selected issue photo ${j + 1}"><button type="button" data-remove-photo="${j}" aria-label="Remove photo ${j + 1}">×</button></div>`).join('');
    input.required = !uploadDraft.photos.length;
    document.querySelectorAll('[data-remove-photo]').forEach(b => b.onclick = () => {
      const [removed] = uploadDraft.photos.splice(Number(b.dataset.removePhoto), 1);
      URL.revokeObjectURL(removed.url); input.value = ''; previews();
    });
  };
  previews();
  input.onchange = e => {
    const files = [...e.target.files];
    const message = files.some(f => !['image/jpeg', 'image/png', 'image/webp'].includes(f.type) || f.size > 10 * 1024 * 1024) ? 'Use JPEG, PNG, or WebP files smaller than 10 MB.'
      : files.length + uploadDraft.photos.length > 3 ? 'Choose up to 3 photos. Remove a photo before adding another.' : '';
    error.textContent = message;
    if (message) { e.target.value = ''; return; }
    uploadDraft.photos.push(...files.map(file => ({ file, url: URL.createObjectURL(file) })));
    previews();
  };
  form.onsubmit = e => {
    e.preventDefault(); saveDraft();
    if (!uploadDraft.photos.length) { error.textContent = 'Add at least one photo.'; return; }
    if (!uploadDraft.coordinates || !insideToronto(uploadDraft.coordinates)) { error.textContent = 'Move the map so the pin is inside Toronto.'; error.scrollIntoView({ block: 'nearest' }); return; }
    uploadModal(true);
  };
  initPicker();
}

function uploadReview() {
  showModal(`${modalHeader('COMMUNITY SUBMISSION', 'Review your issue')}${steps(true)}<div class="modal-body"><div class="review-photos">${uploadDraft.photos.map(p => `<img src="${p.url}" alt="Photo to submit">`).join('')}</div><h3>${esc(uploadDraft.category)}</h3><p>${esc(uploadDraft.description)}</p><div class="confidence-note">${icon('pin')}<div><strong>${esc(uploadDraft.address)}</strong><span>${coordinateText(uploadDraft.coordinates)} · approximate location · confirmed by you</span></div></div><div class="notice-banner">${icon('shield')} Avoid personal information and identifiable people. Submissions require privacy processing and verification before publication.</div><p class="fine-print">Prototype mode: only the issue details are stored in this browser, with the pin rounded to about 100 m. Photos are previewed locally and are not uploaded. This does not create a Toronto 311 request.</p></div><div class="modal-footer"><button class="button" id="upload-back">Back to details</button><button class="button primary" id="upload-submit">Submit local demo ${icon('arrow')}</button></div>`, { label: 'Review your issue' });
  document.querySelector('#upload-back').onclick = () => uploadModal();
  document.querySelector('#upload-submit').onclick = async e => {
    e.currentTarget.disabled = true;
    try {
      const result = await issueRepository.submit({ category: uploadDraft.category, description: uploadDraft.description, address: uploadDraft.address, coordinates: uploadDraft.coordinates.map(v => Number(v.toFixed(3))), created_at: new Date().toISOString() });
      state.pending.push(result); persist('pending', state.pending);
      for (const p of uploadDraft.photos) URL.revokeObjectURL(p.url);
      uploadDraft = freshDraft();
      showModal(`${modalHeader('LOCAL DEMO RECEIPT', 'Thanks for looking out.')}<div class="submission-success">${icon('shield')}<h3>Your sample issue is pending review</h3><code>${result.issue_id}</code><p>Details were saved locally and appear under Saved → Your submissions. No photos were uploaded or published. Connect the submission API to send reports to your team.</p>${badge('Pending review')}</div><div class="modal-footer"><button class="button primary" data-close>Back to workspace</button></div>`, { label: 'Submission received' });
      render();
    } catch {
      document.querySelector('#upload-submit').disabled = false;
      toast('Submission failed. Your details and photos are preserved; please retry.');
    }
  };
}

export function infrastructureModal() {
  const types = ['TTC', 'Schools', 'Roads'], glyph = { TTC: 'train', Schools: 'school', Roads: 'road' }, counts = countBy(infrastructure, 'type');
  showModal(`${modalHeader('MAP CONTEXT', 'Infrastructure & proximity')}<div class="modal-body"><p class="modal-intro">Show sample infrastructure on the map, or narrow issues by their distance to an asset.</p><div class="notice-banner">${icon('layers')} Asset positions are approximate samples. Replace them with TTC, school and Centreline open data.</div><h3>Visible layers</h3><div class="layer-options">${types.map(t => `<label><input type="checkbox" data-layer="${t}" ${state.layers.includes(t) ? 'checked' : ''}>${icon(glyph[t])}<span>${t}</span><small>${counts[t]} sample ${t === 'Roads' ? 'highways' : 'assets'}</small></label>`).join('')}</div><h3>Issues near infrastructure</h3><div class="form-row"><label class="form-label">Asset category<select id="infra-type"><option value="">Don’t filter by distance</option><option value="any" ${state.filters.infra === 'any' ? 'selected' : ''}>Any infrastructure</option>${types.map(t => `<option ${state.filters.infra === t ? 'selected' : ''}>${t}</option>`).join('')}</select></label><label class="form-label">Distance<select id="infra-radius" ${state.filters.infra ? '' : 'disabled'}>${[250, 500, 1000, 2000].map(n => `<option value="${n}" ${String(n) === state.filters.radius ? 'selected' : ''}>Within ${n < 1000 ? `${n}m` : `${n / 1000}km`}</option>`).join('')}</select></label></div><p class="fine-print">Distance is measured to the nearest asset of the chosen category: stations and schools as points, highways as lines.</p></div><div class="modal-footer"><button class="button primary" id="apply-infrastructure">Apply to workspace</button></div>`, { label: 'Infrastructure and proximity' });
  const type = document.querySelector('#infra-type'), radius = document.querySelector('#infra-radius');
  type.onchange = () => { radius.disabled = !type.value; };
  document.querySelector('#apply-infrastructure').onclick = () => {
    state.layers = [...document.querySelectorAll('[data-layer]:checked')].map(el => el.dataset.layer);
    state.filters.infra = type.value; state.filters.radius = radius.value;
    state.page = 1; state.selected = []; state.panel = null;
    closeModal(); render();
  };
}

export function streetModal() {
  showModal(`${modalHeader('STREET-LEVEL EXPLORER', 'A closer look, coming soon')}<div class="modal-body"><div class="street-placeholder">${icon('person')}<strong>No street-level imagery connected</strong><span>Mapillary viewer integration point</span></div><p>Connect your Mapillary image lookup and viewer here to browse available photos near a dropped position.</p><p class="fine-print">Coverage, photo dates, attribution, and adjacent-image navigation depend on the provider. This prototype does not claim live street-level coverage.</p></div><div class="modal-footer"><button class="button" data-close>Return to map</button></div>`, { label: 'Street-level explorer' });
}

export function exportModal(preferredScope = 'filtered') {
  const rows = scopedRows(), selected = rows.filter(i => state.selected.includes(i.issue_id));
  showModal(`${modalHeader('TAKE A CLOSER LOOK', 'Export issue data')}<div class="modal-body"><p>Export the current filtered dataset. Public exports omit coordinates and include the location uncertainty in metres.</p><label class="form-label">Scope<select id="export-scope"><option value="filtered">Filtered results (${rows.length})</option><option value="selected" ${preferredScope === 'selected' ? 'selected' : ''} ${!selected.length ? 'disabled' : ''}>Selected rows (${selected.length})</option></select></label><label class="form-label">Format<select id="export-format"><option value="csv">CSV · spreadsheet</option><option value="geojson">GeoJSON · approximate areas</option></select></label><div class="notice-banner">${icon('shield')} Exports contain fictional records, source labels, ISO timestamps, uncertainty, and the active filters.</div></div><div class="modal-footer"><button class="button primary" id="download-export">${icon('download')} Download</button></div>`, { label: 'Export issue data' });
  document.querySelector('#download-export').onclick = () => {
    exportData(document.querySelector('#export-scope').value === 'selected' ? selected : rows, document.querySelector('#export-format').value);
    closeModal();
  };
}
function exportData(rows, format) {
  let content, mime;
  if (format === 'csv') {
    const headers = ['issue_id', 'issue_type', 'severity', 'resolution_status', 'verification_status', 'neighbourhood_id', 'neighbourhood_name', 'ward_id', 'ward_name', 'address', 'location_radius_m', 'geo_method', 'nearest_asset', 'nearest_asset_type', 'distance_to_asset_m', 'first_seen_at_iso', 'last_seen_at_iso', 'sightings_count', 'detection_confidence', 'source_category', 'is_demo', 'filters_applied'];
    const values = rows.map(i => [i.issue_id, i.issue_type, i.severity, i.resolution_status, i.verification_status, i.neighbourhood_id, i.neighbourhood_name, i.ward_id, i.ward_name, i.address, i.location_radius_m, i.geo_method, i.asset_name, i.infrastructure_type, i.distance_m, i.first_seen_at, i.last_seen_at, i.sightings_count, i.detection_confidence, i.source_category, true, JSON.stringify(state.filters)]);
    // Prefix cells that a spreadsheet would treat as formulas.
    const cell = v => { let s = String(v ?? ''); if (/^[=+\-@\t\r]/.test(s)) s = "'" + s; return '"' + s.replaceAll('"', '""') + '"'; };
    content = '﻿' + [headers, ...values].map(row => row.map(cell).join(',')).join('\r\n');
    mime = 'text/csv;charset=utf-8';
  } else {
    content = JSON.stringify({
      type: 'FeatureCollection', is_demo: true, filters_applied: state.filters,
      coordinate_policy: 'Approximate uncertainty areas, public demo; not exact issue positions.',
      features: rows.map(i => {
        const [lng, lat] = i.geometry.coordinates, r = Math.max(i.location_radius_m, 250), dy = r / 111320, dx = dy / Math.cos(lat * Math.PI / 180);
        const ring = Array.from({ length: 33 }, (_, j) => { const a = j / 32 * Math.PI * 2; return [Number((lng + dx * Math.cos(a)).toFixed(4)), Number((lat + dy * Math.sin(a)).toFixed(4))]; });
        return { type: 'Feature', geometry: { type: 'Polygon', coordinates: [ring] }, properties: { issue_id: i.issue_id, issue_type: i.issue_type, severity: i.severity, neighbourhood_id: i.neighbourhood_id, ward_id: i.ward_id, location_radius_m: r, first_seen_at: i.first_seen_at, last_seen_at: i.last_seen_at, source_category: i.source_category, is_demo: true } };
      }),
    }, null, 2);
    mime = 'application/geo+json';
  }
  const url = URL.createObjectURL(new Blob([content], { type: mime })), a = document.createElement('a');
  a.href = url; a.download = `civiclens-sample-issues.${format}`; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast(`Exported ${rows.length} sample issues`);
}

export function settingsModal() {
  const roles = ['Public', 'Volunteer', 'City Staff'];
  showModal(`${modalHeader('YOUR WORKSPACE', 'Preferences')}<div class="modal-body"><label class="form-label">Demo account type<select id="settings-role">${roles.map(r => `<option ${state.role === r ? 'selected' : ''}>${r}</option>`).join('')}</select></label><div class="setting-row"><div><h3>Local viewing history</h3><p>Remember recently opened issues on this browser.</p></div><input id="history-toggle" type="checkbox" role="switch" aria-label="Enable viewing history" ${state.historyEnabled ? 'checked' : ''}></div><div class="setting-row"><div><h3>Saved issues</h3><p>${state.saved.length} bookmarks stored locally.</p></div><button class="button small" id="clear-saves">Clear saved</button></div><div class="setting-row"><div><h3>Local submissions</h3><p>${state.pending.length} sample submissions. Photos are never stored.</p></div><button class="button small" id="clear-pending">Clear</button></div><p class="fine-print">The account selector previews roles. Authentication, permissions, and cross-device persistence are backend integration points.</p></div><div class="modal-footer"><button class="button primary" data-close>Done</button></div>`, { label: 'Preferences' });
  document.querySelector('#settings-role').onchange = e => { state.role = e.target.value; if (state.view === 'verify' && state.role === 'Public') state.view = 'map'; render(); };
  document.querySelector('#history-toggle').onchange = e => { state.historyEnabled = e.target.checked; persist('historyEnabled', state.historyEnabled); };
  document.querySelector('#clear-saves').onclick = () => { state.saved = []; persist('saved', []); render(); settingsModal(); };
  document.querySelector('#clear-pending').onclick = () => { state.pending = []; persist('pending', []); render(); settingsModal(); };
}

export function helpModal() {
  const steps = [['1', 'Discover', 'Explore issues on the map, or filter and export the same records in Data Explorer.'], ['2', 'Understand', 'Open a pin to inspect evidence, approximate location, how it was located, and nearby infrastructure.'], ['3', 'Verify', 'A volunteer reviews findings before they become reliable public records.']];
  showModal(`${modalHeader('A LITTLE CONTEXT', 'How CivicLens works')}<div class="modal-body help-content"><p>CivicLens brings civic issues from public imagery and community reports into a shared Toronto workspace.</p>${steps.map(([n, t, d]) => `<div class="help-step"><span>${n}</span><div><h3>${t}</h3><p>${d}</p></div></div>`).join('')}<h3>Map controls</h3><p>Drag to pan; scroll, pinch or double-click to zoom; Shift + click to select multiple pins. Focus the map and use arrow keys to pan, + / - to zoom, or Home to return to Toronto. Search suggestions support arrow keys and Enter, and include wards. Fit all matching issues brings filtered results into view. Box select (the dashed square) enables a selection rectangle. A cluster opens a list; choose Zoom in to change the viewport. Pins with a “!” badge are high severity. Escape clears selection.</p><div class="notice-banner">${icon('code')} This is a frontend prototype. Every issue, account, confidence score, geolocation trace and infrastructure relationship is a placeholder. Evidence photos are credited samples that illustrate each category. Map tiles are provided by OpenStreetMap.</div><p class="fine-print">Photos, geolocation, Mapillary, AI analysis, Toronto datasets, 311 context, authentication, and durable submissions require backend integrations.</p></div><div class="modal-footer"><button class="button primary" data-close>Got it</button></div>`, { label: 'How CivicLens works' });
}

export async function shareIssue(i) {
  const url = new URL(location.href);
  url.hash = `map?issue=${i.issue_id}`;
  try { await navigator.clipboard.writeText(url.href); toast('Sample issue link copied'); }
  catch {
    showModal(`${modalHeader('SHARE ISSUE', 'Copy this link')}<div class="modal-body"><input class="share-input" aria-label="Share link" readonly value="${esc(url.href)}"></div>`, { label: 'Share issue' });
    document.querySelector('.share-input').select();
  }
}

export function issueModal(i) {
  remember(i);
  showModal(`<div class="modal-heading"><div><span class="eyebrow">ISSUE DETAILS</span><h2>${esc(i.issue_id)}</h2></div><button class="icon-button" data-close aria-label="Close issue">${icon('close')}</button></div>${detailHtml(i)}<div class="modal-footer"><button class="button" id="modal-save">${icon('bookmark')} ${state.saved.includes(i.issue_id) ? 'Remove saved' : 'Save issue'}</button><button class="button primary" id="modal-on-map">${icon('map')} View on map</button></div>`, { label: `Issue ${i.issue_id}` });
  document.querySelector('#modal-save').onclick = () => { toggleSave([i.issue_id]); closeModal(); };
  document.querySelector('#modal-on-map').onclick = () => { closeModal(); nav('map'); openIssue(i.issue_id); frameIssues([i]); };
}
