"""Abstract base class for all risk models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import joblib
import pandas as pd
from loguru import logger


class BaseRiskModel(ABC):
    """Common interface: fit / predict / save / load."""

    model_name: str = "base"

    @abstractmethod
    def fit(self, df: pd.DataFrame) -> "BaseRiskModel":
        ...

    @abstractmethod
    def predict(self, df: pd.DataFrame) -> pd.Series:
        ...

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.model_name}.joblib"
        joblib.dump(self, path)
        logger.info(f"Saved {self.model_name} to {path}")
        return path

    @classmethod
    def load(cls, directory: Path) -> "BaseRiskModel":
        path = directory / f"{cls.model_name}.joblib"
        model = joblib.load(path)
        logger.info(f"Loaded {cls.model_name} from {path}")
        return model
