export const TIME_ZONE = "America/New_York";

export function timestampLabel(value: string | Date) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: TIME_ZONE,
    year: "numeric", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit", timeZoneName: "short",
  }).format(new Date(value));
}

export function timeLabel(value: string | Date) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: TIME_ZONE,
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function dateLabel(value: string | Date) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: TIME_ZONE,
    weekday: "long",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

export function easternDay(date: Date) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const part = (type: string) => parts.find((p) => p.type === type)!.value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}

// Convert a wall-clock time in Blacksburg without using the browser's timezone.
// For an ambiguous fall-back time, choose its first occurrence; reject nonexistent times.
export function easternInstant(day: string, time: string): string {
  const wall = `${day}T${time}:00`;
  const nominal = Date.parse(`${wall}Z`);
  if (!Number.isFinite(nominal))
    throw new Error("Enter a valid date and time.");
  const formatter = new Intl.DateTimeFormat("sv-SE", {
    timeZone: TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });
  for (const offset of [4, 5]) {
    const candidate = new Date(nominal + offset * 3600000);
    if (formatter.format(candidate).replace(" ", "T") === wall)
      return candidate.toISOString();
  }
  throw new Error(
    "This time does not exist in Eastern Time. Choose another time.",
  );
}

export function searchBounds(now = new Date()) {
  const start = new Date(Math.ceil(now.getTime() / 300000) * 300000);
  return {
    start_time: start.toISOString(),
    end_time: new Date(start.getTime() + 4 * 3600000).toISOString(),
  };
}
