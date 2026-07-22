.PHONY: install train score api monitor test lint format smoke validate analyze-categories \
        migrate migrate-dry-run migrate-sql migration backup backup-list restore-drill \
        web-install web-test web-lint web-build web-ci \
        registry registry-compare validate-tail challenger

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

# ── Model governance & validation ([R4]-[R8]) ───────────────────────────────
registry:
	python scripts/registry.py list

registry-compare:
	@if [ -z "$(v)" ]; then echo "usage: make registry-compare v=<version>"; exit 2; fi
	python scripts/registry.py compare downside_risk $(v)

# Tail-risk backtests beyond Kupiec: breach independence, conditional coverage,
# Expected Shortfall. Runs offline from the committed snapshots by default.
validate-tail:
	python scripts/validate_tail.py

# Logistic / random forest / monotonic XGBoost through the same walk-forward
# path as the champion. Needs a live fetch.
challenger:
	python scripts/challenger.py --register

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

# ── Frontend ([R3]) ─────────────────────────────────────────────────────────
web-install:
	cd ui/web && npm ci

web-test:
	cd ui/web && npm run test:run

web-lint:
	cd ui/web && npm run lint

web-build:
	cd ui/web && npm run build

# Everything CI runs for the frontend, in the same order.
web-ci: web-lint web-test web-build

lint:
	ruff check src/ tests/ alembic/
	mypy src/

format:
	black src/ tests/ scripts/
