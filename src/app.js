// App shell: sidebar, page header, shared filters, routing, actions and keyboard shortcuts.
// Each page lives in src/views/; dialogs live in src/modals.js.
import { categories, issueRepository, wards, neighbourhoods, TORONTO_CENTER, DEMO_DATE, REFERENCE_DATE, setReferenceDate } from './data.js';
import { icon } from './icons.js';
import { esc, date } from './format.js';
import { state, DEFAULT_FILTERS, filtered, scopedRows, findIssue, persist, areaLabel, applyCorrection, reviewQueue, applyLocalSightings } from './state.js';
import { toast, closeModal } from './ui.js';
import { mapHtml, initMap, destroyMap, getMap, renderPanel, clearSelection, selectMap, openIssue, frameIssues, refreshMapFilters, setMapMode, setHeat, visibleIssues } from './views/map-view.js';
import { dataHtml, bindData } from './views/data-view.js';
import { dashboardHtml, bindDashboard } from './views/dashboard-view.js';
import { collectionHtml, verifyHtml, bindWorkspace } from './views/workspace-view.js';
import { methodologyHtml } from './views/methodology-view.js';
import { uploadModal, infrastructureModal, streetModal, exportModal, settingsModal, helpModal, issueModal, tigerModal } from './modals.js';
import { activeTheme, setTheme } from './theme.js';
import { destroyActivity } from './activity.js';

const app = document.querySelector('#app');
const headings = { map: 'Map Explorer', data: 'Data Explorer', dashboard: 'City overview', saved: 'Saved', recents: 'Recently viewed', verify: 'Verification queue', methodology: 'Methodology' };
const VIEWS = ['map', 'data', 'dashboard', 'saved', 'recents', 'methodology'];

