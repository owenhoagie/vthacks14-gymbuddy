import { mergeBusy, type Bounds, type BusyInterval } from "./calendar";

export const GOOGLE_SCOPE = "https://www.googleapis.com/auth/calendar.freebusy";
export type GoogleToken = { access_token?: string; expires_in?: number; scope?: string; error?: string };
export type GoogleOAuth = {
  initTokenClient: (options: {
    client_id: string; scope: string; include_granted_scopes: boolean;
    callback: (response: GoogleToken) => void;
    error_callback: (error: { type: string }) => void;
  }) => { requestAccessToken: (options: { prompt: string }) => void };
  revoke: (token: string, callback: (response: { successful: boolean }) => void) => void;
};
declare global { interface Window { google?: { accounts: { oauth2: GoogleOAuth } } } }

export function validGoogleToken(response: GoogleToken) {
  return !response.error && !!response.access_token && Number(response.expires_in) > 0 &&
    response.scope?.split(" ").includes(GOOGLE_SCOPE);
}

export async function googleBusy(token: string, bounds: Bounds, fetcher = fetch): Promise<BusyInterval[]> {
  const response = await fetcher("https://www.googleapis.com/calendar/v3/freeBusy", {
    method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ timeMin: bounds.start_time, timeMax: bounds.end_time, timeZone: "UTC", items: [{ id: "primary" }] }),
    signal: AbortSignal.timeout(15000), cache: "no-store", credentials: "omit",
  });
  if (response.status === 401) throw new Error("Google access expired. Reconnect your calendar before planning.");
  if (!response.ok) throw new Error("Google Calendar could not be read. Reconnect or try again; your schedule has not been ignored.");
  const data = await response.json();
  const calendar = data.calendars?.primary;
  if (!calendar || calendar.errors?.length || !Array.isArray(calendar.busy) ||
      !(Date.parse(data.timeMin) <= Date.parse(bounds.start_time)) ||
      !(Date.parse(data.timeMax) >= Date.parse(bounds.end_time)))
    throw new Error("Google returned incomplete calendar availability. Try again before planning.");
  const intervals = calendar.busy.map((row: { start?: unknown; end?: unknown }) => {
    if (typeof row.start !== "string" || typeof row.end !== "string" ||
        !/(Z|[+-]\d{2}:\d{2})$/.test(row.start) || !/(Z|[+-]\d{2}:\d{2})$/.test(row.end))
      throw new Error("Google returned an invalid busy time. Try again.");
    return { start_time: row.start, end_time: row.end };
  });
  return mergeBusy(intervals, bounds);
}
