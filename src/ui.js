// Shared UI pieces: toast, modal shell, issue rows, issue detail and stat cards.
import { icon } from './icons.js';
import { esc, badge, date, typeIcon, typeColor, wardLabel, safeUrl, issueName } from './format.js';
import { googleStreetViewUrl, distanceMetres } from './coordinates.js';
import { pendingCorrection, findIssue } from './state.js';

let toastTimer, previousFocus, modalCleanup = null;

export function toast(message) {
  const el = document.querySelector('#toast');
  el.textContent = message;
  el.classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('visible'), 4000);
}

/** Opens (or replaces) the modal. `onClose` runs when this content is closed or replaced. */
export function showModal(content, { wide = false, label = 'GeoIssue dialog', onClose = null } = {}) {
  runModalCleanup();
  document.body.style.overflow = 'hidden';
  const root = document.querySelector('#modal-root');
  if (!root.children.length) previousFocus = document.activeElement;
  root.innerHTML = `<div class="modal-backdrop"><section class="modal ${wide ? 'wide' : ''}" role="dialog" aria-modal="true" aria-label="${esc(label)}" tabindex="-1">${content}</section></div>`;
  modalCleanup = onClose;
  root.querySelectorAll('[data-close]').forEach(b => b.onclick = closeModal);
  root.querySelector('.modal-backdrop').onclick = e => { if (e.target.classList.contains('modal-backdrop')) closeModal(); };
  root.querySelector('button,input,select,textarea')?.focus();
}
function runModalCleanup() { const cleanup = modalCleanup; modalCleanup = null; cleanup?.(); }
export function closeModal() {
  runModalCleanup();
  document.body.style.overflow = '';
  document.querySelector('#modal-root').replaceChildren();
  if (previousFocus?.isConnected) previousFocus.focus();
}
export const modalHeader = (eyebrow, title) => `<div class="modal-heading"><div><h2>${title}</h2>${eyebrow ? `<span class="eyebrow">${eyebrow}</span>` : ''}</div><button class="icon-button" data-close aria-label="Close dialog">${icon('close')}</button></div>`;
export const emptyHtml = (title, description) => `<div class="empty-state">${icon('search')}<h3>${title}</h3><p>${description}</p></div>`;

export const issueRow = i => `<button class="issue-row" data-issue="${esc(i.issue_id)}"><span class="type-square" style="color:${typeColor(i.issue_type)}">${typeIcon(i.issue_type)}</span><span class="issue-row-copy"><strong>${esc(issueName(i))}</strong><span>${esc(i.address)}</span><small>${esc(i.issue_id)} · ${date(i.first_seen_at)} · ${esc(i.verification_status)}</small></span>${badge(i.severity)}${icon('arrow')}</button>`;

/** `extra` is optional markup placed under the note, e.g. a change indicator or sparkline. */
export const statCard = ({ label, value, note, color, extra = '' }) => `<div class="stat-card ${color}"><div><span>${label}</span><strong>${typeof value === 'number' ? value.toLocaleString() : value}</strong><small>${note}</small></div>${extra}</div>`;

function evidencePhotos(i) {
  const photos = i.evidence_photos?.length ? i.evidence_photos : i.evidence_thumbnail ? [{ url: i.evidence_thumbnail, role: 'evidence' }] : [];
  return photos.map(p => ({ ...p, url: safeUrl(p.url) })).filter(p => p.url);
}
function sourceLinks(i) {
  const urls = (i.source_posts || []).map(safeUrl).filter(Boolean);
  return urls.map((url, j) => `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${icon('external')} ${urls.length === 1 ? 'View original post' : `View source post ${j + 1}`}</a>`).join('');
}
function photoCredit(i) {
  const c = i.evidence_credit || {}, source = safeUrl(c.source_url);
  return [source ? `<a href="${esc(source)}" target="_blank" rel="noopener">${esc(c.title || 'Source')}</a>` : '', esc(c.author), esc(c.license)].filter(Boolean).join(' · ');
}
function evidenceHtml(i, index = 0) {
  if (!i.evidence_thumbnail && i.evidence_withheld) return `<div class="evidence-placeholder">${icon('shield')}<strong>Photo withheld</strong><span>${esc(i.evidence_withheld)}</span></div>`;
  const photos = evidencePhotos(i), photo = photos[index];
  if (!photo) return `<div class="evidence-placeholder">${icon('image')}<strong>Evidence photo</strong><span>No photo is available for this issue</span><small>Placeholder, not real evidence</small>${sourceLinks(i)}</div>`;
  const credit = photoCredit(i), sample = i.is_demo || i.evidence_credit?.is_sample, context = photo.role === 'context';
  const label = sample ? 'Sample photo' : context ? 'Context photo' : 'Evidence';
  const blurred = i.evidence_blurred && index === 0 ? `<span class="evidence-tag blurred">${icon('shield')} Faces and plates blurred</span>` : '';
  const note = sample ? 'Illustrates the category, not this record.' : context ? 'Another view from a source post; not independently confirmed as this issue.' : 'Photo from the report.';
  const thumbs = photos.length > 1 ? `<div class="evidence-thumbs" aria-label="Photos from source posts">${photos.map((p, n) => `<button data-evidence-id="${esc(i.issue_id)}" data-photo-select="${n}" aria-label="Show photo ${n + 1} of ${photos.length}" aria-pressed="${n === index}"><img src="${esc(p.url)}" alt="" loading="lazy"><span>${n + 1}</span></button>`).join('')}</div>` : '';
  return `<figure class="evidence-photo"><button class="evidence-open" data-evidence-id="${esc(i.issue_id)}" data-photo-open="${index}" aria-label="View full photo ${index + 1} of ${photos.length}"><img src="${esc(photo.url)}" alt="${label}: ${esc(issueName(i))}" loading="lazy"><span class="evidence-tag">${label}</span>${blurred}<span class="photo-expand">${icon('fit')} Enlarge</span></button>${thumbs}<figcaption><span class="evidence-count">Photo ${index + 1} of ${photos.length}</span> ${note}${credit ? ` ${credit}` : ''}<div class="evidence-links">${sourceLinks(i)}</div></figcaption></figure>`;
}

