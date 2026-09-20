"""Manually capture VT FoodPro menus and serving-specific nutrition. No scheduler."""

from __future__ import annotations

import argparse
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://foodpro.students.vt.edu/menus/API/"
LOCATION_IDS = ("15", "09", "16", "18")
OUTPUT = Path(__file__).resolve().parents[1] / "web/fixtures/dining-snapshot.json"


def api_url(endpoint: str, **params: str) -> str:
    return API + endpoint + ("?" + urlencode(params) if params else "")


def fetch_json(url: str):
    for attempt in range(3):
        try:
            with urlopen(
                Request(url, headers={"Accept": "application/json"}), timeout=25
            ) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code != 429 and error.code < 500:
                raise
            if attempt == 2:
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(attempt + 1)
    raise RuntimeError("Unreachable")


def parse_nutrition(label: dict) -> dict | None:
    """Keep missing nutrition missing, including nonnumeric FoodPro placeholders."""
    if label.get("hasNoNutritionInformation") is not False:
        return None
    result = {}
    for name, key in (
        ("calories", "calories"),
        ("protein", "proteinGrams"),
        ("carbs", "totalCarbohydratesGrams"),
        ("fat", "totalFatGrams"),
    ):
        raw = label.get(key)
        if raw is None or isinstance(raw, bool):
            return None
        try:
            value = float(raw)
        except (ValueError, TypeError):
            return None
        if not math.isfinite(value) or value < 0:
            return None
        result[name] = value
    return result


def capture(menu_date: date) -> dict:
    upstream_date = menu_date.strftime("%m/%d/%Y")
    directory = {row["id"]: row["name"].strip() for row in fetch_json(api_url("Locations.aspx"))}
    locations = []
    for location_id in LOCATION_IDS:
        name = directory[location_id]
        menu_url = api_url("MenuAtLocation.aspx", locationNum=location_id, dtdate=upstream_date)
        menu = fetch_json(menu_url)
        if (
            menu.get("locationNum") != location_id
            or menu.get("date") != upstream_date
            or not isinstance(menu.get("meals"), list)
        ):
            raise ValueError(f"Unexpected menu response for {name}")
        unique = {}
        for period in menu["meals"]:
            for station in period.get("sections", []):
                for recipe in station.get("recipes", []):
                    key = (recipe["recipeId"], recipe["portionSize"], recipe["portionUnit"])
                    if not all(
                        isinstance(value, str) and value.strip() for value in (*key, recipe["name"])
                    ):
                        raise ValueError(f"Missing recipe or serving identity for {name}")
                    if key not in unique:
                        unique[key] = {
                            "id": f"{location_id}:{':'.join(key)}",
                            "recipeId": key[0],
                            "name": recipe["name"].strip(),
                            "hall": name,
                            "hallId": location_id,
                            "servingSize": key[1],
                            "servingUnit": key[2],
                            "mealPeriods": [],
                            "stations": [],
                            "allergens": recipe.get("allergens", ""),
                            "source": "foodpro",
                            "sourceUrl": api_url(
                                "Label.aspx",
                                locationNum=location_id,
                                dtdate=upstream_date,
                                recNumAndPort=f"{key[0]}*{key[1]}",
                            ),
                        }
                    item = unique[key]
                    for field, value in (
                        ("mealPeriods", period["mealName"]),
                        ("stations", station["sectionName"]),
                    ):
                        if value and value not in item[field]:
                            item[field].append(value)

        def with_nutrition(item):
            label = fetch_json(item["sourceUrl"])
            if not isinstance(label, dict):
                raise ValueError("Unexpected nutrition response")
            return {**item, "nutrition": parse_nutrition(label)}

        # Limit pressure on VT. A failed request aborts publication and retains the old file.
        with ThreadPoolExecutor(max_workers=3) as pool:
            items = list(pool.map(with_nutrition, unique.values()))
        locations.append(
            {
                "id": location_id,
                "name": name,
                "menuUrl": menu_url,
                "status": "available" if items else "no_menu",
                "items": items,
            }
        )
        print(
            f"{name}: {len(items)} foods; {sum(item['nutrition'] is not None for item in items)} with nutrition",
            flush=True,
        )
    return {
        "version": 1,
        "source": "VT FoodPro",
        "menuDate": menu_date.isoformat(),
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "locations": locations,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date", required=True, type=date.fromisoformat, help="Menu date, YYYY-MM-DD"
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    snapshot = capture(args.date)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(args.output)
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
