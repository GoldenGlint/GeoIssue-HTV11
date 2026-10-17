/** Fictional demo dataset for the CivicLens prototype.
 * Replace issueRepository.list() with your API; data-contract.md documents the issue shape.
 * Records are generated deterministically, so every reload (and every teammate) sees the same data.
 * Coordinates are coarse and fictional. Wards come from the City of Toronto ward boundaries (point-in-polygon).
 * Backend authorization/privacy processing must happen before returning real records.
 */
import { osmStations, osmRoads } from './osm-infrastructure.js';
import { wardBoundaries } from './ward-boundaries.js';
import { scorePriority } from './priority.js';

export { wardBoundaries };

export const DEMO_DATE = '2026-10-17T12:00:00Z';
export const ELECTION_DATE = '2026-10-26T12:00:00Z';
export const TORONTO_CENTER = [-79.397, 43.661];
export const TORONTO_BOUNDS = { west: -79.64, south: 43.58, east: -79.11, north: 43.86 };
const DAY = 86400000;

export const categories = {
  Pothole: { color: '#fa6575', icon: 'warning' },
  'Sidewalk damage': { color: '#ffb452', icon: 'cone' },
  Graffiti: { color: '#ba80f6', icon: 'tool' },
  Litter: { color: '#25d5ac', icon: 'trash' },
  Flooding: { color: '#4ea8ff', icon: 'water' },
  Other: { color: '#9daec3', icon: 'more' },
};

// Toronto's 25 wards (2018 boundaries).
export const wards = {
  1: 'Etobicoke North', 2: 'Etobicoke Centre', 3: 'Etobicoke—Lakeshore', 4: 'Parkdale—High Park', 5: 'York South—Weston',
  6: 'York Centre', 7: 'Humber River—Black Creek', 8: 'Eglinton—Lawrence', 9: 'Davenport', 10: 'Spadina—Fort York',
  11: 'University—Rosedale', 12: 'Toronto—St. Paul’s', 13: 'Toronto Centre', 14: 'Toronto—Danforth', 15: 'Don Valley West',
  16: 'Don Valley East', 17: 'Don Valley North', 18: 'Willowdale', 19: 'Beaches—East York', 20: 'Scarborough Southwest',
  21: 'Scarborough Centre', 22: 'Scarborough—Agincourt', 23: 'Scarborough North', 24: 'Scarborough—Guildwood', 25: 'Scarborough—Rouge Park',
};