export function bindEvidence(root) {
  root.querySelectorAll('[data-photo-open],[data-photo-select]').forEach(button => {
    button.onclick = () => {
      const issue = findIssue(button.dataset.evidenceId);
      if (!issue) return;
      if (button.dataset.photoOpen != null) return openPhotoViewer(issue, Number(button.dataset.photoOpen));
      const index = Number(button.dataset.photoSelect), gallery = button.closest('.evidence-photo'), parent = gallery.parentElement;
      gallery.outerHTML = evidenceHtml(issue, index);
      bindEvidence(parent);
      parent.querySelector(`[data-photo-select="${index}"]`)?.focus();
    };
  });
}

function openPhotoViewer(issue, index) {
  const photos = evidencePhotos(issue), dialog = document.createElement('dialog');
  const overflow = document.body.style.overflow;
  dialog.className = 'photo-viewer';
  dialog.setAttribute('aria-label', 'Photo viewer');
  dialog.innerHTML = `<header><div><h2>${esc(issueName(issue))}</h2><span class="viewer-count" aria-live="polite"></span></div><button class="icon-button" data-viewer-close aria-label="Close photo viewer" autofocus>${icon('close')}</button></header><div class="viewer-stage"><button class="icon-button" data-viewer-prev aria-label="Previous photo">${icon('back')}</button><img class="viewer-image" alt=""><button class="icon-button" data-viewer-next aria-label="Next photo">${icon('arrow')}</button></div><footer><p class="viewer-note"></p><div class="viewer-credit">${photoCredit(issue)}</div><div class="viewer-links">${sourceLinks(issue)}<a data-viewer-original target="_blank" rel="noopener">${icon('external')} Open image in new tab</a></div></footer>`;
  const draw = () => {
    const photo = photos[index], context = photo.role === 'context', sample = issue.is_demo || issue.evidence_credit?.is_sample;
    const image = dialog.querySelector('.viewer-image');
    image.src = photo.url;
    image.alt = `${sample ? 'Sample' : context ? 'Context' : 'Evidence'} photo ${index + 1} of ${photos.length}: ${issueName(issue)}`;
    dialog.querySelector('.viewer-count').textContent = `Photo ${index + 1} of ${photos.length}`;
    dialog.querySelector('.viewer-note').textContent = sample ? 'Sample photo; does not depict this issue.' : context ? 'Context from a source post; not independently confirmed as this issue.' : 'Evidence photo from the report.';
    dialog.querySelector('[data-viewer-original]').href = photo.url;
  };
  const move = delta => { index = (index + delta + photos.length) % photos.length; draw(); };
  dialog.querySelector('[data-viewer-close]').onclick = () => dialog.close();
  dialog.querySelector('[data-viewer-prev]').onclick = () => move(-1);
  dialog.querySelector('[data-viewer-next]').onclick = () => move(1);
  dialog.querySelectorAll('[data-viewer-prev],[data-viewer-next]').forEach(b => { b.hidden = photos.length < 2; });
  dialog.onkeydown = e => {
    e.stopPropagation(); // Keep Escape and Tab inside this native dialog, including over an issue modal.
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); move(e.key === 'ArrowLeft' ? -1 : 1); }
  };
  dialog.onclose = () => { dialog.remove(); document.body.style.overflow = overflow; };
  draw();
  document.body.append(dialog);
  document.body.style.overflow = 'hidden';
  dialog.showModal();
}

