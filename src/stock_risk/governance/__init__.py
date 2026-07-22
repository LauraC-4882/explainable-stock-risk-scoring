"""[R4][R5] Model governance: registry, lifecycle, lineage, reproducibility."""

from .lineage import (
    FEATURE_SCHEMA_VERSION,
    DataQualityReport,
    ReproducibilityManifest,
    build_manifest,
    dataset_hash,
    git_commit,
    git_is_dirty,
)
from .registry import (
    ModelCard,
    ModelRecord,
    ModelRegistry,
    ModelStatus,
    TransitionError,
    ValidationThresholds,
)

__all__ = [
    "FEATURE_SCHEMA_VERSION",
    "DataQualityReport",
    "ModelCard",
    "ModelRecord",
    "ModelRegistry",
    "ModelStatus",
    "ReproducibilityManifest",
    "TransitionError",
    "ValidationThresholds",
    "build_manifest",
    "dataset_hash",
    "git_commit",
    "git_is_dirty",
]
