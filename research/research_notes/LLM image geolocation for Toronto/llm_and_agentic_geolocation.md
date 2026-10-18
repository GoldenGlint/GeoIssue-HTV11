# LLM/VLM-based and agentic image geolocation: methods, benchmarks, measured accuracy

Scope note: per the coordinator's correction, the draft plan's assumptions (LLM only as clue extractor; "frontier VLMs alone ~10–17% within 1 km") are treated as hypotheses to test, not as a baseline. Designs where the LLM is the orchestrator are evaluated on the evidence. All benchmarks below are worldwide or China-city benchmarks. None measures accuracy inside a single known city at 25–100 m. The finest threshold any source reports is 500 m.

## Q0. Is "frontier VLMs alone ≈ 10–17% within 1 km on generic street views" correct?

### Takeaway
Not as stated. The 10–17% @1 km range matches the **Im2GPS3k (Flickr, worldwide)** numbers for **retrieval-augmented** LLM pipelines (Img2Loc 15.3%, G3 16.7%) and for a zero-shot open 8B VLM (Qwen3-VL-8B 10.5%). It does not describe frontier VLMs on street views. Frontier-model accuracy at ~1 km ranges from about 0% to over 60% depending on the image distribution. On **social-media-style images with visible text**, the case closest to GeoIssue, frontier VLMs alone reach **50–61% within 1 km**.

