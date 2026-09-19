"""Export the authoritative FastAPI schema. Run before frontend type generation."""

import json
from pathlib import Path

from api.main import app


def main():
    destination = Path(__file__).resolve().parents[1] / "fixtures" / "openapi.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(app.openapi(), indent=2) + "\n")
    print(f"Exported {destination}")


if __name__ == "__main__":
    main()
