import SiteHeader from "@/components/site-header";
import MealPlannerCard from "@/components/meal-planner";

export default function MealPlannerPage() {
  return (
    <div className="meal-planner-page">
      <SiteHeader active="food" />
      <main className="page-shell">
        <section className="page-intro meal-planner-intro">
          <div>
            <div className="eyebrow">FUEL FOR THE DAY</div>
            <h1>
              Build your <em>meal plan.</em>
            </h1>
            <p>Pick meals, track macros, and keep your day on pace.</p>
          </div>
        </section>
        <MealPlannerCard />
      </main>
    </div>
  );
}
