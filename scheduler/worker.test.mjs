import assert from "node:assert/strict";
import test from "node:test";
import worker, { dispatchCollection } from "./worker.mjs";

const now = Date.parse("2026-09-19T20:10:00Z");
const event = { scheduledTime: now };
const env = { GITHUB_ACTIONS_TOKEN: "test-secret" };
const quiet = { log() {} };
const json = data => new Response(JSON.stringify(data));

test("scheduled tick dispatches only the fixed collector on main, with an audit timestamp", async () => {
  const calls = [], logs = [];
  const fetcher = async (url, options) => {
    calls.push({ url, ...options });
    return calls.length === 1 ? json({ workflow_runs: [] }) : new Response(null, { status: 204 });
  };
  const result = await dispatchCollection(event, env, fetcher, { log: text => logs.push(text) });
  assert.equal(result.status, "dispatched");
  assert.equal(calls.length, 2);
  assert.match(calls[1].url, /vthacks14-gymbuddy\/actions\/workflows\/collect.yml\/dispatches$/);
  assert.deepEqual(JSON.parse(calls[1].body), {
    ref: "main", inputs: { trigger_source: "cloudflare", scheduled_at: "2026-09-19T20:10:00.000Z" },
  });
  assert.equal(calls[1].headers.Authorization, "Bearer test-secret");
  assert.equal(calls[1].redirect, "manual");
  assert(!logs.join().includes("test-secret"));
});

for (const status of ["queued", "in_progress", "waiting", "pending", "requested"]) {
  test(`does not queue a duplicate behind a ${status} collector`, async () => {
    let calls = 0;
    const result = await dispatchCollection(event, env, async () => {
      calls++;
      return json({ workflow_runs: [{ id: 12, status, head_branch: "main", created_at: new Date(now - 30000).toISOString() }] });
    }, quiet);
    assert.equal(result.status, "already_running");
    assert.equal(calls, 1);
  });
}

test("reports an overdue pending run as failed", async () => {
  await assert.rejects(dispatchCollection(event, env, async () => json({ workflow_runs: [{ id: 12, status: "queued", head_branch: "main", created_at: new Date(now - 660000).toISOString() }] }), quiet), /ten minutes/);
});

test("failed previous collection is retried on the next tick", async () => {
  let calls = 0;
  const result = await dispatchCollection(event, env, async () => ++calls === 1 ? json({ workflow_runs: [{ id: 1, status: "completed", conclusion: "failure", head_branch: "main" }] }) : new Response(null, { status: 204 }), quiet);
  assert.equal(result.status, "dispatched");
});

for (const status of [301, 302, 401, 403, 429, 500, 503]) {
  test(`upstream ${status} is observable and is not retried in a loop`, async () => {
    let calls = 0;
    await assert.rejects(dispatchCollection(event, env, async () => {
      calls++; return new Response("private upstream details", { status });
    }, quiet), new RegExp(`HTTP ${status}`));
    assert.equal(calls, 1);
  });
}

test("failed dispatch and malformed run listing fail closed", async () => {
  let calls = 0;
  await assert.rejects(dispatchCollection(event, env, async () => ++calls === 1 ? json({ workflow_runs: [] }) : new Response("private", { status: 403 }), quiet), /dispatch failed/);
  await assert.rejects(dispatchCollection(event, env, async () => json({}), quiet), /invalid workflow run data/);
});

test("missing token and network failures cannot leak secrets", async () => {
  await assert.rejects(dispatchCollection(event, {}, async () => { throw new Error("must not fetch"); }, quiet), /not configured/);
  await assert.rejects(dispatchCollection(event, env, async () => { throw new Error("test-secret"); }, quiet), error => !error.message.includes("test-secret"));
});

test("no public HTTP endpoint can trigger collection", async () => {
  assert.equal((await worker.fetch(new Request("https://example.com/collect"))).status, 404);
});
