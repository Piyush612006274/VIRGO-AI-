"""Stable dataset record schemas.

Every stage of the Phase 3 pipeline (ingest -> normalize -> language-id ->
filter -> dedup -> split) passes ``DatasetRecord`` objects, not raw dicts.
Each stage returns a *new* record (records are frozen) with additional
fields filled in, so the full processing history of an accepted or
rejected record is always inspectable from the final object alone.

The schema is deliberately generic (``category``/``domain`` are free-form
strings, ``extra`` is an open metadata bag) so it can be reused unchanged
for the instruction-tuning, tool-calling, evaluation and preference
datasets that later phases will add -- Phase 3 only *implements* the
pretraining path, but nothing here is pretraining-specific.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DatasetCategory = Literal[
    "pretraining", "instruction", "tool_calling", "evaluation", "preference"
]
SplitName = Literal["train", "validation", "test"]


@dataclass(frozen=True, slots=True)
class DatasetRecord:
    """One document as it moves through the pipeline.

    ``text`` always holds the *current* text for this stage (raw on
    ingestion, normalized after :mod:`virgo_slm.dataset.normalize`).
    ``record_id`` is stable and content-independent (derived from source
    path + index at ingestion time) so it can be used for deterministic
    split assignment even after ``text`` itself changes downstream.
    """

    record_id: str
    text: str
    source_path: str
    source_index: int

    category: DatasetCategory = "pretraining"
    domain: str = "general"
    language: str | None = None  # explicit override supplied at ingestion
    detected_language: str | None = None  # filled in by langid.py
    license: str | None = None
    provenance: str | None = None

    normalized: bool = False
    exact_hash: str | None = None
    normalized_hash: str | None = None
    split: SplitName | None = None

    rejected: bool = False
    rejection_reasons: tuple[str, ...] = field(default_factory=tuple)

    extra: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.record_id:
            raise ValueError("record_id must not be empty")
        if not self.source_path:
            raise ValueError("source_path must not be empty")
        if self.source_index < 0:
            raise ValueError("source_index must be non-negative")

    @property
    def effective_language(self) -> str:
        """Explicit language override wins; otherwise the detected one."""
        if self.language is not None:
            return self.language
        if self.detected_language is not None:
            return self.detected_language
        return "unknown"

    def with_updates(self, **updates: object) -> DatasetRecord:
        """Return a new record with the given fields replaced.

        Thin wrapper over ``dataclasses.replace`` kept here so pipeline
        stages import one thing from this module instead of also reaching
        into ``dataclasses`` directly.
        """
        from dataclasses import replace

        return replace(self, **updates)  # type: ignore[arg-type]
