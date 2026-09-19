-- Rolling statistics over the previous 30 minutes, for each observation.
CREATE OR REPLACE VIEW {{catalog}}.{{schema}}.occupancy_features AS
SELECT *,
  AVG(occupancy_pct) OVER history AS rolling_mean_pct,
  COUNT(*) OVER history AS sample_count,
  FIRST_VALUE(occupancy_pct) OVER history AS first_pct,
  FIRST_VALUE(observed_at) OVER history AS first_observed_at
FROM {{catalog}}.{{schema}}.raw_occupancy
WINDOW history AS (
  PARTITION BY facility_id ORDER BY UNIX_TIMESTAMP(observed_at)
  RANGE BETWEEN 1800 PRECEDING AND CURRENT ROW
);