// [id, name, ward, relative weight, [address, lng, lat][]]
const neighbourhoodSeed = [
  ['downtown', 'Downtown', '10', 16, [['King St W & Spadina Ave', -79.3953, 43.6455], ['Bay St & Front St W', -79.3792, 43.6457], ['Adelaide St W & Peter St', -79.3925, 43.6478], ['Queen St W & University Ave', -79.3866, 43.6505], ['King St W & John St', -79.3907, 43.6463]]],
  ['st-lawrence', 'St. Lawrence', '13', 5, [['Front St E & Jarvis St', -79.3716, 43.6489], ['King St E & Sherbourne St', -79.3690, 43.6510], ['The Esplanade & Market St', -79.3722, 43.6470]]],
  ['church-wellesley', 'Church–Wellesley', '13', 5, [['Church St & Wellesley St E', -79.3806, 43.6655], ['Yonge St & Carlton St', -79.3830, 43.6618], ['Jarvis St & Isabella St', -79.3776, 43.6683]]],
  ['regent-park', 'Regent Park', '13', 5, [['Dundas St E & Parliament St', -79.3638, 43.6597], ['Gerrard St E & Sumach St', -79.3605, 43.6618], ['Shuter St & Sackville St', -79.3637, 43.6567]]],
  ['kensington-market', 'Kensington Market', '11', 8, [['Augusta Ave & Baldwin St', -79.4013, 43.6556], ['Spadina Ave & College St', -79.4004, 43.6578], ['Kensington Ave & Dundas St W', -79.3987, 43.6532]]],
  ['the-annex', 'The Annex', '11', 6, [['Bloor St W & Bathurst St', -79.4111, 43.6656], ['Bloor St W & St George St', -79.3995, 43.6677], ['Bloor St W & Spadina Ave', -79.4037, 43.6672], ['Harbord St & Brunswick Ave', -79.4065, 43.6620]]],
  ['liberty-village', 'Liberty Village', '10', 6, [['East Liberty St & Strachan Ave', -79.4113, 43.6391], ['King St W & Atlantic Ave', -79.4205, 43.6387], ['Liberty St & Hanna Ave', -79.4185, 43.6380]]],
  ['parkdale', 'Parkdale', '4', 7, [['Queen St W & Dufferin St', -79.4283, 43.6425], ['Queen St W & Lansdowne Ave', -79.4378, 43.6405], ['King St W & Jameson Ave', -79.4365, 43.6375]]],
  ['high-park', 'High Park', '4', 4, [['Bloor St W & Parkside Dr', -79.4565, 43.6553], ['Bloor St W & Keele St', -79.4598, 43.6555], ['Roncesvalles Ave & Howard Park Ave', -79.4506, 43.6510]]],
  ['the-junction', 'The Junction', '4', 4, [['Dundas St W & Keele St', -79.4630, 43.6656], ['Dundas St W & Pacific Ave', -79.4693, 43.6652], ['Annette St & Keele St', -79.4610, 43.6610]]],
  ['davenport', 'Davenport', '9', 5, [['Bloor St W & Dufferin St', -79.4355, 43.6600], ['Dupont St & Lansdowne Ave', -79.4426, 43.6675], ['Geary Ave & Ossington Ave', -79.4300, 43.6720]]],
  ['riverside', 'Riverside', '14', 4, [['Queen St E & Broadview Ave', -79.3531, 43.6591], ['Dundas St E & Broadview Ave', -79.3547, 43.6636], ['Queen St E & Logan Ave', -79.3470, 43.6604]]],
  ['leslieville', 'Leslieville', '14', 5, [['Queen St E & Leslie St', -79.3295, 43.6626], ['Dundas St E & Carlaw Ave', -79.3407, 43.6660], ['Queen St E & Jones Ave', -79.3368, 43.6612]]],
  ['danforth', 'Danforth', '14', 5, [['Danforth Ave & Pape Ave', -79.3446, 43.6798], ['Danforth Ave & Chester Ave', -79.3525, 43.6782], ['Danforth Ave & Logan Ave', -79.3485, 43.6790]]],
  ['east-york', 'East York', '19', 4, [['Coxwell Ave & Danforth Ave', -79.3226, 43.6840], ['O’Connor Dr & Donlands Ave', -79.3466, 43.6955], ['Cosburn Ave & Woodbine Ave', -79.3170, 43.6945]]],
  ['the-beaches', 'The Beaches', '19', 4, [['Queen St E & Woodbine Ave', -79.3101, 43.6670], ['Queen St E & Lee Ave', -79.2990, 43.6703], ['Kingston Rd & Main St', -79.2990, 43.6860]]],
  ['yonge-eglinton', 'Yonge–Eglinton', '12', 5, [['Yonge St & Eglinton Ave', -79.3985, 43.7066], ['Mount Pleasant Rd & Eglinton Ave E', -79.3897, 43.7086], ['Yonge St & Davisville Ave', -79.3970, 43.6979]]],
  ['willowdale', 'Willowdale', '18', 5, [['Yonge St & Sheppard Ave', -79.4110, 43.7615], ['Yonge St & Finch Ave', -79.4155, 43.7805], ['Yonge St & Empress Ave', -79.4129, 43.7685]]],
  ['don-mills', 'Don Mills', '16', 3, [['Don Mills Rd & Lawrence Ave E', -79.3445, 43.7380], ['Don Mills Rd & Eglinton Ave E', -79.3380, 43.7210]]],
  ['weston', 'Weston', '5', 3, [['Weston Rd & Lawrence Ave W', -79.5150, 43.7005], ['Eglinton Ave W & Keele St', -79.4735, 43.6897]]],
  ['etobicoke', 'Etobicoke', '3', 4, [['The Queensway & Islington Ave', -79.5185, 43.6250], ['Bloor St W & Islington Ave', -79.5245, 43.6455], ['Lake Shore Blvd W & Kipling Ave', -79.5205, 43.6015]]],
  ['scarborough-southwest', 'Scarborough Southwest', '20', 3, [['Eglinton Ave E & Kennedy Rd', -79.2636, 43.7325], ['Kingston Rd & Birchmount Rd', -79.2633, 43.6950]]],
  ['scarborough-centre', 'Scarborough Centre', '21', 4, [['McCowan Rd & Ellesmere Rd', -79.2440, 43.7760], ['Brimley Rd & Ellesmere Rd', -79.2600, 43.7735]]],
  ['highland-creek', 'Highland Creek', '25', 4, [['Military Trail & Ellesmere Rd', -79.1883, 43.7840], ['Morningside Ave & Ellesmere Rd', -79.1990, 43.7820], ['Old Kingston Rd & Morningside Ave', -79.1865, 43.7735]]],
];
export const neighbourhoods = neighbourhoodSeed.map(([id, name, ward, weight, places]) => ({ id, name, ward, weight, places }));

