# Case study: geolocating test photo `images/1.png` (LLM + tools)

Date of run: 2026-10-17, 02:31 to about 04:15 EDT (roughly 1 h 45 min of wall-clock time, including Overpass retries and writing these notes).
Prior allowed: "somewhere in the City of Toronto / GTA". Nothing else was assumed.
The image was never uploaded anywhere. Only text queries, Wikimedia Commons and UTSC web pages (downloading reference photos) and the OSM Overpass API were used.
People in the frame were ignored.

Working files (all in `C:/Users/Bader-A/AppData/Local/Temp/claude/C--Users-Bader-A-code-Hackathons-hack-The-Valley-26/828dd531-f602-48f2-a734-2399bb1437cf/scratchpad/geoloc_case/`):
- `crop.py`, `enh.py`, `grid.py`: crop, enhance and grid overlays for pixel measurement
- `refs/`: downloaded Commons and UTSC reference photos, plus contact sheets `sheet1-6.jpg`
- `osm/`: raw Overpass JSON (`utsc_bldg.json`, `utsc_bgeom.json`, `utsc_roads.json`, `utsc_extra.json`)
- `plotmap.py` with `map1-3.png`: OSM plots in local metres
- `fit.py`, `fit2.py`: least-squares camera pose fits
- `overlay.png`: fitted camera and view cone drawn on OSM

---

## Clues

Confidence: H = high, M = medium, L = low.

| # | Clue | Detail | Conf. |
|---|------|--------|-------|
| 1 | Image source | Google Street View screenshot. It has the navigation-arrow overlay (bottom right), the blurred camera car (bottom centre-right) and a faint "© 20?0 [Google]" watermark in the sky. The year is unreadable (2020 or 2026). So the camera sits on a drivable lane, about 2.3 to 2.8 m above the road. | H |
| 2 | Setting | Suburban institutional or post-secondary campus: modern academic buildings set on lawns and mounds, campus lamp posts with banners, private-property signage, pedestrians with backpacks. | H |
| 3 | Left building | About 5-storey dark, printed/fritted glass box with a light frame, sitting on concrete pillars over a glazed ground floor. A lighter box is stacked on top. A 2-storey wing adjoins it to the right, clad in dark grey panels with horizontal slot windows, plus an angled light-grey "fin" wall. A small concrete kiosk sits in front. | H (description) |
| 4 | Right building | About 4-storey beige/buff block with a large dark mechanical penthouse with fans/stacks (lab-style or heavy HVAC) and a tall dark curtain-wall window. A 2-storey grey and glass volume sits in front of it. | H (description) |
| 5 | Signage | "COMMERCIAL DELIVERIES ONLY", with the header probably "PRIVATE PROPERTY" and towing fine print. Two Ontario Rb-19 "Do Not Enter" signs facing the camera, meaning a one-way lane flows toward the camera. | H for the text, M for the header |
| 6 | Lamp-post banner | Maroon/dark red with 5 lines of white caps (unreadable even after enhancement) and a white lower panel with a logo. This misled me toward York (red) for a while. | L |
| 7 | Road markings | Two ladder (zebra) crosswalks that are collinear in the image, an X-style approach mark, a short yellow line, a kerbed tip island with a lamp post, and a long tree-lined median beyond it. Together these mean a divided one-way entrance road. | H |
| 8 | Street furniture | Black lamp posts with a single-arm LED head and banner arms. Two large black wooden flower planters block a former roadway (pedestrianised or closed link). | H |
| 9 | Vegetation and season | A mature pine row along a road, young street trees on the median, full leaf, browning lawns and a hazy sky. Mid/late summer. | M |
| 10 | Context | At the far left, single-storey bungalows with brown roofs sit across a road behind the pines, so the campus edge abuts 1950s-60s housing. A red vehicle in the far distance may be a TTC bus, which would point to Toronto proper (unconfirmed). | M |
| 11 | Absences | No towers, highway or dense urban fabric. Suburban GTA. | M |

