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


settings = Settings()
