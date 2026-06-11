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
