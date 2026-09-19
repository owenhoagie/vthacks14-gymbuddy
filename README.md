# GymBuddy

**When and where should I go to the gym today?**

GymBuddy combines Virginia Tech gym occupancy, short-term forecasts, and a student's available time. FastAPI serves a Next.js dashboard with either an explicitly synthetic, credential-free demo or real VT observations and forecasts stored and computed in Databricks. Recommendations use deterministic availability and crowd ranking, with Gemini tool calls providing grounded explanations when configured.

For a nontechnical project overview and presentation talking points, read the
[team and speech-writing guide](docs/PROJECT_GUIDE.md).

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

`DATA_MODE=live` reads Databricks Bronze observations and Gold forecasts through a background snapshot refreshed every 60 seconds. Recommendations also require verified VT opening hours. During outages, snapshots and newer local observations are labeled cached and keep their original timestamps. Observations older than 15 minutes cannot support recommendations. Live mode never substitutes synthetic observations. Restart the API after changing `.env`; restart Next.js after changing its public API URL.

On this Mac, if Git reports an Xcode license issue, prefix Git commands with `DEVELOPER_DIR=/Library/Developer/CommandLineTools` to use the installed Command Line Tools.

## Configuration

Fill in the ignored root `.env`. Only `NEXT_PUBLIC_API_URL` belongs in `web/.env.local`. Never put a token or API key in a `NEXT_PUBLIC_*` variable.

| Variable | Purpose |
| --- | --- |
| `DATA_MODE` | `demo` (synthetic historical model) or `live` (Databricks with recovery cache) |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Server-side Gemini configuration; see [setup and fallback behavior](docs/GEMINI.md) |
| `DATABRICKS_HOST` | Workspace URL, including `https://` |
| `DATABRICKS_TOKEN` | Server-side token with `sql` API scope and warehouse/catalog permissions |
| `DATABRICKS_SQL_WAREHOUSE_ID` | SQL warehouse ID, not a cluster ID |
| `DATABRICKS_CATALOG`, `DATABRICKS_SCHEMA` | Writable catalog and application schema |
| `NEXT_PUBLIC_API_URL` | Browser-accessible FastAPI URL; default `http://localhost:8000` |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins |
| `COLLECTOR_INTERVAL_SECONDS` | Poll interval; default `300` |

Optional `OCCUPANCY_CSV_PATH` overrides local storage and `STALE_AFTER_MINUTES` overrides the API's 15-minute fetch-age threshold. Demo mode needs no credentials. `/health` reports Databricks connectivity from actual background queries, with degraded status for missing/stale live data; it never returns credentials.

## Commands and contracts

```sh
make collect-once  # fetch both gyms once
make test          # Python tests and frontend type check
make build         # production Next.js build
make smoke         # running API checks + three identical 75-minute recommendations
make contracts     # export FastAPI OpenAPI and regenerate TypeScript types
make fixtures      # regenerate checked-in synthetic API examples
```

Pydantic models in `api/models.py` are authoritative. `fixtures/openapi.json` and `web/lib/api-types.ts` are generated artifacts; regenerate them after contract changes. The synthetic history, evaluation report, and sample requests/responses are in `fixtures/`.

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

