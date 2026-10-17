// Dashboard: a city overview built from the same filtered records as the map and table.
import { categories, demoPipeline, wards, ELECTION_DATE, DEMO_DATE } from '../data.js';
import { icon } from '../icons.js';
import { DAY, esc, date, age, typeIcon, percent, countBy, wardLabel, plural } from '../format.js';
import { state, filtered, previousPeriod } from '../state.js';
import { statCard, emptyHtml, issueRow } from '../ui.js';
import { nav, updateFilteredView, render } from '../app.js';
import { apiStatus, writeDigest } from '../api.js';

const SAMPLE_SPAN_DAYS = 90; // the sample data covers the 90 days up to DEMO_DATE
const statuses = ['Open', 'In review', 'Resolved'], statusColors = ['#42a5f5', '#ffb452', '#25d5ac'];
const windowDays = () => Number(state.filters.days) || SAMPLE_SPAN_DAYS;
// Only compare when the previous period is fully inside the sample data; otherwise the "change" would be invented.
const comparison = () => state.filters.days && Number(state.filters.days) * 2 <= SAMPLE_SPAN_DAYS ? previousPeriod() : null;
const isHigh = i => i.severity === 'High';

/** Issue counts per day (windows up to 31 days) or per week, oldest first. */
function buckets(rows, days = windowDays()) {
  const size = days <= 31 ? 1 : 7, count = Math.ceil(days / size), counts = Array(count).fill(0);
  for (const i of rows) { const a = age(i); if (a < days) counts[count - 1 - Math.floor(a / size)]++; }
  return { counts, size };
}
function change(current, previous) {
  if (previous === null) return '';
  if (!previous) return current ? 'None in the previous period' : 'No change';
  const pct = Math.round((current - previous) / previous * 100);
  return `<span class="delta ${pct > 0 ? 'up' : pct < 0 ? 'down' : ''}">${Math.abs(pct)}%</span> vs previous ${state.filters.days} days`;
}
function sparkline(counts) {
  if (counts.length < 2) return '';
  const max = Math.max(1, ...counts), points = counts.map((n, j) => `${(j / (counts.length - 1) * 100).toFixed(1)},${(28 - n / max * 24).toFixed(1)}`).join(' ');
  return `<svg class="stat-sparkline" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true"><polyline points="${points}"/></svg>`;
}

function statsHtml(rows, previous) {
  const high = rows.filter(isHigh), review = rows.filter(i => i.resolution_status === 'In review').length, resolved = rows.filter(i => i.resolution_status === 'Resolved').length;
  const scope = state.filters.days ? `In the last ${state.filters.days} days` : 'All sample records';
  return `<div class="stat-grid">${[
    statCard({ icon: 'database', label: 'Total issues', value: rows.length, note: change(rows.length, previous?.length ?? null) || scope, color: 'blue', extra: sparkline(buckets(rows).counts) }),
    statCard({ icon: 'warning', label: 'High priority', value: high.length, note: change(high.length, previous ? previous.filter(isHigh).length : null) || `${percent(high.length, rows.length)}% of filtered issues`, color: 'red', extra: sparkline(buckets(high).counts) }),
    statCard({ icon: 'clock', label: 'In review', value: review, note: `${percent(review, rows.length)}% of filtered issues`, color: 'amber' }),
    statCard({ icon: 'check', label: 'Resolved', value: resolved, note: `${percent(resolved, rows.length)}% resolution rate`, color: 'green' }),
  ].join('')}</div>`;
}

