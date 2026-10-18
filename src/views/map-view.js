// Map Explorer: the map canvas, floating controls, and the selection-driven right panel.
import { CivicMap } from '../map.js';
import { attachSearch } from '../search.js';
import { categories, infrastructure, wardBoundaries, TORONTO_CENTER } from '../data.js';
import { icon } from '../icons.js';
import { esc, typeIcon, typeColor, issueName } from '../format.js';
import { planRoute, ROUTE_ASSUMPTIONS, MAX_STOPS } from '../route.js';
import { googleDirectionsUrl, DIRECTIONS_MAX_POINTS, distanceMetres } from '../coordinates.js';
import { searchSuggestions } from '../issues.js';
import { state, filtered, findIssue, remember, sampleWord, shouldShowMapEmptyNotice, dismissMapEmptyNotice } from '../state.js';
import { toast, detailHtml, issueRow, emptyHtml, bindEvidence } from '../ui.js';
import { action, filtersHtml, secondaryFilters, bindFilterChips, updateFilteredView, scopedTable, toggleSave } from '../app.js';
import { shareIssue, streetModal, correctionModal } from '../modals.js';

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
export function frameIssues(issues, maxZoom = 15, duration) {
  if (!issues.length) { toast('No matching issues to frame.'); return; }
  map?.fitTo(issues.map(i => i.geometry.coordinates), mapPadding(), maxZoom, duration);
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
    const button = empty.querySelector('[data-empty-action]');
    empty.hidden = !shouldShowMapEmptyNotice(visible.length);
    empty.querySelector('h3').textContent = rows.length ? 'Matches outside this view' : `No matching ${sampleWord()}issues`;
    button.dataset.action = rows.length ? 'fit-results' : 'reset';
    button.textContent = rows.length ? 'Show matches' : 'Reset filters';
    button.onclick = () => action(button.dataset.action);
    empty.querySelector('[data-dismiss-map-empty]').onclick = () => {
      dismissMapEmptyNotice(); empty.hidden = true;
      map.element.focus({ preventScroll: true });
    };
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
  const emptyNotice = `<div class="map-empty" hidden>${icon('search')}<h3>No matching ${sampleWord()}issues</h3><button class="text-button" data-empty-action data-action="reset">Reset filters</button><button class="icon-button" data-dismiss-map-empty aria-label="Dismiss map notice">${icon('close')}</button></div>`;
  return `<div class="map-workspace ${state.heat ? 'density-mode' : ''}">
    <div class="map-floating-filters"><div class="filterbar">${filtersHtml()}</div>${secondaryFilters()}</div>
    <div id="city-map" class="city-map" role="region" aria-label="Interactive Toronto issue map"></div>
    <div class="map-top-left"><div class="map-segment"><button class="${!state.heat ? 'active' : ''}" data-action="pins">${icon('pin')} Pins</button><button class="${state.heat ? 'active' : ''}" data-action="heat">${icon('density')} Density</button></div></div>
    <div class="map-top-right"><button class="map-control ${state.mapMode === 'pan' ? 'active' : ''}" data-action="pan" title="Pan map" aria-label="Pan map">${icon('hand')}</button><button class="map-control ${state.mapMode === 'box' ? 'active' : ''}" data-action="box" title="Box select" aria-label="Box select">${icon('select')}</button><button class="map-control ${state.layers.length ? 'active' : ''}" data-action="layers" title="Infrastructure layers" aria-label="Infrastructure layers">${icon('layers')}</button></div>
    <div class="map-bottom-left">${emptyNotice}<div class="map-summary"><span class="live-dot"></span><strong class="map-visible-count">Toronto, Ontario</strong> <span class="muted">· ${filtered().length} ${sampleWord()}issues</span><button data-action="search-area" class="text-button">View area issues</button></div><div class="map-legend">${legend}<span class="legend-severity"><i>!</i>High severity</span></div><div class="density-legend"><span>Fewer reports</span><i></i><span>More</span><small>Click a hot spot to list its issues</small></div></div>
    <div class="map-bottom-right"><button class="map-control street-person" draggable="true" data-action="street" aria-label="Street View at the map centre" title="Street View: click for the map centre, or drag onto the map">${icon('person')}</button><div class="zoom-controls"><button class="map-control" data-action="zoom-in" aria-label="Zoom in">${icon('plus')}</button><button class="map-control" data-action="zoom-out" aria-label="Zoom out">${icon('minus')}</button></div><button class="map-control" data-action="fit-results" title="Fit all matching issues" aria-label="Fit all matching issues">${icon('fit')}</button><button class="map-control" data-action="center" title="Reset Toronto view" aria-label="Reset Toronto view">${icon('home')}</button></div>
    <div class="map-hint">${icon(state.mapMode === 'box' ? 'select' : 'hand')} ${hint}</div>
    <div class="map-attribution">© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors</div>
    <aside id="issue-panel" class="issue-panel" aria-label="Selected issues" hidden></aside>
  </div>`;
}

