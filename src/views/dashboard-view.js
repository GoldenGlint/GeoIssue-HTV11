// Dashboard: a city overview built from the same filtered records as the map and table.
import { categories, demoPipeline, wards, ELECTION_DATE, REFERENCE_DATE } from '../data.js';
import { icon } from '../icons.js';
import { DAY, esc, date, age, typeIcon, percent, countBy, wardLabel, plural } from '../format.js';
import { state, filtered, previousPeriod, isSampleData, sampleWord } from '../state.js';
import { statCard, emptyHtml, issueRow } from '../ui.js';
import { selectHtml } from '../select.js';
import { nav, updateFilteredView, render } from '../app.js';
import { apiStatus, writeDigest } from '../api.js';
import { activityPanelHtml, bindActivity } from '../activity.js';
import { mountChart, baseOption, lineOption, sparkOption, rowsOption, morphRows, bindRows, tipHtml, countTo, chartFor } from '../charts.js';

const SAMPLE_SPAN_DAYS = 90; // the simulated data covers the 90 days up to when it was loaded
const statuses = ['Open', 'In review', 'Resolved'], statusColors = ['var(--accent)', 'var(--warning)', 'var(--success)'];
let drawn = {}; // what the last dashboardHtml() charted, for bindDashboard() to draw
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
function sparkline(name, counts) {
  if (counts.length < 2) return '';
  (drawn.sparks ??= {})[name] = counts;
  return `<div class="stat-sparkline" data-spark="${name}" aria-hidden="true"></div>`;
}

function statsHtml(rows, previous) {
  const high = rows.filter(isHigh), review = rows.filter(i => i.resolution_status === 'In review').length, resolved = rows.filter(i => i.resolution_status === 'Resolved').length;
  const scope = state.filters.days ? `In the last ${state.filters.days} days` : `All ${sampleWord()}records`;
  return `<div class="stat-grid">${[
    statCard({ label: 'Total issues', value: rows.length, note: change(rows.length, previous?.length ?? null) || scope, color: 'blue', extra: sparkline('total', buckets(rows).counts) }),
    statCard({ label: 'High priority', value: high.length, note: change(high.length, previous ? previous.filter(isHigh).length : null) || `${percent(high.length, rows.length)}% of filtered issues`, color: 'red', extra: sparkline('high', buckets(high).counts) }),
    statCard({ label: 'In review', value: review, note: `${percent(review, rows.length)}% of filtered issues`, color: 'amber' }),
    statCard({ label: 'Resolved', value: resolved, note: `${percent(resolved, rows.length)}% resolution rate`, color: 'green' }),
  ].join('')}</div>`;
}

function timelineHtml(rows) {
  const { counts, size } = buckets(rows), n = counts.length, unit = size === 1 ? 'day' : 'week';
  const start = j => new Date(Date.parse(REFERENCE_DATE) - ((n - 1 - j) * size + size - 1) * DAY);
  const when = j => size === 1 ? date(start(j)) : `Week of ${date(start(j))}`, peak = counts.indexOf(Math.max(...counts));
  drawn.timeline = { labels: counts.map((_, j) => date(start(j))), values: counts, tips: j => tipHtml(counts[j].toLocaleString(), `${sampleWord()}${counts[j] === 1 ? 'issue' : 'issues'} · ${when(j)}`) };
  const summary = `Issue detections per ${unit} from ${date(start(0))} to ${date(REFERENCE_DATE)}: ${rows.length} in total${counts[peak] ? `, the most (${counts[peak]}) ${size === 1 ? 'on' : 'in the week of'} ${date(start(peak))}` : ''}.`;
  return `<section class="card trend-card"><div class="card-header"><h2>${icon('chart')} Detection timeline</h2><span class="subtle-label">${date(start(0))} – ${date(REFERENCE_DATE)} · per ${unit}</span></div><div class="trend-chart" id="timeline-chart" role="img" aria-label="${esc(summary)}"></div><p class="chart-caption">Observed ${sampleWord()}detections, not a forecast.</p></section>`;
}