### Cited Findings
- Im2GPS3k @1 km/25 km: Img2Loc (GPT-4V + RAG) 15.34/39.83; G3 16.65/40.94; GeoRanker (Qwen2-VL-7B re-ranker) 18.79/45.05; PIGEON 11.3/36.7; GeoCLIP 14.11/34.47. — [GeoRanker, arXiv 2505.13731 (NeurIPS 2025)](https://arxiv.org/html/2505.13731v3)
- Untuned open VLMs on Im2GPS3k @1 km/25 km: Qwen3-VL-8B 10.5/37.2; Qwen3-VL-4B 8.5/32.3. Qwen2.5-VL-7B: 3.97/25.48. — [REVERSE, arXiv 2605.26861](https://arxiv.org/html/2605.26861); [SpotAgent, arXiv 2602.09463](https://arxiv.org/html/2602.09463)
- Social-media-style images (GPTGeoChat: 1,000 images, about 85% with embedded text, about half US): GPT-4.1 **61% R@1 km**, **Claude-3.7-Sonnet 60%**, Gemini-1.5-Pro 50%, and the best open-weight model, Qwen-2.5-VL-72B, 36%. On OSV5 (500 random street-view images from 225 countries), accuracy drops sharply: GPT-4.1 about 11.6% at a threshold the source's garbled table header doesn't make clear. — [Assessing the Geolocation Capabilities… of Generative VLMs, arXiv 2508.19967 (Aug 2025)](https://arxiv.org/html/2508.19967v1)
- GeoBench (GeoVista; 1,132 high-res photos, panoramas and satellite images; easy landmarks removed): Gemini-2.5-Pro **64.45% within 3 km, median 0.80 km**; Gemini-2.5-Flash 58.11%/1.67 km; GPT-5 55.12%/1.86 km. The paper does not say whether the closed models had tools. — [GeoVista, arXiv 2511.15705v2](https://arxiv.org/html/2511.15705v2)
- MAPBench (street-view/storefront POI images in 20 Chinese cities) Acc@500 m: GPT-5 9.02% easy, 0.05% hard; o3 7.68%/0.05%; Gemini-3-Pro with Search/Maps grounding 20.86%/4.02%. — [Thinking with Map, arXiv 2601.05432](https://arxiv.org/html/2601.05432)
- PAVED (urban/commercial street imagery) @500 m/2 km/25 km: Gemini-3.0-Flash 14.92/23.34/54.74; Gemini-3.1-Pro 11.10/17.00/57.50; GPT-5.5 5.31/13.16/39.42. — [GeoPAVE, arXiv 2608.29880](https://arxiv.org/html/2608.29880)
- IMAGEO-Bench street scenes (6,152 NUS Global Streetscapes images, 123 countries), median error: Gemini-2.5-Pro 4.2 km, o3 8.2 km, GPT-4.1 10.5 km, Claude-3.5-Haiku 68.8 km. On 220 private, previously unseen photos, Gemini-2.5-Pro's median error is **0.7 km**. — [IMAGEO-Bench, arXiv 2508.01608](https://arxiv.org/html/2508.01608v1)
- o3 on 50 US Google Street View residential images: about 60% within 1 mile and about 84% within 5 miles, using best-of-4 prompts, which likely inflates the figure. — [Doxing via the Lens, arXiv 2504.19373v2](https://arxiv.org/html/2504.19373v2)

### Inferences
- The draft's figure is approximately the Im2GPS3k RAG-pipeline number, and the label "frontier VLMs alone on street views" is wrong. Measured frontier-alone results run from about 0% (MAPBench hard @500 m) to about 60% (social-media images @1 km).
- For GeoIssue the city is known in advance, so worldwide @1 km numbers overstate the difficulty of the coarse part and say nothing about 25–100 m. Social-media civic-issue photos (potholes, graffiti, broken signals) often lack storefront or landmark text, so the textless OSV5/MAPBench-hard regime may be the more relevant one for many images.

### Gaps
- No source measures VLM accuracy within a single pre-specified city at 25–100 m.
- The OSV5 column mapping in arXiv 2508.19967 is garbled, so the exact R@1 km for street views is uncertain.

## Q1. Frontier-model geolocation results 2025–2026 (o3/GPT-5, Gemini 2.5/3, Claude)

### Takeaway
Across independent evaluations, **Gemini (2.5 Pro, 3 Flash, 3.x Pro) is the most consistent leader at fine scales (median km, @500 m–3 km)**. OpenAI o3/GPT-4.1 are close at city level, and GPT-5 was a regression in Bellingcat's tests. Claude is mixed: older and smaller Claude models (3.5 Haiku, Haiku 4.5) are clearly weaker, Claude 3.7 Sonnet matched GPT-4.1 @1 km on social-media images, and an aggregator lists **Claude Fable 5 at #1 (89%) on country accuracy** in the ccmdi GeoBench.

### Cited Findings
**Independent, peer-reviewed or arXiv:**
- IMAGEO-Bench (GSS street scenes), city accuracy / country accuracy / median km / USD per request: Gemini-2.5-Pro 44.1/92.4/4.2/$0.0056; o3 42.0/88.7/8.2/$0.0146; Gemini-2.5-Flash 41.7/91.2/6.0/$0.0014; GPT-4.1 39.6/88.9/10.5/$0.0054; Claude-3.5-Haiku 30.7/74.5/68.8/$0.0028; Llama-3.2-90B 26.3/66.9/15.7. On US POIs (UPC), city accuracy is only 8.7–26.4%. — [IMAGEO-Bench](https://arxiv.org/html/2508.01608v1)
- GeoAgent (Street View navigation with up to 8 actions; 1,200 locations in 100 cities), median km / city %: **Gemini 3.0 Flash 5.0 km / 50.1%**; GPT-5 Mini 182.3 km / 34.5%; Gemma 3 27B 401.5 / 19.3; Llama 4 Scout 579.7 / 14.7; Geo-R1 7B 575.8 / 17.9; **Claude Haiku 4.5 688.3 km / 14.3%**. The human reference has a 995.9 km median and 7.1% city accuracy. — [GeoAgent, arXiv 2608.29483](https://arxiv.org/html/2608.29483v1)
- GeoBench (GeoVista), city-level accuracy: Gemini-2.5-Pro 78.98%, Gemini-2.5-Flash 73.29%, GPT-5 67.11%, Seed-VL-1.6 70.58%. Claude was not tested. — [GeoVista](https://arxiv.org/html/2511.15705v2)
- arXiv 2508.19967 evaluated 25 models, including Claude-3.5, 3.7, 4.0 and Opus: GPT-4.1 61% and Claude-3.7-Sonnet 60% R@1 km on GPTGeoChat; o3 led city accuracy at 41.3% average; GPT-4.1 led country accuracy at 76.5%. — [arXiv 2508.19967](https://arxiv.org/html/2508.19967v1)
- PAVED: Gemini-3.0-Flash beats Gemini-3.1-Pro at 500 m and 2 km (14.92 vs 11.10 at 500 m), and GPT-5.5 is far behind (5.31). The authors say GPT-5.5 slightly beats their agent on Im2GPS3k, which they attribute to indoor images. — [GeoPAVE](https://arxiv.org/html/2608.29880)
- "Where on Earth?" benchmark: Gemini-2.5-Pro 56.32% average accuracy, with regional bias of up to 42.7%. (Search snippet only; not read in full.) — [arXiv 2510.10880](https://arxiv.org/pdf/2510.10880)
- GeoArena (human pairwise preference over geolocation reasoning, 17 models, ACL 2026): Gemini 2.5 leads, while Qwen 2.5 and Gemma 3 are closing the gap. This measures preference, not distance. — [GeoArena, arXiv 2509.04334](https://arxiv.org/html/2509.04334v3)

**ccmdi GeoBench (GeoGuessr community maps; independent hobbyist benchmark; numbers via aggregators):**
- Method: photos from 5 GeoGuessr community maps; most models tested on 100 images of "A Community World", some expensive models on as few as 20; temperature 0.4; scored up to 5,000 points with exponential decay. — [Epoch AI GeoBench page](https://epoch.ai/benchmarks/geobench)
- ACW country accuracy: **Claude Fable 5 89.0**, Gemini 3.0 Flash 88.0, Gemini-2.5-Pro-05-06 86.0, Gemini 3.0 Pro preview 84.0, GPT-5 (thinking medium) 81.0, o1 80.0, Gemini 2.5 Flash 76.0, **Claude Opus 4.5 75.0**, o3 74.0 (60.0 at thinking high), GPT-4.1 72.0, GPT-4o 71.0, **Claude Sonnet 3.7 68.0**, o4-mini 64.0, **Claude 3.5 Sonnet (new) 62.0**, Grok 4 45.0. Gemini 2.5 Pro scored lower with tools and internet (81.0) than without (86.0). These are from an aggregator, not the primary leaderboard, and country-level only. — [LLMLearner GeoBench-ACW](https://llmlearner.com/rankings/geobench-acw)

**Practitioner and journalist tests (non-academic):**
- Bellingcat, June 2025 (25 holiday photos, 20 models): only o3, o4-mini and o4-mini-high beat Google Lens, and only narrowly. Gemini was below Lens. "Anthropic's strongest models mostly lagged", in some cases identifying only the continent. — [Bellingcat, Jun 2025](https://www.bellingcat.com/resources/how-tos/2025/06/06/have-llms-finally-mastered-geolocation/)
- Bellingcat, Aug 2025 (24 models, 0–10 scale): **Google AI Mode was the most capable overall**. GPT-5 (Thinking and Pro) was a "considerable downgrade" from o4-mini-high, and on a Noordwijk hotel GPT-5 named a beach in France. Most models hallucinated at some point. — [Bellingcat, Aug 2025](https://bellingcat.com/resources/2025/08/14/llms-vs-geolocation-gpt-5-performs-worse-than-other-ai-models/)
- o3 against Master-rank GeoGuessr player Sam Patterson (ACW map, no-move, 5 rounds, o3 allowed web search): o3 won narrowly on total score but guessed better in only 2 of 5 rounds. It rejected fake EXIF GPS as inconsistent with the scenery. — [Simon Willison, 28 Apr 2025](https://simonwillison.net/2025/Apr/28/o3-geoguessr/)

### Inferences
- Gemini 3 Flash looks like the best fine-scale model per dollar: it leads at 500 m/2 km on PAVED, has a 5 km median in GeoAgent, and is 88% on ccmdi country accuracy.
- Claude's frontier model (Fable 5) is now competitive at country level, but no independent source gives a sub-1 km number for any Claude 4.x/5.x model.

### Gaps
- No street-level (1 km) or 25 km numbers for Claude Opus 4.5+, Sonnet 4.5+/5.x, Fable 5 or Haiku 5.5.
- The primary geobench.org leaderboard did not render, so the median-km and points figures there were not retrieved.
- No EPFL, Stanford or Berkeley LLM-geolocation evaluation, and no benchmark named "GeoReasonBench", turned up in searches.

## Q2. Agentic and tool-using geolocation systems: tools, gains, failure modes

### Takeaway
The strongest evidence for fine-scale gains comes from **map/POI-search tools**. On MAPBench, adding a map tool raised Acc@500 m from 1.12% to 16.16%, while zoom and web search added under 1 pp. Hypothesize-then-verify orchestration on a frontier model adds a few points (Gemini 3 Flash +2 pp @500 m, +5 pp @25 km). Untrained or weak models often get worse with tools. Parallel sampling plus a verifier gives further gains.

### Cited Findings
- **Thinking with Map** (Qwen3-VL-30B-A3B with GRPO RL; Jan 2026, Findings of ACL 2026). Tools: image zoom, POI input tips, POI keyword search, POI detail query, static map, satellite map (AMAP and Google Maps).
  - Tool ablation, MAPBench Acc@500 m: base 1.12%; + zoom 1.48%; + web search 1.77%; + **map tool 16.16%**.
  - Full system on MAPBench, Acc@500 m easy/hard: 41.51/12.33 after RL; **44.98/14.86** with parallel ×4 and a verifier; Gemini-3-Pro grounded scores 20.86/4.02.
  - GeoBench Acc@500 m: 37.79% for the best closed model vs 57.94% for this method. IMAGEO-2-test: 16.33% vs 20.53%.
  - The verifier nearly matches oracle best-of-N at N = 2 or 4. Noisy map results can bias coarse predictions. Latency and cost were not reported.
  - Source: [arXiv 2601.05432](https://arxiv.org/html/2601.05432)
- **GeoPAVE** (Aug 2026; built on Gemini-3.0-Flash). One perception pass produces up to 3 candidates, each with confidence, uncertainty tags and suggested checks. Rule-based routing then sends each candidate to skills (OCR, zoom-crop, web "scene verification", map context: POI probes, elevation and spatial cross-checks, Nominatim geocoding). Each skill returns Support, Refute or Refine evidence, and the candidates are re-scored.
  - Gain over base Gemini-3.0-Flash: +1.95 pp @500 m (14.92 → 16.87) and +5.22 pp @25 km.
  - Ablation @500 m: full 16.87; perception only 12.72; without web 11.87 (largest drop); without map 13.58; without OCR 15.16.
  - On a GPT-4o-mini backbone, gains are tiny at fine scales (2.77 → 2.87 @500 m) but +9.35 pp at 750 km.
  - Failures: false textual grounding (a "KICKZ" store sign sent a Melbourne image to Munich, 16,120 km off); no correct candidate generated (a night scene); over-specific candidates.
  - Code and data: github.com/Arandinglv/GeoPAVE.
  - Source: [arXiv 2608.29880](https://arxiv.org/html/2608.29880)
- **GeoAgent** (Street View navigation benchmark; 9 actions such as rotate, look and move, capped at 8): Gemini 3.0 Flash city accuracy rose from 41.5% (8-view static) to 50.1% (agentic), and GPT-5 Mini from 30.3% to 34.5%, while Llama 4 Scout got worse. Unlimited exploration gave no consistent gain. Failures: Geo-R1 7B emitted invalid tool calls in 87.1% of turns; agents rarely recovered from a bad first guess (confirmation bias); strong developed-region bias (mean distance 50–103% lower). The authors conclude gains are "conditional on basic tool calling capabilities". — [arXiv 2608.29483](https://arxiv.org/html/2608.29483v1)
- **GeoVista-7B** (Qwen2.5-VL-7B; cold-start SFT on about 2k trajectories, then GRPO with a hierarchical country/province/city reward; tools: zoom-in and web search via Tavily, up to 6 turns): GeoBench city 72.68%, <3 km 52.83%, median 2.35 km, against Qwen2.5-VL-7B's 32.57%, 29.30% and 2,209.82 km. No tool-removal ablation was run. Failures: invalid crop boxes and incomplete JSON. — [arXiv 2511.15705v2](https://arxiv.org/html/2511.15705v2)
- **SpotAgent** (Qwen2.5-VL-7B; SFT on 200k images, then about 6k agentic cold-start trajectories, then GRPO with a geodesic reward; tools: Google Maps geocoding, web search via Tavily or YDC, zoom; at most 6 calls): Im2GPS3k @1/25 km 14.12/40.36, below G3's 16.65/40.94. On the Street View Text dataset, tools raised @1 km from 9.22 to 19.65. 59% of trajectories used only geocoding. The paper claims less hallucination but gives no metric. — [arXiv 2602.09463](https://arxiv.org/html/2602.09463)
- **REVERSE** (Qwen3-VL-4B; tools: zoom, region image search, text search; trained to tag useful results with an MCC reward): Im2GPS3k @1/25 km **22.5/48.3**, the best reported. YFCC4k 14.1/27.5, below G3's 24.0/35.9. Untuned 4B with tools: @25 km 32.3 → 36.0, but @750 km fell 62.6 → 60.9, so "tool use must be trained to help". Failures: wrong crops, following distractor search results, untuned models overriding correct search evidence with their visual prior. — [arXiv 2605.26861](https://arxiv.org/html/2605.26861)
- **GEO-Detective** (agent with visual reverse search over 4 steps): more than +11.1% country-level accuracy over baseline LLMs. (Snippet only.) — [arXiv 2511.22441](https://arxiv.org/abs/2511.22441)
- **Retrieval + LLM re-rank or generation** (2024–2025, older generation):
  - Img2Loc (GPT-4V + retrieved GPS neighbours): Im2GPS3k @1 km 15.34; YFCC4k 19.78.
  - G3: 16.65 and 23.99.
  - **GeoRanker** (Qwen2-VL-7B scores each query–candidate pair over 12–19 retrieved or GPT-4V-generated candidates): **18.79 and 32.94**, the best at 1 km on both benchmarks. Code and checkpoint released at github.com/Applied-Machine-Learning-Lab/GeoRanker.
  - Source: [GeoRanker](https://arxiv.org/html/2505.13731v3)
- Google's grounded mode: Gemini-3-Pro with Google Search/Maps grounding scored 20.86% @500 m on MAPBench-easy, against 9.02% for ungrounded GPT-5. — [Thinking with Map](https://arxiv.org/html/2601.05432)

### Inferences
- The architecture with the strongest fine-scale evidence is a **VLM that proposes hypotheses (text, POI names, scene type)**, followed by **deterministic map/POI/geocoder lookups** and then **evidence-gated verification**. This is a hybrid with the LLM as planner and verifier. A Toronto open-data / OSM / Places index is a close analogue of the "map tool" that drove 1.12% → 16.16% @500 m.
- LLM as re-ranker over retrieved geo-tagged candidates (GeoRanker) wins at 1 km on Flickr benchmarks, but it needs a dense geo-tagged reference image set. For Toronto that would mean something like street-level imagery; this is an inference, not tested in any source.
- A fully free-form agent built on a small or untuned model is risky: invalid tool calls, distractors, confirmation bias.

### Gaps
- Per-image latency is not reported by any agentic paper.
- Whether GeoBench and GeoPAVE gave their closed baselines tools is unstated.
- SpotAgent's failure appendix was not read.
- No paper tests OSM/Overpass or municipal open data directly as a tool.

## Q3. RL or fine-tuned open-source VLM geolocators: weights, 8 GB VRAM, licences

### Takeaway
Several RL-trained 4–7B geolocators exist, and GeoVista-7B has public weights. They are tuned for worldwide coarse-to-city localization and perform **near zero at 500 m** on fine-grained POI imagery. A 4-bit 7B VLM fits in about 4.5–6 GB, so it would run on an 8 GB RTX 4060. The best fine-grained open agent (Thinking with Map) uses a 30B MoE and would not fit comfortably.

### Cited Findings
- GeoVista: weights on Hugging Face (`LibraTree/GeoVista-RL-6k-7B`, `GeoVista-RL-12k-7B`, `GeoVista-SFT-7B`), plus `LibraTree/GeoVistaBench` and a 1.5k cold-start set. The repo is Apache-2.0, but the weight licence is not stated. Served with vLLM; inference needs a Tavily API key. No quantized release is listed. — [GitHub ekonwang/GeoVista](https://github.com/ekonwang/GeoVista)
- On MAPBench @500 m, the open geolocators collapse at fine scale: GeoVista-7B (with Google Search) 0.33% easy, 0.00% hard; GLOBE-7B 0.17%/0.05%; base Qwen3-VL-30B-A3B 4.01%/0.21%. — [Thinking with Map](https://arxiv.org/html/2601.05432)
- Im2GPS3k @1/25 km for retrieval-free RL or fine-tuned models: GRE Suite 11.3/35.3; GLOBE 9.84/40.18; SpotAgent 14.12/40.36; Geo-R (AAAI'26) 18.1/41.5; REVERSE 22.5/48.3. — [SpotAgent](https://arxiv.org/html/2602.09463); [REVERSE](https://arxiv.org/html/2605.26861)
- REVERSE code at github.com/yonglleee/REVERSE; weights not stated. It depends on a Kimi-K2.6 teacher and an offline search cache. — [REVERSE](https://arxiv.org/html/2605.26861)
- Thinking with Map is built on Qwen3-VL-30B-A3B and trained on 32 H20 GPUs. Weight and code release are not stated in the paper text. — [arXiv 2601.05432](https://arxiv.org/html/2601.05432)
- GeoRanker (Qwen2-VL-7B) checkpoint released; licence not stated. — [GeoRanker](https://arxiv.org/html/2505.13731v3)
- VRAM: one estimate puts Qwen2.5-VL-7B-Instruct-AWQ (INT4) at about 4.5 GB, against about 18 GB at FP16. — [Spheron GPU guide](https://www.spheron.network/tools/gpu-recommender/Qwen/Qwen2.5-VL-7B-Instruct-AWQ/). Another puts the GGUF Q4_K_M build at about 6 GB, so it fits 8 GB, while Q8_0 needs about 10 GB. — [bestllmfor.com](https://bestllmfor.com/catalog/qwen25-vl-7b/). Both are third-party estimates, not measurements.

### Inferences
- GeoVista-7B at 4-bit is technically runnable on the RTX 4060. The evidence suggests it adds little for 25–100 m inside Toronto, because it is trained to name the city, which GeoIssue already knows.
- A 30B-A3B MoE at 4-bit would need roughly 15+ GB for weights. This is my arithmetic, not a sourced figure, and it means Thinking with Map is not practical locally.
- A local 7B VLM is more plausible as a cheap OCR or clue tagger than as the geolocator.

### Gaps
- Weight licences for GeoVista, GLOBE, GRE Suite, Geo-R and SpotAgent were not confirmed.
- The base Qwen licences were not verified in this pass.
- No measured 8 GB benchmark of these geo fine-tunes exists.

## Q4. Reading fine-grained urban clues, hallucination, calibration and abstention

### Takeaway
VLMs exploit text and signage heavily: social-media images with text get about 60% @1 km against far less on textless street views. Text is also the main source of **confident catastrophic errors**: a matching shop name in another city, or a franchise sign. Self-reported confidence does not transfer across models. Few systems abstain properly; the best practice is an evidence gate (Support/Refute) plus multi-sample agreement or a verifier.

### Cited Findings
- About 85% of GPTGeoChat images contain text, and closed models' high R@1 km there is attributed to visual and textual cues. Performance drops on landmark-poor OSV5. — [arXiv 2508.19967](https://arxiv.org/html/2508.19967v1)
- Failure and refusal rates when asked for coordinates: o4-mini 61.4%, o3 33.1%, GPT-4o-mini 21.7%, GPT-4o 11.0%, IDEFICS 75.5%. — [arXiv 2508.19967](https://arxiv.org/html/2508.19967v1)
- In IMAGEO-Bench, success depends mainly on urban, outdoor, street-level and landmark content, and performance is better in high-resource regions such as North America. Self-reported confidence on a 1–5 scale: Gemini-2.5-Pro was most confident and o3 least. Within GPT-4.1, o3 and Claude-3.5-Haiku, higher confidence tracked accuracy, but "confidence alone is not a reliable proxy" across models. — [IMAGEO-Bench](https://arxiv.org/html/2508.01608v1)
- False textual grounding: the "KICKZ" sign sent a Melbourne image to Munich, 16,120 km off. GeoPAVE's evidence gate rejects candidates that are precise but inconsistent with the evidence. — [GeoPAVE](https://arxiv.org/html/2608.29880)
- Agents rarely self-correct after a bad first guess (confirmation bias). Neighbouring regions get confused, for example Southeast Asian countries. — [GeoAgent](https://arxiv.org/html/2608.29483v1)
- Untuned VLMs override correct search evidence with a visual prior (Zuccotti Park sent to Chicago). REVERSE trains explicit "useful result" tagging with an MCC reward to stop the model marking everything as useful. — [REVERSE](https://arxiv.org/html/2605.26861)
- Most models hallucinated at some point, and even the best tool, Google AI Mode, sometimes named the wrong place with confidence. — [Bellingcat, Aug 2025](https://bellingcat.com/resources/2025/08/14/llms-vs-geolocation-gpt-5-performs-worse-than-other-ai-models/)
- Clues o3 used most on US residential images: street layout and front-yard design, then the "Identification" and "Urban Infrastructure" categories. — [Doxing via the Lens](https://arxiv.org/html/2504.19373v2)
- Claude docs: hallucination risk rises on low-quality, rotated or very small images (<200 px). Claude does not read image metadata such as EXIF. Claude 4.7+ models accept up to a 2576 px long edge (4,784 visual tokens) against 1568 px for others, which helps with small signage. Heavy JPEG compression hurts text reading. — [Claude vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)

### Inferences
- For GeoIssue, any text clue (street name, business name, TTC route) should be confirmed against a deterministic Toronto gazetteer or POI index before it is trusted. This guards against the KICKZ-type failure and the chain-store problem.
- An abstain or "needs review" output should fire when samples disagree or when no deterministic match corroborates the clue.

### Gaps
- No paper measures VLM accuracy on specific municipal clues: street-sign typography, transit branding, utility poles or licence plates. That evidence exists only anecdotally in the GeoGuessr community.
- No calibration curves or ECE for geolocation were found.
- No Claude-specific hallucination rate for geolocation was found.

## Q5. Cost, latency and prompt techniques

### Takeaway
A single-image call costs about $0.0001–0.02 depending on model, and Gemini 3 Flash is roughly an order of magnitude cheaper than Claude Haiku 4.5 in agentic loops. Techniques with measured gains: structured JSON clue schemas (used by IMAGEO), hypothesize-and-verify, and parallel sampling (N = 2–4) with a verifier. No source gives per-image latency.

### Cited Findings
**Claude:**
- Image cost formula: ⌈w/28⌉ × ⌈h/28⌉ visual tokens. A 1000×1000 image is 1,296 tokens. A 1920×1080 image is 1,560 tokens on the standard tier and 2,691 on high-res (Claude 4.7+), capped at 4,784 for 4K.
- Anthropic's worked examples: Haiku 4.5 is about $1.30 per 1,000 1-MP images. Opus 5.5 is about $5.18 per 1,000 1-MP images and $19.14 per 1,000 4K images (input only).
- Source: [Claude vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)
- Claude list prices per MTok, input/output:

  | Model | Input | Output |
  |---|---|---|
  | Fable 5 / 5.1 | $10 | $50 |
  | Opus 5.5 | $4 | $20 |
  | Opus 4.5–4.8 | $5 | $25 |
  | Sonnet 5.5 | $2 | $10 |
  | Sonnet 4.5/4.6 | $3 | $15 |
  | Haiku 5.5 (≤100k-token prompts) | $0.10 | $0.50 |
  | Haiku 4.5 | $1 | $5 |

  Batch API is −50%. The web search tool is $10 per 1,000 searches, and web fetch has no extra charge. — [Claude pricing docs](https://platform.claude.com/docs/en/about-claude/pricing)

**Gemini:**
- List prices per MTok, input/output:

  | Model | Input | Output | Free tier |
  |---|---|---|---|
  | Gemini 3 Flash Preview | $0.50 | $3.00 | Yes |
  | Gemini 3.1 Pro Preview | $2 | $12 | No |
  | Gemini 2.5 Pro | $1.25 | $10 | Yes |
  | Gemini 2.5 Flash | $0.30 | $2.50 | Yes |

  Grounding with Google Search/Maps for Gemini 3+: 5,000 free requests a month, then $14 per 1,000. Gemini 2.5 Search grounding: $35 per 1,000 after the free daily quota. — [Gemini pricing (updated 2026-10-16)](https://ai.google.dev/gemini-api/docs/pricing)
- Gemini 3 image tokens: 280 (low), 560 (medium), 1,120 (high and default), 2,240 (ultra_high). "high" is recommended for image analysis. — [Gemini media resolution docs](https://ai.google.dev/gemini-api/docs/media-resolution)

**Measured costs:**
- IMAGEO-Bench, USD per request: o3 $0.0146; Gemini-2.5-Pro $0.0056; GPT-4.1 $0.0054; Claude-3.5-Haiku $0.0028; Gemini-2.5-Flash $0.0014; GPT-4.1-mini $0.0016. — [IMAGEO-Bench](https://arxiv.org/html/2508.01608v1)
- GeoAgent, per agentic round: Claude Haiku 4.5 about $0.0174; GPT-5 Mini about $0.0036; Llama 4 Scout about $0.00098; Gemini 3.0 Flash about $0.00079; Gemma 3 27B about $0.00021. — [GeoAgent](https://arxiv.org/html/2608.29483v1)

**Prompt and inference techniques:**
- IMAGEO used a JSON schema covering image information, reasoning (landmark, text/signage, cultural, spatial) and reverse geocoding (confidence 1–5, address, lat/lon), with CoT and a one-shot example at temperature 0.7. — [IMAGEO-Bench](https://arxiv.org/html/2508.01608v1)
- Parallel ×2/×4 trajectories with an LVLM verifier: MAPBench-easy @500 m went 41.51 → 43.65 → 44.98, and the verifier is close to oracle. — [Thinking with Map](https://arxiv.org/html/2601.05432)
- Multi-hypothesis (top-3) plus tool verification: +4.15 pp @500 m over perception-only (12.72 → 16.87). — [GeoPAVE](https://arxiv.org/html/2608.29880)
- Best-of-4 prompts used for o3 (no ablation). — [Doxing via the Lens](https://arxiv.org/html/2504.19373v2)
- Tool budgets are bounded at 6–8 turns, beyond which the papers report no gain. — [GeoAgent](https://arxiv.org/html/2608.29483v1); [GeoVista](https://arxiv.org/html/2511.15705v2)

### Inferences
- Rough per-image input cost at 1 MP: Gemini 3 Flash about $0.0006 (1,120 tokens); Claude Haiku 5.5 about $0.00013; Sonnet 5.5 about $0.0026; Opus 5.5 about $0.0052. Output tokens and tool calls (Claude web search at $0.01 each, Gemini grounding at $0.014 after the free quota) dominate agentic cost.
- Hackathon volumes (hundreds of images) cost single-digit dollars on any of these models.

### Gaps
- No paper reports wall-clock latency per image for agentic geolocation.
- OpenAI current vision pricing was not fetched; only the measured per-request costs above are available.
- No independent comparison of Claude 5.x against Gemini 3 on identical geolocation images was found.
