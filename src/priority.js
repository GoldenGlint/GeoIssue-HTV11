// Priority score for City staff, matching analysis/stages/priority.py so sample and pipeline issues rank alike.
// Keep these weights in step with [stages.priority] in analysis/config.toml.
export const PRIORITY_WEIGHTS = {
  severityPoints: { High: 40, Medium: 25, Low: 10 },
  pointsPerExtraSighting: 8, maxSightingPoints: 24,
  pointsPerOpenDay: 0.5, maxAgePoints: 15,
  nearAssetM: 100, nearAssetPoints: { Schools: 15, TTC: 12, Roads: 5 },
  lowConfidenceBelow: 0.6, lowConfidenceFactor: 0.7,
};
const DAY = 86400000;
const fmt = n => Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, '');

/** Returns { score: 0–100, reasons: string[] }. `now` is a timestamp in ms. */
export function scorePriority(issue, now, w = PRIORITY_WEIGHTS) {
  if (issue.resolution_status === 'Resolved') return { score: 0, reasons: ['Resolved'] };
  let points = w.severityPoints[issue.severity] ?? 0;
  const reasons = [`${issue.severity} severity (+${fmt(points)})`];
  const extra = (issue.sightings_count || 1) - 1;
  if (extra > 0) {
    const p = Math.min(extra * w.pointsPerExtraSighting, w.maxSightingPoints);
    points += p; reasons.push(`${extra + 1} sightings (+${fmt(p)})`);
  }
  if (issue.first_seen_at) {
    const days = Math.max(0, Math.floor((now - Date.parse(issue.first_seen_at)) / DAY));
    const p = Math.min(days * w.pointsPerOpenDay, w.maxAgePoints);
    if (p) { points += p; reasons.push(`Open ${days} ${days === 1 ? 'day' : 'days'} (+${fmt(p)})`); }
  }
  const nearest = Object.fromEntries((issue.nearby_assets || []).map(a => [a.type, a]));
  for (const [kind, bonus] of Object.entries(w.nearAssetPoints)) {
    const asset = nearest[kind];
    if (asset && asset.distance_m <= w.nearAssetM) { points += bonus; reasons.push(`${asset.distance_m} m from ${asset.name} (+${fmt(bonus)})`); }
  }
  if (issue.detection_confidence != null && issue.detection_confidence < w.lowConfidenceBelow) {
    points *= w.lowConfidenceFactor;
    reasons.push(`Low detection confidence ${Math.round(issue.detection_confidence * 100)}% (x${fmt(w.lowConfidenceFactor)})`);
  }
  return { score: Math.round(Math.min(100, points)), reasons };
}
