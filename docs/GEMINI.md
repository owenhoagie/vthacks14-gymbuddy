# Gemini recommendation explanations

Gemini is integrated into `POST /recommend` using the official Google Gen AI
Python SDK. Both live and explicit historical demo recommendations use it when
server credentials are configured. Databricks (live) or the historical profile
(demo) still computes forecasts; the deterministic scheduler still ranks windows.

## What it does

1. Compute the best workout and alternative using the existing availability,
   opening-hours, freshness, full-duration, crowd-tolerance, and preference rules.
2. Gemini calls `get_workout_options`. Return those validated options and ranking
   context. No calendar blocks, event titles, Google tokens, or source files go to Gemini.
3. Gemini calls `explain_workout` with the fixed primary/alternative IDs and a short
   qualitative explanation. Reject unexpected tools, parallel calls, incomplete
   responses, invalid IDs, extra fields, and malformed explanations. Preserve the
   original model turn (including thought signatures) in the tool-response round trip.
4. Return `method=gemini` and the explanation, copying all candidate times, numeric
   occupancy values, confidence, provenance, warnings, and generation time from
   the scheduler. The dashboard labels this “Gemini explanation · Schedule-checked.”

Gemini does not change the ranking, compute forecasts, book workouts, edit
calendars, or provide a chat interface. Explanations are model-generated prose;
validation of their format does not constitute a guarantee that every phrase is
correct. Numeric claims are excluded from prose; authoritative values appear in
the workout cards. Synthetic-data and crowd-tolerance warnings remain visible.

## Configuration

Set these only on the **API** project (`gymbuddy-api`) and the local ignored `.env`:

```dotenv
GEMINI_API_KEY=your-google-ai-studio-key
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_TIMEOUT_SECONDS=12
```

Create a key in [Google AI Studio](https://aistudio.google.com/apikey). Use the
existing free-tier project; no billing upgrade or paid service is required by this
implementation. Confirm the selected model's free-tier availability and quota in
AI Studio. The app cannot determine your project's billing tier from an API key.
It does not fall through to other models or paid providers when quota runs out.
Never put this key into a `NEXT_PUBLIC_` variable, frontend environment, or git.
Redeploy the API after changing its environment. Clearing `GEMINI_API_KEY` and
redeploying disables model calls without disabling recommendations.

## Failure and quota behavior

- No call when credentials are absent, data is stale/unavailable, or no workout fits.
- At most two model calls per uncached explanation; SDK automatic function execution
  and retries are disabled. Default timeout is 12 seconds per call.
- Any upstream error, quota failure, timeout, or validation failure returns the
  original deterministic result plus a Gemini-unavailable warning.
- One in-flight explanation per warm process; concurrent requests fall back immediately.
- Failures open a 60-second cooldown. Successful explanations are cached for five
  minutes, up to 64 entries, keyed by validated options and preferences. Scheduling
  is recomputed before every cache lookup. Calendar blocks are never cached here.
- These limits and caches are per process, not a global rate limit across Vercel
  instances. Gemini provider quotas remain the hard project-wide limit.
- `/health` makes no model requests. It reports `not_configured` without credentials,
  `unavailable` before a successful exchange or after failure, and `ready` for up to
  15 minutes after a successful validated exchange on that instance. A cold instance
  may report unavailable until it handles a recommendation.

## Verification

`python -m pytest tests/test_gemini.py` covers the tool exchange, authoritative
field preservation, privacy of tool payloads, wrong IDs, malformed/truncated
responses, no-window/missing-key skips, quota/timeout fallback, cooldown recovery,
concurrency, caching, and API/health wiring. These tests mock Google and use no quota.

On a configured deployment, open `/?mode=demo`, choose a workout length, and click
**Find my gym window**. Confirm the Gemini label, a synthetic-data warning, and
unchanged schedule constraints. A no-window result must remain deterministic.
Live recommendations use the same path whenever fresh data and opening hours
permit a workout.

References: [function calling](https://ai.google.dev/gemini-api/docs/function-calling),
[Python SDK](https://googleapis.github.io/python-genai/),
[free-tier pricing and data use](https://ai.google.dev/gemini-api/docs/pricing).
