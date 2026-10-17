// Shared presentation helpers; keep UI sorting separate from API ordering.
const severityOrder = { High: 3, Medium: 2, Low: 1 };
const statusOrder = { Open: 1, 'In review': 2, Resolved: 3 };

export function compareIssues(a, b, key, direction = 1) {
  const value = item => key === 'severity' ? severityOrder[item[key]] ?? 0
    : key === 'resolution_status' ? statusOrder[item[key]] ?? 0 : item[key] ?? '';
  const av = value(a), bv = value(b);
  const comparison = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv));
  return comparison * direction || a.issue_id.localeCompare(b.issue_id);
}

export function searchSuggestions(issues, query) {
  const q = query.trim().toLowerCase();
  if (q.length < 2) return [];
  const matching = issues.filter(i => [i.issue_id, i.address, i.neighbourhood_id, i.issue_type, i.asset_name].join(' ').toLowerCase().includes(q));
  const areas = [...new Set(matching.map(i => i.neighbourhood_id))]
    .filter(area => area.toLowerCase().includes(q))
    .map(area => ({ kind: 'area', area, label: area, description: `${matching.filter(i => i.neighbourhood_id === area).length} matching sample issues · Explore neighbourhood` }));
  const records = matching.map(i => ({ kind: 'issue', id: i.issue_id, label: `${i.issue_type} · ${i.address}`, description: `${i.issue_id} · ${i.neighbourhood_id}` }));
  return [...areas, ...records].slice(0, 6);
}
