# Databricks integration checkpoint

These SQL templates and the repository boundary are **scaffolding**, not an active
or live-verified integration. Set the five `DATABRICKS_*` environment values when
available; `/health` still reports `not_implemented` until the adapter is wired.

The collector already appends real observations to ignored
`data/occupancy_raw.csv`. Never overwrite the CSV to retry an upload: it is the
backfill source of truth. `source_updated_at` remains null because VT does not
provide a verified measurement timestamp.

## Next implementation steps

1. Implement `api/databricks.py` with the SQL Statement Execution API. Send SQL to
   `/api/2.0/sql/statements` with warehouse ID and named value parameters; poll
   pending/running statements by statement ID until success, error, or bounded
   timeout. Handle chunked result retrieval, cancellation, and rate-limit retry.
2. Validate catalog and schema identifiers, substitute the SQL templates, then
   execute `01_bronze.sql`, `02_silver.sql`, `03_gold.sql` in order. Restrict the
   configured token to the required warehouse and schema.
3. Read CSV observations in bounded batches; validate numeric values and aware
   timestamps. Deduplicate by `(facility_id, observed_at)` before a parameterized
   `MERGE INTO raw_occupancy` keyed on the same pair. Insert only unmatched
   rows, recording `ingested_at` separately. Re-running the same CSV must produce
   zero extra rows. Keep a local checkpoint only after confirmed SQL success.
4. Recompute Gold after ingestion; verify Silver windows and forecast bounds.
   Gold inherits the observation time: a new `generated_at` does not make old
   measurements fresh. Serve stale/unavailable state explicitly.
5. Add remote integration tests with a dedicated test schema: two identical
   backfills, mixed valid/malformed CSV, asynchronous failure/timeout, empty
   history, sparse cold start, and stale observations. Compare fixture and live
   contract shapes before enabling the repository.

The supplied baseline clamps forecast percentages to 0–100 while raw occupancy
retains overcapacity values. Sparse histories (<3 observations in 30 minutes)
use a flat mean with low confidence. Model tuning and richer schedules are later
work; this baseplate makes no accuracy claim.

Official reference: https://docs.databricks.com/aws/en/dev-tools/sql-execution-tutorial
