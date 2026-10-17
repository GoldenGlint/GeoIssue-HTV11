// App shell: sidebar, page header, shared filters, routing, actions and keyboard shortcuts.
// Each page lives in src/views/; dialogs live in src/modals.js.
import { categories, issueRepository, wards, neighbourhoods, TORONTO_CENTER } from './data.js';
import { icon } from './icons.js';
import { esc } from './format.js';
import { state, DEFAULT_FILTERS, filtered, scopedRows, findIssue, persist, areaLabel, applyCorrection } from './state.js';
import { toast, closeModal } from './ui.js';
import { mapHtml, initMap, destroyMap, getMap, renderPanel, clearSelection, selectMap, openIssue, frameIssues, refreshMapFilters, setMapMode, setHeat, visibleIssues } from './views/map-view.js';
import { dataHtml, bindData } from './views/data-view.js';
import { dashboardHtml, bindDashboard } from './views/dashboard-view.js';
import { collectionHtml, verifyHtml, bindWorkspace } from './views/workspace-view.js';
import { uploadModal, infrastructureModal, streetModal, exportModal, settingsModal, helpModal, issueModal } from './modals.js';

const app = document.querySelector('#app');
const headings = { map: 'Map Explorer', data: 'Data Explorer', dashboard: 'City overview', saved: 'Saved', recents: 'Recently viewed', verify: 'Verification queue' };

// ---- Shared filters ----
const filterLabels = { query: 'Search', type: 'Issue type', severity: 'Severity', status: 'Status', area: 'Area', days: 'Time' };
function filterChips() {
  return Object.entries(filterLabels).filter(([key]) => key === 'days' ? state.filters.days !== DEFAULT_FILTERS.days : !!state.filters[key]).map(([key, label]) => {
    const value = key === 'days' ? (state.filters.days ? `Last ${state.filters.days} days` : 'Any time') : key === 'area' ? areaLabel(state.filters.area) : state.filters[key];
    return `<button class="filter-chip" data-clear-filter="${key}" aria-label="Remove ${label.toLowerCase()} filter" title="Clear ${label.toLowerCase()}: ${esc(value)}"><span>${esc(value)}</span>${icon('close')}</button>`;
  }).join('');
}
export function bindFilterChips(root = app) {
  root.querySelectorAll('[data-clear-filter]').forEach(b => b.onclick = () => { state.filters[b.dataset.clearFilter] = DEFAULT_FILTERS[b.dataset.clearFilter]; updateFilteredView(); });
}
function selectHtml(key, label, values, glyph) {
  const options = values.map(v => { const [value, text] = Array.isArray(v) ? v : [v, v]; return `<option value="${esc(value)}" ${state.filters[key] === String(value) ? 'selected' : ''}>${esc(text)}</option>`; }).join('');
  return `<label class="filter-select">${icon(glyph)}<select data-filter="${key}" aria-label="${label}"><option value="">${label}</option>${options}</select></label>`;
}
function areaSelectHtml() {
  const used = new Set(state.issues.map(i => i.neighbourhood_id));
  const option = (value, text) => `<option value="${esc(value)}" ${state.filters.area === value ? 'selected' : ''}>${esc(text)}</option>`;
  return `<label class="filter-select">${icon('pin')}<select data-filter="area" aria-label="Area"><option value="">All areas (Toronto)</option><optgroup label="Wards">${Object.entries(wards).map(([id, name]) => option(`ward:${id}`, `Ward ${id} · ${name}`)).join('')}</optgroup><optgroup label="Neighbourhoods">${neighbourhoods.filter(n => used.has(n.id)).map(n => option(n.id, n.name)).join('')}</optgroup></select></label>`;
}
export function filtersHtml() {
  const search = `<label class="search-field">${icon('search')}<input id="global-search" placeholder="Search issues, places, wards or IDs&hellip;" value="${esc(state.filters.query)}" aria-label="Search issues, places, wards or IDs"><kbd>/</kbd></label>`;
  const filters = selectHtml('type', 'All issue types', Object.keys(categories), 'filter')
    + selectHtml('severity', 'All severities', ['High', 'Medium', 'Low'], 'warning')
    + selectHtml('status', 'All statuses', ['Open', 'In review', 'Resolved'], 'check')
    + selectHtml('days', 'Any time', [[7, 'Last 7 days'], [30, 'Last 30 days'], [90, 'Last 90 days']], 'clock')
    + areaSelectHtml();
  const reset = `<button class="reset-button" data-action="reset" title="Reset all filters">${icon('refresh')}<span>Reset</span></button>`;
  return state.view === 'map' ? `<div class="map-search-row">${search}${reset}</div><div class="map-filter-row">${filters}</div>` : `${search}<div class="filter-selects">${filters}</div>${reset}`;
}
export function secondaryFilters() {
  const infra = state.filters.infra ? `<span class="scope-chip">${state.filters.infra === 'any' ? 'Any infrastructure' : esc(state.filters.infra)} · within ${state.filters.radius}m <button data-action="clear-infra" aria-label="Clear infrastructure filter">×</button></span>` : '';
  return `<div class="filter-context"><div class="filter-status">${filterChips()}</div><div class="context-actions">${infra}<button class="text-button" data-action="proximity">${icon('layers')} Infrastructure & proximity</button><span class="context-divider"></span><span><strong>${filtered().length}</strong> sample issues</span></div></div>`;
}
export function updateFilteredView() {
  state.page = 1; state.selected = [];
  if (state.view === 'map' && getMap()) refreshMapFilters();
  else render();
}

