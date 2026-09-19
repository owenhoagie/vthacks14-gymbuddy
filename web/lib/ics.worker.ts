import { parseIcs } from "./ics";

self.onmessage = ({ data }) => {
  try { self.postMessage({ intervals: parseIcs(data.text, data.bounds) }); }
  catch (error) { self.postMessage({ error: error instanceof Error ? error.message : "Unable to read this calendar." }); }
};
