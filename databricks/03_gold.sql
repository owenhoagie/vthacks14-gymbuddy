-- Scaffold baseline: capped +/-0.25 percentage points/minute trend, horizon 4h.
-- Rebuild every five minutes once the Bronze ingestion job is configured.
CREATE OR REPLACE TABLE {{catalog}}.{{schema}}.occupancy_forecast USING DELTA AS
WITH latest AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY facility_id ORDER BY observed_at DESC) AS rownum
  FROM {{catalog}}.{{schema}}.occupancy_features
), trend AS (
  SELECT *, CASE
    WHEN sample_count < 3 OR observed_at = first_observed_at THEN 0.0
    ELSE GREATEST(-0.25, LEAST(0.25,
      (occupancy_pct - first_pct) / ((UNIX_TIMESTAMP(observed_at) - UNIX_TIMESTAMP(first_observed_at)) / 60.0)))
    END AS slope_per_minute
  FROM latest WHERE rownum = 1
), points AS (
  SELECT *, EXPLODE(SEQUENCE(0, 240, 5)) AS offset_minutes FROM trend
)
SELECT facility_id, facility_name,
  TIMESTAMPADD(MINUTE, offset_minutes, observed_at) AS forecast_time,
  GREATEST(0.0, LEAST(100.0, rolling_mean_pct + slope_per_minute * offset_minutes)) AS predicted_occupancy_pct,
  CURRENT_TIMESTAMP() AS generated_at, observed_at,
  CASE WHEN sample_count < 3 THEN 'low' ELSE 'medium' END AS confidence
FROM points;
