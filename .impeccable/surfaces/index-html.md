---
version: 1
slug: "index-html"
primary_target: "index.html"
related_targets: ["src/styles.css"]
---

## Scope

The whole app shell and every page (Map Explorer first, then Data Explorer, Dashboard, workspace pages, dialogs), Operate mode. Layout, navigation and flows stay; the visual world is replaced.

## Audience and task

Residents, City staff and hackathon judges: find, understand, verify and act on civic issues on a map and in a table. Constraints: light default with a dark switch, WCAG AA contrast, GeoIssue name, lens mark and loading animation kept.

## Direction contract

THESIS: GeoIssue as a well-made civic map tool: quiet white surfaces, one blue accent, clear type, and the map and data doing the talking. It refuses the dark neon command-centre look the app had (glows, cyan halos, gradient sheen).
OWN-WORLD: Light: white panels on a cool grey app ground, grey-200 hairline borders, 8px radius, soft offset shadows only on floating map controls and panels, Inter throughout, one blue (#2563eb) for actions, selection and links; category colours as plain saturated pins. Dark: neutral graphite greys (no navy, no glow), the same blue lifted for contrast.
STORY: A visitor sees the city's reported issues on a familiar map, filters them, opens one, understands the evidence and how sure the location is, and saves, shares, corrects or plans a crew route.
FIRST VIEWPORT: Sidebar left (logo, nav, upload button, account), header with the data switch, the map filling the centre with white floating search and filter controls, teardrop pins, legend card bottom-left, zoom controls bottom-right; the right panel opens as a white card on selection.
FORM: canon (the category standard, chosen by the user over the roll); benchmarks Google Maps, Linear / Stripe, civic open-data portals, Mapbox / Felt. seed:4b36f84e73bbe310
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
