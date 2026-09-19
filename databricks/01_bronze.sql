-- Template: replace {{catalog}} and {{schema}} with validated SQL identifiers.
-- Repeatable initialization preserves existing observations.
CREATE SCHEMA IF NOT EXISTS {{catalog}}.{{schema}};
CREATE TABLE IF NOT EXISTS {{catalog}}.{{schema}}.`raw_occupancy` (
  facility_id STRING NOT NULL,
  facility_name STRING NOT NULL,
  source_facility_id STRING NOT NULL,
  occupancy BIGINT NOT NULL,
  remaining BIGINT NOT NULL,
  capacity BIGINT NOT NULL,
  occupancy_pct DOUBLE NOT NULL,
  observed_at TIMESTAMP NOT NULL,
  source_updated_at TIMESTAMP,
  source STRING NOT NULL,
  ingested_at TIMESTAMP NOT NULL
) USING DELTA;
