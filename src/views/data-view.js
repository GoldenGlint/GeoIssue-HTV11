// Data Explorer: summary cards, the records table, and the read-only Query tab.
import { REFERENCE_DATE, wards } from '../data.js';
import { icon } from '../icons.js';
import { DAY, esc, badge, date, typeIcon, typeColor, percent } from '../format.js';
import { compareIssues } from '../issues.js';
import { state, scopedRows, persist } from '../state.js';
import { statCard, emptyHtml, toast, priorityLevel } from '../ui.js';
import { render } from '../app.js';

// Key, header, cell contents and an optional cell class. Issue ID can't be hidden: it opens the record.
const columns = [
  ['issue_id', 'Issue ID', i => `<button class="table-id" data-issue="${i.issue_id}">${i.issue_id}</button>`],
  ['issue_type', 'Issue type', i => `<span class="table-type" style="--type-color:${typeColor(i.issue_type)}">${typeIcon(i.issue_type)}${esc(i.issue_type)}</span>`],
  ['severity', 'Severity', i => badge(i.severity)],
  ['priority_score', 'Priority', i => i.priority_score == null ? '–' : `<span class="priority-pill ${priorityLevel(i.priority_score)}" title="${esc((i.priority_reasons || []).join('\n'))}">${i.priority_score}</span>`],
  ['resolution_status', 'Status', i => badge(i.resolution_status)],
  ['neighbourhood_name', 'Area', i => `<span class="cell-main">${esc(i.neighbourhood_name)}</span><small class="cell-sub" title="${esc(wards[i.ward_id])}">Ward ${esc(i.ward_id)}</small>`],
  ['address', 'Location', i => `<span class="cell-main" title="${esc(i.address)}">${esc(i.address)}</span><small class="cell-sub">${i.distance_m == null ? 'No nearby asset determined' : `${esc(i.asset_name)} · ${i.distance_m.toLocaleString()} m`}</small>`, 'address-cell'],
  ['first_seen_at', 'Detected', i => date(i.first_seen_at)],
  ['last_seen_at', 'Last seen', i => date(i.last_seen_at)],
  ['sightings_count', 'Sightings', i => i.sightings_count, 'num-cell'],
  ['detection_confidence', 'Confidence', i => `<span class="confidence-pill">${Math.round(i.detection_confidence * 100)}%</span>`],
  ['source_category', 'Source', i => esc(i.source_category), 'source-cell'],
  ['verification_status', 'Verification', i => `<span class="verification-dot ${i.verification_status === 'Verified' ? 'verified' : ''}"></span>${esc(i.verification_status)}`],
];
const isHidden = key => state.hiddenColumns.includes(key);
const hiddenAttr = key => isHidden(key) ? ' hidden' : '';
const newestFirst = ['severity', 'priority_score', 'detection_confidence', 'first_seen_at', 'last_seen_at', 'sightings_count'];
const sortedRows = () => scopedRows().sort((a, b) => compareIssues(a, b, state.sort, state.direction));
// The last row ticked. Shift-clicking another row ticks or clears every visible row between the two.
let anchorId = null;

export function dataHtml() {
  const rows = sortedRows();
  state.page = Math.min(state.page, Math.max(1, Math.ceil(rows.length / state.perPage)));
  return `<div class="data-page">${statsHtml(rows)}<div class="records-card">${toolbarHtml(rows)}${state.dataTab === 'query' ? queryHtml(rows) : recordsHtml(rows)}</div><div class="data-bottom"><div class="integration-note">${icon('code')}<div><strong>Ready for your pipeline</strong><p>Map, table, and analytics share a single issue repository. Replace the sample adapter to connect your data.</p></div><code>src/data.js → issueRepository</code></div><span class="privacy-note">${icon('shield')} Public view · approximate locations</span></div></div>`;
}

