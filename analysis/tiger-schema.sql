CREATE SCHEMA IF NOT EXISTS civiclens;

CREATE TABLE IF NOT EXISTS civiclens.issues (
    dataset TEXT NOT NULL CHECK (dataset IN ('pipeline', 'replay')),
    issue_id TEXT NOT NULL,
    public_issue JSONB NOT NULL,
    PRIMARY KEY (dataset, issue_id)
);

CREATE TABLE IF NOT EXISTS civiclens.sightings (
    reported_at TIMESTAMPTZ NOT NULL,
    dataset TEXT NOT NULL CHECK (dataset IN ('pipeline', 'replay')),
    sighting_id TEXT NOT NULL,
    issue_id TEXT NOT NULL,
    ward_id TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    timestamp_basis TEXT NOT NULL CHECK (timestamp_basis IN ('source', 'ingestion')),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset, reported_at, sighting_id),
    FOREIGN KEY (dataset, issue_id) REFERENCES civiclens.issues(dataset, issue_id)
) WITH (
    tsdb.hypertable,
    tsdb.partition_column = 'reported_at',
    tsdb.chunk_interval = '1 day',
    tsdb.segmentby = 'dataset,ward_id,issue_type',
    tsdb.orderby = 'reported_at DESC'
);

CREATE INDEX IF NOT EXISTS sightings_source_key ON civiclens.sightings (dataset, sighting_id);

CREATE TABLE IF NOT EXISTS civiclens.pipeline_state (
    dataset TEXT PRIMARY KEY CHECK (dataset IN ('pipeline', 'replay')),
    metadata JSONB NOT NULL
);

CREATE MATERIALIZED VIEW IF NOT EXISTS civiclens.ward_activity_hourly
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 hour', reported_at) AS bucket,
       dataset, ward_id, issue_type,
       count(*) AS reports,
       count(*) FILTER (WHERE timestamp_basis = 'ingestion') AS undated_reports
FROM civiclens.sightings
GROUP BY bucket, dataset, ward_id, issue_type
WITH NO DATA;

ALTER MATERIALIZED VIEW civiclens.ward_activity_hourly
    SET (timescaledb.materialized_only = false);

SELECT add_continuous_aggregate_policy('civiclens.ward_activity_hourly',
    start_offset => INTERVAL '90 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => true);
