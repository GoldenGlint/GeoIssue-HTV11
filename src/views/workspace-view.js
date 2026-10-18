// Personal workspace pages: Saved, Recents, and the volunteer Verify queue.
import { icon } from '../icons.js';
import { esc, badge, date, typeIcon, typeColor, issueName } from '../format.js';
import { state, filtered, findIssue, isSighting, reviewQueue, persist, applyCorrection, isSampleData, sampleWord } from '../state.js';
import { emptyHtml, issueRow, toast, correctionSummary } from '../ui.js';
import { render } from '../app.js';

// Submissions sent without a location get Claude's answer later (src/geolocate.js); say where that stands.
const where = i => {
  const g = i.geolocation;
  if (i.location_status === 'locating') return `${icon('locate')} Claude is finding where this photo was taken…`;
  if (i.location_status === 'not_found') return `${icon('warning')} Location not found${g?.error ? ` (${esc(g.error)})` : ''}. A reviewer needs to place it.`;
  const place = `${esc(i.address)}${i.coordinates ? `${i.address ? ' · ' : ''}${i.coordinates[1].toFixed(3)}, ${i.coordinates[0].toFixed(3)}` : ''}`;
  if (g?.radius_m == null) return place;
  return `${place} · located by Claude, ${g.verified ? `verified by street-level imagery (±${g.radius_m} m)` : `not verified (±${g.radius_m.toLocaleString()} m), so the location needs a check`}`;
};
const pendingCard = i => isSighting(i)
  ? `<div class="card pending-card"><div><span class="eyebrow">${esc(i.issue_id)} · Sighting${i.created_at ? ` · ${date(i.created_at)}` : ''}</span><h3>Added to ${esc(i.joined_issue_id)} · ${esc(i.category)}</h3>${i.description ? `<p>${esc(i.description)}</p>` : ''}<p>${where(i)}</p></div>${badge('Sighting added', 'verified')}<button class="button small" data-issue="${esc(i.joined_issue_id)}">Open issue</button></div>`
  : `<div class="card pending-card"><div><span class="eyebrow">${esc(i.issue_id)} · Local submission${i.created_at ? ` · ${date(i.created_at)}` : ''}</span><h3>${esc(i.category)}${i.severity ? ` · ${esc(i.severity)} severity` : ''}</h3><p>${esc(i.description)}</p><p>${where(i)}</p>${i.ai_suggestion ? `<p class="fine-print">Gemini suggested ${esc(i.ai_suggestion.category)} · ${esc(i.ai_suggestion.severity)} (${Math.round(i.ai_suggestion.confidence * 100)}%)${i.blurred_areas ? ` · ${i.blurred_areas} area${i.blurred_areas === 1 ? '' : 's'} blurred` : ''}</p>` : ''}</div>${badge('Pending review')}<span class="subtle-label">Privacy processing not connected</span></div>`;

/** A suggested correction; reviewers get Accept and Dismiss. */
const correctionCard = (c, review = false) => {
  const issue = findIssue(c.issue_id);
  if (!issue) return '';
  const actions = review ? `<div class="review-actions"><button class="button small" data-correction="${c.correction_id}" data-decision="accept">${icon('check')} Accept</button><button class="button small" data-correction="${c.correction_id}" data-decision="dismiss">Dismiss</button></div>` : badge(c.status);
  return `<div class="card pending-card correction-card"><div><span class="eyebrow">${esc(c.issue_id)} · Correction · ${date(c.created_at)}</span><h3><button class="text-button" data-issue="${esc(c.issue_id)}">${esc(issueName(issue))} · ${esc(issue.address)}</button></h3><p>${esc(correctionSummary(c, issue))}${c.reason ? `: ${esc(c.reason)}` : ''}.</p>${c.note ? `<p class="correction-quote">“${esc(c.note)}”</p>` : ''}</div>${actions}</div>`;
};

const savedCard = i => `<article class="card saved-card"><div class="saved-card-top">${badge(i.severity)}<button class="icon-button" data-save="${i.issue_id}" aria-label="Toggle saved issue">${icon('bookmark', state.saved.includes(i.issue_id) ? 'saved-icon' : '')}</button></div><button class="saved-card-main" data-issue="${i.issue_id}"><span class="type-orb" style="--type-color:${typeColor(i.issue_type)}">${typeIcon(i.issue_type)}</span><h3>${esc(issueName(i))}</h3><p>${esc(i.address)}</p><span>${esc(i.neighbourhood_name)} · ${date(i.first_seen_at)}</span></button><div class="saved-card-footer">${badge(i.resolution_status)}<span>${i.issue_id}</span></div></article>`;