## Hypotheses

Initial ranking, after clue extraction (about 9 minutes):

1. **University of Toronto Scarborough (UTSC).** Suburban campus surrounded by bungalow neighbourhoods, a TTC-served bus loop, and many 2000s-2010s glass buildings. Prior about 25%.
2. **University of Toronto Mississauga (UTM).** Pines, ring road, modern glass buildings. About 20%.
3. **York University Keele.** The red/maroon banner fits York's colour. About 15%.
4. **Humber North, Seneca Newnham, Centennial Progress/Morningside, Sheridan Davis/Trafalgar.** About 25% combined.
5. **Ontario Tech / Durham College (Oshawa).** About 5%.
6. **Non-campus institutional sites** (hospital or research campus such as Sunnybrook or Sanofi Connaught). About 10%. The lab penthouse and "commercial deliveries" sign fit these too.

How the ranking actually evolved:

- I checked UTSC first, but only its two best-known new buildings (Instructional Centre, Environmental Science & Chemistry). Neither matched, and I wrongly down-weighted the whole campus.
- About 35 minutes then went to eliminating UTM, York, Sheridan, Humber, Seneca, Centennial and Durham from Commons photos.
- A re-crop (Rb-19 signs, possible red TTC vehicle) plus the Commons "UTSC aerial view 2024" brought UTSC back. The aerial shows bungalows directly across Military Trail and a beige Arts & Administration building.
- Overpass building names then gave the full candidate list within 300 m.

## Tool trace

