export type Nutrition = {
  calories: number;
  protein: number;
  carbs: number;
  fat: number;
};

export type MealItem = {
  id: string;
  name: string;
  hall: string;
  servingSize: string;
  servingUnit: string;
  nutrition: Nutrition | null;
  source: "foodpro" | "user_entered";
  sourceUrl?: string;
  mealPeriods?: string[];
  stations?: string[];
};

export type DiningFood = MealItem & {
  source: "foodpro";
  recipeId: string;
  hallId: string;
  sourceUrl: string;
  mealPeriods: string[];
  stations: string[];
  allergens: string;
};

export type DiningLocation = {
  id: string;
  name: string;
  menuUrl: string;
  status: "available" | "no_menu";
  items: DiningFood[];
};

export type DiningSnapshot = {
  version: number;
  source: string;
  menuDate: string;
  capturedAt: string;
  locations: DiningLocation[];
};

export type DiningMenuResponse = {
  source: "foodpro_snapshot";
  menuDate: string;
  capturedAt: string;
  hall: string;
  hallId: string;
  menuUrl: string;
  status: "available" | "no_menu";
  meals: DiningFood[];
};

export const DINING_HALLS = [
  { id: "15", name: "D2 at Dietrick Hall" },
  { id: "09", name: "Hokie Grill at Owens" },
  { id: "16", name: "West End at Cochrane Hall" },
  { id: "18", name: "Squires Food Court" },
];

export function summarizeDailyPlan(meals: MealItem[]): Nutrition {
  const totals = meals.reduce(
    (totals, meal) => {
      if (meal.nutrition) {
        for (const key of ["calories", "protein", "carbs", "fat"] as const) {
          totals[key] += meal.nutrition[key];
        }
      }
      return totals;
    },
    { calories: 0, protein: 0, carbs: 0, fat: 0 },
  );
  // Round once for display; retain VT's decimal values in the saved snapshot.
  return Object.fromEntries(Object.entries(totals).map(([key, value]) => [key, Math.round(value * 10) / 10])) as Nutrition;
}