// ---- Rendering and navigation ----
function navItem(view, glyph, title, count) {
  const active = state.view === view;
  return `<button class="nav-item ${active ? 'active' : ''}" data-nav="${view}" title="${title}" aria-label="${title}" ${active ? 'aria-current="page"' : ''}>${icon(glyph)}<span>${title}</span>${count ? `<span class="nav-count">${count}</span>` : ''}</button>`;
}
function sidebarHtml() {
  const roles = ['Public', 'Volunteer', 'City Staff'];
  const reviewCount = state.pending.length + state.corrections.filter(c => c.status === 'Pending review').length + state.issues.filter(i => i.verification_status === 'Needs review').length;
  return `<aside class="sidebar"><a class="brand" href="#map" data-nav="map" aria-label="CivicLens home"><span class="brand-mark"><i></i></span><span>Civic<span class="cyan">Lens</span></span></a><div class="workspace-label">TORONTO WORKSPACE <span class="live-dot"></span></div><nav aria-label="Main navigation">${navItem('map', 'map', 'Map Explorer')}${navItem('data', 'database', 'Data Explorer')}${navItem('dashboard', 'chart', 'Dashboard')}<div class="nav-divider"></div><span class="nav-section">YOUR WORKSPACE</span>${navItem('saved', 'bookmark', 'Saved', state.saved.length)}${navItem('recents', 'clock', 'Recents')}${state.role !== 'Public' ? navItem('verify', 'shield', 'Verify', reviewCount) : ''}</nav><button class="button primary upload-button" data-action="upload" title="Upload new issue" aria-label="Upload new issue">${icon('plus')}<span>Upload new issue</span></button><div class="sidebar-note">Small observations.<br><strong>Better neighbourhoods.</strong><span>A little attention goes a long way.</span></div><div class="sidebar-bottom"><button class="nav-item" data-action="settings" title="Settings" aria-label="Settings">${icon('settings')}<span>Settings</span></button><button class="nav-item" data-action="help" title="Help and methodology" aria-label="Help and methodology">${icon('help')}<span>Help & methodology</span></button><div class="account"><span class="avatar">JD</span><div><strong>Jamie Davis</strong><select id="role-select" aria-label="Demo account type">${roles.map(r => `<option ${state.role === r ? 'selected' : ''}>${r}</option>`).join('')}</select></div><span class="account-dots">···</span></div></div></aside>`;
}
function pageHtml() {
  switch (state.view) {
    case 'map': return mapHtml();
    case 'data': return dataHtml();
    case 'dashboard': return dashboardHtml();
    case 'verify': return verifyHtml();
    default: return collectionHtml();
  }
}
export function render() {
  destroyMap();
  const title = headings[state.view] || headings.map, onMap = state.view === 'map';
  const sample = state.issues.some(i => i.is_demo);
  const source = `<span class="data-source" title="${sample ? 'Fictional records for the demo. None of them are real reports.' : 'Issues from the analysis pipeline.'}">${sample ? 'Sample data' : 'Analysis data'}</span>`;
  app.innerHTML = `${sidebarHtml()}<main class="main ${onMap ? 'map-page' : ''}"><header class="page-header"><div class="page-title"><h1>${title}</h1>${source}</div><div class="header-right"><button class="icon-button header-settings" data-action="settings" aria-label="Settings">${icon('settings')}</button><button class="icon-button" data-action="help" aria-label="About this demo">${icon('help')}</button></div></header>
  ${onMap ? '' : `<div class="filterbar">${filtersHtml()}</div>${secondaryFilters()}`}
  <div class="workspace-content" id="workspace-content">${pageHtml()}</div>
  ${onMap ? '' : '<footer class="page-footer"><span>CivicLens · Built for a more responsive city</span><span>Fictional sample data · Snapshot: Oct 17, 2026</span></footer>'}</main>`;
  bindShell();
  if (onMap) initMap();
  if (state.view === 'data') bindData();
  if (state.view === 'dashboard') bindDashboard();
  if (state.view === 'verify') bindWorkspace();
  bindIssueLinks(app);
}
export function nav(view) {
  state.view = view; state.page = 1; state.panel = null; state.selected = [];
  if (view === 'data') state.scope = null;
  history.replaceState(null, '', `#${view}`);
  render(); window.scrollTo(0, 0);
}
export function scopedTable(ids) {
  state.scope = [...ids]; state.view = 'data'; state.dataTab = 'records'; state.panel = null; state.page = 1;
  history.replaceState(null, '', '#data');
  render();
}
export function toggleSave(ids) {
  const all = ids.every(id => state.saved.includes(id));
  state.saved = all ? state.saved.filter(id => !ids.includes(id)) : [...new Set([...state.saved, ...ids])];
  persist('saved', state.saved);
  toast(all ? 'Removed from saved issues' : 'Saved to this browser');
  if (state.view !== 'map' || !getMap()) { render(); return; }
  // On the map, refresh only the panel and the sidebar count so the camera and scroll stay put.
  const detailScroll = document.querySelector('.detail-body')?.scrollTop || 0, listScroll = document.querySelector('#panel-results')?.scrollTop || 0;
  renderPanel();
  const detail = document.querySelector('.detail-body'); if (detail) detail.scrollTop = detailScroll;
  const list = document.querySelector('#panel-results'); if (list) list.scrollTop = listScroll;
  const savedNav = document.querySelector('[data-nav="saved"]');
  savedNav.querySelector('.nav-count')?.remove();
  if (state.saved.length) { const count = document.createElement('span'); count.className = 'nav-count'; count.textContent = state.saved.length; savedNav.append(count); }
}