| Step | Tool | Query | Result | Did it narrow the area? |
|------|------|-------|--------|-------------------------|
| 1 | Read (image) | View panorama | Campus scene, Street View UI, planters, divided road | Yes: setting type (about 9 min for steps 1-2) |
| 2 | Python/Pillow crops and enhancement | Banner, sign, watermark, both buildings, far left | "COMMERCIAL DELIVERIES ONLY"; banner unreadable; watermark year ambiguous; bungalows at far left | Partly: campus at a residential edge |
| 3 | WebSearch | UTSC Environmental Science & Chemistry Building cladding/architect | Diamond Schmitt; brick + glass with vertical fins; next to the Instructional Centre | No (pushed me away from UTSC) |
| 4 | WebSearch | UTM Terrence Donnelly HSC exterior | Stainless-steel stacked boxes | No |
| 5 | Commons API search + curl thumbnails + Read | UTSC Instructional Centre, ESCB | No match (IC is pale green glass; ESCB is brick with yellow fins) | **False negative:** UTSC down-weighted (dead end, about 7 min) |
| 6 | Commons search + Pillow contact sheet | UTM, Humber LRC, Sheridan Davis, Seneca Newnham | No match | Weak eliminations |
| 7 | Commons category API + contact sheet | UTM (IC, Innovation Complex, Deerfield, New Science Bldg, Davis, Kaneff) | No match | Eliminated UTM (about 8 min) |
| 8 | Commons category API + contact sheet | York (Life Sciences, Sherman, Seneca@York, HNES) | No match | Weakly eliminated York (about 8 min) |
| 9 | Commons | Sheridan Davis aerial + building; Centennial, Humber, Durham | No match | Eliminated these (about 10 min) |
| 10 | Pillow re-crop | Centre and far-right detail | Rb-19 Do Not Enter signs; red vehicle at far end (TTC?) | Re-opened Toronto-proper campuses |
| 11 | Commons category API | UTSC: AA Building, ARC, bus loop, Military Trail, KWE, Science Wing, **2024 aerial** | AA is beige/cream; the aerial shows bungalows abutting campus along Military Trail | **Yes: back to the UTSC main campus (about 500 m)** |
| 12 | Overpass (named buildings) | `way["building"]` in a UTSC bbox | Highland Hall, Student Centre, AA, ARC, Science Research Bldg, etc. with centroids | **Yes: candidates within about 300 m** |
| 13 | Overpass (roads) | `way["highway"]` and crossing nodes | 502 "server at capacity", then OK on retry (kumi mirror failed) | (infrastructure friction) |
| 14 | matplotlib OSM plots (`map1/2.png`) | Roads and footprints in local metres | Military Trail runs NW-SE with houses on its NE side; Scarborough Circle entrance | **Yes: camera SW of Military Trail, looking SE to S** |
| 15 | Commons category API | Student Centre, Highland Hall photos | Student Centre: dark grey panels with horizontal slot windows; Highland Hall: glass boxes | **Yes: building IDs** |
| 16 | WebSearch + WebFetch | Highland Hall exterior; UTSC news "Five things you need to know about UTSC's newest building" | "Five concrete pillars ... large glass feature above the pillars (satellite image of Scarborough) facing west"; bus loop beside it; Perkins+Will | **Confirmed the left building = Highland Hall's west-facing pillared glass box** |
| 17 | curl + Read | UTSC news hero image (DSC_0650) | Highland Hall's east end: glass box with a stacked top box (red frame on that end) | Confirmed the massing |
| 18 | Overpass (local ways and nodes) | One-ways, crossings, stop nodes | Divided entrance: SB lane way 220546499, NB lane "Scarborough Circle" way 43921804; ladder crossings 4462751464 and 10947535234 lying on one 303/123° line, as the two zebras are collinear in the photo | **Yes: to about 20 m** |
| 19 | Overpass (extras; background retry after 4 x 502) | Barriers, grass areas, lamps, signs | Tip island way 1544695662 (about 3.5 x 5 m), median way 1544695666, `barrier=block` nodes near the hub | **Yes: to about 10 m** |
| 20 | Pillow gridded crops | Pixel coordinates of edges, island kerb, zebra ends, lamp base, kerb vanishing lines | Measurements for the fit | - |
| 21 | scipy least squares (`fit.py`) | Azimuths only (4 building edges + 2 vanishing directions + island) | (59.5, 198.4) m local, sigma (1.1, 5.8) m; heading 156 deg; f = 601 px | To about 6 m (along-road axis weak) |
| 22 | scipy least squares (`fit2.py`) | Plus ground-plane points (island tip, zebra/median end, NB crossing node, lamp base); horizon row free; camera height 2.3/2.5/2.8 m | (57.9, 203.8) m, formal sigma 0.3/0.7 m; 1.6 m spread over camera height; heading 156.4 deg; f about 634 px (hFOV about 115 deg) | **Yes: to about 5 m** |
| 23 | WebSearch | Scarborough Circle closure / planters | Nothing relevant | No (dead end) |
| 24 | matplotlib overlay (`overlay.png`) | Camera, view cone, back-projected planters | Left edge of the cone lands on the bungalows across Military Trail, the right edge past AA; planters land on the closed link | Consistency check |

Rough phase timing:

- Clue extraction: about 9 min.
- Hypothesis testing with Commons photos: about 50 min, of which about 35 min were spent on wrong campuses after the UTSC false negative.
- Building-level identification (aerial, OSM names, HH/SC photos, UTSC article): about 20 min.
- Metre-level OSM geometry and fitting: about 25 min, inflated by Overpass 502s.
- Notes: about 15 min.

## Final answer

- **Place:** University of Toronto Scarborough (UTSC), 1265 Military Trail, Scarborough, Toronto. The camera is on the **southbound entrance lane of the divided campus entrance off Military Trail** (OSM way 220546499). It stands about 4 m NNW of where the now planter-closed Scarborough Circle link (way 43921801) crosses that lane, and about 25 m SW of the Military Trail centreline.
- **Camera position (WGS84):** **43.78584, -79.18728**
- **Facing:** about **156 deg (SSE)**, horizontal FOV about 115 deg (rectilinear).
  - Left: Military Trail behind a pine row, with bungalows beyond.
  - Centre-left: Highland Hall's pillared glass box, then the Student Centre's grey slot-window wing.
  - Centre-right: the lamp-post tip island and the divided lanes.
  - Right: the Arts & Administration Building (beige, with penthouse).
