# Popular features in civic-reporting apps

Researched 2026-10-17 for the implementation plan (`implementation-plan.md`). Sources are listed at the end. Items marked *(inference)* are judgement, not sourced. App-review evidence is thin (about 10 reviews per App Store page), so treat review themes as signals, not statistics. Hack the Valley's own judging rubric was not found; check its Devpost page.

## 1. Ranked features (# = overall rank)

Effort is hackathon / production. "GeoIssue" is the status as of commit `9321865`.

### Residents
| # | Feature | Evidence | How common | Pain if missing | GeoIssue | Effort | Wow |
|---|---|---|---|---|---|---|---|
| 1 | **Closed-loop status updates** (timeline; notice when acknowledged and fixed) | FixMyStreet users whose first report was fixed were 57% more likely to report again (399k users) [Sjoberg 2017][sj]; Boston users shown photos of their fix sent 60% more requests [Buell 2021][bu]; poor communication is Ombudsman Toronto's top fairness issue [Ombudsman][om] | Every 311 app | People feel ignored and stop reporting | Lacks | S (simulated) / L | Med |
| 2 | **Photo-first, ~10-second reporting** (location from GPS/EXIF, few fields, guest mode) | Snap Send Solve 4.8★/12K, "takes me about 10 seconds" [SSS][sss]; Toronto 311 app 2.8★/80 with complaints about too many questions and photo permissions [T311][t311]; Toronto cut questions in 2025 [staff report][tor1] | Every app | Abandoned reports, wrong locations | Partial | S / M | Med |
| 3 | **Live AI triage** (photo → suggested category, severity, description, editable) | Edmonton 311 shipped it July 2026 [Edmonton][edm]; Philadelphia's 2025 RFI names "selecting wrong service" and manual processing as bottlenecks [RFI][phl]; Boston: miscategorised requests send crews to the wrong jobs [Boston][bos] | Emerging | Misrouting, staff re-triage | Partial (offline only) | M / L | High |
| 4 | **"Already reported nearby"** at submit time, with +1/subscribe | FixMyStreet checks open same-category reports within a radius [mySociety][dup1], [SocietyWorks][dup2]; DC311 advertises duplicate detection [DC311][dc] | Modern platforms | Duplicate noise | Partial (offline dedup) | S / M | Med-High |
| 8 | **"Who owns this?" routing** (City vs Toronto Hydro, TTC, provincial highways, private) | Toronto added redirects for utility poles in 2025 after a councillor's letter [staff report][tor1]; routing is Snap Send Solve's core value [SSS][sss]; "closed – outside jurisdiction" confuses residents [Citrus Heights][ch] | Common outside 311 | Reports die silently | Lacks (overlays exist) | S (rules) / L | Med |
| 11 | **Privacy:** blur faces and plates, strip EXIF, hide reporter identity | Canada's Privacy Commissioner expects "proven and effective blurring technologies for faces and vehicle licence plates" plus takedown [OPC][opc]; Mapillary blurs automatically [Mapillary][map]; backlash over photographing parked cars [City Hub][hub]; Philadelphia made requests private after abuse [phila.gov][phl2] | Standard for street imagery, rare in 311 | Legal risk, chilling effect | Lacks | M / M | High |
| 12 | **Accessibility** (WCAG AA, table alternative to the map, keyboard) | AODA has required WCAG 2.0 AA for Ontario public-sector sites since 2021 [Littler][aoda]; US DOJ requires WCAG 2.1 AA by April 2027 [DOJ][doj]; CDC treats a data table + CSV as the compliant map alternative [CDC][cdc] | Required in procurement | A city can't adopt it | Partial (table exists) | S / M | Low |
| 13 | **Multilingual** UI and reports | Toronto 311 has 180+ languages by phone but the site relies on auto-translate [toronto.ca][lang]; low English proficiency tracks with under-reporting [Kontokosta][ko2] | Big-city 311 | Excludes newcomers | Lacks | S (2–3 languages) / M | Med |
| 18 | **"My reports" history** and optional account | Toronto is assessing logins for request history [staff report][tor1]; FixMyStreet users dislike logging in per report [FMS][fms] | Every app | Can't follow up | Partial (Saved) | S / M | Low |

