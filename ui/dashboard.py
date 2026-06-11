"""Streamlit dashboard for the Stock Risk Scoring System."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from stock_risk.data.fetcher import MarketDataFetcher
from stock_risk.data.preprocessor import DataPreprocessor
from stock_risk.features.technical import TechnicalFeatures
from stock_risk.features.risk_metrics import RiskMetrics
from stock_risk.scoring.scorer import RiskScorer

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Stock Risk Scorer",
    page_icon="📉",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar controls ─────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Stock Risk Scorer")
    st.caption("Powered by yfinance + XGBoost")

    ticker = st.text_input("Ticker symbol", value="AAPL").upper().strip()
    period = st.selectbox("History window", ["6mo", "1y", "2y", "5y"], index=2)
    run = st.button("Score", use_container_width=True, type="primary")

    st.divider()
    st.markdown("**Risk scale**")
    st.markdown(
        "🟢 **LOW** 0–25  \n🟡 **MODERATE** 26–50  \n🟠 **HIGH** 51–75  \n🔴 **EXTREME** 76–100"
    )


# ── Helpers ──────────────────────────────────────────────────────────────────
LABEL_COLORS = {"LOW": "green", "MODERATE": "gold", "HIGH": "orange", "EXTREME": "red"}
LABEL_EMOJI = {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🟠", "EXTREME": "🔴"}


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_and_engineer(ticker: str, period: str) -> pd.DataFrame:
    fetcher = MarketDataFetcher()
    preprocessor = DataPreprocessor()
    tech = TechnicalFeatures()
    risk = RiskMetrics()
    raw = fetcher.fetch_history(ticker, period=period)
    df = preprocessor.process(raw)
    df = tech.compute(df)
    df = risk.compute(df)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def _score(ticker: str, period: str) -> dict:
    return RiskScorer().score(ticker, period=period)


def _gauge(score: float, label: str) -> go.Figure:
    color = LABEL_COLORS.get(label, "gray")
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={"suffix": "", "font": {"size": 48}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1},
            "bar": {"color": color},
            "steps": [
                {"range": [0, 25], "color": "#d4edda"},
                {"range": [25, 50], "color": "#fff3cd"},
                {"range": [50, 75], "color": "#ffe5b4"},
                {"range": [75, 100], "color": "#f8d7da"},
            ],
            "threshold": {"line": {"color": color, "width": 4}, "value": score},
        },
    ))
    fig.update_layout(height=260, margin=dict(l=20, r=20, t=30, b=10))
    return fig


def _candlestick(df: pd.DataFrame, ticker: str) -> go.Figure:
    fig = go.Figure(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name=ticker,
    ))
    # Bollinger Bands
    if "BBU_20_2.0" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["BBU_20_2.0"], line=dict(color="lightblue", width=1), name="BB Upper"))
        fig.add_trace(go.Scatter(x=df.index, y=df["BBL_20_2.0"], line=dict(color="lightblue", width=1), fill="tonexty", fillcolor="rgba(173,216,230,0.15)", name="BB Lower"))
    if "ema_20" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["ema_20"], line=dict(color="orange", width=1.5), name="EMA 20"))
    if "ema_50" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["ema_50"], line=dict(color="purple", width=1.5), name="EMA 50"))
    fig.update_layout(
        title=f"{ticker} Price + Bollinger Bands",
        xaxis_rangeslider_visible=False,
        height=420,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    return fig


def _rsi_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["rsi_14"], line=dict(color="#5b9bd5"), name="RSI 14"))
    fig.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Overbought 70")
    fig.add_hline(y=30, line_dash="dash", line_color="green", annotation_text="Oversold 30")
    fig.update_layout(title="RSI (14)", yaxis=dict(range=[0, 100]), height=200, margin=dict(l=10, r=10, t=40, b=10))
    return fig


def _vol_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if "vol_21d" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["vol_21d"], name="21d Vol", line=dict(color="coral")))
    if "vol_63d" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["vol_63d"], name="63d Vol", line=dict(color="steelblue")))
    fig.update_layout(title="Annualised Volatility", yaxis_tickformat=".0%", height=200, margin=dict(l=10, r=10, t=40, b=10))
    return fig


def _drawdown_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Scatter(
        x=df.index, y=df["drawdown"], fill="tozeroy",
        fillcolor="rgba(255,80,80,0.25)", line=dict(color="red"), name="Drawdown",
    ))
    fig.update_layout(title="Rolling Drawdown from Peak", yaxis_tickformat=".0%", height=200, margin=dict(l=10, r=10, t=40, b=10))
    return fig


# ── Main ─────────────────────────────────────────────────────────────────────
st.title("📉 Stock Risk Scoring Dashboard")

if not run and "last_ticker" not in st.session_state:
    st.info("Enter a ticker in the sidebar and click **Score** to begin.")
    st.stop()

if run:
    st.session_state["last_ticker"] = ticker
    st.session_state["last_period"] = period
else:
    ticker = st.session_state["last_ticker"]
    period = st.session_state["last_period"]

with st.spinner(f"Fetching and scoring {ticker} …"):
    try:
        scorecard = _score(ticker, period)
        df = _fetch_and_engineer(ticker, period)
    except Exception as exc:
        st.error(f"Could not score **{ticker}**: {exc}")
        st.stop()

score = scorecard["risk_score"]
label = scorecard["risk_label"]
emoji = LABEL_EMOJI.get(label, "")

# ── Row 1: gauge + key metrics ────────────────────────────────────────────────
col_gauge, col_metrics = st.columns([1, 2])

with col_gauge:
    st.subheader(f"{emoji} {label}")
    st.plotly_chart(_gauge(score, label), use_container_width=True)

with col_metrics:
    st.subheader("Key Risk Metrics")
    m1, m2, m3 = st.columns(3)
    m1.metric("Risk Score", f"{score:.1f} / 100")
    m2.metric("30d Volatility", f"{scorecard.get('volatility_30d', 0):.1%}")
    m3.metric("VaR 95% (21d)", f"{scorecard.get('var_95', 0):.2%}")

    m4, m5, m6 = st.columns(3)
    m4.metric("CVaR 95% (21d)", f"{scorecard.get('cvar_95', 0):.2%}")
    m5.metric("Max Drawdown 63d", f"{scorecard.get('max_drawdown_90d', 0):.2%}")
    beta = scorecard.get("beta")
    m6.metric("Beta", f"{beta:.2f}" if beta else "N/A")

    iv = scorecard.get("implied_volatility")
    ind = scorecard.get("indicators", {})
    m7, m8, m9 = st.columns(3)
    m7.metric("RSI (14)", f"{ind.get('rsi_14', 0):.1f}")
    m8.metric("BB Position", f"{ind.get('bb_pct', 0):.2%}")
    m9.metric("Implied Vol", f"{iv:.2%}" if iv else "N/A")

st.divider()

# ── Row 2: price chart ────────────────────────────────────────────────────────
st.plotly_chart(_candlestick(df, ticker), use_container_width=True)

# ── Row 3: indicator charts ───────────────────────────────────────────────────
col_rsi, col_vol = st.columns(2)
with col_rsi:
    st.plotly_chart(_rsi_chart(df), use_container_width=True)
with col_vol:
    st.plotly_chart(_vol_chart(df), use_container_width=True)

st.plotly_chart(_drawdown_chart(df), use_container_width=True)

# ── Row 4: fundamentals + raw data ───────────────────────────────────────────
with st.expander("Fundamentals"):
    fund = scorecard.get("fundamentals", {})
    st.json(fund)

with st.expander("Raw scorecard JSON"):
    st.json(scorecard)

with st.expander("Feature data (last 20 rows)"):
    display_cols = [c for c in df.columns if c in [
        "close", "rsi_14", "vol_21d", "vol_63d", "var_95_21d",
        "cvar_95_21d", "max_drawdown_63d", "bb_pct", "sharpe_63d",
    ]]
    st.dataframe(df[display_cols].tail(20).style.format("{:.4f}"), use_container_width=True)

st.caption(
    "Data via [yfinance](https://github.com/ranaroussi/yfinance) · "
    "Risk model: XGBoost + sklearn ColumnTransformer · "
    "Indicators: pandas-ta"
)
