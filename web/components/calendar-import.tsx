"use client";

import Script from "next/script";
import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { type Bounds, type BusyInterval, mergeBusy } from "@/lib/calendar";
import { importIcs } from "@/lib/ics-client";
import { GOOGLE_SCOPE, googleBusy, validGoogleToken } from "@/lib/google-calendar";
import { searchBounds, timestampLabel } from "@/lib/time";

export type CalendarHandle = { busy: (bounds: Bounds) => Promise<BusyInterval[]> };
const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

export default function CalendarImport({ ref, disabled, onChange, onBusy }: {
  ref: Ref<CalendarHandle>; disabled: boolean; onChange: () => void; onBusy: (busy: boolean) => void;
}) {
  const file = useRef<{ name: string; text: string } | null>(null);
  const token = useRef<{ value: string; expires: number } | null>(null);
  const [fileName, setFileName] = useState("");
  const [connected, setConnected] = useState(false);
  const [ready, setReady] = useState(false);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<BusyInterval[]>([]);
  const generation = useRef(0);
  const oauthTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => {
    generation.current++;
    clearTimeout(oauthTimer.current);
    token.current = null;
    file.current = null;
  }, []);
  const setBusy = (value: boolean) => { setWorking(value); onBusy(value); };
  const changed = () => { setPreview([]); onChange(); };

  useImperativeHandle(ref, () => ({
    async busy(bounds) {
      try {
        const intervals = file.current ? await importIcs(file.current.text, bounds) : [];
        if (token.current) {
          if (token.current.expires <= Date.now()) throw new Error("Google access expired. Reconnect or disconnect before planning.");
          intervals.push(...await googleBusy(token.current.value, bounds));
        }
        const merged = mergeBusy(intervals, bounds);
        setPreview(merged);
        setError("");
        if (file.current || token.current) setMessage(`Calendar checked ${timestampLabel(new Date())}. ${merged.length} busy block${merged.length === 1 ? "" : "s"} in the next four hours.`);
        return merged;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Your calendar could not be checked.";
        setError(message);
        throw new Error(message);
      }
    },
  }));

  async function readFile(selected: File | undefined) {
    if (!selected) return;
    setBusy(true); setError("");
    try {
      if (!selected.name.toLowerCase().endsWith(".ics")) throw new Error("Choose an .ics calendar export.");
      if (selected.size > 1024 * 1024) throw new Error("Choose a calendar smaller than 1 MB.");
      const text = await selected.text();
      const intervals = await importIcs(text, searchBounds());
      file.current = { name: selected.name, text };
      setFileName(selected.name); changed(); setPreview(intervals);
      setMessage(`Imported ${selected.name}. ${intervals.length} busy blocks in the next four hours. Click Find my gym window to apply your schedule.`);
    } catch (err) { setError(err instanceof Error ? err.message : "Could not read this calendar."); }
    finally { setBusy(false); }
  }

  function connect() {
    const oauth = window.google?.accounts.oauth2;
    if (!oauth || !CLIENT_ID) { setError("Google Calendar is not configured yet."); return; }
    setBusy(true); setError("");
    const attempt = ++generation.current;
    let responseReceived = false;
    const finish = () => { clearTimeout(oauthTimer.current); setBusy(false); };
    oauthTimer.current = setTimeout(() => {
      if (attempt === generation.current) { generation.current++; finish(); setError("Google connection timed out. Try connecting again."); }
    }, 120000);
    try {
      oauth.initTokenClient({
        client_id: CLIENT_ID, scope: GOOGLE_SCOPE, include_granted_scopes: false,
        callback: async (response) => {
          if (attempt !== generation.current || responseReceived) return;
          // GIS can report popup closure around token delivery. The token response
          // is authoritative; a later close event must not overwrite its outcome.
          responseReceived = true;
          setError(""); setBusy(true);
          clearTimeout(oauthTimer.current);
          if (!validGoogleToken(response)) { setError("Calendar permission was not granted. You can use an .ics file instead."); finish(); return; }
          token.current = { value: response.access_token!, expires: Date.now() + Number(response.expires_in) * 1000 - 30000 };
          setConnected(true); changed();
          try {
            const intervals = await googleBusy(token.current.value, searchBounds());
            if (attempt !== generation.current) return;
            setPreview(intervals);
            setMessage(`Google primary calendar connected. ${intervals.length} busy blocks in the next four hours. Click Find my gym window to apply.`);
          } catch (err) { if (attempt === generation.current) setError(err instanceof Error ? err.message : "Could not read Google Calendar."); }
          finally { if (attempt === generation.current) finish(); }
        },
        error_callback: () => { if (attempt === generation.current && !responseReceived) { finish(); setError("Google sign-in was closed or blocked. Allow popups and try again."); } },
      }).requestAccessToken({ prompt: "select_account" });
    } catch { finish(); setError("Google sign-in could not open. Try again."); }
  }

  function disconnect() {
    generation.current++; clearTimeout(oauthTimer.current);
    const previous = token.current;
    token.current = null; setConnected(false); setError(""); changed();
    setMessage("Google disconnected from this page. Calendar busy times were removed.");
    if (previous) window.google?.accounts.oauth2.revoke(previous.value, response => {
      if (!response.successful) setMessage("Disconnected locally. To remove Google's saved permission too, visit your Google Account connections.");
    });
  }

  return <section className="calendar-import" aria-labelledby="calendar-heading">
    {CLIENT_ID && <Script src="https://accounts.google.com/gsi/client" strategy="afterInteractive"
      onReady={() => setReady(true)} onError={() => setError("Google sign-in could not load. Check your connection or import an .ics file.")} />}
    <h3 id="calendar-heading">Bring your schedule</h3>
    <p>Import a calendar or connect Google to keep workouts clear of your plans.</p>
    <label className="calendar-file">{fileName ? "Replace .ics file" : "Import .ics file"}
      <input aria-label="Import .ics calendar" type="file" accept=".ics,text/calendar" disabled={disabled || working}
        onChange={event => { const selected = event.target.files?.[0]; event.target.value = ""; void readFile(selected); }} />
    </label>
    {fileName && <div className="calendar-source"><span>{fileName}</span><button type="button" disabled={disabled || working}
      onClick={() => { file.current = null; setFileName(""); setError(""); setMessage("Imported file removed."); changed(); }}>Remove file</button></div>}
    <button className="calendar-connect" type="button" disabled={disabled || working || !CLIENT_ID || !ready} onClick={connect}>
      {working ? "Checking calendar…" : connected ? "Reconnect Google Calendar" : "Connect Google Calendar"}
    </button>
    {connected && <button type="button" className="calendar-disconnect" disabled={disabled || working} onClick={disconnect}>Disconnect Google</button>}
    {!CLIENT_ID && <p>Google connection is awaiting app setup. You can import an .ics file now.</p>}
    <p className="calendar-privacy">Files and Google access stay in this tab until reload. Only busy times are sent to GymBuddy when you plan. Google checks your primary calendar; no event titles or edits. Floating and all-day file events use Eastern Time unless the file specifies a time zone.</p>
    <a href="/privacy" target="_blank" rel="noreferrer">Calendar privacy</a>
    {message && <p role="status">{message}</p>}
    {error && <p role="alert" className="calendar-error">{error}</p>}
    {preview.length > 0 && <details><summary>{preview.length} imported busy blocks</summary><ul>{preview.map(row => <li key={row.start_time}>{timestampLabel(row.start_time)} – {timestampLabel(row.end_time)}</li>)}</ul></details>}
    {connected && <a href="https://myaccount.google.com/connections" target="_blank" rel="noreferrer">Manage Google permissions</a>}
  </section>;
}
