"""Configuration for the Phase 3 dataset pipeline.

Follows the same convention as ``virgo_slm.model.config`` and
``virgo_slm.tokenizer.config``: frozen dataclasses, validated in
``__post_init__``, no machine-specific defaults baked in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from virgo_slm.dataset.record import DatasetCategory

IngestFormat = Literal["txt", "json", "jsonl", "auto"]
TxtMode = Literal["line", "whole_file"]


@dataclass(frozen=True, slots=True)
class DatasetSourceConfig:
    """One input source (a file or a directory of files).

    Language/domain/license/provenance here are *explicit user-supplied
    metadata* about this source -- the pipeline never infers a license or
    invents provenance. Leave them ``None`` if genuinely unknown; that is
    recorded as ``"unspecified"`` in the manifest rather than guessed.
    """

    path: str
    format: IngestFormat = "auto"
    txt_mode: TxtMode = "line"
    text_field: str = "text"
    category: DatasetCategory = "pretraining"
    domain: str = "general"
    language: str | None = None
    license: str | None = None
    provenance: str | None = None

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("DatasetSourceConfig.path must not be empty")
        if not self.text_field:
            raise ValueError("DatasetSourceConfig.text_field must not be empty")


@dataclass(frozen=True, slots=True)
class DatasetPipelineConfig:
    """Full configuration for one dataset pipeline run."""

    sources: tuple[DatasetSourceConfig, ...]
    output_dir: str
    seed: int = 42

    train_ratio: float = 0.98
    validation_ratio: float = 0.01
    test_ratio: float = 0.01

    min_chars: int = 2
    max_chars: int | None = None

    # Used by filters.filter_character_diversity as (1 - threshold): a
    # record is rejected only if its single most-frequent character makes
    # up more than (1 - low_diversity_threshold) of the text. Default 0.05
    # => reject only when one character exceeds 95% of the text (i.e.
    # genuinely degenerate repetition, not ordinary prose/code).
    low_diversity_threshold: float = 0.05
    whitespace_ratio_threshold: float = 0.9
    max_line_repetition_ratio: float = 0.5

    dedup_enabled: bool = True
    write_manifest: bool = True

    name: str = "virgo-slm-dataset"
    version: str = "0.1.0"

    def __post_init__(self) -> None:
        errors: list[str] = []

        def require(condition: bool, message: str) -> None:
            if not condition:
                errors.append(message)

        require(len(self.sources) > 0, "at least one source is required")
        require(bool(self.output_dir), "output_dir must not be empty")

        ratio_sum = self.train_ratio + self.validation_ratio + self.test_ratio
        require(
            abs(ratio_sum - 1.0) < 1e-9,
            f"train_ratio + validation_ratio + test_ratio must sum to 1.0 "
            f"(got {ratio_sum})",
        )
        for ratio_name, ratio_value in (
            ("train_ratio", self.train_ratio),
            ("validation_ratio", self.validation_ratio),
            ("test_ratio", self.test_ratio),
        ):
            require(0.0 <= ratio_value <= 1.0, f"{ratio_name} must be in [0, 1]")

        require(self.min_chars >= 0, "min_chars must be non-negative")
        if self.max_chars is not None:
            require(
                self.max_chars >= self.min_chars,
                "max_chars must be >= min_chars when set",
            )
        require(
            0.0 <= self.low_diversity_threshold <= 1.0,
            "low_diversity_threshold must be in [0, 1]",
        )
        require(
            0.0 <= self.whitespace_ratio_threshold <= 1.0,
            "whitespace_ratio_threshold must be in [0, 1]",
        )
        require(
            0.0 <= self.max_line_repetition_ratio <= 1.0,
            "max_line_repetition_ratio must be in [0, 1]",
        )

        if errors:
            raise ValueError("Invalid DatasetPipelineConfig: " + "; ".join(errors))
