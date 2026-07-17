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
RiskMetrics               ← VaR, CVaR, Sharpe, Sortino, drawdown, EWMA vol, liquidity, beta,
       │                     vol_regime_change, vol_of_vol, drawdown_acceleration, skew_momentum
       ├──► risk_categories.py  (percentile composite, VIX-regime-weighted) ← primary risk_score
       ├──► XGBoost classifier, isotonic-calibrated  (P[drawdown ≤ -10% / 20d])
       │      + SHAP on the raw pre-calibration model  ← secondary ml_drawdown_probability
       └──► GARCH(1,1), fit live per ticker              ← secondary garch_volatility_forecast

yfinance news        ──► llm/news_risk.py (schema+prompt ready, Haiku 4.5; call mocked) ─ news_risk
yfinance analyst/insider ──────────────────────────────────────────────────────────────── alt_data
^VIX                 ──► risk_categories.regime_adjusted_weights ─────────────── market_regime
2008/2020/2022 scenarios ──► stress_test.py (percentile score only, beta-scaled shocks) ─ stress_test
                │
                ▼
          Risk Scorecard (0–100 + label + category breakdown)
                │
       ┌────────┬────────┐
       ▼        ▼        ▼
  FastAPI   React SPA   Streamlit
  REST API  ui/web/     Dashboard
  /api/*    (built,     ui/dashboard.py
            served at /)
```

## Components

| Module | Description |
|--------|-------------|
| `data/fetcher.py` | Fetches OHLCV, fundamentals, and options IV via **yfinance** |
| `data/preprocessor.py` | Business-day alignment, 6σ outlier removal, log/pct returns |
| `features/technical.py` | RSI, MACD, Bollinger Bands, ATR, OBV, EMA 20/50/200 via **pandas-ta** |
| `features/risk_metrics.py` | Rolling VaR, CVaR, Sharpe, Sortino, drawdown, skew, kurtosis, EWMA vol, liquidity, beta, + vol-regime/vol-of-vol/drawdown-acceleration/skew-momentum cross features |
| `scoring/risk_categories.py` | Percentile-based composite score across 5 risk categories, VIX-threshold regime-weighted (explainable baseline) |
| `scoring/stress_test.py` | Historical-scenario (2008/2020/2022) stress test on the percentile composite, beta-scaled shocks |
| `models/volatility.py` | GARCH(1,1) volatility forecasting via **arch** |
| `models/downside_risk.py` | **XGBoost** classifier (P[max drawdown ≤ -10% in 20d]) inside **sklearn ColumnTransformer** pipeline, isotonic-calibrated for production via `fit_calibrated` |
| `models/evaluation.py` | Chronological Logistic Regression / Random Forest / XGBoost comparison, plus a per-ticker `TimeSeriesSplit` walk-forward backtest with calibration (Precision/Recall/F1/ROC-AUC/PR-AUC/Brier score per fold) |
| `models/explain.py` | **SHAP** attribution for the XGBoost classifier — which features drove `ml_drawdown_probability` |
| `llm/news_risk.py` | News event extraction schema + prompt (Claude structured outputs) — extraction call is mocked until wired |
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

# 6. Build the React web frontend (one-time / after any ui/web change)
cd ui/web && npm install && npm run build && cd ../..

# 7. Start the REST API — serves the built React app at http://localhost:8000/
uvicorn src.stock_risk.api.app:app --reload
# or:  make api

# For frontend development with hot reload instead of rebuilding on every change:
cd ui/web && npm run dev   # proxies /api, /health, /metrics to :8000 — run the API too
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

`ml_drawdown_probability` is otherwise a black box, so `models/explain.py` attaches a **SHAP** (`TreeExplainer`) attribution alongside it as `ml_drawdown_explanation` — the top features pushing that probability up or down, in log-odds units (additive: `base_probability`'s log-odds + every feature's `shap_contribution` = `predicted_probability`'s log-odds). `None` when the model is in fallback mode. Requires `xgboost<3.0` — `shap` 0.49.1 can't parse XGBoost 3.x's `base_score` serialization format.

Feature importances are accessible via `model.feature_importance()`. `scripts/train.py` also runs `models/evaluation.py::compare_classifiers`, which benchmarks Logistic Regression / Random Forest / XGBoost on a chronological (never random) train/test split and reports Precision/Recall/F1/ROC-AUC/PR-AUC/confusion-matrix — accuracy alone is misleading here since drawdown events are a rare minority class.

### Walk-forward backtest + probability calibration

A single train/test split can look fine by luck of where the cut falls. `models/evaluation.py::walk_forward_evaluate` instead runs a per-ticker `TimeSeriesSplit` (with a `gap` between train/test so the forward-looking label window can never leak across the boundary), pooling each fold across tickers, and reports one row per fold plus a mean/std summary — so a caller can see whether e.g. recall holds up or degrades in a specific period instead of only the average:

```python
from stock_risk.models.evaluation import walk_forward_evaluate

result = walk_forward_evaluate(per_ticker_dfs, n_splits=5, gap=20)
#       precision  recall    f1  roc_auc  pr_auc  brier_raw  brier_calibrated
# fold
# 1          0.61    0.68  0.64     0.71    0.55       0.14              0.11
# 2          0.58    0.72  0.64     0.74    0.58       0.15              0.12
# ...
```

An uncalibrated XGBoost probability isn't trustworthy at face value — "P=0.7" should mean the event actually happens in ~70% of such cases, which the training objective doesn't guarantee. Each fold's classifier is isotonic-calibrated (`sklearn.calibration.CalibratedClassifierCV`) on a **chronological** held-out slice — the last 20% of the training rows, strictly after what the model fit on and strictly before the test fold — never a random split, which would leak future rows into "calibration" the same way a random train/test split leaks them into training. `brier_raw` vs `brier_calibrated` makes "does calibration actually help" a number instead of an assumption.

The production model uses the same calibration path: `scripts/train.py` calls `DownsideRiskModel.fit_calibrated(...)` (not the plain `fit`/`fit_dataset`), so `ml_drawdown_probability` in the API response is the calibrated estimate. Because isotonic calibration is a post-hoc, non-smooth remap with no SHAP decomposition of its own, `models/explain.py`'s SHAP breakdown still explains the *raw* pre-calibration model — `ml_drawdown_explanation.predicted_probability` (raw) and `.calibrated_probability` (what's actually served) are both reported when a model is calibrated, so the two never get silently conflated.

## Historical-Scenario Stress Testing

`scoring/stress_test.py` answers "if 2008/2020/2022 conditions recurred, where would this stock's risk score land?" — scoped deliberately to `risk_categories.py`'s percentile composite only, **not** the XGBoost leg. XGBoost's momentum features (RSI, Bollinger %B, distance-from-moving-average) have no defensible "shock" mapping — there's no established rule for "VIX→80 means RSI→X" — and inventing one would undermine the credibility a stress test is supposed to add.

Three built-in scenarios carry real, approximate historical magnitudes (S&P 500 peak-to-trough drawdown, a realized/implied-vol multiplier) sourced from public market history:

| Scenario | Market drawdown | Vol multiplier |
|---|---|---|
| `2008_financial_crisis` | −50% | 3.5× |
| `2020_covid_crash` | −34% | 4.0× |
| `2022_rate_hike_selloff` | −25% | 1.8× |

Each metric is shocked with an actual rationale, not a guess: volatility/VaR/CVaR/kurtosis scale multiplicatively with the vol multiplier (they move roughly linearly with the vol regime); drawdown gets a **CAPM-style beta-scaled shock** (`beta × market_drawdown` — a low-beta utility and a high-beta growth stock don't fall the same amount under the same market move); liquidity metrics scale by a liquidity multiplier; **beta itself is left unchanged** (it measures sensitivity — a scenario doesn't shock the thing that determines its own propagation). Shocked values are ranked against the stock's own real historical distribution using the *same* percentile machinery the live score uses (`risk_categories.composite_score(df, latest=shocked_row)`), not a separately fit model.

```python
from stock_risk.scoring.stress_test import run_stress_test

result = run_stress_test(df, beta=1.8)
result["scenarios"]["2020_covid_crash"]["narrative"]
# "If 2020 COVID-19 Crash conditions recurred, this stock's risk score would move from 67.1 to 92.9 (+25.8)."
```

Baseline and stressed scores within one scenario always use the *same* category weights (that scenario's regime-implied weights), so the reported `delta` reflects only the shock — comparing against a differently-weighted live score would silently mix in a regime-reweighting effect. This also makes `stressed_score >= baseline_score` a mathematical guarantee per scenario, not an empirical tendency. Known limitation: once a shocked value already exceeds the stock's *entire* historical range, its percentile saturates near 100 regardless of how much further it's pushed — so a more severe scenario (2008) is not guaranteed to score strictly higher than a milder one (2022) for the same stock; both can saturate at the same ceiling. This is an inherent property of percentile-based scoring, not a bug — the underlying shocked values themselves remain correctly ordered by severity.

## News / Event Risk Layer (schema ready, LLM call mocked)

`data/fetcher.py::fetch_news` pulls real recent headlines per ticker via yfinance's built-in news (no extra API key). Each headline is run through `llm/news_risk.py::extract_news_risk`, which classifies it into a fixed taxonomy (`event_type`, `risk_category`, `sentiment`, `severity` 0–5, `time_horizon`, `confidence`, `evidence`) using Claude's structured-outputs contract (`output_config.format` + a JSON schema) — the LLM never computes a risk score itself, only extracts structured fields from a single headline.

**The actual Claude API call is not wired in yet** — `extract_news_risk()` returns a clearly-labeled stub (`"source": "mock"`, `severity: 0`) so the fetch → extract → aggregate pipeline runs end-to-end without spending API credits. The `news_risk.llm_configured` field in the API response is `false` until this is activated. To activate: `pip install anthropic`, set `ANTHROPIC_API_KEY`, and pass `llm.news_risk.call_claude_news_extractor` as the `call_llm` argument wherever `extract_news_risk()` is called in `scoring/scorer.py`.

Model: **Claude Haiku 4.5**, not the usual Opus default — this is a high-volume, low-stakes classification task with output already constrained by the schema, so Opus's extra reasoning isn't load-bearing and Haiku is ~5x cheaper per token. Determinism comes from the fixed JSON schema, not a `temperature` parameter (current Claude models don't accept one).

### Free alt-data (analyst ratings, insider transactions, VIX regime)

No paid data vendor required — all via yfinance:

- `fetch_analyst_activity` / `fetch_insider_activity` — recent analyst downgrade/upgrade counts and insider sale/purchase counts, surfaced as `alt_data` in the API response. Informational only for now (not folded into `risk_score`'s calibrated weights).
- `fetch_vix` + `risk_categories.regime_adjusted_weights` — a rule-based (not HMM) regime switch: VIX ≥ 30 ("panic") shifts weight from day-to-day volatility toward tail risk (25/25/20/15/15 → 20/40/15/10/15); VIX ≥ 20 ("elevated") shifts partway there; below 20 ("calm") uses the base weights. Surfaced as `market_regime` in the API response.

## FastAPI Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/score/{ticker}` | Real-time risk score for a ticker |
| GET | `/score/{ticker}/history` | Historical risk scores (JSONL log) |
| GET | `/health` | Health check |
| GET | `/metrics` | Prometheus-compatible metrics |
| POST | `/api/auth/register` | Create an account, returns a JWT |
| POST | `/api/auth/login` | Returns a JWT for an existing account |
| GET | `/api/auth/me` | Current user (requires `Authorization: Bearer <token>`) |
| GET | `/api/watchlist` | Current user's saved tickers |
| POST | `/api/watchlist` | Save a ticker (`{ticker, market, notes?}`) |
| DELETE | `/api/watchlist/{item_id}` | Remove a saved ticker |

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
  "market_regime": {"vix": 22.4, "regime": "elevated"},
  "ml_drawdown_probability": 66.1,
  "ml_drawdown_explanation": {
    "base_probability": 0.08,
    "predicted_probability": 0.601,
    "calibrated_probability": 0.661,
    "top_features": [
      {"feature": "volatility__vol_21d", "raw_value": 0.62, "shap_contribution": 1.42},
      {"feature": "volatility__max_drawdown_63d", "raw_value": -0.24, "shap_contribution": 0.87},
      {"feature": "momentum__rsi_14", "raw_value": 71.2, "shap_contribution": 0.31}
    ],
    "note": "shap_contribution is in log-odds units ... predicted_probability is the raw (pre-calibration) model's output that this SHAP breakdown explains — calibrated_probability is what model.predict() actually serves ..."
  },
  "garch_volatility_forecast": {"vol_1d": 0.031, "vol_30d": 0.51},
  "news_risk": {
    "llm_configured": false,
    "max_severity": 0,
    "negative_count": 0,
    "articles": [
      {"event_type": "none", "risk_category": "none", "sentiment": "neutral", "severity": 0,
       "time_horizon": "unknown", "confidence": 0.0, "evidence": [], "title": "...", "source": "mock"}
    ]
  },
  "alt_data": {
    "analyst_activity": {"downgrade_count": 2, "upgrade_count": 0},
    "insider_activity": {"sale_count": 3, "purchase_count": 0, "net_transaction_count": -3}
  },
  "stress_test": {
    "live_score": 72.4,
    "scenarios": {
      "2008_financial_crisis": {
        "label": "2008 Global Financial Crisis", "baseline_score": 67.1, "stressed_score": 92.9,
        "delta": 25.8, "narrative": "If 2008 Global Financial Crisis conditions recurred, this stock's risk score would move from 67.1 to 92.9 (+25.8).",
        "stressed_categories": { "...": "..." }
      },
      "2020_covid_crash": { "...": "..." },
      "2022_rate_hike_selloff": { "...": "..." }
    }
  },
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

## Web Frontend (React + Tailwind)

`ui/web/` is a Vite + React 18 + Tailwind CSS single-page app (multi-ticker search, side-by-side risk cards, SVG gauge, Chart.js price/risk charts) served by FastAPI at `/` once built — see step 6 in Quick Start. Source lives in `ui/web/src/`; `npm run build` outputs to `ui/web/dist/`, which `api/app.py` mounts at `/assets` and serves `index.html` from at `/`. If `dist/` hasn't been built yet, `/` returns a 503 with instructions rather than a confusing 404.

- `src/App.jsx` — top-level state (ticker list, selected timeframe, market)
- `src/components/StockCard.jsx` — per-ticker fetch + render (score, gauge, direction signal, metric tiles, charts, favorite star)
- `src/api.js` — thin fetch wrappers over `/api/search`, `/api/score/{ticker}`, `/api/score/{ticker}/timeseries`, `/api/auth/*`, `/api/watchlist`
- `src/i18n/` — English/Simplified Chinese locale files + a lightweight Context-based translator (no external i18n library, given the app's size)
- `src/auth/` — `AuthContext` (JWT stored in `localStorage`, session restored on load via `/api/auth/me`), `AuthModal`, `WatchlistPanel`

### Accounts & watchlist

Auth is self-hosted (FastAPI + SQLite + JWT), not a third-party service — no external account is needed to run the app. Passwords are hashed with bcrypt; tokens are bearer JWTs valid for 7 days. Set `JWT_SECRET_KEY` in `.env` before deploying with real users — the app runs fine without it for local dev but logs a startup warning, since the fallback is a published placeholder value.
- `tailwind.config.js` — theme colors matched to the original dark palette (risk label colors, accent gradient)

Verified end-to-end with a headless-Chromium (Playwright) smoke test: multi-card grid, live search with debounce, Enter-to-add, timeframe switching, zero console errors, real yfinance data rendering in both the SVG gauge and Chart.js line charts.

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
│   ├── dashboard.py   (Streamlit)
│   └── web/           React + Vite + Tailwind SPA (src/, package.json, dist/ after build)
├── scripts/           train.py · score.py · monitor.py
├── tests/             test_data · test_features · test_llm · test_models ·
│                       test_explain · test_risk_categories · test_scorer · test_api
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