### Volunteers and verifiers
| # | Feature | Evidence | How common | Pain if missing | GeoIssue | Effort | Wow |
|---|---|---|---|---|---|---|---|
| 14 | **Multi-person consensus** with confidence levels | Zooniverse retires items after N classifications [TESS][tess]; volunteer consensus matched experts >97% on Snapshot Serengeti [overview][zoo]; Ushahidi found plain verified/unverified tags unmanageable [Ushahidi][ush] | Standard in citizen science | One person's error or gaming slips through | Partial (single confirm) | S / M | Med |
| 15 | **"Still there?" re-check and reopen** | FixMyStreet questionnaires; complaints about "fixed" notices while the problem remains [Bristol][bri]; SeeClickFix users ask to reopen [review][scf1] | Rare | False closures erode trust | Lacks | S / M | Med |
| 19 | **Street-level imagery** for remote checking | Mapillary imagery is already blurred [Mapillary][map]; faster verification is *(inference)* | Rare | Site visits | Placeholder | M / M | High |
| 20 | **More outcomes + second review** (Duplicate, Already fixed, Not an issue) | MapRoulette statuses and reviewer step [MapRoulette][mr]; Uchaguzi checks duplicates and logs notes [Uchaguzi][uch] | Common | Ambiguous data | Partial | S / S | Low |
| 25 | **Bite-sized tasks** with quality feedback | Most volunteers are short-burst "dabblers" [Eveleigh 2014][eve] | Common | Drop-off | Partial | S / M | Low |

### City staff
| # | Feature | Evidence | How common | Pain if missing | GeoIssue | Effort | Wow |
|---|---|---|---|---|---|---|---|
| 5 | **Explainable priority queue** ("why this is #1") | Philadelphia names manual processing as a bottleneck [RFI][phl]; staff needing reasons is *(inference)* | Rare | Triage favours the loudest | Has in pipeline, not in UI | S / M | High |
| 6 | **Proof of resolution** (status notes + "after" photo) | Showing the work raised trust 14% [Buell][bu]; NYC closure notes often "ambiguous" [NYC Council][nyc]; DC shows the full life cycle [DC311][dc] | Growing | "Closed" means nothing | Partial | S / M | Med-High |
| 7 | **Equity lens** (reports per capita, under-reporting flags) | Low-income and minority neighbourhoods under-report despite greater need [Kontokosta & Hong][ko]; Toronto: 311 data is "limited to those who actively engage" [report][tor2]; pair citizen reports with planned inspection [SocietyWorks][sw] | Rare | Resources follow the loud | Lacks | S–M / M | High |
| 9 | **Open311 GeoReport v2 output** and work-order handoff | Standard fields: service_code, status, status_notes, media_url, lat/long [Open311][o311]; Philadelphia lists integrations first [RFI][phl] | Many cities | Can't plug into city systems | Lacks | S (export) / L | Low–Med |
| 16 | **Location confidence and verification** | Philadelphia names "inconsistent location accuracy" and wants geolocation verification [RFI][phl]; users misread uncertainty circles [Hegarty][heg] | Emerging | Crews sent to the wrong spot | Has (illustrative) | S / M | Med |
| 17 | **Service-standard metrics** (time to close vs target, by ward) | Toronto's Service Standard Dashboard (Oct 2025), interactive version planned Q1 2026 [dashboard][tdash], [report][tor2] | Growing | No accountability | Partial | S / M | Med |
| 24 | **Anti-abuse controls** | Philadelphia wants "blocking bad actors" [RFI][phl] | Common | Spam, harassment | Lacks | S / M | Low |

### Journalists, researchers and councillors
| # | Feature | Evidence | How common | Pain if missing | GeoIssue | Effort | Wow |
|---|---|---|---|---|---|---|---|
| 10 | **Ward digest / councillor brief** | Toronto's election is Oct 26, 2026 [toronto.ca][elec]; the City will send 311 trend reports to Council twice a year from Q2 2026 [report][tor2] | Rare | No ward-level picture | Has | S (polish) / M | High |
| 21 | **Shareable permalinks** of filtered views | Reporters need a stable view to cite *(inference)* | Common in portals | Can't cite | Lacks (issue links only) | S / S | Med |
| 22 | **Methodology and caveats panel**, data dictionary | Dashboards should be read with their limits stated [Kitchin][kit], [URBACT][urb]; Toronto warns 311 volume ≠ satisfaction [report][tor2] | Moderate | Misleading stories | Partial | S / S | Low |
| 23 | **Trend and anomaly alerts** | Toronto plans comms around seasonal peaks [report][tor2] | Emerging | Missed emerging issues | Partial | S–M / M | Med |

