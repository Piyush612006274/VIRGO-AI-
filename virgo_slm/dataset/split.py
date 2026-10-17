"""Deterministic train/validation/test splitting.

Split assignment is a deterministic function of ``(record_id, seed)`` via
SHA-256 hash bucketing into 10,000 buckets, rather than a stateful shuffle.
This has two properties the task requires:

1. **Reproducible**: the same ``(record_id, seed)`` always maps to the same
   split, on any machine, in any record order -- no RNG state to keep in
   sync.
2. **No duplicate leakage**: this function is only ever called on the
   already-deduplicated record set (deduplication happens strictly before
   splitting in the pipeline), so a document that would have appeared more
   than once has already been reduced to a single surviving record before
   a split is assigned to it. There is nothing left that could split
   across train/validation/test.

Small-dataset handling: if a ratio is non-zero but the dataset is too
small for that split to get a full record via proportional hashing, this
can legitimately produce an empty split (e.g. 3 records at 98/1/1 ratios).
That is surfaced as-is in the manifest rather than artificially forcing a
minimum -- the caller should reduce validation/test ratios or supply more
data for very small corpora.
"""

from __future__ import annotations

import hashlib

from virgo_slm.dataset.record import DatasetRecord, SplitName

_NUM_BUCKETS = 10_000


def _bucket(record_id: str, seed: int) -> int:
    digest = hashlib.sha256(f"{record_id}::{seed}".encode()).hexdigest()
    return int(digest, 16) % _NUM_BUCKETS


def assign_split(
    record_id: str,
    seed: int,
    *,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
) -> SplitName:
    bucket = _bucket(record_id, seed)
    train_cutoff = round(train_ratio * _NUM_BUCKETS)
    validation_cutoff = train_cutoff + round(validation_ratio * _NUM_BUCKETS)
    if bucket < train_cutoff:
        return "train"
    if bucket < validation_cutoff:
        return "validation"
    return "test"


def split_records(
    records: tuple[DatasetRecord, ...],
    *,
    seed: int,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
) -> tuple[DatasetRecord, ...]:
    """Return records with ``.split`` populated. Input should be deduplicated."""
    return tuple(
        record.with_updates(
            split=assign_split(
                record.record_id,
                seed,
                train_ratio=train_ratio,
                validation_ratio=validation_ratio,
                test_ratio=test_ratio,
            )
        )
        for record in records
    )
