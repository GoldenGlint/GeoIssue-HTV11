# Run the image workflow on demand

The workflow collects recent photos, deduplicates them, screens for Toronto / visible issues / location clues, groups same-post views, and writes detailed assessments. **X and Flickr are excluded. No daily job is enabled.**

## Run locally

Use the existing project environment and `GEMINI_API_KEY` in ignored `scraping/.env`:

```sh
.venv/bin/python -m scraping.workflow
```

Inputs live in [workflow.json](../config/workflow.json), the three Bluesky query files, [reddit.json](../config/reddit.json), [reddit-discovery.json](../config/reddit-discovery.json), and [mastodon.json](../config/mastodon.json). All live collection uses seven days of posting history. The wider Reddit batch requires a Toronto-related title/body term before downloading images.

The default run permits 300 new image assessments, including up to 50 images without complaint wording, and 100 group descriptions. Cached assessments are reused. These are request limits, not promised image counts or daily allowances. Limits and unavailable services can leave a partial run with resumable results.

Resume processing saved batches without collecting again:

```sh
.venv/bin/python -m scraping.workflow --skip-collect
```

The request budgets can be changed with `--max-screen-requests`, `--exploration-images` and `--max-description-requests`. Keep exploration within the screening budget. Do not run two workflows against the same output folder; a lock prevents it. After an interrupted process, remove a lock only after confirming that process has stopped.

Open the local results:

```sh
.venv/bin/python -m scraping.demo serve --out scraping/data/workflow/handoff --port 8769
```

Then visit `http://127.0.0.1:8769`. Each post card shows independently passed images, separately labelled context, source links, location clues and detailed support/disagreement. Initial passes with `issue_supported: no` or `uncertain` remain visible as **Needs review**. Neither initial passes nor supported descriptions verify current conditions.

`scraping/data/workflow/workflow-report.json` reports the baseline, new passed images, supported images/groups, context count, source failures and overlapping query yields. Several views of one post are not separate incidents; cross-posted events may still need consolidation downstream.

## Optional Apify pilots

```sh
.venv/bin/python -m scraping.workflow --apify-pilots
```

This explicitly opts in to three small pilots: curated Instagram feeds, the Cycle Toronto public Facebook Page, and Threads keyword search. Each actor has a **US$0.05 server charge cap**, requires a verified non-paying Free account, and saves launch intent/run identity. All three together can consume at most US$0.15 of free credit. No paid upgrade or automatic relaunch is performed. The normal workflow does not use Apify.

Each pilot resumes the same saved run on repetition. A launch with an unknown outcome requires inspecting Apify before any new launch. Changing an actor or its input needs a deliberately new pilot/output folder after reviewing its allowance, rather than deleting state and blindly retrying. Actor pricing and availability are checked each time a new run is launched; access or poor yield can make a source unavailable.

Raw actor responses and image files stay in ignored local data. New normalizers keep only supported attached-photo shapes, expected CDN hosts and original media positions. Public visibility does not establish rights for every downstream use.

## GitHub Actions: manual only

[collect-images.yml](../../.github/workflows/collect-images.yml) has only `workflow_dispatch`. It has no active `schedule`, push or pull-request trigger. It cannot run in GitHub until the file is committed/pushed to the repository's default branch and repository secrets are configured. This implementation does not push changes, configure secrets or dispatch a remote run.

To use it later:

1. Add `GEMINI_API_KEY` under repository **Settings → Secrets and variables → Actions**. Add `APIFY_TOKEN` only if opting in to actor pilots. Enter values in GitHub's secret form; do not put them in workflow YAML or commit an `.env`.
2. Open **Actions → Collect and assess civic images → Run workflow**. Choose the new-screening request limit; Apify pilots default to off.
3. Read the run summary and download `civic-image-handoff-<run-id>`. A partial or failed run retains saved progress and reports its failure.

The job has read-only repository permissions and one-at-a-time concurrency. It caches text assessments/descriptions to avoid repeating model calls. New runs recollect the overlapping seven-day window; fingerprints reuse previous assessments. It uploads **text handoffs and reports**, not unblurred image files, credentials, raw actor payloads or the entire data directory. It does not publish the website or commit generated data.

After extracting an artifact, restore its passed/context photos locally (replace the shared path with the extracted `export/` folder):

```sh
.venv/bin/python -m scraping.share pull \
  --shared /absolute/path/to/extracted-artifact/export \
  --output scraping/data/daily-preview
.venv/bin/python -m scraping.demo serve --out scraping/data/daily-preview --port 8769
```

Restoration fetches the original CDN URLs and checks image fingerprints. Deleted, changed or expired media is omitted and reported; cached metadata does not resurrect removed media.

## Enable daily collection later

When ready, uncomment the two `schedule` lines already provided in the workflow. The example runs at **11:23 UTC once per day**; Toronto local time changes with daylight saving. Scheduled runs use the normal free-source route, 300 new assessments, up to 50 exploration images and 100 descriptions. Apify remains off unless explicitly opted in through a manual run.

Confirm the manual workflow's actual runtime, quotas and yield first. GitHub schedules are best-effort and depend on the workflow being on the default branch. Keep daily collection disabled until explicitly requested. [GitHub trigger documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows).

The current Actions workflow stops at the scraping handoff. Updating the map/app is a separate downstream analysis/publication step; it is not automatically deployed by collection.
