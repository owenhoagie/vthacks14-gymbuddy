"use client";

import { useEffect, useMemo, useState } from "react";
import {
  buildMealSuggestions,
  defaultMealSuggestions,
  summarizeDailyPlan,
  type MealItem,
} from "@/lib/meal-planner";

const HALLS = [
  "D2 at Dietrick Hall",
  "Hokie Grill at Owens",
  "West End at Cochrane Hall",
  "Squires Food Court",
];

function MacroCard({ label, value, suffix }: { label: string; value: number; suffix: string }) {
  return (
    <div className="macro-card">
      <span>{label}</span>
      <strong>
        {value}
        <small>{suffix}</small>
      </strong>
    </div>
  );
}

export default function MealPlannerCard() {
  const [hall, setHall] = useState(HALLS[0]);
  const [suggestions, setSuggestions] = useState<MealItem[]>(defaultMealSuggestions);
  const [selectedMeals, setSelectedMeals] = useState<MealItem[]>([
    defaultMealSuggestions[0],
    defaultMealSuggestions[4],
  ]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [source, setSource] = useState("fallback meal ideas");
  const [searchTerm, setSearchTerm] = useState("");
  const [customMealName, setCustomMealName] = useState("");
  const [customCalories, setCustomCalories] = useState("550");
  const [customProtein, setCustomProtein] = useState("35");
  const [customCarbs, setCustomCarbs] = useState("40");
  const [customFat, setCustomFat] = useState("20");

  useEffect(() => {
    let ignore = false;
    async function loadMeals() {
      setLoading(true);
      setError("");
      try {
        const response = await fetch(`/api/foodpro?hall=${encodeURIComponent(hall)}`);
        const payload = await response.json();
        if (ignore) return;
        const items = Array.isArray(payload.meals) && payload.meals.length > 0
          ? payload.meals
          : buildMealSuggestions("", hall);
        setSuggestions(items);
        setSource(payload.source === "foodpro" ? "VT FoodPro menu" : "fallback meal ideas");
      } catch {
        if (ignore) return;
        setSuggestions(buildMealSuggestions("", hall));
        setError("FoodPro isn’t responding right now, so I’m using the local VT dining fallback list.");
        setSource("fallback meal ideas");
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    void loadMeals();
    return () => {
      ignore = true;
    };
  }, [hall]);

  const totals = useMemo(() => summarizeDailyPlan(selectedMeals), [selectedMeals]);
  const filteredSuggestions = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return suggestions;
    return suggestions.filter((meal) =>
      meal.name.toLowerCase().includes(term) || meal.hall.toLowerCase().includes(term),
    );
  }, [searchTerm, suggestions]);

  function addMeal(meal: MealItem) {
    setSelectedMeals((previous) => {
      if (previous.some((item) => item.id === meal.id || item.name.toLowerCase() === meal.name.toLowerCase()))
        return previous;
      return [...previous, meal];
    });
  }

  function removeMeal(id: string) {
    setSelectedMeals((previous) => previous.filter((item) => item.id !== id));
  }

  function handleCustomMealSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = customMealName.trim();
    if (!name) return;

    const nextMeal: MealItem = {
      id: `custom-${Date.now()}`,
      name,
      hall,
      calories: Number(customCalories) || 0,
      protein: Number(customProtein) || 0,
      carbs: Number(customCarbs) || 0,
      fat: Number(customFat) || 0,
      source: "fallback",
    };

    setSelectedMeals((previous) => {
      if (previous.some((item) => item.name.toLowerCase() === name.toLowerCase())) return previous;
      return [...previous, nextMeal];
    });
    setCustomMealName("");
    setCustomCalories("550");
    setCustomProtein("35");
    setCustomCarbs("40");
    setCustomFat("20");
  }

  return (
    <section id="meal-planner" className="meal-planner card">
      <div className="meal-planner-header">
        <div>
          <span className="section-kicker">02 / FUEL</span>
          <h2>Macro tracker + meal planner</h2>
        </div>
        <span className="meal-source">{loading ? "Loading menu…" : source}</span>
      </div>

      <div className="meal-hall-toggle" role="tablist" aria-label="Dining hall selector">
        {HALLS.map((hallName) => (
          <button
            key={hallName}
            type="button"
            className={hall === hallName ? "active" : ""}
            aria-pressed={hall === hallName}
            onClick={() => setHall(hallName)}
          >
            {hallName}
          </button>
        ))}
      </div>

      {error ? <p className="meal-error">{error}</p> : null}

      <div className="macro-grid">
        <MacroCard label="Calories" value={totals.calories} suffix="kcal" />
        <MacroCard label="Protein" value={totals.protein} suffix="g" />
        <MacroCard label="Carbs" value={totals.carbs} suffix="g" />
        <MacroCard label="Fat" value={totals.fat} suffix="g" />
      </div>

      <div className="meal-plan-layout">
        <div className="meal-list-panel">
          <h3>Today’s plate</h3>
          <div className="meal-chip-list">
            {selectedMeals.length === 0 ? (
              <p className="empty-state">Add a meal, or type in anything you ate.</p>
            ) : (
              selectedMeals.map((meal) => (
                <div key={meal.id} className="meal-chip">
                  <div>
                    <strong>{meal.name}</strong>
                    <small>
                      {meal.hall} · {meal.calories} kcal
                    </small>
                  </div>
                  <button type="button" onClick={() => removeMeal(meal.id)} aria-label={`Remove ${meal.name}`}>
                    Remove
                  </button>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="meal-list-panel">
          <h3>Search and add food</h3>
          <div className="meal-search-row">
            <input
              type="search"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search for chicken, salad, pasta…"
              aria-label="Search for foods to add"
            />
          </div>

          <form className="custom-meal-form" onSubmit={handleCustomMealSubmit}>
            <input
              type="text"
              value={customMealName}
              onChange={(event) => setCustomMealName(event.target.value)}
              placeholder="Or type any food you ate"
              aria-label="Custom food name"
            />
            <div className="custom-macro-grid">
              <input type="number" min="0" value={customCalories} onChange={(e) => setCustomCalories(e.target.value)} aria-label="Calories" />
              <input type="number" min="0" value={customProtein} onChange={(e) => setCustomProtein(e.target.value)} aria-label="Protein grams" />
              <input type="number" min="0" value={customCarbs} onChange={(e) => setCustomCarbs(e.target.value)} aria-label="Carb grams" />
              <input type="number" min="0" value={customFat} onChange={(e) => setCustomFat(e.target.value)} aria-label="Fat grams" />
            </div>
            <button type="submit" className="add-custom-button">Add custom meal</button>
          </form>

          <div className="meal-suggestion-list">
            {filteredSuggestions.length === 0 ? (
              <p className="empty-state">No matches for that search. Try a different food or add your own.</p>
            ) : (
              filteredSuggestions.map((meal) => (
                <div key={meal.id} className="meal-row">
                  <div>
                    <strong>{meal.name}</strong>
                    <small>
                      {meal.hall} · {meal.protein}P / {meal.carbs}C / {meal.fat}F
                    </small>
                  </div>
                  <button type="button" onClick={() => addMeal(meal)}>
                    Add
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
