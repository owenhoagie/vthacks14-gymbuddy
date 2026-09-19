"""Read-only warehouse checks, including synthetic SELECT-only forecast boundary cases.

No synthetic observations are written to any table.
"""

from datetime import datetime, timezone

from api.config import Settings
from api.databricks import DatabricksRepository
from collector.run import latest_observations


def main():
    repo = DatabricksRepository()
    # Exercise the actual Gold SQL against an inline relation, never a synthetic table.
    query = repo.template("03_gold.sql")
    query = query[query.index("WITH latest AS") :]
    cases = """(SELECT * FROM VALUES
      ('cold', 'Cold', 25.0, 25.0, 1, 25.0, TIMESTAMP '2026-09-19 12:00:00',
        TIMESTAMP '2026-09-19 12:00:00'),
      ('rise', 'Rise', 100.0, 70.0, 3, 0.0, TIMESTAMP '2026-09-19 12:00:00',
        TIMESTAMP '2026-09-19 11:50:00'),
      ('fall', 'Fall', 0.0, 30.0, 3, 100.0, TIMESTAMP '2026-09-19 12:00:00',
        TIMESTAMP '2026-09-19 11:50:00')
      AS t(facility_id, facility_name, occupancy_pct, rolling_mean_pct, sample_count,
           first_pct, observed_at, first_observed_at))"""
    result = repo.execute(query.replace(repo.config.table("occupancy_features"), cases))
    groups = {
        name: sorted(
            [r for r in result if r["facility_id"] == name], key=lambda r: r["forecast_time"]
        )
        for name in ("cold", "rise", "fall")
    }
    assert all(len(rows) == 49 for rows in groups.values())
    assert all(
        float(r["predicted_occupancy_pct"]) == 25 and r["confidence"] == "low"
        for r in groups["cold"]
    )
    assert float(groups["rise"][1]["predicted_occupancy_pct"]) == 71.25
    assert float(groups["fall"][1]["predicted_occupancy_pct"]) == 28.75
    assert float(groups["rise"][-1]["predicted_occupancy_pct"]) == 100
    assert float(groups["fall"][-1]["predicted_occupancy_pct"]) == 0
    print("PASS warehouse forecast cold start, slope caps, bounds, and 49-point horizon")
    duplicate = repo.execute(
        f"SELECT facility_id, observed_at, COUNT(*) n "
        f"FROM {repo.config.table('raw_occupancy')} GROUP BY facility_id, observed_at HAVING COUNT(*) > 1"
    )
    assert not duplicate
    local = latest_observations(Settings().occupancy_csv_path)
    occupancy = repo.get_occupancy()
    forecasts = {f.facility_id: f for f in repo.get_forecast()}
    for row in occupancy:
        assert row.occupancy == local[row.facility_id]["occupancy"]
        assert row.observed_at == datetime.fromisoformat(local[row.facility_id]["observed_at"])
        assert row.source_updated_at is None
        forecast = forecasts[row.facility_id]
        assert len(forecast.points) == 49
        assert forecast.observed_at == row.observed_at
        assert all(0 <= p.predicted_occupancy_pct <= 100 for p in forecast.points)
        assert datetime.now(timezone.utc) - row.observed_at < __import__("datetime").timedelta(
            minutes=15
        )
        print(
            f"PASS {row.facility_id.value}: CSV = Bronze = Gold observation {row.observed_at.isoformat()}"
        )


if __name__ == "__main__":
    main()
