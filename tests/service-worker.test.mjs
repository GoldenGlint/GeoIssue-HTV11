import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

test('the legacy worker retires before reloading tabs, without deleting browser data', async () => {
  const handlers = {}, calls = [];
  const urls = ['http://127.0.0.1:5173/', 'http://127.0.0.1:5173/#dashboard'];
  runInNewContext(readFileSync(new URL('../sw.js', import.meta.url), 'utf8'), {
    self: {
      addEventListener: (type, handler) => { handlers[type] = handler; },
      skipWaiting: async () => { calls.push('skip waiting'); },
      registration: { unregister: async () => { calls.push('unregister'); return true; } },
      clients: {
        matchAll: async options => {
          assert.equal(options.type, 'window');
          assert.equal(options.includeUncontrolled, true);
          return urls.map(url => ({ url, navigate: async target => { calls.push(target); } }));
        },
      },
    },
  });
  let work;
  const event = { waitUntil: promise => { work = promise; } };
  handlers.install(event);
  await work;
  handlers.activate(event);
  await work;
  assert.deepEqual(calls, ['skip waiting', 'unregister', ...urls]);
});
