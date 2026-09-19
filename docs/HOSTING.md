# Free GymBuddy hosting

Live dashboard: [GymBuddy](https://gymbuddy.work)

Fallback Vercel URL: https://gymbuddy-vthacks14.vercel.app

Live API health: [health check](https://gymbuddy-api-umber.vercel.app/health)

## Custom domain

`gymbuddy.work` is registered with Porkbun through the MLH domain offer and attached
to the existing `gymbuddy-vthacks14` Vercel project. Porkbun hosts its DNS; the root
A record points to `76.76.21.21` with a 600-second TTL. Vercel provides HTTPS. No
additional hosting plan or nameserver change is required.

Registration expires September 19, 2027; renewal is separate from free hosting.
The Google Calendar OAuth client also needs `https://gymbuddy.work` as an authorized
JavaScript origin. Saving that change is pending owner confirmation; the existing
Vercel origin remains available for Calendar sign-in. See [calendar setup](CALENDARS.md).

Verified on September 19, 2026: custom-domain HTTPS, live occupancy and forecasts,
Databricks/Gemini health, and a 75-minute recommendation rendered in the browser.

## Architecture

- **Vercel Hobby — API:** `gymbuddy-api`, FastAPI, repository root.
- **Vercel Hobby — dashboard:** `gymbuddy-vthacks14`, Next.js, `web/` directory.
- **Cloudflare Workers Free — scheduler:** Cron Trigger every five minutes, starting the collector through GitHub’s API.
- **GitHub Actions — collector:** `Collect live occupancy` in this public repository, using a standard Ubuntu runner and durable artifact retry buffer.
- **Databricks:** existing workspace and SQL warehouse; no new paid resources are provisioned.

The dashboard forwards `/api/*` to server-side `GYMBUDDY_API_URL`. Only the API project
and collector workflow receive Databricks credentials. Production credentials are not supplied
to preview deployments. No Render service, paid cron plan, or paid storage is required.

GitHub’s original cron trigger produced no scheduled runs. Cloudflare now supplies the trigger;
see [scheduler setup and operations](../scheduler/README.md). GitHub runner queues can still be
delayed, so this remains a best-effort five-minute service, not a strict timing guarantee.
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
GYMBUDDY_API_URL=https://gymbuddy-api-umber.vercel.app
```

Deploy using the linked `web/` project. The public production alias is stable across deployments.
Do not set the production API URL to localhost or upload local `.env` files. No Databricks token
belongs in the frontend project. The API proxy preserves query parameters, request bodies, and
validation errors, and exposes only health, occupancy, forecast, and recommendation routes.

## Scheduled collector

Cloudflare dispatches this workflow every five minutes using a repository-scoped Actions token.
The existing `DATABRICKS_*` settings remain GitHub Actions repository secrets. The workflow:

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
vercel deploy --prod --scope owens-projects-92ce76bd --cwd web --local-config "$PWD/web/vercel.json"
```

Pass the frontend configuration explicitly so the CLI does not inherit the repository-root
FastAPI configuration. The dashboard currently deploys through the CLI; pushing to GitHub
runs CI and updates the collector workflow, but does not publish dashboard changes.

Verify the hosted API, three 75-minute dashboard requests, and remote collector runs reaching
Bronze and Gold. Synchronize the last local outbox before stopping the local collector; never
stop it merely because a deployment has built. Verify another cloud collection with the local
collector stopped. Resume local collection only if cloud collection is disabled or unavailable.

References: [GitHub scheduling](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows),
[GitHub free runner usage](https://docs.github.com/en/actions/concepts/billing-and-usage),
[Vercel FastAPI](https://vercel.com/docs/frameworks/backend/fastapi).

## Verified deployment — September 19, 2026

Both projects deployed successfully on the existing Hobby account. GitHub CI passed all
88 backend tests, lint, contract drift checking, frontend type checking, and production build.
The cloud collector fetched both facilities and updated Bronze and Gold with the Mac collector
stopped. Hosted API counts and microsecond observation timestamps matched the warehouse.
Three consecutive 75-minute requests through the public dashboard returned valid live
recommendations. Desktop and 390px mobile checks found no browser errors or horizontal overflow.
The previous local outbox was fully synchronized before cutover. No paid hosting was provisioned.
