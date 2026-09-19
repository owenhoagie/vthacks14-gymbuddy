"""Initialize, backfill, synchronize, or inspect the configured GymBuddy warehouse."""

import argparse
import json
import logging

from api.config import Settings
from api.databricks import DatabricksConfig, DatabricksRepository
from collector.sync import sync_lock, synchronize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "backfill", "sync", "check"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    warehouse = DatabricksRepository(DatabricksConfig.from_settings(settings))
    try:
        if args.command == "init":
            with sync_lock(settings.occupancy_csv_path, warehouse):
                warehouse.initialize()
            print("GymBuddy Bronze, Silver, and Gold initialized.")
        elif args.command in ("backfill", "sync"):
            print(
                json.dumps(
                    synchronize(
                        settings.occupancy_csv_path, warehouse, full=args.command == "backfill"
                    )
                )
            )
        else:
            print(
                json.dumps(
                    {
                        "bronze": warehouse.execute(
                            f"SELECT COUNT(*) row_count, MAX(observed_at) latest "
                            f"FROM {warehouse.config.table('raw_occupancy')}"
                        ),
                        "occupancy": [r.model_dump(mode="json") for r in warehouse.get_occupancy()],
                        "forecasts": [
                            {
                                "facility_id": f.facility_id,
                                "points": len(f.points),
                                "observed_at": f.observed_at.isoformat(),
                                "confidence": f.confidence,
                            }
                            for f in warehouse.get_forecast()
                        ],
                    },
                    indent=2,
                )
            )
        return 0
    except Exception as exc:
        print(f"Databricks command failed ({type(exc).__name__}); observations retained.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
