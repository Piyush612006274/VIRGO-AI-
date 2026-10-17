"""Deterministic deduplication.

Two hash keys are computed per record:

- ``exact_hash``: SHA-256 of the (normalized) text as-is. Catches byte-
  identical duplicates.
- ``normalized_hash``: SHA-256 of the text with all whitespace runs
  collapsed to a single space. Catches near-duplicates that differ only in
  formatting/whitespace (trailing spaces, line-wrap differences, etc.).

This is exact-hash deduplication only -- it does NOT claim semantic or
fuzzy near-duplicate detection (e.g. minhash/simhash over shingles). The
``DedupIndex`` interface below is written so a future near-duplicate
strategy can be plugged in without changing the pipeline's call sites, but
nothing beyond exact/normalized hashing is implemented or claimed here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from virgo_slm.dataset.normalize import whitespace_collapsed
from virgo_slm.dataset.record import DatasetRecord


def compute_hashes(text: str) -> tuple[str, str]:
    """Return ``(exact_hash, normalized_hash)`` for ``text``."""
    exact = hashlib.sha256(text.encode("utf-8")).hexdigest()
    normalized = hashlib.sha256(
        whitespace_collapsed(text).encode("utf-8")
    ).hexdigest()
    return exact, normalized


@dataclass
class DedupIndex:
    """Tracks hashes seen so far; first occurrence wins, deterministically.

    Processing records in a fixed (source-file, then in-file index) order
    and always keeping the first occurrence makes the surviving record for
    any duplicate group deterministic given the same input and ingestion
    order -- required for the Task 16 reproducibility check.
    """

    seen_exact: set[str] = field(default_factory=set)
    seen_normalized: set[str] = field(default_factory=set)
    exact_duplicates_removed: int = 0
    normalized_duplicates_removed: int = 0

    def is_duplicate(self, record: DatasetRecord) -> str | None:
        """Return a rejection reason if this record is a duplicate, else None.

        Does not mutate state -- call :meth:`register` separately once the
        record is confirmed to be kept, so a record rejected for other
        reasons (quality filters) never "occupies" a dedup slot.
        """
        assert record.exact_hash is not None
        assert record.normalized_hash is not None
        if record.exact_hash in self.seen_exact:
            return "exact_duplicate"
        if record.normalized_hash in self.seen_normalized:
            return "normalized_duplicate"
        return None

    def register(self, record: DatasetRecord) -> None:
        assert record.exact_hash is not None
        assert record.normalized_hash is not None
        self.seen_exact.add(record.exact_hash)
        self.seen_normalized.add(record.normalized_hash)