- **Uncertainty radius:** **5 m** best estimate (about 1 sigma). I believe the camera is **within 10 m with about 85-90% confidence**.
- **Confidence:**
  - Correct campus and entrance: about 97%.
  - Within 10 m: about 85-90%.
  - Within 5 m: about 60%.

**Evidence that confirms it:**

1. **Highland Hall:** the left building's dark printed-glass box on concrete pillars, with a stacked lighter box on top, matches UTSC's own description: "five concrete pillars ... a large glass feature above the pillars ... satellite image of Scarborough facing west". The UTSC news image of the east end shows the same stacked-box massing.
2. **Student Centre:** the grey wing with horizontal slot windows matches Commons photos of the UTSC Student Centre (e.g. "UTSC Student Centre (Highland Creek).jpg").
3. **Arts & Administration Building:** the beige right-hand building matches the Commons photo "U of T Arts & Administration Building.jpg". With the fitted pose, its NW tip projects to x = 1403 px against 1405 observed.
4. **OSM road layout:**
   - The divided one-way entrance (SB way 220546499 and NB way 43921804) separated by a long median (1544695666) and a small tip island (1544695662) matches the island, lamp post and tree-lined median in the photo.
   - The two OSM ladder crossings (4462751464, 10947535234) lie on one line at 303/123 deg, matching the two collinear zebras.
   - The NB lane flows toward the camera, matching the north-facing "Do Not Enter" signs.
5. **Military Trail:** it runs at bearing 124 deg, and its vanishing direction (fitted 599 px vs about 630 px observed) matches the receding pine-lined road at left. OSM shows houses on its NE side (the bungalows) and tree nodes in the strip (the pine row).
6. **Pose fit residuals:** a joint fit of 4 building azimuths, 2 vanishing directions and 4 ground points gives residuals of at most 14 px for the building edges and at most 38 px for ground points.
7. **Planters:** back-projected, they lie across the closed hub link next to OSM `barrier=block` nodes. OSM tags the blocks on the adjacent service way (27082944) and still marks the link as `access=permissive`, so OSM is slightly out of date or mis-tagged here.

**Honest caveats:**

- The along-lane (north-south) coordinate depends on the ground-plane depth cues: horizon row, camera height, and OSM kerb accuracy. The azimuth-only fit put the camera about 5.6 m further south.
- I could not read the Street View pano metadata (that needs an API key, which was not allowed) and did not open Google Maps, so the position has not been checked against ground truth.
- The watermark year and the banner text remain unread.

## What 10 m would require

- **Already achieved in principle.** The car must be on a single 4-5 m lane (SB entrance lane) between the Military Trail mouth and the tip island, a segment about 25 m long. The island's north kerb is 9-10 m ahead (depth from image rows). Building azimuths fix the lateral position to about 1 m. This is why I put about 85-90% on being within 10 m.
- **To confirm (any one of these):**
  1. **Pano metadata.** Get the Street View pano's own lat/lng, either from the screenshot's Google Maps URL (`@lat,lng,3a,<fov>y,<heading>h,<pitch>t`) or from the Street View metadata endpoint (needs a key). This is exact and also gives true heading and FOV, which removes `f` as a free parameter.
  2. **Human look.** A person opens Street View at 43.78584, -79.18728 and confirms the planters, island and view, without uploading the image anywhere.
  3. **Recent orthophoto.** Check the island, zebra and planter positions against City of Toronto 2023/2024 aerial imagery (open-data WMS) or similar. The depth constraints rely on OSM kerb geometry, whose absolute accuracy here is unknown (typically 1-3 m).
  4. **Camera intrinsics.** A known camera height (Google Gen-3/4 is roughly 2.4-2.6 m) and FOV would tighten depth. The fit spread over 2.3-2.8 m height is only 1.6 m.
