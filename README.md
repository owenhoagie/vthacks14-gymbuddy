# GymBuddy

**When and where should I go to the gym today?**

GymBuddy combines Virginia Tech gym occupancy, short-term forecasts, and a student's available time. This repository is the runnable baseplate: a real occupancy collector and a credential-free, synthetic-demo dashboard backed by FastAPI. Databricks and Gemini integration are the next milestones; adding keys alone does not activate those integrations yet.

## Run locally

Requires Python 3.11+ and Node 20.9+ (Node 22 or 24 recommended).

```sh
make install
cp .env.example .env
cp web/.env.local.example web/.env.local
```

Start each process in its own terminal, from the repository root:

```sh
make api       # http://localhost:8000; interactive API docs at /docs
make web       # http://localhost:3000
make collect   # real VT observations, every five minutes
```

`DATA_MODE=demo` is the default: the dashboard works without any credentials and always labels its data as synthetic. The collector independently gathers real data into `data/occupancy_raw.csv`; it does not replace synthetic demo data. Keep the collector running to accumulate history.

`DATA_MODE=live` reads the collector's saved observations with a cached label and their original timestamps. Forecasts and recommendations are unavailable until the Databricks milestone is completed. Live mode never substitutes synthetic observations. Restart the API after changing `.env`; restart Next.js after changing its public API URL.

On this Mac, if Git reports an Xcode license issue, prefix Git commands with `DEVELOPER_DIR=/Library/Developer/CommandLineTools` to use the installed Command Line Tools.

## Configuration

Fill in the ignored root `.env`. Only `NEXT_PUBLIC_API_URL` belongs in `web/.env.local`. Never put a token or API key in a `NEXT_PUBLIC_*` variable.

| Variable | Purpose |
| --- | --- |
| `DATA_MODE` | `demo` (synthetic fixtures) or `live` (collector cache; integrations pending) |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Server-side Gemini configuration, reserved for the next integration milestone |
| `DATABRICKS_HOST` | Workspace URL, including `https://` |
| `DATABRICKS_TOKEN` | Databricks access token; leave blank until available |
| `DATABRICKS_SQL_WAREHOUSE_ID` | SQL warehouse ID, not a cluster ID |
| `DATABRICKS_CATALOG`, `DATABRICKS_SCHEMA` | Writable catalog and application schema |
| `NEXT_PUBLIC_API_URL` | Browser-accessible FastAPI URL; default `http://localhost:8000` |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins |
| `COLLECTOR_INTERVAL_SECONDS` | Poll interval; default `300` |

Optional `OCCUPANCY_CSV_PATH` overrides local storage and `STALE_AFTER_MINUTES` overrides the API's 15-minute fetch-age threshold. Missing credentials are normal in the baseplate. `/health` reports configuration and implementation status without returning credentials or claiming connectivity was verified.

## Commands and contracts

```sh
make collect-once  # fetch both gyms once
make test          # Python tests and frontend type check
make build         # production Next.js build
make smoke         # running API checks + three identical 75-minute recommendations
make contracts     # export FastAPI OpenAPI and regenerate TypeScript types
make fixtures      # regenerate checked-in synthetic API examples
```

Pydantic models in `api/models.py` are authoritative. `fixtures/openapi.json` and `web/lib/api-types.ts` are generated artifacts; regenerate them after contract changes. The JSON demo template and sample requests/responses are in `fixtures/`.

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Mode and integration configuration status |
| `GET /occupancy` | Both gyms, counts, fetch times, provenance, and staleness |
| `GET /forecast` | Optional facility/time filtering; bounded forecast points and confidence |
| `POST /recommend` | Availability-aware recommendation, alternative, explanation, warnings |

Public facility IDs are `mccomas` and `war_memorial`; display names are McComas Hall and War Memorial Hall. Inputs must contain timezone offsets. Timestamps are serialized in UTC and the dashboard displays America/New_York time, independent of the browser timezone. Errors use `{ "error": { "code": "...", "message": "...", "details": ... } }`.

The deterministic engine checks the entire workout against opening hours, unavailable blocks, and forecast coverage. It considers starts every five minutes, averages predicted occupancy across the whole workout, gives preferred gyms a five-percentage-point ranking bonus, and breaks ties by earliest start. Crowd limits are 40%, 65%, and 85%. If every candidate exceeds tolerance, the result explicitly warns the user. Confidence labels are heuristic, not calibrated probabilities.

