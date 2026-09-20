// Server-side import: the browser receives only the selected hall's saved menu.
import data from "../fixtures/dining-snapshot.json";
import type { DiningMenuResponse, DiningSnapshot } from "./meal-planner";

const snapshot = data as DiningSnapshot;

export function getDiningMenu(hall: string): DiningMenuResponse | null {
  const location = snapshot.locations.find((item) => item.id === hall || item.name === hall);
  if (!location) return null;
  return {
    source: "foodpro_snapshot",
    menuDate: snapshot.menuDate,
    capturedAt: snapshot.capturedAt,
    hall: location.name,
    hallId: location.id,
    menuUrl: location.menuUrl,
    status: location.status,
    meals: location.items,
  };
}