export function themeButtonHtml() {
  const label = activeTheme() === 'light' ? 'Switch to dark theme' : 'Switch to light theme';
  return `<button class="icon-button theme-toggle" data-action="theme" title="${label}" aria-label="${label}">${icon(activeTheme() === 'light' ? 'moon' : 'sun')}</button>`;
}

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
  return `<label class="filter-select">${icon('pin')}<select data-filter="area" aria-label="Area"><option value="">All areas</option><optgroup label="Wards">${Object.entries(wards).map(([id, name]) => option(`ward:${id}`, `Ward ${id} · ${name}`)).join('')}</optgroup><optgroup label="Neighbourhoods">${neighbourhoods.filter(n => used.has(n.id)).map(n => option(n.id, n.name)).join('')}</optgroup></select></label>`;
}
export function filtersHtml() {
  const search = `<label class="search-field">${icon('search')}<input id="global-search" placeholder="Search issues, places or IDs&hellip;" value="${esc(state.filters.query)}" aria-label="Search issues, places, wards or IDs"><kbd>/</kbd></label>`;
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
  return `<div class="filter-context"><div class="filter-status">${filterChips()}</div><div class="context-actions">${infra}<button class="text-button" data-action="proximity">${icon('layers')} Infrastructure & proximity</button><span class="context-divider"></span><span><strong>${filtered().length}</strong> ${state.issues.some(i => i.is_demo) ? 'sample issues' : 'issues'}</span></div></div>`;
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
  const reviewCount = reviewQueue().length + state.corrections.filter(c => c.status === 'Pending review').length + state.issues.filter(i => i.verification_status === 'Needs review').length;
  return `<aside class="sidebar"><a class="brand" href="#map" data-nav="map" aria-label="CivicLens home"><span class="brand-mark"><i></i></span><span>Civic<span class="cyan">Lens</span></span></a><div class="workspace-label">Toronto <span class="live-dot"></span></div><nav aria-label="Main navigation">${navItem('map', 'map', 'Map Explorer')}${navItem('data', 'database', 'Data Explorer')}${navItem('dashboard', 'chart', 'Dashboard')}<div class="nav-divider"></div><span class="nav-section">Your workspace</span>${navItem('saved', 'bookmark', 'Saved', state.saved.length)}${navItem('recents', 'clock', 'Recents')}${state.role !== 'Public' ? navItem('verify', 'shield', 'Verify', reviewCount) : ''}</nav><button class="button primary upload-button" data-action="upload" title="Upload new issue" aria-label="Upload new issue">${icon('plus')}<span>Upload new issue</span></button><div class="sidebar-bottom"><button class="nav-item" data-action="settings" title="Settings" aria-label="Settings">${icon('settings')}<span>Settings</span></button><button class="nav-item ${state.view === 'methodology' ? 'active' : ''}" data-nav="methodology" title="Help and methodology" aria-label="Help and methodology">${icon('help')}<span>Help & methodology</span></button><div class="account"><span class="avatar">JD</span><div><strong>Jamie Davis</strong><select id="role-select" aria-label="Demo account type">${roles.map(r => `<option ${state.role === r ? 'selected' : ''}>${r}</option>`).join('')}</select></div><span class="account-dots">···</span></div></div></aside>`;
}
function pageHtml() {
  switch (state.view) {
    case 'map': return mapHtml();
    case 'data': return dataHtml();
    case 'dashboard': return dashboardHtml();
    case 'verify': return verifyHtml();
    case 'methodology': return methodologyHtml();
    default: return collectionHtml();
  }
}
// Which dataset is showing, with a switch when pipeline output exists (`python -m analysis`).
function dataSourceHtml() {
  const { sample, pipeline, replay } = state.sources;
  if (!pipeline && !replay) return `<span class="data-source">${icon('database')} Sample data · ${sample}</span>`;
  const options = [['sample', 'Sample data', sample], ['pipeline', issueRepository.backend('pipeline').type === 'tiger' ? 'Collected data' : 'File snapshot', pipeline], ['replay', 'Simulated replay', replay]];
  return `<label class="data-source" title="${esc(state.dataBackend.warning || '')}">${icon('database')}<select id="data-source" aria-label="Data shown">${options.filter(([, , count]) => count).map(([value, label, count]) => `<option value="${value}" ${state.dataSource === value ? 'selected' : ''}>${label} · ${count}</option>`).join('')}</select></label>`;
}
function footerHtml() {
  const generated = state.pipeline.report?.generated_at;
  const label = state.dataSource === 'replay' ? 'Simulated replay' : state.dataBackend.type === 'tiger' ? 'Collected data' : 'File snapshot';
  const source = state.dataBackend.warning || (state.dataSource !== 'sample' ? `${label}${generated ? ` · generated ${new Date(generated).toLocaleString('en-CA', { dateStyle: 'medium', timeStyle: 'short' })}` : ''}` : `Fictional sample data · As of ${date(REFERENCE_DATE, { year: 'numeric' })}`);
  return `<footer class="page-footer"><span>CivicLens · Built for a more responsive city</span><span>${source}</span></footer>`;
}
export function render() {
  destroyActivity();
  destroyMap();
  const title = headings[state.view] || headings.map, onMap = state.view === 'map', withFilters = !onMap && state.view !== 'methodology';
  app.innerHTML = `${sidebarHtml()}<main class="main ${onMap ? 'map-page' : ''}"><header class="page-header"><div class="page-title"><h1>${title}</h1></div><div class="header-right">${dataSourceHtml()}${themeButtonHtml()}<button class="icon-button header-settings" data-action="settings" aria-label="Settings">${icon('settings')}</button><button class="icon-button" data-action="help" aria-label="Map controls and help">${icon('help')}</button></div></header>
  ${withFilters ? `<div class="filterbar">${filtersHtml()}</div>${secondaryFilters()}` : ''}
  <div class="workspace-content" id="workspace-content">${pageHtml()}</div>
  ${onMap ? '' : footerHtml()}</main>`;
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
  const source = document.querySelector('#data-source');
  if (source) source.onchange = () => switchDataSource(source.value);
  const search = document.querySelector('#global-search');
  if (search) search.oninput = () => {
    state.filters.query = search.value; state.panel = null;
    const caret = search.selectionStart;
    updateFilteredView();
    const next = document.querySelector('#global-search'); next.focus(); next.setSelectionRange(caret, caret);
  };
  document.querySelector('#role-select').onchange = e => setRole(e.target.value);
  app.querySelectorAll('[data-save]').forEach(b => b.onclick = () => toggleSave([b.dataset.save]));
}
/** Demo role switch. City Staff work from the priority queue, so the table re-sorts by priority for them. */
export function setRole(role) {
  state.role = role;
  if (role === 'City Staff') { state.sort = 'priority_score'; state.direction = -1; }
  if (state.view === 'verify' && role === 'Public') state.view = 'map';
  render();
}
async function loadIssues() {
  state.sources = await issueRepository.sources();
  // Analysed posts are shown when there are any, unless this browser picked a dataset in the header.
  if (!state.sources[state.dataSource]) state.dataSource = state.sources.pipeline ? 'pipeline' : 'sample';
  state.issues = await issueRepository.list(state.dataSource);
  state.dataBackend = issueRepository.backend(state.dataSource);
  const pipeline = state.dataSource !== 'sample';
  [state.pipeline.report, state.pipeline.areas] = pipeline ? [issueRepository.pipelineReport(state.dataSource), issueRepository.areaSummaries(state.dataSource)] : [null, null];
  // Ages and "last N days" count back from when the pipeline ran, so newly scraped posts are never in the future.
  setReferenceDate(state.dataBackend.type === 'tiger' ? new Date().toISOString() : pipeline ? state.pipeline.report?.generated_at || new Date().toISOString() : DEMO_DATE);
  applyLocalSightings();
  // Corrections accepted in this browser stay applied across reloads (an API would return updated issues).
  state.corrections.filter(c => c.status === 'Accepted').forEach(applyCorrection);
}
async function switchDataSource(source) {
  state.dataSource = source; persist('dataSource', source);
  state.selected = []; state.panel = null; state.scope = null; state.page = 1;
  await loadIssues();
  toast(`Showing ${source === 'replay' ? 'simulated replay' : source === 'pipeline' ? 'pipeline output' : 'sample data'}: ${state.issues.length} issues`);
  render();
  frameAnalysed();
}