// TTC stations and road lines are real OpenStreetMap geometry (regenerate with scripts/fetch-osm-infrastructure.py).
// School positions are approximate samples; replace them with the City's school locations dataset.
const assetSeed = [
  ...osmStations.map(([name, lng, lat]) => ['TTC', name, [lng, lat]]),
  ...Object.entries(osmRoads).map(([name, lines]) => ['Roads', name, lines]),
  ['Schools', 'University of Toronto St. George', [-79.3957, 43.6629]], ['Schools', 'Toronto Metropolitan University', [-79.3788, 43.6577]],
  ['Schools', 'OCAD University', [-79.3915, 43.6530]], ['Schools', 'George Brown College, St. James', [-79.3700, 43.6515]],
  ['Schools', 'University of Toronto Scarborough', [-79.1874, 43.7845]], ['Schools', 'Humber Polytechnic Lakeshore', [-79.5190, 43.5960]],
  ['Schools', 'Kensington Community School', [-79.4030, 43.6560]], ['Schools', 'Jarvis Collegiate Institute', [-79.3770, 43.6680]],
  ['Schools', 'Riverdale Collegiate Institute', [-79.3410, 43.6690]], ['Schools', 'Parkdale Collegiate Institute', [-79.4335, 43.6400]],
  ['Schools', 'Western Technical-Commercial School', [-79.4740, 43.6620]], ['Schools', 'Earl Haig Secondary School', [-79.4060, 43.7660]],
  ['Schools', 'Danforth Collegiate and Technical Institute', [-79.3410, 43.6860]], ['Schools', 'Northern Secondary School', [-79.3990, 43.7120]],
  ['Schools', 'Central Technical School', [-79.4095, 43.6625]], ['Schools', 'Etobicoke School of the Arts', [-79.5050, 43.6340]],
  ['Schools', 'Malvern Collegiate Institute', [-79.3020, 43.6830]], ['Schools', 'Weston Collegiate Institute', [-79.5180, 43.7000]],
];
export const infrastructure = assetSeed.map(([type, name, coordinates], j) => ({
  asset_id: `${type.slice(0, 3).toUpperCase()}-${String(j + 1).padStart(3, '0')}`, type, name,
  geometry: { type: typeof coordinates[0] === 'number' ? 'Point' : 'MultiLineString', coordinates },
}));

// Sample ingestion metrics for the last 30 days. Replace with the pipeline's signal monitor.
export const demoPipeline = { window_days: 30, posts_scanned: 48230, with_images: 10940, toronto_relevant: 2185, public_scenes: 1260 };

