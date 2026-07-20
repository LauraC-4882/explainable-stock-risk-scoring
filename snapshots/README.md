Daily-refreshed OHLCV snapshots (parquet) used as the fetch fallback when
Yahoo throttles the egress IP. Written by MarketDataFetcher on successful
fetches and by .github/workflows/refresh-snapshot.yml on a weekday cron.
