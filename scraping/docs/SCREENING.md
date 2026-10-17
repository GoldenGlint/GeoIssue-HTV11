# Automatic Gemini screening

Updated October 17, 2026. Human review is optional. Collectors download images; `scraping.screen` decides keep/reject.

## Workflow

```sh
# 0) Optional: rank searches first. No downloads, no Gemini.
.venv/bin/python -m scraping.probe_queries bluesky --query-file scraping/config/bluesky-query-candidates.txt
.venv/bin/python -m scraping.probe_queries reddit
.venv/bin/python -m scraping.probe_queries mastodon

# 1) Collect into ignored batches
.venv/bin/python -m scraping.collectors.bluesky \
  --query-file scraping/config/bluesky-queries.txt \
  --pool live --days 7 --max-images 200 --output scraping/data/bluesky-live
.venv/bin/python -m scraping.collectors.mastodon --output scraping/data/mastodon-live
.venv/bin/python -m scraping.collectors.reddit --output scraping/data/reddit-live

# 2) Screen with free-tier Gemini (add GEMINI_API_KEY to scraping/.env)
.venv/bin/python -m scraping.screen --batch scraping/data/reddit-live --max-requests 200
```

## Saving Gemini requests

- **Problem-word filter (on by default).** Before Gemini, the screener checks the caption and alt text for words such as pothole, flood, blocked, construction, removal, dumping, broken, damage or fire. Images without one are skipped and not cached, so `--no-prefilter` screens them later. On the 197 images screened on Oct 17, the filter would have sent 78 to Gemini and still kept all 10 passed images.
- **Cache by image fingerprint.** Each result is saved by `sha256`. Re-running a batch, or collecting the same image again, costs nothing.
- **Shared cache.** The screener also reads the committed `scraping/shared/screening-cache.jsonl`. Images a teammate already screened count as cache hits, and batches whose images are all cached screen without an API key.

An image is **passed** only when every condition holds: public outdoor scene, not sensitive, Toronto confirmed or visually likely, a visible issue at medium or high confidence, locatability high or medium, posted within 7 days, and neither Gemini nor the caption says the photo is old. Other photos never inherit that approval. Eligible photos from the same post can accompany passed images as explicitly labelled context, as described below.

Outputs in the batch:

| File | Meaning |
| --- | --- |
| `screening.jsonl` | Audit of every image, keyed by `sha256` (cache) |
| `passed.jsonl` | Only images that meet every requirement |
| `screening-report.json` | Request counts, passed count, and why others were blocked |

Combine passed images for the next stage. This copies files only; it does not call Gemini:

```sh
.venv/bin/python -m scraping.handoff \
  --batch scraping/data/reddit-live \
  --batch scraping/data/mastodon-live \
  --batch scraping/data/bluesky-live \
  --out scraping/data/handoff
.venv/bin/python -m scraping.describe --batch scraping/data/handoff --max-requests 100
.venv/bin/python -m scraping.demo serve --out scraping/data/handoff --port 8768
```

The page is a local, read-only verification tool for the handoff, separate from the final product. It displays one card per source post, with independently passed images and clearly separated companion photos. It shows issue descriptions, evidence and confidence, Toronto verdicts, location clues, source links, dates, and saved dimensions. Click any photo for its saved full-size JPEG or expand **Exact full post group JSON**. Filter by source or issue type. Human labelling is not part of this workflow.

## Photo groups and detailed issue descriptions

The existing **`passed.jsonl`** remains one record per independently passed image. **`post-groups.jsonl`** is the grouped input for the next stage, with:

- `group_id`, platform, native post identity, post URL, caption and posting date.
- `passed_images`: anchors that passed screening independently, preserving original `media_index` values and their own classifications.
- `supplemental_images`: other successfully downloaded photos from that exact post, in original order. Each carries `screening_status: not_passed` or `not_screened`, its own screening result/reasons when available, `relation: same_post_context`, and `issue_verified: false`. These may show a close-up, a wider scene or location clues; they are not independently approved evidence of an issue.
- `excluded_supplemental`: identifiers and exclusion reasons. Known sensitive images, private/indoor scenes, posters/screenshots, unlikely-Toronto scenes, known old images, missing files and duplicates stay out.
- `detail_status` and, after describing, `issue_details`.

`scraping.describe` sends each post's passed and eligible supplemental photos together to Gemini, clearly identifying their roles. It requests a detailed assessment for every passed image: `title`, a grounded 3–5 sentence `description`, `affected_infrastructure`, `observations`, exact `supporting_image_keys`, `uncertainties`, separately labelled `caption_claims`, confidence and `issue_supported: yes/no/uncertain`. Photos in one post are not assumed to show one incident. An issue supported only by a companion cannot approve the primary image. Descriptions can disagree with the original screening; `no` or `uncertain` is shown as **Needs review** and never silently promotes or demotes an image.

The matching description also appears as `issue_details` on the flat passed record, with `post_group_id` linking back to all photos. Descriptions cite actual photo keys and retain model, prompt version and timestamp. They do not establish exact coordinates, cause, severity, asset ownership or current condition.