// Deterministic PRNG (mulberry32) so the sample data is stable across reloads.
let seed = 20261017;
const random = () => { seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
const pick = list => list[Math.floor(random() * list.length)];
const between = (min, max) => min + random() * (max - min);
const weighted = entries => { let r = random() * entries.reduce((sum, [, w]) => sum + w, 0); for (const [value, w] of entries) if ((r -= w) < 0) return value; return entries.at(-1)[0]; };
const round = (value, digits = 0) => Number(value.toFixed(digits));

const metres = ([lng1, lat1], [lng2, lat2]) => { const k = Math.cos((lat1 + lat2) / 2 * Math.PI / 180); return Math.hypot((lng2 - lng1) * 111320 * k, (lat2 - lat1) * 110540); };
export const distanceMetres = metres;
function distanceTo(point, asset) {
  if (asset.geometry.type === 'Point') return metres(point, asset.geometry.coordinates);
  // Distance to the nearest segment, in a local metric plane centred on the point.
  const [lng0, lat0] = point, k = Math.cos(lat0 * Math.PI / 180);
  let best = Infinity;
  for (const coordinates of asset.geometry.coordinates) {
    const line = coordinates.map(([lng, lat]) => [(lng - lng0) * 111320 * k, (lat - lat0) * 110540]);
    for (let j = 1; j < line.length; j++) {
      const [ax, ay] = line[j - 1], dx = line[j][0] - ax, dy = line[j][1] - ay;
      const t = Math.max(0, Math.min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy || 1)));
      best = Math.min(best, Math.hypot(ax + t * dx, ay + t * dy));
    }
  }
  return best;
}
// Even-odd point-in-polygon over every ring of a ward (outer rings and holes), with a bounding-box pre-check.
const wardIndex = wardBoundaries.map(w => {
  const all = w.rings.flat();
  return { ...w, box: [Math.min(...all.map(p => p[0])), Math.min(...all.map(p => p[1])), Math.max(...all.map(p => p[0])), Math.max(...all.map(p => p[1]))] };
});
export function wardAt([lng, lat]) {
  for (const w of wardIndex) {
    if (lng < w.box[0] || lat < w.box[1] || lng > w.box[2] || lat > w.box[3]) continue;
    let inside = false;
    for (const ring of w.rings) {
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const [xi, yi] = ring[i], [xj, yj] = ring[j];
        if ((yi > lat) !== (yj > lat) && lng < (xj - xi) * (lat - yi) / (yj - yi) + xi) inside = !inside;
      }
    }
    if (inside) return w.id;
  }
  return null;
}

function nearbyAssets(point) {
  return ['TTC', 'Schools', 'Roads'].map(type => {
    const [asset, distance] = infrastructure.filter(a => a.type === type).map(a => [a, distanceTo(point, a)]).sort((a, b) => a[1] - b[1])[0];
    return { type, asset_id: asset.asset_id, name: asset.name, distance_m: Math.round(distance) };
  }).sort((a, b) => a.distance_m - b.distance_m);
}

const typeWeights = [['Pothole', 26], ['Sidewalk damage', 19], ['Graffiti', 17], ['Litter', 18], ['Flooding', 9], ['Other', 11]];
const severityWeights = { Pothole: [40, 40, 20], 'Sidewalk damage': [20, 55, 25], Graffiti: [5, 25, 70], Litter: [10, 35, 55], Flooding: [55, 35, 10], Other: [15, 45, 40] };
const findings = {
  Pothole: ['Deep pothole in the curb lane', 'Cluster of potholes near the crosswalk', 'Pothole widening around a utility cut', 'Broken asphalt along the streetcar track'],
  'Sidewalk damage': ['Heaved sidewalk slab creating a trip edge', 'Cracked curb ramp at the crossing', 'Broken pavers along the boulevard', 'Sunken section of sidewalk holding water'],
  Graffiti: ['Tags on a utility box', 'Graffiti across a transit shelter panel', 'Tags on a bridge abutment', 'Spray paint on a wayfinding sign'],
  Litter: ['Overflowing litter bin', 'Dumped furniture on the boulevard', 'Litter collecting along a fence line', 'Bagged waste left beside a street bin'],
  Flooding: ['Ponding across the curb lane after rain', 'Blocked catch basin', 'Water pooling in the underpass', 'Flooded crosswalk at the intersection'],
  Other: ['Streetlight out', 'Damaged street name sign', 'Fallen branch blocking part of the sidewalk', 'Cracked transit shelter panel'],
};
const genericClues = ['Toronto street name blade', 'Green P parking sign', 'Bike Share Toronto dock', 'TTC stop pole', 'City litter and recycling bin'];
// A sample rainstorm on Oct 4–6 makes flooding reports spike, so the timeline has a real event in it.
const stormDays = [11, 12, 13];
const dayWeights = Array.from({ length: 90 }, (_, d) => {
  const weekday = new Date(Date.parse(DEMO_DATE) - d * DAY).getUTCDay();
  return [d, (1 + 0.7 * (1 - d / 90)) * (weekday === 0 || weekday === 6 ? 1.3 : 1)];
});