## 2. Top 10 complaints about existing apps

1. **"Closed" doesn't mean fixed** (closed when referred, inspected or outside jurisdiction) [Citrus Heights][ch], [Raleigh][ral], [NYC Council][nyc], [Bristol][bri].
2. **Silence after submitting** [Ombudsman][om].
3. **Crashes and network errors that wipe the form** [T311][t311], [SSS][sss].
4. **Photo upload friction** (full photo-library access, bounced to home screen) [T311][t311].
5. **Wrong or hard-to-enter locations** [T311][t311], [FMS][fms], [SeeClickFix][scf].
6. **Too many steps** (repeated logins, retyping contact details) [FMS][fms], [T311][t311], [SSS][sss].
7. **Can't edit or reopen a report** [SeeClickFix][scf], [review][scf1].
8. **Sent to the wrong agency** [Raleigh][ral], [staff report][tor1], [review][scf1].
9. **Cluttered maps** (stale resolved pins, no filters) [FMS][fms].
10. **Privacy and "snitching" worries** [City Hub][hub], [SeeClickFix][scf], [phila.gov][phl2].

An app is "only as useful as the [city's] interest in fixing problems" [SeeClickFix][scf], a reason to show the City's response, not only report counts *(inference)*.

## 3. What makes civic-tech demos memorable

- **One complete live path beats ambition**; narrow scope shows judgement [judge notes][dev].
- **A sentence judges can repeat**: what it is and who it's for, up front [judge notes][dev].
- **Be honest about weaknesses**: naming what breaks first at scale raised scores [judge notes][dev].
- **Plan for wifi failing**: a 60-second backup video; ~3 minutes, half live demo [judge notes][dev], [demo tips][tips].
- **Typical rubric**: innovation, technical execution, impact, presentation [HackTheSpace][hts]. Confirm Hack the Valley's.
- **Real local data and municipal fit**: Canadian municipal staff value hackathons for open-data feedback [Robinson & Johnson][rj]; Toronto wards, TTC, Open311 and AODA vocabulary signal adoptability *(inference)*.
- **Tell the whole loop** *(inference, grounded in [Buell][bu])*: photo → AI fills it in → "3 neighbours already reported this" → staff queue with reasons → fixed with an after photo → resident notified.
- **Lead with one surprising insight** *(inference)*: "Ward X has the most need but the fewest reports" [Kontokosta & Hong][ko], tied to the election.

## 4. If we only had 8 more hours