function bindShell() {
  bindFilterChips();
  app.querySelectorAll('[data-nav]').forEach(b => b.onclick = e => { e.preventDefault(); nav(b.dataset.nav); });
  app.querySelectorAll('[data-action]').forEach(b => b.onclick = () => action(b.dataset.action));
  app.querySelectorAll('[data-filter]').forEach(el => el.onchange = () => { state.filters[el.dataset.filter] = el.value; updateFilteredView(); });
  const search = document.querySelector('#global-search');
  search.oninput = () => {
    state.filters.query = search.value; state.panel = null;
    const caret = search.selectionStart;
    updateFilteredView();
    const next = document.querySelector('#global-search'); next.focus(); next.setSelectionRange(caret, caret);
  };
  document.querySelector('#role-select').onchange = e => { state.role = e.target.value; if (state.view === 'verify' && state.role === 'Public') state.view = 'map'; render(); };
  app.querySelectorAll('[data-save]').forEach(b => b.onclick = () => toggleSave([b.dataset.save]));
}
function bindIssueLinks(root) {
  root.querySelectorAll('[data-issue]').forEach(b => b.onclick = () => {
    if (state.view === 'map') openIssue(b.dataset.issue);
    else issueModal(findIssue(b.dataset.issue));
  });
}

export function action(name) {
  const map = getMap();
  switch (name) {
    case 'upload': uploadModal(); break;
    case 'reset': state.filters = { ...DEFAULT_FILTERS }; state.scope = null; state.panel = null; updateFilteredView(); break;
    case 'clear-infra': state.filters.infra = ''; updateFilteredView(); break;
    case 'proximity': case 'layers': infrastructureModal(); break;
    case 'pan': case 'box': setMapMode(name); break;
    case 'pins': case 'heat': setHeat(name === 'heat'); break;
    case 'zoom-in': map?.setZoom(Math.round(map.targetZoom ?? map.zoom) + 1); break;
    case 'zoom-out': map?.setZoom(Math.round(map.targetZoom ?? map.zoom) - 1); break;
    case 'fit-results': frameIssues(filtered()); break;
    case 'center': map?.flyTo(TORONTO_CENTER, 13); break;
    case 'search-area': { const visible = visibleIssues(); if (visible.length) selectMap(visible.map(i => i.issue_id), 'multi'); else toast('No matching issues in this view. Use Fit all matching issues.'); break; }
    case 'street': streetModal(); break;
    case 'clear-scope': state.scope = null; state.page = 1; render(); break;
    case 'clear-table-selection': state.selected = []; render(); break;
    case 'save-table-selection': toggleSave(state.selected); break;
    case 'export-selected': exportModal('selected'); break;
    case 'table-map': {
      const ids = state.selected.length ? state.selected : scopedRows().map(i => i.issue_id);
      nav('map'); selectMap(ids, 'multi'); frameIssues(state.issues.filter(i => ids.includes(i.issue_id)));
      break;
    }
    case 'export': exportModal(); break;
    case 'clear-recents': state.recent = []; persist('recent', []); render(); break;
    case 'settings': settingsModal(); break;
    case 'help': helpModal(); break;
  }
}

