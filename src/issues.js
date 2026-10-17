// Shared issue logic: filtering, sorting and search. Keep UI sorting separate from API ordering.
import { REFERENCE_DATE, wards } from './data.js';

const DAY = 86400000;
const severityOrder = { High: 3, Medium: 2, Low: 1 };
const statusOrder = { Open: 1, 'In review': 2, Resolved: 3 };

export function compareIssues(a, b, key, direction = 1) {
  const value = item => key === 'severity' ? severityOrder[item[key]] ?? 0
    : key === 'resolution_status' ? statusOrder[item[key]] ?? 0 : item[key] ?? '';
  const av = value(a), bv = value(b);
  const comparison = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv));
  return comparison * direction || a.issue_id.localeCompare(b.issue_id);
}

const searchText = i => [i.issue_id, i.address, i.neighbourhood_name, i.ward_name, i.issue_type, i.asset_name, i.description].join(' ').toLowerCase();
const areaMatches = (i, area) => !area || (area.startsWith('ward:') ? i.ward_id === area.slice(5) : i.neighbourhood_id === area);
function nearInfrastructure(i, infra, radius) {
  if (!infra) return true;
  const near = infra === 'any' ? i.nearby_assets[0] : i.nearby_assets.find(a => a.type === infra);
  return !!near && near.distance_m <= radius;
}

/** True when an issue passes the shared filters. `offset` shifts the time window back by that many
 * days, so offset = days gives the previous period of the same length (used for honest comparisons). */
export function issueMatches(i, f, offset = 0) {
  const query = f.query.trim().toLowerCase(), days = Number(f.days);
  const ageDays = Math.floor((Date.parse(REFERENCE_DATE) - Date.parse(i.first_seen_at)) / DAY);
  return (!query || searchText(i).includes(query))
    && (!f.type || i.issue_type === f.type)
    && (!f.severity || i.severity === f.severity)
    && (!f.status || i.resolution_status === f.status)
    && areaMatches(i, f.area)
    && (!days || (ageDays >= offset && ageDays < offset + days))
    && nearInfrastructure(i, f.infra, Number(f.radius));
}

export function searchSuggestions(issues, query) {
  const q = query.trim().toLowerCase();
  if (q.length < 2) return [];
  const matching = issues.filter(i => searchText(i).includes(q));
  const wardItems = Object.entries(wards).filter(([id, name]) => `ward ${id} ${name}`.toLowerCase().includes(q)).map(([id, name]) => ({ kind: 'area', area: `ward:${id}`, label: `Ward ${id} · ${name}`, description: `${issues.filter(i => i.ward_id === id).length} matching sample issues · Explore ward` }));
  const hoods = new Map(matching.filter(i => i.neighbourhood_name.toLowerCase().includes(q)).map(i => [i.neighbourhood_id, i.neighbourhood_name]));
  const areas = [...hoods].map(([id, name]) => ({ kind: 'area', area: id, label: name, description: `${matching.filter(i => i.neighbourhood_id === id).length} matching sample issues · Explore neighbourhood` }));
  const records = matching.map(i => ({ kind: 'issue', id: i.issue_id, label: `${i.issue_type} · ${i.address}`, description: `${i.issue_id} · ${i.neighbourhood_name}` }));
  return [...wardItems, ...areas, ...records].slice(0, 6);
}
