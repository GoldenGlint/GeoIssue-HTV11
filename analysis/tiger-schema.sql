CREATE SCHEMA IF NOT EXISTS geoissue;

CREATE TABLE IF NOT EXISTS geoissue.issues (
    dataset TEXT NOT NULL CHECK (dataset IN ('collected', 'simulated')),
    issue_id TEXT NOT NULL,
    public_issue JSONB NOT NULL,
    PRIMARY KEY (dataset, issue_id)
);

CREATE TABLE IF NOT EXISTS geoissue.sightings (
    reported_at TIMESTAMPTZ NOT NULL,
    dataset TEXT NOT NULL CHECK (dataset IN ('collected', 'simulated')),
    sighting_id TEXT NOT NULL,
    issue_id TEXT NOT NULL,
    ward_id TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    timestamp_basis TEXT NOT NULL CHECK (timestamp_basis IN ('source', 'ingestion')),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset, reported_at, sighting_id),
    FOREIGN KEY (dataset, issue_id) REFERENCES geoissue.issues(dataset, issue_id)
) WITH (
    tsdb.hypertable,
    tsdb.partition_column = 'reported_at',
    tsdb.chunk_interval = '1 day',
    tsdb.segmentby = 'dataset,ward_id,issue_type',
    tsdb.orderby = 'reported_at DESC'
);

CREATE INDEX IF NOT EXISTS sightings_source_key ON geoissue.sightings (dataset, sighting_id);

CREATE TABLE IF NOT EXISTS geoissue.pipeline_state (
    dataset TEXT PRIMARY KEY CHECK (dataset IN ('collected', 'simulated')),
    metadata JSONB NOT NULL
);

CREATE MATERIALIZED VIEW IF NOT EXISTS geoissue.ward_activity_hourly
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 hour', reported_at) AS bucket,
       dataset, ward_id, issue_type,
       count(*) AS reports,
       count(*) FILTER (WHERE timestamp_basis = 'ingestion') AS undated_reports
FROM geoissue.sightings
GROUP BY bucket, dataset, ward_id, issue_type
WITH NO DATA;

ALTER MATERIALIZED VIEW geoissue.ward_activity_hourly
    SET (timescaledb.materialized_only = false);

SELECT add_continuous_aggregate_policy('geoissue.ward_activity_hourly',
    start_offset => INTERVAL '90 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => true);

-- Issues people submit in the app, with their photos exactly as submitted. Kept apart from geoissue.issues, which
-- each pipeline import replaces. public_issue stays empty while Claude is still finding the location.
CREATE TABLE IF NOT EXISTS geoissue.submissions (
    submission_id TEXT PRIMARY KEY,
    dataset TEXT NOT NULL DEFAULT 'collected' CHECK (dataset IN ('collected', 'simulated')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    located_at TIMESTAMPTZ,
    location_status TEXT NOT NULL CHECK (location_status IN ('provided', 'locating', 'located', 'unverified', 'not_found')),
    token_sha256 TEXT NOT NULL,
    submission JSONB NOT NULL,
    public_issue JSONB
);

CREATE TABLE IF NOT EXISTS geoissue.submission_photos (
    submission_id TEXT NOT NULL REFERENCES geoissue.submissions(submission_id) ON DELETE CASCADE,
    position SMALLINT NOT NULL,
    mime TEXT NOT NULL,
    data BYTEA NOT NULL,
    PRIMARY KEY (submission_id, position)
);