## Real data and honest demo behavior

The collector POSTs directly to [VT RecSports](https://connect.recsports.vt.edu/facilityoccupancy)' `/FacilityOccupancy/GetFacilityData` endpoint. The response is HTML, not JSON. It parses both facilities by their verified IDs, deduplicates responsive canvases, preserves above-capacity counts, and durably appends successful observations independently. Failed requests leave prior observations intact.

- McComas: `232d714e-5b3e-4b0d-9936-e6a738150ec4`
- War Memorial, upstream “WMH Service Desk”: `55069633-b56e-43b7-a68a-64d79364988d`

VT does not supply a verified measurement timestamp. `observed_at` records when fetching succeeded; `source_updated_at` stays null. A recent fetch does **not** prove that upstream counters changed recently. Counts estimate occupancy from access records. The dashboard reports fetch time rather than claiming measurement freshness.

The [VT hours service](https://apps.students.vt.edu/rshours/) supplies date-specific opening intervals for units `1` and `2`. The adapter preserves exceptions and multiple intervals; unknown hours cannot authorize a recommendation. It will be wired to live recommendations with the Gold forecast reader.

Synthetic demo fixtures use a rolling five-minute anchor and explicit simulated opening intervals so the demo works at any hour. They do not represent actual VT opening hours. Use the dashboard's demo scenario to reproduce a 75-minute recommendation. Genuine cached data always retains its original observation time; synthetic data is never described as cached live data.

## Revised delivery checkpoints

Verified locally on September 19, 2026: 53 Python tests, Python lint, frontend
type-check, and production build passed. Browser checks passed on desktop and a
390px viewport, including three consecutive 75-minute recommendations with the
supplied schedule, a fully blocked day, and API failure/recovery. Screenshot
evidence is saved locally under ignored `artifacts/`. Databricks, Gemini, and
external deployment have not been live-verified.

| Checkpoint | Baseplate state |
| --- | --- |
| VT endpoint → parsed observations → local CSV | Implemented; live collection verified |
| Frozen contracts → mock-backed API → dashboard | Implemented |
| Deterministic scheduling and degraded states | Implemented |
| Databricks Bronze → Silver → Gold | Scaffolded; credential-backed execution pending |
| Actual Gemini grounded tool calls | Interface only; implementation and live verification pending |
| Live data → Databricks → Gemini → dashboard | Pending integration |
| External deployment | Pending; local application is the known-good fallback |

### Next: Databricks

Use the [SQL Statement Execution API](https://docs.databricks.com/aws/en/dev-tools/sql-execution-tutorial) against the configured warehouse. Implement bounded polling of asynchronous statements and parameterized data values. Validate identifier configuration separately. Backfill the CSV with an idempotent `(facility_id, observed_at)` key and retain local observations until writes are verified.

Keep Databricks visibly central: Bronze `raw_occupancy`, Silver `occupancy_features`, Gold `occupancy_forecast`. Produce five-minute predictions over the next four hours using rolling mean plus capped slope, bounded to 0–100%, with low-confidence current-value cold starts. Do not synthesize missing observations. Query Gold through the repository interface and cache successful responses with their original generation and observation times. Start with manual/on-demand transformations; add Jobs only after the full flow works.

### Then: Gemini

Use the actual Gemini API with deterministic tools for occupancy, forecasts, gym comparison, availability, and candidate ranking. Only pass validated candidates to final selection. Validate returned facility/time selections against those candidates and copy all numeric values from authoritative tool output. Timeout, malformed output, or service failure falls back to the deterministic result with an explicit method label. Do not send secrets in model prompts.

### Finally: deployment and judging

Deploy `web/` to Vercel, FastAPI to Render, and the collector as a separate persistent worker. Configure public API URL, exact CORS origins, server-side credentials, and durable storage. Never run a continuous collector inside a request handler or a Next.js serverless function. Verify a real Databricks row, Gold forecast, Gemini tool call, and external browser flow before calling the MVP live. Repeat the known-good scenario three times; retain the clearly labeled synthetic demo and cached-data fallback.

Do not add authentication, calendar OAuth, social features, notifications, workout generation, additional facilities, or advanced ML before that end-to-end milestone passes.