export function initMap() {
  const element = document.querySelector('#city-map');
  // Clicking a ward label filters to that ward; clicking the active ward clears the filter.
  const onArea = area => { state.filters.area = state.filters.area === area ? '' : area; updateFilteredView(); };
  map = new CivicMap(element, { onSelect: selectMap, onEmpty: clearSelection, onMove: updateMapMeta, onArea, icon: typeIcon, colorFor: typeColor, assets: infrastructure, boundaries: wardBoundaries, home: TORONTO_CENTER });
  map.center = state.center; map.zoom = state.zoom; map.mode = state.mapMode; map.layers = state.layers; map.showHeat = state.heat; map.activeArea = state.filters.area;
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
  element.ondrop = e => {
    e.preventDefault(); element.classList.remove('coverage-preview');
    const r = element.getBoundingClientRect();
    streetModal(map.coordsAt([e.clientX - r.left, e.clientY - r.top]));
  };
}

/** Re-applies changed filters on the map page without rebuilding the map. */
export function refreshMapFilters() {
  clearSelection();
  const rows = filtered();
  map.activeArea = state.filters.area;
  map.setData(rows, []);
  document.querySelectorAll('[data-filter]').forEach(el => el.value = state.filters[el.dataset.filter]);
  document.querySelector('#global-search').value = state.filters.query;
  document.querySelector('.map-floating-filters .filter-context').outerHTML = secondaryFilters();
  document.querySelectorAll('.map-floating-filters .filter-context [data-action]').forEach(b => b.onclick = () => action(b.dataset.action));
  document.querySelector('.map-summary .muted').textContent = `· ${rows.length} ${sampleWord()}issues`;
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
  document.querySelector('.map-workspace').classList.toggle('density-mode', on);
  document.querySelectorAll('.map-segment button').forEach(b => b.classList.toggle('active', b.dataset.action === (on ? 'heat' : 'pins')));
}

const km = v => `${v < 10 ? v.toFixed(1) : Math.round(v)} km`;
const kg = v => `${v >= 10 ? Math.round(v) : v >= 1 ? v.toFixed(1) : Number(v.toPrecision(2))} kg`;
const duration = minutes => minutes < 60 ? `${Math.max(1, Math.round(minutes))} min` : `${Math.floor(minutes / 60)} h ${Math.round(minutes % 60)} min`;