function statsHtml(rows) {
  const review = rows.filter(i => i.verification_status === 'Needs review').length;
  const confidence = rows.length ? Math.round(rows.reduce((sum, i) => sum + i.detection_confidence, 0) / rows.length * 100) : 0;
  return `<div class="stat-grid">${[
    statCard({ label: 'Total records', value: state.issues.length, note: state.dataSource === 'collected' ? 'Collected by the pipeline' : 'Fictional simulated dataset', color: 'blue' }),
    statCard({ label: 'Filtered results', value: rows.length, note: `${percent(rows.length, state.issues.length)}% of all records`, color: 'cyan' }),
    statCard({ label: 'Awaiting verification', value: review, note: 'Needs a volunteer review', color: 'amber' }),
    statCard({ label: 'Avg. detection confidence', value: rows.length ? `${confidence}%` : '–', note: 'Across filtered records', color: 'green' }),
  ].join('')}</div>`;
}

function toolbarHtml(rows) {
  const records = state.dataTab !== 'query';
  const scope = state.scope ? `<span class="scope-chip">Selected issues <button data-action="clear-scope" aria-label="Clear selection scope">×</button></span>` : '<span class="subtle-label">All accessible Toronto issues</span>';
  const backend = state.dataBackend.type === 'tiger' ? `<button class="activity-source subtle-label" data-action="tiger-info" aria-label="About Tiger Data">${icon('database')} Tiger Data</button>` : '';
  return `<div class="table-toolbar"><div class="table-tabs" role="tablist"><button class="table-tab ${records ? 'active' : ''}" role="tab" aria-selected="${records}" data-tab="records">${icon('database')} Issue records <span>${rows.length}</span></button><button class="table-tab ${records ? '' : 'active'}" role="tab" aria-selected="${!records}" data-tab="query">${icon('code')} Query</button></div><div class="table-actions">${backend}${scope}${records ? columnPickerHtml() : ''}<button class="button small" data-action="table-map">${icon('map')} View on map</button><button class="button small" data-action="export">${icon('download')} Export</button></div></div>`;
}
const columnButtonLabel = () => {
  const shown = columns.filter(([key]) => !isHidden(key)).length;
  return `${icon('columns')} Columns${shown < columns.length ? ` <span class="columns-count">${shown}/${columns.length}</span>` : ''}`;
};
function columnPickerHtml() {
  const options = columns.map(([key, title]) => `<label class="columns-option"><input type="checkbox" data-toggle-col="${key}" ${isHidden(key) ? '' : 'checked'} ${key === 'issue_id' ? 'disabled' : ''}>${title}</label>`).join('');
  return `<button class="button small" id="columns-button" popovertarget="columns-menu">${columnButtonLabel()}</button><div class="columns-menu" id="columns-menu" popover><div class="columns-menu-head"><span>Show columns</span><button class="text-button" id="show-all-columns">Show all</button></div>${options}</div>`;
}

