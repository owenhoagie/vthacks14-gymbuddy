# Calendar setup and verification

## Google Cloud setup (no paid hosting required)

1. In Google Cloud Console, select a project and enable **Google Calendar API**.
2. Configure Google Auth Platform branding: name **GymBuddy**, your support email,
   and developer contact email. Use **External / Testing** and add each demo user's
   Google account under **Audience → Test users**.
3. Under Data Access add only `https://www.googleapis.com/auth/calendar.freebusy`.
4. Create an OAuth client of type **Web application**, named **GymBuddy Web**.
5. Add authorized JavaScript origins (no path or trailing slash):
   - `https://gymbuddy.work` (custom domain; saving this origin is pending owner confirmation)
   - `https://gymbuddy-vthacks14.vercel.app`
   - `http://localhost:3000`
6. No redirect URI is required for the Google Identity Services token popup model.
7. Set `NEXT_PUBLIC_GOOGLE_CLIENT_ID` to the client ID ending in
   `.apps.googleusercontent.com` in the **frontend** Vercel project's production
   environment, then rebuild/deploy it. For local development use `web/.env.local`.
   This client ID is public. Do not supply a client secret, API key, or refresh token.

Optional consent screen links: app home `https://gymbuddy-vthacks14.vercel.app`,
privacy policy `https://gymbuddy-vthacks14.vercel.app/privacy`.
An organization-managed account may require administrator approval. Public rollout beyond
the test audience may require Google's OAuth verification; testing mode is for the demo.

## User behavior and privacy

- `.ics` is parsed in an isolated browser worker with a 5-second timeout, 1 MB file cap,
  2,000-event cap, and 20,000 recurrence-step cap. It never uploads the source file.
- Weekly/daily and other RFC recurrence rules, EXDATE, RDATE, moved/canceled instances,
  UTC, embedded VTIMEZONE, IANA TZIDs, all-day and overnight events are supported.
  All-day ends are exclusive. Floating times default to America/New_York, or the
  export's X-WR-TIMEZONE. Ambiguous wall times choose the earlier instant; nonexistent
  times fail. Transparent and canceled events do not block workouts.
- Recurrence range overrides, period-valued RDATE, unknown zones, duplicate revisions,
  incomplete/malformed files, and overly complex recurrence expansions fail explicitly.
  Replacing a file succeeds atomically; a bad replacement retains the prior file.
- Google requests only free/busy access, reads the **primary calendar** directly from
  Google, and never requests event titles, descriptions, email, write access, or offline
  access. Additional/shared calendar selection is outside this initial integration.
- Access tokens and parsed source files stay in tab memory. Reloading clears them.
  No tokens in localStorage, cookies, server storage, logs, URLs, or Databricks.
- Every recommendation re-expands the file for the current four-hour horizon and refreshes
  Google busy times. Expired tokens, incomplete Google responses, or calendar failures
  block that request until reconnect, retry, or explicit source removal.
- Manual and imported intervals are clipped, deduplicated, and merged before the API's
  50-interval limit. Only UTC start/end pairs are sent to the recommendation API.
- Disconnect clears local access and attempts Google consent revocation. If revocation
  fails, use the Google Account connections link to remove the saved grant.

## Checks

`cd web && npm test` checks recurrence, exceptions, DST, timezone definitions, all-day and
overnight clipping, invalid/oversized inputs, interval merging, and Google failure handling.
Also run typecheck/build and verify file import → recommendation → remove in a browser.
Google consent must be checked with a configured client and a real test user; mocked token
and FreeBusy responses only verify integration behavior, not Google app configuration.

References: [Google token model](https://developers.google.com/identity/oauth2/web/guides/use-token-model),
[FreeBusy API](https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query),
[ICAL.js](https://github.com/kewisch/ical.js).

## Implementation verification — September 19, 2026

88 backend tests, 17 calendar tests, type checking, production build, and contract drift
checks passed. Browser checks verified file import, whole-horizon busy intervals reaching
the recommendation request without titles, preserving a prior file on invalid replacement,
and removing imported blocks. Mocked Google UI checks verified connect, refreshed FreeBusy
requests, blocking recommendations on Google errors, and disconnect/revocation with no
token in localStorage. These mocks do not establish real Google consent success.
The production client ID is configured. The user confirmed successful real Google consent
after adding their account as a test user. The production UI confirmed the primary calendar
was read successfully and returned zero busy blocks in the current four-hour horizon.
