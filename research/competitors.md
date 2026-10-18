# Competitive scan

Researched 2026-10-17 for the implementation plan (`implementation-plan.md`). Most product claims come from vendor material and are labelled as such; "unverified" means no primary source was found. Check anything you quote in the pitch.

## A. Competitors and close analogues

### 1. Resident reporting / 311

**311 Toronto app and portal (City of Toronto)** is the incumbent.
- **Who it serves:** residents and City staff.
- **What it does:** 600+ request types with a photo and GPS pin, a tracking number, opt-in SMS/email updates, an "Explore Map" of open requests within 8 km, and live-agent chat ([App Store](https://apps.apple.com/ca/app/311-toronto/id1558520141), [City](https://www.toronto.ca/home/311-toronto-at-your-service/311-mobile-apps)).
- **Verification:** staff triage; a duplicate still gets its own tracking number.
- **Data access:** monthly open data (last refreshed 2026-10-08) with the ward, but location only as postal-code prefix (FSA) or intersection. It covers about 30–35% of 311 contacts and 6 of 45 divisions ([CKAN metadata](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_show?id=311-service-requests-customer-initiated)). The Open311 API dataset was retired in December 2021.
- **Weaknesses:** 2.8★ on iOS from 80 ratings, English-only listing, photo-permission loops in reviews, no AI.

**SeeClickFix 311 CRM (CivicPlus)** is the US leader for resident reporting plus staff work management.
- Public issue map, photos, follow/comment, staff merging of duplicates ([Albany](https://albanyny.gov/2443/), [Dublin CA](https://dublin.ca.gov/2314)); Open311-compatible API.
- **New in January 2026:** AI photo analysis that suggests the request category ([GovTech](https://www.govtech.com/biz/civicplus-new-ai-tools-work-for-meetings-crm-websites)).
- **Pricing:** about $11k–$39k/year for small cities; about $170k over 3 years for Birmingham, AL ([Muskegon](https://muskegon-mi.gov/documents/view/63/6052/), [WBRC](https://www.wbrc.com/2025/01/22/see-click-fix-app-gets-3-year-extension-birmingham-residents/)). No Canadian deployments verified.

**FixMyStreet / FixMyStreet Pro (mySociety / SocietyWorks, UK).**
- Open-source platform; the council product (Pro) starts at £15k/year ([pricing](https://www.societyworks.org/how-to-buy/)). Map pin, photo, email updates, Open311 back-office integration.
- **Deduplication at intake:** suggests open nearby reports of the same category while the resident types; councils set the radius per category ([2024](https://www.societyworks.org/2024/04/02/you-can-now-customise-fixmystreet-pros-duplicate-report-radius-per-category/)).
- Translated via Transifex; deployed in the UK, Norway, Sweden, Switzerland, Croatia, Kosovo, Uruguay and Australia, not Canada ([sites](https://fixmystreet.org/sites)). No AI detection found.

**Snap Send Solve (Australia/NZ).** Free for residents; reports routed by GPS to 850+ paying "Solver" organisations ([site](https://www.snapsendsolve.com/)). Up to 5 photos. Per its own statement: AI categorisation and routing, duplicate detection, offensive-content flagging with human review, and a "Sensitivity Flag" that blurs sensitive content ([AI statement](https://www.snapsendsolve.com/ai-transparency-statement)). Not in Canada.

**Others:** BOS:311 (Boston, since 2009; photo reports feed work orders, [boston.gov](https://www.boston.gov/civic-engagement/bos311-app)); CitySourced (merged into Rock Solid 2019, bought by Granicus 2022, [GovTech](https://www.govtech.com/biz/citysourced-merges-with-rock-solid-in-private-equity-deal.html)); Accela/PublicStuff (status unverified).

### 2. AI road and asset detection from imagery

- **Vialytics:** phone on a municipal vehicle photographs the road every ~10 ft; AI flags cracking, potholes, signs, drains, markings; map dashboard with work orders. Claims 300–1,000+ communities (its own pages disagree) ([site](https://www.vialytics.com/)). Pricing and blurring not stated.
- **RoadBotics by Michelin:** smartphone imagery → road ratings; bought by Michelin in 2022; "300+ communities assessed" ([Technical.ly](https://technical.ly/startups/roadbotics-acquired-by-michelin)).
- **Blyncsy / Payver (Bentley):** AI on crowdsourced dashcam imagery (vendor: 800k+ vehicles, 40–50+ defect types, [GeoWeek](https://geoweeknews.com/news/bentley-systems-blyncsy-infrastructure-ai-machine-learning)); since 2025 also Google Street View via "Imagery Insights" ([Bentley](https://www.bentley.com/news/bentley-systems-partners-with-google-to-improve-infrastructure-through-asset-analytics/)). Priced per road mile. The closest "no new hardware" analogue, but roads only and for staff.
- **Cyclomedia:** survey-grade 360° imagery + LiDAR, AI asset and pavement scoring (PASER/ASTM), AI face/plate blurring, ArcGIS/QGIS viewer ([products](https://cyclomedia.com/products), [ethical AI](https://go.cyclomedia.com/us-ethical-ai-use)).
- **Active in Canada:** StreetScan (vehicles and sidewalk scooters, claims 100+ Canadian clients, [Essex](https://www.countyofessex.ca/news/posts/vehicle-mounted-technology-used-to-assess-essex-county-roads/)); Vaisala/Xweather RoadAI (Montréal bike network, Region of Waterloo, [Xweather](https://xweather.com/blog/article/roadai-x-montreal)); Calgary's in-house model with AltaML ([CBC](https://amp.cbc.ca/news/canada/calgary/ai-calgary-roadwork-potholes-1.7003767)); Markham's 2020 pilot ([CBC](https://www.cbc.ca/news/canada/toronto/markham-pilots-ai-smartphone-app-to-detect-potholes-1.5591235)). No Toronto AI pavement program found (unverified).
- **City Detect (Alabama):** the most similar issue taxonomy: garbage-truck cameras flag 100+ blight types (graffiti, dumping, overgrowth). Dallas flagged 21,000+ properties; Stockton pays $237,600/year; Huntsville residents raised privacy questions ([Axios](https://www.axios.com/local/huntsville/2025/07/24/huntsville-ai-garbage-truck-cameras-code-enforcement-city-detect)).

### 3. Public-signal / social-media intelligence

- **Zencity:** AI analysis of social media, news, 311 and surveys for 400+ governments (US, Canada, UK); $10–20k/year small to ~$1M largest ([StateScoop](https://statescoop.com/?p=65202)); Vancouver office. Text sentiment, not geolocated photo-backed issues. Backlash: 2,000 signatures against Minneapolis's contract in 2025 ([Spokesman-Recorder](https://spokesman-recorder.com/2025/09/20/minneapolis-zencity-contract-protest/)); EFF/ACLU surveillance concerns ([IAPP](https://iapp.org/news/a/law-enforcement-using-ai-software-to-patrol-social-media)).
- **Dataminr First Alert:** real-time emergency alerts from 1M+ public sources; Esri/ArcGIS feed and API ([Dataminr](https://www.dataminr.com/products/first-alert)). Built for emergencies, not chronic infrastructure.
- **Polco, Go Vocal (CitizenLab):** surveys and idea boards with AI text "sensemaking" ([GovTech](https://www.govtech.com/biz/engagement-tech-firm-citizenlab-rebrands-as-go-vocal)). Opt-in input, not passive detection.

### 4. Crowdsourced mapping and verification

- **Ushahidi:** open-source crowd-reporting map with admin review before publishing; AI classification/translation with Dataminr ([case](https://www.dataminr.com/resources/case-study/ushahidi-creates-new-ai-models-with-dataminr-to-improve-data-management/)).
- **Mapillary (Meta):** crowdsourced street-level imagery, CC BY-SA 4.0, free API, automatic face/plate blurring, 1,500+ sign types ([licence](https://help.mapillary.com/hc/en-us/articles/115001770409), [tech](https://www.mapillary.com/technology)). The legally cleanest reference imagery for GeoIssue's matching step. Toronto coverage not checked.
- **Waze for Cities:** Toronto joined in 2017 ([CP24](https://www.cp24.com/news/city-of-toronto-begins-sharing-data-with-popular-traffic-app-waze-1.3685878)). Since April 2026 Waymo feeds pothole detections into it in 5 US metros (~500 potholes, location only, verified by Waze users) ([Waymo](https://waymo.com/blog/2026/04/partnering-with-waze-to-help-cities-patch-their-potholes/)).
- **Project Sidewalk (University of Washington):** volunteers label sidewalk accessibility problems in Street View, ML validates; ~40 cities, none in Canada; the remote crowd found 92% of problems in a DC study ([arXiv 2026](https://arxiv.org/abs/2602.09216v2)). The best precedent for GeoIssue's volunteer queue.
- **OSM Notes / MapRoulette:** general micro-tasking, ~40k tasks/month ([OSM US](https://openstreetmap.us/news/2023/03/MapRoulette_Announcement/)).

### 5. Civic data dashboards

- **Toronto 311 Service Standard Dashboard and 311 BI:** public volumes and service levels ([City](https://www.toronto.ca/home/311-toronto/311-service-standard-dashboard/)); ward filters planned for Q1 2026 (not confirmed live); councillors have internal ward dashboards ([2024 report](https://www.toronto.ca/legdocs/mmis/2024/ex/bgrd/backgroundfile-244535.pdf)). No photos, severity or non-311 signal.
- **NYC 311 maps, LA "311 Data" (Hack for LA):** aggregates by district ([NYC](https://www.nyc.gov/site/311reporting/311-reports/service-request-maps.page), [GitHub](https://github.com/hackforla/311-data)). Probably what judges picture when they hear "ward digest".
- **Adjacent risk: GeoSpy (Graylark):** AI photo geolocation; 404 Media found it used to try to stalk women; public access closed January 2025; tests suggest city/area-level accuracy, not street level ([404 Media](https://www.404media.co/the-powerful-ai-tool-that-cops-or-stalkers-can-use-to-geolocate-photos-in-seconds/)).

## B. Feature matrix

CL = GeoIssue today. T311 = 311 Toronto; SCF = SeeClickFix; FMS = FixMyStreet; SSS = Snap Send Solve; VEH = vehicle pavement AI (Vialytics, RoadBotics, StreetScan, RoadAI); BLY = Blyncsy/Payver; CYC = Cyclomedia; CD = City Detect; ZC = Zencity; DMR = Dataminr; USH = Ushahidi; MAP = Mapillary; WAZE = Waze for Cities; PS = Project Sidewalk; DASH = public 311 dashboards.

| Feature | CL | T311 | SCF | FMS | SSS | VEH | BLY | CYC | CD | ZC | DMR | USH | MAP | WAZE | PS | DASH |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Map + clustering | ✓ | partial | ✓ | ✓ | ? | ✓ | ✓ | ✓ | ? | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Photo upload (public) | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ |
| AI issue detection (image) | partial¹ | ✗ | partial | ✗ | partial | ✓ | ✓ | ✓ | ✓ | ✗ | ? | ✗ | ✓ | partial | partial | ✗ |
| Auto photo geolocation | partial¹ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ? | ✗ | partial | ✗ | ✗ | ✗ |
| Location-uncertainty display | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ? | ✗ | ✗ | ✗ | ✗ | ✗ |
| Deduplication | ✓ (pipeline) | partial | partial | ✓ | ✓ | partial | ? | ✗ | ? | ✗ | partial | ? | ✗ | partial | partial | partial |
| Status / case lifecycle | partial | ✓ | ✓ | ✓ | partial | partial | ✗ | ✗ | partial | ✗ | ✗ | partial | ✗ | partial | ✗ | partial |
| Notifications to reporters | ✗ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ? | ✗ | ✗ | ✗ | ✗ |
| 311 / work-order integration | ✗ | ✓ | ✓ | ✓ | partial | ✓ | partial | partial | partial | ✗ | partial | ✗ | ✗ | partial | ✗ | ✗ |
| Public dashboard | ✓ | ✓ | partial | partial | ✗ | ✗ | ✗ | ✗ | ✗ | ? | ✗ | ✓ | partial | ✗ | ✓ | ✓ |
| Ward / district reports | ✓ | partial | ? | ✓ | ✗ | partial | partial | ✗ | partial | partial | ✗ | partial | ✗ | ✗ | ✓ | ✓ |
| Open data export / API | ✓ | partial | ✓ | ✓ | ? | partial | ✗ | ✗ | ✗ | ✗ | partial | ✓ | ✓ | partial | ✓ | ✓ |
| Volunteer / community moderation | ✓ | ✗ | partial | partial | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | partial | ✓ | ✓ | ✗ |
| Street-level imagery | placeholder | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ | ✗ |
| Face / plate blurring | ✗ | ? | ? | partial | partial | ? | partial | ✓ | ? | n/a | ? | ✗ | ✓ | n/a | partial | n/a |
| Multilingual | ✗ | partial | ? | ✓ | ? | partial | ? | ? | ? | ✓ | ✓ | ✓ | partial | ✓ | partial | partial |
| Accessibility (documented)² | partial | partial | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | partial | ? |
| Mobile app | web, responsive | ✓ | ✓ | partial (PWA) | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | partial | ✗ |

¹ Offline in the analysis pipeline from the photo-analysis output; not live in the app. ² No competitor's WCAG/AODA conformance could be verified, which leaves an open lane.

## C. Gaps GeoIssue can credibly own

1. **Issues that never reach 311.** Every reporting app waits for a resident to file; Toronto's open 311 data covers about 30–35% of contacts and 6 of 45 divisions. Zencity mines social posts for sentiment, not geolocated, photo-backed issue records.
2. **Geolocating untagged photos, honestly.** Only 0.3–3% of tweets carry a geotag (Francalanci et al., 2018) and platforms strip EXIF; matching social photos to street imagery is still preliminary research ([ISPRS 2026](https://isprs-archives.copernicus.org/articles/XLIX-B3-2026/1277/2026/)). Nothing found shows a confidence radius.
3. **Cross-channel deduplication plus an "already in 311?" check** against the monthly 311 data (ward + intersection/FSA + type).
4. **Election-ready ward digests backed by evidence.** The City's ward dashboards are internal; NYC/LA district dashboards show no photos or severity. Voters choose a mayor and 25 councillors on Oct 26.
5. **Sidewalks, parks, transit and flooding without new hardware.** Vehicle AI covers roads fleets drive; resident photos already cover sidewalks, laneways, TTC stations and flooding.
6. **Social signal that is transparent and private by design**, the opposite of the Zencity, GeoSpy and City Detect controversies.
7. **Open, queryable data.** Competitors are closed and Toronto retired its Open311 API dataset; GeoIssue already exports CSV, GeoJSON and SQL, and could emit Open311 GeoReport v2.

## D. What judges will compare GeoIssue to

- "Isn't this 311 Toronto or SeeClickFix with AI?" (SeeClickFix now does AI photo categorisation.)
- Waze, Google Street View, Blyncsy, City Detect; Zencity or Dataminr if social media comes up; GeoSpy if geolocation comes up; Toronto's 311 dashboard for the ward digest; multimodal reasoning quality for the Gemini track.

**Five differentiators to say out loud:**
1. "311 waits for a report; GeoIssue finds the issues people post about but never file." (30–35% coverage; 0.3–3% geotags.)
2. "We show our uncertainty." (Radius plus the "how this was located" trace, the opposite of GeoSpy's black box.)
3. "One issue, many sightings." (Cross-source dedup, linked to existing 311 records.)
4. "A ward digest, with evidence, before October 26." (Public and exportable; the City's ward views are internal.)
5. "No new hardware, humans check the AI, privacy built in."

## E. Risks

1. **Incumbents handle intake and case tracking better.** Position GeoIssue as a feeder into 311, not a replacement.
2. **Vehicle AI is more systematic for pavement.** Don't claim pavement condition scores (PCI/PASER).
3. **Sampling bias.** Wards with fewer people posting look "healthier" ([Street Sense, arXiv](https://arxiv.org/pdf/1807.06075)). Show sample sizes, normalise, label outputs "signals, not ground truth".
4. **Scraping and privacy law.** Platform terms prohibit scraping; Canada's Privacy Commissioner ruled in the Clearview AI case that PIPEDA's "publicly available" exception does not cover reusing social-media images for unrelated purposes ([PIPEDA Findings #2021-001](https://priv.gc.ca/en/opc-actions-and-decisions/investigations/investigations-into-businesses/2021/pipeda-2021-001)); the BC Court of Appeal upheld the BC finding in February 2026. Use official APIs and consented uploads, blur, store derived data only, offer takedown.
5. **Geolocation misuse (GeoSpy).** Only geolocate public-realm civic issues, show coarse public locations, never link a photo back to its poster.
6. **Street View terms** restrict scraping and ML use ([terms](https://cloud.google.com/terms/maps-platform/maps-analytics-service-terms)). Use Mapillary (mind CC BY-SA share-alike).
7. **Election-period sensitivity.** Brigading or AI-generated photos could skew ward digests; publish the method, check provenance, require verification before an issue counts in a digest.
8. **Accuracy claims.** Keep severity and location claims modest and calibrated.
