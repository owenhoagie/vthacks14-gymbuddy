export default function Privacy() {
  return <main className="app-shell" style={{ maxWidth: 760, padding: "48px 24px", lineHeight: 1.8 }}>
    <a href="/">← GymBuddy</a>
    <h1>Calendar privacy</h1>
    <p>GymBuddy uses your schedule to keep workout recommendations out of busy periods.</p>
    <h2>Calendar files</h2>
    <p>Imported .ics files are processed in your browser. The original file, event titles, descriptions, and attendees are not uploaded. Remove the file or reload this page to clear it from this tab.</p>
    <h2>Google Calendar</h2>
    <p>Connecting Google grants read-only access to calendar availability. GymBuddy queries your primary calendar for busy times directly from Google. It does not request event contents or permission to edit your calendar. The access token stays in this tab’s memory and is cleared on reload; it is not saved to our servers or browser storage.</p>
    <h2>Recommendations</h2>
    <p>When you request a recommendation, GymBuddy sends only busy start and end times, workout duration, and gym preferences to its hosted API. Calendar files and Google tokens are never sent to that API or stored in Databricks. The application does not persist your busy times. Hosting providers process ordinary request metadata to operate the service.</p>
    <h2>Gemini explanations</h2>
    <p>When Gemini is configured, our API sends Google the validated workout options (gym, workout times, forecast occupancy, and confidence), your workout duration, gym preferences, and crowd tolerance to explain the recommendation. Your calendar events, busy blocks, original files, and Google access token are not included. Explanations may be reused briefly in server memory. Google processes these requests under its <a href="https://ai.google.dev/gemini-api/terms">Gemini API terms</a>; free-tier requests may be used to improve Google products. If Gemini is unavailable, the schedule-based recommendation still works.</p>
    <h2>Disconnecting</h2>
    <p>Use Disconnect Google to clear local access and request removal of Google’s saved permission. You can also remove access in <a href="https://myaccount.google.com/connections">Google Account connections</a>. Reloading clears the local session but does not revoke Google’s saved consent.</p>
    <p>This is a hackathon prototype. To report a privacy issue without sharing calendar contents, use the <a href="https://github.com/owenhoagie/vthacks14-gymbuddy/issues">project issue tracker</a>.</p>
  </main>;
}