1. **Live AI ingestion in Upload (~3h):** Gemini suggests category, severity, description with confidence.
2. **"Already reported nearby" + join (~1h):** reuses the dedup logic; "3 neighbours already reported this".
3. **Closed-loop status (~1.5h):** staff marks fixed with an after photo; the resident's receipt and timeline update.
4. **Equity layer (~1.5h):** reports per 1,000 residents by ward plus a "low reports, high need" flag.
5. **Face and plate blurring on upload (~1h):** same Gemini call returns boxes; blur on a canvas; show before/after *(check Gemini's box quality)*.

If time remains: GeoReport v2 JSON export (~30 min).

## Sources

[sj]: https://ora.ox.ac.uk/objects/uuid:2bd169fd-0b27-46e4-8b81-1ccfccf7c55a/files/ma5b19b3d0c0005e21d0bc3e457691bf5
[bu]: https://www.informs.org/News-Room/INFORMS-Releases/News-Releases/Show-Me-Don-t-Tell-Me-Operational-Transparency-Increases-Trust-Support-of-Government
[om]: https://www.ombudsmantoronto.ca/news/toronto-ombudsman-saw-record-cases-in-2024-indicating-increasing-demand-for-accountability-in-local-government/
[sss]: https://apps.apple.com/au/app/snap-send-solve/id377854149
[t311]: https://apps.apple.com/ca/app/311-toronto/id1558520141
[fms]: https://apps.apple.com/gb/app/fixmystreet/id297456545
[scf]: https://apps.apple.com/ca/app/seeclickfix/id322000552
[scf1]: https://apple.co/2JDWZ7g
[tor1]: https://www.toronto.ca/legdocs/mmis/2025/gg/bgrd/backgroundfile-255055.pdf
[tor2]: https://www.toronto.ca/legdocs/mmis/2025/se/bgrd/backgroundfile-259847.pdf
[tdash]: https://www.toronto.ca/home/311-toronto/311-service-standard-dashboard/
[phl]: https://www.phila.gov/media/20250814085348/rfi-OIT-311-mobile-app-addendum-info-session-2025-08-07.pdf
[phl2]: https://www.phila.gov/services/trash-recycling-city-upkeep/track-a-service-request-with-311/
[edm]: https://311.edmonton.ca/posts/welcome
[bos]: https://github.com/CityOfBoston/summerofcode/blob/main/index.md
[dc]: https://ouc.dc.gov/page/dc311-mobile-app
[dup1]: https://www.mysociety.org/2019/04/24/stop-right-there-thats-already-been-reported/
[dup2]: https://www.societyworks.org/2023/05/25/the-duplicate-report-suggestion-radius-on-fixmystreet-pro-is-now-customisable/
[ch]: https://citrusheightssentinel.com/?p=2076923
[ral]: https://theraleighcommons.org/raleighpublicrecord/wp-json/wp/v2/posts/22055
[opc]: https://www.priv.gc.ca/en/privacy-topics/surveillance/video-surveillance-by-businesses/02_05_d_39_prov
[map]: https://blog.mapillary.com/update/2018/04/19/accurate-privacy-blurring-at-scale.html
[hub]: https://cityhub.com.au/?p=129580
[aoda]: https://www.littler.com/news-analysis/asap/ontario-canada-impending-aoda-compliance-deadlines
[doj]: https://campustechnology.com/articles/2026/04/27/doj-extends-deadline-for-ada-title-ii-compliance.aspx
[cdc]: https://www.cdc.gov/cove/about/section-508-accessibility.html
[lang]: https://www.toronto.ca/home/translate/
[ko]: https://marroninstitute.nyu.edu/papers/bias-in-smart-city-governance-how-socio-spatial-disparities-in-311-complaint-behavior-impact-the-fairness-of-data-driven-decisions
[ko2]: https://arxiv.org/pdf/1710.02452
[sw]: https://www.societyworks.org/research-and-guidance/can-relying-on-citizen-reports-make-neighbourhoods-worse/
[tess]: https://arxiv.org/pdf/2011.13944
[zoo]: https://jdmdh.episciences.org/5759/pdf
[ush]: https://hblog.org/2011/11/11/what-is-the-next-step-for-ushahidi-verification/
[uch]: https://docs.ushahidi.com/uchaguzi-support/digital-response-teams/verification
[bri]: https://fixmystreet.bristol.gov.uk/report/8387335
[mr]: https://learn.maproulette.org/en-US/documentation/reviewing/
[eve]: https://discovery.ucl.ac.uk/id/eprint/1418573/
[nyc]: https://council.nyc.gov/data/311-agency/
[o311]: https://wiki.open311.org/GeoReport_v2/
[heg]: https://www.ualberta.ca/psychology/media-library/pdfs/news-and-events/news/hegarty-friedman-boone-barrett-16jepapp.pdf
[elec]: https://www.toronto.ca/news/fact-sheet-2026-toronto-municipal-election/
[kit]: https://mural.maynoothuniversity.ie/id/eprint/5694/
[urb]: https://archive.urbact.eu/node/8068
[dev]: https://dev.to/kurbaitaev/what-judges-actually-score-notes-from-a-year-of-hackathon-judging-3p4l
[tips]: https://blogs.reskilll.com/hackathon-demo-presentation-tips-pitch-3-minutes-win-2026/
[hts]: https://hackquest.io/hackathons/HackTheSpace-Season-2
[rj]: https://libuwspaceprd02.uwaterloo.ca/handle/10012/11063
