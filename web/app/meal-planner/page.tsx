import MealPlannerCard from "@/components/meal-planner";

export default function MealPlannerPage() {
  return (
    <main className="meal-planner-page">
      <header className="site-header">
        <a className="wordmark" href="/" aria-label="GymBuddy home">
          <span className="brand-icon">
            <svg
              width="23"
              height="23"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.65"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M7 9v6M17 9v6M4 7v10M20 7v10M7 12h10M2 10v4M22 10v4" />
            </svg>
          </span>
          gym<span>buddy</span>
          <span className="brand-period">.</span>
        </a>
        <div className="header-right">
          <a className="header-link" href="/">Back to home</a>
          <span className="campus-pill">
            <span className="status-dot" />
            Virginia Tech
          </span>
        </div>
      </header>
      <div className="page-shell">
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
      </div>
    </main>
  );
}
