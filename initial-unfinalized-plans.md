# CivicLens v2: stepwise plan with feasibility tests first

## Context

CivicLens works in four stages:
1. It sweeps recent **public social media posts**, most of which are not complaints.
2. It detects **civic issues** in their images.
3. It **geolocates** each image inside Toronto with an AI OSINT pipeline we build. The heavy models are skipped when the post already carries a location.
4. It serves **the public, volunteers and City staff**.

The previous version of this plan described the full system. The user asked for three changes:
- split it into steps;
- prove the two riskiest assumptions with real tests **before** building: (1) geolocation works, and (2) scraping produces enough usable posts;
- make sure every step has tests and a clear decision on how to proceed.

**Decisions from the user**
- **Ingestion:** official APIs plus third-party scrapers are allowed, but **no paid scraping yet**. The first scraping test uses free sources only, and Apify waits for a go/no-go after those results.
- **Credentials available:** Mapillary token, Gemini API key, Apify token. There is no Bluesky account, so Bluesky goes through the live stream (Jetstream) only.
- **Geolocation test area:** about 1 km² downtown plus a small patch around the hackathon venue.
- **Geolocator:** a cascade of open-source models plus a fusion and calibration model we train.
- **Users:** public, volunteers and staff.

**Machine (measured):**
- GPU: RTX 4060 Laptop, 8 GB
- CPU: Core Ultra 9 185H (16 cores / 22 threads)
- RAM: 31 GB
- Disk: **~15 GB free (tight)**
- Software: Python 3.14 system install, so the project uses a `uv`-managed **Python 3.12** environment for torch wheel compatibility; `uv` itself still needs installing. Node 24 and git are present.

---

## Step overview

| Step | What | Output | Gate |
|---|---|---|---|
| **0** | Environment and credentials | `.venv` (Py 3.12, CUDA torch), `.env`, data downloads | Smoke script passes |
| **1** | **Scraping feasibility test** (free sources) | `spikes/results/scraping_report.md` | S-tests pass or a pivot is chosen |
| **2** | **Geolocation feasibility test** | `spikes/results/geoloc_report.md` | G-tests pass or a pivot is chosen |
| **3** | **Decision checkpoint** with the user | Plan updated with the chosen path; Apify go/no-go | User approves the direction |
| 4 | DB foundation (Tiger: PostGIS + pgvector + Timescale) | migrations, job queue | Migration and queue tests |
| 5 | Loaders and reference index | Toronto anchors, Mapillary index | Lookup and count tests |
| 6 | Ingestion connectors (platforms picked in Step 3) | `posts` stream | Idempotency, relevance precision |
| 7 | Triage (SigLIP → privacy gate → Gemini) | `analyses` | Detector precision/recall, privacy tests |
| 8 | Geolocation cascade + **trained fusion model** | `geolocations` | Eval harness thresholds |
| 9 | Enrichment (cluster, asset snap, 311, road restrictions, TTC) | `issues` | Fixture tests |
| 10 | Web app: public map, `/verify`, `/triage`, GeoExplainer | deployed UI | Playwright + role/privacy tests |
| 11 | Volunteer loop, retraining, deploy (Vultr + Caddy + domain) | live URL | Live smoke test |
| 12 | Demo and submission | video, Devpost, README sources | Rehearsed twice |

Steps 1 and 2 can overlap: the Bluesky stream listens in the background while the Mapillary harvest and embedding run.

---

## Step 0: Environment

1. Install `uv` (`python -m pip install --user uv`), then `uv python install 3.12` and `uv venv -p 3.12 .venv`.
2. Install dependencies:
   - torch + torchvision (CUDA 12.x wheels)
   - `transformers` (SigLIP 2)
   - `git+https://github.com/cvg/LightGlue`
   - `faiss-cpu`, `lightgbm`, `scikit-learn`, `numpy`, `pandas`, `pillow`
   - `httpx`, `websockets`, `duckdb`, `shapely`, `pyproj`, `h3`, `rapidfuzz`
   - `google-genai`, `pydantic`, `Mastodon.py`, `mercantile`, `mapbox-vector-tile`, `imagehash`, `tqdm`, `python-dotenv`