function locate(source, address, near, hood) {
  const streets = address.split(' & ');
  const clues = [`Street sign “${streets.at(-1)}”`];
  if (near.type === 'TTC' && near.distance_m < 400) clues.push(near.name.includes('Station') ? 'TTC station entrance in frame' : 'Streetcar tracks and overhead wires');
  if (random() < 0.6) clues.push(pick(genericClues));
  const fusion = radius => ({ stage: 'Fusion', result: `${radius} m radius at 90% coverage`, status: 'info' });
  if (source === 'Community submission') {
    const radius = round(between(20, 60));
    return { method: 'Reporter-confirmed pin', radius, confidence: between(0.86, 0.95), clues: [], trace: [{ stage: 'Reporter pin', result: 'Placed on the upload map and confirmed by the reporter', status: 'match' }, { stage: 'Privacy rounding', result: 'Published position rounded to about 100 m', status: 'info' }] };
  }
  if (source === 'Public imagery') {
    const radius = round(between(10, 30));
    return { method: 'Image GPS', radius, confidence: between(0.9, 0.97), clues: [], trace: [{ stage: 'Image metadata', result: 'Camera position from the street-level imagery provider', status: 'match' }, { stage: 'Sanity check', result: `Position falls inside ${hood.name}`, status: 'info' }] };
  }
  const roll = random(), candidates = 2 + Math.floor(random() * 4);
  const clueStep = { stage: 'Visual clues', result: `${clues.length} ${clues.length === 1 ? 'clue' : 'clues'} → ${candidates} candidate areas`, status: 'match' };
  if (roll < 0.3) {
    const radius = round(between(120, 300));
    return { method: 'Post location tag + visual clues', radius, confidence: between(0.66, 0.8), clues, trace: [{ stage: 'Post metadata', result: `Place tag “${hood.name}” in the post`, status: 'match' }, clueStep, { stage: 'Street-level match', result: 'No match above the verification threshold', status: 'skip' }, fusion(radius)] };
  }
  if (roll < 0.75) {
    const radius = round(between(25, 90));
    return { method: 'Visual clues + street-level match', radius, confidence: between(0.82, 0.94), clues, trace: [{ stage: 'Post metadata', result: 'No location in the post', status: 'skip' }, clueStep, { stage: 'Street-level match', result: `Top Mapillary reference ${round(between(12, 60))} m away · similarity 0.${round(between(72, 93))}`, status: 'match' }, { stage: 'Geometric check', result: `${round(between(110, 380))} matching keypoints (threshold 80)`, status: 'match' }, fusion(radius)] };
  }
  const radius = round(between(150, 400));
  return { method: 'Visual clues', radius, confidence: between(0.55, 0.7), clues, trace: [{ stage: 'Post metadata', result: 'No location in the post', status: 'skip' }, clueStep, { stage: 'Street-level match', result: 'No match above the verification threshold', status: 'skip' }, { stage: 'Fusion', result: `${radius} m radius · sent to volunteers to confirm the pin`, status: 'info' }] };
}

