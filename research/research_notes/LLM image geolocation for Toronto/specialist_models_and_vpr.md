# Specialist (non-LLM) image geolocation models and visual place recognition (VPR): what reaches street scale, and what can feed a ≤10 m Toronto system

Research date: 2026-10-17.

**Scope.** This note covers:
- GeoCLIP and other global geolocators
- City-scale VPR
- Local-feature re-ranking and verification
- Cell-based methods
- Accuracy ceilings
- Retrieval+LLM hybrids from 2025–2026

**Two course corrections apply.**
1. The draft plan is treated as an unverified hypothesis, not a baseline to defend. That covers MegaLoc + ALIKED/LightGlue, the list of rejected models, and the "10–33% within 1 km" figure.
2. The target is now **≤10 m**, not 25–100 m. Every section below says plainly whether the approach can reach ≤10 m. Full 6-DoF pose estimation (HLoc, PnP, SfM, cross-view metric localization, object-offset estimation) is covered by another researcher. This note only marks where retrieval and verification hand off to it.

**Metric framing used throughout.**
- **Global geolocators** report the share of predictions within 1 / 25 / 200 / 750 / 2500 km over the whole planet. No method reviewed here reports anything finer than 500 m.
- **VPR** reports Recall@N at 25 m: the share of queries where a database image within 25 m of the query's true position appears in the top N. Almost nobody reports VPR at 5 or 10 m.
- **A "correct" VPR hit is only coarse.** It means a reference camera within 25 m of the query camera. It does not give the query camera's position, and it says nothing about where the photographed pothole or flood is.
- **City-level (25 km) accuracy is meaningless for a Toronto-only system**, because the whole city fits inside that radius.

---

## Q0. Can any specialist approach plausibly reach ≤10 m, and where does retrieval/verification hand off to pose estimation?

### Takeaway
No global geolocator can reach ≤10 m:
- GeoCLIP was trained with 150 m GPS noise.
- The finest threshold any global method reports is 1 km, or 500 m for the agentic Thinking with Map.

VPR retrieval is the only specialist family that gets close.
- In the one source found that reports recall at 10 m, 2023-era retrievers found a reference image within 10 m for **about 85–88%** of queries, and within 20 m for about 95–97%. That data is dense vehicle-camera sequences, not social-media photos.
- MegaLoc has not been measured at 10 m.

Even a correct top-1 match gives a reference camera position, so the error budget stacks:
- query-to-reference distance (benchmarks count anything up to 25 m as correct),
- plus Mapillary position error (about 2–5 m in one study; urban-canyon drift is worse),
- plus the camera-to-object offset.

Reliable ≤10 m therefore needs geometric pose estimation from verified correspondences, which is the other researcher's area. Retrieval and verification are the front end that makes that step possible:
- **retrieve:** shortlist candidates,
- **verify:** confirm the place and supply correspondences,
- **hand off:** estimate pose from the verified matches, then estimate the object offset.

Ground truth is a further limit. Phone GPS is typically around 5 m under open sky and worse downtown, so ≤10 m sits close to the noise floor of any Toronto evaluation set built from phone geotags.