function recordsHtml(rows) {
  const pageRows = rows.slice((state.page - 1) * state.perPage, state.page * state.perPage);
  const isSelected = i => state.selected.includes(i.issue_id), count = state.selected.length;
  const head = columns.map(([key, title]) => `<th data-col="${key}"${hiddenAttr(key)} aria-sort="${state.sort === key ? (state.direction === 1 ? 'ascending' : 'descending') : 'none'}"><button data-sort="${key}">${title}<span>${state.sort === key ? (state.direction === 1 ? '↑' : '↓') : '↕'}</span></button></th>`).join('');
  const body = pageRows.map(i => `<tr class="${isSelected(i) ? 'row-selected' : ''}">
    <td><input type="checkbox" data-select-id="${i.issue_id}" aria-label="Select ${i.issue_id}" ${isSelected(i) ? 'checked' : ''}></td>
    ${columns.map(([key, , cell, cls]) => `<td data-col="${key}"${cls ? ` class="${cls}"` : ''}${hiddenAttr(key)}>${cell(i)}</td>`).join('')}
    <td><button class="icon-button" data-save="${i.issue_id}" aria-label="${state.saved.includes(i.issue_id) ? 'Unsave' : 'Save'} ${i.issue_id}">${icon('bookmark', state.saved.includes(i.issue_id) ? 'saved-icon' : '')}</button></td>
  </tr>`).join('');
  // Always in the page, so ticking rows can show and count it without redrawing the table.
  const selectionBar = `<div class="table-selection-bar" ${count ? '' : 'hidden'}><span>${icon('check')} <strong data-selection-count>${count}</strong> selected</span><div><button class="text-button" data-action="save-table-selection">${icon('bookmark')} Save</button><button class="text-button" data-action="export-selected">${icon('download')} Export selected</button><button class="text-button" data-action="clear-table-selection">Clear selection</button></div></div>`;
  const range = rows.length ? `Showing ${(state.page - 1) * state.perPage + 1}–${Math.min(rows.length, state.page * state.perPage)} of ${rows.length}` : '0 results';
  return `${selectionBar}<div class="table-scroll"><table><thead><tr><th><input type="checkbox" id="select-page" aria-label="Select visible rows" ${pageRows.length && pageRows.every(isSelected) ? 'checked' : ''}></th>${head}<th></th></tr></thead><tbody>${body}</tbody></table>${rows.length ? '' : emptyHtml('No issues match these filters', 'Reset filters or try another area.')}</div><div class="table-pagination"><span>${range} <strong id="page-selection" ${count ? '' : 'hidden'}>· <span data-selection-count>${count}</span> selected</strong></span><div><select id="page-size" aria-label="Rows per page">${[10, 20, 50].map(n => `<option ${n === state.perPage ? 'selected' : ''} value="${n}">${n} per page</option>`).join('')}</select><button class="icon-button" data-page="${state.page - 1}" ${state.page === 1 ? 'disabled' : ''} aria-label="Previous page">${icon('back')}</button><span class="page-number">${state.page}</span><button class="icon-button" data-page="${state.page + 1}" ${state.page * state.perPage >= rows.length ? 'disabled' : ''} aria-label="Next page">${icon('arrow')}</button></div></div>`;
}

const schema = [
  ['issue_id', 'text'], ['incident_id', 'text'], ['geom', 'geometry(Point, 4326)'], ['location_radius_m', 'integer'],
  ['neighbourhood_id', 'text'], ['neighbourhood_name', 'text'], ['ward_id', 'text'], ['address', 'text'], ['issue_type', 'text'], ['severity', 'text'],
  ['resolution_status', 'text'], ['verification_status', 'text'], ['detection_confidence', 'real'], ['geo_confidence', 'real'], ['geo_method', 'text'],
  ['first_seen_at', 'timestamptz'], ['last_seen_at', 'timestamptz'], ['sightings_count', 'integer'], ['priority_score', 'integer'], ['priority_reasons', 'text[]'], ['infrastructure_type', 'text'],
  ['asset_id', 'text'], ['distance_m', 'integer'], ['source_category', 'text'], ['evidence_thumbnail', 'text'], ['explanation', 'text'],
];