function timelineHtml(rows) {
  const { counts, size } = buckets(rows), n = counts.length;
  const max = Math.max(2, Math.ceil(Math.max(...counts) / 2) * 2); // even, so the middle label is a whole number
  const x = j => n === 1 ? 260 : j * 520 / (n - 1), y = v => 150 - v / max * 120;
  const start = j => new Date(Date.parse(DEMO_DATE) - ((n - 1 - j) * size + size - 1) * DAY);
  const points = counts.map((v, j) => `${x(j).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const labels = [...new Set([0, Math.round((n - 1) / 3), Math.round(2 * (n - 1) / 3), n - 1])];
  const unit = size === 1 ? 'day' : 'week';
  return `<section class="card trend-card"><div class="card-header"><h2>${icon('chart')} Detection timeline</h2><span class="subtle-label">${date(start(0))} – ${date(DEMO_DATE)} · per ${unit}</span></div><div class="trend-chart"><div class="chart-y"><span>${max}</span><span>${max / 2}</span><span>0</span></div><svg viewBox="0 0 520 170" preserveAspectRatio="none" role="img" aria-label="Sample issue detections per ${unit}"><defs><linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#23adfa" stop-opacity=".32"/><stop offset="100%" stop-color="#23adfa" stop-opacity="0"/></linearGradient></defs>${[30, 90, 150].map(v => `<path d="M0 ${v}H520" stroke="#203346" stroke-dasharray="3 4"/>`).join('')}<polygon points="0,170 ${points} 520,170" fill="url(#chart-fill)"/><polyline points="${points}" fill="none" stroke="#3dbbff" stroke-width="3" vector-effect="non-scaling-stroke"/>${counts.map((v, j) => `<circle cx="${x(j).toFixed(1)}" cy="${y(v).toFixed(1)}" r="${n > 20 ? 2.5 : 3.5}" fill="#b4e7ff" stroke="#1a90da"><title>${size === 1 ? date(start(j)) : `Week of ${date(start(j))}`}: ${v} sample issues</title></circle>`).join('')}</svg></div><div class="chart-x">${labels.map(j => `<span>${date(start(j))}</span>`).join('')}</div><p class="chart-caption">Observed sample detections, not a forecast.</p></section>`;
}

function breakdownHtml(rows) {
  const counts = Object.keys(categories).map(type => ({ type, count: rows.filter(i => i.issue_type === type).length })).sort((a, b) => b.count - a.count);
  const max = Math.max(1, ...counts.map(c => c.count));
  return `<section class="card"><div class="card-header"><h2>${icon('filter')} Issue breakdown</h2></div><div class="breakdown">${counts.map(({ type, count }) => `<button data-type-filter="${type}"><span style="color:${categories[type].color}">${typeIcon(type)}</span><span>${type}</span><div class="bar-track"><i style="width:${count / max * 100}%;background:${categories[type].color}"></i></div><strong>${count}</strong></button>`).join('')}</div></section>`;
}

function resolutionHtml(rows) {
  let accumulated = 0;
  const gradient = statuses.map((s, j) => { const start = accumulated; accumulated += rows.filter(i => i.resolution_status === s).length / Math.max(1, rows.length) * 100; return `${statusColors[j]} ${start}% ${accumulated}%`; }).join(',');
  return `<section class="card"><div class="card-header"><h2>${icon('clock')} Resolution status</h2></div><div class="donut-wrap"><div class="donut" style="background:conic-gradient(${rows.length ? gradient : '#1b2b3e 0% 100%'})"><div><strong>${rows.length}</strong><span>Sample issues</span></div></div></div><div class="status-legend">${statuses.map((s, j) => `<span><i style="background:${statusColors[j]}"></i>${s}<strong>${rows.filter(i => i.resolution_status === s).length}</strong></span>`).join('')}</div></section>`;
}

function wardDigestHtml(rows, previous) {
  const ward = state.filters.area.startsWith('ward:') ? state.filters.area.slice(5) : '';
  const daysLeft = Math.ceil((Date.parse(ELECTION_DATE) - Date.parse(DEMO_DATE)) / DAY);
  const picker = `<select class="ward-select" id="ward-pick" aria-label="Choose a ward"><option value="">Choose a ward…</option>${Object.entries(wards).map(([id, name]) => `<option value="${id}" ${id === ward ? 'selected' : ''}>Ward ${id} · ${esc(name)}</option>`).join('')}</select>`;
  const election = `<span class="election-chip">${icon('ballot')} Municipal election · ${date(ELECTION_DATE)} · ${daysLeft} days away</span>`;
  let body;
  if (!ward) {
    const ranking = Object.entries(countBy(rows, 'ward_id')).sort((a, b) => b[1] - a[1]).slice(0, 5);
    body = `<p class="digest-text">Pick a ward for a short summary of its filtered issues. Busiest wards for the current filters:</p>${ranking.length ? ranking.map(([id, count], j) => `<button class="hotspot-row" data-ward-filter="${id}"><span class="rank">${j + 1}</span><span>${esc(wardLabel(id))}</span><div class="bar-track"><i style="width:${count / ranking[0][1] * 100}%"></i></div><strong>${count}</strong>${icon('arrow')}</button>`).join('') : emptyHtml('No wards', 'Try clearing your filters.')}`;
  } else if (!rows.length) {
    body = `<p class="digest-text">No sample issues in <strong>${esc(wardLabel(ward))}</strong> match the current filters. Try a longer time range or clear other filters.</p>`;
  } else {
    const [topType, topCount] = Object.entries(countBy(rows, 'issue_type')).sort((a, b) => b[1] - a[1])[0];
    const [topPlace, placeCount] = Object.entries(countBy(rows, 'address')).sort((a, b) => b[1] - a[1])[0];
    const high = rows.filter(isHigh).length, resolved = rows.filter(i => i.resolution_status === 'Resolved').length;
    const delta = previous ? previous.length ? ` (${rows.length >= previous.length ? 'up' : 'down'} ${Math.abs(Math.round((rows.length - previous.length) / previous.length * 100))}% from the previous ${state.filters.days} days)` : ' (none in the previous period)' : '';
    const period = state.filters.days ? `In the last ${state.filters.days} days` : 'Across all sample records';
    const tiles = [['Open', rows.filter(i => i.resolution_status === 'Open').length], ['In review', rows.filter(i => i.resolution_status === 'In review').length], ['Resolved', resolved], ['Needs verification', rows.filter(i => i.verification_status === 'Needs review').length]];
    body = `<p class="digest-text">${period}, <strong>${esc(wardLabel(ward))}</strong> logged <strong>${plural(rows.length, state.dataSource === 'sample' ? 'sample issue' : 'issue')}</strong>${delta}. The most common type was <strong>${esc(topType)}</strong> (${topCount}). <strong>${high}</strong> ${high === 1 ? 'is' : 'are'} high severity and <strong>${percent(resolved, rows.length)}%</strong> ${resolved === 1 ? 'is' : 'are'} resolved. The busiest location was <strong>${esc(topPlace)}</strong> (${plural(placeCount, 'issue')}).</p>${writtenDigestHtml(ward, rows)}<div class="digest-stats">${tiles.map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join('')}</div>`;
  }
  return `<section class="card ward-digest"><div class="card-header"><h2>${icon('ballot')} Ward digest</h2>${picker}</div><div class="digest-body">${election}${body}<div class="digest-foot">${icon('shield')}<span>The first paragraph is a fixed template built from the filtered records: counts are observed, not inferred. Ward boundaries are the City of Toronto’s 25 wards.</span></div></div></section>`;
}

// ---- Written digests: the pipeline's summary for the ward, or Gemini on demand through scripts/serve.py ----
const digestCache = new Map();
/** Stats for one ward in the shape of analysis/areas.json, so live and pipeline digests use the same prompt. */
function areaStats(ward, rows) {
  const open = rows.filter(i => i.resolution_status !== 'Resolved');
  const sortDesc = counts => Object.fromEntries(Object.entries(counts).sort((a, b) => b[1] - a[1]));
  return {
    name: ward, label: wards[ward], period: state.filters.days ? `last ${state.filters.days} days` : 'all available records',
    total: rows.length, open: open.length, verified: rows.filter(i => i.verification_status === 'Verified').length,
    sightings: rows.reduce((n, i) => n + (i.sightings_count || 1), 0),
    by_type: sortDesc(countBy(rows, 'issue_type')), by_severity: sortDesc(countBy(rows, 'severity')), by_status: sortDesc(countBy(rows, 'resolution_status')),
    new_recent: rows.filter(i => age(i) < 7).length, new_previous: rows.filter(i => age(i) >= 7 && age(i) < 14).length,
    top_priority: open.sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0)).slice(0, 3).map(i => ({ issue_id: i.issue_id, issue_type: i.issue_type, address: i.address, priority_score: i.priority_score })),
  };
}
const digestKey = (ward, rows) => JSON.stringify(areaStats(ward, rows));
function writtenDigestHtml(ward, rows) {
  const fromPipeline = state.dataSource === 'pipeline' && state.pipeline.areas?.by_area?.ward_id?.find(a => String(a.name) === ward)?.summary;
  if (fromPipeline) {
    const gemini = fromPipeline.method?.startsWith('gemini');
    return `<div class="digest-written"><p>${esc(fromPipeline.text)}</p><span>${gemini ? `Written by Gemini (${esc(fromPipeline.method.slice(7))}) from this ward’s counts during the pipeline run` : 'Template summary from the pipeline run'} · covers all pipeline issues in the ward, not just the current filters</span></div>`;
  }
  const cached = digestCache.get(digestKey(ward, rows));
  if (cached?.text) return `<div class="digest-written"><p>${esc(cached.text)}</p><span>Written by Gemini (${esc(cached.method.slice(7))}) from the counts below${state.dataSource === 'sample' ? ' · sample data' : ''}. Check it before sharing.</span></div>`;
  return `<div class="digest-written pending" id="digest-ai" hidden><button class="button small" id="write-digest">${icon('sun')} Write a summary with Gemini</button><span id="digest-error" class="form-error"></span></div>`;
}

