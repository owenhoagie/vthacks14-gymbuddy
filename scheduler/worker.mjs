// The Worker only starts a fixed workflow on a fixed repository's main branch.
// VT collection, durable retries, and Databricks writes remain in that workflow.
const WORKFLOW = "https://api.github.com/repos/owenhoagie/vthacks14-gymbuddy/actions/workflows/collect.yml";
const PENDING = new Set(["queued", "in_progress", "waiting", "pending", "requested"]);

export async function dispatchCollection(event, env, fetcher = fetch, log = console) {
  if (!env.GITHUB_ACTIONS_TOKEN) throw new Error("Scheduler token is not configured");
  const headers = {
    Authorization: `Bearer ${env.GITHUB_ACTIONS_TOKEN}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "GymBuddy-Cloudflare-Scheduler",
    "Content-Type": "application/json",
  };
  const request = async (url, options = {}) => {
    try {
      return await fetcher(url, {
        // Workers supports manual redirects; reject 3xx through the status checks below.
        ...options, headers, redirect: "manual", signal: AbortSignal.timeout(20000),
      });
    } catch {
      // Never log request headers, raw upstream exceptions, or response bodies.
      throw new Error("GitHub scheduler request failed or timed out");
    }
  };
  const runsResponse = await request(`${WORKFLOW}/runs?branch=main&per_page=10`);
  if (!runsResponse.ok) throw new Error(`GitHub run check failed (HTTP ${runsResponse.status})`);
  let runs;
  try {
    const payload = await runsResponse.json();
    if (!Array.isArray(payload.workflow_runs)) throw new Error();
    runs = payload.workflow_runs;
    if (runs.some(run => typeof run.status !== "string" || typeof run.id !== "number")) throw new Error();
  } catch {
    throw new Error("GitHub returned invalid workflow run data");
  }
  const pending = runs.find(run => run.head_branch === "main" && PENDING.has(run.status));
  const scheduledAt = new Date(event.scheduledTime).toISOString();
  if (pending) {
    // An overdue GitHub queue is observable as a failure, not a healthy collection.
    const age = event.scheduledTime - Date.parse(pending.created_at);
    if (!Number.isFinite(age) || age > 10 * 60 * 1000) {
      throw new Error("Collector run is still pending after ten minutes");
    }
    log.log(JSON.stringify({ event: "collector_already_running", scheduled_at: scheduledAt, run_id: pending.id }));
    return { status: "already_running", run_id: pending.id };
  }
  const response = await request(`${WORKFLOW}/dispatches`, {
    method: "POST",
    body: JSON.stringify({ ref: "main", inputs: { trigger_source: "cloudflare", scheduled_at: scheduledAt } }),
  });
  if (response.status !== 204) throw new Error(`Collector dispatch failed (HTTP ${response.status})`);
  log.log(JSON.stringify({ event: "collector_dispatched", scheduled_at: scheduledAt }));
  return { status: "dispatched", scheduled_at: scheduledAt };
}

export default {
  async scheduled(event, env, ctx) {
    // Rejections mark the actual Cron event failed in Cloudflare observability.
    ctx.waitUntil(dispatchCollection(event, env));
  },
  async fetch() {
    return new Response("Not found", { status: 404 });
  },
};
