import ICAL from "ical.js";
import { mergeBusy, type Bounds, type BusyInterval } from "./calendar";

export const MAX_ICS_BYTES = 1024 * 1024;
const EASTERN = "America/New_York";

// IANA TZIDs commonly omit VTIMEZONE. Intl supplies those rules without a bundled tz database.
function wallInstant(time: ICAL.Time, zone: string): number {
  const nominal = Date.UTC(time.year, time.month - 1, time.day, time.hour, time.minute, time.second);
  let formatter: Intl.DateTimeFormat;
  try {
    formatter = new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric",
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
      second: "2-digit", hourCycle: "h23" });
  } catch { throw new Error("This calendar uses an unsupported time zone. Export with IANA time zones or VTIMEZONE definitions."); }
  const wallAt = (ms: number) => {
    const p = formatter.formatToParts(ms);
    const n = (name: string) => Number(p.find(x => x.type === name)!.value);
    return Date.UTC(n("year"), n("month") - 1, n("day"), n("hour"), n("minute"), n("second"));
  };
  const candidates = [-36, 0, 36].map(hours => {
    const probe = nominal + hours * 3600000;
    return nominal - (wallAt(probe) - probe);
  }).filter(ms => wallAt(ms) === nominal);
  if (!candidates.length) throw new Error("A calendar event falls in a nonexistent daylight-saving time.");
  return Math.min(...candidates);
}

function instant(time: ICAL.Time, component: ICAL.Component, property: string, fallback: string) {
  if (!time || time.year < 1900 || time.year > 2200) throw new Error("Invalid calendar date.");
  if (!time.isDate && time.zone.tzid !== "floating") return time.toJSDate().getTime();
  const tzid = component.getFirstProperty(property)?.getParameter("tzid");
  return wallInstant(time, typeof tzid === "string" ? tzid : fallback);
}

function ignored(c: ICAL.Component) {
  return c.getFirstPropertyValue("status") === "CANCELLED" || c.getFirstPropertyValue("transp") === "TRANSPARENT";
}

export function parseIcs(text: string, bounds: Bounds): BusyInterval[] {
  text = text.replace(/^\uFEFF/, "");
  if (new TextEncoder().encode(text).length > MAX_ICS_BYTES) throw new Error("Choose a calendar file smaller than 1 MB.");
  if (!text.trimEnd().endsWith("END:VCALENDAR")) throw new Error("Choose a complete .ics calendar file.");
  ICAL.TimezoneService.reset();
  let calendar: ICAL.Component;
  try { calendar = new ICAL.Component(ICAL.parse(text)); }
  catch { throw new Error("This .ics file could not be read. Export it again from your calendar."); }
  if (calendar.name !== "vcalendar") throw new Error("Choose an iCalendar (.ics) file.");
  for (const zone of calendar.getAllSubcomponents("vtimezone")) {
    const id = String(zone.getFirstPropertyValue("tzid") || "");
    if (id) ICAL.TimezoneService.register(new ICAL.Timezone({ component: zone, tzid: id }));
  }
  const fallback = String(calendar.getFirstPropertyValue("x-wr-timezone") || EASTERN);
  const components = calendar.getAllSubcomponents("vevent");
  if (components.length > 2000) throw new Error("This calendar has too many events. Export a smaller date range.");
  if (calendar.getFirstPropertyValue("method") === "CANCEL") return [];
  const events = components.map(c => {
    if (c.getFirstProperty("recurrence-id")?.getParameter("range"))
      throw new Error("Recurring range overrides are not supported. Import this calendar through Google instead.");
    if (c.getAllProperties("rdate").some(p => p.type === "period"))
      throw new Error("Period-based recurrence dates are not supported. Use Google Calendar instead.");
    return new ICAL.Event(c, { strictExceptions: true, exceptions: [] });
  });
  const seen = new Set<string>();
  for (const e of events) {
    if (!e.uid) throw new Error("A calendar event is missing its identifier.");
    const key = e.uid + ":" + (e.isRecurrenceException() ? e.recurrenceId.toString() : "master");
    if (seen.has(key)) throw new Error("This export contains duplicate event revisions. Export a fresh calendar.");
    seen.add(key);
  }
  const result: BusyInterval[] = [];
  let iterations = 0;
  const add = (event: ICAL.Event, start: ICAL.Time, end: ICAL.Time) => {
    if (ignored(event.component)) return;
    const a = instant(start, event.component, "dtstart", fallback);
    const b = instant(end, event.component, "dtend", String(event.component.getFirstProperty("dtstart")?.getParameter("tzid") || fallback));
    if (b < a) throw new Error("A calendar event ends before it starts.");
    if (b > a && a < Date.parse(bounds.end_time) && b > Date.parse(bounds.start_time))
      result.push({ start_time: new Date(a).toISOString(), end_time: new Date(b).toISOString() });
  };
  for (const master of events.filter(e => !e.isRecurrenceException())) {
    if (master.component.getFirstPropertyValue("status") === "CANCELLED") continue;
    if (!master.component.hasProperty("dtstart")) throw new Error("A calendar event has no start time.");
    const exceptions = events.filter(e => e.isRecurrenceException() && e.uid === master.uid);
    const cancelled = new Set(exceptions.filter(e => e.component.getFirstPropertyValue("status") === "CANCELLED").map(e => e.recurrenceId.toString()));
    for (const e of exceptions) if (!cancelled.has(e.recurrenceId.toString())) master.relateException(e);
    if (!master.isRecurring()) { add(master, master.startDate, master.endDate); continue; }
    const iterator = master.iterator();
    for (let occurrence = iterator.next(); occurrence; occurrence = iterator.next()) {
      if (++iterations > 20000) throw new Error("This calendar has too many recurrences. Export a smaller date range.");
      if (instant(occurrence, master.component, "dtstart", fallback) >= Date.parse(bounds.end_time)) break;
      if (cancelled.has(occurrence.toString())) continue;
      const details = master.getOccurrenceDetails(occurrence);
      add(details.item, details.startDate, details.endDate);
    }
  }
  // Moved exceptions may fall inside the window even if their original instance falls outside.
  for (const e of events.filter(e => e.isRecurrenceException())) {
    const parent = events.find(m => !m.isRecurrenceException() && m.uid === e.uid);
    if ((!parent || parent.component.getFirstPropertyValue("status") !== "CANCELLED") && !ignored(e.component)) add(e, e.startDate, e.endDate);
  }
  return mergeBusy(result, bounds);
}
