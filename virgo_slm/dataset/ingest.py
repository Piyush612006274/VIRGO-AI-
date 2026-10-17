"""Local dataset ingestion: txt / json / jsonl / directories -> records.

Deliberately local-only. Phase 3's brief allows *designing* interfaces for
external dataset adapters, but this module does not fetch, download, or
otherwise silently pull in any external corpus -- every record here comes
from a file the caller pointed the pipeline at.

Malformed records are never silently dropped: they are surfaced as
``IngestError`` entries alongside the successfully parsed records, and the
pipeline records them in the manifest rather than pretending they did not
exist.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from virgo_slm.dataset.config import DatasetSourceConfig
from virgo_slm.dataset.record import DatasetRecord

_TEXT_EXTENSIONS = {".txt", ".text", ".md"}
_JSON_EXTENSIONS = {".json"}
_JSONL_EXTENSIONS = {".jsonl", ".ndjson"}


@dataclass(frozen=True, slots=True)
class IngestError:
    """One malformed record that could not be parsed."""

    source_path: str
    source_index: int
    reason: str


@dataclass(frozen=True, slots=True)
class IngestResult:
    records: tuple[DatasetRecord, ...]
    errors: tuple[IngestError, ...]
    files_read: tuple[str, ...]
    file_hashes: dict[str, str]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _make_record_id(source_path: str, index: int) -> str:
    return hashlib.sha256(f"{source_path}::{index}".encode()).hexdigest()[:24]


def _resolve_format(path: Path, declared: str) -> str:
    if declared != "auto":
        return declared
    suffix = path.suffix.lower()
    if suffix in _JSONL_EXTENSIONS:
        return "jsonl"
    if suffix in _JSON_EXTENSIONS:
        return "json"
    return "txt"


def _iter_source_files(source_path: Path) -> list[Path]:
    if source_path.is_file():
        return [source_path]
    if source_path.is_dir():
        return sorted(p for p in source_path.rglob("*") if p.is_file())
    raise FileNotFoundError(f"Dataset source path does not exist: {source_path}")


def _read_txt(
    path: Path, source: DatasetSourceConfig
) -> tuple[list[DatasetRecord], list[IngestError]]:
    records: list[DatasetRecord] = []
    errors: list[IngestError] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        errors.append(IngestError(str(path), 0, f"not valid utf-8: {exc}"))
        return records, errors

    if source.txt_mode == "whole_file":
        chunks = [raw]
    else:
        chunks = raw.split("\n")

    for index, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        records.append(
            DatasetRecord(
                record_id=_make_record_id(str(path), index),
                text=chunk,
                source_path=str(path),
                source_index=index,
                category=source.category,
                domain=source.domain,
                language=source.language,
                license=source.license,
                provenance=source.provenance,
            )
        )
    return records, errors


def _record_from_obj(
    obj: object, path: Path, index: int, source: DatasetSourceConfig
) -> tuple[DatasetRecord | None, IngestError | None]:
    if not isinstance(obj, dict):
        return None, IngestError(str(path), index, "record is not a JSON object")
    text = obj.get(source.text_field)
    if not isinstance(text, str) or not text.strip():
        return None, IngestError(
            str(path),
            index,
            f"missing or empty '{source.text_field}' field",
        )
    # Per-record metadata overrides source-level defaults when present,
    # but never invents anything not actually in the record or config.
    language = obj.get("language") if isinstance(obj.get("language"), str) else source.language
    domain = obj.get("domain") if isinstance(obj.get("domain"), str) else source.domain
    license_ = obj.get("license") if isinstance(obj.get("license"), str) else source.license
    provenance = (
        obj.get("provenance") if isinstance(obj.get("provenance"), str) else source.provenance
    )
    record_id_field = obj.get("id")
    record_id = (
        f"{path}::{record_id_field}"
        if isinstance(record_id_field, str)
        else _make_record_id(str(path), index)
    )
    if isinstance(record_id_field, str):
        record_id = hashlib.sha256(record_id.encode("utf-8")).hexdigest()[:24]

    return (
        DatasetRecord(
            record_id=record_id,
            text=text,
            source_path=str(path),
            source_index=index,
            category=source.category,
            domain=domain if isinstance(domain, str) else source.domain,
            language=language if isinstance(language, str) else source.language,
            license=license_ if isinstance(license_, str) else source.license,
            provenance=provenance if isinstance(provenance, str) else source.provenance,
        ),
        None,
    )


def _read_json(
    path: Path, source: DatasetSourceConfig
) -> tuple[list[DatasetRecord], list[IngestError]]:
    records: list[DatasetRecord] = []
    errors: list[IngestError] = []
    try:
        raw_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        errors.append(IngestError(str(path), 0, f"not valid utf-8: {exc}"))
        return records, errors

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        errors.append(IngestError(str(path), 0, f"invalid JSON: {exc}"))
        return records, errors

    items = data if isinstance(data, list) else [data]
    for index, item in enumerate(items):
        record, error = _record_from_obj(item, path, index, source)
        if record is not None:
            records.append(record)
        if error is not None:
            errors.append(error)
    return records, errors


def _read_jsonl(
    path: Path, source: DatasetSourceConfig
) -> tuple[list[DatasetRecord], list[IngestError]]:
    records: list[DatasetRecord] = []
    errors: list[IngestError] = []
    try:
        raw_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        errors.append(IngestError(str(path), 0, f"not valid utf-8: {exc}"))
        return records, errors

    for index, line in enumerate(raw_text.split("\n")):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(IngestError(str(path), index, f"invalid JSON line: {exc}"))
            continue
        record, error = _record_from_obj(obj, path, index, source)
        if record is not None:
            records.append(record)
        if error is not None:
            errors.append(error)
    return records, errors


def ingest_source(source: DatasetSourceConfig) -> IngestResult:
    """Read one configured source (file or directory) into records."""
    root = Path(source.path)
    files = _iter_source_files(root)

    all_records: list[DatasetRecord] = []
    all_errors: list[IngestError] = []
    file_hashes: dict[str, str] = {}

    for file_path in files:
        file_hashes[str(file_path)] = _sha256_file(file_path)
        fmt = _resolve_format(file_path, source.format)
        if fmt == "txt":
            records, errors = _read_txt(file_path, source)
        elif fmt == "json":
            records, errors = _read_json(file_path, source)
        elif fmt == "jsonl":
            records, errors = _read_jsonl(file_path, source)
        else:  # pragma: no cover - _resolve_format only returns known formats
            raise ValueError(f"Unsupported format: {fmt}")
        all_records.extend(records)
        all_errors.extend(errors)

    return IngestResult(
        records=tuple(all_records),
        errors=tuple(all_errors),
        files_read=tuple(str(f) for f in files),
        file_hashes=file_hashes,
    )


def ingest_sources(sources: tuple[DatasetSourceConfig, ...]) -> IngestResult:
    """Ingest every configured source and concatenate the results."""
    records: list[DatasetRecord] = []
    errors: list[IngestError] = []
    files_read: list[str] = []
    file_hashes: dict[str, str] = {}

    for source in sources:
        result = ingest_source(source)
        records.extend(result.records)
        errors.extend(result.errors)
        files_read.extend(result.files_read)
        file_hashes.update(result.file_hashes)

    return IngestResult(
        records=tuple(records),
        errors=tuple(errors),
        files_read=tuple(files_read),
        file_hashes=file_hashes,
    )


def iter_records(sources: tuple[DatasetSourceConfig, ...]) -> Iterator[DatasetRecord]:
    """Convenience generator form for callers that don't need error detail."""
    yield from ingest_sources(sources).records
