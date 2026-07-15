# Stock Risk Scoring System

A production-style system that predicts **downside risk** and **volatility** for individual stocks using live market data fetched via `yfinance`, technical indicators, and machine learning models (XGBoost + sklearn Pipeline).

## Architecture

```
yfinance (live data)
       │
       ▼
DataPreprocessor          ← gap-fill, outlier removal, log/pct returns
       │
       ▼
TechnicalFeatures         ← RSI, MACD, Bollinger Bands, ATR, OBV, EMA
       │
       ▼
RiskMetrics               ← VaR, CVaR, Sharpe, Sortino, drawdown, EWMA vol, liquidity, beta
       │
       ├──► risk_categories.py  (percentile composite)  ← primary, explainable risk_score
       ├──► XGBoost classifier  (P[drawdown ≤ -10% / 20d]) ← secondary ml_drawdown_probability
       └──► GARCH(1,1), fit live per ticker              ← secondary garch_volatility_forecast
                │
                ▼
          Risk Scorecard (0–100 + label + category breakdown)
                │
       ┌────────┴────────┐
       ▼                 ▼
  FastAPI REST      Streamlit Dashboard
  /score/{ticker}   ui/dashboard.py
```

## Components

| Module | Description |
|--------|-------------|
| `data/fetcher.py` | Fetches OHLCV, fundamentals, and options IV via **yfinance** |
| `data/preprocessor.py` | Business-day alignment, 6σ outlier removal, log/pct returns |
| `features/technical.py` | RSI, MACD, Bollinger Bands, ATR, OBV, EMA 20/50/200 via **pandas-ta** |
| `features/risk_metrics.py` | Rolling VaR, CVaR, Sharpe, Sortino, drawdown, skew, kurtosis, EWMA vol, liquidity, beta |
| `scoring/risk_categories.py` | Percentile-based composite score across 5 risk categories (explainable baseline) |
| `models/volatility.py` | GARCH(1,1) volatility forecasting via **arch** |
| `models/downside_risk.py` | **XGBoost** classifier (P[max drawdown ≤ -10% in 20d]) inside **sklearn ColumnTransformer** pipeline |
| `models/evaluation.py` | Chronological Logistic Regression / Random Forest / XGBoost comparison (Precision/Recall/F1/ROC-AUC/PR-AUC) |
| `scoring/scorer.py` | End-to-end orchestration: fetch → preprocess → engineer → score |
| `monitoring/drift.py` | PSI + KS-test feature drift detection |
| `monitoring/metrics.py` | Prometheus gauges and JSONL score logging |
| `api/app.py` | **FastAPI** REST endpoints with Prometheus `/metrics` |
| `ui/dashboard.py` | **Streamlit** interactive dashboard with Plotly charts |

## Quick Start

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Copy and configure environment
cp .env.example .env

# 3. Train baseline models
python scripts/train.py --tickers AAPL MSFT GOOGL --lookback 730

# 4. Score a single ticker (CLI)
python scripts/score.py --ticker TSLA

# 5. Launch the Streamlit dashboard
streamlit run ui/dashboard.py
# or:  make dashboard

# 6. Start the REST API
uvicorn src.stock_risk.api.app:app --reload
# or:  make api
```

## Data Pipeline

```python
from stock_risk.data.fetcher import MarketDataFetcher
from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.features.technical import TechnicalFeatures
from stock_risk.features.risk_metrics import RiskMetrics

fetcher = MarketDataFetcher()
raw = fetcher.fetch_history("AAPL", period="2y")          # yfinance live
df  = DataPreprocessor().process(raw)                      # clean
df  = TechnicalFeatures().compute(df)                      # indicators
df  = RiskMetrics().compute(df)                            # risk metrics
```

## Model Training

The primary risk score (`risk_score` in the API response) is a **percentile-based composite** over five categories — volatility, tail, drawdown, market sensitivity, liquidity — computed relative to each stock's own historical distribution (see `scoring/risk_categories.py`). It requires no training and is fully explainable via `risk_breakdown`.

A secondary, ML-derived signal (`ml_drawdown_probability`) is produced by an **XGBoost classifier** wrapped in a **scikit-learn pipeline** with a `ColumnTransformer` that applies median imputation + `StandardScaler` independently to three feature groups (momentum, volatility, quality). Its target is binary: did the stock's max drawdown breach -10% within the next 20 trading days?

```python
from stock_risk.models.downside_risk import DownsideRiskModel

model = DownsideRiskModel(n_estimators=300, max_depth=5)
model.fit(df)             # label = forward 20-day max drawdown <= -10%
score = model.predict(df)["downside_risk_score"]   # P(event) x 100
```

Falls back to a constant base-rate score (instead of raising) when the training window has no drawdown events at all, since XGBoost can't fit a single-class target.

Feature importances are accessible via `model.feature_importance()`. `scripts/train.py` also runs `models/evaluation.py::compare_classifiers`, which benchmarks Logistic Regression / Random Forest / XGBoost on a chronological (never random) train/test split and reports Precision/Recall/F1/ROC-AUC/PR-AUC/confusion-matrix — accuracy alone is misleading here since drawdown events are a rare minority class.

## FastAPI Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/score/{ticker}` | Real-time risk score for a ticker |
| GET | `/score/{ticker}/history` | Historical risk scores (JSONL log) |
| GET | `/health` | Health check |
| GET | `/metrics` | Prometheus-compatible metrics |

### Example Response