document.addEventListener('keydown', e => {
  const modal = document.querySelector('.modal');
  if (e.key === 'Escape') {
    if (modal) closeModal();
    else if (state.view === 'map') clearSelection();
    // Elsewhere, Escape clears the table selection and redraws so the UI matches the state.
    else if (state.selected.length) { state.selected = []; render(); }
  }
  if (e.key === '/' && !modal && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) { e.preventDefault(); document.querySelector('#global-search')?.focus(); }
  if (e.key === 'Tab' && modal) {
    const els = [...modal.querySelectorAll('button,input,textarea,select,a[href]')].filter(el => !el.disabled && el.offsetParent !== null), first = els[0], last = els.at(-1);
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
  }
});

function route() {
  const [view, query] = location.hash.slice(1).split('?');
  if (['map', 'data', 'dashboard', 'saved', 'recents'].includes(view)) state.view = view;
  const shared = new URLSearchParams(query || '').get('issue'), record = shared && findIssue(shared);
  if (record) {
    state.view = 'map'; state.panel = null; state.selected = [];
    // A shared link must show its issue even when it falls outside the default time filter.
    if (!filtered().includes(record)) state.filters.days = '';
  }
  render();
  if (record) { openIssue(record.issue_id); frameIssues([record]); }
}
// Pasted links and manual URL edits; nav() uses replaceState, which doesn't fire this.
window.addEventListener('hashchange', () => { if (state.issues.length) route(); });

async function start() {
  try {
    state.issues = await issueRepository.list();
    // Corrections accepted in this browser stay applied across reloads (an API would return updated issues).
    state.corrections.filter(c => c.status === 'Accepted').forEach(applyCorrection);
    route();
  } catch (error) {
    app.innerHTML = '<div class="load-error"><h1>Couldn’t load the workspace</h1><p>Check your issue repository connection and reload.</p><button onclick="location.reload()">Retry</button></div>';
    console.error(error);
  }
}
start();
