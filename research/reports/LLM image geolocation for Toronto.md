# Let geometry, not LLMs, place the pin

GeoIssue can reach 10 m only for photos that show enough permanent streetscape to be **geometrically registered against reference images with known positions, or snapped to a surveyed City asset**. No LLM, global geolocator or text geocoder gets there on its own. The finest threshold any LLM or agentic benchmark reports is 500 m. GeoCLIP is trained with 150 m of deliberate GPS noise, and Picarta caps its focused search at a 25 km circle, so these tools can only narrow the search. When registration succeeds, the error budget comes to roughly **3–6 m**, dominated by the 2–3 m error in Mapillary's reference positions; bad cases reach 8–12 m. A reasonable unmeasured estimate is that **30–50% of a realistic mix of civic posts** can honestly be reported within 10 m, and close-ups of bare asphalt almost none. The recommended design gives the LLM three bounded jobs: read the photo and post into a JSON clue schema and route it; pick among at most ten candidates, with "none" allowed; and explain the result. Deterministic tools generate candidates, verify them with local-feature inliers, solve for camera pose, snap to assets, and set a calibrated radius or abstain. The user's instinct that street-view comparison helps is correct. But Google Street View's terms forbid indexing it, creating content from it, or using it to test or validate models, so **Mapillary (CC BY-SA, with structure-from-motion-computed poses) is the only clean automated reference**, and nobody has measured its density in Toronto. Toronto's open data is the under-used asset: **305,237 typed poles digitized at ±30 cm, 5,752 transit shelters, 42,947 hydrants and 17,137 bike rings, all with IDs**. A live blind test placed a sample photo at the University of Toronto Scarborough (UTSC) with a self-estimated 5 m radius in about 1 h 45 min. It got there using Wikimedia Commons, OpenStreetMap (OSM) geometry and a least-squares pose fit, not street-view matching, and the answer has not been checked against ground truth.

## Ten metres is a registration problem that most tools cannot touch

The research points to one structural fact. A 10 m answer has to come from geometry: pose estimation against references whose positions are known, or a match to a surveyed object. Every other tool in the stack works at coarser scales.

