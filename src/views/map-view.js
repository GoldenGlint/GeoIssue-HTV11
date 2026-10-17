// Map Explorer: the map canvas, floating controls, and the selection-driven right panel.
import { CivicMap } from '../map.js';
import { attachSearch } from '../search.js';
import { categories, infrastructure, TORONTO_CENTER } from '../data.js';
import { icon } from '../icons.js';
import { typeIcon, typeColor } from '../format.js';
import { searchSuggestions } from '../issues.js';
import { state, filtered, findIssue, remember } from '../state.js';
import { toast, detailHtml, issueRow, emptyHtml } from '../ui.js';
import { action, filtersHtml, secondaryFilters, bindFilterChips, updateFilteredView, scopedTable, toggleSave } from '../app.js';
import { shareIssue, streetModal } from '../modals.js';

let map = null;
export const getMap = () => map;
const isMobile = () => matchMedia('(max-width:650px)').matches;
const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

export function destroyMap() {
  if (!map) return;
  state.center = map.center; state.zoom = map.zoom;
  map.destroy(); map = null;
}

/** Screen space covered by floating controls and the open panel, in pixels. */
export function mapPadding() {
  const mobile = isMobile();
  return {
    top: state.panel && mobile ? 105 : 165,
    right: state.panel && !mobile ? (document.querySelector('#issue-panel')?.offsetWidth || 360) + 45 : 45,
    bottom: state.panel && mobile ? map.element.clientHeight * .58 + 25 : 115,
    left: 45,
  };
}
export function frameIssues(issues, maxZoom = 15) {
  if (!issues.length) { toast('No matching issues to frame.'); return; }
  map?.fitTo(issues.map(i => i.geometry.coordinates), mapPadding(), maxZoom);
}
const inView = issue => { const [x, y] = map.position(issue.geometry.coordinates); return x >= 0 && y >= 0 && x <= map.element.clientWidth && y <= map.element.clientHeight; };
export const visibleIssues = () => filtered().filter(inView);

export function updateMapMeta() {
  if (!map) return;
  const rows = filtered(), visible = rows.filter(inView);
  const count = document.querySelector('.map-visible-count'); if (count) count.textContent = `${visible.length} in view`;
  const hint = document.querySelector('.map-summary .muted'); if (hint) hint.textContent = `/ ${rows.length} matching`;
  const empty = document.querySelector('.map-empty');
  if (empty) {
    const button = empty.querySelector('button');
    empty.hidden = visible.length > 0 || !!state.panel;
    empty.querySelector('h3').textContent = rows.length ? 'Your matches are outside this view' : 'No matching sample issues';
    empty.querySelector('p').textContent = rows.length ? `${rows.length} issues match your filters. Bring them into view.` : 'Try a different search or remove a filter.';
    button.dataset.action = rows.length ? 'fit-results' : 'reset';
    button.textContent = rows.length ? 'Show matching issues' : 'Reset filters';
    button.onclick = () => action(button.dataset.action);
  }
  document.querySelector('[data-action="zoom-in"]')?.toggleAttribute('disabled', map.zoom >= 18);
  document.querySelector('[data-action="zoom-out"]')?.toggleAttribute('disabled', map.zoom <= 10);
}

// Keeps the chosen pin clear of the panel or bottom sheet that just opened over it.
const reveal = issue => { if (map && issue) map.ensureVisible(issue.geometry.coordinates, mapPadding()); };

