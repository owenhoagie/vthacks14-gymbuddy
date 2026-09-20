"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
    function syncTheme(event: StorageEvent) {
      if (event.key !== "gymbuddy-theme" && event.key !== null) return;
      const next = event.newValue === "dark" ? "dark" : "light";
      document.documentElement.dataset.theme = next;
      setTheme(next);
    }
    window.addEventListener("storage", syncTheme);
    return () => window.removeEventListener("storage", syncTheme);
  }, []);

  function chooseTheme(next: Theme) {
    document.documentElement.dataset.theme = next;
    setTheme(next);
    try {
      localStorage.setItem("gymbuddy-theme", next);
    } catch {
      // The toggle still works when browser storage is unavailable.
    }
  }

  const label = `Switch to ${theme === "light" ? "dark" : "light"} mode`;

  return (
    <button
      className="theme-toggle"
      type="button"
      aria-label={label}
      title={label}
      onClick={() => chooseTheme(theme === "light" ? "dark" : "light")}
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        focusable="false"
      >
        {theme === "light" ? (
          <path d="M20.9 13.1A9 9 0 0 1 10.9 3.1 9 9 0 1 0 20.9 13.1Z" />
        ) : (
          <>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" />
          </>
        )}
      </svg>
    </button>
  );
}
