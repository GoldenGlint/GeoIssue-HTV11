# Tiger Data integration

## Implementation plan

1. Keep the current collection, AI, geolocation, deduplication and privacy rules. Export one database sighting per independent post/incident, rather than per photo.
2. Store public issue snapshots in PostgreSQL, sightings in a time-partitioned hypertable, and pipeline metadata alongside them. Synchronize each complete handoff transactionally; repeated imports must not add reports. Keep real pipeline data and simulated replay in separate datasets.
3. Build an hourly continuous aggregate by dataset, ward and category. Enable real-time aggregation, schedule refreshes, and explicitly refresh historical imports. Let Hypercore move older chunks into columnstore.
4. Add read-only issue, pipeline and activity endpoints to the existing Python server. Database credentials stay on the server. Without a configured/available database, keep the existing public-file experience and label it as a snapshot.
5. Add an activity panel to the dashboard, refreshed every 15 seconds. Distinguish reports from unique issues and compare the last 24 complete hours with the preceding seven days. Apply a minimum report threshold before calling a ward an emerging hotspot.
6. Provide a labelled simulated replay and a benchmark that checks raw/aggregate agreement before reporting timings. Check ingestion, API validation, privacy and fallback behavior; run the existing project checks.

## Setup

Requires Python 3.11+ and Tiger Cloud / TimescaleDB 2.20+.

```sh
.venv/bin/python -m pip install -r analysis/requirements-tiger.txt
```

Put the Tiger Cloud connection URI in the ignored root `.env`:

```dotenv
TIGER_DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/tsdb?sslmode=require
```

Then initialize the schema, analyze the team's complete handoff, and import it:

```sh
.venv/bin/python -m analysis.tiger init
.venv/bin/python -m analysis --input scraping/data/handoff/post-groups.jsonl --tiger
.venv/bin/python scripts/serve.py
```

`--tiger` is explicit: ordinary analysis stays dependency-free and writes the same files. A failed database import exits unsuccessfully while preserving those files. Restart the server after changing `.env`.

The pipeline dataset is an authoritative snapshot of the complete handoff, not an incremental batch. Combine batches before analysis. Import replaces removed records and preserves first ingestion times for existing sightings; it does not invent history from `sightings_count`. Photo files stay in their existing location; only public issue JSON and sanitized sighting metadata enter the database.

## Demo and measurement

```sh
.venv/bin/python -m analysis.tiger replay --events 10000
.venv/bin/python -m analysis.tiger compress
.venv/bin/python -m analysis.tiger benchmark --dataset replay
```

The replay uses a separate dataset, marks every issue as fictional, and adds a flooding-report surge. Select **Simulated replay** in the app header. Re-run with `--events 11000` to add more simulated reports while the activity panel is open. The replay is a labelled simulation, not a live source collector.

The benchmark compares identical hourly raw and aggregate results, reports median database query times, and reports hypertable storage sizes and measured columnstore savings. `compress` immediately converts chunks older than a day; the automatic policy handles future history. Storage statistics cover both datasets in the shared hypertable. Small datasets or cold caches may show no speedup, and columnstore overhead can increase the size of tiny chunks. No compression percentage or speedup is promised.

## API and dashboard semantics

- `GET /api/status`: Gemini availability and whether Tiger Data is configured.
- `GET /api/tiger`: imported collected/simulated report totals and measured storage savings across converted chunks in the shared hypertable. Read-only, with no connection details.
- `GET /api/issues?dataset=pipeline|replay`: public `Issue[]` only.
- `GET /api/pipeline?dataset=…`: pipeline report, area summaries and ingestion metadata.
- `GET /api/activity?dataset=…&days=7|30|90&ward=1..25&type=…`: hourly independent-report counts, the latest 24 complete hours versus the preceding seven days, and emerging wards. `days` defaults to 30.

The activity panel has its own explicit ward, category and period scope, taken from those shared filters. Search, neighbourhood, severity, status and infrastructure filters apply to issue cards/map/table and are not applied to activity. The panel says so. Existing issue totals still count unique issues.

Activity uses the source report timestamp where available and records ingestion time separately. Unknown source dates are bucketed by their first ingestion time and labelled in the response; a report timestamp is not a verified photo capture date. Baselines cover the loaded dataset only and do not establish how many physical defects exist in a ward.

Public responses use the existing privacy-rounded issue representation. Import and replay are local CLI operations; the browser has no database write or arbitrary SQL endpoint. Uploads, corrections and volunteer decisions retain their existing browser-local behavior.

## Verification

```sh
npm test
npm run check
python3 -m unittest discover -s analysis/tests -t .
```

The database check is skipped unless `TIGER_TEST_DATABASE_URL` points to a separate disposable TimescaleDB database. It initializes that database and replaces its pipeline dataset; never point this test setting at the team's database.
