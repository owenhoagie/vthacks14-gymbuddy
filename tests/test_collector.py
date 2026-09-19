import csv
from datetime import datetime, timezone
from urllib.error import URLError

import pytest

from collector.run import (
    FACILITIES,
    URL,
    append_observation,
    collect_once,
    latest_observations,
    parse_occupancy,
)

NOW = datetime(2026, 9, 19, 17, 0, tzinfo=timezone.utc)


def html(facility="mccomas", count=100, remaining=500, capacity=600, mobile=True):
    source = FACILITIES[facility][1]
    snippets = []
    for suffix in ["", "-sm"] if mobile else [""]:
        snippets.append(
            f'<canvas id="occupancyChart-{source}{suffix}" data-ratio="0.17" data-occupancy="{count}" data-remaining="{remaining}" aria-labelledby="chartDesc-{source}{suffix}"></canvas><span id="chartDesc-{source}{suffix}">Max Occupancy: {capacity}, Current Occupancy: 17%</span>'
        )
    return "\n".join(snippets)


@pytest.mark.parametrize("facility", list(FACILITIES))
def test_real_source_canvas_format_deduplicates_and_normalizes(facility):
    row = parse_occupancy(html(facility), facility, NOW)
    assert row["facility_name"] == FACILITIES[facility][0]
    assert row["occupancy"] == 100
    assert row["remaining"] == 500
    assert row["capacity"] == 600
    assert row["occupancy_pct"] == 16.67
    assert row["source_updated_at"] is None
    assert row["observed_at"] == NOW.isoformat()


def test_preserves_overcapacity_despite_clamped_remaining():
    row = parse_occupancy(html(count=650, remaining=0), "mccomas", NOW)
    assert row["capacity"] == 600
    assert row["occupancy_pct"] == 108.33
    assert row["remaining"] == 0


def test_real_endpoint_and_cache_preserve_source_remaining(tmp_path):
    assert URL.endswith("/FacilityOccupancy/GetFacilityData")
    path = tmp_path / "observations.csv"
    append_observation(path, parse_occupancy(html(count=650, remaining=0), "mccomas", NOW))
    assert latest_observations(path)["mccomas"]["remaining"] == 0


def test_capacity_without_description_is_count_plus_remaining():
    source = FACILITIES["mccomas"][1]
    content = (
        f'<canvas id="occupancyChart-{source}" data-occupancy="70" data-remaining="30"></canvas>'
    )
    assert parse_occupancy(content, "mccomas", NOW)["occupancy_pct"] == 70


@pytest.mark.parametrize(
    "content",
    [
        "<html>Temporarily unavailable</html>",
        html(count="oops"),
        html(count=-1),
        html(count=0, remaining=0, capacity=0),
    ],
)
def test_rejects_malformed_source(content):
    with pytest.raises(ValueError):
        parse_occupancy(content, "mccomas", NOW)


def test_rejects_conflicting_responsive_markup_and_naive_time():
    with pytest.raises(ValueError, match="Conflicting"):
        parse_occupancy(
            html(count=100, mobile=False) + html(count=110, mobile=False), "mccomas", NOW
        )
    with pytest.raises(ValueError, match="timezone"):
        parse_occupancy(html(), "mccomas", NOW.replace(tzinfo=None))


def test_partial_failure_saves_success_and_preserves_prior_cache(tmp_path):
    path = tmp_path / "observations.csv"
    old = parse_occupancy(html("war_memorial"), "war_memorial", NOW)
    append_observation(path, old)

    def fetcher(facility):
        if facility == "war_memorial":
            raise URLError("network unavailable")
        return html(facility, count=200, remaining=400)

    assert collect_once(path, fetcher) == (1, 1)
    rows = list(csv.DictReader(path.open()))
    assert len(rows) == 2
    cache = latest_observations(path)
    assert cache["mccomas"]["occupancy"] == 200
    assert cache["war_memorial"]["observed_at"] == NOW.isoformat()
    assert cache["war_memorial"]["source_updated_at"] is None


def test_cache_selects_newest_and_skips_truncated_rows(tmp_path):
    path = tmp_path / "observations.csv"
    newer = parse_occupancy(html(count=120, remaining=480), "mccomas", NOW.replace(hour=18))
    append_observation(path, newer)
    append_observation(path, parse_occupancy(html(), "mccomas", NOW))
    with path.open("a") as f:
        f.write("mccomas,broken\n")
    assert latest_observations(path)["mccomas"]["observed_at"] == newer["observed_at"]
