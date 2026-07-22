.PHONY: install train score api monitor test lint format smoke validate analyze-categories \
        migrate migrate-dry-run migrate-sql migration backup backup-list restore-drill

install:
	pip install -e ".[dev]"

train:
	python scripts/train.py --tickers AAPL MSFT GOOGL TSLA AMZN --lookback 730

score:
	python scripts/score.py --ticker AAPL

api:
	uvicorn src.stock_risk.api.app:app --reload --host 0.0.0.0 --port 8000

monitor:
	python scripts/monitor.py --interval 3600

test:
	pytest tests/ -v

smoke:
	python scripts/smoke.py

validate:
	python scripts/validate_score.py

analyze-categories:
	python scripts/analyze_categories.py

# ── Schema migrations & backups ([R1]) ──────────────────────────────────────
# `migrate` is the guarded path: verified backup -> rehearsal on a copy of the
# real database -> upgrade -> auto-restore if it fails. Prefer it over calling
# `alembic upgrade head` directly.
migrate:
	python scripts/migrate.py

migrate-dry-run:
	python scripts/migrate.py --dry-run

migrate-sql:
	python scripts/migrate.py --sql

# Autogenerate a revision after changing a SQLModel table. Always read the
# generated file before committing — autogenerate cannot infer a data backfill,
# and renames come out as drop+add (which loses the column's data).
migration:
	@if [ -z "$(m)" ]; then echo "usage: make migration m='describe the change'"; exit 2; fi
	python -m alembic revision --autogenerate -m "$(m)"

backup:
	python scripts/backup_db.py create

backup-list:
	python scripts/backup_db.py list

# Proves the newest backup actually restores. A backup never restored is an
# assumption, not a recovery plan.
restore-drill:
	python scripts/backup_db.py drill

lint:
	ruff check src/ tests/ alembic/
	mypy src/

format:
	black src/ tests/ scripts/