export function openIssue(id, back = null) {
  const issue = findIssue(id);
  if (!issue) return;
  remember(issue);
  state.panel = { mode: 'issue', id, back };
  if (!state.selected.includes(id)) state.selected = [id];
  renderPanel(); map?.setData(filtered(), state.selected); updateMapMeta();
  reveal(issue);
}
export function selectMap(ids, mode, e) {
  if (e?.shiftKey) {
    for (const id of ids) state.selected = state.selected.includes(id) ? state.selected.filter(x => x !== id) : [...state.selected, id];
    state.panel = state.selected.length ? { mode: 'multi', ids: [...state.selected] } : null;
  } else {
    state.selected = ids;
    state.panel = ids.length ? mode === 'issue' ? { mode, id: ids[0] } : { mode, ids } : null;
    if (mode === 'issue') remember(findIssue(ids[0]));
  }
  renderPanel(); map?.setData(filtered(), state.selected); updateMapMeta();
  if (state.panel?.mode === 'issue') reveal(findIssue(state.panel.id));
}
export function clearSelection() {
  state.selected = []; state.panel = null;
  renderPanel(); map?.setData(filtered(), []); updateMapMeta();
}

export function mapHtml() {
  const legend = Object.entries(categories).map(([type, c]) => `<button data-legend="${type}" class="${state.filters.type === type ? 'legend-active' : ''}"><span style="color:${c.color}">${typeIcon(type)}</span>${type}</button>`).join('');
  const hint = state.mapMode === 'box' ? 'Drag a rectangle to select issues' : 'Drag to pan · Scroll to zoom · Shift + click to select';
  return `<div class="map-workspace">
    <div class="map-floating-filters"><div class="filterbar">${filtersHtml()}</div>${secondaryFilters()}</div>
    <div id="city-map" class="city-map" role="region" aria-label="Interactive Toronto issue map"></div>
    <div class="map-top-left"><div class="map-segment"><button class="${!state.heat ? 'active' : ''}" data-action="pins">${icon('pin')} Pins</button><button class="${state.heat ? 'active' : ''}" data-action="heat">${icon('density')} Density</button></div><span class="map-demo">FICTIONAL ISSUE LOCATIONS</span></div>
    <div class="map-top-right"><button class="map-control ${state.mapMode === 'pan' ? 'active' : ''}" data-action="pan" title="Pan map" aria-label="Pan map">${icon('hand')}</button><button class="map-control ${state.mapMode === 'box' ? 'active' : ''}" data-action="box" title="Box select" aria-label="Box select">${icon('select')}</button><button class="map-control ${state.layers.length ? 'active' : ''}" data-action="layers" title="Infrastructure layers" aria-label="Infrastructure layers">${icon('layers')}</button></div>
    <div class="map-bottom-left"><div class="map-summary"><span class="live-dot"></span><strong class="map-visible-count">Toronto, Ontario</strong> <span class="muted">· ${filtered().length} sample issues</span><button data-action="search-area" class="text-button">View area issues</button></div><div class="map-legend">${legend}<span class="legend-severity"><i>!</i>High severity</span></div></div>
    <div class="map-bottom-right"><button class="map-control street-person" draggable="true" data-action="street" aria-label="Street-level explorer placeholder" title="Street-level imagery integration">${icon('person')}</button><div class="zoom-controls"><button class="map-control" data-action="zoom-in" aria-label="Zoom in">${icon('plus')}</button><button class="map-control" data-action="zoom-out" aria-label="Zoom out">${icon('minus')}</button></div><button class="map-control" data-action="fit-results" title="Fit all matching issues" aria-label="Fit all matching issues">${icon('fit')}</button><button class="map-control" data-action="center" title="Reset Toronto view" aria-label="Reset Toronto view">${icon('home')}</button></div>
    <div class="map-hint">${icon(state.mapMode === 'box' ? 'select' : 'hand')} ${hint}</div>
    <div class="map-attribution">© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors</div>
    <div class="map-empty" hidden>${icon('search')}<h3>No matching sample issues</h3><p>Try a different search or remove a filter.</p><button class="button small" data-action="reset">Reset filters</button></div>
    <aside id="issue-panel" class="issue-panel" aria-label="Selected issues" hidden></aside>
  </div>`;
}

