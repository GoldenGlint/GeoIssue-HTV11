# Commercial image-geolocation tools and professional OSINT geolocation practice

Research date: 2026-10-17. Scope: how Picarta, GeoSpy/Raven and related tools work and how accurate they are; independent comparisons; expert OSINT workflow; failure modes, confidence presentation and ethics. Per the coordinator's correction, tools and workflows are judged on the evidence, not against any existing GeoIssue design. Items from before 2025 are marked **[older]**. Vendor claims are labelled **(vendor claim)**.

---

## 1. Picarta.ai: claims, model, company, API, pricing, terms, independent tests

### Takeaway
Picarta is a small Italian company (Picarta S.r.l.) that sells a ViT-based global photo geolocator. It returns top-k GPS candidates with confidence scores and can be limited to a country, region or a circle of at most 25 km. Its headline accuracy, **44.8% within 1 km on IM2GPS3k**, comes only from the vendor, and the vendor itself says the comparison may not be fair. The only hands-on independent review found that global searches were "wildly incorrect" but country-restricted searches were "fairly close." The API is **Enterprise-only**, and nothing in the terms grants rights to store or commercially reuse results.

### Cited Findings
**Product and claims**
- The homepage offers three modes: "Search in a Country," "Search Worldwide," and "Focus on Specific Area." It says Picarta "does not rely on EXIF metadata or embedded GPS tags." Results come "with confidence scores," and the site recommends "reviewing the top predictions for the best result." It calls itself "the most accurate and reliable image geolocalization solution" and gives no accuracy numbers on the homepage. It also says "Accuracy depends on the image content and how distinctive its geographical features are." The footer reads "Picarta S.r.l.", "2023 - 2026", "v2.7." **(vendor claim)** — [Picarta homepage](https://picarta.ai/)
- The homepage says the product is "used by OSINT investigators, journalists, law enforcement, photographers, researchers, and travelers." **(vendor claim)** — [Picarta homepage](https://picarta.ai/)
- The free web results are partial ("Upgrade your account to get the full results details"). — [Picarta homepage](https://picarta.ai/)

**Model, benchmark and history**
- "Our AI model is based on vision transformers (ViTs)." Training data size and source are not disclosed. — [Picarta V2 page](https://picarta.ai/picarta-v2)
- "Picarta V2 scores 44.8% accuracy at a 1km distance on the IM2GPS3k dataset." The page compares this with ISNs, GeoDecoder, GeoCLIP and PIGEOTTO but admits the comparison "might not be entirely fair since the experimental conditions differ significantly." No 25 km, 200 km or 750 km figures are given. **(vendor claim)** — [Picarta V2 page](https://picarta.ai/picarta-v2)
- "We estimate with a probability of 70% that our model can predict the GPS location of any outdoor image by looking at the Top 100 predictions." **(vendor claim)** — [Picarta V2 page](https://picarta.ai/picarta-v2)
- Localized search lets users draw a circle on the map. The website shows 10 candidate locations, and the API returns up to 10 with confidence scores. An offline/on-prem model is offered only to corporations and government entities. V1 launched in August 2023, and V2 followed "after a year of dedicated research and development." — [Picarta V2 page](https://picarta.ai/picarta-v2)
- No team members are named and no papers are cited. The company is identified only as Picarta S.r.l., VAT IT01631970520. — [Picarta V2 page](https://picarta.ai/picarta-v2); [Picarta T&C](https://picarta.ai/terms-conditions)

**API**
- Endpoint: `POST https://api.picarta.ai/v1/geolocalize`. "Picarta API is available to Enterprise accounts only." Access requires emailing the company name and use case. A Python SDK exists (`Picarta(api_token)`), with fuller docs at docs.picarta.ai. — [Picarta API page](https://picarta.ai/api)
- Parameters: `IMAGE` (base64 or URL); `TOP_K` (up to 10, default 3); `COUNTRY_CODE` (null means worldwide); `ADMIN1` (state/province, with valid values from `GET /v1/admin1/{country_code}`); `ADMIN2` (county/district, only some countries); `Center_LATITUDE`/`Center_LONGITUDE`; `RADIUS` in km, "max 25km"; `CONTEXT` (free-text hint, "Maximum 500 characters"). The page also lists an EXIF-extraction service and a "Landmarks detection" service marked "coming soon." Response fields and the confidence scale are not documented on that page. — [Picarta API page](https://picarta.ai/api)

**Pricing (as displayed 2026-10-17)**
- Free: 1 search. Wallet: $15.9 for 20 searches, one-time. Subscription: 100 searches/month at $59.9 (monthly) or $49.9 (annual, "Save 17%"). The page does not clearly label which price is which; the mapping is inferred. Enterprise: custom pricing with "Production API," on-premise deployment, priority support and SLA. Rate limits are not stated. — [Picarta pricing](https://picarta.ai/pricing)

**Terms of use**
- Uploaded images are "processed automatically and deleted immediately after analysis." Users grant "a limited license to process them solely to provide our geolocation services." Training on user uploads is not mentioned. — [Picarta T&C](https://picarta.ai/terms-conditions)
- Prohibited: using the service to "harass, stalk, threaten, or harm others"; uploading "images of children under 16 years old" (except for legitimate safety or law-enforcement concerns); and "Use automated tools to scrape or extract data from our services." — [Picarta T&C](https://picarta.ai/terms-conditions)
- The terms do not explicitly cover storing results or using them commercially. The IP clause forbids copying, modifying or distributing "Picarta" content "without our written permission," and it is unclear whether that covers outputs. "Results are estimates and may not always be completely accurate." The service is "as is," and liability is capped at fees paid in the last 12 months. Italian/EU law and Italian courts govern. — [Picarta T&C](https://picarta.ai/terms-conditions)

**Independent or third-party evidence**
- OSINT Newsletter tool review (undated): a known image searched globally returned "wildly incorrect results," while narrowing to a country (they used the whole US) gave results "fairly close to the correct location." Listed cons: it struggles with generic or indoor images, training-data transparency is limited, and results need manual verification. — [OSINT Newsletter tools: Picarta](https://tools.osintnewsletter.com/osint-tools/picarta)
- Competitor-written comparisons (GeoSeer, GeoAxis, GeoInfer) describe Picarta's global accuracy as "Good," say it publishes no head-to-head benchmark, and say it lacks a meter-level street index. These are vendor marketing for rival products, not independent tests. — [GeoSeer vs Picarta (competitor blog)](https://geoseeer.com/blog/geoseer-vs-picarta-ai-photo-geolocation); [GeoAxis roundup (competitor)](https://geoaxis.ai/best-ai-image-location-finders); [GeoInfer roundup (competitor)](https://geoinfer.com/en/blog/best-ai-geolocation-tools-2026)
- Bellingcat's 2025 LLM geolocation tests did not include Picarta. — [Bellingcat, June 2025](https://www.bellingcat.com/resources/how-tos/2025/06/06/have-llms-finally-mastered-geolocation/)

### Inferences
- Picarta's architecture appears to be a "global classifier/retrieval over cells" system (ViT, top-k candidates, a top-100 recall claim). It is built for country, city and km-scale guessing, not 25–100 m street addresses. The top-100 claim implies top-1 accuracy is well below 70%.
- The 44.8% @1 km IM2GPS3k figure would be several times higher than the published academic results the vendor compares against. From background knowledge not re-verified in this session, GeoCLIP and PIGEOTTO score roughly 10–15% at 1 km on IM2GPS3k. Without a disclosed protocol, the result could reflect train/test overlap (IM2GPS3k images are public Flickr photos). Treat it as unverified.
- The useful lesson from Picarta is the interface design, not the accuracy claim. Hard geographic constraints (country, ADMIN1, center plus radius up to 25 km), a free-text `CONTEXT` hint, and top-k outputs with scores are a sensible contract for any geolocator. A Toronto-only system can apply the equivalent constraint much more tightly (the city boundary) than Picarta's 25 km circle.
- For a hackathon, Picarta is impractical as a production component. The API is Enterprise-only, automated use without an API is prohibited, the terms are silent on reusing results, and per-search cost is about $0.50–0.80 on consumer plans. At most it could serve as a manual baseline for a handful of test images, which would require an account and image uploads (out of scope for this research).

### Gaps
- I found no independent quantitative benchmark of Picarta: no Bellingcat test, no academic replication, no city-scale test.
- A search snippet mentioned a Picarta changelog stating **30.4%** @1 km on IM2GPS3k for V2, which conflicts with 44.8%. I could not find that changelog URL, so the discrepancy is unresolved.
- Founders, team size, funding, training-data source, and API response schema/confidence calibration were not found. docs.picarta.ai was not fetched.
- Rate limits are not published anywhere I found.

---

## 2. GeoSpy / Graylark (now "Raven") and other notable tools

### Takeaway
GeoSpy (Graylark Technologies, founded by Daniel Heinen and his brothers) began as a GeoGuessr-inspired global geolocator. After 404 Media reported in January 2025 that users were asking for help stalking women, public access was closed. It has since been rebranded **Raven** and is sold only to law enforcement, government and enterprise. Its "SuperBolt" street-level/"meter-level" capability, as described by third parties, is **visual place recognition (embedding retrieval) against a ~46M street-level image index, plus dense geotagged data for specific cities**. No independent accuracy numbers exist, and Miami-Dade police say it has produced no breakthroughs. Open tools (Bellingcat OSM Search, ShadowFinder, Text-to-Overpass research such as SPOT) show the deterministic half of expert technique: constraint search over map data plus physics.

### Cited Findings
**GeoSpy/Raven history and controversy**
- 404 Media (Jan 20, 2025): GeoSpy was "trained on millions of images" and uses soil, architecture, and the distance between buildings ("GeoGuesser at scale"). It was marketed to law enforcement and government. Some users asked for help stalking specific women, and the founder "aggressively pushed back." Public access closed "after 404 Media contacted him for comment." — [404 Media, Jan 2025](https://www.404media.co/the-powerful-ai-tool-that-cops-or-stalkers-can-use-to-geolocate-photos-in-seconds/)
- heise (Jan 22, 2025): the company said GeoSpy locates the city or area "relatively precisely" but not the street or house number. It uses vegetation, building style, building spacing, and road surface, and is "especially good" in the USA. 404 Media had tested it on clear smartphone photos and low-resolution CCTV stills before access closed. — [heise](https://www.heise.de/en/news/Graylark-closes-public-access-to-AI-tool-for-geolocation-10252293.html)
- EFF's Cooper Quintin: "It's one thing for the police to apply this to a photo that is evidence in the investigation of a serious crime. It's quite another thing to use it en masse to create a geolocation database or gather information on people who are not involved in suspected illegal activity." He also warned that bystanders could be arrested on inaccurate geolocations. — [heise](https://www.heise.de/en/news/Graylark-closes-public-access-to-AI-tool-for-geolocation-10252293.html)
- Police purchases (404 Media via GIGAZINE, Feb 13, 2026): Miami-Dade Sheriff's Office bought a $38,000 custom county model, two annual licences of 350 searches each at $10,000, and 150,000 extra searches for $37,500. LAPD Robbery-Homicide reportedly uses it. Graylark claims locations "down to the meter," using a global dataset plus "high-density geotagged data for specific cities and states." An internal MDSO email: "GeoSpy output should be treated as a clue and should be corroborated using standard investigative techniques." MDSO said use was "limited and largely exploratory" with no significant breakthroughs or arrests. — [GIGAZINE summarizing 404 Media](https://gigazine.net/gsc_news/en/20260213-cops-buying-geospy-ai-geolocates-photos)
- Graylark's site now presents Raven ("Formerly GeoSpy") as a "visual investigation workspace" that "turns low-context imagery into ranked leads for human review." Modules: Find Region, Find Street, Find Property, Short-Term Rental ID, Identify Car, Verify Image, Live Intelligence. It is available "to qualified law enforcement agencies, enterprise users, and government entities." No accuracy figures or pricing are given, and the case study is a "Dramatized recreation." — [Graylark](https://graylark.com/)
- 404 Media (Oct 12, 2026): Raven lets police identify "what specific home" a photo was taken in, including from interiors, and "is clearly pulling data from sites like Zillow and Airbnb." The article is mostly paywalled. — [404 Media, Oct 2026](https://www.404media.co/ai-company-lets-cops-pinpoint-specific-houses-based-on-a-single-interior-photo/)
- Malwarebytes (Oct 15, 2026): Raven is sold only to businesses, government and law enforcement. Third-party consumer sites using the "GeoSpy" name are **not affiliated** with Graylark. "Short-Term Rental ID" searches millions of rental listings. "Find Property" works on exteriors and, in supported cities, interiors. Heinen raised $10.7M in August 2026 and has experimented with dashcam footage. Airbnb says it has no relationship with Graylark, and Zillow says scraping violates its terms. — [Malwarebytes](https://www.malwarebytes.com/it/blog/privacy/2026/10/raven-ai-lets-cops-find-your-home-from-a-photo-taken-inside)
- Sources conflict on when the Raven rename happened (one says April 2026, another snippet said May 11). — [maxintel.org](https://maxintel.org/graylark-raven-police-ai-geolocation-2026.html) (unverified secondary)

**SuperBolt (street-level matching)**
- Third-party descriptions say SuperBolt converts an upload into an embedding and compares it with an index of **46 million+ street-level images**, with claims of accuracy "as close as 1 meter" in some matching scenarios or "within a few meters." These are secondary marketing and aggregator pages; Graylark's own SuperBolt documentation was not found. **(vendor claim via secondary sources)** — [Hiverlab](https://hiverlab.com/geospy-ai-top-5-reasons-enterprise-must-try); [Pasquale Pillitteri](https://pasqualepillitteri.it/en/news/423/geospy-ai-photo-geolocation)
- Search results also surface a "geospys.com" site publishing GeoGuessr-prompt tests. Given Malwarebytes' note that GeoSpy-named consumer sites are unaffiliated, treat such sites as knock-offs. — [geospys.com](https://geospys.com/blog/chatgpt-geoguessr-prompt); [Malwarebytes](https://www.malwarebytes.com/it/blog/privacy/2026/10/raven-ai-lets-cops-find-your-home-from-a-photo-taken-inside)

**Bellingcat OpenStreetMap Search [older: May 2023]**
- The tool is "a dramatically simplified version of the Overpass query language tool." Users pick OSM feature presets or custom `key=value` tags and a "Maximum distance between features" (default 100 m), then draw a search region. It returns locations where all features co-occur. Results (max 100) open in Google Maps or Street View and export to CSV/KML. The first filter sets granularity. Large regions time out, especially in densely mapped areas. Bellingcat's OSM extract was from April 2023 and is updated twice a year. Login needs a Google account and queries are logged. — [Bellingcat OSM Search how-to](https://bellingcat.com/resources/how-tos/2023/05/08/finding-geolocation-leads-with-bellingcats-openstreetmap-search-tool)
- Worked example: fountain + tram tracks + convenience store within 100 m across French-speaking Belgium gave 15 results in about 40 s. Result #8 was confirmed by Street View even though the store name had changed. Advice: choose distinctive, likely-mapped features (rail, wind turbines, plazas), not trees; combine features; check tags in the OSM wiki; check OSM node density; treat hits as leads and verify. — [Bellingcat OSM Search how-to](https://bellingcat.com/resources/how-tos/2023/05/08/finding-geolocation-leads-with-bellingcats-openstreetmap-search-tool)

**Natural-language-to-OSM research**
- SPOT (DW Innovation, ACL 2025 demo) is an open-source natural-language interface that turns scene descriptions into structured OSM object configurations using fine-tuned LLMs, explicitly for journalistic verification and geolocation. — [SPOT arXiv](https://arxiv.org/html/2506.13188v1)
- Text-to-OverpassQL (TACL 2024) introduced the OverpassNL dataset (8,352 NL-to-Overpass pairs) and the OverpassT5 model. LLM-generated Overpass queries suffer from hallucination, "leading to the generation of erroneous and non-executable outputs." — [Text-to-OverpassQL](https://arxiv.org/pdf/2308.16060); [TACL](https://transacl.org/index.php/tacl/article/view/5843)

**ShadowFinder and sun/shadow tools [Aug 2024]**
- Bellingcat ShadowFinder takes an object's height, its shadow length and a date/time (or a sun-altitude angle) and maps the band of Earth locations where that shadow could occur. It ships as a Python library, CLI and Colab notebook (v0.7.0 on PyPI). It replaces manual SunCalc checks for global search. — [Bellingcat ShadowFinder](https://www.bellingcat.com/resources/2024/08/22/shadow-geolocate-geolocation-locate-image-tool-open-source-bellingcat-measure); [PyPI ShadowFinder](https://pypi.org/project/ShadowFinder)
- Bellingcat also has a sun-and-shadows geolocation guide. **[older: 2020]** — [Bellingcat 2020](https://www.bellingcat.com/resources/2020/12/03/using-the-sun-and-the-shadows-for-geolocation/)

**Research systems and GeoGuessr AI [older: 2023]**
- Stanford's PIGEON (4-image Street View panoramas) reportedly got the country right about 92% of the time (PetaPixel says 95%). Over 40% of guesses fell within about 40 km. It beat GeoGuessr pro Trevor Rainbolt in 6 consecutive matches. The single-image PIGEOTTO was trained on about 4M Flickr/Wikipedia images. Neither model is publicly released. These figures come from secondary coverage. — [Windows Central](https://windowscentral.com/software-apps/ai-model-can-pinpoint-your-exact-location-from-a-photo); [PetaPixel](https://petapixel.com/2023/12/28/this-ai-can-geolocate-photos-faster-and-more-accurately-than-any-human); [The Decoder](https://the-decoder.com/this-ai-knows-where-you-took-which-photo/)
- Jay et al. (arXiv 2502.14412, Feb 2025): on a Street View benchmark, foundation models reach median errors under 300 km. VLM agents with supplemental tools (more camera headings and pitches from the same spot, and Google Lens reverse search) cut distance error by up to 30.6%. — [arXiv abstract](https://arxiv.org/abs/2502.14412); [arXiv HTML](https://arxiv.org/html/2502.14412v1)
- GeoVista (arXiv 2511.15705, Nov 2025) combines image zoom with web search under hierarchical RL and argues that zoom-only agents "rely solely on internal knowledge." GeoBrowse (arXiv 2604.04017, 2026) uses an agent with 5 image tools and 4 retrieval tools and reports that no-tool, search-only or image-only setups are insufficient. Both come from abstracts and summaries only. — [GeoVista summary](https://hyper.ai/fr/papers/2511.15705); [GeoBrowse](https://www.alphaxiv.org/abs/2604.04017.md)
- GeoFT (ICLR 2025 workshop) fine-tunes foundation models for automated OSINT geolocation in Russia/Ukraine on street-level imagery and frames manual verification as hard to scale. — [GeoFT](https://mlanthology.org/iclrw/2025/sun2025iclrw-geoft)

**Google Lens and Google AI Mode**
- In Bellingcat's 2025 test, Google Lens (the first 10 "visual match" results) did well on touristic and scenic places but poorly in cities, where it "tended to fixate on larger, similar-looking structures." — [Bellingcat, June 2025](https://www.bellingcat.com/resources/how-tos/2025/06/06/have-llms-finally-mastered-geolocation/)
- Google AI Mode was the best tool overall in Bellingcat's August 2025 retest. At that time it was available only in India, the UK and the US. — [Bellingcat, Aug 2025](https://bellingcat.com/resources/2025/08/14/llms-vs-geolocation-gpt-5-performs-worse-than-other-ai-models/)

### Inferences
- Every credible "street/meter-level" claim (GeoSpy SuperBolt, Raven Find Street/Property, MDSO's "high-density geotagged data for specific cities") rests on **retrieval against a dense, geotagged, street-level image index of the target area**, not on a model "knowing" the world. Global classifiers (Picarta, PIGEON/PIGEOTTO) operate at km to country scale. For a single-city 25–100 m target, the evidence favours building or using a city-scale street-level index (Street View, Mapillary, KartaView, city open data) over relying on any global model or LLM.
- Raven's own framing ("ranked leads for human review") and MDSO's "treat as a clue" show that even the most aggressive commercial product presents its output as candidate leads, not answers.
- Bellingcat OSM Search, SPOT and Text-to-Overpass point to an automatable pattern: an LLM or VLM extracts mappable objects and spatial relations, then a deterministic engine (Overpass/PostGIS over a local OSM extract) finds co-occurrence sites. Generated queries must be validated against a known tag vocabulary because of the documented hallucination problem.
- No GeoSpy/Raven access is possible for a hackathon team. It is restricted, priced per search, and ethically fraught.

### Gaps
- No primary Graylark documentation of SuperBolt, its index sources, or any benchmark was found. The 46M-image figure and the meter-level claims are unverified.
- I found no independent accuracy test of GeoSpy/Raven, beyond 404 Media's anecdotal pre-closure tests and MDSO's "no breakthroughs" statement.
- Picarta's and GeoSpy's training-data provenance and licensing are unknown.
- Whether Google AI Mode is now available in Canada was not checked.
- Not researched in depth: GeoGuessr "meta" clue databases (e.g., Plonkit) and other commercial GeoINT startups beyond the competitor blogs (GeoSeer, GeoAxis, GeoInfer).

---

## 3. Independent comparisons (Bellingcat and others)

### Takeaway
The only rigorous independent comparisons are Bellingcat's two 2025 LLM trials. In June 2025 only OpenAI's o3, o4-mini and o4-mini-high beat Google Lens; in the August 2025 retest Google AI Mode was best. Claude models were the most conservative and lagged. Every model hallucinated at some point. No independent test pits Picarta or GeoSpy against LLMs, and I found no 2026 Bellingcat round.

### Cited Findings
- **Bellingcat, June 6, 2025:** 25 unpublished, metadata-stripped photos from every continent; 500 tests across about 20 model variants (the article's list has 19). The prompt was "Where was this photo taken?", followed by "There is no supporting information. Use this photo alone" if the model asked for context. Scoring was 0–10, where 10 means a correct neighbourhood, trail or landmark. Google Lens was the control. — [Bellingcat, June 2025](https://www.bellingcat.com/resources/how-tos/2025/06/06/have-llms-finally-mastered-geolocation/)
  - Only o3, o4-mini and o4-mini-high beat Google Lens, "though not by a large margin." Gemini scored below Lens and Grok overall. The best Claude and Mistral models "lagged well behind," with Opus 4 about level with Gemini 2.5 Pro. Claude was "the most conservative" and extended thinking made Sonnet more cautious. On average, deep-research and extended-thinking modes made Claude and ChatGPT worse; only Grok DeeperSearch and Gemini Deep Research improved. ChatGPT Deep Research took about 13 min and landed about 50 km off, while o4-mini-high took 39 s and was 15 km closer. — [Bellingcat, June 2025](https://www.bellingcat.com/resources/how-tos/2025/06/06/have-llms-finally-mastered-geolocation/)
  - Per-model numeric scores appear only in a heat-map image, not in the text. — [Bellingcat, June 2025](https://www.bellingcat.com/resources/how-tos/2025/06/06/have-llms-finally-mastered-geolocation/)
- **Bellingcat, Aug 14, 2025:** retest with 24 models (5 previously published photos excluded, implying 20). It added Google AI Mode, GPT-5, GPT-5 Thinking and Grok 4, and ran GPT-5 Pro on the 5 hardest photos. AI Mode was "the most capable geolocation tool overall" and the only one to identify Noordwijk. GPT-5, even in Thinking and Pro modes, was "a considerable downgrade" from o4-mini-high, and GPT-5 Pro (€200/month) was no more accurate. Grok 4 was marginally better than Grok 3 but still behind older Gemini and GPT models. The authors warn that progress "is not guaranteed" and may "plateau or even worsen." — [Bellingcat, Aug 2025](https://bellingcat.com/resources/2025/08/14/llms-vs-geolocation-gpt-5-performs-worse-than-other-ai-models/) (republished by [GIJN](https://gijn.org/stories/updated-test-24-llms-ai-geolocation/))
- Bellingcat's earlier chatbot geolocation test is **[older: July 2023]**. — [Bellingcat 2023](https://bellingcat.com/resources/2023/07/14/can-ai-chatbots-be-used-for-geolocation/)
- GeoSpy's founder publicly framed Bellingcat's results as showing "LLMs haven't mastered geolocation—and probably never will." He has a commercial interest. — [Daniel Heinen on X](https://x.com/heinenbros/status/1931147579540246830)
- An informal Medium test with only 5 photos ranked Gemini 3 (Thinking) top and found Claude Sonnet 4.5 often named the wrong country. The sample is too small to rely on. — [CyberRaya, Medium](https://medium.com/@CyberRaya/geolocation-detection-with-llms-57ff0ee8e133)
- The 2026 "tested & ranked" comparisons of Picarta, GeoSpy and others found in search come from competing vendors (GeoSeer, GeoAxis, GeoInfer), not neutral testers. — [GeoSeer vs GeoSpy](https://geoseeer.com/blog/geoseer-vs-geospy-raven-ai-geolocation); [GeoAxis](https://geoaxis.ai/best-ai-image-location-finders); [GeoInfer](https://geoinfer.com/en/blog/best-ai-geolocation-tools-2026)

### Inferences
- Bellingcat's scoring rewards a correct neighbourhood or landmark. That is roughly 0.5–5 km precision, far coarser than 25–100 m, so even the "winners" are not shown to work at street-address precision.
- Model rankings swing between versions (o4-mini-high beat GPT-5). A system that hard-codes one LLM as its locator is fragile. LLMs fit best as replaceable clue extractors, and the team should run its own small Toronto test set to choose a model rather than rely on 2025 rankings.
- Claude's conservatism is a double-edged result. Low specificity scores poorly on Bellingcat's rubric, but the same caution may lower confident-wrong answers, which matter more for a civic-reporting pipeline. This should be measured, not assumed.
- Bellingcat's test was "photo only." Real social posts carry captions, hashtags and replies, and Bellingcat itself recommends providing context. See section 5 for the risks of over-trusting context.

### Gaps
- I found no independent head-to-head test of Picarta vs GeoSpy vs frontier LLMs.
- No 2026 Bellingcat round was found, so 2026 models (Gemini 3.x, Claude 4.5+/5.x, GPT-5.x) lack an independent, comparable evaluation in this research.
- No city-scale (single metro area, 25–100 m) independent benchmark of any commercial tool was found.

---

## 4. Expert OSINT geolocation workflow and which steps can be automated

### Takeaway
Practitioners use a funnel. First they gather context (source post, metadata, reverse image search). Then they extract and rank clues: text and signage first, then distinctive fixed structures, then generic environment. They narrow the area with map-data constraint queries (Overpass/OSM Search), sun/shadow geometry, distances and terrain. Finally they verify candidates in street-level and satellite imagery, requiring several independent fixed features to match. Clue extraction, OSM constraint search and candidate retrieval are highly automatable. Final verification can be partly automated but is where experts insist on rigour.

### Cited Findings
**Overall funnel and mindset**
- Informal practitioner guides describe a consistent pattern. Gather context and the original source first (metadata, reverse image search; "the clue doesn't come from the image alone, but from the original online source"). Then work through foreground, background and map markings, start broad and narrow down, and refine hypotheses until one location fits. — [Practitioner guide (Medium)](https://medium.com/@refkialfarizi/a-guide-to-osint-geolocation-87d4438830b3); [Practitioner guide (Medium)](https://fidelyafr.medium.com/osint-a-practical-guide-to-geolocation-6242c91653c4) (informal sources)
- Benjamin Strick's casework follows the same order. In the Kumbo (Cameroon) thread he goes from direct visual clues (a tower structure, red roof, concrete square) to a searchable text sign, then to YouTube searches for similar footage. In the Cameroon killings video investigation, analysis began with a mountain range and building cluster in the background, used a tip to narrow to one town, and confirmed against satellite imagery. **[older: 2018–2019 casework]** — [Strick thread (Threadreader)](https://threadreaderapp.com/thread/1063491316812779521.html); [Poynter](https://poynter.org/?p=490105)
- Quiztime players look for store logos, distant towers and shadow angles **[older: 2019]**. Sector035 is noted for chronolocation from sun and shadows **[older: 2021]**. A Quiztime write-up's lesson after a long wrong track: "Assume Nothing / Believe No One / Challenge Everything." — [GIJN on Quiztime](https://gijn.org/stories/the-daily-quiz-that-teaches-journalists-how-to-geolocate-images/); [Cylab on Sector035 quiz](https://cylab.be/blog/128/osint-quiz); [Quiztime Medium](https://medium.com/quiztime/lots-to-learn-by-solving-and-not-solving-quiztime-riddles-cff4320e8a1c)
- Bellingcat's 2025 advice on AI in this workflow: use LLMs "to spot the details that Google Lens or they themselves might miss," but they are "no silver bullet." Exploit multilingual search and small clues (vegetation, architecture, signage, partial text), provide real context, use clean sessions to avoid account-memory bias, and verify everything. — [Bellingcat, June 2025](https://www.bellingcat.com/resources/how-tos/2025/06/06/have-llms-finally-mastered-geolocation/)

**Narrowing the area**
- OSM tag queries via Overpass Turbo: in one worked example, querying a restaurant chain near tram lines in St Petersburg cut thousands of points to a few candidates. Generated queries can be wrong or return nothing, so tags should be checked on the OSM wiki. — [Practitioner guides (Medium, search summary)](https://medium.com/@anugrahendra1/s-53eca46812f6) (informal)
- Bellingcat OSM Search: feature co-occurrence within a distance threshold, with distinctive, likely-mapped features preferred (see section 2). — [Bellingcat OSM Search how-to](https://bellingcat.com/resources/how-tos/2023/05/08/finding-geolocation-leads-with-bellingcats-openstreetmap-search-tool)
- Distance triangulation: distances on a road sign define circles whose intersection is the candidate zone. — [Practitioner guide (Medium)](https://medium.com/@refkialfarizi/a-guide-to-osint-geolocation-87d4438830b3) (informal)
- Sun and shadows: ShadowFinder and SunCalc constrain latitude/longitude bands or time of day from shadow geometry. — [Bellingcat ShadowFinder](https://www.bellingcat.com/resources/2024/08/22/shadow-geolocate-geolocation-locate-image-tool-open-source-bellingcat-measure)

**Verification**
- Street View is the confirmation step, and practitioners advise matching **at least three independent features** before accepting a location. Satellite and Google Earth 3D views are the fallback where Street View is missing. — [Practitioner guides (Medium)](https://medium.com/@refkialfarizi/a-guide-to-osint-geolocation-87d4438830b3) (informal)
- A single match can be coincidental, so a location needs several independent fixed features that agree, such as a building corner, a road junction and a pole position. Mapillary and KartaView have ground-level imagery "down roads Google never reached," and matching means stepping frame by frame until the view lines up. — [Secjuice: How to geolocate a photo](https://secjuice.com/how-to-geolocate-a-photo/)
- Mapillary imagery is often more recent than Google's, and KartaView skews toward dashcam-style views. — [maxintel geo resources](https://maxintel.org/geo.html)
- Bellingcat's Belgium example confirmed via Street View that the tram-curve and fountain geometry matched even though the shop name had changed. Fixed geometry is a better verifier than signage. — [Bellingcat OSM Search how-to](https://bellingcat.com/resources/how-tos/2023/05/08/finding-geolocation-leads-with-bellingcats-openstreetmap-search-tool)
- GeoConfirmed is a volunteer project that publishes geolocation breakdowns on X and Bluesky and keeps maps of verified items. Its written methodology was not found. — [beSpacific on GeoConfirmed](https://www.bespacific.com/?p=121997)

**Automation evidence**
- Tool-augmented VLM agents that request more views and use reverse image search cut distance error by up to 30.6% compared with single-shot models. — [Jay et al. 2025](https://arxiv.org/abs/2502.14412)
- Agentic benchmarks (GeoVista 2025, GeoBrowse 2026) report that combining image-inspection tools with web/knowledge retrieval beats either alone. — [GeoVista summary](https://hyper.ai/fr/papers/2511.15705); [GeoBrowse](https://www.alphaxiv.org/abs/2604.04017.md)
- Fine-tuned NL-to-OSM systems (SPOT) automate the "describe the scene, find matching map configurations" step. — [SPOT](https://arxiv.org/html/2506.13188v1)

### Inferences
Expert workflow mapped to automation potential:

| Expert step | What experts do | How automatable | Suggested component |
|---|---|---|---|
| 0. Provenance/context | Read post text, account, replies, other posts; check EXIF; reverse image search | High (text), medium (reverse search APIs, platform ToS) | LLM reads caption and thread; EXIF parse; treat as hints, not truth (sec. 5) |
| 1. Clue extraction & ranking | List text, signs, logos, street names, transit, distinctive structures, then generic environment | High | VLM plus OCR, outputting structured clues with a specificity rank |
| 2. Direct resolution | Search/geocode street names, business names, addresses | High | Deterministic geocoder/POI lookup on extracted text (fastest route to <100 m) |
| 3. Constraint narrowing | Overpass/OSM Search feature co-occurrence within distance thresholds | High | LLM emits structured feature list; deterministic engine over a local OSM extract with validated tag vocabulary |
| 4. Physics constraints | Shadows/SunCalc, terrain, skyline | Medium-low for social posts (time often uncertain, object heights unknown) | Optional; post timestamp gives only an upper bound on capture time |
| 5. Candidate retrieval | Step through Street View/Mapillary near candidates | High | Image-embedding retrieval against street-level imagery of candidate areas (the SuperBolt-style technique) |
| 6. Verification | Match ≥3 independent fixed features (corners, junctions, poles, rooflines) | Medium | Local feature matching/geometric verification plus VLM side-by-side check; avoid asking an LLM "is it here?" alone (sec. 5) |
| 7. Decision & uncertainty | Accept, reject or leave unresolved; document reasoning | Medium | Calibrated score, top-k candidates, explicit "unresolved" outcome; human review for low-confidence items |

- For the stated 25–100 m goal, steps 2 (text geocoding), 3 (OSM constraints) and 5–6 (street-level retrieval and geometric verification) carry most of the precision. LLM world-knowledge guessing (the Bellingcat-tested skill) mainly helps step 1 and coarse priors, and inside a single known city the coarse prior is already given.
- Experts prefer fixed geometry (road layout, building corners, poles) over transient features (shop names, temporary installations, construction). Civic-issue photos are often close-ups of transient damage (a pothole, graffiti, garbage), so clues will often sit in the photo's background. An automated system should explicitly look for background fixed features and accept "unresolvable" for tight close-ups.

### Gaps
- I found no authoritative, written Bellingcat or GeoConfirmed end-to-end methodology for 2025–2026. Several workflow points come from informal practitioner guides (Medium, Secjuice).
- The GIJN "10 tips" article based on Benjamin Strick's talk returned HTTP 403 and could not be read.
- GeoGuessr-pro techniques (e.g., Plonkit-style "meta" for bollards, poles, road lines) were not researched. They are mostly country-scale and of limited value inside one city.
- No published evaluation of automated multi-feature street-level verification for social-media photos at city scale was found.

---

## 5. Failure modes, overconfidence, confidence presentation and ethics

### Takeaway
Documented failure modes include confident hallucination, temporary or changed scenes, misread scripts, inference from irrelevant metadata (photographer names, account history), and, most relevant for verification, **VLMs falsely confirming claimed locations just outside the true area, with high confidence**. Commercial tools present uncertainty only as ranked top-k lists or "leads" plus uncalibrated scores, and law-enforcement users are told to treat outputs as clues. The ethical line drawn by critics and by vendor terms is between locating *places/evidence* and locating *people and homes*.

### Cited Findings
**Failure modes and overconfidence**
- "All the models, at some point, returned answers that were entirely wrong." ChatGPT was more confident, gave better answers and hallucinated more. Grok placed a Swiss field in the Netherlands, apparently from the photographer's name. Gemini 2.5 Pro misread a storefront as Thai script and suggested Bangkok for a Singapore alley. Models confused a beach with a temporary Ferris wheel with a more photographed beach. Models struggled to produce accurate coordinates. ChatGPT o4-mini referenced earlier conversations, and Grok drew on the user's Twitter profile. — [Bellingcat, June 2025](https://www.bellingcat.com/resources/how-tos/2025/06/06/have-llms-finally-mastered-geolocation/)
- "Even AI Mode sometimes confidently points to the wrong location." — [Bellingcat, Aug 2025](https://bellingcat.com/resources/2025/08/14/llms-vs-geolocation-gpt-5-performs-worse-than-other-ai-models/)
- **GeoContext (arXiv 2609.05761, Sept 4, 2026; Zhang & Wang):** 5 VLMs, 109 sites in 30 cities, 21,933 hint responses and 6,270 verification responses. Two failure modes:
  - (a) "Flat reliance" on user-provided location hints. Hint repetition barely changes with hint quality (1.5 percentage points across referenceability tiers, under 3 across distance bands), while error grows as the hint moves away from the true location.
  - (b) "False confirmation." On a "taken within 150 m of the claimed place?" task, no model reaches d′ = 1 for decoys just beyond 150 m, and **83.8% of false acceptances carry confidence ≥ 0.8**.
  - The authors release the benchmark and scoring code. — [GeoContext arXiv](https://arxiv.org/abs/2609.05761)
- LLM-generated Overpass queries hallucinate and can be non-executable. — [Text-to-OverpassQL](https://arxiv.org/pdf/2308.16060)
- OSM data is incomplete and only as current as its last edit. Bellingcat OSM Search caps results at 100 and times out on large dense regions. — [Bellingcat OSM Search how-to](https://bellingcat.com/resources/how-tos/2023/05/08/finding-geolocation-leads-with-bellingcats-openstreetmap-search-tool)
- Google Lens fixates on larger, similar-looking structures in urban scenes. — [Bellingcat, June 2025](https://www.bellingcat.com/resources/how-tos/2025/06/06/have-llms-finally-mastered-geolocation/)

**How commercial tools present confidence**
- Picarta returns top-k (default 3, max 10) coordinates with a "confidence score" whose scale or calibration is not documented. It advises reviewing the top predictions and markets a 70% top-100 recall. — [Picarta homepage](https://picarta.ai/); [Picarta API](https://picarta.ai/api); [Picarta V2](https://picarta.ai/picarta-v2)
- Picarta's terms say "Results are estimates and may not always be completely accurate." — [Picarta T&C](https://picarta.ai/terms-conditions)
- Raven presents "ranked leads for human review" with no published scores. — [Graylark](https://graylark.com/)
- The MDSO internal email says output "should be treated as a clue and should be corroborated." — [GIGAZINE / 404 Media](https://gigazine.net/gsc_news/en/20260213-cops-buying-geospy-ai-geolocates-photos)
- Malwarebytes: any Raven-suggested location must still be verified with other evidence. — [Malwarebytes](https://www.malwarebytes.com/it/blog/privacy/2026/10/raven-ai-lets-cops-find-your-home-from-a-photo-taken-inside)

**Ethics: people vs places**
- GeoSpy users requested help stalking specific women, and public access was closed. — [404 Media, Jan 2025](https://www.404media.co/the-powerful-ai-tool-that-cops-or-stalkers-can-use-to-geolocate-photos-in-seconds/)
- EFF warns against mass geolocation databases and against acting on inaccurate geolocations. — [heise](https://www.heise.de/en/news/Graylark-closes-public-access-to-AI-tool-for-geolocation-10252293.html)
- Raven now identifies specific homes and rentals from interior photos. Airbnb and Zillow disclaim any relationship, and Zillow says scraping violates its terms. — [404 Media, Oct 2026](https://www.404media.co/ai-company-lets-cops-pinpoint-specific-houses-based-on-a-single-interior-photo/); [Malwarebytes](https://www.malwarebytes.com/it/blog/privacy/2026/10/raven-ai-lets-cops-find-your-home-from-a-photo-taken-inside)
- In April 2025, a viral "reverse location search" trend used ChatGPT o3 and o4-mini (crop, rotate, zoom reasoning) and raised doxxing concerns. Coverage reports OpenAI saying it has safeguards against identifying private individuals or sensitive locations, but these were not independently described. — [TechSpot](https://www.techspot.com/community/topics/chatgpt-gets-scarily-good-at-guessing-photo-locations-sparking-doxxing-concerns.291870/); [TechRadar](https://www.techradar.com/computing/cyber-security/beware-another-chatgpt-trend-threatens-your-privacy-heres-how-to-stay-safe); [Cybernews](https://cybernews.com/cybercrime/chatgpt-turning-casual-snapshots-privacy-nightmares/)
- Picarta prohibits use to "harass, stalk, threaten, or harm others" and uploading images of children under 16. — [Picarta T&C](https://picarta.ai/terms-conditions)
- Jay et al. frame accessible VLM geolocation as having "greater implications for online privacy." — [Jay et al. 2025](https://arxiv.org/abs/2502.14412)
- Bellingcat OSM Search logs queries and requires a Google login, which is an operational-privacy consideration for investigators. — [Bellingcat OSM Search how-to](https://bellingcat.com/resources/how-tos/2023/05/08/finding-geolocation-leads-with-bellingcats-openstreetmap-search-tool)

### Inferences
- **Do not use an LLM/VLM as the final verifier of a location hypothesis**, especially one taken from the post caption. GeoContext shows models rubber-stamp near-miss claims with high confidence at exactly the 150 m scale relevant to a 25–100 m target. Verification should use geometric or image-matching evidence (independent fixed features in street-level imagery). Caption hints should be scored as priors whose weight depends on the evidence, not repeated back.
- Confidence should come from agreeing independent evidence: text geocode, OSM constraint match, street-level visual match, and geometric verification count. Raw model self-reported confidence should not be the score. Present top-k candidates with an explicit "unresolved/low confidence" state, as commercial tools implicitly do ("leads," "top predictions"), and route low-confidence items to human review.
- Trust fixed geometry over transient features (signage, construction, seasonal scenes), as the Bellingcat failures show.
- Ethical guardrails supported by the evidence and vendor norms: geolocate the civic *issue* (public right-of-way infrastructure), not people or private interiors. Refuse or skip indoor/residential-interior photos. Avoid publishing exact coordinates of private residences. Blur faces and plates. Do not build per-person location histories from a user's posts, which is the "en masse database" pattern EFF warns about. Keep separate the post author's identity and the issue's location in anything published.
- Avoid unaffiliated "GeoSpy"-named consumer sites and knock-off tools when choosing baselines.

### Gaps
- I found no published calibration data (reliability curves) for any commercial geolocator's confidence score.
- OpenAI's, Google's and Anthropic's specific geolocation safety policies were not retrieved from primary sources.
- The GeoContext paper's model names and per-model results were not in the abstract, and the full paper was not read.
- No Canadian legal or regulatory analysis (e.g., PIPEDA implications of geolocating social-media photos) was in scope or found here.
