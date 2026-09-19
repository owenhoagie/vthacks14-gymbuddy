# GymBuddy Databricks pipeline

Run `make db-init`, `make db-backfill`, then `make collect`. The existing root `.env`
selects the workspace, warehouse, catalog, and schema. SQL values use named parameters;
identifiers are separately validated. Credentials stay server-side.

- **Bronze `raw_occupancy`**: Delta table; immutable observations inserted with an
  idempotent `(facility_id, observed_at)` MERGE. `ingested_at` is separate from fetch time.
- **Silver `occupancy_features`**: view with 30-minute rolling mean, count, and first sample.
- **Gold `occupancy_forecast`**: Delta table atomically replaced after ingestion. Five-minute
  points through four hours after each facility's observation, rolling mean plus capped
  ±0.25 percentage points/minute slope, clamped to 0–100. Fewer than three samples uses a
  flat mean and low confidence; otherwise confidence is medium.

The independent local upload worker checks for pending rows every 60 seconds. Polling VT
continues every five minutes even when the warehouse is unavailable. Confirmed writes advance
an atomic checkpoint; failed forecast refreshes remain pending. Full backfill is safe to repeat.
A local lock serializes initialization, upload, and rebuild for the configured CSV/target.
No Databricks Job or cloud collector is installed by this milestone.

`make db-check` prints counts and current warehouse data. `make db-sync` retries pending work.
`.venv/bin/python -m scripts.verify_databricks` tests the actual forecast SQL using temporary
inline SELECT relations (no writes), then checks real CSV/Bronze/Gold parity and duplicate keys.

Never replace the CSV with synthetic fixtures. Unknown source measurement timestamps remain
null. Rebuilding Gold does not refresh the underlying observation timestamp, and the API
excludes forecasts backed by observations older than 15 minutes.

References: [Statement Execution API](https://docs.databricks.com/aws/en/dev-tools/sql-execution-tutorial),
[Python SDK](https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/statement_execution.html),
[AI Dev Kit](https://github.com/databricks-solutions/ai-dev-kit).
