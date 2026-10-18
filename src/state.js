// UI state shared by the map, table and dashboard, plus browser-local persistence.
import { TORONTO_CENTER, REFERENCE_DATE, neighbourhoods, wards, nearbyAssets, nearestNeighbourhood, nearestCorner, wardAt } from './data.js';
import { issueMatches } from './issues.js';
import { scorePriority } from './priority.js';
import { wardLabel } from './format.js';
import { distanceMetres } from './coordinates.js';
import { toast } from './ui.js';

export const DEFAULT_FILTERS = { query: '', type: '', severity: '', status: '', days: '30', area: '', infra: '', radius: '500' };
export const read = (key, fallback) => { try { return JSON.parse(localStorage.getItem(`geoissue:${key}`)) ?? fallback; } catch { return fallback; } };
export const persist = (key, value) => { try { localStorage.setItem(`geoissue:${key}`, JSON.stringify(value)); } catch { toast('Browser storage is unavailable. Changes will last for this session.'); } };

export const state = {
  issues: [], view: 'map', filters: { ...DEFAULT_FILTERS }, selected: [], scope: null, panel: null,
  saved: read('saved', []), recent: read('recent', []), pending: read('pending', []), corrections: read('corrections', []), historyEnabled: read('historyEnabled', true),
  role: 'Public', sort: 'first_seen_at', direction: -1, page: 1, perPage: 10, dataTab: 'records', hiddenColumns: read('hiddenColumns', []),
  layers: [], mapMode: 'pan', heat: false, center: TORONTO_CENTER, zoom: 13,
  mapEmptyDismissedFor: null,
  // Tiger Data's two datasets: issues the pipeline collected, and fictional simulated issues with their reports.
  dataSource: read('dataSource', null), sources: { collected: 0, simulated: 0 }, pipeline: { report: null, areas: null },
  dataBackend: { type: 'unavailable' },
};

export const filtered = (filters = state.filters) => state.issues.filter(i => issueMatches(i, filters));
/** Issues matching the same filters in the previous period of equal length, or null without a time filter. */
export const previousPeriod = (filters = state.filters) => filters.days ? state.issues.filter(i => issueMatches(i, filters, Number(filters.days))) : null;
export const scopedRows = () => filtered().filter(i => !state.scope || state.scope.includes(i.issue_id));
export const findIssue = id => state.issues.find(i => i.issue_id === id);
/** True when the loaded issues are fictional sample records; labels say "sample" only then. */
export const isSampleData = () => state.issues.some(i => i.is_demo);
export const sampleWord = () => (isSampleData() ? 'sample ' : '');
/** Keep a dismissed map notice closed during panning, until filters/data or visible results change. */
export function shouldShowMapEmptyNotice(visibleCount) {
  const context = JSON.stringify([state.dataSource, state.filters]);
  if (visibleCount || state.mapEmptyDismissedFor !== context) state.mapEmptyDismissedFor = null;
  return visibleCount === 0 && !state.panel && state.mapEmptyDismissedFor !== context;
}
export function dismissMapEmptyNotice() {
  state.mapEmptyDismissedFor = JSON.stringify([state.dataSource, state.filters]);
}
/** This browser's newest correction for an issue that is still waiting for review. */
export const pendingCorrection = id => state.corrections.findLast(c => c.issue_id === id && c.status === 'Pending review');
/** Applies an accepted correction to its issue in memory. With an API, the server does this and returns the updated issue. */
export function applyCorrection(c) {
  const issue = findIssue(c.issue_id);
  if (!issue) return;
  if (c.kind === 'location') {
    const moved = Math.round(distanceMetres(issue.geometry.coordinates, c.coordinates));
    issue.geometry = { type: 'Point', coordinates: c.coordinates };
    issue.location_radius_m = 25;
    // Recompute what depends on the position: nearest assets, and the area when the point maps to one.
    const nearby = nearbyAssets(c.coordinates), area = nearestNeighbourhood(c.coordinates);
    Object.assign(issue, { nearby_assets: nearby, infrastructure_type: nearby[0].type, asset_id: nearby[0].asset_id, asset_name: nearby[0].name, distance_m: nearby[0].distance_m });
    issue.address = nearestCorner(c.coordinates) || `Near ${nearby[0].name}`;
    if (area) Object.assign(issue, { neighbourhood_id: area.id, neighbourhood_name: area.name });
    // Official ward boundaries decide the ward; the sample neighbourhood's ward is the fallback.
    const ward = wardAt(c.coordinates) || area?.ward;
    if (ward) Object.assign(issue, { ward_id: ward, ward_name: wards[ward] });
    issue.geo_method = 'Corrected by a community member, confirmed by a reviewer';
    issue.geo_trace = [...(issue.geo_trace || []), { stage: 'Correction', result: `Pin moved ${moved.toLocaleString()} m after review`, status: 'match' }];
    issue.explanation = issue.explanation?.replace(/approximate within [\d,]+ ?(m|metres)\b/, 'confirmed within 25 m after a reviewed correction');
    issue.verification_status = 'Verified';
  } else if (c.kind === 'issue_type') issue.issue_type = c.issue_type;
  else if (c.kind === 'resolved') issue.resolution_status = 'Resolved';
  else issue.verification_status = 'Dismissed';
}
export const areaLabel = area => area.startsWith('ward:') ? wardLabel(area.slice(5)) : neighbourhoods.find(n => n.id === area)?.name || area;
export function remember(issue) {
  if (!state.historyEnabled || !issue) return;
  state.recent = [issue.issue_id, ...state.recent.filter(id => id !== issue.issue_id)].slice(0, 20);
  persist('recent', state.recent);
}

// "This is the same issue" from the upload form: an extra sighting on an existing issue, kept in this browser.
export const isSighting = entry => entry.kind === 'sighting';
export const reviewQueue = () => state.pending.filter(entry => !isSighting(entry));
function bumpSightings(issue) {
  issue.sightings_count = (issue.sightings_count || 1) + 1;
  Object.assign(issue, (({ score, reasons }) => ({ priority_score: score, priority_reasons: reasons }))(scorePriority(issue, Date.parse(REFERENCE_DATE))));
}
export function addSighting(id, details = {}) {
  const issue = findIssue(id);
  if (!issue) return null;
  bumpSightings(issue);
  state.pending.push({ kind: 'sighting', issue_id: `LOCAL-${Date.now().toString(36).toUpperCase()}`, joined_issue_id: id, category: issue.issue_type, address: issue.address, created_at: new Date().toISOString(), ...details });
  persist('pending', state.pending);
  return issue;
}
/** Re-applies sightings added in earlier visits after the issues load. */
export function applyLocalSightings() {
  for (const entry of state.pending.filter(isSighting)) {
    const issue = findIssue(entry.joined_issue_id);
    if (issue) bumpSightings(issue);
  }
}
