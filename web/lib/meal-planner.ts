export type MealItem = {
  id: string;
  name: string;
  hall: string;
  calories: number;
  protein: number;
  carbs: number;
  fat: number;
  source: "FoodPro" | "fallback";
};

export type DailyMacroTotals = {
  calories: number;
  protein: number;
  carbs: number;
  fat: number;
};

const SECTION_EXCLUDES = new Set([
  "breakfast",
  "lunch",
  "dinner",
  "brunch",
  "late night",
  "menu",
  "today",
  "tomorrow",
  "home",
  "dining",
  "hall",
  "campus",
  "vegetarian",
  "vegan",
  "gluten free",
  "allergen",
  "view",
  "foodpro",
  "vt",
]);

export const defaultMealSuggestions: MealItem[] = [
  {
    id: "dietrick-grilled-chicken-bowl",
    name: "Grilled Chicken Bowl",
    hall: "D2 at Dietrick Hall",
    calories: 540,
    protein: 42,
    carbs: 42,
    fat: 18,
    source: "fallback",
  },
  {
    id: "dietrick-salmon-rice-plate",
    name: "Salmon Rice Plate",
    hall: "D2 at Dietrick Hall",
    calories: 610,
    protein: 38,
    carbs: 48,
    fat: 24,
    source: "fallback",
  },
  {
    id: "dietrick-quinoa-salad",
    name: "Quinoa Veggie Salad",
    hall: "D2 at Dietrick Hall",
    calories: 430,
    protein: 21,
    carbs: 36,
    fat: 15,
    source: "fallback",
  },
  {
    id: "dietrick-bean-burrito",
    name: "Bean Burrito",
    hall: "D2 at Dietrick Hall",
    calories: 500,
    protein: 19,
    carbs: 54,
    fat: 17,
    source: "fallback",
  },
  {
    id: "dietrick-broccoli-rice",
    name: "Broccoli & Rice",
    hall: "D2 at Dietrick Hall",
    calories: 360,
    protein: 10,
    carbs: 42,
    fat: 12,
    source: "fallback",
  },
  {
    id: "owens-chicken-pasta-primavera",
    name: "Chicken Pasta Primavera",
    hall: "Hokie Grill at Owens",
    calories: 620,
    protein: 31,
    carbs: 58,
    fat: 28,
    source: "fallback",
  },
  {
    id: "owens-hummus-wrap",
    name: "Turkey & Hummus Wrap",
    hall: "Hokie Grill at Owens",
    calories: 470,
    protein: 30,
    carbs: 40,
    fat: 17,
    source: "fallback",
  },
  {
    id: "owens-veggie-pasta",
    name: "Veggie Pasta",
    hall: "Hokie Grill at Owens",
    calories: 510,
    protein: 20,
    carbs: 56,
    fat: 19,
    source: "fallback",
  },
  {
    id: "owens-tofu-stir-fry",
    name: "Tofu Stir Fry",
    hall: "Hokie Grill at Owens",
    calories: 480,
    protein: 24,
    carbs: 46,
    fat: 18,
    source: "fallback",
  },
  {
    id: "west-end-turkey-hummus-wrap",
    name: "Turkey & Hummus Wrap",
    hall: "West End at Cochrane Hall",
    calories: 470,
    protein: 30,
    carbs: 40,
    fat: 17,
    source: "fallback",
  },
  {
    id: "west-end-chicken-caesar-wrap",
    name: "Chicken Caesar Wrap",
    hall: "West End at Cochrane Hall",
    calories: 530,
    protein: 34,
    carbs: 39,
    fat: 22,
    source: "fallback",
  },
  {
    id: "west-end-smoothie-bowl",
    name: "Smoothie Bowl",
    hall: "West End at Cochrane Hall",
    calories: 390,
    protein: 18,
    carbs: 48,
    fat: 11,
    source: "fallback",
  },
  {
    id: "squires-veggie-rice-bowl",
    name: "Veggie Rice Bowl",
    hall: "Squires Food Court",
    calories: 460,
    protein: 22,
    carbs: 52,
    fat: 16,
    source: "fallback",
  },
  {
    id: "squires-burger-slider",
    name: "Burger Slider",
    hall: "Squires Food Court",
    calories: 520,
    protein: 28,
    carbs: 34,
    fat: 25,
    source: "fallback",
  },
  {
    id: "squires-fruit-cup",
    name: "Fruit Cup",
    hall: "Squires Food Court",
    calories: 180,
    protein: 2,
    carbs: 38,
    fat: 1,
    source: "fallback",
  },
  {
    id: "squires-yogurt-parfait",
    name: "Yogurt Parfait",
    hall: "Squires Food Court",
    calories: 310,
    protein: 15,
    carbs: 35,
    fat: 9,
    source: "fallback",
  },
  {
    id: "squires-pesto-pasta",
    name: "Pesto Pasta",
    hall: "Squires Food Court",
    calories: 560,
    protein: 20,
    carbs: 60,
    fat: 21,
    source: "fallback",
  },
  {
    id: "squires-oatmeal-bowl",
    name: "Oatmeal Bowl",
    hall: "Squires Food Court",
    calories: 340,
    protein: 12,
    carbs: 48,
    fat: 9,
    source: "fallback",
  },
  {
    id: "squires-salmon-rice-plate",
    name: "Salmon Rice Plate",
    hall: "Squires Food Court",
    calories: 610,
    protein: 38,
    carbs: 48,
    fat: 24,
    source: "fallback",
  },
  {
    id: "squires-chicken-burrito",
    name: "Chicken Burrito",
    hall: "Squires Food Court",
    calories: 590,
    protein: 33,
    carbs: 52,
    fat: 22,
    source: "fallback",
  },
];