- **Below 5 m** would need a measured ground-truth control point (survey or orthophoto) and an exact FOV/heading from the URL.

## Lessons for an automated pipeline

**What the LLM did well (no tools needed):**
- Recognised a Street View screenshot (UI arrow, blurred car). This is a strong prior: the camera is on a drivable lane at about 2.5 m height.
- Read the legible signage, identified Ontario sign types (Rb-19), and spotted the collinear zebras, divided entrance and planter closure.
- Described architecture precisely enough to match reference photos once the right ones were in hand.
- Reasoned about bearings and layout (houses to the left means looking SE with Military Trail on the left).
- Wrote throwaway crop/grid/fit/plot scripts quickly.

**What needed tools:**
- **Enumerating candidates.** Commons category listings and, above all, **Overpass building names in a bbox**. The single biggest jump from "a GTA campus" to "these 6 buildings" came from the Commons UTSC aerial plus Overpass names.
- **Reference photos for visual matching.** Commons thumbnails viewed locally, and an institution's own news page, which supplied the decisive "pillars + glass feature" text.
- **Metre-level precision.** OSM geometry: one-way lanes, crossing nodes, grass islands. Plus a **least-squares pose fit**. OSM geometry gave the biggest precision jump of the run, from about 200 m to about 5 m.

**What would have made it faster:**
- A **pre-built GTA campus index**: for every campus, all OSM-named buildings with footprints, plus 1-3 Commons or official photos per building. My worst error was checking only the famous buildings of the correct campus (UTSC IC/ESCB) and rejecting the campus, which cost about 35 min. An index would have shown Highland Hall and the Student Centre immediately.
- A **local OSM extract or Overpass instance** for the GTA. The public endpoint returned 502 "at capacity" 6+ times, forcing backoff and background retries.
- **Aerial or oblique imagery** (City of Toronto orthophotos, Commons drone shots), which show adjacency cues such as "campus edge with bungalows" at a glance.
- **Toronto 3D massing open data**, for automatic silhouette and azimuth matching instead of hand-picked corners.
- The **original Street View URL**, if the product can capture it, which makes all of this trivial.

**What a fully automated system would likely get wrong:**
- **Premature elimination.** Matching a campus on its 2-3 best-known buildings, then discarding it (exactly my mistake). The pipeline should require eliminating by *all* named buildings within reach, not the famous ones.
- **Over-weighting weak cues.** Banner colour (maroon pointed me at York; it was UTSC), an unreadable watermark year, or hallucinated readings of blurred banner text.
- **Wrong facade or end.** Highland Hall's east end has a red frame and the west end a light one. A system matching the "famous" photo literally could reject the true building.
- **Trusting OSM tags literally.** The closed link is still `access=permissive` in OSM, and the planter blocks are tagged on a neighbouring way. Treat OSM as geometry, not current state.
- **False metre-level confidence.** Depth from image rows is sensitive to horizon row, camera height and terrain slope (the SB-lane vanishing point sat about 20 px above the far building bases, suggesting slope). Report the spread across nuisance parameters, not the formal sigma (which was 0.7 m and is too optimistic).
- **Missing the "on a road" prior.** Without recognising the Street View screenshot, the search space for the camera is much larger. With it, the camera is constrained to a lane polygon, which is what made 10 m achievable.

Sources consulted (text and reference photos only): Wikimedia Commons (UTSC, UTM, York, Humber, Centennial, Durham, Seneca, Sheridan categories and files); utsc.utoronto.ca "Five things you need to know about UTSC's newest building" and its hero image; urbantoronto.ca, constructioncanada.net, architectmagazine.com and canadianarchitect.com search snippets (ESCB, TDHSC, Highland Hall); OpenStreetMap via overpass-api.de.
