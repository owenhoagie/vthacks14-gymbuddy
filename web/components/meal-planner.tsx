"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  DINING_HALLS,
  addMealToPlate,
  setMealServings,
  validServings,
  MIN_SERVINGS,
  MAX_SERVINGS,
  type PlateEntry,
  type DiningMenuResponse,
  summarizeDailyPlan,
  type MealItem,
} from "@/lib/meal-planner";

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

function ServingControl({ name, quantity, onChange }: { name: string; quantity: number; onChange: (value: number) => void }) {
  const [draft, setDraft] = useState(String(quantity));
  useEffect(() => setDraft(String(quantity)), [quantity]);

  return (
    <div className="serving-control">
      <span>Servings</span>
      <div className="serving-stepper">
        <button type="button" aria-label={`Decrease servings of ${name} by half`} disabled={quantity <= MIN_SERVINGS} onClick={() => onChange(quantity - 0.5)}>−</button>
        <input
          type="number"
          min={MIN_SERVINGS}
          max={MAX_SERVINGS}
          step="0.5"
          inputMode="decimal"
          aria-label={`Servings of ${name}`}
          value={draft}
          onChange={(event) => {
            setDraft(event.target.value);
            const value = Number(event.target.value);
            if (validServings(value)) onChange(value);
          }}
          onBlur={() => setDraft(String(quantity))}
          onKeyDown={(event) => {
            if (event.key === "Enter") event.currentTarget.blur();
          }}
        />
        <button type="button" aria-label={`Increase servings of ${name} by half`} disabled={quantity >= MAX_SERVINGS} onClick={() => onChange(quantity + 0.5)}>+</button>
      </div>
    </div>
  );
}

