"""Orchestrates ingest -> normalize -> language-id -> filter -> dedup -> split.

This is the single entry point the CLI and tests use. Each stage is kept
in its own module (:mod:`ingest`, :mod:`normalize`, :mod:`langid`,
:mod:`filters`, :mod:`dedup`, :mod:`split`) so each is independently
testable; this module wires them together in the fixed order the
reproducibility guarantees depend on:

    ingest (fixed file order from ``sorted()`` + in-file index)
    -> normalize
    -> language-id
    -> quality filter (rejects recorded, not silently dropped)
    -> exact/normalized dedup (first occurrence in ingest order wins)
    -> deterministic split assignment (hash-based, order-independent)
    -> write per-split text files + manifest
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from virgo_slm.dataset.config import DatasetPipelineConfig
from virgo_slm.dataset.dedup import DedupIndex, compute_hashes
from virgo_slm.dataset.filters import apply_filters
from virgo_slm.dataset.ingest import IngestError, ingest_sources
from virgo_slm.dataset.langid import detect_language
from virgo_slm.dataset.manifest import DatasetManifest, build_manifest
from virgo_slm.dataset.normalize import normalize_text
from virgo_slm.dataset.record import DatasetRecord, SplitName
from virgo_slm.dataset.split import split_records

DOCUMENT_SEPARATOR = "\n\n"
_SPLIT_FILE_NAMES: dict[SplitName, str] = {
    "train": "train.txt",
    "validation": "validation.txt",
    "test": "test.txt",
}
_SPLIT_JSONL_FILE_NAMES: dict[SplitName, str] = {
    "train": "train.jsonl",
    "validation": "validation.jsonl",
    "test": "test.jsonl",
}


@dataclass(frozen=True, slots=True)
class PipelineResult:
    accepted_records: tuple[DatasetRecord, ...]
    rejected_records: tuple[DatasetRecord, ...]
    ingest_errors: tuple[IngestError, ...]
    manifest: DatasetManifest
    split_files: dict[SplitName, str]
    split_jsonl_files: dict[SplitName, str]
    manifest_path: str | None


def _process_record(
    record: DatasetRecord, config: DatasetPipelineConfig
) -> DatasetRecord:
    normalized_text = normalize_text(record.text)
    record = record.with_updates(text=normalized_text, normalized=True)

    detected = detect_language(normalized_text)
    record = record.with_updates(detected_language=detected)

    reasons = apply_filters(record, config)
    if reasons:
        return record.with_updates(rejected=True, rejection_reasons=reasons)

    exact_hash, normalized_hash = compute_hashes(normalized_text)
    return record.with_updates(exact_hash=exact_hash, normalized_hash=normalized_hash)


def run_pipeline(config: DatasetPipelineConfig) -> PipelineResult:
    ingest_result = ingest_sources(config.sources)

    processed = tuple(_process_record(r, config) for r in ingest_result.records)

    passed_filters = [r for r in processed if not r.rejected]
    filter_rejected = [r for r in processed if r.rejected]

    dedup_index = DedupIndex()
    kept: list[DatasetRecord] = []
    dedup_rejected: list[DatasetRecord] = []
    for record in passed_filters:
        if config.dedup_enabled:
            reason = dedup_index.is_duplicate(record)
        else:
            reason = None
        if reason is not None:
            if reason == "exact_duplicate":
                dedup_index.exact_duplicates_removed += 1
            else:
                dedup_index.normalized_duplicates_removed += 1
            dedup_rejected.append(
                record.with_updates(rejected=True, rejection_reasons=(reason,))
            )
            continue
        dedup_index.register(record)
        kept.append(record)

    split_kept = split_records(
        tuple(kept),
        seed=config.seed,
        train_ratio=config.train_ratio,
        validation_ratio=config.validation_ratio,
        test_ratio=config.test_ratio,
    )

    rejected = tuple(filter_rejected) + tuple(dedup_rejected)

    manifest = build_manifest(
        config=config,
        input_files=ingest_result.files_read,
        file_hashes=ingest_result.file_hashes,
        ingest_errors=ingest_result.errors,
        accepted_records=split_kept,
        rejected_records=rejected,
        exact_duplicates_removed=dedup_index.exact_duplicates_removed,
        normalized_duplicates_removed=dedup_index.normalized_duplicates_removed,
    )

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    split_files = _write_split_files(split_kept, output_dir)
    split_jsonl_files = _write_split_jsonl_files(split_kept, output_dir)

    manifest_path: str | None = None
    if config.write_manifest:
        manifest_path = str(manifest.save(output_dir))

    return PipelineResult(
        accepted_records=split_kept,
        rejected_records=rejected,
        ingest_errors=ingest_result.errors,
        manifest=manifest,
        split_files=split_files,
        split_jsonl_files=split_jsonl_files,
        manifest_path=manifest_path,
    )


def _write_split_files(
    records: tuple[DatasetRecord, ...], output_dir: Path
) -> dict[SplitName, str]:
    buckets: dict[SplitName, list[str]] = {"train": [], "validation": [], "test": []}
    for record in records:
        assert record.split is not None
        buckets[record.split].append(record.text)

    paths: dict[SplitName, str] = {}
    for split_name, file_name in _SPLIT_FILE_NAMES.items():
        path = output_dir / file_name
        path.write_text(
            DOCUMENT_SEPARATOR.join(buckets[split_name]), encoding="utf-8"
        )
        paths[split_name] = str(path)
    return paths


def _write_split_jsonl_files(
    records: tuple[DatasetRecord, ...], output_dir: Path
) -> dict[SplitName, str]:
    """Write one JSON object per accepted record, per split, one per line.

    Added for Phase 4 (:mod:`virgo_slm.training.data`): the flat
    ``{split}.txt`` files above join documents with
    ``DOCUMENT_SEPARATOR`` ("\\n\\n"), but :mod:`virgo_slm.dataset.normalize`
    legitimately preserves a genuine double-blank-line *inside* a
    document (it only collapses 3+ consecutive newlines), so splitting a
    flat file back into per-document boundaries by that same separator is
    ambiguous. JSONL (one record per line, text embedded as a JSON
    string) has no such ambiguity and is what LM training data loading
    actually needs -- exact document boundaries, not a display format.
    This does not change ``{split}.txt`` or the manifest in any way.
    """
    buckets: dict[SplitName, list[DatasetRecord]] = {
        "train": [], "validation": [], "test": []
    }
    for record in records:
        assert record.split is not None
        buckets[record.split].append(record)

    paths: dict[SplitName, str] = {}
    for split_name, file_name in _SPLIT_JSONL_FILE_NAMES.items():
        path = output_dir / file_name
        lines = [
            json.dumps(
                {
                    "text": r.text,
                    "language": r.effective_language,
                    "domain": r.domain,
                    "record_id": r.record_id,
                },
                ensure_ascii=False,
            )
            for r in buckets[split_name]
        ]
        path.write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
        )
        paths[split_name] = str(path)
    return paths