export function initMap() {
  const element = document.querySelector('#city-map');
  map = new CivicMap(element, { onSelect: selectMap, onEmpty: clearSelection, onMove: updateMapMeta, icon: typeIcon, colorFor: typeColor, assets: infrastructure, home: TORONTO_CENTER });
  map.center = state.center; map.zoom = state.zoom; map.mode = state.mapMode; map.layers = state.layers; map.showHeat = state.heat;
  map.setData(filtered(), state.selected); renderPanel(); updateMapMeta();
  attachSearch(document.querySelector('#global-search'), {
    icon, getItems: query => searchSuggestions(filtered(), query),
    onChoose: item => {
      state.filters.query = '';
      if (item.kind === 'area') state.filters.area = item.area;
      updateFilteredView(); document.querySelector('#global-search').blur();
      if (item.kind === 'issue') { openIssue(item.id); frameIssues([findIssue(item.id)]); }
      else frameIssues(filtered(), 14);
    },
  });
  document.querySelectorAll('[data-legend]').forEach(b => b.onclick = () => { state.filters.type = state.filters.type === b.dataset.legend ? '' : b.dataset.legend; updateFilteredView(); });
  const person = document.querySelector('.street-person');
  person.ondragstart = e => { e.dataTransfer.setData('text/plain', 'civiclens-street'); element.classList.add('coverage-preview'); };
  person.ondragend = () => element.classList.remove('coverage-preview');
  element.ondragover = e => e.preventDefault();
  element.ondrop = e => { e.preventDefault(); element.classList.remove('coverage-preview'); streetModal(); };
}

/** Re-applies changed filters on the map page without rebuilding the map. */
export function refreshMapFilters() {
  clearSelection();
  const rows = filtered();
  map.setData(rows, []);
  document.querySelectorAll('[data-filter]').forEach(el => el.value = state.filters[el.dataset.filter]);
  document.querySelector('#global-search').value = state.filters.query;
  document.querySelector('.map-floating-filters .filter-context').outerHTML = secondaryFilters();
  document.querySelectorAll('.map-floating-filters .filter-context [data-action]').forEach(b => b.onclick = () => action(b.dataset.action));
  document.querySelector('.map-summary .muted').textContent = `· ${rows.length} sample issues`;
  document.querySelectorAll('[data-legend]').forEach(b => b.classList.toggle('legend-active', b.dataset.legend === state.filters.type));
  bindFilterChips(); updateMapMeta();
}

export function setMapMode(mode) {
  state.mapMode = mode; map.stopMotion(); map.mode = mode; map.render();
  for (const name of ['pan', 'box']) document.querySelector(`[data-action="${name}"]`).classList.toggle('active', name === mode);
  document.querySelector('.map-hint').innerHTML = `${icon(mode === 'box' ? 'select' : 'hand')} ${mode === 'box' ? 'Drag a rectangle to select issues' : 'Drag to pan &middot; Scroll to zoom &middot; Shift + click to select'}`;
}
export function setHeat(on) {
  state.heat = on; map.stopMotion(); map.showHeat = on; map.render();
  document.querySelectorAll('.map-segment button').forEach(b => b.classList.toggle('active', b.dataset.action === (on ? 'heat' : 'pins')));
  if (on) toast('Density preview: overlapping sample issues glow.');
}

