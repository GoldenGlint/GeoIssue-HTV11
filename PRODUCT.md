# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Public residents** checking what is broken around them, adding a sighting or reporting a new issue, often on a phone.
- **City staff and volunteers** who triage, verify, correct and plan fixes for reported issues at a desk.
- **Hack the Valley judges** (School of Cities challenge, Toronto's 2026 municipal election) who evaluate the prototype in a short demo, usually on a laptop or projector.

All three weigh in; the role switch in the app decides what each sees.

## Product Purpose

GeoIssue turns public photos of civic issues (potholes, broken sidewalks, graffiti, dumping, flooding) into one shared, privacy-protected dataset that people can explore on a map, in a table and on a dashboard, verify and correct, and act on. Success: a resident sees what is already reported nearby, and staff can see where issues cluster and plan the work.

## Positioning

One civic issue dataset behind two synchronized workspaces (Map Explorer and Data Explorer). Issues come from screened public social posts and community uploads, are located from place names and visual clues with the method shown, merged into incidents, and published only at coarse precision until verified.

## Operating Context

Hackathon prototype for the School of Cities challenge on Toronto's 2026 municipal election. Used at a desk (staff, judges' demo on a laptop or projector) and on phones outdoors (residents). Both a dark and a light theme are offered and switchable.

## Capabilities and Constraints

- Static web app: vanilla JavaScript modules, one hand-written stylesheet with light and dark theme tokens, no framework or build step.
- Map Explorer (custom OpenStreetMap map with pins, density, wards, infrastructure layers, Street View, crew routes), Data Explorer table, Dashboard, Saved, Recents, Verify queue, Methodology, upload and correction flows.
- Data: real analysed posts from the scraping handoff and a labelled fictional sample of 240 issues. Photos that need face and plate blurring are withheld; unverified locations are rounded to a 250 m grid.
- Core layout and flows are settled and stay: sidebar, map with floating filters, contextual right panel, same pages.

## Brand Commitments

- The GeoIssue name and the lens mark, including the short loading animation where the lens draws itself.
- Light/dark theme switching stays.
- Identity is civic and public-service, not tied to Toronto alone.
- Must not look AI-generated (glows, neon accents, gradient sheen).
- Visual direction (chosen 2026-10-18): the category standard, executed at full craft with no novelty: the familiar civic map-and-data tool. The bar is Google Maps, Linear / Stripe, City open-data portals (Toronto Open Data, NYC 311) and Mapbox / Felt.
- Light theme is the default; dark is a switch away.

## Evidence on Hand

Real analysed issues in `data/analyzed/`, the fictional sample in `src/data.js` (always labelled as sample), OpenStreetMap infrastructure and City of Toronto ward boundaries. No real testimonials, partner logos or adoption figures exist; do not invent them.

## Product Principles

- Show the evidence and its uncertainty: how a location was found, how confident it is, what is withheld and why.
- One dataset, many views: map, table and dashboard always agree.
- Privacy before precision for anything public.
- Useful to act on: every view should lead to a next step (verify, correct, plan, report).