export function collectionHtml() {
  const saved = state.view === 'saved', ids = saved ? state.saved : state.recent;
  const visible = new Set(filtered().map(i => i.issue_id));
  const all = ids.map(findIssue).filter(Boolean), issues = all.filter(i => visible.has(i.issue_id)), hidden = all.length - issues.length;
  const submissions = saved && state.pending.length ? `<div class="collection-heading"><h2>Your submissions <span>${state.pending.length}</span></h2><span class="subtle-label">Stored in this browser · waiting for review</span></div><div class="submission-list">${state.pending.map(pendingCard).join('')}</div>` : '';
  const corrections = saved && state.corrections.length ? `<div class="collection-heading"><h2>Your corrections <span>${state.corrections.length}</span></h2><span class="subtle-label">Stored in this browser</span></div><div class="submission-list">${[...state.corrections].reverse().map(c => correctionCard(c)).join('')}</div>` : '';
  const empty = emptyHtml(saved ? 'A place for the issues you care about' : 'Nothing here yet', hidden ? 'Your items are hidden by the current filters. Reset filters to see them.' : saved ? 'Open an issue and choose Save issue. Your bookmarks stay in this browser.' : 'Issues you open will appear here when local history is enabled.');
  return `<div class="collection-page">${submissions}${corrections}<div class="collection-heading"><h2>${saved ? 'Saved issues' : 'Your recent activity'} <span>${issues.length}</span></h2><div class="collection-actions">${hidden ? `<span class="subtle-label">${hidden} hidden by filters</span><button class="button small" data-action="reset">Reset filters</button>` : ''}${saved ? '' : '<button class="button small" data-action="clear-recents">Clear history</button>'}</div></div>${issues.length ? `<div class="collection-grid">${issues.map(savedCard).join('')}</div>` : empty}</div>`;
}

export function verifyHtml() {
  if (state.role === 'Public') return emptyHtml('Volunteer access required', 'Switch the demo account to Volunteer to preview the review workflow.');
  const queue = state.issues.filter(i => i.verification_status === 'Needs review');
  const corrections = state.corrections.filter(c => c.status === 'Pending review');
  const review = queue.map(i => `<div class="review-item">${issueRow(i)}<div class="review-actions"><button class="button small" data-review="${i.issue_id}" data-decision="confirm">${icon('check')} Confirm${isSampleData() ? ' sample' : ''}</button><button class="button small" data-review="${i.issue_id}" data-decision="dismiss">Dismiss${isSampleData() ? ' sample' : ''}</button></div></div>`).join('');
  const submissions = reviewQueue();
  const correctionList = corrections.length ? `<div class="collection-heading"><h2>Suggested corrections <span>${corrections.length}</span></h2><span class="subtle-label">Accepting updates the issue for everyone</span></div><div class="submission-list">${corrections.map(c => correctionCard(c, true)).join('')}</div>` : '';
  return `<div class="collection-page"><div class="notice-banner">${icon('shield')} Demo role switcher only. Production access must be enforced by your server.</div>${correctionList}<div class="collection-heading"><h2>Awaiting a human review <span>${queue.length + submissions.length}</span></h2></div>${submissions.map(pendingCard).join('')}<div class="card review-list">${review || (!submissions.length ? emptyHtml('You’re all caught up', 'No ${sampleWord()}issues are waiting for review.') : '')}</div></div>`;
}

export function bindWorkspace() {
  document.querySelectorAll('[data-review]').forEach(b => b.onclick = () => {
    const i = findIssue(b.dataset.review), confirm = b.dataset.decision === 'confirm';
    i.verification_status = confirm ? 'Verified' : 'Dismissed';
    toast(`${isSampleData() ? 'Sample ' : ''}${i.issue_id} ${confirm ? 'verified' : 'dismissed'} for this session`);
    render();
  });
  document.querySelectorAll('[data-correction]').forEach(b => b.onclick = () => {
    const c = state.corrections.find(x => x.correction_id === b.dataset.correction), accept = b.dataset.decision === 'accept';
    c.status = accept ? 'Accepted' : 'Dismissed';
    c.reviewed_at = new Date().toISOString();
    if (accept) applyCorrection(c);
    persist('corrections', state.corrections);
    toast(accept ? `Correction accepted. ${c.issue_id} is updated.` : 'Correction dismissed');
    render();
  });
}
