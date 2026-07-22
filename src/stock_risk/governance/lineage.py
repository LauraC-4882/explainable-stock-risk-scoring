"""[R5] Dataset and code lineage: what exactly produced this model?

Every trained model here answers to a set of questions that were previously
unanswerable after the fact:

* Which data was it trained on, and has that data changed since?
* Which features, at which version of their definitions?
* Which commit of this repository computed them?
* Which tickers were in the universe, and which were dropped, and why?
* Why does today's run differ from yesterday's?

The last one is the reason this exists. `yfinance` returns *today's* view of
history: prices get restated for splits and dividends, a delisted ticker stops
resolving, a vendor backfills a gap. Retraining on "the same" 5-year window a
month later can legitimately produce a different model, and without a recorded
fingerprint of the input there is no way to tell that apart from a code change
or a bug.

The dataset hash is the load-bearing piece. It hashes the actual feature values
that entered training — not a filename, not a row count, both of which stay
identical while the numbers underneath shift.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger

# Bump when the *meaning* of a feature changes — a different window, a
# corrected formula, a new normalisation. Two models trained on the same raw
# dates but different feature versions are not comparable, and nothing else in
# the manifest would reveal that: the dataset hash changes, but it changes for
# data reasons too, so it can't distinguish "the data moved" from "we redefined
# the feature".
FEATURE_SCHEMA_VERSION = "1.0.0"


def git_commit() -> Optional[str]:
    """Current HEAD, or None outside a git checkout (e.g. a Docker image).

    None rather than a placeholder string: "unknown" in a lineage field reads
    like a recorded fact, whereas a null is unambiguously missing.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


def git_is_dirty() -> Optional[bool]:
    """Whether the working tree has uncommitted changes.

    A model trained from a dirty tree is NOT reproducible from its commit hash,
    which is exactly the situation a reproducibility manifest exists to expose
    rather than paper over.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return bool(result.stdout.strip())
    except Exception:
        return None


def dataset_hash(df: pd.DataFrame, columns: Optional[list[str]] = None) -> str:
    """Content hash of the feature matrix that actually entered training.

    Hashes VALUES, not a path or a shape. A file name is stable while its
    contents are restated; a row count is stable while every price in it moves
    after a split adjustment. Only a content hash distinguishes "the same data"
    from "the same amount of different data".

    Columns are sorted so column *order* — an implementation detail of however
    the frame was assembled — doesn't change the hash. Floats are rounded to 10
    decimals first: without that, cross-platform float noise in the last bits
    would make the same logical dataset hash differently on a different BLAS,
    and the hash would flag drift that isn't there.
    """
    subset = df[sorted(columns)] if columns else df[sorted(df.columns)]
    numeric = subset.select_dtypes(include=["number"]).round(10)
    non_numeric = subset.select_dtypes(exclude=["number"])

    hasher = hashlib.sha256()
    hasher.update(",".join(subset.columns).encode())
    hasher.update(pd.util.hash_pandas_object(numeric, index=True).values.tobytes())
    if not non_numeric.empty:
        hasher.update(pd.util.hash_pandas_object(non_numeric, index=True).values.tobytes())
    return hasher.hexdigest()


@dataclass
class DataQualityReport:
    """Missingness and staleness for one training run.

    Recorded rather than merely checked because "the model got worse" and "20%
    of one feature went missing that month" are the same investigation, and
    without this you cannot tell them apart after the fact.
    """

    rows: int
    columns: int
    missing_by_column: dict[str, float] = field(default_factory=dict)
    fully_missing_columns: list[str] = field(default_factory=list)
    date_min: Optional[str] = None
    date_max: Optional[str] = None
    # Trading days between the last observation and when this ran. A model
    # trained on data that stopped two weeks ago is a different object from one
    # trained through yesterday, and the metrics won't say so.
    staleness_days: Optional[int] = None

    @classmethod
    def from_frame(cls, df: pd.DataFrame) -> "DataQualityReport":
        missing = (df.isna().mean() * 100).round(3)
        date_min = date_max = None
        staleness = None
        if isinstance(df.index, pd.DatetimeIndex) and len(df):
            date_min = str(df.index.min().date())
            date_max = str(df.index.max().date())
            staleness = (datetime.now(timezone.utc).date() - df.index.max().date()).days
        return cls(
            rows=len(df),
            columns=len(df.columns),
            missing_by_column={k: float(v) for k, v in missing.items() if v > 0},
            fully_missing_columns=[c for c in df.columns if df[c].isna().all()],
            date_min=date_min,
            date_max=date_max,
            staleness_days=staleness,
        )


@dataclass
class ReproducibilityManifest:
    """Everything needed to answer "what produced this model, exactly?".

    Written alongside every trained artefact. The fields are chosen so that two
    manifests can be diffed to explain a metric change: if the dataset hash
    differs the data moved, if the commit differs the code moved, if the
    feature version differs the definitions moved, and if none differ but the
    metrics did, the run is nondeterministic and that is itself the finding.
    """

    model_name: str
    model_version: str
    created_at: str
    git_commit: Optional[str]
    git_dirty: Optional[bool]
    feature_schema_version: str
    dataset_hash: str
    feature_names: list[str]
    training_start: Optional[str]
    training_end: Optional[str]
    universe: list[str]
    excluded_tickers: dict[str, str]  # ticker -> why it was dropped
    random_seed: Optional[int]
    hyperparameters: dict
    metrics: dict
    data_quality: dict
    label_definition: Optional[str] = None
    notes: Optional[str] = None

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent, sort_keys=True, default=str)

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        logger.info(f"[lineage] manifest written: {path}")
        return path

    @classmethod
    def load(cls, path: Path) -> "ReproducibilityManifest":
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))

    def differences_from(self, other: "ReproducibilityManifest") -> dict[str, tuple]:
        """Field-by-field diff against another manifest.

        The intended use is triage: run this first when a metric moves, before
        assuming a code change caused it.
        """
        diffs = {}
        for key, value in asdict(self).items():
            other_value = asdict(other).get(key)
            if value != other_value:
                diffs[key] = (other_value, value)
        return diffs


def build_manifest(
    *,
    model_name: str,
    model_version: str,
    features: pd.DataFrame,
    feature_names: list[str],
    universe: list[str],
    excluded_tickers: Optional[dict[str, str]] = None,
    hyperparameters: Optional[dict] = None,
    metrics: Optional[dict] = None,
    random_seed: Optional[int] = None,
    label_definition: Optional[str] = None,
    notes: Optional[str] = None,
) -> ReproducibilityManifest:
    """Assemble a manifest from a training run's actual inputs."""
    quality = DataQualityReport.from_frame(features)
    return ReproducibilityManifest(
        model_name=model_name,
        model_version=model_version,
        created_at=datetime.now(timezone.utc).isoformat(),
        git_commit=git_commit(),
        git_dirty=git_is_dirty(),
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        dataset_hash=dataset_hash(features, feature_names),
        feature_names=sorted(feature_names),
        training_start=quality.date_min,
        training_end=quality.date_max,
        universe=sorted(universe),
        excluded_tickers=excluded_tickers or {},
        random_seed=random_seed,
        hyperparameters=hyperparameters or {},
        metrics=metrics or {},
        data_quality=asdict(quality),
        label_definition=label_definition,
        notes=notes,
    )
