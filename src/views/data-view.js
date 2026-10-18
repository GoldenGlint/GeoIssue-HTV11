// Data Explorer: summary cards, the records table, and the read-only Query tab.
import { REFERENCE_DATE, wards } from '../data.js';
import { icon } from '../icons.js';
import { DAY, esc, badge, date, typeIcon, typeColor, percent } from '../format.js';
import { compareIssues } from '../issues.js';
import { state, scopedRows } from '../state.js';
import { statCard, emptyHtml, toast, priorityLevel } from '../ui.js';
import { render } from '../app.js';

const columns = [
  ['issue_id', 'Issue ID'], ['issue_type', 'Issue type'], ['severity', 'Severity'], ['priority_score', 'Priority'], ['resolution_status', 'Status'],
  ['neighbourhood_name', 'Area'], ['address', 'Location'], ['first_seen_at', 'Detected'], ['last_seen_at', 'Last seen'],
  ['sightings_count', 'Sightings'], ['detection_confidence', 'Confidence'], ['source_category', 'Source'], ['verification_status', 'Verification'],
];
const newestFirst = ['severity', 'priority_score', 'detection_confidence', 'first_seen_at', 'last_seen_at', 'sightings_count'];
const sortedRows = () => scopedRows().sort((a, b) => compareIssues(a, b, state.sort, state.direction));

export function dataHtml() {
  const rows = sortedRows();
  state.page = Math.min(state.page, Math.max(1, Math.ceil(rows.length / state.perPage)));
  return `<div class="data-page">${statsHtml(rows)}<div class="records-card">${toolbarHtml(rows)}${state.dataTab === 'query' ? queryHtml(rows) : recordsHtml(rows)}</div><div class="data-bottom"><div class="integration-note">${icon('code')}<div><strong>Ready for your pipeline</strong><p>Map, table, and analytics share a single issue repository. Replace the sample adapter to connect your data.</p></div><code>src/data.js → issueRepository</code></div><span class="privacy-note">${icon('shield')} Public view · approximate locations</span></div></div>`;
}

function statsHtml(rows) {
  const review = rows.filter(i => i.verification_status === 'Needs review').length;
  const confidence = rows.length ? Math.round(rows.reduce((sum, i) => sum + i.detection_confidence, 0) / rows.length * 100) : 0;
  return `<div class="stat-grid">${[
    statCard({ label: 'Total records', value: state.issues.length, note: state.dataSource === 'pipeline' ? 'Pipeline output' : 'Accessible sample dataset', color: 'blue' }),
    statCard({ label: 'Filtered results', value: rows.length, note: `${percent(rows.length, state.issues.length)}% of all records`, color: 'cyan' }),
    statCard({ label: 'Awaiting verification', value: review, note: 'Needs a volunteer review', color: 'amber' }),
    statCard({ label: 'Avg. detection confidence', value: rows.length ? `${confidence}%` : '–', note: 'Across filtered records', color: 'green' }),
  ].join('')}</div>`;
}

function toolbarHtml(rows) {
  const records = state.dataTab !== 'query';
  const scope = state.scope ? `<span class="scope-chip">Selected issues <button data-action="clear-scope" aria-label="Clear selection scope">×</button></span>` : '<span class="subtle-label">All accessible Toronto issues</span>';
  return `<div class="table-toolbar"><div class="table-tabs" role="tablist"><button class="table-tab ${records ? 'active' : ''}" role="tab" aria-selected="${records}" data-tab="records">${icon('database')} Issue records <span>${rows.length}</span></button><button class="table-tab ${records ? '' : 'active'}" role="tab" aria-selected="${!records}" data-tab="query">${icon('code')} Query</button></div><div class="table-actions">${scope}<button class="button small" data-action="table-map">${icon('map')} View on map</button><button class="button small" data-action="export">${icon('download')} Export</button></div></div>`;
}