3. **Disk discipline** (~15 GB free):
   - Point `HF_HOME`, `TORCH_HOME` and `UV_CACHE_DIR` at the project's `.cache/` so they can be deleted later.
   - Keep reference thumbnails only for the test areas (about 1.5–2.5 GB).
   - Embed distractor images and then discard the files, keeping only their vectors.
   - Budget is about 7–9 GB in total.
4. Create `spikes/.env` (gitignored) holding `MAPILLARY_TOKEN`, `GEMINI_API_KEY` and `APIFY_TOKEN` (unused until Step 3). Keys are never printed.
5. Write `spikes/common/smoke.py`, which checks:
   - CUDA is available;
   - MegaLoc and EigenPlaces load through torch.hub;
   - SigLIP 2 loads;
   - ALIKED+LightGlue runs on two images;
   - one Gemini call returns structured JSON;
   - one Mapillary bbox query returns images.

**Done when** `smoke.py` prints all checks green.

---

## Step 1: Scraping feasibility test (free sources only)

The test answers five questions:
1. Can we get enough **recent Toronto image posts** for free?
2. Are the images retrievable?
3. How many posts already carry location info?
4. **What share of posts that weren't complaints actually show a civic issue (the "yield")?** This is the product's riskiest assumption.
5. Do targeted keywords raise that yield?

### Scripts (`spikes/scraping/`)

