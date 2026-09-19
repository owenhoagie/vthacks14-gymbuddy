# Free automatic collection

Cloudflare's `gymbuddy-collector-scheduler` Worker runs `*/5 * * * *` in UTC.
It dispatches only `collect.yml` on `owenhoagie/vthacks14-gymbuddy`'s `main` branch.
The GitHub job still fetches VT, preserves its retry outbox, uploads to Bronze,
and refreshes Gold. No Mac or open browser is required.

## Credentials

Cloudflare Worker secret `GITHUB_ACTIONS_TOKEN` is a **fine-grained GitHub token**:

- Resource owner: `owenhoagie`
- Repository: only `vthacks14-gymbuddy`
- Repository permission: **Actions: Read and write** (Metadata: Read-only is automatic)
- No contents write, account permissions, or Databricks/Gemini credentials

The initial token expires **September 26, 2026**. Replace it before then if the
project stays running after the hackathon. Do not commit or log the token.

## Deploy

```sh
cd scheduler
npm ci
npm test
npx wrangler login --scopes account:read user:read workers_scripts:write workers_tail:read
npm run deploy
# Paste the fine-grained token at Wrangler's hidden prompt:
npx wrangler secret put GITHUB_ACTIONS_TOKEN
```

The secret can also be set in Cloudflare → Workers & Pages →
`gymbuddy-collector-scheduler` → Settings → Variables and Secrets.

Use the existing Workers Free plan. The Worker makes at most two GitHub API
requests per tick (288 ticks/day), performs no heavy compute, and uses no paid
storage, queues, AI, custom domains, or Vercel cron upgrades. Provider free-tier
quotas still apply; deployment must not upgrade the account.

## Behavior and verification

- A pending collector is not duplicated. A pending run older than ten minutes
  fails the Cron event so the problem is visible instead of reported as healthy.
- Failed HTTP requests and rejected credentials fail the Cron event. No secrets
  or upstream error bodies are logged. The next scheduled tick tries again.
- There is no public HTTP trigger (`workers_dev` and preview URLs are disabled).
- Worker logs distinguish `collector_dispatched` from `collector_already_running`.
- GitHub run titles contain `cloudflare` and the original UTC scheduled time.
- GitHub job completion must be checked separately: a successful dispatch alone
  does **not** prove that VT was fetched or forecasts refreshed.
- Cloudflare Cron changes can take up to 15 minutes to propagate. Wait for real
  ticks; a local test or manual workflow dispatch is not scheduler verification.

```sh
npm run logs
# In the repository root:
gh run list --workflow collect.yml --limit 10 --json displayTitle,status,conclusion,createdAt
.venv/bin/python -m scripts.databricks check
curl https://gymbuddy-api-umber.vercel.app/health
```

Verify two consecutive Cloudflare-triggered runs, advancing observation times in
Bronze and Gold, and `/forecast` reporting `stale: false`. The API reads a new
warehouse snapshot at most once per minute, so dashboard freshness can trail
collection by that amount.

## Operations

GitHub Actions still supplies the runner and artifact outbox. If GitHub runner
queues are delayed, Cloudflare cannot make them run instantly. The scheduler
removes the missing GitHub cron trigger, not every external-service dependency.
The app continues to reject observations older than 15 minutes.

If collection stops, inspect Cloudflare invocation errors, token expiration, the
GitHub run, then Databricks connectivity/quota. `gh workflow run collect.yml` is a
manual recovery action; it does not fix automatic scheduling. Keep failed outbox
artifacts for retries. To stop automatic collection, remove the Cron Trigger
in Cloudflare or deploy with `triggers.crons: []`.

Sources: [Cloudflare Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/),
[Workers Free limits](https://developers.cloudflare.com/workers/platform/limits/),
[GitHub workflow dispatch](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event).
