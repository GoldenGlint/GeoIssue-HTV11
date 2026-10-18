# Metre-level ("last mile") localization of a single casual photo in Toronto: methods, data, error budget, pipeline

Scope note: this file covers the step after a coarse region (roughly 100-500 m) is already known, i.e. getting from "the right street" to camera and object positions within 10 m. Coarse retrieval/VPR, LLM geolocation and Google ToS are covered by other researchers. Dates: today is 2026-10-17; sources from before 2024 are flagged [older].

---

## Q1. Structure-based visual localization (HLoc: retrieval -> local features -> LightGlue -> 2D-3D -> PnP-RANSAC): accuracy, requirements, licences

### Takeaway
When a query overlaps a good SfM reference model, structure-based localization is sub-metre for most daytime outdoor queries (about 87-90% within 0.25 m on Aachen Day; Cambridge median about 16 cm). That is about 20-40x better than the 10 m requirement, so the absolute error comes from how well the reference model is georegistered, not from the localizer. It needs a triangulated SfM model of the area with features extracted from the reference images. Use ALIKED (BSD-3) or DISK (Apache-2.0) with LightGlue (Apache-2.0). Avoid SuperPoint and SuperGlue if a commercial licence matters.

### Cited Findings
- HLoc pipeline: (1) extract local features for database and query images; (2) build a reference 3D SfM model (covisible pairs via retrieval, match with SuperGlue/LightGlue, triangulate with COLMAP); (3) retrieve database images for each query; (4) match the query; (5) localize. "When 3D Lidar scans are available ... step 2 can be skipped." Since hloc-v1.3, COLMAP does not need installing (pycolmap is enough). Intrinsics can be given or are refined during reconstruction. Repo licence: Apache-2.0. Supported features: SuperPoint, DISK, D2-Net, SIFT, R2D2. Matchers: SuperGlue, LightGlue, NN, LoFTR — [cvg/Hierarchical-Localization](https://github.com/cvg/Hierarchical-Localization)
- HLoc README, Aachen Day-Night [older, ~2020-21 README numbers, NetVLAD retrieval; three thresholds per cell, conventionally (0.25 m,2°)/(0.5 m,5°)/(5 m,10°)]: SuperPoint+SuperGlue Day 89.6/95.4/98.8, Night 86.7/93.9/100. SuperPoint+NN Day 85.4/93.3/97.2, Night 75.5/86.7/92.9 — [cvg/Hierarchical-Localization](https://github.com/cvg/Hierarchical-Localization). Threshold convention (0.25 m,2°)/(0.5 m,5°)/(5 m,10°) — [Residual Learning for Image Point Descriptors, arXiv 2312.15471](https://arxiv.org/pdf/2312.15471)
- Aachen Day-Night v1.1, SuperPoint+LightGlue: Day 90.2/96.0/99.4, Night 77.0/91.1/100 at (0.25 m,2°)/(0.5 m,5°)/(1.0 m,10°) [older, ICCV 2023] — [LightGlue ICCV 2023 supplemental](https://openaccess.thecvf.com/content/ICCV2023/supplemental/Lindenberger_LightGlue_Local_Feature_ICCV_2023_supplemental.pdf)
- Aachen v1.1 with HLoc (model triangulated from the 6,697 reference images), ALIKED: about 87.3% day and 73.3% night at (0.25 m,2°), about 97.3% day and 96.9% night at (5 m,10°). The matcher paired with ALIKED is not confirmed in the snippet — [RIPE, arXiv 2507.04839](https://arxiv.org/pdf/2507.04839)
- Aachen v1.1, structure-based HLoc with SP+LG: top-20 retrieval gives Day 88.1/95.4/99.0, Night 71.7/89.0/97.9. Top-10 gives Day 87.0/94.8/98.5, Night 70.2/87.4/97.4 (0.25 m/0.5 m/5 m). MeshLoc top-20: Day 85.9/93.6/98.8 — [A Guide to Structureless Visual Localization, arXiv 2504.17636 (2025)](https://arxiv.org/html/2504.17636v1)
- Cambridge Landmarks, hloc (structure-based): median 15.6 cm / 0.21°, strict success (0.25 m,2°) 0.688. Reloc3r-512 on the same benchmark: 55.6 cm / 0.57°, success 0.233 — [RIC-Loc, arXiv 2607.04722 (2026)](https://arxiv.org/html/2607.04722v1)
- Licences of feature components: LightGlue code and weights Apache-2.0. "SuperPoint follows a different, restrictive license" (covers the weights and superpoint.py). DISK Apache-2.0. "ALIKED was published under a BSD-3-Clause license." — [cvg/LightGlue](https://github.com/cvg/LightGlue)
- LightGlue speed: on an RTX 3080, "150 FPS @ 1024 keypoints and 50 FPS @ 4096 keypoints per image" with compilation and adaptivity. That is a 4-10x speedup over SuperGlue. CPU (i7-10700K): 20 FPS at 512 keypoints. Flash attention cuts memory "without any impact on accuracy" — [cvg/LightGlue](https://github.com/cvg/LightGlue)

### Inferences
- These benchmarks use dense, curated reference sets with accurate relative poses (Aachen has 6,697 references). Casual social-media photos taken against crowd-sourced Mapillary references will see lower recall: more viewpoint and season change, cropping, unknown focal length. When registration does succeed, though, the error relative to the reference model stays well under 1 m. So the 10 m budget is spent on (a) georegistering the reference model and (b) moving from camera to object (see Q2 and Q7).
- For a hackathon demo, SuperPoint's restrictive licence may be tolerable, but ALIKED+LightGlue costs nothing to switch to and is licence-clean (BSD-3 + Apache-2.0). It also reaches comparable Aachen numbers.
- An RTX 4060 Laptop (8 GB) is slower than a desktop 3080. Matching 10-20 retrieved references with LightGlue at 2,048 keypoints should still take around a second (my extrapolation from the 3080 figures, not a measured number).

### Gaps
- I found no exact ALIKED+LightGlue Aachen v1.1 number with a confirmed matcher, and no HLoc numbers for crowd-sourced (Mapillary-style) reference maps.
- I found no published VRAM or runtime for running the full HLoc pipeline on an 8 GB laptop GPU.

---

## Q2. Building the 3D reference from Mapillary (API v4 fields, absolute accuracy, SfM on downloaded images)

### Takeaway
Mapillary API v4 provides per-image SfM-refined poses (computed_geometry, computed_compass_angle, computed_rotation, computed_altitude), intrinsics (camera_parameters), and links to a point cloud and a mesh. That is enough to build a fixed-pose reference model in hloc: import the poses, re-extract ALIKED features, triangulate. Running unconstrained SfM is not needed. Absolute accuracy of Mapillary positions is a few metres: raw phone GPS is about 5-10 m, and map features derived from Mapillary have about 2 m mean error. That is good enough for a 10 m target but sets the floor of the error budget. The sfm_cluster point cloud is a zlib-compressed JSON partial reconstruction with no local descriptors, so it cannot be used directly for 2D-3D matching.

### Cited Findings
- Image entity fields (verbatim from docs): altitude ("original altitude from camera Exif"), atomic_scale ("scale of the SfM reconstruction around the image"), camera_parameters (focal length, k1, k2), camera_type ("perspective", "fisheye", "equirectangular"/"spherical"), compass_angle ("original"), computed_altitude, computed_compass_angle ("after running image processing"), computed_geometry ("GeoJSON Point, location after running image processing"), computed_rotation ("corrected orientation of the image as an axis-angle rotation vector"), geometry (original GeoJSON point), mesh ({id,url} "URL to the mesh"), sfm_cluster ({id,url} "URL to the point cloud data in JSON and compressed by zlib"), thumb_256/512/1024/2048/original_url, sequence, detections, quality_score (0-1), is_pano, merge_cc ("ID of the aligned connected component") — [Mapillary API v4 docs](https://www.mapillary.com/developer/api-documentation)
- Rate limits: entity APIs 60,000/min per app, search APIs 10,000/min, tiles 50,000/day. Image, map-feature and detection bbox queries "must be smaller than 0.01 degrees square" — [Mapillary API v4 docs](https://www.mapillary.com/developer/api-documentation)
- sfm_cluster refers to partial local SfM reconstructions (a local reconstruction may contain several sfm_cluster values; merge_cc covers the whole). The full download URL is returned in the API response, and hand-built URLs return "Bad URL hash". Earlier docs labelled it .ply, but it is compressed JSON — [Mapillary forum: images optimized together](https://forum.mapillary.com/t/api-identify-images-whose-geometry-was-optimized-together/10070); [Mapillary forum: mesh and point cloud format](https://forum.mapillary.com/t/api-mesh-and-point-cloud-format/6664)
- How computed positions are made: OpenSfM computes camera positions from image and GPS data, and has historically not assessed GPS quality because no good Exif metric exists (GPSDOP is receiver-relative) — [Mapillary forum: How does Mapillary correct GPS location](https://forum.mapillary.com/t/how-does-mapillary-correct-gps-location/7193). Image count and overlap matter more than GPS quality, and panoramas help most — same forum thread via [search summary](https://forum.mapillary.com/t/how-does-mapillary-correct-gps-location/7193). Mapillary's SfM triangulates several images around a place to correct rough phone GPS, and positions should improve as more images are added — [Mapillary help center](https://help.mapillary.com/hc/en-us/articles/115001778685)
- Accuracy of Mapillary-derived map features [older, 2022]: street lights in Altınordu (323 lights, 9 km²) had mean positional error 2.02 m (GoPro MAX), 2.17 m (GoPro Hero 7), 2.21 m (iPhone 11). Completeness was 77.3% / 87.6% / 71.9%. "A large part of the final positional error" is attributed to device GPS, and the 3D reconstruction "mitigates some of these effects". All errors under 5 m — [SotM 2022 talk](https://2022.stateofthemap.org/sessions/DKLT7X/)
- The MapAnything authors measured a mean deviation of 5.5 m between Mapillary GPS positions and truth on 12 manually measured images (small sample) — [MapAnything, arXiv 2509.14839v3 (2025)](https://arxiv.org/html/2509.14839v3)
- Failure reports (Aug 2024): estimated ("orange dot") positions are sometimes "way off", e.g. flying into woodland or off a motorway bridge, especially for dashcam/time-lapse sequences. Some users note the estimate has improved over the past year. No staff reply and no metre figures — [Mapillary forum thread 8311](https://forum.mapillary.com/t/the-estimated-position-is-sometimes-severely-off-causing-wrong-object-placements-on-map/8311)
- Older context: input phone GPS errors are about 5 m in an OpenSfM pipeline [older, 2018] — [LineNet, arXiv 1807.05696](https://arxiv.org/pdf/1807.05696). Mapillary sequences "often" show GPS drift, and overlapping repeat uploads can correct it [older, 2019] — [arXiv 1909.05621](https://arxiv.org/pdf/1909.05621)
- Licence: all Mapillary images are CC BY-SA (changed from CC BY-NC on 29 April 2014). Attribution format: title, link, username, "licensed under CC-BY-SA" — [Mapillary help: Licenses](https://help.mapillary.com/hc/en-us/articles/115001770409-Licenses); [Mapillary blog 2014](https://blog.mapillary.com/update/2014/03/17/mapillary-goes-creative-commons.html). The CC BY-SA licence permits commercial use, but a community thread flags possible conflicts with service-terms restrictions (unresolved) — [Mapillary forum: Wikimedia licensing](https://forum.mapillary.com/t/licensing-issues-for-using-mapillary-images-on-wikimedia-commons/3821)
- Precedent: OrienterNet's MGL dataset is built directly from Mapillary via the API with a developer token (`python -m maploc.data.mapillary.prepare --token ...`), and the dataset is CC-BY-SA — [facebookresearch/OrienterNet](https://github.com/facebookresearch/OrienterNet)
- SfM runtime (for the option of reconstructing from downloaded images): on KITTI, per 100 frames, about 346 s total for COLMAP vs about 102 s for GLOMAP, with mapping being most of the gap — [CuSfM, arXiv 2510.15271 (2025)](https://arxiv.org/pdf/2510.15271). On CAMPUS (>29,000 images): COLMAP about 1,588 min vs GLOMAP about 580 min — [MGSfM ICCV 2025 supplemental](https://openaccess.thecvf.com/content/ICCV2025/supplemental/Tao_MGSfM_Multi-Camera_Geometry_ICCV_2025_supplemental.pdf). GLOMAP is "on par or better than COLMAP" in accuracy and "orders of magnitude faster" [ECCV 2024] — [GLOMAP](https://www.ecva.net/papers/eccv_2024/papers_ECCV/html/5646_ECCV_2024_paper.php). On a tiny ETH3D scene, COLMAP (12.7 s) beat GLOMAP (16.4 s) — [DGSfM, arXiv 2607.09507](https://arxiv.org/pdf/2607.09507)

### Inferences
- Recommended reference build (per 200-500 m tile): query the Mapillary bbox in tiles under 0.01°. Download thumb_1024 or thumb_2048 images. Write a COLMAP model whose camera poses come from computed_geometry plus computed_rotation (converted to local ENU metres) and whose intrinsics come from camera_parameters. Then run hloc's "triangulation from known poses" with ALIKED+LightGlue, matching pairs chosen by distance/heading. This avoids full SfM. The point triangulation and the Sim(3) to world coordinates are then exactly Mapillary's georegistration, so absolute error is about 2-5 m, inherited from Mapillary. Images from one sequence share correlated GPS bias, so averaging helps less than 1/sqrt(N).
- Alternative: run COLMAP or GLOMAP on about 300-1,000 downloaded images with GPS priors and align with Sim(3) to computed_geometry. From the KITTI rate (about 1-3.5 s per frame), expect about 10-60 min per tile on a laptop. Feature extraction and LightGlue matching fit in 8 GB. GLOMAP/COLMAP mapping is mostly CPU and RAM (31 GB is plenty for that scale). This is an extrapolation, not a measurement.
- Disk: 1,000 images at 1024 px (about 150-250 KB each) is roughly 0.2 GB per tile, plus features. Pre-building 20-50 hotspot tiles fits in about 15 GB (estimate).
- Prefer is_pano images and recent captured_at. Filter on quality_score. Merge across several sequences (several merge_cc components) to dilute per-sequence GPS bias.

### Gaps
- Mapillary does not publish an absolute accuracy figure for computed_geometry. The best evidence is the 2022 street-light study (about 2 m mean) and anecdotes.
- The units and normalisation of camera_parameters focal length are not stated in the docs excerpt (OpenSfM normally normalises focal by image size, but I did not verify this). The exact JSON schema of the sfm_cluster file is undocumented (presumably OpenSfM reconstruction JSON). Unverified.
- I found nothing on Mapillary coverage density in Toronto (images per km, recency). The team should check this with their token early.

---

## Q3. Structure-free alternatives (posed references + relative pose/triangulation; DUSt3R/MASt3R/VGGT/Reloc3r; map-free)

### Takeaway
"Structureless" localization from a handful of posed reference images (no prebuilt SfM) gets close to structure-based accuracy when it uses explicit geometry: E5+1 or local triangulation with RoMa or SP+LightGlue and the top-10 references reaches 76-84% within 0.25 m and about 98% within 5 m on Aachen Day. That makes it the natural fit for on-the-fly Mapillary or Street View references. Pure relative-pose regression (Reloc3r) and feed-forward 3D models alone are much worse at outdoor city scale. MASt3R/DUSt3R are non-commercial. VGGT code is commercial-friendly, but its original weights are non-commercial, and a VGGT reference-consensus method needed 13 GB VRAM.

### Cited Findings
- Aachen Day-Night v1.1, top-10 EigenPlaces references, recall (0.25 m,2°)/(0.5 m,5°)/(5 m,10°) — [A Guide to Structureless Visual Localization, arXiv 2504.17636 (2025)](https://arxiv.org/html/2504.17636v1):
  - Essential matrix 5-pt (RoMa): Day 59.1/80.0/97.9, Night 52.4/78.0/97.4
  - Essential matrix 3-pt+depth (RoMa/Metric3D): Day 66.7/86.8/98.4
  - E5+1 semi-generalized relative pose (RoMa): Day 78.4/89.8/97.8, Night 65.4/84.8/97.9
  - Local triangulation (all) + absolute pose (RoMa): Day 84.0/92.8/97.9, Night 68.6/85.3/97.9
  - LazyLoc (MASt3R): Day 73.7/90.5/97.5
  - Relative pose regression: Reloc3r Day 5.2/14.2/63.0. MASt3R pose-align 9.6/39.6/88.6. Essential matrix from MASt3R poses 23.2/49.0/91.0. MASt3R depth+P3P 0.1/1.1/37.7
  - With SP+LG and top-20: Local triangulation Day 86.7/93.8/98.3 vs HLoc 88.1/95.4/99.0. E5+1 Day 77.8/89.1/98.1
  - Extended CMU Seasons Urban, local triangulation (RoMa): 95.5/98.5/99.5. E5+1: 93.0/97.2/99.1
  - Conclusions: "more explicit use of geometric reasoning often leads to better pose accuracy", and "structureless approaches can be competitive compared to structure-based methods". RoMa was best for most methods outdoors. The paper does not study noisy reference poses.
- RIC-Loc (2026): a frozen VGGT predicts poses, depth and tracks against K=8 references chosen from a pool of L=20 (MegaLoc). Each reference gives one pose hypothesis, fused by robust consensus. Cambridge median 40.0 cm / 0.40° (hloc 15.6 cm, Reloc3r 55.6 cm). 7-Scenes 2.9 cm. Per-query 1.9-3.4 s. Peak memory 13.1 GB on an RTX 4090. Failure-detection AUROC 0.77-0.82 — [RIC-Loc, arXiv 2607.04722](https://arxiv.org/html/2607.04722v1)
- NAVER Gangnam (large indoor station), recall at (1 m,5°): MASt3R 54.1% (B2) / 55.6% (B1). Reloc3r 0.4% / 0.9% (median 38 m / 4.7 m). DUSt3R 28.3% / 58.2% — [RIC-Loc](https://arxiv.org/html/2607.04722v1)
- Map-free relocalization leaderboard (single reference frame, metric pose): DUNE (ViT-B)+MASt3R median 0.389 m / 4.56°, VCRE<45px AUC 0.840. RoMa-Omega 0.440 m. MASt3R (Ess.Mat + D.Scale) 0.368 m / 2.20°. RoMa w/ Metric3Dv2 0.834 m / 11.89° — [Niantic map-free leaderboard](https://nianticspatial.com/research/map-free/leaderboard). The MASt3R paper reports test-set medians of 0.93 m (feature-based) and 0.46 m (auto depth), and a NAVER blog says 0.36 m. The figures differ by setting and version — [MASt3R arXiv 2406.09756](https://arxiv.org/pdf/2406.09756); [NAVER Labs blog](https://europe.naverlabs.com/blog/mast3r-matching-and-stereo-3d-reconstruction/)
- MASt3R licence: "The code is distributed under the CC BY-NC-SA 4.0 License". Checkpoints also require agreeing to every training dataset's licence, and "The mapfree dataset license in particular is very restrictive." MASt3R-SfM = make_pairs (retrieval) + sparse_global_alignment — [naver/mast3r](https://github.com/naver/mast3r)
- VGGT licence: "All code in this repository is now under a commercial-use-friendly license" (excluding military use). "The original checkpoint remains non-commercial." VGGT-1B-Commercial is available via an application form (Co3D AUC@30 90.37 vs 89.98 for the original). A May 2026 fix lets it run "roughly 2-3x more input frames" at the same memory. Predicts intrinsics and extrinsics. "Typically reconstructs a scene in less than 1 second" — [facebookresearch/vggt](https://github.com/facebookresearch/vggt)
- RoMa: "All our code except DINOv2 is MIT license". DINOv2 is Apache-2.0. Default resolution 560 upsampled to 864. A Tiny RoMa (XFeat-based) variant exists — [Parskatt/RoMa](https://github.com/Parskatt/RoMa). Runtime: about 198.8 ms per pair at 560×560, batch 8, on an RTX 6000 — [RoMa CVPR 2024 supplemental](https://openaccess.thecvf.com/content/CVPR2024/supplemental/Edstedt_RoMa_Robust_Dense_CVPR_2024_supplemental.pdf). RoMa v2 (Nov 2025) is about 1.7x faster than RoMa — [RoMa v2, arXiv 2511.15706](https://arxiv.org/pdf/2511.15706)

### Inferences
- For CivicLens, the most practical structure-free recipe is: retrieve about 10-20 posed Mapillary references near the coarse location; match with ALIKED+LightGlue (fast) or RoMa (robust, MIT); then either (a) locally triangulate 3D points from reference pairs using their Mapillary poses and solve query PnP-RANSAC ("local triangulation", the best structureless variant), or (b) estimate relative pose to each reference and triangulate the camera centre from the bearing rays (pose triangulation / E5+1). Both inherit the absolute error of Mapillary's poses (Q2).
- Reloc3r and other pure relative-pose regressors should not carry the metric estimate: they score 5% at 0.25 m and 63% at 5 m on Aachen Day. MASt3R can serve as a fallback matcher or scale source on hard pairs (wide baselines, night), if non-commercial licensing is acceptable for the hackathon.
- VGGT-based consensus (RIC-Loc) needed 13.1 GB at K=8 on a 4090. On 8 GB it would need fewer references or the 2026 memory fix (unverified on 8 GB).

### Gaps
- I found no study of structureless accuracy as a function of reference-pose noise (exactly the Mapillary case). The Guide explicitly does not evaluate it.
- I did not verify Reloc3r's licence or DUSt3R's licence text directly (DUSt3R is believed to share NAVER's CC BY-NC-SA terms; unverified here).

---

## Q4. Street-level reference matching / "render-and-compare" last mile (Street View panoramas or Mapillary crops at candidate points)

### Takeaway
Matching a query photo against street-level panoramas or their perspective crops with known poses, then solving relative pose plus triangulation or PnP, is a proven route to metre-level positions. Google's own VPS, built from Street View, typically achieves better than 5 m and often about 1 m. A 2015 academic Street View metric-localization system got 40% within 1 m and 60% within 1.5 m (with image sequences). The accuracy figures from Q1-Q3 apply directly. The per-photo cost is retrieving about 10-20 reference views (each panorama cut into several perspective crops) and matching them, which takes about 1-5 s on an 8 GB GPU with LightGlue and longer with RoMa. Open-source GeoGuessr-style "Street View + LightGlue" tools exist, but their accuracy claims are unverified.

### Cited Findings
- Google ARCore Geospatial API (VPS built from Street View imagery): "under typical conditions, VPS can be expected to provide positional accuracy typically better than 5 meters and often around 1 meter, and a rotational accuracy of better than 5 degrees". Outside VPS coverage it falls back to GPS, which "may be low in dense urban settings" — [ARCore Config.GeospatialMode reference](https://developers.google.com/ar/reference/java/com/google/ar/core/Config.GeospatialMode); VPS uses a global 3D point cloud from Street View — [ARCore Geospatial overview](https://developers.google.cn/ar/develop/geospatial)
- Agarwal, Burgard & Spinello, "Metric Localization using Google Street View" [older, 2015]: matched rectilinear crops of Street View panoramas, triangulated features from a short monocular sequence (bearing-only), and aligned rigidly to the panoramas. Freiburg parking lot, AprilTag ground truth: "about 40% of the runs we are within a 1m accuracy, 60% within 1.5m". Per-panorama errors ranged from about 0.37 m to 12.38 m. Accuracy fell when features were far away (>50 m) and was best with features at 15-20 m. The system refuses to report when matching views are estimated too far away. It cites mobile-phone GPS at 5-8.5 m — [ar5iv 1503.04287](https://ar5iv.labs.arxiv.org/html/1503.04287)
- Street View georeferencing accuracy [older, 2012]: intersection from a pair of GSV panoramas against known points gave RMSE ±0.52 m (X), ±1.23 m (Y), ±5.78 m (h). Errors in Google-supplied position parameters dominate — [ISPRS Annals I-4, 2012](https://isprs-annals.copernicus.org/articles/I-4/305/2012/)
- Zamir & Shah: ECCV 2010 "Accurate Image Localization Based on Google Maps Street View" targeted accuracy comparable to hand-held GPS. The TPAMI 2014 GMCP method matches SIFT features to multiple nearest neighbours on about 102k Street View images and beats the prior state of the art by about 10%. The public dataset has 62,058 GSV images (Pittsburgh, Orlando, part of Manhattan). These are retrieval methods: their output is the nearest panorama location, not a metric pose [older] — [CRCV GMCP project](https://www.crcv.ucf.edu/projects/GMCP_Geolocalization/); [ECCV 2010](https://mlanthology.org/eccv/2010/zamir2010eccv-accurate); [arXiv 1703.07815](https://arxiv.org/pdf/1703.07815)
- Open-source "Netryx": crawls Street View panoramas, indexes CosPlace embeddings, then runs global retrieval, ALIKED/DISK + LightGlue matching, and refinement. Claims "sub-50m accuracy" and a 4 GB VRAM minimum. Claims are self-reported and come from third-party mirrors of its docs (unverified) — [Netryx skill mirror](https://claudeskills.info/skills/aradotso/trending-skills/netryx-street-level-geolocation/)
- Reference counts used by state-of-the-art structureless methods: top-10 or top-20 retrieved references ([Structureless guide](https://arxiv.org/html/2504.17636v1)). K=8 active of L=20 retrieved, with 7-Scenes strict success rising from 0.748 (K=4) to 0.796 (K=16) ([RIC-Loc](https://arxiv.org/html/2607.04722v1)).
- Matching speed: LightGlue 50-150 FPS on an RTX 3080 ([cvg/LightGlue](https://github.com/cvg/LightGlue)). RoMa about 199 ms per pair on an RTX 6000 ([RoMa supplemental](https://openaccess.thecvf.com/content/CVPR2024/supplemental/Edstedt_RoMa_Robust_Dense_CVPR_2024_supplemental.pdf)).
- Render-and-compare against city models: localizing against textureless LoD1/LoD2 models relies on silhouette/line alignment (LoD-Loc v2, ICCV 2025, aerial). The egenioussBench benchmark (smartphone images vs a city-scale mesh plus CityGML LoD2, cm-level ground truth) says the task "exposes the limitations" of feature-based and simple render-and-compare strategies — [LoD-Loc v2, arXiv 2507.00659](https://arxiv.org/pdf/2507.00659); [ISPRS 2025 egenioussBench](https://isprs-archives.copernicus.org/articles/XLVIII-1-W6-2025/75/2025/)

### Inferences
- Concrete render-and-compare loop (works for Mapillary today, and for Street View subject to the ToS check by the other researcher):
  1. Sample candidate reference viewpoints within the coarse region (for example the top-N retrieval hits plus their neighbours).
  2. For each panorama, cut 4-8 perspective crops (90° FoV, headings every 45-90°, pitch about 0-10°). Mapillary perspective images are used as they are.
  3. Match the query with ALIKED+LightGlue (RoMa for hard cases).
  4. Keep references with at least about 50-100 inliers.
  5. Estimate pose by local triangulation plus PnP-RANSAC, or pose triangulation from 3 or more references with sufficient baseline.
  Budget: about 20 reference views per photo. That is about 1 s of LightGlue matching, or about 5-10 s with RoMa, on a 4060 Laptop (scaled from the 3080/RTX 6000 figures; not measured).
- Without depth or SfM points, the camera position comes from triangulating bearings to two or more references a few metres apart. A single reference gives direction but no scale. A panorama spacing of about 10 m along streets (not verified here) gives a good baseline. Accuracy then depends on the reference positions (about 1-3 m for Street View per the 2012 study and VPS; about 2-5 m for Mapillary).
- Rendering synthetic views from a mesh (Mapillary mesh field, Google 3D Tiles, Toronto 3D massing) is a weaker fallback. Real imagery from posed panoramas is the better reference for casual photos.

### Gaps
- I found no peer-reviewed, recent (2024-2026) evaluation of single-photo localization against Street View panoramas reporting a metre-level error distribution. Academic numbers are either older (2015) or Google's product statement for live AR sessions.
- Zamir & Shah's exact metre-threshold percentages were not retrieved.
- I did not verify Google Street View panorama spacing or the accuracy of its depth data.

---

## Q5. Cross-view (ground-to-aerial) fine-grained metric localization, and whether Toronto aerial imagery is usable

### Takeaway
On benchmarks, cross-view methods reach a median of about 1-2 m (VIGOR panoramas, known orientation). Means are 2.4-5 m and degrade sharply for limited-FoV images with unknown orientation: FG² two-step on VIGOR cross-area is 2.40 m median and 5.95 m mean; KITTI cross-area means are 7.5-9.2 m. Casual social-media photos are limited-FoV with unknown heading, so they sit at the hard end. Toronto's own high-resolution orthoimagery is restricted (academic or data-release agreement). Ontario's open imagery (OGL, 16-50 cm) only covers collections Ontario owns, and I could not confirm Toronto coverage. Treat cross-view as a secondary cue, not the primary last-mile method.

### Cited Findings
- VIGOR, known orientation (mean/median m), same-area / cross-area: CCVPE 3.60/1.36 and 4.97/1.68. GGCVT 4.12/1.34 and 5.16/1.40. HC-Net 2.65/1.17 and 3.35/1.59. FG² (CVPR 2025) 1.95/1.08 and 2.41/1.37 — [FG², arXiv 2503.18725](https://arxiv.org/html/2503.18725v1)
- VIGOR, unknown orientation (loc mean/median m): CCVPE same 3.74/1.42, cross 5.41/1.89. FG² one-step cross 10.02/8.14. FG²† two-step same 3.78/1.70, cross 5.95/2.40 (orientation median 2.20°) — [FG²](https://arxiv.org/html/2503.18725v1)
- KITTI (front-facing pinhole, i.e. limited FoV), cross-area: CCVPE mean 9.16 / median 3.33 m. HC-Net 8.47/4.57. FG² 7.45/4.03. Same-area means are 0.75-1.48 m — [FG²](https://arxiv.org/html/2503.18725v1)
- Slice-Loc (2025), VIGOR cross-area: mean 3.00 m, median 1.17 m, <1 m 41.8%, <5 m 87.1%. Filtered: median 1.01 m, <5 m 95.7%. A-contrario validation cut errors >10 m from 5.61% to 0.68% on DReSS. Panorama-focused (vehicle 360° cameras) — [Slice-Loc, arXiv 2508.05369](https://arxiv.org/html/2508.05369v1)
- OrienterNet (CVPR 2023) on KITTI with satellite-refinement baseline: lateral R@1/3/5 m 27.8/59.8/72.9, longitudinal 5.8/16.4/26.5. OrienterNet-OSM did better than the satellite baseline on the same split [older] — [OrienterNet paper](https://arxiv.org/html/2304.02009v1)
- City of Toronto orthoimagery 2009-2024: licence "restricted". 2024 is high-res TIFF, mostly leaf-off, 4-band NIR, available only to current U of T members — [U of T MDL record](https://mdl-data.library.utoronto.ca/items/show/1140); [U of T 2024 note](https://mdl.library.utoronto.ca/node/55596). Earlier City sets are "for personal use for academic, research, and/or teaching purposes" and need a data release agreement — [Waterloo: City of Toronto 2020 orthoimagery](https://uwaterloo.ca/lib-geospatial/collections/aerial-photographs-satellite-and-orthoimagery/image-data-compilation-regional-provincial-national-and/city-toronto-and-greater-toronto-area-gta-orthoimagery/city-toronto-digital-orthoimagery-2020)
- Ontario imagery: Open Government Licence – Ontario, but only where "Ontario owns the intellectual property rights". Collections include SWOOP 2006/2010/2015/2020, COOP 2016/2021, SCOOP 2013/2018/2023, DRAPE. Pixel size 16-50 cm. Toronto coverage is not stated — [data.ontario.ca Open Ontario Imagery](https://data.ontario.ca/en/dataset/open-ontario-imagery)

### Inferences
- Benchmarks assume panoramas (VIGOR) or a car-mounted forward camera with gravity known. Social-media photos are about 50-70° FoV, handheld, unknown heading and often cropped. Expect several-metre medians with a heavy tail, so cross-view alone cannot be trusted for ≤10 m per photo. Where it is legally usable, it fits best as a consistency check (does the PnP pose agree with the aerial-derived pose?).
- With Toronto's orthoimagery restricted, and Esri/Bing tiles generally covered by service terms (not checked here), OSM vectors (OrienterNet, Q6) are the cleaner "overhead" source for this team.

### Gaps
- I found no published cross-view results on handheld, limited-FoV, unknown-heading phone photos.
- I did not check Esri World Imagery or Bing Maps terms for ML use (another researcher may cover ToS). Whether SCOOP/COOP collections cover the City of Toronto with an open licence is unconfirmed.

---

## Q6. OrienterNet and image-to-OSM map matching

### Takeaway
OrienterNet localizes a single image in a 2D OSM raster. On MGL (Mapillary, 12 cities) single-image recall is 15.8% / 47.8% / 59.0% at 1/3/5 m. It needs a location prior within about 32 m (searching a 128 m tile), gravity-rectified input and a known focal length. Weights are CC-BY-NC, and the evaluation config wants about 11 GB VRAM (reduce rotations to fit 8 GB). Useful as a refinement or verification layer when the coarse prior is already within tens of metres. It does not by itself guarantee ≤10 m: about 40% of single images miss 5 m, and the 10 m recall is unreported.

### Cited Findings
- MGL validation, single image (paper): OrienterNet position R@1/3/5 m = 15.78/47.75/58.98, orientation R@1/3/5° = 22.14/52.56/66.32. Map-retrieval baseline 2.02/15.21/24.21. Featuremetric refinement 8.09/26.02/35.31 [older, CVPR 2023] — [OrienterNet arXiv 2304.02009v1](https://arxiv.org/html/2304.02009v1). The repo reports the released model at about 14.37/48.69/61.7 (xy) and 20.95/54.96/70.17 (yaw). Sequential: 29.73/73.25/91.17 — [facebookresearch/OrienterNet](https://github.com/facebookresearch/OrienterNet)
- KITTI Test2 (MGL+KITTI training): lateral R@1/3/5 m 65.91/92.76/96.54, longitudinal 33.07/65.18/75.15, orientation 35.72/77.49/91.51 — [OrienterNet paper](https://arxiv.org/html/2304.02009v1)
- Aria (head-mounted, pedestrian-like), single frame: Seattle 3.39/14.49/23.92 at 1/3/5 m (GPS 1.25/8.82/18.44). Detroit 6.26/32.41/51.76 (GPS 3.96/27.75/51.33). Multi-frame Detroit 17.18/68.77/89.26 — [OrienterNet paper](https://arxiv.org/html/2304.02009v1)
- Requirements: MGL maps are 128×128 m centred within 32 m of the true pose, and the paper notes GPS "can be off by over 20 meters". KITTI tiles are 64×64 m with ±20 m / ±10° priors. "Images are rectified with a homography from known gravity" (roll and tilt zeroed). "Calibration is assumed known", with focal length as an input. BEV grid 32×32 m at 50 cm, depth planes 0.5-128 m. Map raster 50 cm/pixel. Runtime 94 ms per localization on an RTX 2080 — [OrienterNet paper](https://arxiv.org/html/2304.02009v1)
- Licences and compute: "The model implementation and the pre-trained weights follow a CC-BY-NC license". MGL dataset CC-BY-SA. OSM data ODbL. Evaluation "requires a GPU with 11GB of memory". For OOM, reduce `model.num_rotations` from 256 to 128. Training used 3×3090 for 3-4 days — [facebookresearch/OrienterNet](https://github.com/facebookresearch/OrienterNet)
- GeoCalib (same lab) provides the gravity and focal inputs OrienterNet needs (Q8) — [cvg/GeoCalib](https://github.com/cvg/GeoCalib)

### Inferences
- In Toronto's dense downtown, OSM is rich (sidewalks, buildings, crossings), which helps OrienterNet. On residential streets with repetitive structure it will be ambiguous along the street direction (longitudinal recall is much lower than lateral on KITTI).
- Best role: given a prior from VPR or Mapillary retrieval within about 30 m, OrienterNet gives a probability map over position and heading that can (a) cross-check an HLoc/structureless pose and (b) act as a fallback when no reference imagery overlaps. Its output probability volume can be turned into a confidence radius. Non-commercial licence: fine for a hackathon demo, but flag it.

### Gaps
- R@10 m for single images is not reported. I found no newer (2024-2026) OSM-matching method with better single-image MGL numbers in this search; successors may exist but were not checked.

---

## Q7. Object position vs camera position (monocular metric depth, ray casting, snapping to City assets)

### Takeaway
Going from camera to object adds error that grows with distance. Monocular metric depth on urban street imagery has a mean absolute error of about 1.2-1.7 m below 5 m, about 1.4-2 m at 5-10 m (best models), about 3.5-6 m at 10-20 m, and about 11-14 m beyond 20 m. Geolocating actual traffic signs from single images with good poses gave about 4.4 m mean error (UniDepth-B), and pavement damage within 10 m gave about 2.3-2.8 m. So within about 20 m, depth-based object placement fits a 10 m budget. Beyond about 20 m, use multi-view triangulation against the reference images, ray-cast to the SfM points or ground plane, or snap to a known asset (Toronto transit shelters, traffic signals, trees).

### Cited Findings
- MapAnything (2025): depth MAE (m) by distance interval on urban data against LiDAR, total / <5 / 5-10 / 10-20 / >20 m — [arXiv 2509.14839v3](https://arxiv.org/html/2509.14839v3):
  - UniDepth-B (no intrinsics): 5.7 / 1.3 / 1.4 / 5.0 / 11.0 (AbsRel total 0.267)
  - Metric3D-ViT (with intrinsics): 5.6 / 1.7 / 1.5 / 3.5 / 11.4 (AbsRel 0.251)
  - Depth Pro: 13.7 / 2.2 / 3.2 / 13.8 / 26.9
  - Depth Anything (metric, B): 9.0 / 1.5 / 3.9 / 9.7 / 14.4
  - Inference time on RTX 4090: UniD-B 0.9 s, M3D-V 3.2 s, Depth Pro 7.1 s
- Traffic-sign geolocation from single images (average distance to true location): Cyclomedia imagery, UniDepth-B 4.4 m (3.0 m for signs <10 m, 3.7 m at 10-20 m, 5.7 m >20 m), Depth Pro 4.8 m, Metric3D-V 7.3 m, Cyclomedia database 2.3 m. Mapillary imagery: UniDepth-B 5.7 m, Depth Pro 6.0 m, Metric3D-V 6.6 m — [MapAnything](https://arxiv.org/html/2509.14839v3)
- Road pavement damage geolocation (2-10 m from camera): Depth Anything-B 2.34 m, UniDepth-B 2.80 m, Depth Pro 3.86 m, Metric3D-V 4.42 m. Ablation: replacing ground-truth depth with UniDepth estimates adds 2.17 m mean error — [MapAnything](https://arxiv.org/html/2509.14839v3)
- Focal estimation from Depth Pro in that study: true 960 px vs average predicted 1,433 px — [MapAnything](https://arxiv.org/html/2509.14839v3)
- Licences: UniDepth "released under Creatives Common BY-NC 4.0 license" (predicts intrinsics; UniDepthV2 ViT-S/B/L; KITTI d1 98.9 for V2) — [UniDepth](https://github.com/lpiccinelli-eth/UniDepth). Depth Anything V2: "Small model is under the Apache-2.0 license", "Base/Large/Giant models are under the CC-BY-NC-4.0 license" — [Depth-Anything-V2](https://github.com/DepthAnything/Depth-Anything-V2). Depth Pro uses Apple's custom licence for the "Apple Software" (permits use, modification and redistribution with notice; commercial use is not explicitly addressed) — [ml-depth-pro LICENSE](https://raw.githubusercontent.com/apple/ml-depth-pro/main/LICENSE); Depth Pro produces "a 2.25-megapixel depth map in 0.3 seconds on a standard GPU" and estimates focal length — [apple/ml-depth-pro](https://github.com/apple/ml-depth-pro)
- Toronto asset datasets (open.toronto.ca CKAN): Street Furniture – Transit Shelter, Bench, Litter Receptacle, Poster Board, Poster Structure, Publication Structure, Information Pillar/Wayfinding (all "open-government-licence-toronto"). Automated Public Washroom ("License not specified") — [Toronto CKAN street furniture search](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=street%20furniture&rows=20). Shelters are Astral Media assets under the Coordinated Street Furniture Program — [City GIS PRAI Transit Shelter layer](https://gis.toronto.ca/arcgis/rest/services/cot_geospatial2/MapServer/35/iteminfo?f=pjson)
- Traffic Signals Tabular (locations of all City traffic signals), Traffic Control Devices (signals, pedestrian crossovers, beacons) — [Toronto CKAN traffic signals search](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=traffic%20signals&rows=10). Street Tree Data ("License not specified"). The portal notes positions are not accurate enough to verify ownership and some records may be years old. "Topographic Mapping – Physical location of trees" (OGL-Toronto, derived from aerial photography) — [Toronto CKAN tree search](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=tree&rows=10)

### Inferences
- Better than monocular depth once the camera is posed: (1) if the issue's pixels match reference images, triangulate the object directly from multiple views (sub-metre to metre). (2) Ray-cast the object's pixel ray onto the local SfM point cloud or mesh. (3) For road-surface issues such as potholes, flooding and road paint, intersect the ray with the ground plane at camera height h of about 1.4-1.6 m. Calculation: distance error is about (d²/h)·δθ, so with a 1° pitch error, about 1.2 m at d=10 m, about 4.7 m at 20 m and about 10.5 m at 30 m. Ground-plane intersection is therefore reliable only within about 20 m unless pitch is known to better than 1°. PnP-posed cameras usually have sub-degree rotation error (Aachen thresholds 2°). GeoCalib pitch alone has a median of 0.87-1.94°.
- Asset snapping: when the issue class is a damaged shelter, broken signal or fallen tree, snap the estimated object position to the nearest asset of that class within about 15-25 m. Then report the asset ID and its surveyed coordinate (shelter and signal datasets are OGL-Toronto). Tree positions carry the portal's own accuracy caveat. TTC station elevators need station-level asset data (not found here).
- Close-up pothole photos with only asphalt visible cannot be localized visually by any method. They need context (text, other photos, user location) or must be abstained.

### Gaps
- I found no open Toronto dataset of street-light/utility poles or 3D massing in the CKAN queries I ran. The searches were truncated, so they may exist.
- I did not verify the TTC elevator location dataset or Metric3D v2's licence text.
- MapAnything evaluates on Dutch/European imagery. Toronto-specific depth error is unknown.

---

## Q8. Error budget: reference GPS, phone GPS, unknown intrinsics, focal estimation. Is 10 m realistic, and for what share?

### Takeaway
For photos that show distinctive street structure and overlap Mapillary/Street View references, a 10 m budget is realistic. Root-sum-square of about 2-5 m reference georegistration, under 0.5 m query registration and about 1-5 m camera-to-object (objects within about 20 m) comes to about 3-7 m. Failures are dominated by gross errors: no reference overlap, textureless close-ups, wrong coarse region, objects more than 25 m away. Phone GPS (about 7-13 m RMSE urban) would by itself often break 10 m, and social platforms strip EXIF GPS and usually focal length anyway. Focal length can be recovered with GeoCalib (median vFoV error 3-5°) or estimated inside PnP. No source measures the share of social-media civic photos that are localizable. My estimate, clearly an inference: about 30-60% of street-scene photos and close to 0% of close-ups.

### Cited Findings
- Smartphone GPS, urban: iPhone 6 on the University of Georgia campus, RMSE 7.42-12.99 m (GPS-only) across 8 collection periods. Overall about 9.9 m, max 99.7 m. The authors summarize "7-13 m" [older, 2019] — [Merry & Bettinger, PLOS ONE 2019](https://pmc.ncbi.nlm.nih.gov/articles/PMC6638960/)
- Phone static median horizontal error 5.0-8.5 m, max under 30 m outdoors [older, 2011] — [search summary of J. Navigation 2011](https://www.cambridge.org/core/product/E1EE20CD1A301C537BEE8EC66766B0A9). Top phones keep average horizontal RMS under 5 m, and some reach 450 m errors at tunnel exits — [DXOMARK](https://www.dxomark.com/gps-on-your-smartphone-why-youre-not-always-there-when-it-says-youre-there/). Single-frequency GNSS is typically limited to 5-10 m in urban settings — [Sensors and Materials](https://sensors.myu-group.co.jp/sm_pdf/SM2778.pdf). Phone photo geotags: mean errors of 4 m to nearly 50 m depending on device — [Unirioja CIG](https://publicaciones.unirioja.es/ojs/index.php/cig/article/view/6565)
- In the urban canyon test, no epochs achieved fixed ambiguity (no carrier-phase precision) — [Inside GNSS](https://insidegnss.com/what-are-the-actual-performances-of-gnss-positioning-using-smartphone-technology/)
- Social platforms (Facebook, Instagram, X) strip GPS, camera details and timestamps from publicly viewable copies. Evidence is vendor or blog testing, not peer-reviewed — [fast.io](https://fast.io/resources/social-media-photo-metadata-platforms-strip/)
- GeoCalib (ECCV 2024): median errors roll/pitch/vFoV = Stanford2D3D 0.40°/0.93°/3.21°, TartanAir 0.43/1.49/4.90, MegaDepth 0.36/1.94/4.46, LaMAR 0.28/0.87/3.03. The retrained Perspective-Fields ParamNet* scored 1.14/1.94/9.01 on Stanford2D3D and 14.71° vFoV on LaMAR. "Calibrating a single image takes about 100ms". Adding GeoCalib gravity to InLoc localization improves recall (DUC1 at 0.25 m: 43.4 to 44.9) — [GeoCalib arXiv 2409.06704v2](https://arxiv.org/html/2409.06704v2). Code Apache-2.0, weights CC-BY-4.0. Estimates gravity and focal (pinhole) or distortion (simple_radial, needs "distorted" weights). Principal point fixed at image centre — [cvg/GeoCalib](https://github.com/cvg/GeoCalib). The paper notes the principal point "can often be assumed to be at the center of the image unless it has been cropped" — [GeoCalib](https://arxiv.org/html/2409.06704v2)
- Depth Pro's focal estimate was off by about 49% (1,433 vs 960 px) in one urban study — [MapAnything](https://arxiv.org/html/2509.14839v3)
- Mapillary-derived features about 2.0-2.2 m mean error ([SotM 2022](https://2022.stateofthemap.org/sessions/DKLT7X/)). Mapillary GPS deviation 5.5 m on 12 images ([MapAnything](https://arxiv.org/html/2509.14839v3)). Street View intersection RMSE about 0.5-1.2 m horizontal [older] ([ISPRS 2012](https://isprs-annals.copernicus.org/articles/I-4/305/2012/)). Street-View-based VPS typically under 5 m, often about 1 m ([ARCore](https://developers.google.com/ar/reference/java/com/google/ar/core/Config.GeospatialMode)).

### Inferences
- Error budget per photo (successful-registration case, 1-sigma-ish, metres; the combination is my calculation):

  | Component | Typical | Bad case |
  |---|---|---|
  | Reference georegistration (Mapillary computed, multi-sequence) | 2-3 | 5-8 (single sequence, urban-canyon GPS) |
  | Reference georegistration (Street View) | 1-2 | 3-5 |
  | Query pose vs references (HLoc/structureless, correct match) | 0.1-0.5 | 1-3 (few inliers, far features) |
  | Unknown focal (GeoCalib about 3-5° vFoV): mostly absorbed by PnP-with-focal, affects depth scale | <0.5 | 1-2 |
  | Camera to object, multi-view triangulation or ray-cast within 20 m | 0.5-2 | 3-5 |
  | Camera to object, monocular depth 10-20 m | 3.5-5 | 10+ (>20 m) |
  | RSS total (Mapillary refs, object <20 m) | about 3-6 | about 8-12 |

- So ≤10 m is realistic for well-registered photos with objects within about 20 m. The binding constraint is coverage and registrability, not geometry.
- Rough share estimate (inference, no source): photos showing facades, storefronts, intersections or shelters in Mapillary-covered downtown or arterial streets have about 60-80% registration success. Residential or tree-heavy streets, about 30-50%. Pothole or flood close-ups dominated by pavement or water, about 0-10%. Indoor TTC elevators: visual localization against outdoor street imagery does not apply; snap to the station's elevator via text clues instead. Across a realistic civic-issue mix, perhaps 30-50% can be reported within 10 m with honest confidence. The rest should get a larger radius or an abstention.
- Do not use phone GPS from EXIF as the 10 m answer even when present (RMSE about 10 m urban, outliers near 100 m). Use it as a prior.

### Gaps
- I found no study of how many social-media civic-issue photos are localizable at 10 m. A Toronto validation set is needed (see Q9).
- I found no Toronto-specific (downtown canyon) smartphone GPS measurements.

---

## Q9. Outputting and calibrating a radius; abstaining

### Takeaway
Use geometric reliability signals (PnP inlier count and inlier ratio, pose covariance, agreement across references, a-contrario NFA) to predict error. Calibrate them empirically on a Toronto hold-out set, which is free: Mapillary images with computed_geometry act as pseudo-queries. Abstain or widen the radius when signals are weak. Published evidence: consensus/covariance scores reach AUROC about 0.76-0.82 for failure detection, and a-contrario validation cut >10 m errors from 5.61% to 0.68% in cross-view localization.

### Cited Findings
- RIC-Loc failure-detection AUROC (strict failure): joint score 0.822 (7-Scenes), 0.767 (Cambridge), 0.791/0.781 (NAVER B2/B1). Covariance score 0.778/0.764/0.806/0.813. Retrieval-score gap only 0.53-0.55 (near random). Risk-coverage AURC on Cambridge 0.489 vs 0.685 random. Catastrophic-failure AUROC 0.92-0.97 with the covariance score — [RIC-Loc](https://arxiv.org/html/2607.04722v1)
- Slice-Loc a-contrario NFA filtering: >10 m errors 5.61% to 0.68% (lg ε < 0) to 0.24% (lg ε < -1). Filtered VIGOR cross-area <5 m rose from 87.13% to 95.69% — [Slice-Loc](https://arxiv.org/html/2508.05369v1)
- Agarwal et al. refuse to report a localization when the matching rectilinear views are estimated too far away [older] — [ar5iv 1503.04287](https://ar5iv.labs.arxiv.org/html/1503.04287)
- GeoCalib's optimization "estimates uncertainties, which help flag failure cases and benefit downstream applications like visual localization" — [GeoCalib paper (ECCV 2024)](https://www.ecva.net/papers/eccv_2024/papers_ECCV/html/5636_ECCV_2024_paper.php)
- HLoc logs the number of RANSAC inliers per query — [cvg/Hierarchical-Localization](https://github.com/cvg/Hierarchical-Localization)

### Inferences
- Recommended radius model: r = max(r_ref, f(inliers, inlier_ratio, spread of per-reference camera-centre estimates, object distance)) + r_obj(distance). Here r_ref is the reference-registration floor (about 3 m Mapillary, about 2 m Street View) and r_obj comes from the Q7 depth table (about 1.5 m <10 m, about 5 m at 10-20 m). Fit f by isotonic or quantile regression of observed error at the 90th percentile on the hold-out set.
- Hold-out set: sample about 100-300 Mapillary images in target neighbourhoods, ideally phone-captured and pedestrian (on_foot) to resemble social-media photos. Crop them randomly and strip intrinsics to mimic social media. Localize them against references from other sequences. Use computed_geometry as ground truth (itself about 2-3 m uncertain, so calibration is valid to about 3 m).
- Abstain rules (starting points to tune): fewer than about 50 PnP inliers or inlier ratio under about 0.2. Camera-centre estimates from different references disagree by more than about 8 m. The pose falls outside the coarse region or off public right-of-way. The object is more than about 30 m away with no multi-view triangulation. On abstention, report the street segment (centreline) with a 25-50 m radius.

### Gaps
- No public work calibrates radii for crowd-sourced-reference localization of social-media images. The thresholds above are starting heuristics, not published values.

---

## Recommended last-mile pipeline (synthesis)

### Takeaway
Recommendation: real-imagery reference matching against posed Mapillary images (plus Street View if the ToS review allows), with ALIKED+LightGlue (licence-clean, fast), RoMa for hard cases, and local-triangulation/PnP or pose triangulation. GeoCalib supplies focal and gravity. Objects are placed by multi-view triangulation, ray-casting or ground-plane intersection, with monocular depth (UniDepthV2/Metric3D) as a fallback and snapping to Toronto asset datasets. OrienterNet (OSM) serves as verification or fallback. Calibrated radii and abstention come from Q9. Expected outcome: about 3-6 m camera/object error on photos that register, 10 m feasible for a minority-to-half of real civic posts, abstain on the rest.

### Cited Findings
- Structureless local triangulation with RoMa and top-10 references: Aachen Day 84.0/92.8/97.9 at 0.25/0.5/5 m — [Structureless guide](https://arxiv.org/html/2504.17636v1). HLoc structure-based about 87-90% at 0.25 m Day — [same](https://arxiv.org/html/2504.17636v1); [LightGlue supplemental](https://openaccess.thecvf.com/content/ICCV2023/supplemental/Lindenberger_LightGlue_Local_Feature_ICCV_2023_supplemental.pdf)
- Mapillary API exposes computed poses and intrinsics; bbox under 0.01°; 60k entity requests/min — [Mapillary API v4](https://www.mapillary.com/developer/api-documentation)
- GeoCalib Apache-2.0 code / CC-BY-4.0 weights, about 100 ms per image — [cvg/GeoCalib](https://github.com/cvg/GeoCalib); [GeoCalib paper](https://arxiv.org/html/2409.06704v2)
- Licence summary: LightGlue Apache-2.0, ALIKED BSD-3, DISK Apache-2.0, SuperPoint restrictive ([cvg/LightGlue](https://github.com/cvg/LightGlue)). hloc Apache-2.0 ([hloc](https://github.com/cvg/Hierarchical-Localization)). RoMa MIT, DINOv2 Apache-2.0 ([RoMa](https://github.com/Parskatt/RoMa)). MASt3R CC BY-NC-SA 4.0 plus dataset terms ([mast3r](https://github.com/naver/mast3r)). VGGT code commercial-friendly, original weights NC, Commercial checkpoint via application ([vggt](https://github.com/facebookresearch/vggt)). OrienterNet CC-BY-NC ([OrienterNet](https://github.com/facebookresearch/OrienterNet)). UniDepth CC BY-NC 4.0 ([UniDepth](https://github.com/lpiccinelli-eth/UniDepth)). Depth Anything V2 Small Apache-2.0, B/L CC-BY-NC-4.0 ([DAv2](https://github.com/DepthAnything/Depth-Anything-V2)). Depth Pro Apple custom ([LICENSE](https://raw.githubusercontent.com/apple/ml-depth-pro/main/LICENSE)). Mapillary imagery CC BY-SA ([Mapillary help](https://help.mapillary.com/hc/en-us/articles/115001770409-Licenses)). Toronto street furniture OGL-Toronto ([CKAN](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=street%20furniture&rows=20))

### Inferences
Proposed deterministic tool chain (the LLM orchestrator only routes, extracts clues and explains):
1. **Inputs**: photo, coarse region (VPR/LLM, a few hundred metres), LLM-extracted clues (street signs, storefront names, TTC station, issue class), plus a pixel box or mask for the issue (VLM or open-vocabulary detector).
2. **Calibration**: EXIF focal if present; otherwise GeoCalib (focal + gravity + uncertainty). Treat a cropped image's principal point as unknown, and let PnP refine focal.
3. **References**: list Mapillary images within the region (tiles under 0.01°), preferring recent, panoramic and high-quality_score images. Cut perspective crops from panoramas. Optionally add Street View crops (ToS pending). For demo hotspots, pre-build hloc models offline with poses fixed to Mapillary computed poses and triangulate ALIKED+LightGlue points.
4. **Retrieval within region**: top 10-20 references (the other researcher's VPR model).
5. **Matching**: ALIKED (about 2k keypoints) + LightGlue. If inliers are too few, retry with RoMa (or Tiny RoMa) at 560 px.
6. **Pose**: (a) pre-built model: PnP-RANSAC with focal refinement (hloc localize); (b) on the fly: local triangulation from reference pairs + PnP, or E5+1/pose triangulation across 3 or more references. Run a consensus check across references.
7. **Verification (optional)**: OrienterNet on the OSM tile around the pose (num_rotations=128 for 8 GB). Flag disagreements over about 10 m.
8. **Object placement**: multi-view triangulation of the issue pixels in matched references, else ray-cast to SfM points or mesh, else ground-plane intersection (road-surface issues, d < 20 m), else monocular depth (UniDepthV2 or Metric3D-ViT) along the ray. Then snap to the nearest same-class asset (shelter, signal, tree) within about 20 m and return the asset ID.
9. **Uncertainty and abstention**: radius from inliers, consensus spread, reference floor and object distance, calibrated on a Mapillary hold-out set. Abstain or downgrade to street-segment level otherwise.
- Per-photo compute on an RTX 4060 Laptop (estimate): GeoCalib about 0.1-0.3 s, feature extraction for about 20 references about 1-2 s (cacheable), LightGlue about 1 s, RoMa fallback about 5-10 s, PnP under 0.1 s, depth 1-3 s. Mapillary downloads (about 20-50 thumbnails) dominate when not cached. Pre-building tiles for demo neighbourhoods removes this.

### Gaps
- No end-to-end published system reports ≤10 m success rates on social-media photos against crowd-sourced references. Expected performance must be measured on the team's own hold-out set.
- Mapillary coverage and recency in Toronto, and the legality of Street View indexing, are open (the latter is with another researcher).