/** The current filters, scope, sort and page as one SQL statement (display only; never executed). */
export function buildQuery() {
  const f = state.filters, quote = v => `'${String(v).replaceAll("'", "''")}'`, where = [];
  if (f.days) where.push(`first_seen_at > TIMESTAMPTZ ${quote(new Date(Date.parse(REFERENCE_DATE) - f.days * DAY).toISOString().replace('T', ' ').slice(0, 19) + '+00')}  -- last ${f.days} days`);
  if (f.type) where.push(`issue_type = ${quote(f.type)}`);
  if (f.severity) where.push(`severity = ${quote(f.severity)}`);
  if (f.status) where.push(`resolution_status = ${quote(f.status)}`);
  if (f.area.startsWith('ward:')) where.push(`ward_id = ${quote(f.area.slice(5))}  -- ${wards[f.area.slice(5)]}`);
  else if (f.area) where.push(`neighbourhood_id = ${quote(f.area)}`);
  if (f.query.trim()) where.push(`search_text ILIKE ${quote(`%${f.query.trim()}%`)}  -- ID, address, area, type, asset, description`);
  if (f.infra) where.push(`EXISTS (SELECT 1 FROM infrastructure a\n              WHERE ${f.infra === 'any' ? '' : `a.type = ${quote(f.infra)} AND `}ST_DWithin(a.geom::geography, issues.geom::geography, ${f.radius}))`);
  if (state.scope) where.push(`issue_id = ANY(:selected_ids)  -- ${state.scope.length} selected issues`);
  const ranked = { severity: "array_position(ARRAY['Low', 'Medium', 'High'], severity)", resolution_status: "array_position(ARRAY['Open', 'In review', 'Resolved'], resolution_status)" };
  // The table's visible columns (Area also shows the ward), a few to a line.
  const fields = columns.filter(([key]) => !isHidden(key)).flatMap(([key]) => key === 'neighbourhood_name' ? [key, 'ward_id'] : [key]), select = [];
  for (const name of fields) if (select.length && select.at(-1).length + name.length < 64) select[select.length - 1] += `, ${name}`; else select.push(name);
  return [
    ...select.map((line, j) => `${j ? '       ' : 'SELECT '}${line}${j < select.length - 1 ? ',' : ''}`),
    'FROM issues',
    ...where.map((condition, j) => `${j ? '  AND' : 'WHERE'} ${condition}`),
    `ORDER BY ${ranked[state.sort] || state.sort} ${state.direction === 1 ? 'ASC' : 'DESC'}, issue_id`,
    `LIMIT ${state.perPage} OFFSET ${(state.page - 1) * state.perPage};`,
  ].join('\n');
}
function highlight(sql) {
  const tokens = /(--[^\n]*)|('(?:[^']|'')*')|\b(SELECT|FROM|WHERE|AND|ORDER|BY|LIMIT|OFFSET|ASC|DESC|EXISTS|ILIKE|ANY|TIMESTAMPTZ|ARRAY)\b|\b(ST_DWithin|array_position)\b|\b(\d+)\b/g;
  let html = '', last = 0;
  for (const m of sql.matchAll(tokens)) {
    html += esc(sql.slice(last, m.index));
    const kind = m[1] ? 'cmt' : m[2] ? 'str' : m[3] ? 'kw' : m[4] ? 'fn' : 'num';
    html += `<span class="${kind}">${esc(m[0])}</span>`;
    last = m.index + m[0].length;
  }
  return html + esc(sql.slice(last));
}
function queryHtml(rows) {
  const sql = buildQuery(), pages = Math.max(1, Math.ceil(rows.length / state.perPage));
  const sortLabel = columns.find(([key]) => key === state.sort)?.[1] || state.sort;
  return `<div class="query-view"><div><div class="query-head"><div><h3>Generated query</h3><p>A read-only view of the active filters, scope, sort and page, written as SQL for transparency. The table reads from the issue API; nothing here runs in the browser.</p></div><button class="button small" data-action="copy-query">${icon('copy')} Copy</button></div><pre class="query-code"><code>${highlight(sql)}</code></pre><div class="query-meta"><span><strong>${rows.length}</strong> matching rows</span><span>Page <strong>${state.page}</strong> of ${pages}</span><span>Sorted by <strong>${esc(sortLabel)}</strong></span></div></div><div class="schema-card"><h3>${icon('database')} issues <span class="subtle-label">${schema.length} columns</span></h3><div class="schema-list">${schema.map(([name, type]) => `<div><code>${name}</code><span>${type}</span></div>`).join('')}</div><p class="fine-print">Ward and neighbourhood joins, deduplication into incidents, and 311 context happen on the backend.</p></div></div>`;
}

export function bindData() {
  document.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => { state.dataTab = b.dataset.tab; render(); });
  document.querySelector('[data-action="copy-query"]')?.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(buildQuery()); toast('Query copied'); } catch { toast('Copy is unavailable in this browser. Select the query text instead.'); }
  });
  if (state.dataTab === 'query') return;
  document.querySelectorAll('[data-sort]').forEach(b => b.onclick = () => {
    if (state.sort === b.dataset.sort) state.direction *= -1;
    else { state.sort = b.dataset.sort; state.direction = newestFirst.includes(state.sort) ? -1 : 1; }
    render();
  });
  document.querySelectorAll('[data-page]').forEach(b => b.onclick = () => { state.page = Number(b.dataset.page); render(); });
  document.querySelector('#page-size').onchange = e => { state.perPage = Number(e.target.value); state.page = 1; render(); };
  const boxes = [...document.querySelectorAll('[data-select-id]')], ids = boxes.map(c => c.dataset.selectId);
  boxes.forEach(c => {
    // Without this, Shift-click also selects the page text between the two rows.
    c.onmousedown = e => { if (e.shiftKey) e.preventDefault(); };
    c.onclick = e => {
      const from = e.shiftKey ? ids.indexOf(anchorId) : -1, to = ids.indexOf(c.dataset.selectId);
      selectRows(from < 0 ? [c.dataset.selectId] : ids.slice(Math.min(from, to), Math.max(from, to) + 1), c.checked);
      anchorId = c.dataset.selectId;
    };
  });
  document.querySelector('#select-page').onchange = e => selectRows(ids, e.target.checked);
  syncSelection();
  bindColumnPicker();
}

