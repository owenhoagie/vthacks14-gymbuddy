.PHONY: install api web collect collect-once test contracts smoke build fixtures

install:
	python3 -m venv .venv
	.venv/bin/python -m pip install -e '.[dev]'
	cd web && npm ci

api:
	.venv/bin/python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000

web:
	cd web && npm run dev

collect:
	.venv/bin/python -m collector

collect-once:
	.venv/bin/python -m collector --once

test:
	.venv/bin/ruff check api collector scripts tests
	.venv/bin/python -m pytest -q
	cd web && npm run typecheck

contracts:
	.venv/bin/python -m scripts.export_contracts
	cd web && npm run generate:types

smoke:
	.venv/bin/python -m scripts.smoke_test

build:
	cd web && npm run build

fixtures:
	.venv/bin/python -m scripts.seed_demo_data

.PHONY: demo-history
demo-history:
	.venv/bin/python -m scripts.generate_demo_history
	.venv/bin/python -m scripts.seed_demo_data

.PHONY: db-init db-backfill db-sync db-check

db-init:
	.venv/bin/python -m scripts.databricks init

db-backfill:
	.venv/bin/python -m scripts.databricks backfill

db-sync:
	.venv/bin/python -m scripts.databricks sync

db-check:
	.venv/bin/python -m scripts.databricks check