function breakdownHtml(rows) {
  const counts = Object.keys(categories).map(type => ({ type, count: rows.filter(i => i.issue_type === type).length })).sort((a, b) => b.count - a.count);
  drawn.breakdown = counts.map(({ type, count }) => ({ key: type, name: type, icon: categories[type].icon, color: categories[type].color, value: count,
    tip: tipHtml(count.toLocaleString(), `${type} · ${percent(count, rows.length)}% of filtered issues`, categories[type].color, 'Select to open them in Data Explorer') }));
  return `<section class="card"><div class="card-header"><h2>${icon('filter')} Issue breakdown</h2></div><div class="row-chart breakdown-chart" style="--rows:${counts.length}"><div class="chart-canvas" aria-hidden="true"></div><div class="chart-rows">${counts.map(({ type, count }) => `<button data-type-filter="${esc(type)}" aria-label="${esc(type)}: ${plural(count, 'issue')}. Open them in Data Explorer"><span>${esc(type)}</span><strong>${count}</strong></button>`).join('')}</div></div></section>`;
}

function resolutionHtml(rows) {
  const counts = statuses.map(s => rows.filter(i => i.resolution_status === s).length);
  drawn.status = { counts, total: rows.length };
  return `<section class="card status-card"><div class="card-header"><h2>${icon('clock')} Resolution status</h2></div><div class="donut-wrap"><div class="donut"><div class="chart-canvas" aria-hidden="true"></div><div class="donut-center" aria-hidden="true"><strong data-donut-value>${rows.length}</strong><span data-donut-label>issues</span></div></div></div><div class="status-legend">${statuses.map((s, j) => `<button data-status-filter="${s}" aria-label="${s}: ${plural(counts[j], 'issue')}. Open them in Data Explorer"><i style="background:${statusColors[j]}"></i>${s}<strong>${counts[j]}</strong></button>`).join('')}</div></section>`;
}
/** The donut: a ring split by status with a 2px gap between slices; the centre label is its readout. */
function statusOption(t, { counts, total }) {
  const colors = [t.accent, t.warning, t.success], slices = statuses.map((name, j) => ({ name, value: counts[j], itemStyle: { color: colors[j] } })).filter(d => d.value);
  return baseOption(t, {
    tooltip: { show: false },
    series: [{
      type: 'pie', radius: ['70%', '94%'], startAngle: 90, padAngle: slices.length > 1 ? 2 : 0, itemStyle: { borderRadius: 3 }, label: { show: false }, labelLine: { show: false },
      data: total ? slices : [{ name: 'None', value: 1, itemStyle: { color: t.surface3 }, emphasis: { disabled: true } }], silent: !total,
      emphasis: { scale: true, scaleSize: 4, focus: 'self' }, blur: { itemStyle: { opacity: .3 } },
      animationType: 'expansion', animationDuration: 800, animationEasing: 'cubicOut', animationDelay: 60,
    }],
  });
}