function pipelineHtml() {
  const counts = state.dataSource === 'pipeline' && state.pipeline.report?.counts;
  if (counts) {
    // Real counts from the latest `python -m analysis` run (data/analyzed/report.json).
    const stages = [['Input records', counts.input_records], ['Civic issues', counts.input_records - (counts.skipped_not_an_issue || 0)], ['Located in Toronto', counts.located], ['Sightings', counts.sightings], ['Issues after merging repeats', counts.issues], ['Verified', state.issues.filter(i => i.verification_status === 'Verified').length]];
    const max = Math.max(1, stages[0][1]);
    return `<section class="card"><div class="card-header"><h2>${icon('funnel')} Pipeline funnel</h2><span class="subtle-label">Latest pipeline run</span></div><div class="funnel">${stages.map(([label, value], j) => `<div class="funnel-row derived"><span>${label}${j ? `<small>${percent(value, stages[j - 1][1])}% of previous</small>` : '<small>From the photo analysis</small>'}</span><div class="bar-track"><i style="width:${Math.max(2, value / max * 100)}%"></i></div><strong>${value.toLocaleString()}</strong></div>`).join('')}</div><p class="funnel-foot">From data/analyzed/report.json, generated ${esc(new Date(state.pipeline.report.generated_at).toLocaleString('en-CA', { dateStyle: 'medium', timeStyle: 'short' }))}.</p></section>`;
  }
  const recent = state.issues.filter(i => age(i) < demoPipeline.window_days);
  const stages = [
    ['Posts scanned', demoPipeline.posts_scanned, false], ['With images', demoPipeline.with_images, false],
    ['Toronto-relevant', demoPipeline.toronto_relevant, false], ['Public scenes', demoPipeline.public_scenes, false],
    ['Issues detected', recent.length, true], ['Verified', recent.filter(i => i.verification_status === 'Verified').length, true],
  ];
  const top = Math.log10(stages[0][1]);
  return `<section class="card"><div class="card-header"><h2>${icon('funnel')} Pipeline funnel</h2><span class="subtle-label">Last ${demoPipeline.window_days} days · unfiltered</span></div><div class="funnel">${stages.map(([label, value, fromData], j) => `<div class="funnel-row ${fromData ? 'derived' : ''}"><span>${label}${j ? `<small>${percent(value, stages[j - 1][1])}% of previous</small>` : '<small>Bluesky, Mastodon, Reddit</small>'}</span><div class="bar-track"><i style="width:${Math.max(2, Math.log10(Math.max(1, value)) / top * 100)}%"></i></div><strong>${value.toLocaleString()}</strong></div>`).join('')}</div><p class="funnel-foot">The first four stages are sample ingestion metrics until the pipeline is connected; issues detected and verified come from the dataset. Bars use a log scale.</p></section>`;
}

