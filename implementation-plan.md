# CivicLens implementation plan and priorities

**Draft for review · 2026-10-17 · based on commit `9321865`** (frontend improvements + analysis pipeline). Supporting research: [`research/competitors.md`](research/competitors.md) and [`research/popular-features.md`](research/popular-features.md).

**How to review:** answer the five decisions in §2, then mark each item in §5 as keep, cut or change. Effort: **S** ≤ 1.5 h, **M** 2–4 h, **L** > 4 h. Lanes: **FE** frontend, **AI** pipeline/AI, **PT** pitch and data. The plan assumes roughly a day of build time is left; if there is less, use the 8-hour cut in §5.

## 1. Where the app stands

**Solid**
- Every map, table, dashboard, upload and verify flow in `features.md` works on desktop and phone with no console errors (checked in a real browser at 390–1672 px).
- The analysis pipeline passes its 38 tests, and its output loads in the frontend without errors: every field in `data-contract.md` is present.
- Real OpenStreetMap geometry for TTC stations and highways; credited sample photos; ward digest; read-only SQL view.

**Thin**
- **Detection and geolocation are not live in the app.** The upload form doesn't call any AI, and the geolocation cascade from the original plan (MegaLoc, LightGlue and Gemini clues) isn't in this repo. The pipeline reads coordinates the photo analysis already supplies. The "how this location was estimated" traces are illustrative.
- **Nothing persists beyond one browser:** submissions, verifications and saves are all local.
- **Ward assignment is approximate** (one ward per sample neighbourhood). That weakens the ward digest, which is the School of Cities angle.

## 2. Decisions

| # | Decision | Answer (2026-10-17) |
|---|---|---|
| D1 | Which data to demo | **The 240-issue sample for now.** The app opens on it; pipeline output stays available behind the data switch (P0-1). |
| D2 | Where the Gemini key lives | **In a `.env` file**, read by the local dev server (`scripts/serve.py`), never by browser code. |
| D3 | Public URL | **Live data eventually.** For testing the frontend, placeholder data is fine. |
| D4 | Close the loop now? | Not decided; stays P1. |
| D5 | Lanes | **Frontend:** you. **Scraping images online:** teammate 1. **Identifying where a photo was taken (geolocation):** teammate 2. Items marked AI below that aren't scraping or geolocation (Gemini triage, blurring, ward boundaries, digests) are done in the frontend lane, on branch `frontend-p0`. |

## 3. Review findings

| ID | Finding | Impact | Addressed by |
|---|---|---|---|
| R1 | When `data/analyzed/issues.public.json` exists, it silently replaces the 240-issue sample, so the app shows 13 issues | Demo looks empty; nobody can tell which data is showing | P0-1 |
| R2 | The pipeline computes `priority_score` with `priority_reasons`, plus per-ward stats and Gemini summaries in `areas.json`; the UI uses none of them | The strongest staff and School of Cities features are invisible | P0-2, P0-7 |
| R3 | Every pipeline issue arrives as Open / Needs review, and verify decisions only last for the session | No status story to tell | P1-1, P1-6 |
| R4 | Ward and neighbourhood come from sample street corners, not official boundaries | Ward digest credibility | P0-6, P1-10 |
| R5 | With pipeline data loaded, the funnel mixes made-up ingestion numbers with real counts ("1% of previous") | Looks wrong to a careful judge | P0-1 |
| R6 | `DEMO_DATE` is fixed at Oct 17, so "last 7 days" counts from that date even with live data | Wrong windows on real data | P1-9 |
| R7 | 90 of 287 font sizes are under 10 px | Unreadable on a projector; AODA | P0-8 |
| R8 | Evidence-credit links accept any URL scheme (e.g. `javascript:`) | XSS risk once data comes from outside | Q1 |
| R9 | No automated frontend tests in the repo (the Playwright checks I ran live in a scratch folder) | Regressions during the crunch | P1-7 |
| R10 | Submissions never leave the browser and can't be approved | Upload story stops at "pending" | P1-1, P1-6, P2 |
| R11 | No live AI in the app (see §1) | The headline claim can't be shown live | P0-3, P0-4, P2-1 |
| R12 | No face/plate blurring anywhere; the pipeline ignores the input's `privacy.*` flags | Privacy risk; Privacy Commissioner expectations | P0-4, Q4 |
| R13 | Pipeline config doesn't map `broken streetlight` | One sample record lands as an unknown type | Q2 |
| R14 | No public URL; the local server keeps getting stopped by low memory | Judges can't open it | P0-9 |

## 4. What the research says

**What we can credibly own** ([competitors](research/competitors.md) §C–D)
1. "311 waits for a report; CivicLens finds the issues people post about but never file." Toronto's open 311 data covers about 30–35% of contacts.
2. "We show our uncertainty." No competitor shows a confidence radius or explains how a photo was located; GeoSpy is the cautionary black box.
3. "One issue, many sightings": cross-source deduplication and an "already in 311?" check.
4. "A ward digest, with evidence, before October 26." The City's ward dashboards are internal.
5. "No new hardware, humans check the AI, privacy built in." It covers sidewalks, parks and transit, not only roads.

