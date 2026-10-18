// Low-carbon crew routes: the order to visit a set of issues that keeps driving short, and what that drive
// emits in a gasoline van versus an electric one. Pure functions, so they run in Node tests too.
import { distanceMetres } from './coordinates.js';

// Every plan shows these, so a reader can check the numbers. Rough planning figures, not measurements.
export const ROUTE_ASSUMPTIONS = {
  detourFactor: 1.3,       // road distance ≈ 1.3 × straight-line distance on Toronto's street grid
  speedKmh: 25,            // average city driving speed between stops
  gasLitresPer100Km: 15,   // full-size gasoline cargo van, city driving
  gasKgCo2PerLitre: 2.3,   // CO₂ from burning one litre of gasoline (Natural Resources Canada)
  evKwhPerKm: 0.3,         // full-size electric cargo van
  gridKgCo2PerKwh: 0.03,   // Ontario's grid, mostly nuclear and hydro: about 30 g CO₂e per kWh
};
export const MAX_STOPS = 60;

const legKm = (a, b) => distanceMetres(a, b) / 1000 * ROUTE_ASSUMPTIONS.detourFactor;

/** Kilograms of CO₂ for driving `km` in each van. */
export function emissions(km) {
  const a = ROUTE_ASSUMPTIONS;
  return { gasKg: km * a.gasLitresPer100Km / 100 * a.gasKgCo2PerLitre, evKg: km * a.evKwhPerKm * a.gridKgCo2PerKwh };
}

/** Estimated road kilometres to visit the points in the given order. */
export function pathKm(points, order = points.map((_, i) => i)) {
  let km = 0;
  for (let i = 1; i < order.length; i++) km += legKm(points[order[i - 1]], points[order[i]]);
  return km;
}

/** A short order to visit every point once, starting anywhere: nearest neighbour from each possible start,
 * then 2-opt (reversing any stretch that makes the path shorter) until nothing improves. */
export function planOrder(points) {
  const n = points.length;
  if (n < 3) return points.map((_, i) => i);
  const d = points.map(a => points.map(b => legKm(a, b)));
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
  // Reversing order[i..k] only changes the edges into i and out of k; an open path has none at its ends.
  const edge = (a, b) => (a === undefined || b === undefined ? 0 : d[a][b]);
  for (let improved = true; improved;) {
    improved = false;
    for (let i = 0; i < n - 1; i++) {
      for (let k = i + 1; k < n; k++) {
        const before = edge(best[i - 1], best[i]) + edge(best[k], best[k + 1]);
        const after = edge(best[i - 1], best[k]) + edge(best[i], best[k + 1]);
        if (after < before - 1e-9) { best = [...best.slice(0, i), ...best.slice(i, k + 1).reverse(), ...best.slice(k + 1)]; improved = true; }
      }
    }
  }
  return best;
}

/** A crew route through the issues, compared with visiting them in the order they were reported. */
export function planRoute(issues) {
  // Past the cap, the highest-priority issues are planned first.
  const ranked = [...issues].sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0));
  const chosen = ranked.slice(0, MAX_STOPS);
  const points = chosen.map(i => i.geometry.coordinates);
  const stops = planOrder(points).map(i => chosen[i]);
  const reported = [...chosen].sort((a, b) => a.first_seen_at.localeCompare(b.first_seen_at) || a.issue_id.localeCompare(b.issue_id));
  const km = pathKm(stops.map(i => i.geometry.coordinates)), reportedKm = pathKm(reported.map(i => i.geometry.coordinates));
  return {
    stops, km, reportedKm, left: issues.length - chosen.length,
    minutes: km / ROUTE_ASSUMPTIONS.speedKmh * 60,
    planned: emissions(km), reportedGasKg: emissions(reportedKm).gasKg,
  };
}
