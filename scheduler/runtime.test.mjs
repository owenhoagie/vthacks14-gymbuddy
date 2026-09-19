import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { Miniflare, convertV4MiniflareOptions } from "miniflare";

const source = await readFile(new URL("./worker.mjs", import.meta.url), "utf8");
// Exercise the production dispatch code with workerd's native fetch implementation.
// Only outbound transport is mocked; no real credentials or GitHub calls are used.
const script = source.replace("export default {", "const worker = {") + `
export default { async fetch() {
  try {
    return Response.json(await dispatchCollection(
      {scheduledTime: Date.parse("2026-09-19T20:20:00Z")},
      {GITHUB_ACTIONS_TOKEN: "runtime-test-token"}, undefined, {log() {}}
    ));
  } catch (error) { return new Response(error.message, {status: 502}); }
}};`;

for (const redirect of [false, true]) {
  test(`Cloudflare runtime ${redirect ? "rejects redirects without forwarding credentials" : "dispatches through native fetch"}`, async () => {
    const calls = [];
    const mf = new Miniflare(convertV4MiniflareOptions({
      modules: true, compatibilityDate: "2026-09-19", script,
      outboundService: async request => {
        calls.push(request.url);
        if (redirect) return new Response(null, {status: 302, headers: {Location: "https://unexpected.example/"}});
        return request.method === "POST"
          ? new Response(null, {status: 204})
          : Response.json({workflow_runs: []});
      },
    }));
    try {
      const response = await mf.dispatchFetch("http://localhost");
      assert.equal(response.status, redirect ? 502 : 200);
      if (redirect) assert.match(await response.text(), /HTTP 302/);
      else assert.equal((await response.json()).status, "dispatched");
      assert.equal(calls.length, redirect ? 1 : 2);
      assert(calls.every(url => url.startsWith("https://api.github.com/")));
    } finally {
      await mf.dispose();
    }
  });
}