| Script | Does |
|---|---|
| `gazetteer.py` | Builds the Toronto relevance matcher from Toronto Open Data neighbourhood names (158), TTC GTFS station names, arterial street names (Centreline), and keywords (toronto, ttc, the6ix, #TOpoli…). Generic names such as "Annex" or "Junction" only count when they appear next to another Toronto term. |
| `jetstream_probe.py` | Connects to Bluesky Jetstream (`wantedCollections=app.bsky.feed.post`) for **≥60 minutes**, in the background. It also tests **cursor replay** of the last 24 hours as a free backfill. It logs: total posts, posts with images, Toronto-relevant posts, and Toronto posts with images. It downloads the images (`cdn.bsky.app/img/feed_fullsize/plain/{did}/{cid}@jpeg`) and records whether they fetch and whether they carry EXIF. |
| `bsky_public_probe.py` | Tries `searchPosts` without logging in (expect a 403) and `getAuthorFeed` for known Toronto accounts (@ttcriders etc.), then records what works. |
| `mastodon_probe.py` | Reads the tag timelines #toronto, #ttc, #topoli and #torontolife on mstdn.ca, mastodon.social and socialontario.ca without logging in. Counts posts with media over the last 7 days. |
| `reddit_probe.py` | Makes one request each to `r/toronto/new.json` (expect 403) and **`r/toronto/new/.rss`** (it might still work without logging in), plus r/askTO and r/TTC RSS. Records the status codes and whether image or thumbnail URLs are present. |
| `wikimedia_probe.py` | Commons `geosearch` over both test areas: count, recency and licences. This feeds the geolocation eval set. |
| `issue_yield.py` | Runs every collected Toronto image post (target ≥300, ≤1,000) through **SigLIP 2** zero-shot (public scene vs selfie, food, screenshot or private), then **Gemini Flash-Lite** with the issue schema. Two arms: **passive** (any Toronto post) vs **targeted** (complaint keywords: pothole, flooding, graffiti, "out of service", elevator, 311, broken…). It records per-class counts, cost per image and latency. It writes an HTML contact sheet of the positives for a **human precision check**: I review the first pass, the user spot-checks. |
| `report.py` | Writes `spikes/results/scraping_report.md` |

### Pass criteria

| ID | Test | Pass |
|---|---|---|
| S1 | Bluesky stream volume | ≥20 Toronto-relevant image posts per hour; ≥95% of images fetch |
| S2 | Jetstream cursor replay | 24 h of backfill works (otherwise the live stream only) |
| S3 | Mastodon | ≥50 Toronto image posts in 7 days across instances |
| S4 | Reddit RSS | HTTP 200 with image or thumbnail URLs, giving a free Reddit route (note the ToS caveat) |
| S5 | **Issue yield** | ≥10 human-confirmed issues in ≤1,000 Toronto image posts (either arm), and Gemini precision ≥70% on the positives |
| S6 | Cost and speed | Gemini ≤ $0.005 per image, median latency ≤5 s; SigLIP ≤100 ms per image |
| S7 | Location metadata rate | Share of posts with a usable place in the text or a tag (feeds the cascade's L0/L1 stages) |

**Decisions this step produces:**
- the platform priority list;
- the passive vs targeted mix;
- whether the Apify free-credit micro-test (Instagram location pages, about 100–200 posts) is worth running, which **needs the user's OK**;
- whether the paid plan is needed later.

**If S5 fails**, the pivot is to lead with targeted keyword and location-page queries plus volunteer-submitted links, and to present passive discovery as a bonus.

---

## Step 2: Geolocation feasibility test

The test answers five questions:
1. Does **MegaLoc retrieval + LightGlue verification** place social-style photos within about 25–100 m in Toronto?
2. Do **Gemini clues → Toronto anchors** resolve signage to the right spot?
3. Does using the clue region to **prefilter** retrieval help once the reference database is city-sized?
4. Is a **fusion model** learnable and calibrated?
5. Is it **fast enough** on this laptop?

### Areas and data

| Item | Spec |
|---|---|
| Area A (downtown) | About 1 km² around Queen/King × Spadina/Bathurst. Final bbox chosen after the Mapillary density check. |
| Area B (venue) | About 0.25 km² around the hackathon venue (UTSC, 1265 Military Trail; confirm). |
| Reference DB | Mapillary images in A and B, captured 2019 or later, deduplicated per 5 m × 45° bin. 360° panoramas are cut into 4 perspective crops. Uses `thumb_1024`. |
| **Distractors** | About 10k Mapillary images from 2–3 other Toronto areas, embedded only, to simulate city-scale search. |
| Q1 | 200 held-out Mapillary images from sequences **not** in the reference DB and from a different capture day; ground truth from `computed_geometry` |
| Q1-aug | Q1 with social-media degradations: crop to 50–90%, long side 1080 px, JPEG quality 60–80, colour shifts, and a text or sticker overlay on 10% |
| Q2 | Wikimedia Commons geotagged photos in A and B, excluding ones where the coordinates mark the object rather than the camera |
| Q3 | **Real posts** from Step 1 whose text names a location in A or B. That text is ground truth (about ±100 m), and **the text is hidden from the image models**. Target 20–40 posts. |
| Q4 | Images with readable signage (from Q1, Q2 and Q3, plus about 30 team photos), at least 30 total, for the clue test |
| T | About 30 GPS-tagged **team phone photos around the venue**, which tests the live demo. The team takes these tonight. |

### Scripts (`spikes/geoloc/`)

| Script | Does |
|---|---|
| `mapillary_harvest.py` | Pulls z14 vector tiles and bbox queries smaller than 0.01 square degrees. Reports count, `captured_at` histogram and % panoramas per area, then downloads thumbnails for the reference set and queries. |
| `build_sets.py` | Splits by sequence and date, generates the augmentations, assembles Q1–Q4 and T |
| `embed.py` | Embeds with MegaLoc (fp16, GPU) and EigenPlaces-R50, and **times GPU vs CPU** |
| `retrieve.py` | Full-dimension FAISS vs **PCA-whitened 1024-D** (fitted on the references), with and without distractors and with and without a spatial prefilter |
| `verify.py` | ALIKED+LightGlue on the top-k results; inlier histograms for correct vs wrong matches; picks the threshold; times each pair |
| `clues.py` | Gemini Flash returns `location_clues` JSON. A resolver matches it against **Toronto-wide** anchors (Centreline intersections, Overture places through DuckDB, TTC GTFS stops and route shapes, street-furniture layers), scores H3 res-10 cells and returns the top cells |
| `cascade.py` | L0/L1 (the metadata path is tested on Q3 only, with text shown in this mode) → L2 clues → L3 VPR inside the region (or globally) → L4 verify → heuristic fusion → point, radius or abstain |
| `fusion_probe.py` | LightGBM on per-candidate features with spatial-block cross-validation, then isotonic calibration and a split-conformal radius |
| `report.py` | Writes `spikes/results/geoloc_report.md` with tables, failure examples (images), and recommendations |

### Pass criteria

| ID | Test | Metric | Pass |
|---|---|---|---|
| G0 | Coverage | Mapillary images per area, captured since 2022 | A ≥3k; B ≥300, or plan a team walkthrough |
| G1 | Speed | MegaLoc fp16 images/s on the 4060; CPU images/s | Index of 10k images in ≤15 min on GPU |
| G2 | Retrieval | Recall@1/5 within 25 m and 50 m on Q1, Q1-aug, Q2, Q3; MegaLoc vs EigenPlaces | MegaLoc R@5 (25 m) ≥60% on Q1-aug |
| G3 | Compression | Recall loss from PCA-1024 vs full dimension | ≤3 points, which means pgvector `halfvec(1024)` is viable |
| G4 | City scale | R@1 with distractors, with vs without the L2 prefilter | The prefilter recovers ≥50% of the drop distractors cause |
| G5 | Verification | Precision and recall at the inlier threshold; ms per pair | ≥95% precision with ≥50% of correct matches verified; ≤150 ms per pair on GPU |
| G6 | Clue resolution | % of Q4 within 100 m and 500 m | ≥60% within 100 m |
| G7 | **Cascade** | % within 50, 100, 250 and 1000 m; abstention; seconds per image, on Q1-aug, Q3 and T | Q1-aug ≥40% within 100 m; Q3 ≥25% within 100 m with abstention ≤50%; ≤10 s per image |
| G8 | Fusion | Ranking quality (AUC); conformal radius coverage | AUC ≥0.85; coverage 90% ± 5% |
| G9 | Indoor (optional) | One public building at the venue: a 3-minute walkthrough, then 20 query photos | Venue and zone correct ≥70% |

**Decisions this step produces:**
- the backbone (MegaLoc vs EigenPlaces);
- the vector store (pgvector halfvec vs FAISS);
- the cascade order (clue-first vs VPR-first, based on G6 vs G2);
- the verification k (from G5 timings);
- whether the live venue demo is viable (G0, and G7 on set T);
- whether indoor support is in scope.

**If G7 on real posts is below 20% within 100 m**, reframe the claim as neighbourhood-level (≤1 km) automatic placement, with volunteers making the final pin. The verify UI already supports that.

---

## Step 3: Decision checkpoint

- Present both reports to the user with a **decision table** (option chosen, evidence, runner-up).
- Ask for the **Apify go/no-go**.
- Update this plan: lock the platforms, backbone, vector store, cascade order and claims wording. Delete the branches that weren't chosen.
- Spike code that passed is promoted into `pipeline/` in Steps 5–8. The rest is deleted.

---

## Steps 4–12: build (each ends with its tests)

**4. DB foundation**
- Tiger Cloud with PostGIS, pgvector and TimescaleDB.
- Migrations `001_core.sql`, `002_vectors.sql` and `003_timeseries.sql` create:
  - hypertables: `posts`, `issue_events`, `toronto_311`, `ttc_alerts`;
  - the `reference_images` vectors;
  - a `jobs` queue polled with `FOR UPDATE SKIP LOCKED`.
- *Tests:* fresh-DB migration; extensions present; two workers never claim the same job; a continuous aggregate with `materialized_only=false` shows a newly inserted row.

**5. Loaders and reference index**
- Centreline, Address Points, street furniture (transit shelters, benches, litter bins, poster boards, washrooms), TTC GTFS, wards (25), neighbourhoods (158), 311 yearly ZIPs, and Overture places + buildings (DuckDB, Toronto bbox).
- The Mapillary index for the areas chosen in Step 3.
- *Tests:* row counts (25 wards, 158 neighbourhoods); "Queen St W" + "Spadina Ave" resolves within 20 m of the known intersection; route 504 resolves to the King shape; a known shelter ID round-trips.

**6. Ingestion**
- Connectors for the Step 3 platforms write normalised `posts`.
- Toronto relevance comes from the gazetteer; reposts are deduplicated by perceptual hash; the author ID is stored only as a salted hash; deletion events are honoured.
- *Tests:* a re-run inserts no duplicates; relevance precision ≥80% on 100 hand-checked posts; no username field reaches the DB.

**7. Triage**
- SigLIP filter → **privacy gate** (person as subject, private interior or home, minors → stop) → Gemini schema:
  - scene; privacy flags;
  - issues[]: type, evidence, certainty, severity, box_2d;
  - location_clues; photo age hint; possibly synthetic.
- Then blur with EgoBlur (GPU) or deface, and strip EXIF.
- *Tests:* schema validation; the privacy gate blocks a labelled privacy set; detector precision and recall per class on 100 labelled posts are written to `docs/eval.md`.

**8. Geolocation and the fusion model**
- Promote the spike cascade into `pipeline/geo/`.
- Train LightGBM on Q1-aug + Q2 + Q3 + T, plus volunteer labels later.
- Output: a point, a conformal radius, a probability, the method and a trace, or abstain.
- *Tests:* the eval harness (`worker eval`) shows ≥ the Step 2 numbers (a regression gate); coverage stays 90% ± 5%; abstained items land in the volunteer queue.

**9. Enrichment**
- Cluster by type within max(radius, 30 m) and 14 days, with image similarity.
- Snap to the nearest matching City asset ID.
- Join with 311 (intersection or FSA, and type), live road restrictions, utility-cut and building permits, TTC GTFS-RT `/alerts/accessibility`, and Environment Canada weather.
- Priority score.
- 311 wording: "No matching record in published 311 data…", never "unreported".
- *Tests:* fixture duplicates merge; the asset snap picks the right shelter; the wording test passes.

**10. Web**
- Next.js, MapLibre, shadcn and Auth.js with roles.
- Pages: public map (verified issues precise, unverified issues coarse or hidden), `/issues/[id]`, `/wards/[n]` digest (neutral, grounded in SQL, election-season), `/verify` (issue? pin right? choose a candidate or drag the pin → `volunteer_labels`), `/triage` (priority queue, clusters, context, 311 draft with asset ID, CSV/GeoJSON export), the **GeoExplainer** (clue geometries, candidate pins, matched reference with LightGlue match lines, confidence circle, trace) and the **Signal monitor** (live funnel per platform).
- *Tests:* Playwright smoke at desktop and mobile widths; anonymous `/api/geolocate` and the triage APIs return **403**; API JSON never contains usernames or handles; every displayed image is a blurred derivative.
- > **Status (2026-10-17):** the frontend was built as a dependency-free vanilla JS app (custom map engine on OpenStreetMap tiles, no Next.js/shadcn/MapLibre/Recharts yet) on the `frontEnd` branch. See `README.md` for what exists and `data-contract.md` for the issue shape the API should return. Before starting a separate Next.js app, decide as a team whether to port or keep extending it.

**11. Volunteer loop and deploy**
- Retrain fusion with volunteer labels and report the before/after honestly.
- Deploy on Vultr (Docker Compose: web + workers + Caddy automatic TLS) with a GoDaddy domain. Rent a Vultr GPU only for batch embedding and blurring if the laptop isn't enough.
- *Tests:* live URL smoke test; a teammate photographs something outside the venue, uploads it as a volunteer, and the pin lands inside the stated radius.

**12. Demo and submission**
- Snapshot the demo dataset early, since anti-bot measures can break scrapers.
- Demo script, 2–3 minute video, Devpost, a README with every data-source link and licence, and a methodology page.
- The methodology page covers: the PIPEDA/Clearview caveat, so production would need a privacy impact assessment and platform agreements; Bellingcat ethics practices; and the eval tables.
- Write the DEV article after the event.

---

## Reference: stack picks (from the 2026-10-16 research)

| Area | Choice |
|---|---|
| Retrieval | **MegaLoc** (MIT, torch.hub `gmberton/MegaLoc`); CPU fallback **EigenPlaces-R50** (MIT) |
| Verification | **ALIKED + LightGlue** (BSD-3 / Apache). Avoid SuperPoint, which is non-commercial. GPU upgrade: RoMa (MIT). |
| Vector search | **pgvector `halfvec(1024)`** after PCA-whitening (the HNSW index caps at 4000 dims), else FAISS |
| Pre-filter | **SigLIP 2** base (Apache) |
| Vision LLM | **Gemini Flash / Flash-Lite**: the docs list `gemini-3.8-flash` and `gemini-3.5-flash-lite`; confirm the IDs. About $0.001–0.004 per image. |
| Geocoding | Local only: Centreline, Address Points, GTFS, Overture (DuckDB), OSM extract, `rapidfuzz`, `h3`. No public Nominatim in the main path. |
| Fusion | LightGBM + isotonic calibration + split-conformal radius |
| Privacy | EgoBlur (Apache) / deface (MIT); Presidio (MIT); Pillow re-encode to strip EXIF |
| Connectors | Bluesky Jetstream (`atproto`/websockets), Mastodon.py, Reddit RSS if S4 passes. Gated on Step 3: Apify `apidojo/instagram-scraper` (location URLs, returns lat/lng), `apidojo/tweet-scraper`, `clockworks/tiktok-scraper`. |
| Web | Next.js, Tailwind/shadcn, MapLibre, Recharts, Auth.js |
| DB | Tiger Data (PostGIS + pgvector + TimescaleDB) |
| Hosting | Vultr VM + Caddy, Object Storage, GPU on demand |

**Rejected** (from the open-source model analysis):

| Option | Why |
|---|---|
| Global geolocators (GeoCLIP, StreetCLIP, PLONK, PIGEON, G3, GeoRanker) | Only 10–33% of photos within 1 km, even globally |
| Sample4Geo | No licence file; Toronto orthophotos are academic-use only |
| MASt3R | Non-commercial licence |
| SALAD | GPL, and MegaLoc already includes it |
| MixVPR | No licence |
| AnyLoc | Too heavy |
| Google Street View / Places photos | Their terms ban storing, indexing and ML use |
| Frontier VLMs alone | About 10–17% within 1 km on generic street views, so used for clues only |
| Borrowed idea | GeoRanker/Img2Loc's "retrieve candidates, then a VLM re-ranks" becomes an optional L5 feature |

## Reference: privacy rules (apply from Step 1 on)

1. **Geolocate the issue, never the person.** The privacy gate runs before geolocation.
2. **Public posts only.** No logged-in scraping, no team accounts.
3. **Minimise storage.** Delete originals after inference. Non-issue posts keep only their ID and hash for 7 days. Usernames are never stored or shown.
4. **Spike data stays local and gitignored**, and is deleted after Step 3, apart from the derived metrics.
5. **Indoor geolocation covers allowlisted public venues only**, and outputs the venue and zone, not a point.
6. **No public geolocation endpoint.** Only logged-in volunteers and staff can upload images.

## Reference: additional data

| Purpose | Datasets |
|---|---|
| Anchors | Toronto Centreline; Address Points; street-furniture datasets (shelters, benches, litter bins, poster boards, washrooms, wayfinding); traffic signals; street trees; 3D massing; building outlines; TTC GTFS; Bike Share GBFS; Overture places + buildings; OSM Ontario; Mapillary map features; City `traffic-cameras` (verify the licence) |
| Context | 311 customer-initiated (intersection, FSA, ward, type; updated monthly); road restrictions (live JSON); utility-cut, building and development permits; TTC GTFS-RT accessibility alerts; TTC delay data; Environment Canada weather; ward and neighbourhood profiles |
| Evaluation | Held-out Mapillary sequences; Wikimedia Commons; team GPS photos; real posts with location text; volunteer labels |

**Attribution:**
- OGL-Toronto: "Contains information licensed under the Open Government Licence – Toronto"
- OSM: "© OpenStreetMap contributors"
- Mapillary: CC BY-SA, credited per image
- Overture: CDLA / Apache

## Reference: prize targeting

| Track | Angle |
|---|---|
| **School of Cities** (primary) | Ward digests for the Oct 26 election |
| AI for Social Impact | Direct fit |
| Gemini | Vision, clues, digests |
| Tiger Data | Vectors + PostGIS + hypertables in one database |
| Vultr | Hosting, GPU, object storage |
| GoDaddy | Domain |
| DEV | Article after the event |
| Theme mentions | Climate (flooding, dumping); accessibility (elevator outages, trip hazards) |
| **Skip** | Solana, KAZE, PointClickCare, FDM, FinTech |

## Verification summary

- **Steps 1–2** are verified by their reports (`spikes/results/*.md`) against the S- and G-criteria tables above. Every number comes from a script run; nothing is estimated.
- **Step 3** is verified by the user approving the decision table.
- **Steps 4–12** are verified by each step's listed tests, plus `worker eval` as a regression gate and the live-URL smoke test.