export function dashboardHtml() {
  const rows = filtered(), previous = comparison();
  const counts = Object.keys(categories).map(type => ({ type, count: rows.filter(i => i.issue_type === type).length })).sort((a, b) => b.count - a.count);
  const areas = Object.entries(countBy(rows, i => i.neighbourhood_id)).map(([id, count]) => ({ id, count, name: rows.find(i => i.neighbourhood_id === id).neighbourhood_name })).sort((a, b) => b.count - a.count).slice(0, 5);
  const recent = rows.slice().sort((a, b) => b.first_seen_at.localeCompare(a.first_seen_at)).slice(0, 4);
  return `<div class="dashboard-page">${statsHtml(rows, previous)}
    <div class="dashboard-charts">${timelineHtml(rows)}${breakdownHtml(rows)}${resolutionHtml(rows)}</div>
    <div class="dashboard-civic">${wardDigestHtml(rows, previous)}${pipelineHtml()}</div>
    <div class="dashboard-lower">
      <section class="card"><div class="card-header"><h2>${icon('pin')} Neighbourhood hotspots</h2><span class="subtle-label">Sample counts</span></div>${areas.length ? areas.map(({ id, name, count }, j) => `<button class="hotspot-row" data-area-filter="${esc(id)}"><span class="rank">${j + 1}</span><span>${esc(name)}</span><div class="bar-track"><i style="width:${count / areas[0].count * 100}%"></i></div><strong>${count}</strong>${icon('arrow')}</button>`).join('') : emptyHtml('No neighbourhoods', 'Try clearing your filters.')}</section>
      <section class="card"><div class="card-header"><h2>${icon('clock')} Recent detections</h2><button class="text-button" data-nav="data">View all ↗</button></div>${recent.map(issueRow).join('') || emptyHtml('No detections', 'Try clearing your filters.')}</section>
      <section class="card insights-card"><div class="card-header"><h2>${icon('sun')} At a glance</h2></div><div class="insight"><span class="stat-icon red">${icon('warning')}</span><div><span>Most common issue</span><strong>${counts[0]?.count ? counts[0].type : 'No issues'}</strong><small>${counts[0]?.count || 0} of ${rows.length} filtered records</small></div></div><div class="insight"><span class="stat-icon blue">${icon('pin')}</span><div><span>Highest sample activity</span><strong>${esc(areas[0]?.name || 'No areas')}</strong><small>Based on sample record count</small></div></div><div class="insight-foot">${icon('shield')} ${state.dataSource === 'sample' ? 'These insights describe fictional records. Connect verified data before drawing conclusions.' : 'Counts cover issues found in public photos and uploads, not every issue in the city.'}</div></section>
    </div></div>`;
}

