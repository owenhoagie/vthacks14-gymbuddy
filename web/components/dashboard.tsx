"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import ForecastChart from "./forecast-chart";
import {
  apiRequest,
  type Candidate,
  type FacilityId,
  type ForecastResponse,
  type HealthResponse,
  type OccupancyResponse,
  type RecommendationRequest,
  type RecommendationResponse,
} from "@/lib/api";
import {
  dateLabel,
  easternDay,
  easternInstant,
  searchBounds,
  timeLabel,
} from "@/lib/time";

type Block = { id: number; day: string; start: string; end: string };
const GYMS: { id: FacilityId; name: string; short: string }[] = [
  { id: "mccomas", name: "McComas Hall", short: "McComas" },
  { id: "war_memorial", name: "War Memorial Hall", short: "War Memorial" },
];
function Icon({
  name,
  size = 20,
}: {
  name:
    | "arrow"
    | "clock"
    | "spark"
    | "gym"
    | "refresh"
    | "check"
    | "plus"
    | "close";
  size?: number;
}) {
  const paths = {
    arrow: (
      <>
        <path d="M5 12h14M13 6l6 6-6 6" />
      </>
    ),
    clock: (
      <>
        <circle cx="12" cy="12" r="8.5" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    spark: (
      <>
        <path d="m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6L12 3Z" />
      </>
    ),
    gym: (
      <>
        <path d="M7 9v6M17 9v6M4 7v10M20 7v10M7 12h10M2 10v4M22 10v4" />
      </>
    ),
    refresh: (
      <>
        <path d="M20 10a8 8 0 0 0-14-4L3 9m0-6v6h6M4 14a8 8 0 0 0 14 4l3-3m0 6v-6h-6" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    plus: <path d="M12 5v14M5 12h14" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

function CandidateDisplay({ candidate }: { candidate: Candidate }) {
  return (
    <>
      <div className="recommendation-headline">
        <h2>{candidate.facility_name}</h2>
        <div className="rec-percent">
          {Math.round(candidate.predicted_occupancy_pct)}
          <span>%</span>
          <small>predicted full</small>
        </div>
      </div>
      <div className="workout-time">
        {timeLabel(candidate.start_time)} <span>—</span>{" "}
        {timeLabel(candidate.end_time)}
      </div>
      <div className="rec-chips">
        <span>
          <Icon name="clock" size={14} />
          {Math.round(
            (Date.parse(candidate.end_time) -
              Date.parse(candidate.start_time)) /
              60000,
          )}{" "}
          min workout
        </span>
        <span>
          <span className="tiny-dot" />
          {candidate.exceeds_tolerance
            ? "Above your crowd preference"
            : "Within your crowd preference"}
        </span>
      </div>
    </>
  );
}

export default function Dashboard() {
  const [occupancy, setOccupancy] = useState<OccupancyResponse | null>(null);
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [result, setResult] = useState<RecommendationResponse | null>(null);
  const [duration, setDuration] = useState(75);
  const [preferred, setPreferred] = useState<FacilityId[]>(["mccomas"]);
  const [tolerance, setTolerance] = useState<"low" | "medium" | "high">("low");
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [now, setNow] = useState<Date | null>(null);
  const [loading, setLoading] = useState(true);
  const [planning, setPlanning] = useState(false);
  const [error, setError] = useState("");
  const [planError, setPlanError] = useState("");
  const [dirty, setDirty] = useState(false);
  const sequence = useRef(0);
  const nextId = useRef(3);
  const demo = occupancy?.data_mode === "demo" || health?.data_mode === "demo";

  async function makeRecommendation(
    currentBlocks: Block[],
    settings: {
      duration: number;
      preferred: FacilityId[];
      tolerance: "low" | "medium" | "high";
    },
    at: Date,
  ) {
    setPlanning(true);
    setPlanError("");
    try {
      const unavailable = currentBlocks.map((b) => {
        const start_time = easternInstant(b.day, b.start),
          end_time = easternInstant(b.day, b.end);
        if (end_time <= start_time)
          throw new Error(
            "Each unavailable block must end after it starts. Use two blocks for an overnight event.",
          );
        return { start_time, end_time };
      });
      const body: RecommendationRequest = {
        ...searchBounds(at),
        unavailable,
        workout_duration_minutes: settings.duration,
        preferred_gyms: settings.preferred,
        crowd_tolerance: settings.tolerance,
      };
      const recommendation = await apiRequest<RecommendationResponse>(
        "/recommend",
        { method: "POST", body: JSON.stringify(body) },
      );
      setResult(recommendation);
      setDirty(false);
    } catch (err) {
      setPlanError(
        err instanceof Error
          ? err.message
          : "We couldn't find your window. Try again.",
      );
    } finally {
      setPlanning(false);
    }
  }

  async function loadData(at: Date) {
    const request = ++sequence.current;
    setLoading(true);
    setError("");
    const bounds = searchBounds(at);
    const query = new URLSearchParams(bounds).toString();
    const settled = await Promise.allSettled([
      apiRequest<OccupancyResponse>("/occupancy"),
      apiRequest<ForecastResponse>(`/forecast?${query}`),
      apiRequest<HealthResponse>("/health"),
    ]);
    if (request !== sequence.current) return;
    const [o, f, h] = settled;
    if (o.status === "fulfilled") setOccupancy(o.value);
    if (f.status === "fulfilled") setForecast(f.value);
    if (h.status === "fulfilled") setHealth(h.value);
    if (settled.some((s) => s.status === "rejected"))
      setError(
        "We couldn't refresh all gym data. Check that the API is running, then try again. Any data still shown is from the previous fetch.",
      );
    setLoading(false);
  }

  useEffect(() => {
    const at = new Date(),
      day = easternDay(at);
    const defaults = [
      { id: 1, day, start: "10:00", end: "12:00" },
      { id: 2, day, start: "16:00", end: "17:15" },
    ];
    setNow(at);
    setBlocks(defaults);
    void loadData(at);
    void makeRecommendation(
      defaults,
      { duration: 75, preferred: ["mccomas"], tolerance: "low" },
      at,
    );
    return () => {
      sequence.current++;
    };
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    const at = new Date();
    setNow(at);
    void loadData(at);
    void makeRecommendation(blocks, { duration, preferred, tolerance }, at);
  }
  function changeBlock(
    id: number,
    field: "day" | "start" | "end",
    value: string,
  ) {
    setBlocks((previous) =>
      previous.map((b) => (b.id === id ? { ...b, [field]: value } : b)),
    );
    setDirty(true);
  }
  function clearDemoSchedule() {
    const at = new Date();
    setBlocks([]);
    setDuration(75);
    setPreferred(["mccomas"]);
    setTolerance("low");
    setNow(at);
    void loadData(at);
    void makeRecommendation(
      [],
      { duration: 75, preferred: ["mccomas"], tolerance: "low" },
      at,
    );
  }

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="wordmark" href="/" aria-label="GymBuddy home">
          <span className="brand-icon">
            <Icon name="gym" size={23} />
          </span>
          gym<span>buddy</span>
          <span className="brand-period">.</span>
        </a>
        <div className="header-right">
          <span className="campus-label">MADE FOR HOKIES</span>
          <span className="campus-pill">
            <span className="status-dot" />
            Virginia Tech
          </span>
        </div>
      </header>
      <main>
        <section className="page-intro">
          <div>
            <div className="eyebrow">LESS WAITING. MORE LIFTING.</div>
            <h1>
              Your day. <em>Your gym window.</em>
            </h1>
            <p>
              A little planning. A quieter gym. Find the right time to show up.
            </p>
          </div>
          <div className="today">
            <Icon name="clock" size={17} />
            <div>
              <strong>{now ? dateLabel(now) : "Your next workout"}</strong>
              <span>Blacksburg, VA · Eastern Time</span>
            </div>
          </div>
        </section>
        {demo ? (
          <div className="demo-banner">
            <span className="demo-tag">DEMO</span>
            <span>
              You’re exploring synthetic gym data. All times and recommendations
              are for this demo.
            </span>
            <button
              type="button"
              onClick={clearDemoSchedule}
              disabled={planning || loading}
            >
              Load demo scenario <span aria-hidden="true">↗</span>
            </button>
          </div>
        ) : null}
        {error ? (
          <div role="alert" className="error-banner">
            {error}
            <button
              type="button"
              onClick={() => void loadData(new Date())}
              disabled={loading}
            >
              Retry
            </button>
          </div>
        ) : null}
        <div className="dashboard-grid">
          <aside className="planner card">
            <div className="section-heading">
              <div>
                <span className="section-kicker">01 / YOUR ROUTINE</span>
                <h2>Make it fit.</h2>
              </div>
              <span className="outline-icon">
                <Icon name="clock" />
              </span>
            </div>
            <p className="section-description">
              Tell us when you’re free. We’ll find the gap.
            </p>
            <form onSubmit={submit}>
              <fieldset disabled={planning}>
                <legend>
                  Workout length <span>minutes</span>
                </legend>
                <div className="duration-options">
                  {[30, 45, 60, 75, 90].map((n) => (
                    <button
                      type="button"
                      className={duration === n ? "active" : ""}
                      aria-pressed={duration === n}
                      key={n}
                      onClick={() => {
                        setDuration(n);
                        setDirty(true);
                      }}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </fieldset>
              <fieldset disabled={planning}>
                <legend>
                  Where do you like to go? <span>optional</span>
                </legend>
                <div className="gym-options">
                  {GYMS.map((g) => (
                    <label
                      className={preferred.includes(g.id) ? "selected" : ""}
                      key={g.id}
                    >
                      <input
                        type="checkbox"
                        checked={preferred.includes(g.id)}
                        onChange={() => {
                          setPreferred((previous) =>
                            previous.includes(g.id)
                              ? previous.filter((id) => id !== g.id)
                              : [...previous, g.id],
                          );
                          setDirty(true);
                        }}
                      />
                      <span className="checkbox-mark">
                        {preferred.includes(g.id) ? (
                          <Icon name="check" size={12} />
                        ) : null}
                      </span>
                      {g.short}
                    </label>
                  ))}
                </div>
                <p className="field-note">
                  We’ll favor your picks, while checking both gyms.
                </p>
              </fieldset>
              <fieldset disabled={planning}>
                <legend>Your crowd comfort</legend>
                <div className="tolerance-options">
                  {(
                    [
                      { value: "low", label: "Keep it quiet", bars: "▂" },
                      { value: "medium", label: "Some buzz", bars: "▂▄" },
                      { value: "high", label: "Busy is fine", bars: "▂▄▆" },
                    ] as const
                  ).map((item) => (
                    <button
                      type="button"
                      key={item.value}
                      className={tolerance === item.value ? "active" : ""}
                      aria-pressed={tolerance === item.value}
                      onClick={() => {
                        setTolerance(item.value);
                        setDirty(true);
                      }}
                    >
                      <span aria-hidden="true">{item.bars}</span>
                      {item.label}
                    </button>
                  ))}
                </div>
              </fieldset>
              <fieldset disabled={planning}>
                <legend>
                  When are you unavailable?<span>Eastern Time</span>
                </legend>
                <div className="unavailable-blocks">
                  {blocks.map((block, index) => (
                    <div className="time-block" key={block.id}>
                      <div className="block-top">
                        <label className="block-date-label">
                          Busy block {index + 1}
                          <input
                            aria-label={`Date for busy block ${index + 1}`}
                            type="date"
                            value={block.day}
                            onChange={(e) =>
                              changeBlock(block.id, "day", e.target.value)
                            }
                            required
                          />
                        </label>
                        <button
                          type="button"
                          className="remove-block"
                          aria-label={`Remove busy block ${index + 1}`}
                          onClick={() => {
                            setBlocks((previous) =>
                              previous.filter((b) => b.id !== block.id),
                            );
                            setDirty(true);
                          }}
                        >
                          <Icon name="close" size={15} />
                        </button>
                      </div>
                      <div className="time-inputs">
                        <input
                          aria-label={`Start time for busy block ${index + 1}`}
                          type="time"
                          value={block.start}
                          onChange={(e) =>
                            changeBlock(block.id, "start", e.target.value)
                          }
                          required
                        />
                        <span>to</span>
                        <input
                          aria-label={`End time for busy block ${index + 1}`}
                          type="time"
                          value={block.end}
                          onChange={(e) =>
                            changeBlock(block.id, "end", e.target.value)
                          }
                          required
                        />
                      </div>
                    </div>
                  ))}
                </div>
                <button
                  className="add-block"
                  type="button"
                  disabled={blocks.length >= 50}
                  onClick={() => {
                    setBlocks((previous) => [
                      ...previous,
                      {
                        id: nextId.current++,
                        day: easternDay(new Date()),
                        start: "14:00",
                        end: "15:00",
                      },
                    ]);
                    setDirty(true);
                  }}
                >
                  <Icon name="plus" size={15} /> Add unavailable time
                </button>
              </fieldset>
              <button
                type="submit"
                className="primary-button"
                disabled={planning || !now}
              >
                {planning ? "Finding your window…" : "Find my gym window"}
                <Icon name="arrow" size={18} />
              </button>
              <p className="form-footnote">
                Looking at the next 4 hours · No calendar needed
              </p>
            </form>
          </aside>
          <div className="results-column">
            <section
              className="recommendation-card"
              aria-live="polite"
              aria-busy={planning}
            >
              <div className="recommendation-top">
                <span className="section-kicker">
                  <Icon name="spark" size={16} /> YOUR BEST WINDOW
                </span>
                <span className="recommendation-status">
                  {planning
                    ? "PLANNING"
                    : dirty
                      ? "UPDATE TO APPLY CHANGES"
                      : result?.recommendation
                        ? "MADE FOR YOUR DAY"
                        : "LET’S FIND YOUR TIME"}
                </span>
              </div>
              {planning && !result ? (
                <div className="recommendation-empty">
                  <h2>
                    A good workout starts
                    <br />
                    with a little space.
                  </h2>
                  <p>Checking your schedule and the crowd forecast…</p>
                </div>
              ) : result?.recommendation ? (
                <CandidateDisplay candidate={result.recommendation} />
              ) : (
                <div className="recommendation-empty">
                  <h2>
                    {result?.status === "no_available_window"
                      ? "Let’s make a little room."
                      : result?.status === "data_unavailable"
                        ? "Waiting on gym data."
                        : "Your next good workout."}
                  </h2>
                  <p>
                    {result?.explanation ||
                      "Set your routine and we’ll help you find a quieter time to go."}
                  </p>
                </div>
              )}
              {result?.recommendation ? (
                <div className="recommendation-reason">
                  <Icon name="check" size={17} />
                  <p>{result.explanation}</p>
                </div>
              ) : null}
              {planError ? (
                <p className="plan-error" role="alert">
                  {planError}
                </p>
              ) : null}
              {result?.warnings?.length ? (
                <div className="recommendation-warnings">
                  {result.warnings.map((warning) => (
                    <p key={warning}>{warning}</p>
                  ))}
                </div>
              ) : null}
              {result ? (
                <div className="rec-meta">
                  {result.data_mode === "demo"
                    ? "Synthetic demo"
                    : result.recommendation?.provenance === "cached"
                      ? "Cached data"
                      : "Live data"}{" "}
                  ·{" "}
                  {result.method === "deterministic"
                    ? "Schedule-based ranking"
                    : "Assisted ranking"}{" "}
                  ·{" "}
                  {result.recommendation?.confidence
                    ? `${result.recommendation.confidence} confidence · `
                    : ""}
                  Updated {timeLabel(result.generated_at)} ET
                  {dirty ? " · Settings changed" : ""}
                </div>
              ) : null}
            </section>
            {result?.alternative ? (
              <div className="alternative card">
                <span className="alternative-label">ANOTHER GOOD OPTION</span>
                <div>
                  <strong>{result.alternative.facility_name}</strong>
                  <span>
                    {timeLabel(result.alternative.start_time)} –{" "}
                    {timeLabel(result.alternative.end_time)}
                  </span>
                </div>
                <span className="alternative-percent">
                  {Math.round(result.alternative.predicted_occupancy_pct)}%{" "}
                  <small>full</small>
                </span>
                <Icon name="arrow" size={18} />
              </div>
            ) : null}
            <section className="occupancy-section">
              <div className="row-heading">
                <h2>
                  At the gyms <span>right now</span>
                </h2>
                <button
                  type="button"
                  className="text-button"
                  disabled={loading}
                  onClick={() => void loadData(new Date())}
                >
                  <Icon name="refresh" size={13} />
                  {loading ? "Refreshing" : "Refresh"}
                </button>
              </div>
              <div className="occupancy-grid">
                {GYMS.map((gym) => {
                  const gymData = occupancy?.facilities.find(
                    (f) => f.facility_id === gym.id,
                  );
                  const percent = gymData?.occupancy_pct;
                  const unavailable =
                    !gymData ||
                    percent == null ||
                    gymData.provenance === "unavailable";
                  return (
                    <article className="gym-card card" key={gym.id}>
                      <div className="gym-card-top">
                        <span
                          className={`gym-icon ${gym.id === "war_memorial" ? "orange-icon" : ""}`}
                        >
                          <Icon name="gym" size={21} />
                        </span>
                        <span
                          className={`crowd-badge ${unavailable ? "muted" : percent > 65 ? "busy" : ""}`}
                        >
                          {unavailable
                            ? loading
                              ? "Loading"
                              : "Unavailable"
                            : gymData.stale
                              ? "Stale data"
                              : gymData.provenance === "cached"
                                ? "Cached"
                                : percent <= 40
                                  ? "Room to move"
                                  : percent <= 65
                                    ? "Some activity"
                                    : "Getting busy"}
                        </span>
                      </div>
                      <h3>{gym.name}</h3>
                      <div className="occupancy-number">
                        {unavailable ? "—" : Math.round(percent)}
                        {!unavailable ? (
                          <span>
                            %<small>full</small>
                          </span>
                        ) : null}
                      </div>
                      <div className="occupancy-bar">
                        <span
                          className={gym.id === "war_memorial" ? "orange" : ""}
                          style={{
                            width: `${unavailable ? 0 : Math.min(percent, 100)}%`,
                          }}
                        />
                      </div>
                      <div className="gym-card-bottom">
                        <span>
                          {unavailable
                            ? "No observation available"
                            : `${gymData.occupancy} / ${gymData.capacity} people`}
                        </span>
                        <span>
                          {gymData?.provenance === "demo"
                            ? "Synthetic"
                            : gymData?.provenance === "cached"
                              ? "Cached"
                              : ""}
                        </span>
                      </div>
                      <p className="fetched-time">
                        {gymData?.observed_at
                          ? `Fetched ${timeLabel(gymData.observed_at)} ET${gymData.stale ? " · stale" : ""}`
                          : "Awaiting a successful fetch"}
                      </p>
                      {gymData &&
                      gymData.provenance !== "demo" &&
                      gymData.observed_at ? (
                        <p className="fetched-time">
                          {gymData.source_updated_at
                            ? `Source updated ${timeLabel(gymData.source_updated_at)} ET`
                            : "Source update time unavailable"}
                        </p>
                      ) : null}
                    </article>
                  );
                })}
              </div>
            </section>
            <section className="forecast-card card">
              <div className="row-heading">
                <div>
                  <span className="section-kicker">A LITTLE LOOK AHEAD</span>
                  <h2>Follow the quieter hours.</h2>
                </div>
                <span className="next-hours">NEXT 4 HOURS</span>
              </div>
              <ForecastChart
                data={forecast}
                candidate={result?.recommendation ?? null}
                loading={loading}
              />
              <p className="forecast-note">
                {demo
                  ? "Illustrative forecasts from synthetic demo data."
                  : "Forecasts are estimates, not a guarantee of space."}{" "}
                {forecast?.facilities.some((f) => f.stale)
                  ? "Some underlying observations are stale. "
                  : ""}
                All times Eastern.
              </p>
            </section>
          </div>
        </div>
        <footer>
          <span>
            gymbuddy<span className="brand-period">.</span>{" "}
            <span className="footer-divider">/</span> More reps. Less waiting.
          </span>
          <span>
            Built at VTHacks 14 <span aria-hidden="true">↗</span>
          </span>
        </footer>
      </main>
    </div>
  );
}