/** The crew route panel: the planned order on the map, its distance and CO₂ in a gas or electric van, and the stops. */
function routeHtml(plan) {
  const a = ROUTE_ASSUMPTIONS, { stops } = plan;
  const savedKm = plan.reportedKm - plan.km, savedShare = plan.reportedKm ? savedKm / plan.reportedKm : 0;
  const avoided = plan.reportedGasKg - plan.planned.evKg, avoidedShare = plan.reportedGasKg ? avoided / plan.reportedGasKg : 0;
  const bars = [['Gas van, order reported', plan.reportedGasKg, 'gas faded'], ['Gas van, this route', plan.planned.gasKg, 'gas'], ['Electric van, this route', plan.planned.evKg, 'ev']];
  const most = Math.max(...bars.map(b => b[1])) || 1;
  const rows = stops.map((issue, n) => {
    const legKm = n ? distanceMetres(stops[n - 1].geometry.coordinates, issue.geometry.coordinates) / 1000 * a.detourFactor : 0;
    const leg = !n ? ' · start' : legKm < 0.05 ? ` · same spot as stop ${n}` : ` · ${km(legKm)} from stop ${n}`;
    return `<li><button class="route-stop-row" data-issue="${esc(issue.issue_id)}"><span class="route-num">${n + 1}</span><span><strong>${esc(issueName(issue))}</strong><small>${esc(issue.address)}${leg}</small></span>${icon('arrow')}</button></li>`;
  }).join('');
  const directions = stops.length > DIRECTIONS_MAX_POINTS ? `Directions for the first ${DIRECTIONS_MAX_POINTS} stops` : 'Directions in Google Maps';
  return `<div class="panel-heading"><button class="text-button" data-action="panel-back">${icon('back')} Back to selection</button><button class="icon-button" data-action="close-panel" aria-label="Close route">${icon('close')}</button></div>
    <div class="detail-body route-body">
      <div class="route-title"><span class="route-orb">${icon('route')}</span><div><span class="eyebrow">Crew route · estimate</span><h2>${stops.length} stops · ${km(plan.km)}</h2></div></div>
      <p class="route-lede">About ${duration(plan.minutes)} of driving. ${savedShare >= 0.005 ? `Visiting in this order instead of the order they were reported saves <strong>${km(savedKm)}</strong> (${Math.floor(savedShare * 100)}%).` : 'The order they were reported is already about as short.'}</p>
      <div class="route-bars">${bars.map(([label, value, kind]) => `<div class="route-bar ${kind}"><span>${label}</span><strong>${kg(value)} CO₂</strong><i style="width:${Math.max(1.5, value / most * 100).toFixed(1)}%"></i></div>`).join('')}</div>
      <p class="route-callout">${icon('leaf')}<span>Planned and driven electric, this trip emits <strong>${kg(avoided)} CO₂ less</strong> than a gas van taking the issues in the order reported, ${Math.floor(avoidedShare * 100)}% less.</span></p>
      <h3 class="route-subhead">Stops in order</h3>
      <ol class="route-stops">${rows}</ol>
      ${plan.left ? `<p class="fine-print">${plan.left} more selected ${plan.left === 1 ? 'issue was' : 'issues were'} left out: routes plan up to ${MAX_STOPS} stops, highest priority first.</p>` : ''}
      <details class="route-assumptions"><summary>How this is estimated</summary><ul>
        <li>The order: the shortest of the nearest-next routes from every stop, then improved by reversing any stretch that shortens it.</li>
        <li>Road distance is ${a.detourFactor} × the straight line between stops, driven at ${a.speedKmh} km/h. Work time at each stop isn't included.</li>
        <li>Gas van: ${a.gasLitresPer100Km} L per 100 km × ${a.gasKgCo2PerLitre} kg CO₂ per litre of gasoline.</li>
        <li>Electric van: ${a.evKwhPerKm} kWh per km × about ${a.gridKgCo2PerKwh * 1000} g CO₂e per kWh on Ontario's mostly nuclear and hydro grid.</li>
        <li>Issue positions are approximate (public ones are rounded to a 250 m grid), so the stops are too.</li>
      </ul></details>
    </div>
    <div class="panel-footer"><a class="button primary" href="${googleDirectionsUrl(stops.map(i => i.geometry.coordinates))}" target="_blank" rel="noopener">${icon('external')} ${directions}</a><button class="button" data-action="route-fit">${icon('fit')} Show route</button></div>`;
}