Results are saved incrementally in ignored `scraping/data/issue-details-cache.jsonl`, separate from screening, and reused while the photos, caption and screening evidence match. Rebuilding the handoff preserves matching descriptions. `descriptions-report.json` records requests, cache hits and pending groups. A request cap or API failure leaves successful groups cached for resuming. Teammates also reuse descriptions embedded in shared groups without another Gemini call.

## Sharing results with teammates

The GitHub repository is public, so image files are not committed. They show unblurred faces until the downstream step censors them. Share text instead:

```sh
.venv/bin/python -m scraping.share export   # text only: passed records, post groups, screening cache and report
git add scraping/shared && git commit -m "Update shared passed images"
```

A teammate rebuilds the handoff folder without scraping or Gemini:

```sh
.venv/bin/python -m scraping.share pull     # re-downloads passed images, checks sha256, writes scraping/data/handoff
.venv/bin/python -m scraping.demo serve --out scraping/data/handoff --port 8768
```

Images deleted or changed at the source since export are left out and counted in `report.json`. Companion failures do not discard good primary images. Groups and descriptions are marked with unavailable image keys when their original context could not be fully restored.

Training-pool collection (older photos allowed):

```sh
.venv/bin/python -m scraping.collectors.bluesky \
  --query-file scraping/config/bluesky-queries.txt \
  --pool training --days 180 --max-images 1000 \
  --output scraping/data/bluesky-training
.venv/bin/python -m scraping.screen --batch scraping/data/bluesky-training
```

## Questions answered per image

1. Is this in Toronto? (`toronto.verdict`: confirmed / likely / unlikely / unknown)
2. Is there a visible infrastructure problem? (`issue.present` + confidence)
3. Can it be located from street signs, buildings, etc.? (`locatability.level`)

Code owns keep/reject: reject if `sensitive` or scene is not `public_outdoor`, or Toronto is not confirmed/likely. Kept rows with recent posting time and `appears_old=false` enter the **live** pool; other kept rows enter **training**.

## Handoff fields

`scraping/data/handoff/passed.jsonl` includes each saved image plus its evidence:

| Fields | Meaning |
| --- | --- |
| `screening.scene_type`, `sensitive` | Public outdoor scene classification and sensitivity check |
| `screening.toronto_verdict`, `toronto_basis`, `toronto_evidence` | Toronto verdict and whether it rests on visual cues or caption claims |
| `screening.issue_present`, `issue_type`, `issue_confidence`, `issue_evidence` | Visible infrastructure issue classification and supporting description |
| `screening.locatability`, `clues`, `location_guess`, `location_verified` | Location clues and a text guess; verified stays false until the downstream location stage |
| `platform`, `collector`, `post_id`, `post_url`, `found_by` | Source, native post identity, browser link for Reddit/Mastodon/Bluesky, and discovery query/tag/subreddit |
| `posted_at`, `captured_at`, `freshness`, `screening.appears_old` | Posting date and capture-age evidence; recent posting is not proof of a current condition |
| `local_path`, `media_url`, `media_index`, `sha256`, `dhash` | Saved file, source image URL, carousel position, exact source-pixel hash and similarity hash |
| `width`, `height`, `saved_width`, `saved_height` | Source image dimensions versus the actual saved JPEG dimensions; use saved dimensions for boxes/crops |
| `screening.model`, `prompt_version`, `screened_at`, `blur_before_public_display` | Screening provenance and the requirement to censor identifiable details before public display |
| `post_group_id`, `issue_details` | Same-post group identity and detailed multi-image issue assessment, when generated |

Caption, alt text, source location claims and the source batch are also retained. These are model-screened candidates, not verified issue reports. Issue classes are pothole, sidewalk damage, blocked access, dumping, drain, flooding, damaged transit/shelter, and other. The prompt requires visible outdoor infrastructure evidence; it does not verify municipal asset ownership, exact coordinates, severity, or whether an issue has since been fixed. Screenshots and ordinary street scenes can still be misclassified.

## Free-tier caveat

`GEMINI_API_KEY` uses Google AI Studio free tier. Google may use free-tier inputs to improve its products. Inputs here are public social posts. Stay at US$0 out of pocket; stop cleanly at `--max-requests` when the daily cap is hit. Partial results are preserved and cached by image hash.

## One-time label check

```sh
.venv/bin/python -m scraping.research.gemini_eval \
  --batch scraping/data/combined-demo --max-requests 200
```

Compares Gemini decisions to the existing `labels.json` (no new human labelling). Writes [gemini-eval-results.json](../research/results/gemini-eval-results.json). Gate: ≥90% useful/noise agreement, no known traps kept, Queen/Spadina drain detected as an issue with usable locatability.

## Optional gallery spot check

Source-batch galleries show only passed images. The handoff preview shows passed images plus separately labelled eligible same-post context, including its own screening status, and detailed issue descriptions when available.

## Privacy

Unblurred images may be sent to Gemini and used for local model training. A separate downstream component censors faces and identifiable information before public display or sharing. `blur_before_public_display` / `blur_required` means censor before public display, not before screening.

## Suggested repeat schedule

Live pool freshness needs re-collection. Example every six hours (adjust paths):

```sh
# crontab -e
0 */6 * * * cd /path/to/HTV-2026-BDO && .venv/bin/python -m scraping.collectors.reddit --output scraping/data/reddit-live && .venv/bin/python -m scraping.screen --batch scraping/data/reddit-live --max-requests 150
```