function selectRows(ids, on) {
  state.selected = on ? [...new Set([...state.selected, ...ids])] : state.selected.filter(id => !ids.includes(id));
  syncSelection();
}
export function clearTableSelection() {
  state.selected = [];
  syncSelection();
}
/** Matches the checkboxes, row highlights and counts to state.selected in place, so ticking a row doesn't redraw the page. */
function syncSelection() {
  const all = document.querySelector('#select-page');
  if (!all) return;
  const boxes = [...document.querySelectorAll('[data-select-id]')], count = state.selected.length;
  for (const box of boxes) {
    box.checked = state.selected.includes(box.dataset.selectId);
    box.closest('tr').classList.toggle('row-selected', box.checked);
  }
  // Some but not all visible rows selected: the header box shows a dash.
  all.checked = boxes.length > 0 && boxes.every(c => c.checked);
  all.indeterminate = !all.checked && boxes.some(c => c.checked);
  document.querySelector('.table-selection-bar').hidden = document.querySelector('#page-selection').hidden = !count;
  document.querySelectorAll('[data-selection-count]').forEach(el => el.textContent = count);
}

// Column picker. Hiding a column hides its cells rather than redrawing, so the table keeps its scroll position.
function bindColumnPicker() {
  const menu = document.querySelector('#columns-menu');
  menu.addEventListener('beforetoggle', e => {
    const open = e.newState === 'open', listen = open ? 'addEventListener' : 'removeEventListener';
    window[listen]('scroll', placeColumnMenu, true);
    window[listen]('resize', placeColumnMenu, true);
    // The menu has no size until it opens; this runs once it has one, before it is first drawn.
    if (open) requestAnimationFrame(placeColumnMenu);
  });
  menu.querySelectorAll('[data-toggle-col]').forEach(c => c.onchange = () => {
    const key = c.dataset.toggleCol;
    setHiddenColumns(c.checked ? state.hiddenColumns.filter(k => k !== key) : [...state.hiddenColumns, key]);
  });
  document.querySelector('#show-all-columns').onclick = () => setHiddenColumns([]);
}
function setHiddenColumns(keys) {
  state.hiddenColumns = keys;
  persist('hiddenColumns', keys);
  document.querySelectorAll('[data-col]').forEach(cell => cell.hidden = isHidden(cell.dataset.col));
  document.querySelectorAll('[data-toggle-col]').forEach(c => c.checked = !isHidden(c.dataset.toggleCol));
  document.querySelector('#columns-button').innerHTML = columnButtonLabel();
}
/** The menu opens in the top layer, so it is placed by hand: under its button, right edges aligned, or above it when there is more room there. */
function placeColumnMenu() {
  const menu = document.querySelector('#columns-menu'), button = document.querySelector('#columns-button');
  if (!menu?.matches(':popover-open')) return;
  const r = button.getBoundingClientRect(), gap = 6, edge = 8;
  const below = innerHeight - r.bottom - gap - edge, above = r.top - gap - edge, up = menu.scrollHeight > below && above > below;
  menu.style.maxHeight = `${up ? above : below}px`;
  menu.style.left = `${Math.max(edge, r.right - menu.offsetWidth)}px`;
  menu.style.top = `${up ? r.top - gap - menu.offsetHeight : r.bottom + gap}px`;
}
