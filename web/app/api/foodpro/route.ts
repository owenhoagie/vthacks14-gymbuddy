import { NextRequest } from "next/server";
import { buildMealSuggestions } from "@/lib/meal-planner";

export const runtime = "nodejs";

const FOODPRO_URL = "https://foodpro.students.vt.edu/menus/";

export async function GET(request: NextRequest) {
  const hall = request.nextUrl.searchParams.get("hall") || "D2 at Dietrick Hall";

  try {
    const response = await fetch(FOODPRO_URL, {
      headers: {
        "User-Agent": "Mozilla/5.0",
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      },
      redirect: "follow",
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    });

    if (!response.ok) {
      throw new Error(`FoodPro returned ${response.status}`);
    }

    const html = await response.text();
    const meals = buildMealSuggestions(html, hall);
    const hasValidFoodNames = meals.some((meal) => !/virginia|dining|menu|search|directions|issue|version|rights reserved/i.test(meal.name));

    if (!hasValidFoodNames) {
      return Response.json({
        hall,
        source: "fallback",
        meals: buildMealSuggestions("", hall),
        fetchedAt: new Date().toISOString(),
      });
    }

    return Response.json({
      hall,
      source: "foodpro",
      meals,
      fetchedAt: new Date().toISOString(),
    });
  } catch {
    const meals = buildMealSuggestions("", hall);
    return Response.json({
      hall,
      source: "fallback",
      meals,
      fetchedAt: new Date().toISOString(),
    });
  }
}
