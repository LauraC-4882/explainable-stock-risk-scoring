"""Live market data fetcher using yfinance."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf
from loguru import logger


class MarketDataFetcher:
    """Fetches OHLCV price history, fundamentals, and options data from Yahoo Finance."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def fetch_history(
        self,
        ticker: str,
        period: str = "2y",
        interval: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """Return daily OHLCV DataFrame for *ticker*.

        Args:
            ticker: Stock symbol, e.g. "AAPL".
            period: yfinance period string used when start/end are not given.
            interval: Bar interval ("1d", "1h", …).
            start: ISO date string override.
            end: ISO date string override.
        """
        logger.info(f"Fetching history for {ticker} | period={period} interval={interval}")
        tk = yf.Ticker(ticker)
        if start or end:
            df = tk.history(start=start, end=end, interval=interval, auto_adjust=True)
        else:
            df = tk.history(period=period, interval=interval, auto_adjust=True)

        if df.empty:
            raise ValueError(f"No data returned for ticker '{ticker}'")

        df.index = pd.to_datetime(df.index, utc=True).tz_convert(None)
        df.index.name = "date"
        df.columns = [c.lower() for c in df.columns]
        return df[["open", "high", "low", "close", "volume"]]

    def fetch_info(self, ticker: str) -> dict:
        """Return key fundamentals/metadata for *ticker*."""
        logger.info(f"Fetching info for {ticker}")
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        keys = [
            "shortName", "sector", "industry", "marketCap", "beta",
            "trailingPE", "forwardPE", "dividendYield", "52WeekChange",
            "sharesOutstanding", "floatShares",
        ]
        return {k: info.get(k) for k in keys}

    def fetch_news(self, ticker: str, limit: int = 8) -> list[dict]:
        """Return recent news headlines for *ticker* via yfinance (no API key required)."""
        logger.info(f"Fetching news for {ticker}")
        try:
            tk = yf.Ticker(ticker)
            items = tk.news or []
        except Exception as exc:
            logger.warning(f"Could not fetch news for {ticker}: {exc}")
            return []

        articles = []
        for item in items[:limit]:
            content = item.get("content", item)  # yfinance nests fields under "content"
            title = content.get("title")
            if not title:
                continue
            articles.append({
                "title": title,
                "summary": content.get("summary") or content.get("description") or "",
                "publisher": (content.get("provider") or {}).get("displayName")
                    if isinstance(content.get("provider"), dict) else content.get("publisher"),
                "published_at": content.get("pubDate") or content.get("providerPublishTime"),
                "link": (content.get("canonicalUrl") or {}).get("url")
                    if isinstance(content.get("canonicalUrl"), dict) else content.get("link"),
            })
        return articles

    def fetch_analyst_activity(self, ticker: str, lookback_days: int = 90) -> dict:
        """Recent analyst rating-change counts via yfinance (no extra API key).

        Downgrades are a forward-looking risk signal — analysts often move
        ahead of a drawdown, not just react to one.
        """
        logger.info(f"Fetching analyst activity for {ticker}")
        empty = {"downgrade_count": 0, "upgrade_count": 0}
        try:
            df = yf.Ticker(ticker).upgrades_downgrades
        except Exception as exc:
            logger.warning(f"Could not fetch analyst activity for {ticker}: {exc}")
            return empty

        if df is None or df.empty:
            return empty

        df = df.reset_index()
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        if date_col is not None:
            try:
                dates = pd.to_datetime(df[date_col], utc=True).dt.tz_localize(None)
                cutoff = pd.Timestamp.now() - pd.Timedelta(days=lookback_days)
                df = df[dates >= cutoff]
            except Exception:
                df = df.head(20)  # date parsing failed — fall back to "most recent N rows"
        else:
            df = df.head(20)

        action_col = next((c for c in df.columns if c.lower() == "action"), None)
        if action_col is None:
            return empty

        actions = df[action_col].astype(str).str.lower()
        return {
            "downgrade_count": int(actions.eq("downgrade").sum()),
            "upgrade_count": int(actions.eq("upgrade").sum()),
        }

    def fetch_insider_activity(self, ticker: str) -> dict:
        """Recent insider transaction summary via yfinance (no extra API key)."""
        logger.info(f"Fetching insider activity for {ticker}")
        empty = {"sale_count": 0, "purchase_count": 0, "net_transaction_count": 0}
        try:
            df = yf.Ticker(ticker).insider_transactions
        except Exception as exc:
            logger.warning(f"Could not fetch insider transactions for {ticker}: {exc}")
            return empty

        if df is None or df.empty or "Transaction" not in df.columns:
            return empty

        transaction = df["Transaction"].astype(str).str.lower()
        sale_count = int(transaction.str.contains("sale").sum())
        purchase_count = int(transaction.str.contains("purchase").sum())
        return {
            "sale_count": sale_count,
            "purchase_count": purchase_count,
            "net_transaction_count": purchase_count - sale_count,
        }

    def fetch_vix(self) -> Optional[float]:
        """Return the latest CBOE VIX index level, or None on failure."""
        try:
            return float(yf.Ticker("^VIX").fast_info.last_price)
        except Exception as exc:
            logger.warning(f"Could not fetch VIX: {exc}")
            return None

    def fetch_options_iv(self, ticker: str) -> Optional[float]:
        """Return the nearest-expiry at-the-money implied volatility, or None."""
        try:
            tk = yf.Ticker(ticker)
            expirations = tk.options
            if not expirations:
                return None
            chain = tk.option_chain(expirations[0])
            spot = tk.fast_info.last_price
            calls = chain.calls
            atm = calls.iloc[(calls["strike"] - spot).abs().argsort().iloc[0]]
            return float(atm.get("impliedVolatility", float("nan")))
        except Exception as exc:
            logger.warning(f"Could not fetch options IV for {ticker}: {exc}")
            return None