function generateIssues(count) {
  const now = Date.parse(DEMO_DATE), issues = [];
  for (let n = 0; n < count; n++) {
    const day = weighted(dayWeights), storm = stormDays.includes(day);
    const type = weighted(typeWeights.map(([t, w]) => [t, t === 'Flooding' ? w * (storm ? 10 : 0.45) : w]));
    const hood = weighted(neighbourhoods.map(h => [h, h.weight]));
    const [address, lng, lat] = pick(hood.places);
    const coordinates = [round(lng + between(-0.0018, 0.0018), 5), round(lat + between(-0.0012, 0.0012), 5)];
    const severity = weighted(['High', 'Medium', 'Low'].map((s, j) => [s, severityWeights[type][j]]));
    const source = weighted([['Public social post', 55], ['Public imagery', 20], ['Community submission', 25]]);
    const firstSeen = now - day * DAY - between(0.5, 11.5) * 3600000;
    const resolution = weighted(day < 3 ? [['Open', 70], ['In review', 30]] : day < 15 ? [['Open', 45], ['In review', 30], ['Resolved', 25]] : day < 45 ? [['Open', 30], ['In review', 20], ['Resolved', 50]] : [['Open', 20], ['In review', 10], ['Resolved', 70]]);
    const nearby = nearbyAssets(coordinates), near = nearby[0];
    const geo = locate(source, address, near, hood);
    const verification = resolution === 'Resolved' ? 'Verified' : random() < (day < 2 ? 0.5 : geo.method === 'Visual clues' ? 0.45 : 0.12) ? 'Needs review' : 'Verified';
    const sightings = 1 + Math.floor(random() ** 2 * (day < 7 ? 4 : 7));
    const finding = pick(findings[type]);
    const ward = wardAt(coordinates) || hood.ward; // jittered points can land in the lake; fall back to the neighbourhood's ward
    issues.push({
      issue_type: type, severity, resolution_status: resolution, verification_status: verification,
      neighbourhood_id: hood.id, neighbourhood_name: hood.name, ward_id: ward, ward_name: wards[ward], address,
      geometry: { type: 'Point', coordinates }, location_radius_m: geo.radius, geo_confidence: round(geo.confidence, 2),
      geo_method: geo.method, geo_trace: geo.trace, geo_clues: geo.clues,
      infrastructure_type: near.type, asset_id: near.asset_id, asset_name: near.name, distance_m: near.distance_m, nearby_assets: nearby,
      sightings_count: sightings, detection_confidence: round(between(0.72, 0.98), 2),
      first_seen_at: new Date(firstSeen).toISOString(),
      last_seen_at: new Date(Math.min(now - 3600000, firstSeen + random() * Math.min(day, 14) * DAY)).toISOString(),
      source_category: source, evidence_thumbnail: null, evidence_credit: null,
      description: `${finding} near ${address}.`,
      explanation: `The sample image analysis indicates ${finding.toLowerCase()}. ${sightings > 1 ? `${sightings} independent sightings were linked to it.` : 'There is one sighting so far.'} Location is approximate within ${geo.radius} metres. A reviewer should confirm the issue and location before any operational action.`,
      is_demo: true,
    });
  }
  // Newest issues get the highest IDs, like a real sequence. Priority uses the same rules as the pipeline.
  return issues.sort((a, b) => b.first_seen_at.localeCompare(a.first_seen_at)).map((issue, j) => {
    const { score, reasons } = scorePriority(issue, now);
    return { issue_id: `CL-${10712 - j}`, incident_id: `INC-${4240 - j}`, ...issue, priority_score: score, priority_reasons: reasons };
  });
}
export const demoIssues = generateIssues(240);

// Sample evidence photos (assets/evidence/credits.json) illustrate each category; they never depict the record itself.
async function evidenceByCategory() {
  try {
    const response = await fetch(new URL('../assets/evidence/credits.json', import.meta.url));
    if (!response.ok) return {};
    const groups = {};
    for (const credit of await response.json()) (groups[credit.category] ||= []).push({ ...credit, url: new URL(`../assets/evidence/${credit.file}`, import.meta.url).href });
    return groups;
  } catch { return {}; }
}

// Written by `python -m analysis` (see analysis/README.md). Missing files mean the pipeline hasn't been run.
const analyzedFile = async name => {
  try {
    const response = await fetch(new URL(`../data/analyzed/${name}`, import.meta.url), { cache: 'no-store' });
    return response.ok ? await response.json() : null;
  } catch { return null; }
};
let analyzedCache;
const analyzedIssues = () => analyzedCache ||= analyzedFile('issues.public.json').then(issues => Array.isArray(issues) && issues.length ? issues : null);

export const issueRepository = {
  /** Issue counts per dataset. The sample is always available; pipeline output only after `python -m analysis`. */
  async sources() { return { sample: demoIssues.length, pipeline: (await analyzedIssues())?.length || 0 }; },
  /** Pipeline run report (counts per stage) and per-area stats and summaries, or null when not available. */
  pipelineReport: () => analyzedFile('report.json'),
  areaSummaries: () => analyzedFile('areas.json'),
  async list(source = 'sample') {
    if (source === 'pipeline') { const analyzed = await analyzedIssues(); if (analyzed) return structuredClone(analyzed); }
    const photos = await evidenceByCategory(), issues = structuredClone(demoIssues);
    for (const [j, issue] of issues.entries()) {
      const options = photos[issue.issue_type];
      if (!options?.length) continue;
      const photo = options[j % options.length];
      issue.evidence_thumbnail = photo.url;
      issue.evidence_credit = { title: photo.title, author: photo.author, license: photo.license, license_url: photo.license_url, source_url: photo.source_url, is_sample: true };
    }
    return issues;
  },
  async submit(draft) {
    // Replace with POST /api/submissions. Do not publish uploads until privacy review.
    return { ...draft, issue_id: `LOCAL-${Date.now().toString(36).toUpperCase()}`, verification_status: 'Pending review', local_only: true };
  },
};
