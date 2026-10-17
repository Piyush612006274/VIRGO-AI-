"""Dataset manifest generation.

The manifest is the audit trail for one pipeline run: what files went in
(with content hashes), how many records were accepted/rejected and why,
language/domain distribution, dedup counts, split counts, and the exact
configuration + seed used. It is written as JSON so it is diffable and
so :func:`virgo_slm.dataset.pipeline` reproducibility checks can compare
two runs field-by-field.

Only ``generated_at_utc`` is expected to differ between two runs of the
same config/input/seed (Task 16 permits explicitly-documented
non-deterministic metadata) -- every other field must match exactly.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from virgo_slm.dataset.config import DatasetPipelineConfig
from virgo_slm.dataset.ingest import IngestError
from virgo_slm.dataset.record import DatasetRecord

MANIFEST_FILE_NAME = "dataset_manifest.json"
PIPELINE_VERSION = "0.1.0"

# Fields intentionally excluded from reproducibility comparison.
NON_DETERMINISTIC_FIELDS = ("generated_at_utc",)


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    name: str
    version: str
    pipeline_version: str
    seed: int
    generated_at_utc: str

    input_files: tuple[str, ...]
    file_hashes: dict[str, str]

    total_ingested: int
    total_ingest_errors: int
    ingest_error_reasons: dict[str, int]

    total_accepted: int
    total_rejected: int
    rejection_reason_counts: dict[str, int]

    exact_duplicates_removed: int
    normalized_duplicates_removed: int

    language_distribution: dict[str, int]
    domain_distribution: dict[str, int]
    category_distribution: dict[str, int]
    license_distribution: dict[str, int]
    provenance_distribution: dict[str, int]

    split_counts: dict[str, int]

    total_characters_accepted: int
    length_distribution: dict[str, int]

    config: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def save(self, output_dir: str | Path) -> Path:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / MANIFEST_FILE_NAME
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, path: str | Path) -> DatasetManifest:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**data)


def _length_bucket(char_count: int) -> str:
    if char_count < 50:
        return "0-49"
    if char_count < 200:
        return "50-199"
    if char_count < 1000:
        return "200-999"
    if char_count < 5000:
        return "1000-4999"
    return "5000+"


def build_manifest(
    *,
    config: DatasetPipelineConfig,
    input_files: tuple[str, ...],
    file_hashes: dict[str, str],
    ingest_errors: tuple[IngestError, ...],
    accepted_records: tuple[DatasetRecord, ...],
    rejected_records: tuple[DatasetRecord, ...],
    exact_duplicates_removed: int,
    normalized_duplicates_removed: int,
) -> DatasetManifest:
    total_ingested = len(accepted_records) + len(rejected_records)

    rejection_reason_counts: Counter[str] = Counter()
    for record in rejected_records:
        for reason in record.rejection_reasons:
            rejection_reason_counts[reason] += 1

    ingest_error_reasons: Counter[str] = Counter(
        error.reason.split(":")[0].strip() for error in ingest_errors
    )

    language_distribution: Counter[str] = Counter(
        r.effective_language for r in accepted_records
    )
    domain_distribution: Counter[str] = Counter(r.domain for r in accepted_records)
    # Explicitly widened to Counter[str]: r.category/r.split are narrow
    # Literal types (DatasetCategory/SplitName), which is correct for the
    # record schema, but the manifest's *distribution* fields are
    # deliberately str-keyed (arbitrary categories may appear once
    # instruction/tool-calling/eval/preference datasets exist in later
    # phases) -- this is a genuine widening, not a suppression.
    category_distribution: Counter[str] = Counter(
        r.category for r in accepted_records
    )
    license_distribution: Counter[str] = Counter(
        r.license or "unspecified" for r in accepted_records
    )
    provenance_distribution: Counter[str] = Counter(
        r.provenance or "unspecified" for r in accepted_records
    )
    split_counts: Counter[str] = Counter(
        r.split or "unassigned" for r in accepted_records
    )
    length_distribution: Counter[str] = Counter(
        _length_bucket(len(r.text)) for r in accepted_records
    )

    return DatasetManifest(
        name=config.name,
        version=config.version,
        pipeline_version=PIPELINE_VERSION,
        seed=config.seed,
        generated_at_utc=datetime.now(UTC).isoformat(),
        input_files=input_files,
        file_hashes=file_hashes,
        total_ingested=total_ingested,
        total_ingest_errors=len(ingest_errors),
        ingest_error_reasons=dict(ingest_error_reasons),
        total_accepted=len(accepted_records),
        total_rejected=len(rejected_records),
        rejection_reason_counts=dict(rejection_reason_counts),
        exact_duplicates_removed=exact_duplicates_removed,
        normalized_duplicates_removed=normalized_duplicates_removed,
        language_distribution=dict(language_distribution),
        domain_distribution=dict(domain_distribution),
        category_distribution=dict(category_distribution),
        license_distribution=dict(license_distribution),
        provenance_distribution=dict(provenance_distribution),
        split_counts=dict(split_counts),
        total_characters_accepted=sum(len(r.text) for r in accepted_records),
        length_distribution=dict(length_distribution),
        config={
            k: v for k, v in asdict(config).items()
        },
    )


def manifests_equal_ignoring_nondeterministic_fields(
    a: DatasetManifest, b: DatasetManifest
) -> bool:
    """Compare two manifests for the Task 16 reproducibility check."""
    da, db = a.to_dict(), b.to_dict()
    for key in NON_DETERMINISTIC_FIELDS:
        da.pop(key, None)
        db.pop(key, None)
    return da == db
