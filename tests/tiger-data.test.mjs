import { test } from 'node:test';
import assert from 'node:assert/strict';
import { issueRepository } from '../src/data.js';
import { activityOptions, activityBody, activityPanelHtml, tigerProofHtml } from '../src/activity.js';

test('static hosting keeps public snapshots and never claims a live database', async t => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async url => {
    if (String(url) === '/api/status') return { ok: false };
    const data = String(url).endsWith('issues.public.json') ? [{ issue_id: 'public-snapshot' }] : {};
    return { ok: true, json: async () => data };
  };
  const sources = await issueRepository.sources();
  assert.equal(sources.pipeline, 1);
  assert.equal(sources.replay, 0);
  assert.equal(issueRepository.backend('pipeline').type, 'file');
  assert.deepEqual(await issueRepository.list('pipeline'), [{ issue_id: 'public-snapshot' }]);
});

test('configured but unavailable database visibly falls back to the file snapshot', async t => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async url => {
    if (String(url) === '/api/status') return { ok: true, json: async () => ({ tiger: true }) };
    if (String(url).startsWith('/api/')) return { ok: false };
    return { ok: true, json: async () => String(url).endsWith('issues.public.json') ? [{ issue_id: 'fallback' }] : {} };
  };
  assert.equal((await issueRepository.sources()).pipeline, 1);
  assert.match(issueRepository.backend('pipeline').warning, /unavailable.*snapshot/);
});

test('database datasets keep replay separate and refresh current issues', async t => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  let version = 1;
  globalThis.fetch = async url => {
    url = String(url);
    if (url === '/api/status') return { ok: true, json: async () => ({ tiger: true }) };
    const dataset = new URL(url, 'http://localhost').searchParams.get('dataset');
    return { ok: true, json: async () => url.startsWith('/api/issues')
      ? [{ issue_id: `${dataset}-${version}` }] : { report: { version }, simulated: dataset === 'replay' } };
  };
  assert.equal((await issueRepository.sources()).replay, 1);
  assert.equal(issueRepository.backend('pipeline').type, 'tiger');
  assert.equal(issueRepository.backend('replay').simulated, true);
  version = 2;
  await issueRepository.refresh('pipeline');
  assert.equal((await issueRepository.list('pipeline'))[0].issue_id, 'pipeline-2');
  assert.equal((await issueRepository.list('replay'))[0].issue_id, 'replay-1');
});

test('activity scope excludes unsupported issue filters and labels simulated reports', () => {
  const options = activityOptions('replay', { days: '', area: 'ward:10', type: 'Flooding', query: 'private', status: 'Resolved' });
  assert.deepEqual(Object.fromEntries(options), { dataset: 'replay', days: '90', ward: '10', type: 'Flooding' });
  const html = activityBody({ series: [{ bucket: '2026-10-17T12:00:00Z', reports: 8 }], wards: [],
    days: 7, reports: 8, undated_reports: 1, simulated: true, baseline_available: false, as_of: '2026-10-17T12:00:00Z' });
  assert.match(html, /Fictional reports/);
  assert.match(html, /Insufficient history/);
  assert.match(html, /1 undated reports/);
  assert.match(html, /Other filters apply to issue views/);
});

test('Tiger details stay behind a small source link and storage claims use measured savings', () => {
  for (const type of ['sample', 'file']) {
    assert.doesNotMatch(activityPanelHtml({ type }, type), /data-action="tiger-info"/);
  }
  const panel = activityPanelHtml({ type: 'tiger' }, 'pipeline');
  assert.match(panel, /aria-label="About Tiger Data"/);
  assert.doesNotMatch(panel, /Powered by|tiger-intro|tiger-proof|activity-powered/);
  const stats = { reports_by_dataset: { pipeline: 6, replay: 10000 },
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
