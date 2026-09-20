# Free collector fallback

On September 20 the Databricks Free Edition warehouse exhausted its daily compute allowance. VT collection and the Cloudflare five-minute trigger still worked, but warehouse reads and writes failed. The warehouse start API confirmed the daily limit.

## Current live path

Cloudflare triggers the GitHub collector every five minutes. Each successful VT fetch is saved to the retry CSV with its original timestamp. The collector combines real observations with the previous 48 hours of real history, then publishes `snapshot.json` and `history.csv` to the `live-data` branch. That branch contains no credentials and disables Vercel deployments. The application remains on `main`.

Forecasts use a 30-minute mean and a trend capped at +/-0.25 percentage points per minute, with five-minute points through four hours. Fewer than three samples produces a flat forecast at the latest observed percentage. Predictions stay between 0 and 100. All fallback forecasts have low confidence and an explicit `collector_fallback` source. No synthetic observations enter this path.

The API uses `LIVE_DATA_SOURCE=collector_fallback` to read the public snapshot at most once a minute per warm instance. Original observation and generation times are preserved. Its usual 15-minute staleness checks and verified VT opening hours still gate recommendations. Failed reads retain the last valid snapshot. Health reports Databricks unavailable separately from fallback readiness.

`SKIP_DATABRICKS=true` in the collector workflow pauses warehouse calls. The retry artifact is never cleared in this mode, preserving the backlog for a later idempotent backfill. The public 48-hour history is a separate bounded copy. No paid resources were enabled.

## Recovery and verification

- Check the latest `Collect live occupancy` workflow: both collection and public snapshot publication must pass.
- Inspect `https://gymbuddy.work/api/health`: `collector_fallback` should be ready.
- Check `/api/occupancy` timestamps and `/api/forecast` source. Cached provenance describes a published real-data snapshot, not synthetic data.
- A stale/missing snapshot must not produce a recommendation.

## Returning to Databricks

After its quota resets, first verify the warehouse can execute a read. Download the newest `gymbuddy-outbox` artifact and backfill its CSV with `OCCUPANCY_CSV_PATH=PATH python -m scripts.databricks backfill`. Verify Bronze and Gold before setting the API's `LIVE_DATA_SOURCE=databricks` and redeploying. Set workflow `SKIP_DATABRICKS=false` only when warehouse ingestion is confirmed. Replaying observations is idempotent. Keep the free fallback available because five-minute warehouse workloads can exhaust the daily allowance again.

## Opening hours

Live occupancy cards also check VT's public facility-hours service. They show
Open now, Closed now, or Hours unavailable, plus a known opening or closing time
in Eastern Time. A closed gym shows Closed instead of a prominent occupancy
percentage; its last reported headcount and fetch timestamp remain visible.
Hours are cached for at most 15 minutes. Missing, malformed, or expired hours
never imply that a gym is open. Explicit closures are distinguished from missing
schedules. Recommendations still require the entire workout to fit inside a
verified opening interval, even when the reported occupancy is zero. A future
recommendation for a currently closed gym explicitly tells the user to wait.
The historical demo uses its own clearly labeled fictional hours.
