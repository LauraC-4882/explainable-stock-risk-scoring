from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    yfinance_timeout: int = 30
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    model_dir: Path = Path("models/artefacts")
    monitoring_log_dir: Path = Path("logs/monitoring")
    mlflow_tracking_uri: str = "http://localhost:5000"

    # Risk score thresholds
    risk_low_max: float = 25.0
    risk_moderate_max: float = 50.0
    risk_high_max: float = 75.0

    def model_post_init(self, __context):
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.monitoring_log_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