function recordsHtml(rows) {
  const pageRows = rows.slice((state.page - 1) * state.perPage, state.page * state.perPage);
  const selected = rows.filter(i => state.selected.includes(i.issue_id));
  const isSelected = i => state.selected.includes(i.issue_id);
  const head = columns.map(([key, title]) => `<th aria-sort="${state.sort === key ? (state.direction === 1 ? 'ascending' : 'descending') : 'none'}"><button data-sort="${key}">${title}<span>${state.sort === key ? (state.direction === 1 ? '↑' : '↓') : '↕'}</span></button></th>`).join('');
  const body = pageRows.map(i => `<tr class="${isSelected(i) ? 'row-selected' : ''}">
    <td><input type="checkbox" data-select-id="${i.issue_id}" aria-label="Select ${i.issue_id}" ${isSelected(i) ? 'checked' : ''}></td>
    <td><button class="table-id" data-issue="${i.issue_id}">${i.issue_id}</button></td>
    <td><span class="table-type" style="--type-color:${typeColor(i.issue_type)}">${typeIcon(i.issue_type)}${esc(i.issue_type)}</span></td>
    <td>${badge(i.severity)}</td>
    <td>${i.priority_score == null ? '–' : `<span class="priority-pill ${priorityLevel(i.priority_score)}" title="${esc((i.priority_reasons || []).join('\n'))}">${i.priority_score}</span>`}</td>
    <td>${badge(i.resolution_status)}</td>
    <td><span class="cell-main">${esc(i.neighbourhood_name)}</span><small class="cell-sub" title="${esc(wards[i.ward_id])}">Ward ${esc(i.ward_id)}</small></td>
    <td class="address-cell" title="${esc(i.address)}"><span class="cell-main">${esc(i.address)}</span><small class="cell-sub">${i.distance_m == null ? 'No nearby asset determined' : `${esc(i.asset_name)} · ${i.distance_m.toLocaleString()} m`}</small></td>
    <td>${date(i.first_seen_at)}</td><td>${date(i.last_seen_at)}</td><td class="num-cell">${i.sightings_count}</td>
    <td><span class="confidence-pill">${Math.round(i.detection_confidence * 100)}%</span></td>
    <td class="source-cell">${esc(i.source_category)}</td>
    <td><span class="verification-dot ${i.verification_status === 'Verified' ? 'verified' : ''}"></span>${esc(i.verification_status)}</td>
    <td><button class="icon-button" data-save="${i.issue_id}" aria-label="${state.saved.includes(i.issue_id) ? 'Unsave' : 'Save'} ${i.issue_id}">${icon('bookmark', state.saved.includes(i.issue_id) ? 'saved-icon' : '')}</button></td>
  </tr>`).join('');
  const selectionBar = selected.length ? `<div class="table-selection-bar"><span>${icon('check')} <strong>${selected.length}</strong> selected</span><div><button class="text-button" data-action="save-table-selection">${icon('bookmark')} Save</button><button class="text-button" data-action="export-selected">${icon('download')} Export selected</button><button class="text-button" data-action="clear-table-selection">Clear selection</button></div></div>` : '';
  const range = rows.length ? `Showing ${(state.page - 1) * state.perPage + 1}–${Math.min(rows.length, state.page * state.perPage)} of ${rows.length}` : '0 results';
  return `${selectionBar}<div class="table-scroll"><table><thead><tr><th><input type="checkbox" id="select-page" aria-label="Select visible rows" ${pageRows.length && pageRows.every(isSelected) ? 'checked' : ''}></th>${head}<th></th></tr></thead><tbody>${body}</tbody></table>${rows.length ? '' : emptyHtml('No issues match these filters', 'Reset filters or try another area.')}</div><div class="table-pagination"><span>${range} ${state.selected.length ? `<strong>· ${state.selected.length} selected</strong>` : ''}</span><div><select id="page-size" aria-label="Rows per page">${[10, 20, 50].map(n => `<option ${n === state.perPage ? 'selected' : ''} value="${n}">${n} per page</option>`).join('')}</select><button class="icon-button" data-page="${state.page - 1}" ${state.page === 1 ? 'disabled' : ''} aria-label="Previous page">${icon('back')}</button><span class="page-number">${state.page}</span><button class="icon-button" data-page="${state.page + 1}" ${state.page * state.perPage >= rows.length ? 'disabled' : ''} aria-label="Next page">${icon('arrow')}</button></div></div>`;
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
  return [
    'SELECT issue_id, issue_type, severity, priority_score, resolution_status,',
    '       neighbourhood_name, ward_id, address, first_seen_at,',
    '       last_seen_at, sightings_count, detection_confidence,',
    '       source_category, verification_status',
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
  document.querySelectorAll('[data-select-id]').forEach(c => c.onchange = () => {
    state.selected = c.checked ? [...new Set([...state.selected, c.dataset.selectId])] : state.selected.filter(id => id !== c.dataset.selectId);
    render();
  });
  document.querySelector('#select-page').onchange = e => {
    const ids = [...document.querySelectorAll('[data-select-id]')].map(c => c.dataset.selectId);
    state.selected = e.target.checked ? [...new Set([...state.selected, ...ids])] : state.selected.filter(id => !ids.includes(id));
    render();
  };
}
