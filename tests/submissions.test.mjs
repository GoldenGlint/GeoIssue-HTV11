import { test } from 'node:test';
import assert from 'node:assert/strict';
import { issueRepository } from '../src/data.js';
import { geolocationService, geoUrl, LOCAL_CLAUDE } from '../src/api.js';

function mockFetch(t, handler) {
  const original = globalThis.fetch, calls = [];
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async (url, options = {}) => { calls.push({ url: String(url), options }); return handler(String(url), options); };
  return calls;
}
const reply = (status, data) => ({ ok: status < 400, status, json: async () => data });

test('a submission goes to the database with its photos, and this browser keeps the token, not the photos', async t => {
  const calls = mockFetch(t, () => reply(201, { submission_id: 'SUB-0123456789', token: 'secret', location_status: 'provided' }));
  const photos = [{ image: 'AAAA', mime: 'image/jpeg' }];
  const entry = await issueRepository.submit({ category: 'Litter', description: 'Bags', coordinates: [-79.38, 43.65], photos });
  assert.equal(calls[0].url, '/api/submissions');
  assert.deepEqual(JSON.parse(calls[0].options.body).photos, photos);
  assert.equal(entry.issue_id, 'SUB-0123456789');
  assert.equal(entry.token, 'secret');
  assert.equal(entry.photo_count, 1);
  assert.equal(entry.photos, undefined);
});

test('a failed submission reports the server’s reason', async t => {
  mockFetch(t, () => reply(400, { error: 'The location must be in Toronto' }));
  await assert.rejects(issueRepository.submit({ category: 'Litter', photos: [] }), /must be in Toronto/);
});

test('Claude’s answer is sent with the token, and a repeat after it got through counts as done', async t => {
  let status = 409;
  const calls = mockFetch(t, () => reply(status, {}));
  const entry = { issue_id: 'SUB-0123456789', token: 'secret', location_status: 'located', coordinates: [-79.38, 43.65], geolocation: { job_id: 'j' }, description: 'not sent' };
  assert.equal(await issueRepository.locateSubmission(entry), true);
  assert.equal(calls[0].url, '/api/submissions/SUB-0123456789/location');
  assert.deepEqual(JSON.parse(calls[0].options.body), { token: 'secret', location_status: 'located', coordinates: [-79.38, 43.65], geolocation: { job_id: 'j' } });
  status = 503;
  await assert.rejects(issueRepository.locateSubmission(entry));
});

test('the hosted app uses this computer’s Claude only when switched on and running', async t => {
  const originalLocation = globalThis.location;
  t.after(() => { globalThis.location = originalLocation; });
  globalThis.location = { origin: 'https://geoissue.photo' };
  let localUp = true;
  const calls = mockFetch(t, url => {
    if (url === '/api/status') return reply(200, { geolocate: { available: false, missing: ['Claude Code'] } });
    if (url === `${LOCAL_CLAUDE}/api/status`) return localUp ? reply(200, { geolocate: { available: true, model: 'opus' } }) : Promise.reject(new TypeError('Failed to fetch'));
    throw new Error(`unexpected ${url}`);
  });
  assert.equal((await geolocationService(false)).available, false);
  assert.ok(!calls.some(c => c.url.startsWith(LOCAL_CLAUDE)), 'nothing is asked of this computer until switched on');
  assert.equal(geoUrl('/api/geolocate'), '/api/geolocate');
  const local = await geolocationService(true);
  assert.deepEqual([local.available, local.local], [true, true]);
  assert.equal(geoUrl('/api/geolocate'), `${LOCAL_CLAUDE}/api/geolocate`);
  localUp = false;
  assert.equal(await geolocationService(true), null);
  assert.equal(geoUrl('/api/geolocate'), '/api/geolocate');
});
