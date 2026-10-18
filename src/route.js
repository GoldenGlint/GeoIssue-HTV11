// Low-carbon crew routes: the order to visit a set of issues that keeps driving short, and what that drive
// emits in a gasoline van versus an electric one. Road distances, times and the driving path come from OSRM
// (OpenStreetMap routing); straight lines are the fallback. Planning is pure, so it runs in Node tests too.
import { distanceMetres } from './coordinates.js';

// Every plan shows these, so a reader can check the numbers. Rough planning figures, not measurements.
export const ROUTE_ASSUMPTIONS = {
  detourFactor: 1.3,       // without the router: road distance ≈ 1.3 × straight-line distance
  speedKmh: 25,            // without the router: average city driving speed between stops
  gasLitresPer100Km: 15,   // full-size gasoline cargo van, city driving
  gasKgCo2PerLitre: 2.3,   // CO₂ from burning one litre of gasoline (Natural Resources Canada)
  evKwhPerKm: 0.3,         // full-size electric cargo van
  gridKgCo2PerKwh: 0.03,   // Ontario's grid, mostly nuclear and hydro: about 30 g CO₂e per kWh
};
export const MAX_STOPS = 60;
export const ROUTER = 'https://router.project-osrm.org';

/** Kilograms of CO₂ for driving `km` in each van. */
export function emissions(km) {
  const a = ROUTE_ASSUMPTIONS;
  return { gasKg: km * a.gasLitresPer100Km / 100 * a.gasKgCo2PerLitre, evKg: km * a.evKwhPerKm * a.gridKgCo2PerKwh };
}

/** Estimated road kilometres between every pair of points, from straight lines. */
export const straightMatrix = points => points.map(a => points.map(b => distanceMetres(a, b) / 1000 * ROUTE_ASSUMPTIONS.detourFactor));

/** Kilometres to visit the points in the given order. */
export function pathKm(points, order = points.map((_, i) => i), matrix = straightMatrix(points)) {
  let km = 0;
  for (let i = 1; i < order.length; i++) km += matrix[order[i - 1]][order[i]];
  return km;
}

/** A short order to visit every point once, starting anywhere: nearest neighbour from each possible start,
 * then 2-opt (reversing any stretch that makes the path shorter) until nothing improves. Road distances
 * can differ by direction, so a reversed stretch is measured both ways. */
export function planOrder(points, d = straightMatrix(points)) {
  const n = points.length;
  if (n < 2) return points.map((_, i) => i);
  const length = order => order.slice(1).reduce((sum, stop, i) => sum + d[order[i]][stop], 0);
  let best = null, bestKm = Infinity;
  for (let start = 0; start < n; start++) {
    const order = [start], left = new Set(points.keys()); left.delete(start);
    while (left.size) {
      const at = order.at(-1);
      let next = -1;
      for (const j of left) if (next < 0 || d[at][j] < d[at][next]) next = j;
      order.push(next); left.delete(next);
    }
    const km = length(order);
    if (km < bestKm) { best = order; bestKm = km; }
  }
  for (let improved = true; improved;) {
    improved = false;
    for (let i = 0; i < n - 1; i++) {
      for (let k = i + 1; k < n; k++) {
        const candidate = [...best.slice(0, i), ...best.slice(i, k + 1).reverse(), ...best.slice(k + 1)];
        const km = length(candidate);
        if (km < bestKm - 1e-9) { best = candidate; bestKm = km; improved = true; }
      }
    }
  }
  return best;
}

/** A crew route through the issues, compared with visiting them in the order they were reported.
 * `roads` ({ km, minutes } matrices from `roadMatrix`, in the order of `issues` after the cap) switches
 * distances and times from straight-line estimates to the road network. */
export function planRoute(issues, roads = null) {
  // Past the cap, the highest-priority issues are planned first.
  const chosen = capStops(issues);
  const points = chosen.map(i => i.geometry.coordinates);
  const km = roads?.km || straightMatrix(points);
  const order = planOrder(points, km), stops = order.map(i => chosen[i]);
  const reported = chosen.map((issue, i) => ({ issue, i })).sort((a, b) => a.issue.first_seen_at.localeCompare(b.issue.first_seen_at) || a.issue.issue_id.localeCompare(b.issue.issue_id)).map(r => r.i);
  const plannedKm = pathKm(points, order, km), reportedKm = pathKm(points, reported, km);
  return {
    stops, km: plannedKm, reportedKm, left: issues.length - chosen.length, method: roads ? 'roads' : 'straight',
    legs: order.map((stop, n) => (n ? km[order[n - 1]][stop] : 0)),
    minutes: roads ? pathKm(points, order, roads.minutes) : plannedKm / ROUTE_ASSUMPTIONS.speedKmh * 60,
    planned: emissions(plannedKm), reportedGasKg: emissions(reportedKm).gasKg,
  };
}
export const capStops = issues => [...issues].sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0)).slice(0, MAX_STOPS);

const lonLat = points => points.map(([lng, lat]) => `${lng.toFixed(6)},${lat.toFixed(6)}`).join(';');
async function getJson(url, fetchImpl, timeoutMs) {
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(url, { signal: controller.signal });
    const body = await response.json();
    if (!response.ok || body.code !== 'Ok') throw new Error(body.message || `Routing failed (${response.status})`);
    return body;
  } finally { clearTimeout(timer); }
}

/** Road kilometres and driving minutes between every pair of points. A pair the router can't connect
 * (an island, a closed road) falls back to its straight-line estimate. */
export async function roadMatrix(points, { fetchImpl = fetch, timeoutMs = 10000 } = {}) {
  const body = await getJson(`${ROUTER}/table/v1/driving/${lonLat(points)}?annotations=distance,duration`, fetchImpl, timeoutMs);
  const straight = straightMatrix(points);
  return {
    km: body.distances.map((row, i) => row.map((m, j) => (m == null ? straight[i][j] : m / 1000))),
    minutes: body.durations.map((row, i) => row.map((s, j) => (s == null ? straight[i][j] / ROUTE_ASSUMPTIONS.speedKmh * 60 : s / 60))),
  };
}

/** The driving path through the points in order, as [lng, lat] coordinates along the roads. */
export async function roadPath(points, { fetchImpl = fetch, timeoutMs = 10000 } = {}) {
  const body = await getJson(`${ROUTER}/route/v1/driving/${lonLat(points)}?overview=full&geometries=geojson`, fetchImpl, timeoutMs);
  return body.routes[0].geometry.coordinates;
}
