.PHONY: install train score api dashboard monitor test lint format smoke

install:
	pip install -e ".[dev]"

train:
	python scripts/train.py --tickers AAPL MSFT GOOGL TSLA AMZN --lookback 730

score:
	python scripts/score.py --ticker AAPL

api:
	uvicorn src.stock_risk.api.app:app --reload --host 0.0.0.0 --port 8000

dashboard:
	streamlit run ui/dashboard.py

monitor:
	python scripts/monitor.py --interval 3600

test:
	pytest tests/ -v

smoke:
	python scripts/smoke.py

lint:
	ruff check src/ tests/
	mypy src/

format:
	black src/ tests/ scripts/
