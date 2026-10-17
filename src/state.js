// UI state shared by the map, table and dashboard, plus browser-local persistence.
import { TORONTO_CENTER, DEMO_DATE, neighbourhoods } from './data.js';
import { issueMatches } from './issues.js';
import { scorePriority } from './priority.js';
import { wardLabel } from './format.js';
import { toast } from './ui.js';

export const DEFAULT_FILTERS = { query: '', type: '', severity: '', status: '', days: '30', area: '', infra: '', radius: '500' };
export const read = (key, fallback) => { try { return JSON.parse(localStorage.getItem(`civiclens:${key}`)) ?? fallback; } catch { return fallback; } };
export const persist = (key, value) => { try { localStorage.setItem(`civiclens:${key}`, JSON.stringify(value)); } catch { toast('Browser storage is unavailable. Changes will last for this session.'); } };

export const state = {
  issues: [], view: 'map', filters: { ...DEFAULT_FILTERS }, selected: [], scope: null, panel: null,
  saved: read('saved', []), recent: read('recent', []), pending: read('pending', []), historyEnabled: read('historyEnabled', true),
  role: 'Public', sort: 'first_seen_at', direction: -1, page: 1, perPage: 10, dataTab: 'records',
  layers: [], mapMode: 'pan', heat: false, center: TORONTO_CENTER, zoom: 13,
  // 'sample' (240 generated issues) or 'pipeline' (data/analyzed from `python -m analysis`), with per-source counts.
  dataSource: read('dataSource', 'sample'), sources: { sample: 0, pipeline: 0 }, pipeline: { report: null, areas: null },
};

export const filtered = (filters = state.filters) => state.issues.filter(i => issueMatches(i, filters));
/** Issues matching the same filters in the previous period of equal length, or null without a time filter. */
export const previousPeriod = (filters = state.filters) => filters.days ? state.issues.filter(i => issueMatches(i, filters, Number(filters.days))) : null;
export const scopedRows = () => filtered().filter(i => !state.scope || state.scope.includes(i.issue_id));
export const findIssue = id => state.issues.find(i => i.issue_id === id);
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
  Object.assign(issue, (({ score, reasons }) => ({ priority_score: score, priority_reasons: reasons }))(scorePriority(issue, Date.parse(DEMO_DATE))));
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