function wardDigestHtml(rows, previous) {
  const ward = state.filters.area.startsWith('ward:') ? state.filters.area.slice(5) : '';
  const daysLeft = Math.ceil((Date.parse(ELECTION_DATE) - Date.parse(REFERENCE_DATE)) / DAY);
  const picker = selectHtml({ id: 'ward-pick', label: 'Ward', options: [['', 'All wards'], ...Object.entries(wards).map(([id, name]) => [id, `Ward ${id} · ${name}`])], value: ward, search: 'Search wards', className: 'ward-select' });
  const election = `<span class="election-chip">${icon('ballot')} Municipal election · ${date(ELECTION_DATE)} · ${daysLeft} days away</span>`;
  let body;
  if (!ward) {
    const ranking = Object.entries(countBy(rows, 'ward_id')).sort((a, b) => b[1] - a[1]).slice(0, 5);
    body = `<p class="digest-text">Pick a ward for a short summary of its filtered issues. Busiest wards for the current filters:</p>${ranking.length ? ranking.map(([id, count], j) => `<button class="hotspot-row" data-ward-filter="${id}"><span class="rank">${j + 1}</span><span>${esc(wardLabel(id))}</span><div class="bar-track"><i style="width:${count / ranking[0][1] * 100}%"></i></div><strong>${count}</strong>${icon('arrow')}</button>`).join('') : emptyHtml('No wards', 'Try clearing your filters.')}`;
  } else if (!rows.length) {
    body = `<p class="digest-text">No ${sampleWord()}issues in <strong>${esc(wardLabel(ward))}</strong> match the current filters. Try a longer time range or clear other filters.</p>`;
  } else {
    const [topType, topCount] = Object.entries(countBy(rows, 'issue_type')).sort((a, b) => b[1] - a[1])[0];
    const [topPlace, placeCount] = Object.entries(countBy(rows, 'address')).sort((a, b) => b[1] - a[1])[0];
    const high = rows.filter(isHigh).length, resolved = rows.filter(i => i.resolution_status === 'Resolved').length;
    const delta = previous ? previous.length ? ` (${rows.length >= previous.length ? 'up' : 'down'} ${Math.abs(Math.round((rows.length - previous.length) / previous.length * 100))}% from the previous ${state.filters.days} days)` : ' (none in the previous period)' : '';
    const period = state.filters.days ? `In the last ${state.filters.days} days${isSampleData() ? ' of sample data' : ''}` : `Across all ${sampleWord()}records`;
    const tiles = [['Open', rows.filter(i => i.resolution_status === 'Open').length], ['In review', rows.filter(i => i.resolution_status === 'In review').length], ['Resolved', resolved], ['Needs verification', rows.filter(i => i.verification_status === 'Needs review').length]];
    body = `<p class="digest-text">${period}, <strong>${esc(wardLabel(ward))}</strong> logged <strong>${plural(rows.length, state.dataSource === 'simulated' ? 'sample issue' : 'issue')}</strong>${delta}. The most common type was <strong>${esc(topType)}</strong> (${topCount}). <strong>${high}</strong> ${high === 1 ? 'is' : 'are'} high severity and <strong>${percent(resolved, rows.length)}%</strong> ${resolved === 1 ? 'is' : 'are'} resolved. The busiest location was <strong>${esc(topPlace)}</strong> (${plural(placeCount, 'issue')}).</p>${writtenDigestHtml(ward, rows)}<div class="digest-stats">${tiles.map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join('')}</div>`;
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
  const fromPipeline = state.dataSource === 'collected' && state.pipeline.areas?.by_area?.ward_id?.find(a => String(a.name) === ward)?.summary;
  if (fromPipeline) {
    const gemini = fromPipeline.method?.startsWith('gemini');
    return `<div class="digest-written"><p>${esc(fromPipeline.text)}</p><span>${gemini ? `Written by Gemini (${esc(fromPipeline.method.slice(7))}) from this ward’s counts during the pipeline run` : 'Template summary from the pipeline run'} · covers all pipeline issues in the ward, not just the current filters</span></div>`;
  }
  const cached = digestCache.get(digestKey(ward, rows));
  if (cached?.text) return `<div class="digest-written"><p>${esc(cached.text)}</p><span>Written by Gemini (${esc(cached.method.slice(7))}) from the counts below${state.dataSource === 'simulated' ? ' · simulated data' : ''}. Check it before sharing.</span></div>`;
  return `<div class="digest-written pending" id="digest-ai" hidden><button class="button small" id="write-digest">${icon('sparkles')} Write a summary with Gemini</button><span id="digest-error" class="form-error"></span></div>`;
}

function pipelineHtml() {
  const report = state.dataSource === 'collected' ? state.pipeline.report : null, verified = state.issues.filter(i => i.verification_status === 'Verified').length;
  let stages, subtitle, foot, firstNote;
  if (report?.counts) {
    // The analysis run's own counts (data/analyzed/report.json), so every number is measured.
    const c = report.counts, found = (c.sightings || 0) + (c.dropped || 0);
    stages = [['Photos analysed', c.records ?? c.input_records ?? 0, true], ['Civic issues found', found, true], ['Located in Toronto', c.sightings || 0, true], ['Unique issues', c.issues || 0, true], ['Verified', verified, true]];
    subtitle = `Last analysis run · ${date(report.generated_at)}`;
    firstNote = 'From the photo analysis';
    const reasons = Object.entries(countBy(report.dropped || [], 'reason')).map(([reason, n]) => `${n} ${reason}`).join(', ');
    foot = `Counts from the analysis report. Duplicate sightings were merged into unique issues${reasons ? `; dropped: ${reasons}` : ''}. Bars use a log scale.`;
  } else {
    const recent = state.issues.filter(i => age(i) < demoPipeline.window_days);
    stages = [['Posts scanned', demoPipeline.posts_scanned, false], ['With images', demoPipeline.with_images, false], ['Toronto-relevant', demoPipeline.toronto_relevant, false], ['Public scenes', demoPipeline.public_scenes, false],
      ['Issues detected', recent.length, true], ['Verified', recent.filter(i => i.verification_status === 'Verified').length, true]];
    subtitle = `Last ${demoPipeline.window_days} days · sample metrics`;
    firstNote = 'Bluesky, Mastodon, Reddit';
    foot = 'The first four stages are sample ingestion metrics until the pipeline is connected; issues detected and verified come from the dataset. Bars use a log scale.';
  }
  const top = Math.log10(Math.max(10, stages[0][1]));
  drawn.funnel = stages.map(([label, value, fromData], j) => ({ key: label, name: label, note: j ? `${percent(value, stages[j - 1][1])}% of previous` : firstNote, derived: fromData,
    value: Math.max(2, Math.log10(Math.max(1, value)) / top * 100), display: value.toLocaleString() }));
  return `<section class="card"><div class="card-header"><h2>${icon('funnel')} Pipeline funnel</h2><span class="subtle-label">${subtitle}</span></div><div class="row-chart funnel-chart" style="--rows:${stages.length}"><div class="chart-canvas" aria-hidden="true"></div><div class="chart-rows">${drawn.funnel.map(r => `<div><span>${esc(r.name)}<small>${esc(r.note)}</small></span><strong>${r.display}</strong></div>`).join('')}</div></div><p class="funnel-foot">${esc(foot)}</p></section>`;
}

export function dashboardHtml() {
  const rows = filtered(), previous = comparison();
  drawn = {};
  const counts = Object.keys(categories).map(type => ({ type, count: rows.filter(i => i.issue_type === type).length })).sort((a, b) => b.count - a.count);
  const areas = Object.entries(countBy(rows, i => i.neighbourhood_id)).map(([id, count]) => ({ id, count, name: rows.find(i => i.neighbourhood_id === id).neighbourhood_name })).sort((a, b) => b.count - a.count).slice(0, 5);
  const recent = rows.slice().sort((a, b) => b.first_seen_at.localeCompare(a.first_seen_at)).slice(0, 4);
  return `<div class="dashboard-page">${statsHtml(rows, previous)}
    ${activityPanelHtml(state.dataBackend, state.dataSource)}
    <div class="dashboard-charts">${timelineHtml(rows)}${breakdownHtml(rows)}${resolutionHtml(rows)}</div>
    <div class="dashboard-civic">${wardDigestHtml(rows, previous)}${pipelineHtml()}</div>
    <div class="dashboard-lower">
      <section class="card"><div class="card-header"><h2>${icon('pin')} Neighbourhood hotspots</h2><span class="subtle-label">${isSampleData() ? 'Sample counts' : 'Counts'}</span></div>${areas.length ? areas.map(({ id, name, count }, j) => `<button class="hotspot-row" data-area-filter="${esc(id)}"><span class="rank">${j + 1}</span><span>${esc(name)}</span><div class="bar-track"><i style="width:${count / areas[0].count * 100}%"></i></div><strong>${count}</strong>${icon('arrow')}</button>`).join('') : emptyHtml('No neighbourhoods', 'Try clearing your filters.')}</section>
      <section class="card"><div class="card-header"><h2>${icon('clock')} Recent detections</h2><button class="text-button" data-nav="data">View all ↗</button></div>${recent.map(issueRow).join('') || emptyHtml('No detections', 'Try clearing your filters.')}</section>
      <section class="card insights-card"><div class="card-header"><h2>${icon('lightbulb')} At a glance</h2></div><div class="insight"><span class="stat-icon red">${icon('warning')}</span><div><strong>${counts[0]?.count ? counts[0].type : 'No issues'}</strong><small>Most common issue · ${counts[0]?.count || 0} of ${rows.length} filtered records</small></div></div><div class="insight"><span class="stat-icon blue">${icon('pin')}</span><div><strong>${esc(areas[0]?.name || 'No areas')}</strong><small>Highest ${sampleWord()}activity · by ${sampleWord()}record count</small></div></div><div class="insight-foot">${icon('shield')} ${state.dataSource === 'simulated' ? 'These insights describe fictional records. Connect verified data before drawing conclusions.' : 'Counts cover issues found in public photos and uploads, not every issue in the city.'}</div></section>
    </div></div>`;
}

function drawCharts() {
  const { sparks = {}, timeline, breakdown, status, funnel } = drawn;
  document.querySelectorAll('[data-spark]').forEach(el => mountChart(el, `spark:${el.dataset.spark}`, t => sparkOption(t, sparks[el.dataset.spark], el.dataset.spark === 'high' ? t.dangerText : t.accentText)));
  const trend = document.querySelector('#timeline-chart');
  mountChart(trend, 'timeline', t => lineOption(t, { ...timeline, height: trend.clientHeight }));
  const types = document.querySelector('.breakdown-chart');
  mountChart(types.querySelector('.chart-canvas'), 'breakdown', (t, el) => rowsOption(t, el, breakdown, { delay: 80 }), { morph: morphRows });
  bindRows(types);
  const stages = document.querySelector('.funnel-chart');
  mountChart(stages.querySelector('.chart-canvas'), 'funnel', (t, el) => rowsOption(t, el, funnel.map(r => ({ ...r, color: r.derived ? t.success : t.accent,
    tip: tipHtml(r.display, r.name, r.derived ? t.success : t.accent, r.note) })), { max: 100 }), { morph: morphRows });
  bindRows(stages);
  drawDonut(status);
}

/** Hovering a slice or a legend row lifts that slice, fades the rest and turns the centre label into its readout. */
function drawDonut({ counts, total }) {
  const card = document.querySelector('.status-card'), ring = card.querySelector('.chart-canvas');
  const value = card.querySelector('[data-donut-value]'), label = card.querySelector('[data-donut-label]'), rows = card.querySelectorAll('[data-status-filter]');
  const show = name => {
    const j = statuses.indexOf(name);
    rows.forEach((row, k) => row.classList.toggle('is-active', k === j));
    countTo(value, j < 0 ? total : counts[j], { duration: 260 });
    label.textContent = j < 0 ? 'issues' : name;
  };
  const pick = name => { state.filters.status = name; nav('data'); };
  mountChart(ring, 'status', t => statusOption(t, { counts, total }), { onDraw: (chart, previous) => {
    countTo(value, total, { from: previous ? previous.series[0].data.reduce((sum, d) => sum + (d.name === 'None' ? 0 : d.value), 0) : 0, duration: 800 });
    chart.on('mouseover', ({ name }) => show(name));
    chart.on('mouseout', () => show(null));
    chart.on('click', ({ name }) => statuses.includes(name) && pick(name));
  } });
  rows.forEach(row => {
    const name = row.dataset.statusFilter, slice = { type: 'highlight', seriesIndex: 0, name };
    const on = () => { if (!counts[statuses.indexOf(name)]) return; chartFor(ring)?.dispatchAction(slice); show(name); };
    const off = () => { chartFor(ring)?.dispatchAction({ ...slice, type: 'downplay' }); show(null); };
    row.addEventListener('pointerenter', on); row.addEventListener('pointerleave', off);
    row.addEventListener('focus', on); row.addEventListener('blur', off);
    row.onclick = () => pick(name);
  });
}

export function bindDashboard() {
  bindActivity(state.dataSource, state.filters, state.dataBackend, ward => { state.filters.area = `ward:${ward}`; updateFilteredView(); });
  drawCharts();
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