// Why this issue ranks where it does in the staff queue (score and reasons come from src/priority.js or the pipeline).
export const priorityLevel = score => score >= 60 ? 'high' : score >= 35 ? 'medium' : 'low';
function priorityHtml(i) {
  if (i.priority_score == null) return '';
  return `<section class="priority-card ${priorityLevel(i.priority_score)}"><div class="priority-score"><strong>${i.priority_score}</strong><span>of 100</span></div><div><h4>Priority for City staff</h4><ul>${(i.priority_reasons || []).map(r => `<li>${esc(r)}</li>`).join('')}</ul></div></section>`;
}

function geoHtml(i) {
  const steps = i.geo_trace || [];
  return `<section class="geo-explainer"><h4>${icon('locate')} How this location was estimated</h4><div class="geo-summary"><strong>${esc(i.geo_method)}</strong><span>${i.location_radius_m}m radius · ${Math.round(i.geo_confidence * 100)}% confidence</span></div>${steps.length ? `<ol class="geo-trace">${steps.map(s => `<li class="${esc(s.status)}"><span></span><div><b>${esc(s.stage)}</b><small>${esc(s.result)}</small></div></li>`).join('')}</ol>` : ''}${i.geo_clues?.length ? `<div class="geo-clues">${i.geo_clues.map(c => `<span>${esc(c)}</span>`).join('')}</div>` : ''}${i.is_demo ? '<span class="geo-foot">Illustrative trace · connect the geolocation pipeline for real results</span>' : ''}</section>`;
}

export function correctionSummary(c, issue) {
  if (c.kind === 'location') return `New location ${Math.round(distanceMetres(issue.geometry.coordinates, c.coordinates)).toLocaleString()} m from this pin`;
  if (c.kind === 'issue_type') return `Issue type should be ${c.issue_type}`;
  return c.kind === 'resolved' ? 'Reported as fixed' : 'Reported as not a public issue';
}

function locationHtml(i) {
  const correction = pendingCorrection(i.issue_id);
  return `<div class="confidence-note">${icon('target')}<div><strong>Approximate location · ${i.location_radius_m} m radius</strong><span>The pin may be off by up to this distance.</span><a class="street-link" href="${googleStreetViewUrl(i.geometry.coordinates)}" target="_blank" rel="noopener">${icon('external')} Open in Google Street View</a></div></div>${correction ? `<div class="correction-note">${icon('edit')}<div><strong>You suggested a correction</strong><span>${esc(correctionSummary(correction, i))}. A reviewer will check it.</span></div></div>` : ''}`;
}

export function detailHtml(i) {
  const facts = [
    ['Neighbourhood', i.neighbourhood_name], ['Ward', wardLabel(i.ward_id)],
    ['First detected', date(i.first_seen_at, { year: 'numeric' })], ['Last seen', date(i.last_seen_at, { year: 'numeric' })],
    ['Detection confidence', `${Math.round(i.detection_confidence * 100)}%`], ['Independent sightings', i.sightings_count],
    ['Nearby infrastructure', i.asset_name || 'Not determined'], ['Distance to asset', i.distance_m == null ? 'Not determined' : `${i.distance_m.toLocaleString()} metres`],
  ];
  return `<div class="detail-body"><div class="detail-title"><span class="type-orb" style="--type-color:${typeColor(i.issue_type)}">${typeIcon(i.issue_type)}</span><div><h2>${esc(issueName(i))}</h2><span class="eyebrow">${esc(i.issue_id)}${i.is_demo ? ' · Sample record' : ''}${i.title ? ` · ${esc(i.issue_type)}` : ''}</span></div></div>${evidenceHtml(i)}<div class="detail-badges">${badge(i.severity)} ${badge(i.resolution_status)} ${badge(i.verification_status)}</div><h3>${esc(i.address)}</h3><p>${esc(i.description)}</p>${locationHtml(i)}${priorityHtml(i)}<div class="detail-grid">${facts.map(([label, value]) => `<div><span>${label}</span><strong>${esc(value)}</strong></div>`).join('')}</div>${geoHtml(i)}<div class="analysis-card"><h4>${icon('sun')} Why this was flagged</h4><p>${esc(i.explanation)}</p><span>${i.is_demo ? 'Illustrative explanation · ' : ''}human review recommended</span></div><p class="fine-print">Source: ${esc(i.source_category)}${i.is_demo ? ' (sample)' : ''}. No linked 311 record. A detection does not establish a service request.</p></div>`;
}
