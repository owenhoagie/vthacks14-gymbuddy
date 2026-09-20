import assert from "node:assert/strict";
import test from "node:test";
import { getDiningMenu } from "../lib/dining-snapshot";
import { DINING_HALLS, summarizeDailyPlan, type MealItem } from "../lib/meal-planner";
import { GET } from "../app/api/foodpro/route";
import { NextRequest } from "next/server";

test("saved menus are hall-specific with real source URLs and valid nutrition", () => {
  const names = new Set<string>();
  for (const hall of DINING_HALLS) {
    const menu = getDiningMenu(hall.id)!;
    assert.equal(menu.hall, hall.name);
    assert.deepEqual(getDiningMenu(hall.name), menu);
    assert.equal(menu.source, "foodpro_snapshot");
    for (const meal of menu.meals) {
      assert.equal(meal.hallId, hall.id);
      assert.equal(meal.hall, hall.name);
      assert.equal(meal.source, "foodpro");
      const url = new URL(meal.sourceUrl);
      assert.equal(url.hostname, "foodpro.students.vt.edu");
      assert.equal(url.searchParams.get("locationNum"), hall.id);
      assert.equal(url.searchParams.get("recNumAndPort"), `${meal.recipeId}*${meal.servingSize}`);
      assert.ok(meal.servingUnit.length > 0);
      assert.ok(meal.mealPeriods.length > 0);
      if (meal.nutrition) {
        for (const value of Object.values(meal.nutrition)) assert.ok(Number.isFinite(value) && value >= 0);
      }
      names.add(meal.name);
    }
    assert.equal(new Set(menu.meals.map((meal) => meal.id)).size, menu.meals.length);
  }
  assert.ok(names.size > 200);
  assert.equal(getDiningMenu("unrecognized"), null);
});

test("pancakes preserve captured VT decimals and serving size", () => {
  const food = getDiningMenu("15")!.meals.find((meal) => meal.recipeId === "141002")!;
  assert.equal(food.servingSize, "2");
  assert.equal(food.servingUnit, "PANCAKES");
  assert.deepEqual(food.nutrition, { calories: 217, protein: 6.7, carbs: 31.7, fat: 6.3 });
});

test("empty menus and missing nutrition never receive synthetic substitutes", () => {
  const menu = getDiningMenu("09")!;
  assert.equal(menu.status, "no_menu");
  assert.deepEqual(menu.meals, []);
  const missing = DINING_HALLS.flatMap((hall) => getDiningMenu(hall.id)!.meals).filter((meal) => meal.nutrition === null);
  assert.ok(missing.length > 0);
  assert.deepEqual(summarizeDailyPlan(missing), { calories: 0, protein: 0, carbs: 0, fat: 0 });
});

test("totals start at zero and sum actual decimals", () => {
  assert.deepEqual(summarizeDailyPlan([]), { calories: 0, protein: 0, carbs: 0, fat: 0 });
  const meal: MealItem = { id: "custom", name: "User food", hall: "Entered by you", source: "user_entered", servingSize: "1", servingUnit: "serving", nutrition: { calories: 217, protein: 6.7, carbs: 31.7, fat: 6.3 } };
  assert.deepEqual(summarizeDailyPlan([meal, meal]), { calories: 434, protein: 13.4, carbs: 63.4, fat: 12.6 });
});

test("API preserves snapshot dates without upstream requests and rejects unknown halls", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error("Unexpected external request"); };
  try {
    const first = await GET(new NextRequest("http://localhost/api/foodpro?hall=15"));
    const second = await GET(new NextRequest("http://localhost/api/foodpro?hall=15"));
    assert.equal(first.status, 200);
    const a = await first.json();
    const b = await second.json();
    assert.equal(a.menuDate, "2026-09-19");
    assert.ok(Number.isFinite(Date.parse(a.capturedAt)));
    assert.equal(a.capturedAt, b.capturedAt);
    assert.deepEqual(a.meals, b.meals);
    const invalid = await GET(new NextRequest("http://localhost/api/foodpro?hall=bogus"));
    assert.equal(invalid.status, 400);
  } finally {
    globalThis.fetch = original;
  }
});

test("repeat adds increase servings and scale all macros without changing VT data", async () => {
  const { addMealToPlate, setMealServings } = await import("../lib/meal-planner");
  const food = getDiningMenu("15")!.meals.find((meal) => meal.recipeId === "141002")!;
  const before = structuredClone(food);
  const once = addMealToPlate([], food);
  const twice = addMealToPlate(once, food);
  assert.equal(once[0].quantity, 1);
  assert.equal(twice.length, 1);
  assert.equal(twice[0].quantity, 2);
  assert.deepEqual(summarizeDailyPlan(twice), { calories: 434, protein: 13.4, carbs: 63.4, fat: 12.6 });
  const half = setMealServings(twice, food.id, 0.5);
  assert.deepEqual(summarizeDailyPlan(half), { calories: 108.5, protein: 3.4, carbs: 15.9, fat: 3.2 });
  assert.deepEqual(food, before);
});

test("same names across halls remain distinct and invalid servings cannot change totals", async () => {
  const { addMealToPlate, setMealServings, MAX_SERVINGS } = await import("../lib/meal-planner");
  const food = getDiningMenu("15")!.meals.find((meal) => meal.recipeId === "141002")!;
  const other = { ...food, id: "other-hall-pancakes", hall: "Another hall" };
  const entries = addMealToPlate(addMealToPlate([], food), other);
  assert.equal(entries.length, 2);
  for (const invalid of [0, -1, NaN, Infinity, 0.25, 100]) {
    assert.deepEqual(setMealServings(entries, food.id, invalid), entries);
  }
  const max = setMealServings(entries, food.id, MAX_SERVINGS);
  assert.equal(addMealToPlate(max, food)[0].quantity, MAX_SERVINGS);
  assert.deepEqual(addMealToPlate(entries, { ...food, nutrition: null }), entries);
});
