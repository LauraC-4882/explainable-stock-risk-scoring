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
    # deployable unit with no external account/service required.
    db_path: Path = Path("data/app.db")
    jwt_secret_key: str = "dev-insecure-secret-change-me-before-deploying"

    def model_post_init(self, __context):
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.monitoring_log_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