### Cited Findings
**Global models**
- GeoCLIP training adds Gaussian noise of σ = 150 m to batch GPS coordinates and 1000 m to queue coordinates. — [GeoCLIP paper](https://arxiv.org/html/2309.16020)
- The finest reported threshold for GeoCLIP, G3, GeoRanker, Img2Loc, PIGEON and Pinpoint is 1 km. — [GeoRanker](https://arxiv.org/html/2505.13731); [Pinpoint](https://arxiv.org/html/2606.04133)
- Thinking with Map reports 500 m as its finest: 14.86% on MAPBench-hard, 57.94% on GeoBench. — [Thinking with Map](https://arxiv.org/html/2601.05432v1)

**VPR recall at 10 m and 20 m (SF-Loc, Wuhan vehicle-camera data)**
- Setup: database frames about 9.46 m apart on average; DGNSS/INS ground truth.

| Method | Recall @10 m | Recall @20 m |
|---|---|---|
| NetVLAD | 59.53 | 67.46 |
| AnyLoc | 80.39 | 89.73 |
| CosPlace-R18 | 84.41 | 95.38 |
| CosPlace-R50 | 85.71 | 95.55 |
| MixVPR | 86.75 | 95.60 |
| EigenPlaces-R50 | 87.62 | 97.12 |
| EigenPlaces-R50, 10-frame multi-frame | 96.80 | 100.00 |

- The authors say coarse recall within about 20 m is needed before fine localization is possible.
- Their sequential factor-graph fine stage then reaches 0.209 m RMSE (98.53% within 0.5 m). That needs a video sequence, not one photo. — [SF-Loc](https://arxiv.org/html/2412.01500)

**Recall versus distance threshold (Deep Visual Geo-localization Benchmark, CVPR 2022, models trained on Pitts30k)**
- Recall@1 rises fast with threshold, and growth "slows down somewhere between 10 and 25 meters".
- Recall@1 does not reach 90% on any dataset even at 50 m (2022 models).
- Database density caps what is achievable: on St Lucia, only 88% of queries even have a database image within 5 m.
- Training positives are images within 10 m; negatives are beyond 25 m.
- Of correct predictions on R-SF, 90% are within 45° of the query heading, 57% within 30°, and about 14% within 10°. — [Deep Visual Geo-localization Benchmark](https://arxiv.org/html/2204.03444)

**No re-ranking results below 25 m**
- The main 2025 re-ranking study reports only 25 m and 100 m thresholds, with no 5, 10 or 15 m results.
- It warns that "GPS labels, even when post-processed (e.g. Mapillary famously post-processes images' GPS with SfM), can be wrong." It gives an MSLS pair whose GPS labels are more than 50 m apart, though the photos were likely taken much closer. — [To Match or Not to Match](https://arxiv.org/html/2504.06116)

**Mapillary position accuracy**
- A State of the Map 2022 talk by Meta/Mapillary staff measured 2.02 m positional error for GoPro MAX and 2.21 m for iPhone 11, for extracted map features (street lights). It concluded overall accuracy is under 5 m and attributed most error to device GPS, partly corrected by 3D reconstruction. — [SotM 2022 talk](https://2022.stateofthemap.org/sessions/DKLT7X/)
- A Mapillary team member says "computed" positions are predictions that are "sometimes quite accurate, and sometimes not at all". — [Mapillary forum](https://forum.mapillary.com/t/how-does-mapillary-correct-gps-location/7193)
- Mapillary sequences often show GPS drift caused by tall buildings or tree canopy. — [Automated Detecting and Placing Road Objects](https://arxiv.org/pdf/1909.05621)

**Phone GPS accuracy (for ground-truthing a Toronto evaluation set)**
- Smartphones are reportedly accurate to about 4.9 m under open sky, degrading near structures and trees.
- This comes via a secondary source; the gps.gov primary page returned 404 when fetched. — [Mapscaping](https://mapscaping.com/how-accurate-is-gps/)
- Multipath in urban canyons adds timing errors. — [Inside GNSS](https://insidegnss.com/what-are-the-actual-performances-of-gnss-positioning-using-smartphone-technology/)

**Metric localization after retrieval (LaMAR, with a 3D map)**
- MegaLoc retrieval followed by local-feature pose estimation reaches these recalls at (5°, 1 m): 60.4% (CAB phone), 92.9% (HGE phone), 94.9% (LIN phone). This is the kind of hand-off pipeline that gets well below 10 m. — [MegaLoc paper](https://arxiv.org/html/2502.17237)

### Inferences
**Error budget for "retrieval only"**
- Predicted point = top-1 Mapillary camera position. Its error is roughly the query-to-reference camera offset plus the reference's GPS error (about 2–5 m, worse downtown).
- Toronto arterial rights-of-way are tens of metres wide. A sidewalk photo matched to a Mapillary car-lane capture can be 5–15 m off laterally even when the match is perfect (not measured).
- So retrieval alone gets **some** locatable photos within 10 m. Expect well below the 85–88% SF-Loc figure for casual social-media photos with large viewpoint shifts.
- It cannot guarantee ≤10 m, and it cannot place the object.

**Plausible ≤10 m pipeline, all specialist pieces**
1. Retrieve (MegaLoc) within an LLM- or GeoCLIP-narrowed area.
2. Verify the top-k with LightGlue or LoFTR inliers.
3. Hand off: relative pose from correspondences to two or more verified Mapillary frames with known poses (triangulation, PnP against Mapillary SfM points), then object-offset estimation.
4. Abstain when inliers are low.

**Hard dependencies**
- Database spacing of ≤5–10 m along each street, ideally both travel directions or 360° imagery. SF-Loc's 9.46 m spacing produced 85–88% recall at 10 m.
- Accurate reference poses: Mapillary computed geometry, not raw GPS.

**Evaluation**
- Ground truth from phone geotags (about 5 m open sky, worse among towers) is too noisy to score ≤10 m reliably.
- Hand-label ground truth on a map for the test set.

### Gaps
- No published VPR results at 5 or 10 m for MegaLoc, BoQ or SALAD, or on social-media queries.
- SF-Loc's 5 m and 1 m recall numbers exist but were not extracted.
- No published measurement of Mapillary computed-geometry camera-position error in Toronto or any comparable city. The 2–5 m figure covers extracted map features in one study.
- No study measures the camera-to-subject distance in social-media civic-issue photos.

---

## Q1. GeoCLIP: how it works, reported accuracy, custom-gallery and fine-tuning potential, licence, size, speed

### Takeaway
GeoCLIP matches an image against a gallery of GPS points, not images. The gallery can be swapped in one line, so restricting it to Toronto costs almost nothing. It runs in about 8 ms per image and is MIT-licensed.

**It cannot plausibly reach ≤10 m.**
- Published accuracy is 14.11% within 1 km on Im2GPS3k and 9.59% on YFCC4k.
- Training deliberately blurs GPS by 150 m.
- No within-city resolution test exists, and the repo has no training loop.

On merit it is a cheap, complementary coarse prior: a neighbourhood-level heatmap that narrows the VPR search, especially for photos with little streetscape. It is not a locator at the new target.

### Cited Findings
**Architecture**
- Image side: frozen CLIP ViT-L/14, then two trainable linear layers (768 → 512).
- Location side: GPS goes through the Equal Earth Projection, then Random Fourier Features at 3 levels (σ from 2⁰ to 2⁸). Each level has an MLP (four 1024-unit ReLU layers, 512-dim output), and the outputs are summed. — [GeoCLIP paper](https://arxiv.org/html/2309.16020)

**Training**
- Contrastive image–GPS training on MP-16 (about 4.72M Flickr images).
- A dynamic queue of 4096 GPS negatives.
- GPS noise of σ = 150 m on batch coordinates and 1000 m on the queue.
- Adam, learning rate 3e-5, batch 512, converging around epoch 10. — [GeoCLIP paper](https://arxiv.org/html/2309.16020)

**Inference**
- Ten-crop averaging against a gallery of training-set coordinates: 100K points for Im2GPS3k and YFCC26k, 500K for GWS15k.
- Going from 21K to 100K points improved fine-scale accuracy; 500K and 1M points gave slight drops. — [GeoCLIP paper](https://arxiv.org/html/2309.16020)

**Accuracy at 1 / 25 / 200 / 750 / 2500 km**
- Im2GPS3k: **14.11 / 34.47 / 50.65 / 69.67 / 83.82**. GeoDecoder gets 12.8 / 33.5 / 45.9 / 61.0 / 76.1. — [GeoCLIP paper](https://arxiv.org/html/2309.16020)
- YFCC26k: **11.61 / 22.19 / 36.69 / 57.47 / 76.02**. — [GeoCLIP paper](https://arxiv.org/html/2309.16020)
- YFCC4k: **9.59 / 19.31 / 32.63 / 55.0 / 74.69**. — [GeoRanker](https://arxiv.org/html/2505.13731); [G3](https://arxiv.org/html/2405.14702)

**Low-data robustness (Im2GPS3k, 1 km / 25 km)**
- 100% of training data: 14.1 / 34.5
- 20%: 13.1 / 32.6
- 10%: 12.1 / 31.9
- 5%: 10.8 / 31.1
- ISNs at 5%: 3.2 / 9.6 — [GeoCLIP paper](https://arxiv.org/html/2309.16020)

**Gallery is replaceable**
- `gps_gallery` loads from `gps_gallery/coordinates_100K.csv` into a non-persistent buffer, so you can assign a new tensor directly.
- `predict(image_path, top_k)` softmaxes similarity over the whole gallery.
- The package contains no loss, optimizer or training loop. — [GeoCLIP source](https://raw.githubusercontent.com/VicenteVivan/geo-clip/main/geoclip/model/GeoCLIP.py)

**Packaging and licence**
- MIT licence; `pip install geoclip`; 512-dim GPS embeddings. — [GeoCLIP repo](https://github.com/VicenteVivan/geo-clip)

**Training code still missing**
- GitHub issues #1, #10 and #11 request training code; #18 asks for the full evaluation artefact.
- No issue covers custom galleries or region restriction. — [GeoCLIP issues](https://github.com/VicenteVivan/geo-clip/issues?q=is%3Aissue)

**Speed**
- 0.008 s per image end to end on an RTX 5090. — [Pinpoint](https://arxiv.org/html/2606.04133)

**Fine-tune precedents**
- GeoFT (ICLR 2025 workshop) fine-tuned GeoCLIP for Russia and Ukraine and only cut mean error from 3,520 km to 2,150 km. No street- or city-level numbers, no code. — [GeoFT](https://mlanthology.org/iclrw/2025/sun2025iclrw-geoft/)
- A Stanford CS231n project fine-tuned StreetCLIP, not GeoCLIP, on San Francisco street images and reportedly got about 600 m average error. This is a search snippet only; the PDF was too large to fetch. — [GeoVision SF](https://cs231n.stanford.edu/2025/papers/text_file_840560503-CS_231n_Final_Project.pdf)

**Other benchmarks (search snippets, not verified at source)**
- GeoCLIP on OSV-5M: 19.8% city-level accuracy. — [Semivariogram contrastive paper](https://arxiv.org/pdf/2509.21573)
- GeoCLIP within 25 km: 7.7%, versus 14.7% for GPT-4o, on a 2025 benchmark. — [GeoComp](https://arxiv.org/html/2502.13759)

### Inferences
**The draft's rejection figure: right numbers, wrong comparison**
- "10–33% within 1 km" matches the global literature.
- But that is a planet-wide search. A Toronto-only gallery removes all country- and city-scale error, so within-city performance at 1 km will be higher by an unmeasured amount.

**Why GeoCLIP still can't reach ≤10 m**
- The 150 m training noise, multi-scale RFF smoothing and sparse Flickr coverage of non-touristy Toronto make 10–100 m discrimination implausible without retraining.
- Even a Toronto fine-tune that lowers GPS noise to about 5–10 m would be an image → GPS regressor competing with image → image retrieval, where the photo is checked against an actual reference image. Specialist evidence favours retrieval plus verification for metre-scale work.

**Recommended role**
- Toronto gallery of about 50–100K points (for example a 50–100 m grid, or Mapillary image locations).
- Output a heatmap at roughly 0.5–2 km.
- Use it to restrict which Mapillary tiles MegaLoc searches, and as a signal the LLM can reason over.
- Cost: about 1 hour; the ViT-L/14 runs in fp16 within 8 GB.

### Gaps
- No published single-city gallery restriction or city-scale fine-tune of GeoCLIP with distance-threshold metrics.
- No published parameter count for GeoCLIP's trainable parts.
- MP-16 coverage of Toronto is unknown.

---

## Q2. Other global geolocators (PIGEON/PIGEOTTO, StreetCLIP, PLONK, OSV-5M baselines, G3, GeoRanker, Img2Loc, plus Pinpoint 2026): headline accuracy, code, weights, licences, and ≤10 m potential

### Takeaway
**None can reach ≤10 m. None reports anything finer than 1 km.**

The best global 1 km numbers are about 20% on Im2GPS3k and about 33% on YFCC4k (Pinpoint 2026, GeoRanker 2025).

Usable code and weights:
- G3: Apache-2.0
- GeoRanker: Apache-2.0
- PLONK: MIT
- GeoCLIP: MIT

Unusable:
- StreetCLIP: CC-BY-NC
- PIGEON: no weights
- Pinpoint: no weights

What transfers is the architecture pattern: retrieve, have an LLM add extra candidates, verify deterministically. The models themselves do not transfer.

### Cited Findings
**Leaderboards at 1 / 25 / 200 / 750 / 2500 km**

| Method | Im2GPS3k | YFCC4k |
|---|---|---|
| Pinpoint (2026) | **20.5** / 47.4 / 63.5 / 79.0 / 90.2 | **33.0** / 44.4 / 57.5 / 71.8 / 84.5 |
| GeoRanker (2025) | 18.79 / 45.05 / 61.49 / 76.31 / 89.29 | 32.94 / 43.54 / 54.32 / 69.79 / 82.45 |
| G3 (2024) | 16.65 / 40.94 / 55.56 / 71.24 / 84.68 | 23.99 / 35.89 / 46.98 / 64.26 / 78.15 |
| Img2Loc (2024) | 15.34 / 39.83 / 53.59 / 69.7 / 82.78 | 19.78 / 30.71 / 41.4 / 58.11 / 74.07 |
| PIGEOTTO (2024) | 11.3 / 36.7 / 53.8 / 72.4 / 85.3 | 10.4 / 23.7 / 40.6 / 62.2 / 77.7 |
| GeoCLIP | 14.11 / 34.47 / 50.65 / 69.67 / 83.82 | 9.59 / 19.31 / 32.63 / 55.0 / 74.69 |

Sources: [GeoRanker Table 1](https://arxiv.org/html/2505.13731); [Pinpoint](https://arxiv.org/html/2606.04133)

**Conflicting numbers**
- Img2Loc (GPT-4V) is reported elsewhere as 17.1 / 45.1 / 57.9 / 72.9 / 84.7 on Im2GPS3k and 14.1 / 29.6 / 41.4 / 59.3 / 76.9 on YFCC4k. — [arXiv 2509.01341](https://arxiv.org/html/2509.01341) vs [G3](https://arxiv.org/html/2405.14702)
- PIGEON on YFCC4k at 25 km: 23.7 per [GeoRanker](https://arxiv.org/html/2505.13731), 24.4 per [PLONK](https://arxiv.org/html/2412.06781).

**PIGEON / PIGEOTTO**
- PIGEON puts "over 40% of its guesses within 25 kilometers" globally on street view.
- PIGEOTTO gains up to 7.7 percentage points at city level and 38.8 at country level over the prior state of the art.
- Techniques: semantic geocells, multi-task contrastive pretraining, and retrieval over location clusters to refine guesses. — [PIGEON paper](https://arxiv.org/abs/2307.05845)
- Release: no weights, geocells or datasets; the code is for "academic validation" only. — [PIGEON repo](https://github.com/LukasHaas/PIGEON)

**StreetCLIP**
- CLIP ViT-L/14 at 336 px, about 1.1M street images from 101 countries.
- Zero-shot Im2GPS3k at 25 / 200 / 750 / 2500 km: 22.4 / 37.4 / 61.3 / 80.4. No 1 km number.
- **CC-BY-NC-4.0.** The card says geolocating users' private images is "out-of-scope and discouraged". — [StreetCLIP card](https://huggingface.co/geolocal/StreetCLIP)

**PLONK (CVPR 2025)**
- OSV-5M: GeoScore 3767, mean error 1069 km, country / region / city 76.2 / 44.2 / 15.4.
- YFCC4k at 25 / 200 / 750 / 2500 km: 23.7 / 36.4 / 54.5 / 73.6.
- Size and speed: ψ network about 36M parameters on a frozen DINOv2-L; about 2 ms per sample. — [PLONK paper](https://arxiv.org/html/2412.06781)
- Release: MIT; weights `PLONK_YFCC`, `PLONK_OSV_5M`, `PLONK_iNat` on Hugging Face. — [PLONK repo](https://github.com/nicolas-dufour/plonk)

**OSV-5M baselines (country / region / city)**
- SC Retrieval: 73.4 / 45.8 / 19.9
- Hybrid (classification + regression): 68.0 / 39.4 / 15.9 — [PLONK Table 1](https://arxiv.org/html/2412.06781)
- Code MIT; `osv5m/baseline` weights on Hugging Face. — [OSV-5M repo](https://github.com/gastruc/osv5m)
- Dataset licence: CC-BY-SA-4.0. — [Pinpoint](https://arxiv.org/html/2606.04133)

**G3**
- Geo-alignment: contrastive image / GPS / text alignment on MP16-Pro, with a GeoCLIP-style GPS encoder (Mercator projection plus RFF).
- Geo-diversification: GPT-4V proposes candidates from 4 RAG prompts.
- Geo-verification: the image-to-GPS encoder picks the best candidate. Without it, 1 km accuracy drops from 16.65 to 14.98.
- An open LLaVA-Next-8B variant is weaker but competitive. — [G3 paper](https://arxiv.org/html/2405.14702)
- Release: Apache-2.0; checkpoints and index at `Jia-py/G3-checkpoint`. — [G3 repo](https://github.com/Applied-Machine-Learning-Lab/G3)

**GeoRanker**
- Qwen2-VL-7B with LoRA scores retrieved and LLM-generated candidates, trained with a distance-aware loss.
- Training: about 16 h per epoch on 4× L40S at about 30 GB per GPU. — [GeoRanker paper](https://arxiv.org/html/2505.13731)
- Release: Apache-2.0; LoRA weights released. — [GeoRanker repo](https://github.com/Applied-Machine-Learning-Lab/GeoRanker)
- Inference: the re-ranking stage alone measured 288 s per image on an RTX 5090. — [Pinpoint](https://arxiv.org/html/2606.04133)

**Img2Loc**
- Training-free CLIP retrieval plus GPT-4V or LLaVA RAG. — [Img2Loc](https://arxiv.org/abs/2403.19584v1)
- No official code or licence found. — [search summary](https://astro.paperswithcode.com/paper/img2loc-revisiting-image-geolocalization)

**Pinpoint (2026)**
- Retrieval: frozen SigLIP 2 giant with a learned 256-dim image–GPS space.
- Re-ranking: a 4-layer Transformer. No MLLM.
- OSV-5M: city 26.0%; 35.6% within 25 km.
- Speed: 0.098 s per image.
- Release: no weights. — [Pinpoint](https://arxiv.org/html/2606.04133)

### Inferences
- **≤10 m verdict: no.** All are 1 km+ instruments. Their place in a ≤10 m pipeline is, at most, an area prior.
- **Most transferable idea:** G3-style "LLM proposes, deterministic verifier decides". At ≤10 m the verifier must be image-to-image (VPR plus local-feature inliers, then pose), not image-to-GPS.
- **Hardware fit:**
  - GeoCLIP, PLONK and the OSV-5M baseline run trivially on an RTX 4060.
  - GeoRanker needs a 7B VLM; it fits only quantized and is far too slow (estimate).

### Gaps
- No method reports thresholds below 1 km.
- Img2Loc's code and licence, and PIGEON's licence type, were not found.

---

## Q3. City-scale VPR (MegaLoc, SALAD, BoQ, EigenPlaces, CosPlace, MixVPR, AnyLoc): Recall@N, ≤10 m evidence, non-street-view queries, licences, VRAM and throughput

### Takeaway
VPR is the only specialist family whose output (a reference image with a known position) can support ≤10 m, but only as the first stage.

- **Accuracy at 25 m:** MegaLoc (2025, MIT) leads. Recall@1:
  - 95.3% on SF-XL v1, which uses hand-picked Flickr queries against a 2.8M-image street-view database
  - 96.5% on Tokyo 24/7 (phone queries)
  - about 52% on Flickr night and occlusion queries
- **Real social-media flood photos:** older 512-D models get only 30–52% Recall@1 at 100 m.
- **Accuracy at 10 m:** the only numbers found are 85–88% Recall@1 for CosPlace, EigenPlaces and MixVPR on dense vehicle data (SF-Loc). MegaLoc has not been measured at 10 m.
- **Licences:** SALAD is GPL-3.0. MegaLoc, BoQ and EigenPlaces are MIT; AnyLoc is BSD-3.
- **Storage:** MegaLoc descriptors take about 33.8 KB per image in fp32, which matters with 15 GB of free disk.

### Cited Findings
**MegaLoc model**
- DINOv2-B plus a SALAD layer; about 228M parameters; 8448-D descriptor; 322 px inference.
- Trained on GSV-Cities, MSLS, MegaScenes, ScanNet and SF-XL. — [MegaLoc paper](https://arxiv.org/html/2502.17237)
- MIT licence; loadable via `torch.hub`. No training code. The FAQ says fine-tuning is rarely needed, and 360° panoramas should be cut into perspective crops. — [MegaLoc repo](https://github.com/gmberton/MegaLoc)

**MegaLoc Table 1, Recall@1 / Recall@10 at 25 m**

| Method | MSLS val | Pitts30k | Tokyo 24/7 | SF-XL v1 (Flickr) | SF-XL night (Flickr) | SF-XL occlusion (Flickr) | Baidu |
|---|---|---|---|---|---|---|---|
| MegaLoc | 91.0 / 95.8 | 94.1 / 98.2 | 96.5 / 99.4 | **95.3 / 98.0** | **52.8 / 73.8** | **51.3 / 75.0** | 87.7 / 98.0 |
| SALAD | 88.2 / 95.0 | 92.3 / 97.4 | 94.6 / 98.1 | 88.7 / 94.4 | 46.1 / 62.4 | 50.0 / 68.4 | 72.7 / 93.6 |
| CliqueMining | 91.6 / 95.9 | 92.6 / 97.8 | 96.8 / 97.8 | 85.5 / 92.6 | 46.1 / 60.9 | 44.7 / 64.5 | 72.9 / 92.7 |
| EigenPlaces | 85.9 / 93.1 | 92.5 / 97.6 | 93.0 / 97.5 | 84.0 / 90.7 | 23.6 / 34.5 | 32.9 / 52.6 | 69.1 / 91.9 |
| CosPlace | 85.0 / 92.6 | 90.9 / 96.7 | 87.3 / 95.6 | 76.6 / 85.5 | 23.6 / 32.8 | 30.3 / 44.7 | 52.0 / 80.4 |
| MixVPR | 83.2 / 91.9 | 91.6 / 96.4 | 87.0 / 94.0 | 72.5 / 80.9 | 19.5 / 30.5 | 30.3 / 38.2 | 71.9 / 94.7 |
| AnyLoc | 58.7 / 74.5 | 86.3 / 96.7 | 87.6 / 97.5 | out of RAM | out of RAM | out of RAM | 75.6 / 95.2 |

- SF-XL v2 Recall@1: MegaLoc 94.8, SALAD 94.6.
- NetVLAD (2016, superseded): SF-XL v1 40.1, night 6.7. — [MegaLoc paper](https://arxiv.org/html/2502.17237)

**MegaLoc limitations**
- CliqueMining beats it on MSLS, which is mostly forward-facing Mapillary imagery.
- It fails when the database covers only one direction of travel, which the paper says is common in MSLS/Mapillary.
- Mapillary and Google Street View GPS labels contain errors. — [MegaLoc paper](https://arxiv.org/html/2502.17237)

**What the benchmark queries are**
- SF-XL v1: 1,000 hand-picked, location-verified Flickr photos with wide viewpoint and day/night variation, against 2.8M images from 2013.
- SF-XL v2: 598 San Francisco Landmark queries, mostly sunny.
- Correct means within 25 m. — [SF-XL / CosPlace paper](https://arxiv.org/html/2204.02287)
- SF-XL night (466 queries) and SF-XL occlusion (76 queries) are manually verified Flickr photos. Night photos add heavy viewpoint shift and artificial lighting. — [Barbarani et al. 2023](https://arxiv.org/pdf/2304.05887)
- Tokyo 24/7: 315 phone queries against about 76K Street View images. — [NPR paper](https://arxiv.org/pdf/2304.00276); [Deep VG Benchmark](https://arxiv.org/pdf/2204.03444)

**10 m and 20 m recall**
- Single-frame, on Wuhan vehicle data with about 9.46 m map spacing:
  - EigenPlaces-R50: 87.62 / 97.12
  - MixVPR: 86.75 / 95.60
  - CosPlace-R50: 85.71 / 95.55
  - AnyLoc: 80.39 / 89.73 — [SF-Loc](https://arxiv.org/html/2412.01500)
- Gains from loosening the threshold flatten between 10 and 25 m (2022 models). — [Deep VG Benchmark](https://arxiv.org/html/2204.03444)

**Real social-media flood photos (VPR-AttLLM, 100 m threshold because of geotag noise)**
- CosPlace-R50 (512-D), Recall@1 / @5 / @10:
  - San Francisco, 100 photos against 2.81M images: 52 / 57 / 60
  - Hong Kong, 100 photos against 1.15M Street View crops sampled every 15 m: 30 / 45 / 47
- EigenPlaces-VGG16: 38 / 40 / 41 (San Francisco) and 18 / 33 / 38 (Hong Kong).
- Gemini LLM attention adds about 1–4 points; SALAD gains 0.5–1.0.
- MegaLoc and BoQ were not tested. — [VPR-AttLLM](https://arxiv.org/html/2512.11811)

**BoQ (MIT)**
- DINOv2 variant (12,288-D), Recall@1 / Recall@5:
  - MSLS-val 93.8 / 96.8
  - Pitts30k 93.7 / 97.1
  - Pitts250k 96.6 / 99.1
  - AmsterTime 63.0 / 81.6
- Training code released December 2024. — [BoQ repo](https://github.com/amaralibey/Bag-of-Queries)

**SALAD**
- **GPL-3.0.**
- Recall@1: MSLS val 92.2; MSLS challenge 75.0.
- Compact variants: 512+32 and 2048+64 dimensions. — [SALAD repo](https://github.com/serizba/salad)

**EigenPlaces**
- MIT; ResNet / VGG backbones from 128 to 2048 dimensions.
- The README now recommends MegaLoc. — [EigenPlaces repo](https://github.com/gmberton/EigenPlaces)

**CosPlace**
- Trains a classifier over **10 m cells × 30° heading classes**; plain kNN at test time.
- About 80% less training memory than the previous state of the art.
- 512-D kNN search is about 8× faster than 4096-D.
- About 80 images per second (VGG16, V100). — [CosPlace paper](https://arxiv.org/html/2204.02287)

**MixVPR**
- Pitts250k / MSLS-val Recall@1 by descriptor size: 4096-D 94.3 / 88.2; 512-D 93.2 / 84.1; 128-D 88.7 / 78.5.
- No licence file visible. — [MixVPR repo](https://github.com/amaralibey/MixVPR)

**AnyLoc**
- BSD-3; DINOv2 ViT-G/14 with VLAD.
- A 16 GB GPU "should also work"; large databases may need up to 256 GB of RAM. — [AnyLoc repo](https://github.com/AnyLoc/AnyLoc)

**Evaluation tooling**
- `VPR-methods-evaluation` (MIT) wraps 19 methods and accepts custom query and database folders. Recall is computed from `@UTM_east@UTM_north@` filenames; `--no_labels` skips recall. The README excerpt read did not show whether the 25 m threshold is a command-line option.
- Each model keeps its own licence. — [VPR-methods-evaluation](https://github.com/gmberton/VPR-methods-evaluation)

### Inferences
**≤10 m verdict: partially**
- A modern retriever finds a reference within 10 m for most locatable, street-facing photos, if the database is dense (≤10 m spacing).
- SF-Loc's 85–88% at 10 m used 2023 models on easy same-domain vehicle queries. MegaLoc should do at least as well there. Social-media photos will be lower: on SF-XL night and occlusion, even 25 m Recall@1 is about 52%.
- The retrieved coordinate is the reference camera's, so ≤10 m on the photographed object requires the pose and offset hand-off.

**Use top-k geographic consensus**
- Even when top-1 is wrong at 10 m, Recall@10 at 25 m is 98% for MegaLoc on SF-XL v1.
- Feed the top-k into verification and pose estimation rather than trusting top-1.

**Storage (arithmetic)**

| Descriptor | 100K images | 1M images |
|---|---|---|
| 8448-D fp32 | 3.4 GB | 33.8 GB |
| 8448-D fp16 | 1.7 GB | 16.9 GB |
| 512-D fp32 | 0.2 GB | 2 GB |

- Dense ≤10 m spacing over all of Toronto (roughly 5,000+ km of streets, not verified) at several images per position will reach the hundreds of thousands to millions.
- Plan for fp16, PCA or PQ, or index only LLM/GeoCLIP-selected tiles on demand.

**Choice of retriever**
- MegaLoc (MIT) is the default on merit. BoQ-DINOv2 (MIT) is a reasonable second model for ensembling.
- Avoid SALAD if licence matters.
- Mapillary one-direction coverage is a documented MegaLoc failure mode.

### Gaps
- No 5 m or 10 m results for MegaLoc, BoQ or SALAD.
- No results on social-media civic-issue photos (potholes, graffiti, elevators) for any model.
- No consumer-GPU throughput or VRAM figures.
- MixVPR and CosPlace licences not verified.
- Not checked whether MegaLoc's MIT code reuses GPL-3.0 SALAD code.

---

## Q4. Re-ranking and verification (LightGlue, RoMa, MASt3R, LoFTR): speed versus accuracy, licences, and role at ≤10 m

### Takeaway
Verification does not produce a better coordinate by itself. At ≤10 m its two jobs are:
1. confirming which candidate actually shows the place, and abstaining when none does;
2. supplying correspondences for the pose step (hand-off).

**2025 evidence (MegaLoc top-100 re-ranked, 25 m):**
- Blind re-ranking lowers Recall@1 on easy sets, for example Pitts30k 94.1 → 85.2 with ALIKED+LightGlue.
- It raises Recall@1 on hard, Flickr-like sets: SF-XL night 52.8 → 56–61; SF-XL occlusion 51.3 → 55–61.
- Inlier counts beat descriptor distance as a confidence signal on hard sets.
- LoFTR and the LightGlue variants are the most consistent; RoMa is the worst in VPR despite leading two-view pose benchmarks.

No study reports re-ranking at thresholds below 25 m.

Licences:
- LightGlue: Apache-2.0
- ALIKED: BSD-3
- DISK: Apache-2.0
- SuperPoint: non-commercial
- LoFTR: Apache-2.0
- RoMa: MIT
- MASt3R: CC BY-NC-SA

### Cited Findings
**Recall@1 at 25 m after re-ranking MegaLoc's top-100**

| Matcher | Baidu | MSLS val | Pitts30k | SF-XL night | SF-XL occlusion | Tokyo 24/7 | Average |
|---|---|---|---|---|---|---|---|
| MegaLoc baseline (no re-ranking) | 87.7 | 91.0 | 94.1 | 52.8 | 51.3 | 96.5 | 85.5 |
| LoFTR | 94.8 | 85.4 | 87.2 | 58.2 | 60.5 | 96.5 | 85.7 |
| SuperGlue | 91.9 | 85.4 | 85.5 | 60.7 | 55.3 | 95.9 | 83.6 |
| SuperPoint + LightGlue | 92.6 | 83.9 | 85.9 | 58.8 | 56.6 | 98.4 | 84.5 |
| ALIKED + LightGlue | 94.3 | 87.5 | 85.2 | 56.2 | 56.6 | 97.5 | 83.3 |
| GIM-LightGlue | 92.4 | 86.4 | 88.8 | 59.7 | 53.9 | 96.5 | 85.0 |
| MASt3R | 89.8 | 71.7 | 85.9 | 56.2 | 56.6 | 94.0 | 81.4 |
| RoMa | 88.7 | 45.9 | 72.8 | 44.6 | 36.8 | 84.1 | 68.6 |

- No matcher improves average Recall@10.
- Degradation persists at 100 m.
- Only 25 m and 100 m thresholds were tested. — [To Match or Not to Match](https://arxiv.org/html/2504.06116)

**Verification as a confidence score**
- Area under the precision-recall curve for separating correct from wrong top-1 results, using inlier count:
  - SF-XL night: GIM-LightGlue 76.5, SuperPoint+LightGlue 75.8, versus 69.8 for L2 descriptor distance.
  - SF-XL occlusion: LoFTR 84.5 versus 77.5.
  - MASt3R falls below L2 on night (67.4).
- No precision at a fixed inlier threshold is reported. A logistic regression on inliers is shown only as histograms.
- Recommendation: use inliers as a gate and re-rank only low-confidence queries.
- Caveats: fixed 512×512 resolution (may handicap RoMa); single retriever. — [To Match or Not to Match](https://arxiv.org/html/2504.06116)

**Two-view benchmarks**

| Matcher | MegaDepth-1500 AUC@5 / 10 / 20 | WxBS mAA@10px |
|---|---|---|
| RoMa | 62.6 / 76.7 / 86.3 | 80.1 |
| LoFTR | 52.8 / 69.2 / 81.2 | 55.4 |
| LightGlue | 51.0 / 68.1 / 80.7 | 41.7 (with DISK) |

- RoMa runtime: 198.8 ms per pair (RTX 6000, 560 px, batch 8). — [RoMa paper](https://arxiv.org/html/2305.15404)
- RoMa licence: code MIT; DINOv2 Apache-2.0. Tiny RoMa (on XFeat) is the light option. — [RoMa repo](https://github.com/Parskatt/RoMa)

**LightGlue**
- Speed:
  - About 150 FPS at 1024 keypoints, and about 50 FPS at 4096, on an RTX 3080.
  - About 20 FPS at 512 keypoints on CPU.
  - 4–10× faster than SuperGlue.
- Licences: code and weights Apache-2.0; DISK Apache-2.0; ALIKED BSD-3; SuperPoint restrictive. — [LightGlue repo](https://github.com/cvg/LightGlue)
- SuperPoint's licence permits only "noncommercial internal research purposes". — [SuperPoint LICENSE](https://github.com/magicleap/SuperPointPretrainedNetwork/blob/master/LICENSE)

**LoFTR**
- Apache-2.0; SuperGlue optimal-transport files are not bundled.
- 4 checkpoints of about 45 MB each; also in Kornia. — [LoFTR repo](https://github.com/zju3dv/LoFTR)

**MASt3R**
- **CC BY-NC-SA 4.0**; checkpoints also inherit dataset licences.
- ViT-L encoder, ViT-B decoder, 512 px; ASMK retrieval option. — [MASt3R repo](https://github.com/naver/mast3r)

### Inferences
**≤10 m role**
- Use ALIKED+LightGlue or LoFTR on the top 5–20 (well under 1 s on a 4060, by estimate from the 3080 figures).
- Keep candidates with enough inliers.
- Pass the verified correspondences, together with Mapillary SfM poses, to the pose researcher's step: relative pose or PnP, triangulated across two or more references.
- Abstain if no candidate verifies.

**Reconsidering the draft**
- ALIKED+LightGlue is a sound, permissively licensed choice.
- But don't let it overwrite MegaLoc's ranking on clear, confident queries. Re-ranking a deep top-100 cost 6–9 points of Recall@1 on easy sets.

**RoMa and MASt3R**
- Weak as VPR re-rankers. MASt3R is also non-commercial.
- Either may still be useful later for metric pose between a few verified pairs, which belongs to the other researcher.

### Gaps
- No re-ranking results at ≤10 m.
- No precision at a fixed inlier threshold.
- No 4060 latency measurements.
- Efficient LoFTR and RoMa v2 not checked.

---

## Q5. Hierarchical and cell-based approaches (S2/H3 cells, geocells), and refinement after retrieval

### Takeaway
Global cell classification is largely superseded: PlaNet's S2 cells, PIGEON's semantic geocells and the OSV-5M hybrid have given way to continuous GPS embeddings and retrieve-then-re-rank. At city scale:
- CosPlace's **10 m × 30° heading** cells are the useful form, for training only.
- Coarse cells (H3 or neighbourhoods) are useful as a prior and for restricting search.
- Refinement to ≤10 m is not a cell problem. It is the pose hand-off.

### Cited Findings
- **CosPlace:** 10 m cells × 30° heading classes with a CosFace loss; kNN at test time. — [CosPlace paper](https://arxiv.org/html/2204.02287)
- **PIGEON:** semantic geocells plus retrieval within location clusters to refine guesses. — [PIGEON paper](https://arxiv.org/abs/2307.05845)
- **OSV-5M city accuracy by approach:**
  - Hybrid classification + regression: 15.9%
  - Regression: 10.7%
  - Retrieval: 19.9%
  - PLONK: 15.4%
  - Pinpoint retrieve-and-re-rank: 26.0% — [PLONK](https://arxiv.org/html/2412.06781); [Pinpoint](https://arxiv.org/html/2606.04133)
- **Hand-off evidence:** with a 3D map, MegaLoc retrieval plus local-feature pose reaches (5°, 1 m) recall of 60.4–94.9% on LaMAR phone queries. — [MegaLoc paper](https://arxiv.org/html/2502.17237)
- **Sequential refinement:** SF-Loc's sequence-based factor-graph refinement after VPR reaches 0.209 m RMSE. This needs video sequences, not single photos. — [SF-Loc](https://arxiv.org/html/2412.01500)

### Inferences
**Hierarchy for a ≤10 m Toronto system**
1. LLM clues plus GeoCLIP-over-Toronto: candidate H3 cells. Resolution 8 (about 0.7 km²) or 9 (about 0.1 km²) is a reasonable granularity (not sourced).
2. MegaLoc kNN inside those cells.
3. LightGlue or LoFTR verification.
4. Hand-off to pose and object-offset estimation.

The sub-10 m precision comes entirely from step 4.

### Gaps
- No city-scale comparison of H3 versus S2 cells.
- No published work on single-photo pose refinement against Mapillary SfM for social-media queries. That may be covered by the other researcher.

---

## Q6. Realistic accuracy ceiling for street-level geolocation of casual phone photos in a city with dense reference imagery, at ≤25 m and ≤10 m

### Takeaway
**At 25 m (reference image found):**

| Query type | Recall@1 |
|---|---|
| Locatable outdoor photos | About 95–97% (MegaLoc on Flickr / phone queries) |
| Night or occluded Flickr photos | About 51–61% (with re-ranking) |
| Real flood social-media photos | 30–52% at 100 m (older models) |
| Close-ups | No VPR signal |

**At ≤10 m, nobody has published a number for social-media photos.**
- The closest is 85–88% reference recall at 10 m on dense, same-domain vehicle data.
- Database pose error (about 2–5 m for Mapillary features, worse with urban-canyon drift) and query geotag error (about 5 m open sky, worse downtown) eat much of a 10 m budget.

A realistic ≤10 m success rate for unfiltered civic-issue social posts is well below the 25 m figures. It is only achievable with pose estimation on verified matches, and it is upper-bounded by how many photos show enough permanent streetscape.

### Cited Findings
**At 25 m**
- MegaLoc: SF-XL v1 (Flickr) 95.3 / 98.0 and Tokyo 24/7 (phone) 96.5 / 99.4 at Recall@1 / @10. — [MegaLoc paper](https://arxiv.org/html/2502.17237)
- Hard Flickr queries: SF-XL night 52.8 Recall@1 (60.7 with SuperGlue re-ranking); occlusion 51.3 (60.5 with LoFTR). — [MegaLoc](https://arxiv.org/html/2502.17237); [To Match or Not to Match](https://arxiv.org/html/2504.06116)
- Real flood photos at 100 m: CosPlace-R50 52% (San Francisco) and 30% (Hong Kong); +1–4 points with LLM attention. — [VPR-AttLLM](https://arxiv.org/html/2512.11811)

**At 10 m**
- 85.71–87.62% Recall@1 (CosPlace-R50, MixVPR, EigenPlaces-R50) on vehicle data with about 9.46 m spacing; 96.80% with 10-frame multi-frame fusion. — [SF-Loc](https://arxiv.org/html/2412.01500)
- Recall growth slows between 10 and 25 m; database density caps it (St Lucia: 88% of queries have a reference within 5 m). — [Deep VG Benchmark](https://arxiv.org/html/2204.03444)

**Position error in the references and ground truth**
- Mapillary-derived features: about 2.0–2.2 m error; "under 5m" overall. — [SotM 2022](https://2022.stateofthemap.org/sessions/DKLT7X/)
- Mapillary GPS drift near tall buildings. — [arXiv 1909.05621](https://arxiv.org/pdf/1909.05621)
- Phone GPS: about 4.9 m open sky (secondary source). — [Mapscaping](https://mapscaping.com/how-accurate-is-gps/)

**Global baseline for contrast**
- Best global result within 1 km is about 33% (YFCC4k). — [Pinpoint](https://arxiv.org/html/2606.04133)

### Inferences
**Rough ≤10 m expectation (not measured)**

| Photo type | Expected within 10 m |
|---|---|
| Clear daytime streetscape with dense Mapillary coverage | Perhaps 50–80%, after verification and pose |
| Flood, night or occluded | Perhaps 20–45% |
| Close-ups (pothole detail, elevator interior) | Near 0% from VPR. Must come from text, OCR, station or elevator IDs, or poster context |

**Evaluation**
- Build the Toronto test set with hand-verified map positions of the photographed object, not phone geotags.
- Report a locatable / unlocatable split and an abstention rate.

### Gaps
- No public ≤10 m benchmark of social-media or civic-issue photos.
- No statistic on the share of civic-issue social posts that are visually locatable.

---

## Q7. 2025–2026 work combining retrieval models with an LLM, and whether any reaches ≤10 m

### Takeaway
Three patterns exist, and none reports accuracy at ≤10 m:
1. **RAG:** retrieved coordinates go into the prompt (Img2Loc, G3, arXiv 2509.01341). Finest reported threshold: 1 km.
2. **VLM re-ranking or verification:** GeoRanker, at 1 km; "Scale, Don't Fine-tune" for VPR, at 25 m.
3. **LLM attention or agents:** VPR-AttLLM at 25 and 100 m; Thinking with Map at 500 m; GeoAgent.

For ≤10 m, the LLM's job is upstream:
- clues and OCR to narrow the area,
- proposing candidate cells,
- masking transient regions (water, vehicles, people),
- deciding when to abstain.

Metre-level work stays with retrieval, verification and pose.

### Cited Findings
**RAG with open VLMs (arXiv 2509.01341)**
- Qwen2-VL-72B with SigLIP retrieval over about 10M images.
- At 1 / 25 km: Im2GPS3k 17.1 / 38.7; YFCC4k 24.3 / 35.1.
- No code. — [arXiv 2509.01341](https://arxiv.org/html/2509.01341)

**VLM re-ranking for VPR ("Scale, Don't Fine-tune")**
- Qwen2.5-VL re-ranks the top-20 from DINOv2-GeM with JSON scoring of permanent objects.
- Tokyo 24/7 Recall@1 at 25 m: 77.14 → 83.81 (7B, 3.67 s per query) → 91.11 (32B with uncertainty penalty, 46.69 s per query).
- Pitts30k Recall@1: 77.77 → 82.33.
- The describe-then-compare approach (LLM4VPR-style) took 773–2,576 s per query and did worse than retrieval alone. — [arXiv 2509.02129](https://arxiv.org/html/2509.02129); [LLM4VPR](https://github.com/ai4ce/LLM4VPR)

**VPR-AttLLM**
- Gemini-2.5-Flash attention maps over the query.
- +1–4 points Recall@1 on real flood photos at 100 m.
- About $0.30 per 100 queries; Qwen3-VL-8B locally on a T4 takes about 57 s per query. — [VPR-AttLLM](https://arxiv.org/html/2512.11811)

**Global LLM-assisted methods versus Pinpoint**
- Pinpoint (no MLLM) beats GeoRanker at 1 km (20.5 versus 18.8 on Im2GPS3k) at 0.098 s versus 288 s per image for GeoRanker's re-ranking stage. — [Pinpoint](https://arxiv.org/html/2606.04133)

**Agents**
- Thinking with Map: Qwen3-VL-30B-A3B with map tools, GRPO training and a Qwen3-VL-235B verifier.
- Acc@500m: 14.86 (MAPBench-hard) and 57.94 (GeoBench). — [Thinking with Map](https://arxiv.org/html/2601.05432v1)
- GeoAgent: Street View navigation agents beat static baselines, but self-correction is weak. — [GeoAgent](https://arxiv.org/abs/2608.29483)
- GEO-Detective: +11.1% at country level. — [GEO-Detective](https://arxiv.org/abs/2511.22441)

### Inferences
- An MLLM re-ranker over a weak retriever (91.1 at 25 m on Tokyo 24/7) still trails MegaLoc alone (96.5). For ≤10 m it adds latency without supplying geometry.
- Use the LLM where specialists are blind: reading signs and post text, proposing areas, masking transients, abstaining, explaining.
- Borrowable:
  - G3-style "propose, then verify"
  - JSON lists of matching and mismatched permanent objects, useful as UI explanations
  - VPR-AttLLM-style masking of transient regions before retrieval

### Gaps
- No LLM + VPR system reports ≤10 m.
- The "Perceive to Hypothesize, Verify to Ground" paper (arXiv 2608.29880) was seen only as a reference list.
- Code and licences for VPR-AttLLM and Thinking with Map are unconfirmed.

---

## Q8. Which approaches transfer to a single-city (Toronto) ≤10 m system, and which techniques are worth borrowing

### Takeaway
**Transfers:**
- VPR retrieval: MegaLoc (MIT) as the default, BoQ (MIT) as a second.
- Local-feature verification: ALIKED+LightGlue or LoFTR, all permissive.
- Both serve as the front end to a pose and object-offset stage, the only route to reliable ≤10 m.

**Re-examined on merit:**
- GeoCLIP deserves a role the draft did not give it: a free Toronto-gallery prior. It cannot be the locator at ≤10 m.

**Do not transfer:** the global geolocators. They are 1 km+ instruments, and several carry licence or weight blockers.

**Borrow:**
- G3's propose-then-verify
- Inlier-gated re-ranking with abstention
- CosPlace's 10 m × heading cell training
- PIGEON's classify-a-cell-then-retrieve-within-it
- VPR-AttLLM's transient-region masking

### Cited Findings
- GeoCLIP: gallery swappable; MIT; 0.008 s per image; 150 m training noise; 14.11% within 1 km globally. — [GeoCLIP source](https://raw.githubusercontent.com/VicenteVivan/geo-clip/main/geoclip/model/GeoCLIP.py); [Pinpoint](https://arxiv.org/html/2606.04133); [GeoCLIP paper](https://arxiv.org/html/2309.16020)
- MegaLoc: 95.3% Recall@1 at 25 m on Flickr queries; MIT. — [MegaLoc paper](https://arxiv.org/html/2502.17237); [MegaLoc repo](https://github.com/gmberton/MegaLoc)
- Retrievers reach 85–88% at 10 m on dense vehicle data. — [SF-Loc](https://arxiv.org/html/2412.01500)
- Blind re-ranking hurts easy queries; inlier gating is recommended. — [To Match or Not to Match](https://arxiv.org/html/2504.06116)
- G3 verification ablation: 16.65 → 14.98 at 1 km without verification. — [G3](https://arxiv.org/html/2405.14702)
- Licence traps:
  - StreetCLIP: CC-BY-NC
  - SuperPoint: non-commercial
  - MASt3R: CC BY-NC-SA
  - SALAD: GPL-3.0
  - PIGEON and Pinpoint: no weights
  - Sources: [StreetCLIP](https://huggingface.co/geolocal/StreetCLIP); [SuperPoint](https://github.com/magicleap/SuperPointPretrainedNetwork/blob/master/LICENSE); [MASt3R](https://github.com/naver/mast3r); [SALAD](https://github.com/serizba/salad); [PIGEON](https://github.com/LukasHaas/PIGEON); [Pinpoint](https://arxiv.org/html/2606.04133)

### Inferences
**Ranked by value for a ≤10 m target on an RTX 4060 (8 GB) and 15 GB of disk**
1. **Dense Mapillary database.** Aim for ≤10 m spacing, both directions or 360° crops, and computed (SfM) poses. The SF-Loc and Deep VG evidence says database density and pose quality cap ≤10 m more than model choice does.
2. **MegaLoc retrieval** over that database, stored as fp16, PCA or PQ, or indexed per tile on demand.
3. **ALIKED+LightGlue or LoFTR on the top 5–20.** Use inliers for the accept/abstain decision and as correspondences for the pose hand-off. Do not blindly reorder confident retrievals.
4. **Hand-off to pose and object-offset estimation** (other researcher) for the final ≤10 m coordinate.
5. **GeoCLIP over a Toronto gallery** (about 1 hour of work) as a prior over the search area, alongside LLM clue extraction.
6. **Skip:**
   - PIGEON and Pinpoint: no weights.
   - StreetCLIP: non-commercial, and its card discourages this use.
   - GeoRanker: too slow and coarse.
   - PLONK: redundant with GeoCLIP for one city.
   - RoMa and MASt3R as re-rankers: weak in VPR, and MASt3R is non-commercial.

**Test set**
- Hand-label ground truth for the photographed object.
- Score at 10 m and 25 m, with an abstention rate.
- Use `VPR-methods-evaluation` with UTM-named files for the retrieval stage.

### Gaps
- No Toronto-specific VPR benchmark. Mapillary density in Toronto was not assessed (possibly another researcher's scope).
- No head-to-head of GeoCLIP-with-a-city-gallery versus VPR.
- No ≤10 m evaluation of the full retrieve → verify → pose pipeline on social-media photos.
