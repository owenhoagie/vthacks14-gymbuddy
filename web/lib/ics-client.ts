import type { Bounds, BusyInterval } from "./calendar";

export function importIcs(text: string, bounds: Bounds): Promise<BusyInterval[]> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL("./ics.worker.ts", import.meta.url));
    const finish = () => { clearTimeout(timer); worker.terminate(); };
    const timer = setTimeout(() => { finish(); reject(new Error("Calendar processing took too long. Export a smaller date range.")); }, 5000);
    worker.onmessage = ({ data }) => {
      finish();
      if (data.error) reject(new Error(data.error)); else resolve(data.intervals);
    };
    worker.onerror = () => { finish(); reject(new Error("Calendar processing failed. Try a new export.")); };
    worker.postMessage({ text, bounds });
  });
}