export function renderPanel() {
  const el = document.querySelector('#issue-panel');
  if (!el) return;
  const slide = isMobile() ? 'translateY(18px)' : 'translateX(22px)';
  document.querySelector('.map-workspace').classList.toggle('panel-open', !!state.panel);
  if (!state.panel) {
    delete el.dataset.open;
    if (!el.hidden && !reducedMotion()) el.animate([{ opacity: 1, transform: 'translate(0)' }, { opacity: 0, transform: slide }], { duration: 160, easing: 'ease-in' }).finished.then(() => { if (!state.panel) el.hidden = true; });
    else el.hidden = true;
    return;
  }
  el.hidden = false;
  if (!el.dataset.open) { el.dataset.open = 'true'; el.animate([{ opacity: 0, transform: slide }, { opacity: 1, transform: 'translate(0)' }], { duration: reducedMotion() ? 0 : 230, easing: 'cubic-bezier(.2,.8,.2,1)' }); }
  const p = state.panel;
  if (p.mode === 'issue') {
    const i = findIssue(p.id);
    el.innerHTML = `<div class="panel-heading"><button class="text-button" data-action="panel-back">${icon('back')} ${p.back ? 'Back to results' : 'Issue details'}</button><button class="icon-button" data-action="close-panel" aria-label="Close issue details">${icon('close')}</button></div>${detailHtml(i)}<div class="panel-footer"><button class="button" data-action="save-issue">${icon('bookmark')} ${state.saved.includes(i.issue_id) ? 'Saved' : 'Save issue'}</button><button class="button" data-action="share-issue">${icon('external')} Share</button></div>`;
    el.querySelector('[data-action="save-issue"]').onclick = () => toggleSave([i.issue_id]);
    el.querySelector('[data-action="share-issue"]').onclick = () => shareIssue(i);
    el.querySelector('[data-action="panel-back"]').onclick = () => { if (p.back) { state.panel = p.back; renderPanel(); } else clearSelection(); };
  } else {
    const issues = p.ids.map(findIssue).filter(Boolean), cluster = p.mode === 'cluster';
    const high = issues.filter(i => i.severity === 'High').length, verified = issues.filter(i => i.verification_status === 'Verified').length;
    el.innerHTML = `<div class="panel-heading"><div><span class="eyebrow">${cluster ? 'MAP CLUSTER' : 'YOUR SELECTION'}</span><h2>${issues.length} ${issues.length === 1 ? 'issue' : 'issues'} ${cluster ? 'in this cluster' : 'selected'}</h2></div><button class="icon-button" data-action="close-panel" aria-label="Close selection">${icon('close')}</button></div><div class="panel-info">${cluster ? 'Grouped at this zoom level. These may be separate incidents.' : 'Shift + click markers to add or remove issues.'}</div><div class="panel-list-controls"><input id="panel-search" placeholder="Filter these issues…" aria-label="Filter these issues"><select id="panel-sort" aria-label="Sort issues"><option value="date">Newest first</option><option value="severity">Severity</option><option value="type">Issue type</option></select></div><div class="selection-summary">${high} high priority <span>·</span> ${verified} verified</div><div id="panel-results" class="panel-results"></div><div class="panel-footer wrap"><button class="button primary" data-action="selection-table">${icon('database')} View as table</button>${cluster ? '<button class="button" data-action="cluster-zoom">Zoom in ↗</button>' : ''}<button class="button" data-action="save-selection">${icon('bookmark')} Save selection</button></div>`;
    const severityRank = ['High', 'Medium', 'Low'];
    const updateList = () => {
      const query = el.querySelector('#panel-search').value.toLowerCase(), sort = el.querySelector('#panel-sort').value;
      const rows = issues.filter(i => `${i.address} ${i.issue_type}`.toLowerCase().includes(query)).sort((a, b) => sort === 'severity' ? severityRank.indexOf(a.severity) - severityRank.indexOf(b.severity) : sort === 'type' ? a.issue_type.localeCompare(b.issue_type) : b.first_seen_at.localeCompare(a.first_seen_at));
      el.querySelector('#panel-results').innerHTML = rows.length ? rows.map(issueRow).join('') : emptyHtml('No matching issues', 'Try a different search.');
      el.querySelectorAll('[data-issue]').forEach(b => b.onclick = () => openIssue(b.dataset.issue, p));
    };
    updateList();
    el.querySelector('#panel-search').oninput = updateList;
    el.querySelector('#panel-sort').onchange = updateList;
    el.querySelector('[data-action="selection-table"]').onclick = () => scopedTable(p.ids);
    el.querySelector('[data-action="save-selection"]').onclick = () => toggleSave(p.ids);
    const zoom = el.querySelector('[data-action="cluster-zoom"]');
    if (zoom) zoom.onclick = () => frameIssues(issues, Math.min(18, Math.round(map.zoom) + 2));
  }
  el.querySelector('[data-action="close-panel"]').onclick = clearSelection;
}
