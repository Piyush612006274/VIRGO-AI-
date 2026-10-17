"""Typed temporary evidence contracts for bounded knowledge-on-demand."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from virgo.contracts.models.correlation import new_correlation_id
from virgo.contracts.models.learning import KnowledgeScope


class KnowledgeType(StrEnum):
    STABLE_KNOWLEDGE = "stable_knowledge"
    CURRENT_INFORMATION = "current_information"
    TIME_SENSITIVE_INFORMATION = "time_sensitive_information"
    SOURCE_SPECIFIC_INFORMATION = "source_specific_information"
    LOCAL_PROJECT_KNOWLEDGE = "local_project_knowledge"


class FreshnessState(StrEnum):
    CURRENT = "current"
    RECENT = "recent"
    STALE = "stale"
    UNKNOWN = "unknown"


class KnowledgeRetrievalStatus(StrEnum):
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    CONFLICTING = "conflicting"
    NOT_FOUND = "not_found"
    NOT_CONFIGURED = "not_configured"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeNeed:
    task_id: str
    question: str
    knowledge_type: KnowledgeType
    scope: KnowledgeScope
    scope_key: str
    session_id: str | None = None
    known_context: tuple[str, ...] = ()
    maximum_sources: int = 3
    timeout_seconds: float = 10.0
    max_retries: int = 0

    def __post_init__(self) -> None:
        if (
            not self.task_id.strip()
            or not self.question.strip()
            or not self.scope_key.strip()
        ):
            raise ValueError("knowledge need identity is invalid")
        if len(self.known_context) > 5 or not 1 <= self.maximum_sources <= 5:
            raise ValueError("knowledge need exceeds source/context bounds")
        if not 0 < self.timeout_seconds <= 60 or not 0 <= self.max_retries <= 1:
            raise ValueError("knowledge retrieval time/retry bounds are invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeSource:
    source_type: str
    title: str
    origin: str
    excerpt: str
    provenance: str
    retrieval_method: str
    freshness: FreshnessState = FreshnessState.UNKNOWN
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    published_at: datetime | None = None
    updated_at: datetime | None = None
    claim_key: str | None = None
    claim_value: str | None = None
    source_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        for value in (
            self.source_type,
            self.title,
            self.origin,
            self.excerpt,
            self.provenance,
            self.retrieval_method,
        ):
            if not value.strip():
                raise ValueError("knowledge source text is invalid")
        if len(self.excerpt) > 500:
            raise ValueError("knowledge source excerpt exceeds 500 characters")
        if (
            "://" in self.origin
            and "@" in self.origin.split("://", 1)[1].split("/", 1)[0]
        ):
            raise ValueError("knowledge source origin must not contain credentials")
        if any(
            value is not None and value.tzinfo is None
            for value in (self.retrieved_at, self.published_at, self.updated_at)
        ):
            raise ValueError("knowledge source timestamps must be timezone-aware")
        if (self.claim_key is None) != (self.claim_value is None):
            raise ValueError("knowledge source claim metadata must be paired")


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeConflict:
    claim_key: str
    source_ids: tuple[str, ...]
    values: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.claim_key.strip()
            or len(self.source_ids) < 2
            or len(self.values) < 2
        ):
            raise ValueError("knowledge conflict requires incompatible sourced values")


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeEvidencePackage:
    task_id: str
    need: KnowledgeNeed
    sources: tuple[KnowledgeSource, ...]
    conflicts: tuple[KnowledgeConflict, ...]
    status: KnowledgeRetrievalStatus
    remaining_unknowns: tuple[str, ...] = ()
    requires_verification: bool = True

    def __post_init__(self) -> None:
        if (
            self.task_id != self.need.task_id
            or len(self.sources) > self.need.maximum_sources
        ):
            raise ValueError("knowledge evidence package exceeds its need")
        if (self.status is KnowledgeRetrievalStatus.CONFLICTING) != bool(
            self.conflicts
        ):
            raise ValueError("knowledge conflict status and evidence must agree")