**Best-evidenced features** ([features](research/popular-features.md) §1)
1. Closed-loop status.
2. Photo-first reporting in about 10 seconds.
3. Live AI triage (Edmonton 311 shipped it in 2026; SeeClickFix in January 2026).
4. "Already reported nearby."
5. An explainable priority queue.
6. Proof of resolution.
7. An equity lens.

**Avoid:**
- "Closed" that doesn't mean fixed.
- Silence after submitting.
- Forms that lose input.
- Location entry that's hard to use.
- Cluttered maps.
- "Snitching" and privacy worries.

**Judges' comparisons to prepare for:** 311 Toronto, SeeClickFix's AI categorisation, Zencity (social listening and its backlash), GeoSpy (photo geolocation misuse), Blyncsy and City Detect (AI on imagery).

## 5. Priorities

### P0: must have for the demo (≈ 16 h across three lanes)

| ID | Item | Why | Effort | Lane | Depends on | Done when |
|---|---|---|---|---|---|---|
| P0-1 | **Data-source switch and labelling** | R1, R5 | S · 1 h | FE | D1 | The header shows "Data: Demo sample (240) / Pipeline output (13)" with a switch that survives a reload. The funnel hides its sample stages on pipeline data. |
| P0-2 | **Priority queue with reasons** | R2; research #5 | S · 1.5 h | FE | — | Data Explorer can sort by priority (the default for City Staff). The issue panel shows the score and "why it ranks here". The sample generator also gets priority scores. |
| P0-3 | **Live AI triage on upload** (Gemini) | R11; research #3; Gemini track | M · 3 h | AI + FE | D2 | Choosing a photo fills category, severity and description with confidence chips, all editable. Any failure falls back to manual entry. Photos where a person is the subject are refused. |
| P0-4 | **Face and plate blurring on upload** | R12; research #11; risks E4–E5 | M · 1.5 h | AI + FE | P0-3 | The same call returns face and plate boxes, which are blurred on a canvas. A before/after toggle; only the blurred image is kept. Fallback: a manual blur brush. |
| P0-5 | **"Already reported nearby"** | Research #4; gap C3 | S · 1 h | FE | — | After the pin and category are set, same-type issues within 150 m from the last 30 days appear. "This is the same issue" adds a sighting and shows the receipt. |
| P0-6 | **Official ward boundaries** | R4 | M · 2.5 h | AI | — | City of Toronto 25-ward GeoJSON (Open Data, OGL-Toronto) used for point-in-polygon in the pipeline and the sample generator. A ward-outline layer on the map. The digest drops its "approximate" caveat. |
| P0-7 | **Ward digest from pipeline and Gemini summaries** | R2; School of Cities | S · 1.5 h | FE + AI | P0-6 | The digest shows `areas.json` text labelled "Written by Gemini from these counts" or "Template", with the counts beside it. Falls back to today's template. |
| P0-8 | **Readability pass** | R7; AODA | S · 1 h | FE | — | Nothing below 10 px, body text 12 px or more, AA contrast on key text, checked on a projector-sized screen. |
| P0-9 | **Demo package** | R14; research §3 | S · 2 h | PT | D3 | A 3-minute script (§7) rehearsed twice, a 60–90 s backup video, and a public static URL with sample data only. |
| P0-10 | **Methodology and caveats page** | Research #22; risks E3, E4, E7 | S · 1 h | PT + FE | — | Help → Methodology covers data sources, "signals, not ground truth", sampling bias, privacy (no poster identities, blurring, takedown) and how geolocation works and its limits. |

**8-hour cut (if time is short):** P0-3, P0-5, P0-2, P0-10, P0-9, plus the quick fixes. That keeps the Gemini moment, the "neighbours already reported this" moment, staff reasoning and honesty.

### P1: should have if time allows

| ID | Item | Why | Effort | Lane |
|---|---|---|---|---|
| P1-1 | **Closed-loop status timeline and proof of resolution:** staff move an issue Detected → Verified → Sent to 311 → Resolved with a note and after photo; the reporter's submission card updates (see D4) | Research #1, #6; R3, R10 | M · 2 h | FE |
| P1-2 | **Equity lens:** reports per 1,000 residents by ward (ward profiles, 2021 Census) and a "low reports, high need" flag, with sample sizes shown | Research #7; risk E3 | M · 2 h | AI + FE |
| P1-3 | **"Probably already in 311":** fuzzy-match against Toronto's monthly 311 open data (ward + intersection/FSA + type) | Gap C3 | M · 3 h | AI |
| P1-4 | **311-ready report and Open311 GeoReport v2 export:** copyable text plus JSON with service_code, status, media_url, lat/long | Research #9; gap C7 | S · 1 h | FE |
| P1-5 | **"Who owns this?" hints:** TTC, Toronto Hydro, provincial highway (401) or City, from asset proximity | Research #8 | S · 1 h | FE |
| P1-6 | **Verification upgrades:** 2-of-3 consensus; Duplicate / Already fixed / Not an issue; approve/reject submissions; "still there?" re-check | Research #14, #15, #20; R10 | M · 3 h | FE |
| P1-7 | **Automated smoke tests in the repo:** Playwright run through the `features.md` acceptance table | R9 | S · 1.5 h | FE |
| P1-8 | **Shareable links for filtered views:** filters in the URL | Research #21 | S · 1 h | FE |
| P1-9 | **Real "now" for live data:** use the current date unless the sample dataset is loaded | R6 | S · 0.5 h | FE |
| P1-10 | **Official neighbourhood boundaries (158)** for hotspots and assignment | R4 | M · 2 h | AI |