function decodeHtmlEntities(value: string): string {
  return value
    .replace(/&amp;/gi, "&")
    .replace(/&nbsp;/gi, " ")
    .replace(/&ndash;/gi, "-")
    .replace(/&mdash;/gi, "-")
    .replace(/&apos;/gi, "'")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/&#x27;/gi, "'");
}

function normalizeName(value: string): string {
  return decodeHtmlEntities(value)
    .replace(/\s+/g, " ")
    .replace(/\u00a0/g, " ")
    .trim();
}

const FOOD_KEYWORDS = [
  "chicken",
  "turkey",
  "beef",
  "salmon",
  "steak",
  "tofu",
  "shrimp",
  "pasta",
  "rice",
  "salad",
  "wrap",
  "bowl",
  "pizza",
  "burger",
  "sandwich",
  "soup",
  "veggie",
  "vegetable",
  "bean",
  "quinoa",
  "fruit",
  "cereal",
  "oat",
  "yogurt",
  "egg",
  "omelet",
  "potato",
  "broccoli",
  "greens",
  "grilled",
  "roasted",
  "baked",
  "fried",
  "cheese",
  "taco",
  "quesadilla",
  "pita",
  "toast",
  "noodle",
  "curry",
  "smoothie",
  "stir",
  "seasoned",
  "burrito",
];

