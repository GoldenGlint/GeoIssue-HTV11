// Independent report history. This panel deliberately has a narrower scope than issue filters.
import { icon } from './icons.js';
import { esc, date, wardLabel } from './format.js';
import { mountChart, lineOption, tipHtml } from './charts.js';

let timer, controller;
export function destroyActivity() {
  clearTimeout(timer);
  controller?.abort();
}

export function activityOptions(source, filters) {
  return new URLSearchParams({ dataset: source, days: filters.days || '90',
    ward: filters.area.startsWith('ward:') ? filters.area.slice(5) : '', type: filters.type });
}

export function tigerProofHtml(data) {
  const counts = data.reports_by_dataset, storage = data.shared_columnstore;
  const reduction = storage.storage_reduction_percent;
  const savings = reduction > 0 ? `${reduction.toFixed(1)}% smaller historical chunks` : `${storage.compressed_chunks || 0} chunks in columnstore`;
  return `<strong>${Number(counts.pipeline || 0).toLocaleString()}</strong> collected reports <span>·</span> <strong>${Number(counts.replay || 0).toLocaleString()}</strong> simulated reports <span>·</span> <strong>${esc(savings)}</strong><small>Live database totals. Storage measurement covers converted chunks across both datasets.</small>`;
}

export function activityPanelHtml(backend, source) {
  const live = backend.type === 'tiger';
  const text = backend.warning || (source === 'sample'
    ? 'Sample issues do not include an independent report history. Choose collected data or a simulated replay to explore activity.'
    : 'This file snapshot contains issue totals. Report activity appears when a connected history is available.');
  return `<section class="card activity-card" aria-labelledby="activity-title"><div class="card-header"><h2 id="activity-title">${icon('chart')} Report activity</h2><div class="activity-meta"><span class="subtle-label" id="activity-status">${live ? source === 'replay' ? 'Simulated replay · refreshes every 15 s' : 'Refreshes every 15 s' : 'Snapshot'}</span>${live ? `<button class="activity-source subtle-label" data-action="tiger-info" aria-label="About Tiger Data">${icon('database')} Tiger Data</button>` : ''}</div></div><div id="activity-content">${live ? '<p class="chart-caption" role="status">Loading report history…</p>' : `<p class="chart-caption">${esc(text)}</p>`}</div></section>`;
}

export function activityBody(data) {
  const series = data.series, max = Math.max(0, ...series.map(row => row.reports));
  const recent = data.wards.reduce((sum, ward) => sum + ward.recent, 0);
  const baseline = data.wards.reduce((sum, ward) => sum + ward.baseline, 0) / 7;
  const emerging = data.wards.filter(ward => ward.emerging);
  const scope = [data.ward ? wardLabel(data.ward) : 'All wards', data.type || 'All categories', `Last ${data.days} days`].join(' · ');
  const tiles = [['Independent reports', data.reports.toLocaleString()], ['Last 24 complete hours', recent.toLocaleString()], ['Previous 7 days · daily average', data.baseline_available ? baseline.toFixed(1) : 'Insufficient history']];
  return `<p class="activity-scope">${esc(scope)}${data.simulated ? ' · Fictional reports' : ''}</p>
    <div class="digest-stats activity-stats">${tiles.map(([label, value]) => `<div><span>${label}</span><strong>${esc(value)}</strong></div>`).join('')}</div>
    <div class="activity-chart"><span>Reports per hour</span><div class="chart-canvas" id="activity-chart" role="img" aria-label="Independent reports per hour over the last ${data.days} days, at most ${max} in one hour"></div></div>
    <div class="activity-hotspots"><h3>Emerging ward activity</h3>${emerging.length ? emerging.slice(0, 5).map(ward => `<button class="hotspot-row" data-activity-ward="${esc(ward.ward_id)}"><span>${icon('pin')}</span><span>${esc(wardLabel(ward.ward_id))}</span><strong>${ward.recent} reports · ${ward.ratio}× baseline</strong>${icon('arrow')}</button>`).join('') : `<p>${data.baseline_available ? 'No wards meet the surge threshold in this scope.' : 'At least eight days of report history are needed for the baseline.'}</p>`}</div>
    <p class="chart-caption">Activity follows ward, category and period only. Other filters apply to issue views. Multiple photos from one post count once per issue; these are reports, not unique issues or verified conditions.${data.undated_reports ? ` ${data.undated_reports} undated reports use their first ingestion time.` : ''}</p>
    <p class="chart-caption">Updated ${esc(new Date(data.as_of).toLocaleTimeString())} · Current hour is partial. Surge: at least 5 reports in the last 24 complete hours, at least 7 in the preceding week, and at least twice that week’s daily average.</p>`;
}

const hour = value => new Date(value).toLocaleString('en-CA', { month: 'short', day: 'numeric', hour: 'numeric', timeZone: 'America/Toronto' });
/** Draws the hourly line into a freshly rendered activity body; each refresh morphs from the last one. */
function drawActivity(slot, data) {
  const el = slot.querySelector('#activity-chart'), series = data.series, n = series.length;
  if (!el || !n) return;
  mountChart(el, 'activity', t => lineOption(t, { labels: series.map(row => date(row.bucket)), values: series.map(row => row.reports), ticks: [0, Math.floor(n / 2), n - 1], height: el.clientHeight,
    tips: j => tipHtml(series[j].reports.toLocaleString(), `${series[j].reports === 1 ? 'report' : 'reports'} · ${hour(series[j].bucket)}`) }));
}

export function bindActivity(source, filters, backend, onWard) {
  if (backend.type !== 'tiger') return;
  const slot = document.querySelector('#activity-content'), status = document.querySelector('#activity-status');
  const query = activityOptions(source, filters);
  let last;
  async function poll() {
    if (!slot?.isConnected) return;
    if (!document.hidden) {
      controller = new AbortController();
      const request = controller, timeout = setTimeout(() => request.abort(), 10000);
      try {
        const response = await fetch(`/api/activity?${query}`, { cache: 'no-store', signal: request.signal });
        if (!response.ok) throw new Error('Report history is temporarily unavailable.');
        const data = await response.json();
        if (!slot.isConnected) return;
        last = data;
        slot.innerHTML = activityBody(data);
        drawActivity(slot, data);
        status.textContent = `${data.simulated ? 'Simulated replay · refreshes' : 'Refreshes'} every 15 s`;
      } catch {
        if (!slot.isConnected) return;
        status.textContent = 'Connection unavailable';
        slot.innerHTML = `<p class="chart-caption" role="status">${last ? 'Showing the last loaded report history. Retrying automatically.' : 'Report history is temporarily unavailable. Retrying automatically.'}</p>${last ? activityBody(last) : ''}`;
        if (last) drawActivity(slot, last);
      } finally { clearTimeout(timeout); }
      slot.querySelectorAll('[data-activity-ward]').forEach(button => button.onclick = () => onWard(button.dataset.activityWard));
    }
    if (slot.isConnected) timer = setTimeout(poll, 15000);
  }
  poll();
}