// Refresh only changed live issue snapshots. Activity has its own lightweight polling lifecycle.
let refreshingIssues = false;
setInterval(async () => {
  if (refreshingIssues || document.hidden || state.dataBackend.type !== 'tiger' || document.querySelector('.modal-backdrop')) return;
  const source = state.dataSource;
  refreshingIssues = true;
  try {
    const before = JSON.stringify(await issueRepository.list(source));
    const snapshot = await issueRepository.refresh(source);
    if (source !== state.dataSource || before === JSON.stringify(snapshot.issues)) return;
    state.issues = structuredClone(snapshot.issues);
    state.sources[source] = snapshot.issues.length;
    state.pipeline = { report: snapshot.report, areas: snapshot.areas };
    setReferenceDate(new Date().toISOString());
    applyLocalSightings();
    state.corrections.filter(c => c.status === 'Accepted').forEach(applyCorrection);
    if (state.view === 'map' && getMap()) refreshMapFilters();
    else render();
  } catch { /* The activity panel reports outages; keep the last loaded map/table intact. */ }
  finally { refreshingIssues = false; }
}, 15000);
// The analysed posts are few and spread across the city, so the map starts with all of them in view. It jumps
// there: the new map's first resize callback would stop an animation.
function frameAnalysed() {
  if (state.dataSource === 'pipeline' && state.view === 'map' && !state.panel && filtered().length) requestAnimationFrame(() => frameIssues(filtered(), 15, 0));
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
    case 'theme': setTheme(activeTheme() === 'light' ? 'dark' : 'light'); app.querySelector('.theme-toggle').outerHTML = themeButtonHtml(); app.querySelector('.theme-toggle').onclick = () => action('theme'); break;
    case 'help': helpModal(); break;
    case 'tiger-info': tigerModal(); break;
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
  if (VIEWS.includes(view)) state.view = view;
  const shared = new URLSearchParams(query || '').get('issue'), record = shared && findIssue(shared);
  if (record) {
    state.view = 'map'; state.panel = null; state.selected = [];
    // A shared link must show its issue even when it falls outside the default time filter.
    if (!filtered().includes(record)) state.filters.days = '';
  }
  render();
  // Frame after the panel or bottom sheet has laid out, so the pin lands in the visible part of the map.
  if (record) { openIssue(record.issue_id); requestAnimationFrame(() => frameIssues([record])); }
}
// Pasted links and manual URL edits; nav() uses replaceState, which doesn't fire this.
window.addEventListener('hashchange', () => { if (state.issues.length) route(); });

// The loading screen in index.html plays once, then fades out when the first view is ready. It waits for its
// own animations rather than a fixed time: they only exist once the page is first painted, which waits for the
// stylesheet and its fonts, and the data can be ready before that.
async function dismissSplash() {
  const splash = document.querySelector('#splash');
  if (!splash) return;
  const firstPaint = new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  await Promise.race([firstPaint, new Promise(resolve => setTimeout(resolve, 3000))]);
  const played = Promise.all(splash.getAnimations({ subtree: true }).map(a => a.finished));
  await Promise.race([played, new Promise(resolve => setTimeout(resolve, 3000))]).catch(() => {});
  splash.classList.add('done');
  setTimeout(() => splash.remove(), 400);
}

// A shared link opens its issue even when that is in the other dataset. The switch isn't remembered.
async function loadSharedIssueDataset() {
  const shared = new URLSearchParams(location.hash.split('?')[1] || '').get('issue');
  const other = state.dataSource === 'pipeline' ? 'sample' : 'pipeline';
  if (!shared || findIssue(shared) || !state.sources[other]) return;
  const previous = state.dataSource;
  state.dataSource = other;
  await loadIssues();
  if (!findIssue(shared)) { state.dataSource = previous; await loadIssues(); }
}

async function start() {
  try {
    await loadIssues();
    await loadSharedIssueDataset();
    route();
    frameAnalysed();
  } catch (error) {
    app.innerHTML = '<div class="load-error"><h1>Couldn’t load the workspace</h1><p>Check your issue repository connection and reload.</p><button onclick="location.reload()">Retry</button></div>';
    console.error(error);
  }
  dismissSplash();
}
start();