export default function MealPlannerCard() {
  const foodDropdown = useRef<HTMLDetailsElement>(null);
  const [hall, setHall] = useState(DINING_HALLS[0].id);
  const [suggestions, setSuggestions] = useState<MealItem[]>([]);
  const [selectedMeals, setSelectedMeals] = useState<PlateEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [menu, setMenu] = useState<DiningMenuResponse | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [customMealName, setCustomMealName] = useState("");
  const [customCalories, setCustomCalories] = useState("");
  const [customProtein, setCustomProtein] = useState("");
  const [customCarbs, setCustomCarbs] = useState("");
  const [customFat, setCustomFat] = useState("");

  useEffect(() => {
    function closeOutside(event: PointerEvent) {
      if (event.target instanceof Node && foodDropdown.current && !foodDropdown.current.contains(event.target)) {
        foodDropdown.current.open = false;
      }
    }
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, []);

  useEffect(() => {
    let ignore = false;
    async function loadMeals() {
      setLoading(true);
      setError("");
      setSuggestions([]);
      setMenu(null);
      try {
        const response = await fetch(`/api/foodpro?hall=${encodeURIComponent(hall)}`);
        if (!response.ok) throw new Error("Menu unavailable");
        const payload: DiningMenuResponse = await response.json();
        if (payload.source !== "foodpro_snapshot" || !Array.isArray(payload.meals)) {
          throw new Error("Invalid menu snapshot");
        }
        if (ignore) return;
        setSuggestions(payload.meals);
        setMenu(payload);
      } catch {
        if (ignore) return;
        setSuggestions([]);
        setError("The saved VT menu could not be loaded. Try selecting a hall again or enter your own food below.");
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
    setSelectedMeals((previous) => addMealToPlate(previous, meal));
  }

  function changeServings(id: string, quantity: number) {
    setSelectedMeals((previous) => setMealServings(previous, id, quantity));
  }

  function removeMeal(id: string) {
    setSelectedMeals((previous) => previous.filter((item) => item.id !== id));
  }

  function handleCustomMealSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = customMealName.trim();
    const values = [customCalories, customProtein, customCarbs, customFat];
    if (!name || values.some((value) => !value.trim() || !Number.isFinite(Number(value)) || Number(value) < 0)) return;

    const nextMeal: MealItem = {
      id: `custom-${crypto.randomUUID()}`,
      name,
      hall: "Entered by you",
      servingSize: "1",
      servingUnit: "custom serving",
      nutrition: {
        calories: Number(customCalories),
        protein: Number(customProtein),
        carbs: Number(customCarbs),
        fat: Number(customFat),
      },
      source: "user_entered",
    };

    addMeal(nextMeal);
    setCustomMealName("");
    setCustomCalories("");
    setCustomProtein("");
    setCustomCarbs("");
    setCustomFat("");
  }

  return (
    <section id="meal-planner" className="meal-planner card">
      <div className="meal-planner-header">
        <div>
          <span className="section-kicker">02 / FUEL</span>
          <h2>Macro tracker + meal planner</h2>
        </div>
        <span className="meal-source">{loading ? "Loading snapshot…" : menu ? "VT menu snapshot" : "Menu unavailable"}</span>
      </div>

      {menu ? (
        <p className="dining-snapshot-note">
          Real VT menu for {new Date(`${menu.menuDate}T12:00:00Z`).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric", timeZone: "America/New_York" })}.
          {" "}Saved {new Date(menu.capturedAt).toLocaleString("en-US", { timeZone: "America/New_York", timeZoneName: "short" })}.
          {" "}This demo uses a saved snapshot, not today's availability. Nutrition is per listed serving.
          {" "}<a href={menu.menuUrl} target="_blank" rel="noopener noreferrer">VT source</a>
        </p>
      ) : null}

      <div className="meal-hall-toggle" role="group" aria-label="Dining hall selector">
        {DINING_HALLS.map(({ id, name }) => (
          <button
            key={id}
            type="button"
            className={hall === id ? "active" : ""}
            aria-pressed={hall === id}
            onClick={() => setHall(id)}
          >
            {name}
          </button>
        ))}
      </div>

      {error ? <p className="meal-error">{error}</p> : null}

      <div className="macro-grid" aria-live="polite" aria-atomic="true">
        <MacroCard label="Calories" value={totals.calories} suffix="kcal" />
        <MacroCard label="Protein" value={totals.protein} suffix="g" />
        <MacroCard label="Carbs" value={totals.carbs} suffix="g" />
        <MacroCard label="Fat" value={totals.fat} suffix="g" />
      </div>

      <div className="meal-plan-layout">
        <div className="meal-list-panel">
          <h3>Your plate</h3>
          <p className="plate-note">Your plate resets when you reload or leave this page.</p>
          <div className="meal-chip-list">
            {selectedMeals.length === 0 ? (
              <p className="empty-state">Add a meal, or type in anything you ate.</p>
            ) : (
              selectedMeals.map((meal) => (
                <div key={meal.id} className="meal-chip">
                  <div>
                    <strong>{meal.name}</strong>
                    <small>
                      {meal.hall} · 1 serving = {meal.servingSize} {meal.servingUnit}
                    </small>
                  </div>
                  <div className="meal-chip-actions">
                    <ServingControl name={meal.name} quantity={meal.quantity} onChange={(quantity) => changeServings(meal.id, quantity)} />
                    <small className="serving-subtotal">{summarizeDailyPlan([meal]).calories} kcal for {meal.quantity} {meal.quantity === 1 ? "serving" : "servings"}</small>
                    <button type="button" onClick={() => removeMeal(meal.id)} aria-label={`Remove ${meal.name}`}>
                      Remove
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="meal-list-panel">
          <h3>Search and add food</h3>
          <details
            key={hall}
            ref={foodDropdown}
            className="food-dropdown"
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.currentTarget.open = false;
                event.currentTarget.querySelector("summary")?.focus();
              }
            }}
          >
            <summary>Choose food <span>{loading ? "Loading…" : `${suggestions.length} foods`}</span></summary>
            <div className="food-dropdown-menu">
              <div className="meal-search-row">
                <input
                  type="search"
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                  placeholder="Search for chicken, salad, pasta…"
                  aria-label="Search for foods to add"
                />
              </div>
              <div className="meal-suggestion-list">
                {filteredSuggestions.length === 0 ? (
                  <p className="empty-state">{loading ? "Loading saved menu…" : error ? "Menu unavailable." : menu?.status === "no_menu" ? "VT returned no menu items for this hall on the snapshot date. Choose another hall or enter your own food." : "No matches for that search. Try a different food or add your own."}</p>
                ) : (
                  filteredSuggestions.map((meal) => (
                    <div key={meal.id} className="meal-row">
                      <div>
                        <strong>{meal.name}</strong>
                        <small>
                          {meal.servingSize} {meal.servingUnit} · {meal.mealPeriods?.join(", ")}
                        </small>
                        <small className="dining-nutrition">
                          {meal.nutrition ? `${meal.nutrition.calories} kcal · ${meal.nutrition.protein}g protein / ${meal.nutrition.carbs}g carbs / ${meal.nutrition.fat}g fat` : "Nutrition unavailable from VT. Not included in macro totals."}
                        </small>
                        <a className="dining-source-link" href={meal.sourceUrl} target="_blank" rel="noopener noreferrer">VT nutrition source</a>
                      </div>
                      <button type="button" disabled={!meal.nutrition} onClick={() => addMeal(meal)} aria-label={`Add ${meal.name}`}>
                        Add
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>
          </details>

          <form className="custom-meal-form" onSubmit={handleCustomMealSubmit}>
            <input
              type="text"
              value={customMealName}
              onChange={(event) => setCustomMealName(event.target.value)}
              placeholder="Or type any food you ate"
              aria-label="Custom food name"
              required
            />
            <p className="dining-snapshot-note">Custom entries use the nutrition you provide for one serving.</p>
            <div className="custom-macro-grid">
              <label>Calories<input type="number" min="0" step="any" required value={customCalories} onChange={(e) => setCustomCalories(e.target.value)} /></label>
              <label>Protein (g)<input type="number" min="0" step="any" required value={customProtein} onChange={(e) => setCustomProtein(e.target.value)} /></label>
              <label>Carbs (g)<input type="number" min="0" step="any" required value={customCarbs} onChange={(e) => setCustomCarbs(e.target.value)} /></label>
              <label>Fat (g)<input type="number" min="0" step="any" required value={customFat} onChange={(e) => setCustomFat(e.target.value)} /></label>
            </div>
            <button type="submit" className="add-custom-button">Add custom meal</button>
          </form>

        </div>
      </div>
    </section>
  );
}
