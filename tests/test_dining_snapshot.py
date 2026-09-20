import json
from datetime import date

import pytest

from scripts import snapshot_dining


def test_nutrition_retains_zero_and_decimals():
    label = {
        "hasNoNutritionInformation": False,
        "calories": "0",
        "proteinGrams": "6.7",
        "totalCarbohydratesGrams": "31.7",
        "totalFatGrams": "6.3",
    }
    assert snapshot_dining.parse_nutrition(label) == {
        "calories": 0,
        "protein": 6.7,
        "carbs": 31.7,
        "fat": 6.3,
    }
    for missing in (None, "", "- - -", "NaN", "Infinity", "-1", True):
        assert snapshot_dining.parse_nutrition({**label, "calories": missing}) is None
    assert snapshot_dining.parse_nutrition({**label, "hasNoNutritionInformation": True}) is None


def test_capture_uses_hall_date_and_exact_fractional_serving(monkeypatch):
    monkeypatch.setattr(snapshot_dining, "LOCATION_IDS", ("15",))
    calls = []

    def fake_fetch(url):
        calls.append(url)
        if "Locations.aspx" in url:
            return [{"id": "15", "name": "D2 at Dietrick Hall"}]
        if "MenuAtLocation.aspx" in url:
            recipe = {
                "recipeId": "123",
                "name": "Test Food",
                "portionSize": "1/2",
                "portionUnit": "CUP",
            }
            return {
                "locationNum": "15",
                "date": "09/19/2026",
                "meals": [
                    {
                        "mealName": meal,
                        "sections": [{"sectionName": "Station", "recipes": [recipe]}],
                    }
                    for meal in ("Lunch", "Dinner")
                ],
            }
        return {"hasNoNutritionInformation": True}

    monkeypatch.setattr(snapshot_dining, "fetch_json", fake_fetch)
    result = snapshot_dining.capture(date(2026, 9, 19))
    items = result["locations"][0]["items"]
    assert len(items) == 1
    assert items[0]["mealPeriods"] == ["Lunch", "Dinner"]
    assert items[0]["nutrition"] is None
    assert "recNumAndPort=123%2A1%2F2" in calls[-1]
    assert "locationNum=15" in calls[-1]
    assert len(calls) == 3


def test_failed_capture_preserves_previous_snapshot(monkeypatch, tmp_path):
    target = tmp_path / "saved.json"
    target.write_text(json.dumps({"previous": True}))
    monkeypatch.setattr(
        "sys.argv", ["snapshot_dining", "--date", "2026-09-19", "--output", str(target)]
    )

    def fail(_):
        raise RuntimeError("VT unavailable")

    monkeypatch.setattr(snapshot_dining, "capture", fail)
    with pytest.raises(RuntimeError, match="VT unavailable"):
        snapshot_dining.main()
    assert json.loads(target.read_text()) == {"previous": True}
