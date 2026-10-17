// UI state shared by the map, table and dashboard, plus browser-local persistence.
import { TORONTO_CENTER, neighbourhoods, wards, nearbyAssets, nearestNeighbourhood } from './data.js';
import { issueMatches } from './issues.js';
import { wardLabel } from './format.js';
import { distanceMetres } from './coordinates.js';
import { toast } from './ui.js';

export const DEFAULT_FILTERS = { query: '', type: '', severity: '', status: '', days: '30', area: '', infra: '', radius: '500' };
export const read = (key, fallback) => { try { return JSON.parse(localStorage.getItem(`civiclens:${key}`)) ?? fallback; } catch { return fallback; } };
export const persist = (key, value) => { try { localStorage.setItem(`civiclens:${key}`, JSON.stringify(value)); } catch { toast('Browser storage is unavailable. Changes will last for this session.'); } };

export const state = {
  issues: [], view: 'map', filters: { ...DEFAULT_FILTERS }, selected: [], scope: null, panel: null,
  saved: read('saved', []), recent: read('recent', []), pending: read('pending', []), corrections: read('corrections', []), historyEnabled: read('historyEnabled', true),
  role: 'Public', sort: 'first_seen_at', direction: -1, page: 1, perPage: 10, dataTab: 'records',
  layers: [], mapMode: 'pan', heat: false, center: TORONTO_CENTER, zoom: 13, pipeline: null,
};

export const filtered = (filters = state.filters) => state.issues.filter(i => issueMatches(i, filters));
/** Issues matching the same filters in the previous period of equal length, or null without a time filter. */
export const previousPeriod = (filters = state.filters) => filters.days ? state.issues.filter(i => issueMatches(i, filters, Number(filters.days))) : null;
export const scopedRows = () => filtered().filter(i => !state.scope || state.scope.includes(i.issue_id));
export const findIssue = id => state.issues.find(i => i.issue_id === id);
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
    if (area) Object.assign(issue, { neighbourhood_id: area.id, neighbourhood_name: area.name, ward_id: area.ward, ward_name: wards[area.ward] });
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