```json
{
  "ticker": "TSLA",
  "timestamp": "2026-06-11T10:30:00Z",
  "risk_score": 72.4,
  "risk_label": "HIGH",
  "risk_note": "Score reflects this stock's risk relative to its own historical distribution ...",
  "risk_breakdown": {
    "volatility": {"score": 81.2, "weight": 0.25, "metrics": {"vol_21d": 88.4, "vol_63d": 79.1, "downside_dev_63d": 76.0}},
    "tail": {"score": 74.5, "weight": 0.25, "metrics": {"cvar_95_21d": 80.2, "var_95_21d": 71.0, "skew_63d": 65.8, "kurt_63d": 79.3}},
    "drawdown": {"score": 69.8, "weight": 0.20, "metrics": {"max_drawdown_63d": 75.1, "drawdown": 63.4, "drawdown_duration": 60.2}},
    "sensitivity": {"score": 88.0, "weight": 0.15, "metrics": {"beta_63d": 88.0}},
    "liquidity": {"score": 45.3, "weight": 0.15, "metrics": {"amihud_illiq_21d": 40.1, "volume_vol_21d": 51.2, "dollar_volume_21d": 55.0}}
  },
  "ml_drawdown_probability": 66.1,
  "garch_volatility_forecast": {"vol_1d": 0.031, "vol_30d": 0.51},
  "volatility_30d": 0.48,
  "var_95": -0.034,
  "cvar_95": -0.052,
  "beta": 1.87,
  "max_drawdown_90d": -0.21,
  "implied_volatility": 0.62,
  "indicators": {
    "rsi_14": 68.2,
    "bb_pct": 0.82,
    "atr_14": 9.41
  },
  "fundamentals": {
    "sector": "Consumer Cyclical",
    "market_cap": 712000000000,
    "trailing_pe": 52.1
  }
}
```

## Streamlit Dashboard

Run `streamlit run ui/dashboard.py` (or `make dashboard`) and open `http://localhost:8501`.

Features:
- Risk gauge (0–100) with colour-coded label
- Key metric tiles: volatility, VaR, CVaR, max drawdown, beta, implied vol
- Interactive candlestick chart with Bollinger Bands and EMAs
- RSI panel with overbought/oversold lines
- Rolling volatility comparison (21d vs 63d)
- Rolling drawdown from peak
- Raw feature table and JSON scorecard expanders

## Deployment

```bash
# Docker (API only)
docker-compose up --build

# Run continuous monitoring loop
python scripts/monitor.py --tickers AAPL MSFT TSLA --interval 3600
# or: make monitor
```

## Risk Score Interpretation

| Score | Label | Description |
|-------|-------|-------------|
| 0–25 | LOW | Low downside risk, stable volatility |
| 26–50 | MODERATE | Some risk; standard diversification advised |
| 51–75 | HIGH | Elevated risk; reduce position sizing |
| 76–100 | EXTREME | High probability of significant drawdown |

## Project Structure

```
stock_risk/
├── src/stock_risk/
│   ├── data/          fetcher.py · preprocessor.py
│   ├── features/      technical.py · risk_metrics.py
│   ├── models/        base.py · volatility.py · downside_risk.py
│   ├── scoring/       scorer.py
│   ├── monitoring/    drift.py · metrics.py
│   ├── api/           app.py  (FastAPI)
│   └── config.py
├── ui/
│   └── dashboard.py   (Streamlit)
├── scripts/           train.py · score.py · monitor.py
├── tests/             test_data · test_features · test_models · test_api
├── configs/           model_config.yaml · monitoring_config.yaml
├── docker/            Dockerfile · docker-compose.yml
└── .github/workflows/ ci.yml · cd.yml
```

## Dependencies & Citations

- **yfinance** — Aroussi, R. (2019). *yfinance: Download market data from Yahoo Finance's API*. https://github.com/ranaroussi/yfinance
- **XGBoost** — Chen, T., & Guestrin, C. (2016). XGBoost: A scalable tree boosting system. *Proceedings of KDD 2016*, 785–794. https://doi.org/10.1145/2939672.2939785
- **scikit-learn** — Pedregosa et al. (2011). Scikit-learn: Machine Learning in Python. *JMLR*, 12, 2825–2830. https://jmlr.org/papers/v12/pedregosa11a.html
- **pandas-ta** — Twang (2021). *pandas_ta: A Technical Analysis Library in Python*. https://github.com/twopirllc/pandas-ta
- **arch** — Sheppard, K. (2023). *ARCH: Autoregressive Conditional Heteroskedasticity models in Python*. https://github.com/bashtage/arch
- **FastAPI** — Ramírez, S. (2021). *FastAPI*. https://fastapi.tiangolo.com
- **Streamlit** — Streamlit Inc. (2019–2026). *Streamlit: The fastest way to build data apps*. https://streamlit.io
- **Plotly** — Plotly Technologies Inc. (2015–2026). *Plotly Python graphing library*. https://plotly.com/python
- **Prometheus / prometheus-client** — Prometheus Authors (2012–2026). https://prometheus.io
- **Value at Risk methodology** — Jorion, P. (2006). *Value at Risk: The New Benchmark for Managing Financial Risk* (3rd ed.). McGraw-Hill.
- **GARCH models** — Bollerslev, T. (1986). Generalized autoregressive conditional heteroskedasticity. *Journal of Econometrics*, 31(3), 307–327. https://doi.org/10.1016/0304-4076(86)90063-1
