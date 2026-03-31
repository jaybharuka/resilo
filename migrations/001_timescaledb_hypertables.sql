-- Migration 001: TimescaleDB hypertables, compression, and indexes
-- Run once against a PostgreSQL instance that has the TimescaleDB extension installed.
-- Safe to re-run: all statements use IF NOT EXISTS guards.

-- 1. Enable the extension ──────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- 2. metric_snapshots — high-frequency (every 30 s per agent) ─────────────────
--    1-day chunks: keeps each chunk small enough to compress efficiently
--    while covering a full day of data in a single chunk scan.
SELECT create_hypertable(
    'metric_snapshots', 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists        => TRUE,
    migrate_data         => TRUE
);

-- Segmented compression: queries filtered by org_id+agent_id skip entire chunks.
ALTER TABLE metric_snapshots SET (
    timescaledb.compress,
    timescaledb.compress_segmentby   = 'org_id,agent_id',
    timescaledb.compress_orderby     = 'timestamp DESC'
);

-- Compress chunks older than 7 days automatically.
SELECT add_compression_policy(
    'metric_snapshots',
    compress_after   => INTERVAL '7 days',
    if_not_exists    => TRUE
);

-- 3. alert_records — lower frequency (one row per fired alert) ─────────────────
--    1-week chunks: alert volume is ~100× lower than metrics.
SELECT create_hypertable(
    'alert_records', 'created_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists        => TRUE,
    migrate_data         => TRUE
);

-- Descending index so "ORDER BY created_at DESC LIMIT N" hits the latest chunk only.
CREATE INDEX IF NOT EXISTS ix_alert_org_created_desc
    ON alert_records (org_id, created_at DESC);

-- 4. audit_logs — append-only, queried by org + recent window ─────────────────
SELECT create_hypertable(
    'audit_logs', 'created_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists        => TRUE,
    migrate_data         => TRUE
);

CREATE INDEX IF NOT EXISTS ix_audit_org_created_desc
    ON audit_logs (org_id, created_at DESC);

-- 5. notification_logs — low volume, time-range filtered ─────────────────────
SELECT create_hypertable(
    'notification_logs', 'sent_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists        => TRUE,
    migrate_data         => TRUE
);

CREATE INDEX IF NOT EXISTS ix_notiflog_org_sent_desc
    ON notification_logs (org_id, sent_at DESC);

-- 6. Verify ────────────────────────────────────────────────────────────────────
-- After running this file, confirm with:
--
--   SELECT hypertable_name, num_chunks
--   FROM timescaledb_information.hypertables;
--
--   SELECT hypertable_name, compress_after
--   FROM timescaledb_information.jobs
--   JOIN timescaledb_information.policies USING (job_id)
--   WHERE proc_name = 'policy_compression';