export function bindDashboard() {
  document.querySelectorAll('[data-type-filter]').forEach(b => b.onclick = () => { state.filters.type = b.dataset.typeFilter; nav('data'); });
  document.querySelectorAll('[data-area-filter]').forEach(b => b.onclick = () => { state.filters.area = b.dataset.areaFilter; nav('data'); });
  document.querySelectorAll('[data-ward-filter]').forEach(b => b.onclick = () => { state.filters.area = `ward:${b.dataset.wardFilter}`; updateFilteredView(); });
  document.querySelector('#ward-pick').onchange = e => { state.filters.area = e.target.value ? `ward:${e.target.value}` : ''; updateFilteredView(); };
  const slot = document.querySelector('#digest-ai');
  if (!slot) return;
  apiStatus().then(status => {
    if (!status.gemini || !slot.isConnected) return;
    slot.hidden = false;
    slot.querySelector('#write-digest').onclick = async e => {
      const ward = state.filters.area.slice(5), rows = filtered(), button = e.currentTarget;
      button.disabled = true; button.textContent = 'Writing…';
      try {
        digestCache.set(digestKey(ward, rows), await writeDigest(areaStats(ward, rows)));
        render();
      } catch (error) {
        button.disabled = false; button.textContent = 'Try again';
        slot.querySelector('#digest-error').textContent = error.message;
      }
    };
  });
}
