# Free GymBuddy hosting

## Architecture

- **Vercel Hobby — API:** `gymbuddy-api`, FastAPI, repository root.
- **Vercel Hobby — dashboard:** `gymbuddy-vthacks14`, Next.js, `web/` directory.
- **GitHub Actions — collector:** `Collect live occupancy` in this public repository,
  standard Ubuntu runner, scheduled every five minutes at minutes 2, 7, 12, …, 57.
- **Databricks:** existing workspace and SQL warehouse; no new paid resources are provisioned.

The dashboard forwards `/api/*` to server-side `GYMBUDDY_API_URL`. Only the API project
and collector workflow receive Databricks credentials. Production credentials are not supplied
to preview deployments. No Render service, paid cron plan, or paid storage is required.

GitHub schedules are best effort: runs can be delayed or dropped, and GitHub disables scheduled
workflows after 60 days without repository activity. This is not a guaranteed five-minute service.
The dashboard uses actual fetch timestamps, marks observations stale after 15 minutes, and
refuses stale forecasts for recommendations. Account quotas and existing Databricks trial/token
expiration still apply; there is no automatic paid upgrade.

## Vercel API

Environment variables, production only:

```dotenv
DATA_MODE=live
API_RUNTIME=serverless
OCCUPANCY_CSV_PATH=/tmp/gymbuddy/occupancy_raw.csv
CORS_ORIGINS=
DATABRICKS_HOST=<existing workspace origin>
DATABRICKS_TOKEN=<existing token>
DATABRICKS_SQL_WAREHOUSE_ID=<existing warehouse ID>
DATABRICKS_CATALOG=workspace
DATABRICKS_SCHEMA=gymbuddy
```

`API_RUNTIME=serverless` disables background refresh threads. Requests perform a serialized
refresh at most once per minute per warm instance; recommendation requests also refresh opening
hours when their 15-minute cache expires. Warm memory and `/tmp` snapshots can provide cached
fallback, but neither is durable across cold starts. Databricks remains authoritative; a fresh
instance with an unavailable warehouse reports unavailable data instead of inventing it.

The existing local API keeps `API_RUNTIME=persistent`, its default. Local development and
its durable CSV outbox continue to work independently.

## Vercel dashboard

Production environment:

```dotenv
NEXT_PUBLIC_API_URL=/api
GYMBUDDY_API_URL=https://<verified-production-api-alias>
```

Deploy using the linked `web/` project. The public production alias is stable across deployments.
Do not set the production API URL to localhost or upload local `.env` files. No Databricks token
belongs in the frontend project. The API proxy preserves query parameters, request bodies, and
validation errors, and exposes only health, occupancy, forecast, and recommendation routes.

## Scheduled collector

The five existing `DATABRICKS_*` settings are GitHub Actions repository secrets. The workflow:

1. Restores the newest `gymbuddy-outbox` artifact from the default branch.
2. Fetches both VT facilities and saves each successful observation to CSV immediately.
3. MERGEs the outbox into Bronze and refreshes Gold using the existing adapter.
4. Clears only observations whose upload and forecast refresh succeeded.
5. Saves the remaining outbox even when upload fails. Keeps only the newest two artifacts,
   each with seven-day retention, to bound artifact storage usage.

No credentials are included in artifacts. Do not delete a nonempty outbox during an outage.
If artifact restoration fails, collection does not proceed with an empty replacement. Outbox
recovery depends on GitHub artifact retention/availability; after seven days with no runs,
unuploaded observations can expire. Confirmed history remains in Databricks.

Run manually or inspect status:

```sh
gh workflow run collect.yml
gh run list --workflow collect.yml --limit 5
```

Keep this repository public to retain free standard hosted-runner minutes. The workflow refuses
to run when the repository is private. No schedule runs on pull requests.

## Deployment and cutover

```sh
vercel deploy --prod --scope owens-projects-92ce76bd
vercel deploy --prod --scope owens-projects-92ce76bd --cwd web
```

Verify the hosted API, three 75-minute dashboard requests, and remote collector runs reaching
Bronze and Gold. Synchronize the last local outbox before stopping the local collector; never
stop it merely because a deployment has built. Verify another cloud collection with the local
collector stopped. Resume local collection only if cloud collection is disabled or unavailable.

References: [GitHub scheduling](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows),
[GitHub free runner usage](https://docs.github.com/en/actions/concepts/billing-and-usage),
[Vercel FastAPI](https://vercel.com/docs/frameworks/backend/fastapi).
