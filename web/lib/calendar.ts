export type BusyInterval = { start_time: string; end_time: string };
export type Bounds = BusyInterval;

// Clip and union before enforcing the API's 50-block limit. Never drop busy time.
export function mergeBusy(intervals: BusyInterval[], bounds: Bounds): BusyInterval[] {
  const lo = Date.parse(bounds.start_time), hi = Date.parse(bounds.end_time);
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi <= lo)
    throw new Error("Invalid calendar search bounds.");
  const times = intervals.map((row) => {
    const start = Date.parse(row.start_time), end = Date.parse(row.end_time);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start)
      throw new Error("The calendar contains an invalid busy interval.");
    return [Math.max(start, lo), Math.min(end, hi)];
  }).filter(([start, end]) => start < end).sort((a, b) => a[0] - b[0]);
  const merged: number[][] = [];
  for (const [start, end] of times) {
    const last = merged.at(-1);
    if (last && start <= last[1]) last[1] = Math.max(last[1], end);
    else merged.push([start, end]);
  }
  if (merged.length > 50) throw new Error("Too many separate busy blocks in this four-hour window.");
  return merged.map(([start, end]) => ({
    start_time: new Date(start).toISOString(), end_time: new Date(end).toISOString(),
  }));
}