**Global geolocators and LLM agents stop at 500 m to 1 km.** GeoCLIP, G3, GeoRanker, Img2Loc, PIGEON and Pinpoint report nothing finer than 1 km ([GeoRanker](https://arxiv.org/html/2505.13731); [Pinpoint](https://arxiv.org/html/2606.04133)). The finest any LLM agent reports is 500 m, where the best open agent, Thinking with Map, scores **14.86%** on hard street imagery ([Thinking with Map](https://arxiv.org/html/2601.05432v1)).

**Visual place recognition (VPR) gets close but returns the wrong point.** On dense vehicle-camera data with references every 9.46 m, 2023-era retrievers put a reference image within 10 m of the query for **85–88%** of queries ([SF-Loc](https://arxiv.org/html/2412.01500)). But a VPR hit gives the *reference camera's* position, not the query camera's and certainly not the pothole's. The main 2025 re-ranking study reports nothing finer than 25 m ([To Match or Not to Match](https://arxiv.org/html/2504.06116)).

**Structure-based localization is sub-metre whenever a query overlaps a good reference model.** About 87–90% of Aachen daytime queries land within 0.25 m, and Cambridge Landmarks has a 15.6 cm median ([cvg/Hierarchical-Localization](https://github.com/cvg/Hierarchical-Localization); [A Guide to Structureless Visual Localization](https://arxiv.org/html/2504.17636v1); [RIC-Loc](https://arxiv.org/html/2607.04722v1)). That is 20–40 times tighter than GeoIssue needs. So the binding limits are elsewhere: how accurately the reference images are georegistered, and the step from camera to object.

| Component | Precision when it works | Reaches ≤10 m alone? | Proper role |
|---|---|---|---|
| LLM/VLM location guess | Finest benchmark threshold is 500 m. GPT-5 scores 0.05% at 500 m on hard Chinese street/POI imagery ([Thinking with Map](https://arxiv.org/html/2601.05432)) | No | Reading clues, routing, explaining |
| Global geolocators (GeoCLIP, Picarta, PIGEON, Pinpoint) | Best global result is about 20–33% within 1 km ([Pinpoint](https://arxiv.org/html/2606.04133)) | No | Optional coarse prior |
| Text → street, neighbourhood or intersection centroid | Hundreds of metres. An intersection and its approaches span 30–100 m | No | Narrowing |
| Text → Address Point (500k+ points, placed inside the correct parcel) | About one lot frontage along the street ([CKAN address points](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=address%20points)) | Only with an asset snap | Strong prior |
| VPR top-1 Mapillary position | Narrows to 20–50 m | No | Supplies reference images for registration |
| Cross-view matching to aerial imagery | Median about 1–2 m on VIGOR panoramas with known heading. Cross-area means of 7.5–9.2 m on KITTI's forward-facing camera ([FG²](https://arxiv.org/html/2503.18725v1)) | No, for handheld photos with unknown heading | Consistency check |
| OrienterNet (image vs OSM raster) | 15.8 / 47.8 / 59.0% within 1 / 3 / 5 m on Mapillary MGL ([OrienterNet paper](https://arxiv.org/html/2304.02009v1)) | Partly; about 40% of single images miss 5 m | Verifier or fallback, given a prior within about 32 m |
| Pose against posed references (HLoc, local triangulation + PnP) | Sub-metre relative to the references | Yes, bounded by reference georegistration | Primary metric step |
| Snap to a City asset inventory | Poles digitized at ±30 cm ([CKAN poles](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=pole)) | Yes, when the matched configuration is unique | Primary absolute anchor |

When registration succeeds, the arithmetic is forgiving. Summing the components in quadrature gives roughly **3–6 m** for a photo matched against Mapillary references with the issue within 20 m of the camera, and **8–12 m** in bad cases. The combination below is the metre-level researcher's calculation from the cited inputs.

| Error component | Typical (m) | Bad case (m) | Basis |
|---|---|---|---|
| Reference georegistration: Mapillary computed poses across several sequences | 2–3 | 5–8 (single sequence, GPS among tall buildings) | Mapillary-derived street lights averaged 2.02–2.21 m error, all under 5 m ([SotM 2022 talk by Meta/Mapillary staff](https://2022.stateofthemap.org/sessions/DKLT7X/)). Mapillary GPS deviated 5.5 m on 12 measured images ([MapAnything](https://arxiv.org/html/2509.14839v3)) |
| Reference georegistration: Google Street View | 1–2 | 3–5 | Intersecting a pair of panoramas gave RMSE of ±0.5 m (X) and ±1.2 m (Y) ([ISPRS 2012](https://isprs-annals.copernicus.org/articles/I-4/305/2012/)). Per-panorama errors ranged 0.37–12.38 m ([Agarwal et al. 2015](https://ar5iv.labs.arxiv.org/html/1503.04287)) |
| Query pose relative to references | 0.1–0.5 | 1–3 (few inliers, distant features) | Aachen and Cambridge results above |
| Unknown focal length (mostly absorbed by PnP with focal refinement) | <0.5 | 1–2 | GeoCalib median vertical-FoV error of 3–5° ([GeoCalib](https://arxiv.org/html/2409.06704v2)) |
| Camera to object: multi-view triangulation or ray-cast, object within 20 m | 0.5–2 | 3–5 | [MapAnything](https://arxiv.org/html/2509.14839v3) |
| Camera to object: monocular depth at 10–20 m | 3.5–5 | 10+ beyond 20 m | UniDepth-B and Metric3D error by distance ([MapAnything](https://arxiv.org/html/2509.14839v3)) |
| **Root-sum-square total (Mapillary references, object within 20 m)** | **≈3–6** | **≈8–12** | Calculation |

**Gross failures, not geometric precision, sink the budget.** The usual causes are no overlap with any reference, textureless close-ups, the wrong coarse region, and objects more than 25 m away. Mapillary's reference positions carry their own tail risk:

- A Mapillary team member calls computed positions predictions that are "sometimes quite accurate, and sometimes not at all" ([Mapillary forum](https://forum.mapillary.com/t/how-does-mapillary-correct-gps-location/7193)).
- Users report estimated positions "way off" on dashcam and time-lapse sequences ([Mapillary forum thread 8311](https://forum.mapillary.com/t/the-estimated-position-is-sometimes-severely-off-causing-wrong-object-placements-on-map/8311)).
- Sequences often drift near tall buildings ([arXiv 1909.05621](https://arxiv.org/pdf/1909.05621)), and input phone GPS in an OpenSfM pipeline is about 5 m off ([LineNet](https://arxiv.org/pdf/1807.05696)).

Images from one sequence share a correlated GPS bias, so averaging them helps less than 1/√N. Prefer references drawn from several aligned components (`merge_cc`).

**Placing the object, not just the camera, is the second sink.** Monocular metric depth on urban imagery has these mean absolute errors for UniDepth-B: about 1.3 m under 5 m, 1.4 m at 5–10 m, 5.0 m at 10–20 m, and 11.0 m beyond 20 m. Geolocating real traffic signs from single images averaged 4.4 m on Cyclomedia imagery and 5.7 m on Mapillary imagery. Pavement damage 2–10 m from the camera was placed within 2.34–2.80 m ([MapAnything](https://arxiv.org/html/2509.14839v3)).

For road-surface issues, intersecting the pixel ray with the ground plane gives a distance error of about (d²/h)·δθ. With a camera 1.5 m high and a 1° pitch error, that is **1.2 m at 10 m, 4.7 m at 20 m and 10.5 m at 30 m** (the researcher's calculation). GeoCalib alone estimates pitch with a median error of 0.87–1.94° ([GeoCalib](https://arxiv.org/html/2409.06704v2)). So ground-plane placement is safe only within about 20 m. Beyond that, GeoIssue must triangulate from several references or snap to a known asset.

**Ground truth is nearly as noisy as the target.** Smartphone GPS on an urban campus had an RMSE of 7.42–12.99 m with a maximum near 100 m ([Merry & Bettinger, PLOS ONE 2019](https://pmc.ncbi.nlm.nih.gov/articles/PMC6638960/)). Open-sky accuracy is about 4.9 m ([Mapscaping](https://mapscaping.com/how-accurate-is-gps/)), and urban multipath degrades it further ([Inside GNSS](https://insidegnss.com/what-are-the-actual-performances-of-gnss-positioning-using-smartphone-technology/)). Social platforms strip GPS and camera metadata from public copies anyway, per vendor and blog testing ([fast.io](https://fast.io/resources/social-media-photo-metadata-platforms-strip/)). Two consequences follow:

- EXIF GPS, when present, is a prior and never the 10 m answer.
- A test set built from phone geotags cannot score a 10 m system. It needs hand-labelled map positions of the photographed object.

Nobody has published a ≤10 m benchmark for social-media or civic-issue photos. The closest real-world evidence is weaker than the vehicle-data numbers:

- MegaLoc's 25 m Recall@1 falls to **52.8%** on night Flickr queries and **51.3%** on occluded ones ([MegaLoc paper](https://arxiv.org/html/2502.17237)).
- Older retrievers found real social-media flood photos only **30–52%** of the time even at 100 m ([VPR-AttLLM](https://arxiv.org/html/2512.11811)).

The researchers' expected shares are below. They are inferences, not measurements.

| Photo type | Expected share within 10 m (inference) |
|---|---|
| Facades, storefronts, intersections or shelters on Mapillary-covered downtown and arterial streets | 60–80% register; about 50–80% within 10 m after verification and pose |
| Residential or tree-heavy streets | 30–50% |
| Night, flood or occluded scenes | 20–45% |
| Close-ups dominated by pavement or water | 0–10%, only from text or post context |
| Indoor TTC elevators | Not registrable against outdoor imagery; station-level (100–200 m) via OCR and GTFS |
| **Realistic civic-post mix** | **30–50%**, with the rest given a wider radius or an abstention |

The verdict: **10 m is a per-photo certificate, not a system-wide promise.** GeoIssue should claim it only when an absolute anchor confirms the location. That means registration to two or more references with consistent poses, or a uniquely matched asset configuration. Every other output gets a calibrated, wider radius.

## Prior art stops at a kilometre, and vendor metre claims remain unverified

### GeoCLIP is a cheap neighbourhood prior, not a locator

GeoCLIP matches an image against a gallery of GPS coordinates rather than images:

- **Image side:** a frozen CLIP ViT-L/14 followed by two trainable linear layers.
- **Location side:** the Equal Earth projection followed by random Fourier features at three scales.
- **Training:** contrastive, on about 4.72M Flickr images, with **σ = 150 m of noise deliberately added** to batch coordinates ([GeoCLIP paper](https://arxiv.org/html/2309.16020)).

It scores **14.11 / 34.47 / 50.65 / 69.67 / 83.82%** at 1 / 25 / 200 / 750 / 2,500 km on Im2GPS3k, and 9.59% at 1 km on YFCC4k ([GeoCLIP paper](https://arxiv.org/html/2309.16020); [G3](https://arxiv.org/html/2405.14702)).

The engineering is friendly:

- The gallery is a non-persistent buffer loaded from a CSV, so it can be replaced with a Toronto grid in one line ([GeoCLIP source](https://raw.githubusercontent.com/VicenteVivan/geo-clip/main/geoclip/model/GeoCLIP.py)).
- The package is MIT-licensed and installs with pip ([GeoCLIP repo](https://github.com/VicenteVivan/geo-clip)).
- It runs in 8 ms per image on an RTX 5090 ([Pinpoint](https://arxiv.org/html/2606.04133)).
- It has no training loop, and issues asking for training code remain open ([GeoCLIP issues](https://github.com/VicenteVivan/geo-clip/issues?q=is%3Aissue)).

Fine-tuning precedents are discouraging. GeoFT cut mean error for Russia and Ukraine only from 3,520 km to 2,150 km ([GeoFT](https://mlanthology.org/iclrw/2025/sun2025iclrw-geoft/)). A Stanford CS231n project fine-tuned StreetCLIP on San Francisco and reportedly reached about 600 m average error; only a search snippet was seen ([GeoVision SF](https://cs231n.stanford.edu/2025/papers/text_file_840560503-CS_231n_Final_Project.pdf)). Unverified snippets put GeoCLIP at 19.8% city-level accuracy on OSV-5M ([semivariogram paper](https://arxiv.org/pdf/2509.21573)) and at 7.7% within 25 km against GPT-4o's 14.7% ([GeoComp](https://arxiv.org/html/2502.13759)).

The draft plan rejected GeoCLIP with a "10–33% within 1 km" figure. Those numbers are right, but the comparison is wrong: a Toronto-only gallery removes all country-scale error. Still, the 150 m training noise makes 10–100 m discrimination implausible. The two researchers who examined it disagree only on priority:

- One sees about an hour of work for a 0.5–2 km heatmap that restricts where VPR searches.
- The other notes that MegaLoc over a Toronto gallery already gives coarse and fine retrieval with no training.

The resolution: GeoCLIP is optional, worth adding only after the core pipeline works, and most useful for textless street photos.

### Picarta: copy the interface, not the headline number

Picarta (Picarta S.r.l., Italy) describes itself as ViT-based and claims **"44.8% accuracy at a 1km distance on the IM2GPS3k dataset"** (vendor claim). The same page admits the comparison "might not be entirely fair since the experimental conditions differ significantly", and claims 70% recall in the top 100 predictions (vendor claim) ([Picarta V2](https://picarta.ai/picarta-v2)). Its homepage calls it "the most accurate and reliable" solution, says it does not rely on EXIF, and recommends reviewing the top predictions (vendor claims) ([Picarta homepage](https://picarta.ai/)).

The 44.8% figure is roughly three times what the published systems Picarta compares itself against achieve on the same benchmark. PIGEOTTO scores 11.3% and GeoCLIP 14.11% ([GeoRanker](https://arxiv.org/html/2505.13731v3)). A search snippet also cited a Picarta changelog stating **30.4%**, which conflicts. Im2GPS3k is made of public Flickr photos, so train/test overlap cannot be ruled out.

The only independent hands-on review found that global searches gave "wildly incorrect results", while country-restricted searches came "fairly close" ([OSINT Newsletter](https://tools.osintnewsletter.com/osint-tools/picarta)). Bellingcat's 2025 trials did not include Picarta ([Bellingcat, June 2025](https://www.bellingcat.com/resources/how-tos/2025/06/06/have-llms-finally-mastered-geolocation/)). The "tested and ranked" comparisons that surface in search come from rival vendors, not neutral testers ([GeoSeer vs Picarta](https://geoseeer.com/blog/geoseer-vs-picarta-ai-photo-geolocation); [GeoAxis](https://geoaxis.ai/best-ai-image-location-finders); [GeoInfer](https://geoinfer.com/en/blog/best-ai-geolocation-tools-2026)).

Picarta is unusable as a component:

- The API is Enterprise-only ([Picarta API](https://picarta.ai/api)).
- Consumer pricing works out to about $0.50–0.80 per search ([Picarta pricing](https://picarta.ai/pricing)).
- The terms forbid automated scraping and say nothing about reusing results ([Picarta T&C](https://picarta.ai/terms-conditions)).

**The lesson worth keeping is its interface contract.** The API takes hard geographic constraints (`COUNTRY_CODE`, `ADMIN1`, a centre plus `RADIUS` up to 25 km) and a 500-character free-text `CONTEXT` hint. It returns up to 10 candidates with scores ([Picarta API](https://picarta.ai/api)). GeoIssue's internal tools should take the same shape, with the Toronto boundary as a far tighter constraint.

### GeoSpy/Raven shows that metre claims rest on dense street-level indexes

**GeoSpy began as a GeoGuessr-style global locator.** It was "trained on millions of images" and used soil, architecture and building spacing. Public access closed after 404 Media reported users asking for help stalking specific women ([404 Media, Jan 2025](https://www.404media.co/the-powerful-ai-tool-that-cops-or-stalkers-can-use-to-geolocate-photos-in-seconds/)). The company then said it located a city or area "relatively precisely" but not the street or house number. The EFF's Cooper Quintin warned against using it "en masse to create a geolocation database" ([heise](https://www.heise.de/en/news/Graylark-closes-public-access-to-AI-tool-for-geolocation-10252293.html)).

**Law-enforcement use has produced no breakthroughs.** The Miami-Dade Sheriff's Office bought licences and 150,000 extra searches. Graylark claims locations "down to the meter" using "high-density geotagged data for specific cities and states" (vendor claim). Yet an internal MDSO email says output "should be treated as a clue", and MDSO called its use "limited and largely exploratory" with no breakthroughs ([GIGAZINE summarizing 404 Media](https://gigazine.net/gsc_news/en/20260213-cops-buying-geospy-ai-geolocates-photos)).

**Today the product is Raven, sold only to government and enterprise.** It turns imagery "into ranked leads for human review" ([Graylark](https://graylark.com/)). It now identifies specific homes from interior photos ([404 Media, Oct 2026](https://www.404media.co/ai-company-lets-cops-pinpoint-specific-houses-based-on-a-single-interior-photo/)). Airbnb disclaims any relationship, and Zillow says scraping violates its terms ([Malwarebytes](https://www.malwarebytes.com/it/blog/privacy/2026/10/raven-ai-lets-cops-find-your-home-from-a-photo-taken-inside)). Sources disagree on when the rename happened ([maxintel](https://maxintel.org/graylark-raven-police-ai-geolocation-2026.html)).

**The SuperBolt street-level feature is described only second-hand.** Third parties say it embeds an upload and compares it against **46M+ street-level images**, with accuracy "as close as 1 meter" (vendor claim via secondary sources) ([Hiverlab](https://hiverlab.com/geospy-ai-top-5-reasons-enterprise-must-try); [Pasquale Pillitteri](https://pasqualepillitteri.it/en/news/423/geospy-ai-photo-geolocation)). "GeoSpy"-named consumer sites are knock-offs unaffiliated with Graylark ([geospys.com](https://geospys.com/blog/chatgpt-geoguessr-prompt)). The founder has framed Bellingcat's results as showing LLMs "probably never will" master geolocation, and he has a commercial interest in that view ([Daniel Heinen on X](https://x.com/heinenbros/status/1931147579540246830)).

The pattern matters for GeoIssue. **Every credible street- or metre-level claim rests on retrieval against dense, geotagged street-level imagery of the target area**, not on a model that "knows" the world. That supports the user's street-view intuition, even though no independent accuracy figure exists for any of these products.

### Open research systems: what transfers and what does not

| System | Key result | Licence / weights | Lesson for GeoIssue |
|---|---|---|---|
| PIGEON / PIGEOTTO | About 92% country accuracy on Street View (95% per PetaPixel); over 40% within 25 km; beat GeoGuessr pro Trevor Rainbolt ([Windows Central](https://windowscentral.com/software-apps/ai-model-can-pinpoint-your-exact-location-from-a-photo); [PetaPixel](https://petapixel.com/2023/12/28/this-ai-can-geolocate-photos-faster-and-more-accurately-than-any-human); [The Decoder](https://the-decoder.com/this-ai-knows-where-you-took-which-photo/)) | No weights; code for "academic validation" ([PIGEON paper](https://arxiv.org/abs/2307.05845); [PIGEON repo](https://github.com/LukasHaas/PIGEON)) | Borrow "classify a cell, then retrieve within it" |
| StreetCLIP | 22.4% within 25 km zero-shot on Im2GPS3k | CC-BY-NC; card discourages geolocating private images ([StreetCLIP](https://huggingface.co/geolocal/StreetCLIP)) | Skip |
| PLONK (CVPR 2025) | OSV-5M city accuracy 15.4%; about 2 ms per sample ([PLONK paper](https://arxiv.org/html/2412.06781)) | MIT, weights on HF ([PLONK repo](https://github.com/nicolas-dufour/plonk)) | Redundant with GeoCLIP for one city |
| OSV-5M baselines | Retrieval baseline 19.9% city accuracy | Code MIT; dataset CC-BY-SA ([OSV-5M repo](https://github.com/gastruc/osv5m)) | Benchmark only |
| G3 | Removing its verification stage drops 1 km accuracy from 16.65% to 14.98% ([G3 paper](https://arxiv.org/html/2405.14702)) | Apache-2.0 ([G3 repo](https://github.com/Applied-Machine-Learning-Lab/G3)) | **Borrow "LLM proposes, deterministic verifier decides"** |
| GeoRanker (NeurIPS 2025) | 18.79% at 1 km on Im2GPS3k, but 288 s per image on an RTX 5090 ([GeoRanker paper](https://arxiv.org/html/2505.13731v3); [Pinpoint](https://arxiv.org/html/2606.04133)) | Apache-2.0 LoRA ([GeoRanker repo](https://github.com/Applied-Machine-Learning-Lab/GeoRanker)) | Too slow, too coarse |
| Img2Loc | Training-free CLIP retrieval plus GPT-4V RAG ([Img2Loc](https://arxiv.org/abs/2403.19584v1)) | No official code ([Papers with Code](https://astro.paperswithcode.com/paper/img2loc-revisiting-image-geolocalization)) | RAG pattern only |
| Pinpoint (2026) | 20.5% at 1 km, 0.098 s per image, no MLLM | No weights ([Pinpoint](https://arxiv.org/html/2606.04133)) | A fast specialist beats a slow LLM re-ranker |
| Thinking with Map | **Map tool lifted Acc@500 m from 1.12% to 16.16%**; zoom and web search each added under 1 point ([Thinking with Map](https://arxiv.org/html/2601.05432)) | 30B MoE; release unstated | Map/POI lookups are the tools that matter |
| GeoPAVE | Support/Refute/Refine evidence gate; +1.95 points at 500 m on Gemini 3 Flash ([GeoPAVE](https://arxiv.org/html/2608.29880)) | Code on GitHub (Arandinglv/GeoPAVE) | Borrow the evidence-gating schema |
| Bellingcat OSM Search | Feature co-occurrence within 100 m; 15 Belgian leads in about 40 s ([Bellingcat how-to](https://bellingcat.com/resources/how-tos/2023/05/08/finding-geolocation-leads-with-bellingcats-openstreetmap-search-tool)) | MIT, self-host on PostgreSQL ([bellingcat/osm-search](https://github.com/bellingcat/osm-search)) | Rebuild locally over City asset layers |
| SPOT, Text-to-OverpassQL | Natural language to OSM configurations ([SPOT](https://arxiv.org/html/2506.13188v1)); LLM-written Overpass queries hallucinate and can fail to execute ([Text-to-OverpassQL](https://arxiv.org/pdf/2308.16060); [TACL](https://transacl.org/index.php/tacl/article/view/5843)) | Open | Validate generated tags against a fixed vocabulary |
| ShadowFinder | Maps where a shadow length is possible at a given time ([Bellingcat](https://www.bellingcat.com/resources/2024/08/22/shadow-geolocate-geolocation-locate-image-tool-open-source-bellingcat-measure); [PyPI](https://pypi.org/project/ShadowFinder)) | Open | Heading check only inside one city |
| Netryx | Street View crawl + CosPlace + ALIKED/LightGlue, claims "sub-50m" (self-reported) ([Netryx mirror](https://claudeskills.info/skills/aradotso/trending-skills/netryx-street-level-geolocation/)) | Unverified | Same architecture, ToS-problematic data |

### LLM benchmarks: the draft's "10–17% within 1 km" figure is mislabelled

The draft's figure matches **retrieval-augmented pipelines on worldwide Flickr images**, not frontier VLMs on street views. On Im2GPS3k at 1 km / 25 km:

- Img2Loc scores 15.34 / 39.83 and G3 16.65 / 40.94 ([GeoRanker](https://arxiv.org/html/2505.13731v3)).
- Untuned Qwen3-VL-8B scores 10.5 / 37.2 ([REVERSE](https://arxiv.org/html/2605.26861)), and Qwen2.5-VL-7B 3.97 / 25.48 ([SpotAgent](https://arxiv.org/html/2602.09463)).

Measured frontier accuracy swings from almost zero to over 60% depending on the images:

- **Social-media-style images, about 85% of which contain text** (the closest match to GeoIssue), within 1 km: GPT-4.1 **61%**, Claude-3.7-Sonnet **60%**, Gemini-1.5-Pro 50%, and the best open model, Qwen-2.5-VL-72B, 36% ([arXiv 2508.19967](https://arxiv.org/html/2508.19967v1)).
- **GeoBench:** Gemini-2.5-Pro gets 64.45% within 3 km with a 0.80 km median ([GeoVista](https://arxiv.org/html/2511.15705v2)).
- **Hard Chinese storefront imagery at 500 m:** GPT-5 gets 0.05% ([Thinking with Map](https://arxiv.org/html/2601.05432)).
- **PAVED at 500 m:** Gemini-3.0-Flash scores 14.92% against GPT-5.5's 5.31% ([GeoPAVE](https://arxiv.org/html/2608.29880)).
- **IMAGEO-Bench street scenes, median error:** Gemini-2.5-Pro 4.2 km, Claude-3.5-Haiku 68.8 km. On private, previously unseen photos Gemini's median drops to 0.7 km ([IMAGEO-Bench](https://arxiv.org/html/2508.01608v1)).
- **US residential Street View:** o3 placed about 60% within 1 mile using best-of-4 prompts ([Doxing via the Lens](https://arxiv.org/html/2504.19373v2)).

Two smaller sources add context. Gemini-2.5-Pro averaged 56.32% on a "Where on Earth?" benchmark, with regional bias up to 42.7% ([arXiv 2510.10880](https://arxiv.org/pdf/2510.10880)). Human pairwise preference also favours Gemini 2.5's geolocation reasoning ([GeoArena](https://arxiv.org/html/2509.04334v3)).

**Gemini is the most consistent fine-scale leader, and Claude is mixed.**

- In a Street View navigation benchmark, Gemini 3.0 Flash reached a **5.0 km median and 50.1% city accuracy**, while Claude Haiku 4.5 sat at **688.3 km and 14.3%** ([GeoAgent](https://arxiv.org/html/2608.29483v1)).
- The hobbyist ccmdi GeoBench, reported through an aggregator, lists Claude Fable 5 first on country accuracy (89.0%), just ahead of Gemini 3.0 Flash (88.0%), with Claude Opus 4.5 at 75.0% ([LLMLearner](https://llmlearner.com/rankings/geobench-acw); [Epoch AI GeoBench](https://epoch.ai/benchmarks/geobench)).
- No independent source gives a sub-1 km number for any Claude 4.x or 5.x model.
- Bellingcat's June 2025 trial found Claude "the most conservative" and lagging. Only o3, o4-mini and o4-mini-high beat Google Lens, and not by much ([Bellingcat, June 2025](https://www.bellingcat.com/resources/how-tos/2025/06/06/have-llms-finally-mastered-geolocation/)).
- In August 2025, Google AI Mode was best overall, and GPT-5 was "a considerable downgrade" from o4-mini-high ([Bellingcat, Aug 2025](https://bellingcat.com/resources/2025/08/14/llms-vs-geolocation-gpt-5-performs-worse-than-other-ai-models/); [GIJN republication](https://gijn.org/stories/updated-test-24-llms-ai-geolocation/)).
- Bellingcat's 2023 test predates all of these models ([Bellingcat 2023](https://bellingcat.com/resources/2023/07/14/can-ai-chatbots-be-used-for-geolocation/)).
- A five-photo informal test ranked Gemini 3 first and saw Claude Sonnet 4.5 miss countries; the sample is too small to rely on ([CyberRaya](https://medium.com/@CyberRaya/geolocation-detection-with-llms-57ff0ee8e133)).
- Against a Master-rank GeoGuessr player, o3 with web search won narrowly on total score but guessed better in only 2 of 5 rounds ([Simon Willison](https://simonwillison.net/2025/Apr/28/o3-geoguessr/)).

Rankings flip between model versions, so a design that hard-codes one LLM as the locator is fragile.

**Tools help only when they are map tools and the model can use them.**

- A map/POI tool produced the biggest gain on record, 1.12% → 16.16% at 500 m ([Thinking with Map](https://arxiv.org/html/2601.05432)).
- Multi-hypothesis generation plus verification added about 4 points at 500 m ([GeoPAVE](https://arxiv.org/html/2608.29880)).
- Geocoding tools doubled 1 km accuracy on Street View text images (9.22% → 19.65%), and 59% of trajectories used only geocoding ([SpotAgent](https://arxiv.org/html/2602.09463)).
- Tool-using VLM agents cut distance error by up to 30.6% ([Jay et al.](https://arxiv.org/abs/2502.14412); [HTML](https://arxiv.org/html/2502.14412v1)), and visual reverse search added 11.1 points at country level ([GEO-Detective](https://arxiv.org/abs/2511.22441)).
- Agentic benchmarks report that combining image inspection with retrieval beats either alone ([GeoVista summary](https://hyper.ai/fr/papers/2511.15705); [GeoBrowse](https://www.alphaxiv.org/abs/2604.04017.md)).

The limits are just as clear. Untuned models can get *worse* with tools ("tool use must be trained to help") ([REVERSE](https://arxiv.org/html/2605.26861)). A 7B geolocator emitted invalid tool calls in 87.1% of turns, and agents rarely recover from a bad first guess ([GeoAgent](https://arxiv.org/html/2608.29483v1)). RL-trained 7B geolocators such as GeoVista ([GitHub](https://github.com/ekonwang/GeoVista)) collapse to **0.33% at 500 m** on fine-grained imagery ([Thinking with Map](https://arxiv.org/html/2601.05432)). They would fit on the 4060 at 4-bit, at roughly 4.5–6 GB ([Spheron](https://www.spheron.network/tools/gpu-recommender/Qwen/Qwen2.5-VL-7B-Instruct-AWQ/); [bestllmfor](https://bestllmfor.com/catalog/qwen25-vl-7b/)), but they are trained to name the city, which GeoIssue already knows. A fine-tuning effort for Russia and Ukraine also frames manual verification as the bottleneck ([GeoFT](https://mlanthology.org/iclrw/2025/sun2025iclrw-geoft)).

**Failure modes argue against letting an LLM verify.** GeoContext tested five VLMs across 109 sites ([GeoContext](https://arxiv.org/abs/2609.05761)) and found two problems:

- **Flat reliance on hints:** models repeat user-supplied location hints regardless of how good the hint is.
- **False confirmation:** asked whether a photo was taken within 150 m of a claimed place, no model reached d′ = 1 against decoys just beyond 150 m, and **83.8% of false acceptances carried confidence ≥0.8**.

Other documented failures:

- A "KICKZ" store sign sent a Melbourne photo to Munich, 16,120 km away ([GeoPAVE](https://arxiv.org/html/2608.29880)).
- Gemini misread a storefront as Thai, and Grok guessed from a photographer's name ([Bellingcat, June 2025](https://www.bellingcat.com/resources/how-tos/2025/06/06/have-llms-finally-mastered-geolocation/)).
- When asked for coordinates, o4-mini failed or refused 61.4% of the time ([arXiv 2508.19967](https://arxiv.org/html/2508.19967v1)).
- Self-reported confidence "alone is not a reliable proxy" across models ([IMAGEO-Bench](https://arxiv.org/html/2508.01608v1)).
- Claude's documentation warns that hallucination risk rises on images under 200 px, and notes that Claude does not read EXIF ([Claude vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)).

### Vendor claims versus independent evidence

| Claim | Source type | Independent check |
|---|---|---|
| Picarta 44.8% at 1 km on IM2GPS3k; 70% top-100 recall | Vendor ([Picarta V2](https://picarta.ai/picarta-v2)) | None. Vendor admits unfair comparison; a changelog snippet says 30.4%. One review: global "wildly incorrect" ([OSINT Newsletter](https://tools.osintnewsletter.com/osint-tools/picarta)) |
| GeoSpy/Raven "down to the meter"; SuperBolt 46M images, "as close as 1 meter" | Vendor, mostly via secondary marketing | MDSO: no breakthroughs, "treat as a clue" ([GIGAZINE](https://gigazine.net/gsc_news/en/20260213-cops-buying-geospy-ai-geolocates-photos)) |
| Google VPS "typically better than 5 meters and often around 1 meter" | Vendor product documentation for live AR sessions ([ARCore](https://developers.google.com/ar/reference/java/com/google/ar/core/Config.GeospatialMode); [ARCore overview](https://developers.google.cn/ar/develop/geospatial)) | Older academic Street View localization: 40% within 1 m with image sequences ([Agarwal et al.](https://arxiv.org/pdf/1503.04287)) |
| Mapillary-derived features under 5 m error | Meta/Mapillary staff talk ([SotM 2022](https://2022.stateofthemap.org/sessions/DKLT7X/)) | 5.5 m mean on 12 images ([MapAnything](https://arxiv.org/html/2509.14839v3)); forum reports of severe outliers |
| Netryx "sub-50m" | Self-reported | None |
| GeoSeer/GeoAxis/GeoInfer "tested and ranked" lists ([GeoSeer vs GeoSpy](https://geoseeer.com/blog/geoseer-vs-geospy-raven-ai-geolocation)) | Competing vendors | None |
| LLM accuracy rankings (Bellingcat, IMAGEO, GeoAgent, PAVED, MAPBench) | Independent journalists and academics | Mutually consistent that Gemini leads fine scales; none tests 10 m |
| VPR and pose-estimation accuracies (MegaLoc, HLoc, SF-Loc) | Peer-reviewed or arXiv benchmarks | Replicable code; none on social-media civic photos |

## Street-view comparison works, but only Mapillary is legally automatable

### Matching against street-level imagery is where metre-level precision comes from

The independent evidence backs the user's suggestion. **MegaLoc retrieval accuracy at 25 m (Recall@1):**

- **95.3%** for hand-picked Flickr photos against a 2.8M-image street-view database ([MegaLoc paper](https://arxiv.org/html/2502.17237)). The SF-XL queries are location-verified Flickr photos with wide viewpoint change ([SF-XL / CosPlace](https://arxiv.org/html/2204.02287); [Barbarani et al.](https://arxiv.org/pdf/2304.05887)).
- **96.5%** for Tokyo 24/7 phone queries against about 76K Street View images ([NPR](https://arxiv.org/pdf/2304.00276); [Deep VG Benchmark](https://arxiv.org/pdf/2204.03444)).

**Pose estimation against posed panoramas yields metres.** Using short image sequences matched to Street View panoramas, Agarwal et al. reached 1 m in 40% of runs and 1.5 m in 60% ([Agarwal et al.](https://ar5iv.labs.arxiv.org/html/1503.04287)). Older Street View retrieval work (Zamir & Shah) returned only the nearest panorama location, not a metric pose ([CRCV GMCP](https://www.crcv.ucf.edu/projects/GMCP_Geolocalization/); [ECCV 2010](https://mlanthology.org/eccv/2010/zamir2010eccv-accurate); [arXiv 1703.07815](https://arxiv.org/pdf/1703.07815)).

**Practitioners use street-level imagery as the confirmation step.** They require at least three independent fixed features to match ([practitioner guide](https://medium.com/@refkialfarizi/a-guide-to-osint-geolocation-87d4438830b3)) and step frame by frame through Mapillary or KartaView "down roads Google never reached" ([Secjuice](https://secjuice.com/how-to-geolocate-a-photo/)). Mapillary is often more recent than Google ([maxintel](https://maxintel.org/geo.html)).

**Three caveats keep this from being a silver bullet:**

- **Database density caps recall.** Recall growth "slows down somewhere between 10 and 25 meters", and on one dataset only 88% of queries even had a reference within 5 m ([Deep VG Benchmark](https://arxiv.org/html/2204.03444)).
- **One-way coverage hurts.** MegaLoc fails when the database covers only one direction of travel, which the paper says is common in Mapillary. Mapillary and Street View GPS labels both contain errors ([MegaLoc paper](https://arxiv.org/html/2502.17237)).
- **Blind re-ranking hurts easy queries.** Re-ranking MegaLoc's top-100 with local features *cut* Pitts30k Recall@1 from 94.1% to 85.2%. On hard night and occlusion sets it helped (52.8% → 56–61%). Inlier counts separated right from wrong matches better than descriptor distance (AUC-PR 76.5 vs 69.8 on night queries) ([To Match or Not to Match](https://arxiv.org/html/2504.06116)).

So LightGlue should **gate and supply correspondences**, not overwrite confident retrievals.

### Google's terms block automated Street View use, even fetch-and-discard

No clause in the current Google Maps Platform terms permits analysing Street View images in your own backend. The Service Specific Terms have no Street View section. Their only Street View mention allows caching `pano_id` ([GMP Service Specific Terms, Oct 15 2026](https://cloud.google.com/maps-platform/terms/maps-service-terms); [archived version](https://cloud.google.com/maps-platform/terms/maps-service-terms/index-20240522)). The general terms apply instead ([GMP ToS, last modified Aug 26 2026](https://cloud.google.com/maps-platform/terms)):

| Clause | Text (quoted) | Effect on GeoIssue |
|---|---|---|
| §3.2.3(a) No Scraping | "will not export, extract, or otherwise scrape Google Maps Content for use outside the Services ... pre-fetch, index, store ... bulk download ... Street View images" | No VPR index or stored thumbnails; on-the-fly matching still extracts pixels for use outside the Services |
| §3.2.3(b) No Caching | "will not cache Google Maps Content except as expressly permitted" | Only `pano_id`s may be kept |
| §3.2.3(c)(v) | Example: "construct an index of tree locations within a city from Street View imagery" | Deriving a location from Street View is structurally the same act |
| §3.2.3(c)(vii) | "use Google Maps Content to improve machine learning and artificial intelligence models, including to train, test, validate or fine-tune" | **No Street View-based test or evaluation set** |
| §3.2.3(e) | "display Street View imagery and non-Google Maps on the same screen" | A moderator view cannot sit beside a Leaflet/MapLibre/OSM map |

The Street View Static API policies prohibit "pre-fetching, indexing, storing, or caching" except place and panorama IDs. They are silent on image analysis ([Street View Static API Policies](https://developers.google.com/maps/documentation/streetview/policies)). Even Google's sanctioned LLM route, Maps Grounding, forbids using grounded output to "train, develop, or improve" ML systems and allows caching only for 30 days for evaluation or display ([GMP Service Specific Terms](https://cloud.google.com/maps-platform/terms/maps-service-terms)).

**Fetch-match-discard is still high legal risk.** It sidesteps the caching clauses, but it still extracts Street View pixels into a non-Google pipeline and produces location data derived from them. The research team's reading, which is not legal advice, is that this **is not defensible without written permission from Google**. A Street View MCP server that saves images to local files makes the conflict explicit ([Glama: Street View MCP](https://glama.ai/mcp/servers/integrations/google-street-view)).

**Price is not the obstacle.** Metadata calls are free and unlimited. Static Street View is 10,000 free per month, then $7 per 1,000. Street View Tiles are 100,000 free per month, then $2 per 1,000 ([GMP pricing](https://developers.google.com/maps/billing-and-pricing/pricing); [Street View metadata](https://developers.google.com/maps/documentation/streetview/metadata)). Ten candidates at 4–6 headings each would cost about $0.28–0.42 per photo beyond the free tier.

**Positions are good but not guaranteed.** Google publishes no panorama accuracy figure, and its metadata page contains an unexplained "accurate to 50 meters" sentence. One 2024 study found "significant deviations in some locations" ([arXiv 2411.08231](https://arxiv.org/pdf/2411.08231)). An AprilTag study found per-panorama errors mostly between 0.4 and 6 m ([arXiv 1503.04287](https://arxiv.org/pdf/1503.04287)). A pano-pair intersection study measured roughly ±0.5–1.2 m horizontally ([ISPRS 2012](https://isprs-annals.copernicus.org/articles/I-4/305/2012/isprsannals-I-4-305-2012.html)).

**The safe uses are narrow:**

- A moderator clicks "open in Google Maps" on a separate screen.
- GeoIssue stores `pano_id`s so that link opens the right panorama.
- Free metadata can show that coverage exists, but kept off the non-Google map.

Google has covered Toronto since 2009 ([TechWyse](https://techwyse.com/blog/online-innovation/toronto-canada-now-appearing-in-google-street-view)) and even campus paths by tricycle ([UTM news](https://www.utm.utoronto.ca/node/2937)). That makes it a superb **human** verifier.

### Alternatives: Mapillary is the only clean automated reference

| Source | Toronto status | Licence and access | Automated use |
|---|---|---|---|
| **Mapillary** | Unmeasured. Coverage is community-driven and "uneven" ([atlas.co](https://atlas.co/data-sources/mapillary)). Montréal uploaded 1M+ 360° images, while a contributor "had no luck" engaging the City of Toronto ([OSM community](https://community.openstreetmap.org/t/high-resolution-360-imagery-in-montreal/120447)) | CC BY-SA 4.0 since 2014 ([Mapillary help](https://help.mapillary.com/hc/en-us/articles/115001770409-CC-BY-SA-license-for-open-data); [Licenses](https://help.mapillary.com/hc/en-us/articles/115001770409-Licenses); [2014 blog](https://blog.mapillary.com/update/2014/03/17/mapillary-goes-creative-commons.html); [Wikipedia](https://en.wikipedia.org/wiki/Mapillary)). A forum thread flags tension between Mapillary's terms and CC ([forum](https://forum.mapillary.com/t/licensing-issues-for-using-mapillary-images-on-wikimedia-commons/3821)). Faces and plates are auto-blurred ([Mapillary](https://www.mapillary.com/)) | **Yes.** Exposes `computed_geometry`, `computed_rotation`, `camera_parameters`, `merge_cc`, `sfm_cluster`. Limits: entity API 60k/min, search 10k/min, tiles 50k/day, bbox under 0.01°, radius search ≤50 m ([API docs](https://www.mapillary.com/developer/api-documentation)) |
| Panoramax | About 31.9k items, mostly one contributor, 2023–24 ([live probe](https://api.panoramax.xyz/api/collections?bbox=-79.64,43.58,-79.11,43.86&limit=100)) | CC-BY-SA-4.0; federated FOSS, about 105M images network-wide ([Wikipedia](https://en.wikipedia.org/wiki/Panoramax); [OSM wiki](https://wiki.openstreetmap.org/wiki/Panoramax)) | Minor supplement |
| KartaView | API returned 408 timeouts on Toronto queries ([live probe](https://api.openstreetcam.org/2.0/photo/?lat=43.6532&lng=-79.3832&radius=300&itemsPerPage=20)) | — | Not worth hackathon time |
| Apple Look Around | Toronto since Dec 2020 ([Apple Newsroom](https://www.apple.com/ca/newsroom/2020/12/apple-delivers-all-new-apple-maps-across-canada/); [Justin O'Beirne](https://justinobeirne.com/look-around-release-11)); backpack rigs in 2021 ([blogTO](https://blogto.com/tech/2021/09/apple-mapping-toronto-huge-backpack-camera-rigs)) | MapKit JS display widget only ([MapKit JS LookAround](https://developer.apple.com/documentation/mapkitjs/lookaround.md)) | No |
| Bing Streetside | Enterprise ends 30 June 2028 ([Microsoft](https://learn.microsoft.com/zh-tw/bingmaps/coverage)); users report it no longer loads ([OSM community](https://community.openstreetmap.org/t/bing-streetside-discontinued/137189)) | — | No |
| City traffic cameras | 336 cameras, each with four directional reference images ([CKAN](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=traffic%20camera); [CSV](https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/a3309088-5fd4-4d34-8297-77c8301840ac/resource/8f9d6db7-faa0-405c-9627-b0298489cf9f/download/traffic-camera-list-4326.csv)) | Open data, licence field blank | Yes, near major intersections |
| City orthophotos | Colour 8 cm, 2015–2022, plus current year, as WMTS/MapServer ([CKAN](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=orthoimagery); [cot_ortho service](https://gis.toronto.ca/arcgis/rest/services/basemap/cot_ortho/MapServer?f=pjson)) | Web service listed OGL-Toronto. Raw high-res TIFFs are restricted to academic use ([U of T MDL](https://mdl-data.library.utoronto.ca/items/show/1140); [U of T 2024 note](https://mdl.library.utoronto.ca/node/55596); [Waterloo](https://uwaterloo.ca/lib-geospatial/collections/aerial-photographs-satellite-and-orthoimagery/image-data-compilation-regional-provincial-national-and/city-toronto-and-greater-toronto-area-gta-orthoimagery/city-toronto-digital-orthoimagery-2020)). Ontario's open imagery may not cover Toronto ([data.ontario.ca](https://data.ontario.ca/en/dataset/open-ontario-imagery)) | Verification and clamping |
| NUS Global Streetscapes | About 10M Mapillary and KartaView images across 688 cities ([NUS](https://ual.sg/project/global-streetscapes)) | Hugging Face | Quick coverage count |

Mapillary's poses make the last mile possible without running full structure-from-motion. The team can import `computed_geometry` and `computed_rotation` as fixed poses, re-extract ALIKED features, and triangulate in hloc. The `sfm_cluster` file is zlib-compressed JSON with no descriptors, so it cannot be used directly for matching, and hand-built URLs fail ([Mapillary forum: optimized together](https://forum.mapillary.com/t/api-identify-images-whose-geometry-was-optimized-together/10070); [forum: mesh format](https://forum.mapillary.com/t/api-mesh-and-point-cloud-format/6664)). Mapillary says positions improve as more overlapping images arrive ([Mapillary help](https://help.mapillary.com/hc/en-us/articles/115001778685)). OrienterNet's MGL dataset was built straight from this API, which sets a precedent ([OrienterNet repo](https://github.com/facebookresearch/OrienterNet)).

If full reconstruction is needed, GLOMAP is "orders of magnitude faster" than COLMAP with equal accuracy ([GLOMAP](https://www.ecva.net/papers/eccv_2024/papers_ECCV/html/5646_ECCV_2024_paper.php)). Measured runtimes: about 102 s vs 346 s per 100 KITTI frames ([CuSfM](https://arxiv.org/pdf/2510.15271)); 580 vs 1,588 minutes on a 29k-image campus ([MGSfM](https://openaccess.thecvf.com/content/ICCV2025/supplemental/Tao_MGSfM_Multi-Camera_Geometry_ICCV_2025_supplemental.pdf)). COLMAP still wins on tiny scenes ([DGSfM](https://arxiv.org/pdf/2607.09507)).

### Toronto's asset inventories are the strongest absolute anchors

At 10 m, the limit is the absolute accuracy of the reference data, and the City publishes better anchors than any crowd-sourced imagery. All load via the CKAN API ([centreline](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=centreline); [topographic mapping](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=topographic%20mapping)) and mostly fall under the Open Government Licence – Toronto ([licence](https://open.toronto.ca/open-data-license/)). The asset CSVs total under about 100 MB and load easily into DuckDB or GeoPandas.

| Dataset | Size and precision | Role at 10 m |
|---|---|---|
| Topographic poles | **305,237** (207,923 street lights; 10,267 traffic signals; 7,094 pedestrian lights), digitized at **±30 cm** with height ([CSV](https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/cdf46145-7a91-4f1c-9dd1-91cd58338238/resource/5ce5f150-f0be-4417-af94-d531594d61f4/download/poles-4326.csv)) | Primary anchor for asset-constellation matching |
| Transit shelters | **5,752**, IDs like `SH-02003`, with fronting street and side ([CKAN street furniture](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=street%20furniture); [all furniture layers](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=street%20furniture&rows=20); [Astral program layer](https://gis.toronto.ca/arcgis/rest/services/cot_geospatial2/MapServer/35/iteminfo?f=pjson)) | Snap a damaged-shelter report to an ID |
| Fire hydrants | **42,947**, IDs like `HY2010909`, with a field-verified flag ([CSV](https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/fbfcf7fa-1026-4b29-bff6-0765ca3f8a54/resource/4575b5ca-59a1-41f5-93b4-e735577fbe53/download/fire-hydrants-data-4326.csv); [CKAN](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=hydrant)) | Constellation member |
| Bike rings | **17,137**, IDs like `BP-11699` ([CSV](https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/71e6c206-96e1-48f1-8f6f-0e804687e3be/resource/f8b62a45-b4ef-4273-ac0a-5d4c95dcf554/download/street-furniture-bicycle-parking-data-4326.csv); [CKAN](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=bicycle%20parking)) | Constellation member |
| Signals, PXOs, red-light cameras | Full inventory ([CKAN](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=traffic%20signals); [CKAN, 10 rows](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=traffic%20signals&rows=10)) | Snap signal-fault reports |
| Edge-of-road, sidewalk and building outlines | Polygons from aerial photography ([CKAN sidewalk](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=sidewalk); [building outlines](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=building%20outlines)) | Clamp a pothole to the roadway, a crack to the sidewalk |
| 2023 LiDAR-derived 2.5 m TIN | Bare-earth elevation, slope, aspect ([CKAN elevation](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=elevation)) | Ground-plane projection |
| Address Points, Intersection File | 500k+ addresses, daily refresh ([CKAN intersection](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=intersection)) | Text-to-coordinate narrowing |
| TTC GTFS, Bike Share GBFS | GTFS updated about every 6 weeks ([CKAN TTC](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=TTC%20routes%20schedules)); **1,072 stations**, often intersection-named ([GBFS live](https://tor.publicbikesystem.net/customer/gbfs/v2/en/station_information); [CKAN](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=bike%20share)) | Station resolver; streetcar corridors |
| 3D massing | "Illustrative purposes only" ([CKAN](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=3D%20massing)) | Skyline reasoning; skip for the hackathon |
| Street trees | **Avoid**: "geographically coded to the parcel address" ([CKAN street tree](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=street%20tree); [tree search](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=tree&rows=10)). Aerial-derived tree points are usable ([CKAN lidar](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=lidar)) | Aerial layer only |
| 311 requests | FSA-level location only ([CKAN](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=graffiti)) | Weak prior |

The research proposes one new deterministic tool, an **asset-constellation matcher**:

- **Input:** the LLM lists visible inventoried objects with types, left-to-right order and rough distances, for example "shelter, left, ~5 m; street-light pole behind; hydrant on right curb".
- **Search:** inside the narrowed region, score candidate camera positions on the sidewalk or roadway by how well predicted bearings match.
- **Output:** with 305k typed poles at ±30 cm plus sparser distinctive assets, short constellations are often unique within 100–200 m. This is the researcher's judgement and untested.

Other tools rank below the City layers for metre-level work:

- **Overture places** add storefront names under CDLA-Permissive, Apache or CC0, by source ([Overture attribution](https://docs.overturemaps.org/attribution/)). The bbox CLI or DuckDB pulls them ([Overture docs](https://docs.overturemaps.org/getting-data); [workshop](https://labs.overturemaps.org/workshop/2-accessing-data.html)). Release paths expire after about 60 days ([GDAL](https://gdal.org/en/stable/tutorials/vector_geoparquet_tut.html)).
- **OSM** should be a local extract, not the public Overpass server, which asks regular users to stay under about 100 queries per day ([OSM wiki](https://wiki.openstreetmap.org/wiki/Overpass_API)).
- **Reverse image search** is mostly for provenance and spotting recycled photos. Cloud Vision Web Detection is the one clean API ($3.50 per 1,000 after 1,000 free) ([Cloud Vision pricing](https://cloud.google.com/vision/pricing)). Bing's search APIs were retired on 11 Aug 2025 ([The Register](https://www.theregister.com/2025/05/15/bing_search_apis_retired/); [dev.to](https://dev.to/tonywangca/best-bing-search-api-alternatives-in-2026-after-the-retirement-kdi)). Lens has only third-party scrapers ([Apify](https://apify.com/s-r/google-lens/pricing)). TinEye sells $0.01–0.04 per search ([TinEye](https://blog.tineye.com/new-image-search-pricing/)). In cities, Lens "tended to fixate on larger, similar-looking structures" ([Bellingcat, June 2025](https://www.bellingcat.com/resources/how-tos/2025/06/06/have-llms-finally-mastered-geolocation/)).
- **Sun and shadow** analysis constrains heading, not position ([Bellingcat 2020](https://www.bellingcat.com/resources/2020/12/03/using-the-sun-and-the-shadows-for-geolocation/); [Bellingcat 2021](https://www.bellingcat.com/resources/2021/05/18/unsure-when-a-video-or-photo-was-taken-how-to-tell-by-measuring-the-length-of-shadows/); [Shadow Finder](https://bellingcat.com/resources/2024/08/22/shadow-geolocate-geolocation-locate-image-tool-open-source-bellingcat-measure)).
- **Commons and Wikidata** help with landmarks ([Wikidata licensing](https://www.wikidata.org/wiki/Wikidata:Licensing)). Many Commons files carry a placeholder city-centroid coordinate, so filter those out ([Commons probe](https://commons.wikimedia.org/w/api.php?action=query&list=geosearch&gscoord=43.6532|-79.3832&gsradius=10000&gslimit=500&gsnamespace=6&format=json)).

## The LLM reads, routes and adjudicates; deterministic tools decide

### Why not a fully agentic loop or a fixed cascade

The evidence rules out both ends:

- **A free-form ReAct agent** costs about 5–10 times more tokens and takes 20–60 s. It can invent coordinates instead of calling tools, and it shows the confirmation bias and invalid-call failures documented in GeoAgent.
- **A fixed linear cascade** wastes compute running VPR on photos it can never solve, such as asphalt close-ups and indoor elevators.

The recommended pattern is a **router plus parallel deterministic tools plus bounded adjudication**. It costs close to a cascade and approaches an agent's accuracy on hard cases. It mirrors the approaches with the best fine-scale evidence: G3's propose-then-verify, GeoPAVE's evidence gate, and Thinking with Map's map tools.

| Stage | Who decides | Tools and data | Output |
|---|---|---|---|
| 0. Ingest | Deterministic | Post text, alt text, hashtags, replies, timestamp. EXIF GPS if present, checked against the Toronto polygon | Hints, treated as priors |
| 1. Clue and route call | **LLM, one call, fixed JSON schema** | Gemini 3 Flash, Claude Haiku/Sonnet 5.5, or local Qwen3.5-9B | OCR strings; named streets, businesses, TTC stations; scene type; visible inventoried assets with left/right order; day/night; issue type; locatability |
| 2. Route | Deterministic rules on the scene type | — | Close-up without text: text-only or abstain. Indoor transit: station resolver. Street scene: all channels |
| 3. Candidate generation | Deterministic, in parallel | `resolve_place` (fuzzy match over Centreline, Intersection File, Address Points, GTFS, GBFS, Overture); `feature_search` (DuckDB-spatial over City assets and OSM); `vpr_search` (MegaLoc top-50 over Mapillary inside the prior); optional GeoCLIP Toronto prior | Candidate clusters at about 30 m |
| 4. Verification | Deterministic | `mapillary_nearby` (≤50 m); ALIKED+LightGlue inliers; heading agreement with `computed_compass_angle`; sun azimuth | Same-place evidence per candidate |
| 5. Adjudication (about 20–40% of photos) | **LLM, bounded**: returns a candidate ID or "none", never coordinates | Query plus ≤10 thumbnails at 512 px plus an evidence table | Choice or abstention |
| 6. Optional agent (about 5–10%) | **LLM, ≤3 tool calls**, then back to the scorer | `feature_search`, `mapillary_nearby`, `ortho_patch`, `reverse_image` | More evidence |
| 7. Metric anchoring | Deterministic | GeoCalib focal and gravity; hloc or local-triangulation PnP against ≥2 Mapillary references in one `merge_cc`; asset-constellation match; ray to the TIN ground plane, clamped to the edge-of-road or sidewalk polygon; snap to an asset ID within about 20 m | **The only stage that can certify ≤10 m** |
| 8. Score, radius, abstain | Deterministic | Logistic regression with isotonic calibration; per-route conformal radius | Coordinate plus radius, or abstention |
| 9. Human review | Moderator | Google Maps link-out on a separate screen; stored `pano_id` | Accept or correct |

**The LLM never moves the pin.** It reads, routes, chooses among candidates that tools produced, and writes the explanation shown to users. That division follows directly from the evidence:

- GeoContext's 83.8% of high-confidence false confirmations at the 150 m scale.
- The KICKZ-style false textual grounding.
- Bellingcat's finding that every model hallucinated at some point.
- The map-tool result: deterministic lookups, not model knowledge, moved Acc@500 m from 1% to 16%.

Every text clue must be confirmed against the Toronto gazetteer before it counts, which also defuses chain-store and look-alike-name errors. Generated OSM tags must be checked against a fixed vocabulary.

### Model choice, cost and the 8 GB budget

**For the clue call, start with Gemini Flash.** The team already has the key, and Gemini 3 Flash leads at 500 m–2 km in independent tests. Gemini 3.6/3.8 Flash costs $0.75/$3.75 per million tokens through December 2026, doubling from January 2027. Gemini 3 Flash Preview costs $0.50/$3.00 ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)). Images default to 1,120 tokens ([Gemini media resolution](https://ai.google.dev/gemini-api/docs/media-resolution)). The Flash free tier is fine for development, but "free-tier content may be used to improve Google's products", which matters for scraped social-media photos.

**For adjudication, Claude is a reasonable choice if available.** Claude's conservatism, the very thing that cost it points in Bellingcat's rubric, may lower the confident-wrong rate that matters most here. That is a hypothesis to measure, not a finding. Prices per million tokens are $0.10/$0.50 for Haiku 5.5, $2/$10 for Sonnet 5.5 and $4/$20 for Opus 5.5 ([Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing)). On Claude 4.7+ models, downscale to ≤1024 px, because a 1080p photo otherwise costs 2,691 image tokens ([Claude vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)).

**Estimated costs per image** (the tools researcher's arithmetic):

- Clue call plus re-ranking on 30% of images: about **$0.0008** on Haiku 5.5, **$0.011** on Gemini 3.6/3.8 Flash and **$0.016** on Sonnet 5.5.
- A six-turn Sonnet ReAct loop: about $0.086.
- End to end, about 3–8 s per photo, 10–20 s with adjudication.

Measured per-request costs in benchmarks agree in order of magnitude. Gemini-2.5-Flash cost $0.0014 per request in IMAGEO-Bench ([IMAGEO-Bench](https://arxiv.org/html/2508.01608v1)). In GeoAgent, one agentic round cost about $0.00079 on Gemini 3.0 Flash and $0.0174 on Claude Haiku 4.5 ([GeoAgent](https://arxiv.org/html/2608.29483v1)).

**Hardware sets hard limits:**

- **What fits.** MegaLoc (about 228M parameters, MIT) and ALIKED+LightGlue fit easily in 8 GB ([MegaLoc repo](https://github.com/gmberton/MegaLoc); [LightGlue](https://github.com/cvg/LightGlue)).
- **What needs time-sharing.** A local Qwen3.5-9B (Apache-2.0, OCRBench 89.2) at 4-bit needs about 5.5–6 GB plus the vision projector, so it must swap the GPU with the vision stack ([Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B)). The smaller Gemma 4 E4B (Apache-2.0, function calling) can sit beside it ([Gemma releases](https://ai.google.dev/gemma/docs/releases?hl=en); [LM Studio](https://lmstudio.ai/models/gemma-4); [Wikipedia](https://en.wikipedia.org/wiki/Gemma_(language_model))). VRAM estimates for Qwen3-VL-8B conflict, at about 6 GB vs 12 GB ([codersera](https://codersera.com/blog/qwen3-vl-4b-vs-qwen3-vl-8b-benchmarks-vram-guide/); [aiindigo](https://aiindigo.com/tool/qwen3-vl-8b-thinking-gguf); [llmrun](https://llmrun.dev/model/qwen-qwen3-vl-8b-instruct)).
- **What won't fit.** OrienterNet evaluation wants 11 GB (halve `num_rotations` to fit 8 GB). The VGGT-based RIC-Loc peaked at 13.1 GB ([RIC-Loc](https://arxiv.org/html/2607.04722v1)).
- **Disk.** MegaLoc's 8,448-D descriptor is about 16.9 KB in fp16, so 100k images take 1.7 GB. 50k thumbnails at 1024 px would take 7–15 GB, which is too tight on 15 GB free. Store descriptors (PCA or PQ to 512–1024 dimensions), re-fetch the top-K thumbnails on demand, and pre-build pose models only for a few demo hotspots at about 0.2 GB per 1,000-image tile.

Licences steer component choice:

- **Use (permissive):** ALIKED (BSD-3), LightGlue (Apache-2.0), DISK (Apache-2.0), LoFTR (Apache-2.0) ([LoFTR](https://github.com/zju3dv/LoFTR)), RoMa (MIT) ([RoMa](https://github.com/Parskatt/RoMa)), hloc (Apache-2.0), GeoCalib (Apache-2.0 code, CC-BY-4.0 weights) ([GeoCalib](https://github.com/cvg/GeoCalib)), and MegaLoc, BoQ and EigenPlaces (all MIT) ([BoQ](https://github.com/amaralibey/Bag-of-Queries); [EigenPlaces](https://github.com/gmberton/EigenPlaces)).
- **Avoid if a commercial future matters:** SuperPoint ([licence](https://github.com/magicleap/SuperPointPretrainedNetwork/blob/master/LICENSE)), MASt3R (CC BY-NC-SA) ([MASt3R](https://github.com/naver/mast3r)), SALAD (GPL-3.0) ([SALAD](https://github.com/serizba/salad)), OrienterNet (CC-BY-NC), UniDepth (CC BY-NC) ([UniDepth](https://github.com/lpiccinelli-eth/UniDepth)), and the Base/Large Depth Anything V2 models (CC-BY-NC) ([Depth Anything V2](https://github.com/DepthAnything/Depth-Anything-V2)).
- **Check terms:** Depth Pro uses Apple's custom licence ([LICENSE](https://raw.githubusercontent.com/apple/ml-depth-pro/main/LICENSE); [repo](https://github.com/apple/ml-depth-pro)).

### Calibration, abstention and guardrails

**Geometric signals predict error far better than model confidence or retrieval scores.**

- In RIC-Loc, consensus and covariance scores detected localization failures with an AUROC of 0.77–0.82. The retrieval-score gap scored 0.53–0.55, near random ([RIC-Loc](https://arxiv.org/html/2607.04722v1)).
- A-contrario validation cut errors above 10 m from 5.61% to 0.68% in cross-view localization ([Slice-Loc](https://arxiv.org/html/2508.05369v1)).
- GeoCalib's uncertainty estimates help flag failures ([GeoCalib ECCV](https://www.ecva.net/papers/eccv_2024/papers_ECCV/html/5636_ECCV_2024_paper.php)).

The suggested starting abstain rules are below. They are heuristics to tune, not published values.

| Signal | Abstain or widen when |
|---|---|
| PnP inliers | Fewer than about 50, or inlier ratio below 0.2 |
| Agreement across references | Camera centres disagree by more than 8 m |
| Plausibility | The pose falls outside the coarse region or off the public right-of-way |
| Object distance | More than 30 m away without multi-view triangulation |

On abstention, report the street segment with a 25–50 m radius.

**Calibrate per route.** Address hits, VPR-verified hits, station hits and adjudicated hits have very different error distributions, so use split (Mondrian) conformal prediction for each route. Use logistic regression with isotonic calibration while labels number in the hundreds. A LightGBM ranker becomes worthwhile around 1,000+ labels.

**Ethical guardrails come from both critics and vendors.**

- Geolocate the civic issue on the public right-of-way, never people or private interiors.
- Do not build per-author location histories, the "en masse database" the EFF warns about.
- Blur faces and plates.
- Present outputs as leads with a radius, as Raven and Picarta both do.

The doxxing coverage of 2025's viral "reverse location search" trend shows how quickly this becomes a story ([TechSpot](https://www.techspot.com/community/topics/chatgpt-gets-scarily-good-at-guessing-photo-locations-sparking-doxxing-concerns.291870/); [TechRadar](https://www.techradar.com/computing/cyber-security/beware-another-chatgpt-trend-threatens-your-privacy-heres-how-to-stay-safe); [Cybernews](https://cybernews.com/cybercrime/chatgpt-turning-casual-snapshots-privacy-nightmares/)).

### What the evidence says about the draft plan's hypotheses

| Draft hypothesis | Verdict | Why |
|---|---|---|
| "Frontier VLMs alone ≈10–17% within 1 km" | **Refuted as framed** | That is the Im2GPS3k RAG-pipeline range. Frontier models score 0–61% depending on image type |
| LLM only as a clue extractor | **Confirmed and extended** | Add routing and bounded adjudication. Never final verifier or coordinate source |
| MegaLoc over Mapillary + ALIKED/LightGlue | **Confirmed for the street-scene branch** | Licence-clean and state of the art. LightGlue should gate, not blindly re-rank. Insufficient for 10 m without a pose and anchoring stage |
| Reject GeoCLIP over "10–33% within 1 km" | **Partly refuted** | Right numbers, wrong comparison. Worth it only as an optional cheap prior |
| Fixed L0–L4 cascade | **Refuted** | Needs scene-type routing. Text/address exits give 10–60 m and become narrowing steps |
| LightGBM fusion | **Premature** | Overfits a few hundred labels. Use logistic/isotonic first |
| Conformal radius | **Confirmed, per route** | A single global radius is too wide for address hits and too narrow for VPR hits |

## A blind test reached about 5 metres through map geometry, not imagery

On 2026-10-17 a researcher geolocated test photo `images/1.png` blind, given only "somewhere in Toronto or the GTA". The image was never uploaded anywhere, and the tools were text search, Wikimedia Commons, UTSC web pages, the public Overpass API and throwaway Python. Working files, including crops, OSM extracts, pose-fit scripts and the overlay, are in the session scratchpad under `geoloc_case/`.

**The answer:**

- **Place:** UTSC, on the southbound lane of the divided campus entrance off Military Trail (OSM way 220546499).
- **Camera:** **43.78584, -79.18728**, facing about 156° (SSE).
- **Precision:** self-estimated 5 m radius, with about 85–90% confidence of being within 10 m and 97% confidence in the campus and entrance.

**This result has not been checked against ground truth**, because the researcher deliberately did not open Google Maps or call the Street View metadata API.

| Phase | Time | What moved the estimate |
|---|---|---|
| Clue extraction | ~9 min | Recognised a **Google Street View screenshot** (navigation arrow, blurred camera car, watermark), which puts the camera on a drivable lane about 2.5 m up. Read "COMMERCIAL DELIVERIES ONLY" and two Ontario Rb-19 "Do Not Enter" signs, collinear zebra crossings, a divided entrance and a planter closure |
| Hypothesis testing with Commons photos | ~50 min, ~35 wasted | Checked only UTSC's two famous new buildings, rejected the campus, then spent 35 min eliminating UTM, York, Sheridan, Humber, Seneca, Centennial and Durham |
| Building identification | ~20 min | A Commons 2024 UTSC aerial (bungalows across Military Trail) plus **Overpass building names in a bbox** narrowed the campus to ~6 buildings within ~300 m. UTSC's own news page described Highland Hall's "five concrete pillars ... large glass feature ... facing west" |
| Metre-level fit | ~25 min (inflated by 6+ Overpass 502 errors) | OSM one-way lanes, crossing nodes and a 3.5 × 5 m tip island, then a least-squares pose fit on 4 building azimuths, 2 vanishing directions and 4 ground points. **~200 m → ~5 m** |

Four lessons carry over to the automated design.

**First, the biggest precision jump came from vector geometry plus a pose fit, not from street-level imagery.** That is the deterministic route OrienterNet automates, and it works where Mapillary is thin. Campuses and residential edges are exactly where crowd-sourced imagery is expected to be sparse.

**Second, the costliest error was premature elimination.** Matching a campus on its two best-known buildings and discarding it cost a third of the run. A pipeline must eliminate a site only after checking *every* named building within reach. A **pre-built GTA landmark and campus index** would have surfaced Highland Hall immediately: OSM-named footprints plus one to three Commons or official photos per building.

**Third, weak cues mislead.** A maroon lamp-post banner pointed toward York. OSM still tagged the planter-closed link `access=permissive`. The formal 0.7 m sigma was far too optimistic next to the 1.6 m spread across plausible camera heights and the 5.6 m shift between fits. **Treat OSM as geometry, not current state, and report the spread across nuisance parameters.**

**Fourth, infrastructure friction is real.** Repeated 502s from the public Overpass server argue for a local GTA extract from day one. The OSM MCP servers wrap the same public endpoints and suit exploration only ([cyanheads/openstreetmap-mcp-server](https://github.com/cyanheads/openstreetmap-mcp-server); [GRABOSM/osm-mcp](https://glama.ai/mcp/servers/GRABOSM/osm-mcp/inspect); [socket.dev](https://socket.dev/npm/package/osm-mcp); [Rusty0508/overpass-mcp](https://glama.ai/mcp/servers/Rusty0508/overpass-mcp); [Pipeworx](https://www.getdrio.com/mcp/io-github-pipeworx-io-overpass)). No Mapillary MCP server exists ([Mapillary platform](https://www.mapillary.com/platform)).

The test photo is unrepresentative in one important way. A Street View screenshot comes with a known camera height, a wide field of view and a "camera is on a road lane" prior, which a phone photo of a pothole lacks. The expert workflow it reproduced is standard practice:

- **Gather context, rank clues, narrow with map queries, verify with several independent fixed features** ([practitioner guide](https://fidelyafr.medium.com/osint-a-practical-guide-to-geolocation-6242c91653c4); [Overpass worked example](https://medium.com/@anugrahendra1/s-53eca46812f6)).
- **Strick's casework** works from structures to searchable signs to satellite confirmation ([Strick thread](https://threadreaderapp.com/thread/1063491316812779521.html); [Poynter](https://poynter.org/?p=490105)).
- **Quiztime's motto** is "Assume Nothing / Believe No One / Challenge Everything" ([GIJN on Quiztime](https://gijn.org/stories/the-daily-quiz-that-teaches-journalists-how-to-geolocate-images/); [Cylab](https://cylab.be/blog/128/osint-quiz); [Quiztime Medium](https://medium.com/quiztime/lots-to-learn-by-solving-and-not-solving-quiztime-riddles-cff4320e8a1c)).
- **GeoConfirmed's volunteers** publish breakdowns but no written method ([beSpacific](https://www.bespacific.com/?p=121997)).

The cheapest validation of the whole case study is allowed under Google's terms: a person opens Google Maps at the fitted coordinate and checks the planters and island by eye.

## Measure Mapillary coverage before writing pipeline code

The decisive unknowns are empirical, cheap to measure, and should be settled before the architecture hardens. The effort column gives rough estimates.

| # | Experiment | How | Decision it drives | Effort |
|---|---|---|---|---|
| 1 | **Toronto Mapillary density** | Pull the ~450 z14 tiles of `mly1_computed_public` over the Toronto bbox (well under the 50k tiles/day limit). Measure (a) the share of Centreline segments by class with ≥1 image within 10 m captured in the last 3 years; (b) the share of shelters, bike rings, hydrants and signal poles with ≥2 images within 20 m pointing toward the asset; (c) pano share; (d) the share of images in large `merge_cc` components. Cross-check with a Global Streetscapes Toronto count | If (b) is below ~50% for target issue types, image registration cannot be the core 10 m step, and asset snapping, traffic cameras and orthos must carry it | 2–4 h |
| 2 | **Mapillary position error in Toronto** | Find Mapillary images of poles, triangulate or read map-feature positions, and compare against the ±30 cm City pole layer | Sets the real reference floor in the error budget | 3–4 h |
| 3 | **Hand-labelled test set** | 100–300 items: team-shot photos and real public posts collected for the project, with the *object* hand-placed on the 8 cm ortho. Add Mapillary pseudo-queries (pedestrian captures, randomly cropped, intrinsics stripped) held out from the index. No Street View | Every threshold, model choice and radius depends on it | 4–6 h |
| 4 | **What share of civic posts are locatable** | On the corpus, tag: has street or business text; shows permanent streetscape; close-up only; indoor | Sizes each route; tells the team whether text or VPR is the primary path | 1–2 h |
| 5 | **LLM clue-call bake-off** | Same JSON schema on Gemini 3 Flash, Claude Haiku/Sonnet 5.5 and local Qwen3.5-9B. Score OCR recall, entity accuracy after gazetteer resolution, and **confident-wrong rate**. Add GeoContext-style near-miss decoys (true place vs 150–300 m away) to measure false confirmation | Picks the model; proves whether Claude's caution pays off | 3 h |
| 6 | **Retrieval and verification spike** | MegaLoc over 1–2 dense tiles using `VPR-methods-evaluation` with UTM-named files ([repo](https://github.com/gmberton/VPR-methods-evaluation)). Recall@1/@10 at 10 and 25 m; ALIKED+LightGlue inlier histograms for right vs wrong; 4060 latency and VRAM | Sets the inlier gate; confirms the latency budget | 4 h |
| 7 | **Last-mile pose spike** | One hotspot tile: import Mapillary computed poses, triangulate ALIKED points in hloc, localize test photos with GeoCalib + PnP, place the object by ground-plane ray. Compare with hand labels | First real ≤10 m success rate | 6–8 h |
| 8 | **Asset-constellation uniqueness** | For random 100–200 m regions, count how many camera positions match 2–4-asset constellations (pole subtype, shelter, hydrant) with bearing order | Validates the new anchor tool before building the matcher | 2–3 h |
| 9 | **Local data stack** | GTA OSM extract, City asset CSVs, Address Points, GTFS and GBFS into DuckDB-spatial; build `resolve_place` and a campus/landmark index (OSM-named buildings plus Commons photos) | Removes the Overpass bottleneck seen in the case study | 3–4 h |
| 10 | **Case-study ground truth and re-run** | A human checks the fitted coordinate in Google Maps (link-out only), then re-runs the photo through the pipeline | First end-to-end regression test | 1 h |

Two cheap additions are worth slotting in early:

- Check whether Toronto shelters, hydrants or poles carry visible ID plates. That would enable OCR → asset ID → exact surveyed point.
- Check whether TTC GTFS `stop_code` values match the numbers printed on stop poles.

## Open questions that could still change the design

| Open question | Why it matters | Current state |
|---|---|---|
| How dense, recent and two-directional is Mapillary in Toronto, especially residential streets, laneways and campuses? | Decides whether imagery or assets carry the 10 m claim | No primary statistic; Experiment 1 |
| How large is `computed_geometry` error in Toronto's downtown canyons? | Sets the error-budget floor | Only a 2022 Turkish street-light study and a 12-image sample |
| What share of real civic posts are locatable at all? | The 30–50% figure is an inference | No study anywhere; Experiment 4 |
| Can a zero-shot LLM re-ranker beat LightGlue inliers for same-place decisions? | Decides how much adjudication to buy | GeoRanker needed training. A Qwen2.5-VL re-ranker reached 91.1% on Tokyo 24/7 at 46.69 s per query, still below MegaLoc alone ([Scale, Don't Fine-tune](https://arxiv.org/html/2509.02129)). Describe-then-compare took 773–2,576 s ([LLM4VPR](https://github.com/ai4ce/LLM4VPR)) |
| Is single-photo pose against crowd-sourced references robust to noisy reference poses? | The structureless guide explicitly did not test noisy poses | No study; Experiment 7 |
| How do Claude 4.x/5.x models perform below 1 km? | Model choice | No independent number exists |
| Would Google grant written permission for transient Street View matching? What does "accurate to 50 meters" mean? | Could unlock a denser reference | Unanswered |
| Licence edge cases: blank CKAN licence fields; OGL-Toronto attribution wording; Mapillary terms on storing descriptors; conflicting GTA 2023 LiDAR records ([IRIU mirror](https://dev.donnees.iriu.ca/dataset/7c3d7022-2631-45bc-8f6b-f3d51b7779a7/resource/3df5be0b-afa6-46de-a8f2-d65d9a3b41e0) vs [Waterloo](https://uwaterloo.ca/lib-geospatial/collections/canadian-geospatial-data-resources/ontario/lidar-cloud-point-and-raster-elevation-data); [Ontario point cloud](https://data.ontario.ca/dataset/ontario-classified-point-cloud-lidar-derived)) | Matters only if GeoIssue outlives the hackathon | Unresolved |
| Canadian privacy law (PIPEDA) on geolocating public posts | Product risk | Not researched |
| Picarta's 44.8% vs 30.4% discrepancy; GeoContext per-model results | Prior-art accuracy | Unresolved |

## Conclusion

The question changes once the target is 10 m. Model choice stops being the central question, because no model is a locator at that scale. The real question becomes **which absolute anchor each photo can reach**: two consistent posed references, a unique constellation of surveyed City assets, or neither. That reframing makes Toronto's open inventories a competitive advantage that global products lack. A ±30 cm pole layer with 305,237 typed entries is a ground-truth grid no global geolocator has. It also means the team's first deliverable should be a coverage map and a labelled test set, not a model.

The case study adds a second, less obvious insight. **Vector map geometry fitted with simple projective constraints carried a photo from 200 m to about 5 m without any street-level imagery.** If Mapillary proves thin where civic complaints cluster, automating that OSM-and-asset fitting may matter more than any retrieval model. The LLM's real contribution is breadth: reading signs, describing assets in order, choosing among candidates and explaining. Its real danger is false confirmation. A design in which the LLM can never move the pin keeps the first and contains the second.

## Source index

These links from the research notes support background points summarised above. They are listed here so that every source remains reachable.

**Retrieval, matching and pose:** [Deep VG Benchmark (PDF)](https://arxiv.org/pdf/2204.03444); [MixVPR](https://github.com/amaralibey/MixVPR); [AnyLoc](https://github.com/AnyLoc/AnyLoc); [RoMa paper](https://arxiv.org/html/2305.15404); [RoMa CVPR 2024 supplemental](https://openaccess.thecvf.com/content/CVPR2024/supplemental/Edstedt_RoMa_Robust_Dense_CVPR_2024_supplemental.pdf); [RoMa v2](https://arxiv.org/pdf/2511.15706); [LightGlue ICCV 2023 supplemental](https://openaccess.thecvf.com/content/ICCV2023/supplemental/Lindenberger_LightGlue_Local_Feature_ICCV_2023_supplemental.pdf); [Residual descriptors (threshold convention)](https://arxiv.org/pdf/2312.15471); [RIPE](https://arxiv.org/pdf/2507.04839); [VGGT](https://github.com/facebookresearch/vggt); [MASt3R paper](https://arxiv.org/pdf/2406.09756); [NAVER Labs MASt3R blog](https://europe.naverlabs.com/blog/mast3r-matching-and-stereo-3d-reconstruction/); [Niantic map-free leaderboard](https://nianticspatial.com/research/map-free/leaderboard); [LoD-Loc v2](https://arxiv.org/pdf/2507.00659); [egenioussBench](https://isprs-archives.copernicus.org/articles/XLVIII-1-W6-2025/75/2025/); [RAG with open VLMs](https://arxiv.org/html/2509.01341); [Img2Loc abstract](https://arxiv.org/abs/2403.19584); [GeoRanker abstract](https://arxiv.org/abs/2505.13731v3); [GeoRanker NeurIPS](https://proceedings.neurips.cc/paper_files/paper/2025/hash/19b30d80dbb996efe36fd51a702800b7-Abstract-Conference.html); [Thinking with Map (alt)](https://arxiv.org/html/2601.05432v1); [GeoAgent abstract](https://arxiv.org/abs/2608.29483); [GeoFT (alt URL)](https://mlanthology.org/iclrw/2025/sun2025iclrw-geoft); [Bellingcat OSM Search (www)](https://www.bellingcat.com/resources/how-tos/2023/05/08/finding-geolocation-leads-with-bellingcats-openstreetmap-search-tool/).

**GPS and positional accuracy:** [J. Navigation 2011](https://www.cambridge.org/core/product/E1EE20CD1A301C537BEE8EC66766B0A9); [DXOMARK](https://www.dxomark.com/gps-on-your-smartphone-why-youre-not-always-there-when-it-says-youre-there/); [Sensors and Materials](https://sensors.myu-group.co.jp/sm_pdf/SM2778.pdf); [Unirioja CIG](https://publicaciones.unirioja.es/ojs/index.php/cig/article/view/6565); [Mapillary forum: SfM lat/lon](https://forum.mapillary.com/t/sfm-lat-lon-not-in-api-lat-lon-question/2881).

**OCR tooling (for the clue call or a local fallback):** [PaddleOCR model list](https://www.paddleocr.ai/v3.3.2/version3.x/model_list.html); [InfoQ on PP-OCRv5](https://www.infoq.com/news/2025/09/baidu-pp-ocrv5); [Roboflow OCR models](https://blog.roboflow.com/best-open-source-ocr-models/).