### P2: after the hackathon or feasibility-gated

| ID | Item | Why |
|---|---|---|
| P2-1 | **Real geolocation cascade surfaced in the UI.** The teammates' feasibility work (plan steps 1–2) writes real `geo_trace` values; show the matched reference image. The UI is already built for it. | Gap C2, the core claim; R11 |
| P2-2 | **Mapillary street-level viewer** behind the person icon | `features.md` §2.5; research #19 |
| P2-3 | **Accounts and server-side persistence** for submissions, verifications and saves, enforced by role | R10; `features.md` §7 |
| P2-4 | **Notifications** (email/SMS) on acknowledgement and fix | Research #1 |
| P2-5 | **Multilingual UI** (Toronto's top languages) | Research #13 |
| P2-6 | **Saved searches, custom areas, lasso, column settings, group-by** | `features.md` P1/P2 |
| P2-7 | **Trend and anomaly alerts** | Research #23 |
| P2-8 | **Full WCAG 2.0 AA audit** and anti-abuse controls (backend) | Research #12, #24 |

### Quick fixes (under 30 minutes each, anyone, anytime)

- **Q1** Only allow `http(s)` links in evidence credits and other data-driven links (R8).
- **Q2** Map `broken streetlight` to Other in `analysis/config.toml` (R13).
- **Q3** Pass the pipeline's `privacy.blurred` flag through and show a "Blurred" badge on evidence (R12).
- **Q4** Note in the README which data the app is showing and how to switch (pairs with P0-1).

### Not doing (and why)

- **Replacing 311.** Pitch CivicLens as a feeder into 311; incumbents do intake and case tracking better.
- **Pavement condition scores (PCI/PASER).** Vehicle AI does this systematically; don't claim it.
- **Google Street View scraping or Street View imagery for ML.** The terms forbid it; use Mapillary.
- **Showing poster identities or linking photos to accounts.** Clearview precedent; the GeoSpy misuse risk.
- **Logged-in social-media scraping.** Platform terms and the original plan's privacy rules.

## 6. Suggested sequence for three people

| Order | FE (frontend) | AI (pipeline/AI) | PT (pitch and data) |
|---|---|---|---|
| 1 | P0-1 data switch · quick fixes | P0-3 Gemini triage proxy and prompt | Confirm the Hack the Valley rubric; settle D1–D5 |
| 2 | P0-2 priority queue | P0-4 blur boxes | Ward boundaries download for P0-6; methodology text for P0-10 |
| 3 | P0-5 already-reported | P0-6 official wards | Draft the §7 script; choose the "surprising insight" ward |
| 4 | P0-3/P0-4 upload UI hooks with AI | P0-7 summaries hand-off | Deploy the static site (P0-9) |
| 5 | P0-8 readability · P0-10 page | P1-2 ward population data | Rehearse; record the backup video after feature freeze |
| Then | P1-1 loop · P1-8 links · P1-7 tests | P1-3 311 matching | Devpost write-up with sources and licences |

Set a **feature freeze** about 3 hours before submission. After that, only fixes, rehearsal and the video.

## 7. Demo outline (about 3 minutes, half of it live)

1. **0:00 One sentence:** "311 waits for a report. CivicLens finds the issues Torontonians post about but never file, and shows how sure it is."
2. **0:15 Map:** cluster → issue → "how this location was estimated" with the radius (differentiator 2).
3. **0:45 Live upload:** photo → Gemini fills it in and blurs a plate → "2 neighbours already reported this" → join (P0-3, P0-4, P0-5).
4. **1:30 City Staff:** priority queue with reasons → verify (P0-2; P1-1 if built).
5. **2:00 Ward digest:** one ward, 9 days before the election, one surprising insight (P0-6, P0-7; P1-2 if built).
6. **2:30 Honesty:** methodology page, "signals, not ground truth", privacy, and what breaks first at scale (P0-10).
7. **2:50 Close:** open exports and a GeoReport v2 handoff. "It feeds 311; it doesn't replace it."

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Live Gemini call fails on venue wifi | Cache one demo photo's response; backup video (P0-9) |
| Judges ask "isn't this 311 with AI?" | Lead with differentiator 1 and the 30–35% coverage figure |
| Privacy questions (scraping, Clearview, GeoSpy) | Methodology page, blurring, no poster identities, official APIs and consented uploads only |
| Sampling bias makes some wards look "healthier" | Show sample sizes; equity lens (P1-2); "signals, not ground truth" |
| Election-period sensitivity | The digest stays neutral (the pipeline prompt already forbids mentioning candidates); verified issues only |
| Scope creep in the last hours | Feature freeze; the 8-hour cut |
