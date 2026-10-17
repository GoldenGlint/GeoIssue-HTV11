// Personal workspace pages: Saved, Recents, and the volunteer Verify queue.
import { icon } from '../icons.js';
import { esc, badge, date, typeIcon, typeColor } from '../format.js';
import { state, filtered, findIssue } from '../state.js';
import { emptyHtml, issueRow, toast } from '../ui.js';
import { render } from '../app.js';

const pendingCard = i => `<div class="card pending-card"><div><span class="eyebrow">${esc(i.issue_id)} · LOCAL SUBMISSION${i.created_at ? ` · ${date(i.created_at)}` : ''}</span><h3>${esc(i.category)}</h3><p>${esc(i.description)}</p><p>${esc(i.address)}${i.coordinates ? ` · ${i.coordinates[1].toFixed(3)}, ${i.coordinates[0].toFixed(3)}` : ''}</p></div>${badge('Pending review')}<span class="subtle-label">Privacy processing not connected</span></div>`;

const savedCard = i => `<article class="card saved-card"><div class="saved-card-top">${badge(i.severity)}<button class="icon-button" data-save="${i.issue_id}" aria-label="Toggle saved issue">${icon('bookmark', state.saved.includes(i.issue_id) ? 'saved-icon' : '')}</button></div><button class="saved-card-main" data-issue="${i.issue_id}"><span class="type-orb" style="--type-color:${typeColor(i.issue_type)}">${typeIcon(i.issue_type)}</span><h3>${esc(i.issue_type)}</h3><p>${esc(i.address)}</p><span>${esc(i.neighbourhood_name)} · ${date(i.first_seen_at)}</span></button><div class="saved-card-footer">${badge(i.resolution_status)}<span>${i.issue_id}</span></div></article>`;

export function collectionHtml() {
  const saved = state.view === 'saved', ids = saved ? state.saved : state.recent;
  const visible = new Set(filtered().map(i => i.issue_id));
  const all = ids.map(findIssue).filter(Boolean), issues = all.filter(i => visible.has(i.issue_id)), hidden = all.length - issues.length;
  const submissions = saved && state.pending.length ? `<div class="collection-heading"><h2>Your submissions <span>${state.pending.length}</span></h2><span class="subtle-label">Stored in this browser · waiting for review</span></div><div class="submission-list">${state.pending.map(pendingCard).join('')}</div>` : '';
  const empty = emptyHtml(saved ? 'A place for the issues you care about' : 'Nothing here yet', hidden ? 'Your items are hidden by the current filters. Reset filters to see them.' : saved ? 'Open an issue and choose Save issue. Your bookmarks stay in this browser.' : 'Issues you open will appear here when local history is enabled.');
  return `<div class="collection-page">${submissions}<div class="collection-heading"><h2>${saved ? 'Saved issues' : 'Your recent activity'} <span>${issues.length}</span></h2><div class="collection-actions">${hidden ? `<span class="subtle-label">${hidden} hidden by filters</span><button class="button small" data-action="reset">Reset filters</button>` : ''}${saved ? '' : '<button class="button small" data-action="clear-recents">Clear history</button>'}</div></div>${issues.length ? `<div class="collection-grid">${issues.map(savedCard).join('')}</div>` : empty}</div>`;
}

export function verifyHtml() {
  if (state.role === 'Public') return emptyHtml('Volunteer access required', 'Switch the demo account to Volunteer to preview the review workflow.');
  const queue = state.issues.filter(i => i.verification_status === 'Needs review');
  const review = queue.map(i => `<div class="review-item">${issueRow(i)}<div class="review-actions"><button class="button small" data-review="${i.issue_id}" data-decision="confirm">${icon('check')} Confirm sample</button><button class="button small" data-review="${i.issue_id}" data-decision="dismiss">Dismiss sample</button></div></div>`).join('');
  return `<div class="collection-page"><div class="notice-banner">${icon('shield')} Demo role switcher only. Production access must be enforced by your server.</div><div class="collection-heading"><h2>Awaiting a human review <span>${queue.length + state.pending.length}</span></h2></div>${state.pending.map(pendingCard).join('')}<div class="card review-list">${review || (!state.pending.length ? emptyHtml('You’re all caught up', 'No sample issues are waiting for review.') : '')}</div></div>`;
}

export function bindWorkspace() {
  document.querySelectorAll('[data-review]').forEach(b => b.onclick = () => {
    const i = findIssue(b.dataset.review), confirm = b.dataset.decision === 'confirm';
    i.verification_status = confirm ? 'Verified' : 'Dismissed';
    toast(`Sample ${i.issue_id} ${confirm ? 'verified' : 'dismissed'} for this session`);
    render();
  });
}
