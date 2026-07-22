from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    yfinance_timeout: int = 30
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # [F2]: ENABLE_ML=0 on memory-constrained deploys (Render's 512MB free
    # tier) skips loading DownsideRiskModel entirely, so xgboost/shap never
    # enter sys.modules — see RiskScorer._try_load_downside_model.
    enable_ml: bool = True
    # Fusion share of the ML drawdown leg in risk_score (percentile composite
    # gets 1 - this). Opened at 0.15 after the [A1]/[A2] validations landed —
    # see producers/base.py and README "Architecture" for the rationale and
    # the unit caveat. Set ML_FUSION_WEIGHT=0 to reproduce the pure-percentile
    # score.
    ml_fusion_weight: float = 0.15
    model_dir: Path = Path("models/artefacts")
    # [IP-block resilience] On a successful fetch_history, the OHLCV frame is
    # persisted here; when Yahoo throttles the egress IP (chronic on shared
    # datacenter IPs — see README "Deployment"), the fetcher serves the last
    # snapshot instead of failing the request. The tracked snapshots/ dir is
    # refreshed daily by .github/workflows/refresh-snapshot.yml so free-tier
    # deploys ship with recent data baked in.
    snapshot_dir: Path = Path("snapshots")
    monitoring_log_dir: Path = Path("logs/monitoring")

    # Risk score thresholds
    risk_low_max: float = 25.0
    risk_moderate_max: float = 50.0
    risk_high_max: float = 75.0

    # Auth / persistence — SQLite by default so the app stays a single
    # deployable unit with no external account/service required. Set
    # DATABASE_URL (any SQLAlchemy URL, e.g. postgresql+psycopg2://...) to
    # point at a durable external database instead — needed on any host
    # whose local filesystem doesn't survive a restart/redeploy, since that
    # silently wipes every registered account. See db.py.
    db_path: Path = Path("data/app.db")
    database_url: str | None = None
    # Verified pre-migration and scheduled backups land here (see backup.py).
    # Kept outside db_path's directory so a "wipe the data dir" recovery step
    # doesn't take the backups with it.
    backup_dir: Path = Path("backups")
    # How many backups to keep when pruning. 10 covers the daily schedule plus
    # several pre-migration snapshots without unbounded growth on a small disk.
    backup_retention: int = 10
    jwt_secret_key: str = "dev-insecure-secret-change-me-before-deploying"

    # Site-owner admin account, re-created/promoted idempotently on every
    # boot (see auth/admin.py:ensure_admin_user) rather than seeded once —
    # a one-off seed would vanish along with data/app.db on the next
    # redeploy, same limitation as jwt_secret_key's insecure default above.
    # Unset: no admin account exists, admin features are simply
    # unavailable, same "log a warning, don't crash" treatment as an unset
    # JWT_SECRET_KEY.
    admin_email: str | None = None
    admin_password: str | None = None

    # ── [R2] API hardening ───────────────────────────────────────────────────
    # CORS. Default is the local dev origins only — NOT "*". The previous
    # wildcard was unsafe next to JWT auth: any site a signed-in user visited
    # could call this API and read the response. Set CORS_ALLOWED_ORIGINS to a
    # comma-separated list for a real deployment.
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Behind a reverse proxy (Render, any CDN) the client IP is in
    # X-Forwarded-For. Off by default because trusting that header on a
    # directly-exposed server lets a caller forge a fresh identity per request
    # and bypass IP rate limiting entirely.
    trust_proxy_headers: bool = False
    # Send HSTS (HTTPS responses only). Off by default so a local dev server
    # can't pin localhost to HTTPS in a developer's browser.
    enable_hsts: bool = False

    # Token bucket: sustained requests/second and burst capacity, per client
    # (authenticated user, else IP). Costs are per-endpoint — see api/app.py's
    # _ENDPOINT_COSTS.
    #
    # Burst is sized against a real page load, not guessed. Opening the app with
    # five watchlisted stocks issues roughly 5 x (score + timeseries + outcomes
    # + community posts) plus panel traffic — around 35-40 tokens in a couple of
    # seconds, and a user browsing several tickers doubles that. The first
    # values tried here (5/s, burst 40) made exactly that legitimate flow 429:
    # scripts/ui_shot.sh's admin walkthrough failed with a KeyError because the
    # API returned `{"detail": "Rate limit exceeded"}` where it expected data.
    # A limiter that fires on normal use gets switched off, so it has to clear
    # real usage by a wide margin and still stop a loop.
    rate_limit_per_second: float = 10.0
    rate_limit_burst: float = 120.0
    # Authenticated users get a larger allowance: they're identifiable, and
    # abuse is attributable to an account that can be banned.
    rate_limit_user_per_second: float = 20.0
    rate_limit_user_burst: float = 240.0
    rate_limit_enabled: bool = True

    # Failed-login lockout, keyed by email (see FailedLoginTracker).
    login_failure_threshold: int = 5
    login_lockout_seconds: float = 900.0

    # Score cache. fresh_ttl is deliberately minutes, not seconds: the score is
    # computed from daily bars, so a 5-minute-old answer is the same answer.
    # stale_ttl bounds how long a value may be served after an upstream failure.
    score_cache_fresh_seconds: float = 300.0
    score_cache_stale_seconds: float = 3600.0

    # JWT lifetime. Shortened from the original 7 days: a leaked token was
    # valid for a week with no way to revoke it short of rotating the signing
    # key and logging everyone out. Refresh happens transparently — see
    # auth/security.py:should_refresh.
    access_token_expire_minutes: int = 60 * 12  # 12 hours
    # Re-issue a token when it's within this long of expiring, so an active
    # session never gets logged out mid-use by the shorter lifetime above.
    access_token_refresh_within_minutes: int = 60 * 2

    @property
    def cors_origins_list(self) -> list[str]:
        """Parsed allowlist. Empty entries dropped so a trailing comma in the
        env var can't become an empty-string origin that matches nothing but
        looks configured."""
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    # [Data-source migration] Yahoo throttles shared datacenter IPs for
    # extended windows (see README "Deployment") — Twelve Data is a real
    # commercial API built for exactly this traffic pattern, unlike
    # yfinance's scrape of Yahoo's unofficial endpoint. Unset, US equities
    # fall back to yfinance (unchanged local-dev/CI behavior); set
    # TWELVE_DATA_KEY to route US history through Twelve Data instead. Free
    # plan is US-only (no HK, no options) — CN/HK already route through
    # akshare (free, no key) regardless of this setting; see fetcher.py.
    twelve_data_key: str | None = None

    def model_post_init(self, __context):
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.monitoring_log_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
