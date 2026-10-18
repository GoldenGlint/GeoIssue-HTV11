import { test } from 'node:test';
import assert from 'node:assert/strict';
import { issueRepository } from '../src/data.js';
import { activityOptions, activityBody, activityPanelHtml, tigerProofHtml } from '../src/activity.js';

test('without Tiger Data both datasets are empty and say the database is unavailable', async t => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  const requested = [];
  globalThis.fetch = async url => { requested.push(String(url)); return { ok: false }; };
  assert.deepEqual(await issueRepository.sources(), { collected: 0, simulated: 0 });
  assert.equal(issueRepository.backend('collected').type, 'unavailable');
  assert.match(issueRepository.backend('simulated').warning, /Tiger Data unavailable/);
  assert.deepEqual(await issueRepository.list('collected'), []);
  assert.ok(requested.every(url => url.startsWith('/api/')), 'no file snapshot is fetched');
});

test('database datasets keep simulated issues separate and refresh current issues', async t => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  let version = 1;
  globalThis.fetch = async url => {
    url = String(url);
    if (url === '/api/status') return { ok: true, json: async () => ({ tiger: true }) };
    const dataset = new URL(url, 'http://localhost').searchParams.get('dataset');
    return { ok: true, json: async () => url.startsWith('/api/issues')
      ? [{ issue_id: `${dataset}-${version}` }] : { report: { version }, simulated: dataset === 'simulated' } };
  };
  assert.equal((await issueRepository.sources()).simulated, 1);
  assert.equal(issueRepository.backend('collected').type, 'tiger');
  assert.equal(issueRepository.backend('simulated').simulated, true);
  version = 2;
  await issueRepository.refresh('collected');
  assert.equal((await issueRepository.list('collected'))[0].issue_id, 'collected-2');
  assert.equal((await issueRepository.list('simulated'))[0].issue_id, 'simulated-1');
});

test('activity scope excludes unsupported issue filters and labels simulated reports', () => {
  const options = activityOptions('simulated', { days: '', area: 'ward:10', type: 'Flooding', query: 'private', status: 'Resolved' });
  assert.deepEqual(Object.fromEntries(options), { dataset: 'simulated', days: '90', ward: '10', type: 'Flooding' });
  const html = activityBody({ series: [{ bucket: '2026-10-17T12:00:00Z', reports: 8 }], wards: [],
    days: 7, reports: 8, undated_reports: 1, simulated: true, baseline_available: false, as_of: '2026-10-17T12:00:00Z' });
  assert.match(html, /Fictional reports/);
  assert.match(html, /Insufficient history/);
  assert.match(html, /1 undated reports/);
  assert.match(html, /Other filters apply to issue views/);
});

test('Tiger details stay behind a small source link and storage claims use measured savings', () => {
  assert.doesNotMatch(activityPanelHtml({ type: 'unavailable' }, 'collected'), /data-action="tiger-info"/);
  const panel = activityPanelHtml({ type: 'tiger' }, 'collected');
  assert.match(panel, /aria-label="About Tiger Data"/);
  assert.doesNotMatch(panel, /Powered by|tiger-intro|tiger-proof|activity-powered/);
  const stats = { reports_by_dataset: { collected: 6, simulated: 10000 },
    shared_columnstore: { compressed_chunks: 8, storage_reduction_percent: 55.74 } };
  assert.match(tigerProofHtml(stats), /6<\/strong> collected reports/);
  assert.match(tigerProofHtml(stats), /10,000<\/strong> simulated reports/);
  assert.match(tigerProofHtml(stats), /55.7% smaller historical chunks/);
  assert.match(tigerProofHtml(stats), /across both datasets/);
  stats.shared_columnstore.storage_reduction_percent = -4;
  assert.doesNotMatch(tigerProofHtml(stats), /smaller/);
  stats.shared_columnstore.storage_reduction_percent = null;
  assert.match(tigerProofHtml(stats), /8 chunks in columnstore/);
});
