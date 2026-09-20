import ThemeToggle from "./theme-toggle";

export default function SiteHeader({ active }: { active: "gym" | "food" }) {
  return (
    <header className="site-header section-header">
      <a className="wordmark" href="/" aria-label="GymBuddy home">
        <span className="brand-icon">
          <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M7 9v6M17 9v6M4 7v10M20 7v10M7 12h10M2 10v4M22 10v4" />
          </svg>
        </span>
        gym<span>buddy</span><span className="brand-period">.</span>
      </a>
      <nav className="section-nav" aria-label="Main navigation">
        <a href="/" aria-current={active === "gym" ? "page" : undefined}>Gym</a>
        <a href="/meal-planner" aria-current={active === "food" ? "page" : undefined}>Food</a>
      </nav>
      <div className="header-right">
        <span className="campus-pill"><span className="status-dot" />Virginia Tech</span>
        <ThemeToggle />
      </div>
    </header>
  );
}
