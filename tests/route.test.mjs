import { test } from 'node:test';
import assert from 'node:assert/strict';
import { planOrder, pathKm, planRoute, emissions, roadMatrix, roadPath, ROUTE_ASSUMPTIONS, MAX_STOPS } from '../src/route.js';
import { googleDirectionsUrl } from '../src/coordinates.js';

// Points along Queen Street, west to east, about 600 m apart.
const line = Array.from({ length: 8 }, (_, i) => [-79.43 + i * 0.0075, 43.645]);
const issue = (coordinates, n, extra = {}) => ({ issue_id: `CL-${n}`, geometry: { type: 'Point', coordinates }, first_seen_at: `2026-10-${String(10 + n).padStart(2, '0')}T12:00:00Z`, ...extra });

test('a shuffled line is visited end to end', () => {
  const shuffled = [3, 7, 0, 5, 1, 6, 2, 4].map(i => line[i]);
  const order = planOrder(shuffled);
  assert.deepEqual([...order].sort(), [...shuffled.keys()].sort(), 'every stop exactly once');
  assert.ok(Math.abs(pathKm(shuffled, order) - pathKm(line)) < 1e-9, 'as short as walking the line in order');
});

test('the planned route is never longer than the reported order', () => {
  const scattered = [[-79.40, 43.65], [-79.30, 43.70], [-79.39, 43.66], [-79.31, 43.71], [-79.41, 43.64], [-79.29, 43.69]];
  const plan = planRoute(scattered.map((c, n) => issue(c, n)));
  assert.equal(plan.stops.length, 6);
  assert.ok(plan.km < plan.reportedKm, `${plan.km} < ${plan.reportedKm}`);
  assert.ok(plan.planned.evKg < plan.planned.gasKg);
});

test('emissions follow the stated assumptions', () => {
  const a = ROUTE_ASSUMPTIONS, { gasKg, evKg } = emissions(100);
  assert.equal(gasKg, a.gasLitresPer100Km * a.gasKgCo2PerLitre);
  assert.ok(Math.abs(evKg - 100 * a.evKwhPerKm * a.gridKgCo2PerKwh) < 1e-9);
});

test('past the cap, the highest-priority issues are planned', () => {
  const many = Array.from({ length: MAX_STOPS + 5 }, (_, n) => issue([-79.4 + n * 0.001, 43.65], n % 28, { issue_id: `CL-${n}`, priority_score: n }));
  const plan = planRoute(many);
  assert.equal(plan.stops.length, MAX_STOPS);
  assert.equal(plan.left, 5);
  assert.ok(!plan.stops.some(s => s.priority_score < 5));
});

test('directions links keep the order and stop at 9 waypoints', () => {
  const url = new URL(googleDirectionsUrl(line.slice(0, 3)));
  assert.equal(url.searchParams.get('origin'), '43.645000,-79.430000');
  assert.equal(url.searchParams.get('destination'), '43.645000,-79.415000');
  assert.equal(url.searchParams.get('waypoints'), '43.645000,-79.422500');
  const long = new URL(googleDirectionsUrl([...line, ...line]));
  assert.equal(long.searchParams.get('waypoints').split('|').length, 9);
});

test('road distances decide the order when the router supplies them', () => {
  // Three stops in a row, but the road from the middle one to the east end is long (a river with no bridge).
  const points = [[-79.40, 43.65], [-79.39, 43.65], [-79.38, 43.65]];
  const km = [[0, 1, 2], [1, 0, 9], [2, 9, 0]];
  const plan = planRoute(points.map((c, n) => issue(c, n)), { km, minutes: km.map(row => row.map(v => v * 2)) });
  assert.equal(plan.method, 'roads');
  assert.deepEqual(plan.stops.map(s => s.issue_id), ['CL-1', 'CL-0', 'CL-2']);
  assert.equal(plan.km, 3);
  assert.equal(plan.minutes, 6);
  assert.deepEqual(plan.legs, [0, 1, 2]);
});

const reply = body => async () => ({ ok: true, status: 200, json: async () => body });

test('router replies are read, and unconnected pairs fall back to straight lines', async () => {
  const points = [[-79.40, 43.65], [-79.39, 43.65]];
  const roads = await roadMatrix(points, { fetchImpl: reply({ code: 'Ok', distances: [[0, 1500], [null, 0]], durations: [[0, 180], [null, 0]] }) });
  assert.equal(roads.km[0][1], 1.5);
  assert.equal(roads.minutes[0][1], 3);
  assert.ok(roads.km[1][0] > 0.8 && roads.km[1][0] < 1.2, 'straight-line estimate for the missing pair');
  const path = await roadPath(points, { fetchImpl: reply({ code: 'Ok', routes: [{ geometry: { coordinates: [[-79.4, 43.65], [-79.395, 43.651], [-79.39, 43.65]] } }] }) });
  assert.equal(path.length, 3);
  await assert.rejects(roadMatrix(points, { fetchImpl: reply({ code: 'TooBig', message: 'Too many table coordinates' }) }), /Too many/);
});