function isLikelyLocationOrSiteText(value: string): boolean {
  const normalized = normalizeName(value);
  if (!normalized) return true;

  const lowered = normalized.toLowerCase();
  if (lowered.length > 80) return true;
  if (/^[a-z0-9\s&'.,()/-]+$/.test(normalized) && !/[A-Z]/.test(normalized)) return true;
  if (/(?:virginia tech|virginia polytechnic institute and state university|dining services|dining menus|foodpro|vt\s+university|find your fuel|explore menus|dining events|skip to main content|privacy statement|acceptable use|we remember|university libraries|accessibility|jobs at virginia tech|consumer information|report an issue|search for food items|select a dining location|version)/i.test(lowered)) return true;
  if (/(?:\bat\s+[a-z]+\s+hall\b|\bfood court\b|\bstudent union\b|\bcenter\b|\bmarket\b|\bdirections\b|\bissue\b|\bsearch\b|\bversion\b)/i.test(lowered)) return true;
  if (/\b(?:hall|campus|dining|menu|services|events|home|navigate|directions|location|search|version)\b/i.test(lowered) && normalized.split(/\s+/).length <= 8) return true;
  return false;
}

function isLikelyMenuLabel(value: string): boolean {
  const normalized = normalizeName(value);
  const lowered = normalized.toLowerCase();
  if (!normalized || normalized.length < 3) return true;
  if (SECTION_EXCLUDES.has(lowered)) return true;
  if (isLikelyLocationOrSiteText(value)) return true;

  const hasFoodKeyword = FOOD_KEYWORDS.some((keyword) => lowered.includes(keyword));
  if (!hasFoodKeyword && normalized.split(/\s+/).length <= 4) return true;

  if (normalized.includes("menu") && normalized.length < 30) return true;
  if (/^(\d{1,2}:\d{2}|\d{1,2}\/\d{1,2}|today|tomorrow|week|all|selection|seasonal)$/i.test(normalized))
    return true;
  if (normalized.startsWith("serving") || normalized.startsWith("nutrition")) return true;
  return false;
}

export function extractMealNamesFromHtml(html: string): string[] {
  const cleaned = html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, "\n");

  const names = Array.from(
    cleaned.matchAll(/([^\n\r]{2,80})/g),
    ([match]) => normalizeName(match),
  )
    .map((value) => value.replace(/[|•·]+/g, " ").trim())
    .filter((value) => value.length > 2)
    .filter((value) => !value.startsWith("/"))
    .filter((value) => !isLikelyMenuLabel(value))
    .filter((value) => !/^[A-Z ]{2,}$/.test(value) || value.split(" ").length > 1)
    .filter((value) => !/[0-9]{1,2}(:|\/)\d{2}/.test(value))
    .filter((value) => !/^(?:Open|Closed|Breakfast|Lunch|Dinner|Brunch|Late Night|Menu|Dining|FoodPro)$/i.test(value));

  const deduped: string[] = [];
  const seen = new Set<string>();
  for (const name of names) {
    const key = name.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    deduped.push(name);
  }

  return deduped;
}

function estimateMealMacros(name: string, hall: string): Omit<MealItem, "id" | "source"> {
  const lower = name.toLowerCase();
  const base = {
    name,
    hall,
    calories: 420,
    protein: 24,
    carbs: 38,
    fat: 16,
  };

  if (/(chicken|turkey|beef|salmon|tofu|shrimp|steak)/.test(lower)) {
    base.calories += 120;
    base.protein += 18;
    base.fat += 8;
  }
  if (/(pasta|ramen|burger|wrap|pizza|sandwich)/.test(lower)) {
    base.calories += 80;
    base.carbs += 16;
  }
  if (/(salad|veggie|greens|broccoli|rice|bowl|quinoa|bean)/.test(lower)) {
    base.carbs += 20;
    base.protein += 8;
  }
  if (/(fruit|smoothie|oat|yogurt|cereal|toast)/.test(lower)) {
    base.calories -= 50;
    base.carbs += 15;
  }
  if (/(fried|cheese|mac|butter|cream)/.test(lower)) {
    base.calories += 90;
    base.fat += 12;
  }

  return {
    ...base,
    calories: Math.max(250, base.calories),
    protein: Math.max(8, base.protein),
    carbs: Math.max(12, base.carbs),
    fat: Math.max(6, base.fat),
  };
}

export function buildMealSuggestions(html: string, hall: string): MealItem[] {
  const names = extractMealNamesFromHtml(html);
  if (names.length === 0) return defaultMealSuggestions;

  const meals = names.map((name, index) => ({
    id: `${hall.toLowerCase().replace(/\s+/g, "-")}-${index}-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
    source: "FoodPro" as const,
    ...estimateMealMacros(name, hall),
  }));

  if (meals.length === 0) return defaultMealSuggestions;
  return meals;
}

export function summarizeDailyPlan(meals: MealItem[]): DailyMacroTotals {
  return meals.reduce(
    (totals, meal) => ({
      calories: totals.calories + meal.calories,
      protein: totals.protein + meal.protein,
      carbs: totals.carbs + meal.carbs,
      fat: totals.fat + meal.fat,
    }),
    { calories: 0, protein: 0, carbs: 0, fat: 0 },
  );
}