The [VT hours service](https://apps.students.vt.edu/rshours/) supplies date-specific opening intervals for units `1` and `2`. The adapter preserves exceptions and multiple intervals; unknown hours cannot authorize a recommendation. Live recommendations use these intervals, cached for at most 15 minutes. Failed or expired hours never authorize a workout.

The historical demo fits weekday/time-of-day patterns from 12,096 synthetic observations across nine weeks. It uses a rolling five-minute anchor and fictional opening intervals so a 75-minute scenario works at any hour. Select **Historical demo** or open `/?mode=demo`; see [docs/DEMO_HISTORY.md](docs/DEMO_HISTORY.md) for generation, held-out evaluation, and limitations. These are not actual VT opening hours. Genuine cached data always retains its original observation time; synthetic data is never described as cached live data.

## Databricks setup and operation

The configured workspace uses `DATABRICKS_CATALOG=workspace` and `DATABRICKS_SCHEMA=gymbuddy`.
The token needs the `sql` API scope. Its principal also needs CAN USE on the SQL warehouse,
USE CATALOG, USE SCHEMA, and SELECT/MODIFY/CREATE TABLE privileges on the application schema
(including ownership or sufficient privileges to replace the application view and Gold table).
Use the HTTPS workspace origin for `DATABRICKS_HOST`, without a page path or query string.

```sh
make db-init       # repeatable Bronze table, Silver view, and atomic Gold rebuild
make db-backfill   # replay real CSV observations; MERGE inserts only missing keys
make db-check      # counts and latest observation/forecast metadata, no credentials
make collect      # five-minute collection plus independent upload worker
```

After backfill and a subsequent collection are verified, set `DATA_MODE=live` in `.env`
and restart the API. No frontend credentials change. The collector uploads when Databricks
credentials are configured, independently of whether the dashboard is in demo or live mode.
`make collect-once` collects and synchronizes once. `make db-sync` retries pending uploads
and forecast refresh without fetching new VT observations.

The CSV is a durable outbox, not a disposable export. Uploads use batches of at most 100
observations and a `(facility_id, observed_at)` MERGE key. Ignored, target-specific checkpoints
advance only after confirmed writes. Malformed rows are skipped with their CSV line numbers
logged; the original file is retained. Correcting a row causes a safe replay. A failed Gold
refresh remains pending even when the Bronze upload succeeded. Local file locks serialize
sync/backfill operations. Run one collector against one CSV per workspace.

Databricks computes a 30-minute rolling mean and caps slope at ±0.25 percentage points per
minute. Gold contains 49 points per facility, five minutes apart, ending four hours after the
underlying observation. Fewer than three samples yields a flat mean and low confidence;
otherwise confidence is medium. These are heuristic estimates, not calibrated probabilities.
Raw overcapacity values are preserved; forecasts are bounded to 0–100%.

The API serves memory snapshots without warehouse queries in request handlers. It writes
validated recovery snapshots under ignored `data/`, refreshes every minute, and preserves
both observation and forecast-generation timestamps during fallback. A stalled refresh
worker stops claiming live connectivity after two minutes. API startup may briefly show
unavailable data until the first warehouse refresh completes.

To recover: restore credentials/connectivity, run `make db-sync`, and check `make db-check`
and `/health`. Do not delete the CSV or reset its timestamps. To return to the synthetic demo,
set `DATA_MODE=demo` and restart the API. This leaves real warehouse observations intact.

### Validation and hosting

Verified September 19, 2026: 88 backend tests, lint, unchanged generated contracts,
frontend type checking, and production build pass. Two backfills of the same 22 observations
left exactly 22 Bronze rows. A subsequent five-minute collection reached Bronze and Gold;
CSV, warehouse, and running API values matched, including microsecond timestamps. Real SQL
forecast boundary checks and three consecutive live 75-minute dashboard scenarios passed.
Desktop and 390px mobile checks found no browser errors or horizontal overflow. Local
screenshot evidence is under ignored `artifacts/databricks-live-*.png`.

Run `make test`, `make build`, and `make smoke`. `make contracts` regenerates contracts;
CI verifies they have not drifted. For configured workspaces, run
`.venv/bin/python -m scripts.verify_databricks` to check actual SQL cold starts, trend caps,
bounds, duplicate keys, and CSV/Bronze/Gold parity. Synthetic boundary cases use SELECT-only
inline relations and never write test observations to live tables. Run parity checks after
an upload completes, between collection cycles.

## Free cloud hosting

Live dashboard: **https://gymbuddy-vthacks14.vercel.app**

The hosting configuration uses **Vercel Hobby** for the API and dashboard, **Cloudflare Workers Free**
to trigger collection every five minutes, and **GitHub Actions** to run the collector.
See [docs/HOSTING.md](docs/HOSTING.md) for deployment commands,
environment variables, retry-outbox behavior, and cutover checks. No paid Render service is used.
Cloudflare replaces the GitHub cron trigger that never produced scheduled runs. Runner queues
can still cause delays. The scheduler token expires September 26, 2026; see
[rotation instructions](scheduler/README.md). Staleness remains based on actual
observation time, and the API does not recommend workouts using observations older than 15 minutes.

In Vercel's serverless runtime the API refreshes during requests, at most once per minute per
warm instance. It never depends on daemon threads surviving between invocations. Warm-instance
caches can provide fallback; cold starts require Databricks. Locally, `make api` and `make collect`
still support the original persistent-process mode.

| Checkpoint | State |
| --- | --- |
| VT → durable CSV → duplicate-safe Bronze upload | Implemented |
| Silver rolling features → atomic Gold forecasts | Implemented |
| Live API, real hours, cached recovery, dashboard refresh | Implemented |
| Deterministic recommendations and credential-free demo | Implemented |
| Gemini grounded tool calls | Validated workout tools + Gemini explanations, deterministic fallback |
| Calendar import / Google OAuth | Browser .ics import + Google primary-calendar free/busy; see [setup](docs/CALENDARS.md) |
| Free cloud hosting | Vercel API/dashboard + Cloudflare schedule + GitHub Actions collector; see hosting guide |

### Gemini explanations

Gemini reads the validated workout options through a tool call and explains the
primary recommendation. The scheduler retains control over ranking, times,
occupancy, and calendar conflicts. Failures fall back to the deterministic result.
Set `GEMINI_API_KEY` and `GEMINI_MODEL` on the API project only.
See [configuration, privacy, health, and verification](docs/GEMINI.md).

### Next: judging and remaining integrations

Verify the public dashboard and scheduled collection with local processes stopped. Preserve the
explicitly labeled historical demo for presentations. Conversational preference parsing
and calendar write-back remain outside the current integration.

Calendar imports and Google primary-calendar OAuth are implemented. Social features, notifications, workout generation, additional facilities, and advanced ML remain outside this migration.

## Personal schedules

Use **Bring your schedule** to import an `.ics` export or connect Google Calendar.
Recurring events, time zones, all-day events, and cancellations become unavailable periods.
Imported files and Google access stay in tab memory and clear on reload; only merged busy
start/end times are sent with a recommendation. Google reads the primary calendar and asks
for free/busy permission only. No event titles or offline access are requested.

Setup, privacy, supported formats, and verification: [docs/CALENDARS.md](docs/CALENDARS.md).
Set `NEXT_PUBLIC_GOOGLE_CLIENT_ID` on the Vercel **frontend** and rebuild to enable Google.
Run frontend calendar tests with `cd web && npm test`.
