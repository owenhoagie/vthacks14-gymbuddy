import type { Candidate, ForecastResponse } from "@/lib/api";
import { timeLabel } from "@/lib/time";

type Props = {
  data: ForecastResponse | null;
  candidate: Candidate | null;
  loading: boolean;
};
export default function ForecastChart({ data, candidate, loading }: Props) {
  const facilities = data?.facilities.filter((f) => f.points.length > 1) ?? [];
  if (!facilities.length)
    return (
      <div className="chart-placeholder">
        {loading
          ? "Finding the quieter hours…"
          : "Forecast unavailable. Collect observations to begin."}
      </div>
    );
  const times = facilities.flatMap((f) =>
    f.points.map((p) => Date.parse(p.forecast_time)),
  );
  const first = Math.min(...times),
    last = Math.max(...times);
  const x = (time: number) => 46 + ((time - first) / (last - first || 1)) * 666;
  const y = (percent: number) => 190 - percent * 1.55;
  const selectionStart = candidate
    ? Math.max(first, Date.parse(candidate.start_time))
    : 0;
  const selectionEnd = candidate
    ? Math.min(last, Date.parse(candidate.end_time))
    : 0;
  return (
    <div className="chart-wrap">
      <svg
        viewBox="0 0 750 230"
        role="img"
        aria-label="Predicted gym occupancy over the next four hours for McComas Hall and War Memorial Hall. Line colors match the legend. The shaded region is your recommended workout."
      >
        {[0, 25, 50, 75, 100].map((n) => (
          <g key={n}>
            <line
              x1="46"
              x2="712"
              y1={y(n)}
              y2={y(n)}
              stroke="var(--chart-grid)"
              strokeDasharray={n === 0 ? undefined : "3 5"}
            />
            <text x="29" y={y(n) + 4} textAnchor="end" className="chart-label">
              {n}%
            </text>
          </g>
        ))}
        {candidate && selectionEnd > selectionStart ? (
          <rect
            x={x(selectionStart)}
            y="26"
            width={x(selectionEnd) - x(selectionStart)}
            height="164"
            rx="6"
            fill="var(--chart-window)"
            opacity="var(--chart-window-opacity)"
          />
        ) : null}
        {facilities.map((f) => (
          <polyline
            key={f.facility_id}
            points={f.points
              .map(
                (p) =>
                  `${x(Date.parse(p.forecast_time)).toFixed(1)},${y(p.predicted_occupancy_pct).toFixed(1)}`,
              )
              .join(" ")}
            fill="none"
            stroke={f.facility_id === "mccomas" ? "var(--chart-primary)" : "var(--chart-secondary)"}
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}
        {[0, 1, 2, 3, 4].map((n) => (
          <text
            key={n}
            x={46 + n * 166.5}
            y="218"
            textAnchor="middle"
            className="chart-label"
          >
            {timeLabel(new Date(first + ((last - first) * n) / 4))}
          </text>
        ))}
      </svg>
      <div className="chart-caption">
        <span>
          <span className="legend-dot primary" />
          McComas Hall
        </span>
        <span>
          <span className="legend-dot orange" />
          War Memorial Hall
        </span>
        <span className="window-legend">▧ Your workout window</span>
      </div>
    </div>
  );
}