export function renderPanel() {
  const el = document.querySelector('#issue-panel');
  if (!el) return;
  // The route stays drawn while one of its stops is open from the route panel.
  const routePanel = state.panel?.mode === 'route' ? state.panel : state.panel?.back?.mode === 'route' ? state.panel.back : null;
  map?.setRoute(routePanel ? routePanel.plan.stops.map(i => i.geometry.coordinates) : null);
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
    el.innerHTML = `<div class="panel-heading"><button class="text-button" data-action="panel-back">${icon('back')} ${p.back ? `Back to ${p.back.mode === 'route' ? 'route' : 'results'}` : 'Issue details'}</button><button class="icon-button" data-action="close-panel" aria-label="Close issue details">${icon('close')}</button></div>${detailHtml(i)}<div class="panel-footer"><button class="button" data-action="save-issue">${icon('bookmark')} ${state.saved.includes(i.issue_id) ? 'Saved' : 'Save'}</button><button class="button" data-action="share-issue">${icon('external')} Share</button><button class="button" data-action="correct-issue">${icon('edit')} Suggest correction</button></div>`;
    el.querySelector('[data-action="save-issue"]').onclick = () => toggleSave([i.issue_id]);
    el.querySelector('[data-action="correct-issue"]').onclick = () => correctionModal(i);
    el.querySelector('[data-action="share-issue"]').onclick = () => shareIssue(i);
    bindEvidence(el);
    el.querySelector('[data-action="panel-back"]').onclick = () => { if (p.back) { state.panel = p.back; renderPanel(); } else clearSelection(); };
  } else if (p.mode === 'route') {
    el.innerHTML = routeHtml(p.plan);
    el.querySelectorAll('[data-issue]').forEach(b => b.onclick = () => openIssue(b.dataset.issue, p));
    el.querySelector('[data-action="panel-back"]').onclick = () => { state.panel = p.back; renderPanel(); };
    el.querySelector('[data-action="route-fit"]').onclick = () => frameIssues(p.plan.stops);
  } else {
    const issues = p.ids.map(findIssue).filter(Boolean), cluster = p.mode === 'cluster';
    const high = issues.filter(i => i.severity === 'High').length, verified = issues.filter(i => i.verification_status === 'Verified').length;
    el.innerHTML = `<div class="panel-heading"><div><h2>${issues.length} ${issues.length === 1 ? 'issue' : 'issues'} ${cluster ? 'in this cluster' : 'selected'}</h2></div><button class="icon-button" data-action="close-panel" aria-label="Close selection">${icon('close')}</button></div><div class="panel-info">${cluster ? 'Grouped at this zoom level. These may be separate incidents.' : 'Shift + click markers to add or remove issues.'}</div><div class="panel-list-controls"><input id="panel-search" placeholder="Filter these issues…" aria-label="Filter these issues"><select id="panel-sort" aria-label="Sort issues"><option value="date">Newest first</option><option value="severity">Severity</option><option value="type">Issue type</option></select></div><div class="selection-summary">${high} high priority <span>·</span> ${verified} verified</div><div id="panel-results" class="panel-results"></div><div class="panel-footer wrap"><button class="button primary" data-action="selection-table">${icon('database')} View as table</button>${cluster ? `<button class="button" data-action="cluster-zoom">${icon('fit')} Zoom in</button>` : ''}<button class="button" data-action="save-selection">${icon('bookmark')} Save selection</button>${issues.length > 1 ? `<button class="button" data-action="plan-route">${icon('route')} Plan crew route</button>` : ''}</div>`;
    const severityRank = ['High', 'Medium', 'Low'];
    const updateList = () => {
      const query = el.querySelector('#panel-search').value.toLowerCase(), sort = el.querySelector('#panel-sort').value;
      const rows = issues.filter(i => `${i.address} ${i.issue_type} ${i.title || ''}`.toLowerCase().includes(query)).sort((a, b) => sort === 'severity' ? severityRank.indexOf(a.severity) - severityRank.indexOf(b.severity) : sort === 'type' ? a.issue_type.localeCompare(b.issue_type) : b.first_seen_at.localeCompare(a.first_seen_at));
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
    const route = el.querySelector('[data-action="plan-route"]');
    if (route) route.onclick = () => {
      state.panel = { mode: 'route', ids: p.ids, plan: planRoute(issues), back: p };
      renderPanel(); frameIssues(state.panel.plan.stops);
    };
  }
  el.querySelector('[data-action="close-panel"]').onclick = clearSelection;
}
