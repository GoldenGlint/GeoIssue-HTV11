// Methodology: data sources, how an issue reaches the map, privacy, limits and licences.
import { icon } from '../icons.js';
import { PRIORITY_WEIGHTS as W } from '../priority.js';
import { state } from '../state.js';

const status = kind => ({ live: '<span class="method-status live">Live in this prototype</span>', sample: '<span class="method-status sample">Sample / illustrative</span>', planned: '<span class="method-status planned">In progress (team lane)</span>' }[kind]);

export function methodologyHtml() {
  const counts = state.pipeline.report?.counts;
  const issues = state.dataSource === 'replay'
    ? `${state.issues.length} fictional issues and their simulated reports, stored in a separate Tiger Data replay dataset. They do not describe real places or conditions.`
    : state.dataSource === 'pipeline'
    ? `Pipeline output from <code>python -m analysis</code>${counts ? `: ${counts.records ?? counts.input_records} photos analysed → ${(counts.sightings || 0) + (counts.dropped || 0)} civic issues found → ${counts.sightings} located in Toronto → ${counts.issues} unique issues` : ''}.`
    : `${state.sources.sample} fictional records generated for the demo (deterministic, so everyone sees the same data). Switch to pipeline output in the header once <code>python -m analysis</code> has run.`;
  const steps = [
    ['Collect', 'Public posts from official platform APIs and photos people upload here. No logged-in scraping and no private accounts.', 'planned'],
    ['Check photos', 'Collected public-post evidence can display in full. For uploads, Gemini suggests the issue type and severity, checks for person-focused or private scenes, and identifies faces and licence plates for the upload form’s blurring tools.', 'live'],
    ['Locate', 'Location tags in the post when present; otherwise visual clues (street signs, transit, landmarks) and matching against street-level imagery. Every location carries an uncertainty radius.', 'planned'],
    ['Deduplicate', 'Sightings of the same type close together within 14 days, or a reposted photo, become one issue with a sighting count. Uploaders can add a sighting to an existing issue instead of filing a duplicate.', 'live'],
    ['Prioritize', `A 0–100 score with its reasons: severity (High ${W.severityPoints.High}, Medium ${W.severityPoints.Medium}, Low ${W.severityPoints.Low}), +${W.pointsPerExtraSighting} per extra sighting (max ${W.maxSightingPoints}), +${W.pointsPerOpenDay} per day open (max ${W.maxAgePoints}), and a bonus within ${W.nearAssetM} m of a school (+${W.nearAssetPoints.Schools}), TTC station (+${W.nearAssetPoints.TTC}) or highway (+${W.nearAssetPoints.Roads}). Low detection confidence scales it down; resolved issues score 0.`, 'live'],
    ['Verify', 'Volunteers confirm the issue and its location before it counts as reliable. In this prototype decisions last for the session and are not authentication.', 'sample'],
  ];
  const sources = [
    ['Issues', issues],
    ['Report history', state.dataBackend.type === 'tiger' ? 'Stored in Tiger Data alongside current issue records. Timestamped reports power hourly ward trends; older report chunks use compressed column storage. <button class="text-button" data-action="tiger-info">How Tiger Data powers GeoIssue →</button>' : 'The current source is a sample or file snapshot. A connected Tiger Data source provides timestamped report history and hourly ward trends.'],
    ['Evidence photos', 'Analysed issues display their collected photos in full. Fictional records use sample photos under CC BY / CC BY-SA that illustrate the category, not the record itself. Sample credits: <a href="assets/evidence/CREDITS.md" target="_blank" rel="noopener">assets/evidence/CREDITS.md</a>.'],
    ['Ward boundaries', 'City of Toronto “City Wards” open data (25-ward model). Contains information licensed under the Open Government Licence – Toronto.'],
    ['TTC stations and highways', 'OpenStreetMap, © OpenStreetMap contributors (ODbL). Distances to the nearest station, school and highway drive the proximity filter and priority.'],
    ['Schools', 'An approximate sample list, to be replaced with the City’s school locations dataset.'],
    ['Map tiles', '© OpenStreetMap contributors.'],
  ];
  const limits = [
    ['Signals, not ground truth', 'Counts cover issues found in public photos and community uploads, not every issue in an area.'],
    ['Who posts shapes what we see', 'Neighbourhoods where fewer people post online can look “healthier” than they are. Compare wards with care and look at sample sizes.'],
    ['Locations are approximate', 'Public locations are coarse on purpose. The radius shows how far off a pin may be.'],
    ['AI makes mistakes', 'Suggestions, severity and blurring can be wrong. Everything is editable and reviewed by people before it is relied on.'],
    ['Not a 311 request', 'Reporting here doesn’t create a City service request. GeoIssue is meant to feed 311, not replace it.'],
    ['Neutral in the election period', 'Ward digests describe counts only. They never mention candidates or tell anyone how to vote.'],
  ];
  return `<div class="methodology-page">
    <section class="card method-intro"><h2>${icon('sun')} What GeoIssue is</h2><p>GeoIssue finds civic problems such as potholes, broken sidewalks, graffiti, dumping and flooding in photos people already post publicly and in photos uploaded here. It estimates where each photo was taken and shows how sure it is, groups repeat sightings into one issue, and lets volunteers check the results before City staff act on them. It feeds Toronto 311; it doesn’t replace it.</p><button class="button small" data-action="help">${icon('help')} Map controls and shortcuts</button></section>
    <section class="card"><div class="card-header"><h2>${icon('database')} Where the data comes from</h2></div><dl class="method-sources">${sources.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl></section>
    <section class="card"><div class="card-header"><h2>${icon('layers')} How an issue gets onto the map</h2></div><ol class="method-steps">${steps.map(([title, text, kind], j) => `<li><span class="method-num">${j + 1}</span><div><h3>${title} ${status(kind)}</h3><p>${text}</p></div></li>`).join('')}</ol></section>
    <section class="card"><div class="card-header"><h2>${icon('shield')} Privacy</h2></div><ul class="method-list"><li><strong>Full evidence photos.</strong> Collected photos can be displayed as provided, including faces and licence plates, under the current photo-display policy.</li><li><strong>Public issue details.</strong> Original post links let you check the context. Usernames and handles are not stored as separate account fields.</li><li><strong>Upload controls.</strong> The upload form includes automatic and manual blurring tools.</li><li><strong>Local evidence.</strong> Collected photos are kept locally alongside the analysed issues.</li><li><strong>Takedown.</strong> Anyone can ask for a photo or record to be removed. <em>Add a contact address here before launch.</em></li></ul></section>
    <section class="card"><div class="card-header"><h2>${icon('warning')} What this data can’t tell you</h2></div><div class="method-limits">${limits.map(([k, v]) => `<div><h3>${k}</h3><p>${v}</p></div>`).join('')}</div></section>
  </div>`;
}
