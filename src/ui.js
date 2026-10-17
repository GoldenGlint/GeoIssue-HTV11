// Shared UI pieces: toast, modal shell, issue rows, issue detail and stat cards.
import { icon } from './icons.js';
import { esc, badge, date, typeIcon, typeColor, wardLabel } from './format.js';

let toastTimer, previousFocus, modalCleanup = null;

export function toast(message) {
  const el = document.querySelector('#toast');
  el.textContent = message;
  el.classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('visible'), 4000);
}

/** Opens (or replaces) the modal. `onClose` runs when this content is closed or replaced. */
export function showModal(content, { wide = false, label = 'CivicLens dialog', onClose = null } = {}) {
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
export const modalHeader = (eyebrow, title) => `<div class="modal-heading"><div><span class="eyebrow">${eyebrow}</span><h2>${title}</h2></div><button class="icon-button" data-close aria-label="Close dialog">${icon('close')}</button></div>`;
export const emptyHtml = (title, description) => `<div class="empty-state">${icon('search')}<h3>${title}</h3><p>${description}</p></div>`;

export const issueRow = i => `<button class="issue-row" data-issue="${esc(i.issue_id)}"><span class="type-square" style="color:${typeColor(i.issue_type)}">${typeIcon(i.issue_type)}</span><span class="issue-row-copy"><strong>${esc(i.issue_type)}</strong><span>${esc(i.address)}</span><small>${esc(i.issue_id)} · ${date(i.first_seen_at)} · ${esc(i.verification_status)}</small></span>${badge(i.severity)}${icon('arrow')}</button>`;

/** `extra` is optional markup placed under the note, e.g. a change indicator or sparkline. */
export const statCard = ({ icon: name, label, value, note, color, extra = '' }) => `<div class="stat-card ${color}"><span class="stat-icon">${icon(name)}</span><div><span>${label}</span><strong>${typeof value === 'number' ? value.toLocaleString() : value}</strong><small>${note}</small></div>${extra}</div>`;

function evidenceHtml(i) {
  if (!i.evidence_thumbnail) return `<div class="evidence-placeholder">${icon('image')}<strong>Evidence photo</strong><span>Connect privacy-processed imagery here</span><small>PLACEHOLDER · NO REAL EVIDENCE</small></div>`;
  const c = i.evidence_credit || {};
  const credit = [c.source_url ? `<a href="${esc(c.source_url)}" target="_blank" rel="noopener">${esc(c.title || 'Source')}</a>` : '', esc(c.author), esc(c.license)].filter(Boolean).join(' · ');
  return `<figure class="evidence-photo"><img src="${esc(i.evidence_thumbnail)}" alt="Sample photo of ${esc(i.issue_type.toLowerCase())}, not this exact issue" loading="lazy"><span class="evidence-tag">Sample photo</span><figcaption>Illustrates the category, not this record.${credit ? ` ${credit}` : ''}</figcaption></figure>`;
}

function geoHtml(i) {
  const steps = i.geo_trace || [];
  return `<section class="geo-explainer"><h4>${icon('locate')} How this location was estimated</h4><div class="geo-summary"><strong>${esc(i.geo_method)}</strong><span>${i.location_radius_m}m radius · ${Math.round(i.geo_confidence * 100)}% confidence</span></div>${steps.length ? `<ol class="geo-trace">${steps.map(s => `<li class="${esc(s.status)}"><span></span><div><b>${esc(s.stage)}</b><small>${esc(s.result)}</small></div></li>`).join('')}</ol>` : ''}${i.geo_clues?.length ? `<div class="geo-clues">${i.geo_clues.map(c => `<span>${esc(c)}</span>`).join('')}</div>` : ''}<span class="geo-foot">Illustrative trace · connect the geolocation pipeline for real results</span></section>`;
}

export function detailHtml(i) {
  const facts = [
    ['Neighbourhood', i.neighbourhood_name], ['Ward', wardLabel(i.ward_id)],
    ['First detected', date(i.first_seen_at, { year: 'numeric' })], ['Last seen', date(i.last_seen_at, { year: 'numeric' })],
    ['Detection confidence', `${Math.round(i.detection_confidence * 100)}%`], ['Independent sightings', i.sightings_count],
    ['Nearby infrastructure', i.asset_name], ['Distance to asset', `${i.distance_m.toLocaleString()} metres`],
  ];
  return `<div class="detail-body"><div class="detail-title"><span class="type-orb" style="--type-color:${typeColor(i.issue_type)}">${typeIcon(i.issue_type)}</span><div><span class="eyebrow">${esc(i.issue_id)} · SAMPLE RECORD</span><h2>${esc(i.issue_type)}</h2></div></div>${evidenceHtml(i)}<div class="detail-badges">${badge(i.severity)} ${badge(i.resolution_status)} ${badge(i.verification_status)}</div><h3>${esc(i.address)}</h3><p>${esc(i.description)}</p><div class="confidence-note">${icon('target')}<div><strong>Approximate location · ${i.location_radius_m}m radius</strong><span>Location uncertainty is preserved in the public view.</span></div></div><div class="detail-grid">${facts.map(([label, value]) => `<div><span>${label}</span><strong>${esc(value)}</strong></div>`).join('')}</div>${geoHtml(i)}<div class="analysis-card"><h4>${icon('sun')} Why this was flagged</h4><p>${esc(i.explanation)}</p><span>Illustrative explanation · human review recommended</span></div><p class="fine-print">Source: ${esc(i.source_category)} (sample). No linked 311 record. A detection does not establish a service request.</p></div>`;
}
