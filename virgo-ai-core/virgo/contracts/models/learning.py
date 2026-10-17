"""Typed, local-first contracts for controlled learning."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from virgo.contracts.models.correlation import new_correlation_id


class KnowledgeGapStatus(StrEnum):
    KNOWN = "known"
    INSUFFICIENT_KNOWLEDGE = "insufficient_knowledge"
    CONFLICTING_KNOWLEDGE = "conflicting_knowledge"
    OUTDATED_KNOWLEDGE = "outdated_knowledge"
    UNKNOWN = "unknown"


class LearningSourceType(StrEnum):
    USER_DOCUMENT = "user_document"
    WEBSITE = "website"
    GITHUB_REPOSITORY = "github_repository"
    TECHNICAL_DOCUMENTATION = "technical_documentation"
    TASK_OUTCOME = "task_outcome"
    CORRECTED_RESPONSE = "corrected_response"
    VALIDATED_SKILL = "validated_skill"
    EDUCATIONAL_TRANSCRIPT = "educational_transcript"


class ResearchDecision(StrEnum):
    ALLOW_ONCE = "allow_once"
    ALLOW_FOR_CURRENT_RESEARCH_TASK = "allow_for_current_research_task"
    DENY = "deny"
    MODIFY_SCOPE = "modify_scope"


class KnowledgeScope(StrEnum):
    GLOBAL = "global"
    USER = "user"
    PROJECT = "project"
    SESSION = "session"
    TASK = "task"
    SKILL = "skill"


class PrivacyClassification(StrEnum):
    PUBLIC = "public"
    USER_PRIVATE = "user_private"
    PROJECT_PRIVATE = "project_private"
    SENSITIVE = "sensitive"


class ClaimStatus(StrEnum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    REJECTED = "rejected"
    OUTDATED = "outdated"
    SUPERSEDED = "superseded"


class QualityDecision(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    UNCERTAIN = "uncertain"
    DISPUTED = "disputed"


class ResearchProviderStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"
    AVAILABLE = "available"


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeGap:
    topic: str
    question: str
    status: KnowledgeGapStatus
    reason: str
    gap_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        _text(self.topic, "topic")
        _text(self.question, "question")
        _text(self.reason, "reason")


@dataclass(frozen=True, slots=True, kw_only=True)
class ResearchScope:
    topic: str
    source_types: tuple[LearningSourceType, ...]
    allowed_origins: tuple[str, ...] = ()
    network_allowed: bool = False
    persist_allowed: bool = False
    max_sources: int = 5
    max_bytes: int = 200_000
    max_claims: int = 50
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        _text(self.topic, "topic")
        if not self.source_types or not 1 <= self.max_sources <= 10:
            raise ValueError("research scope requires 1-10 source types/sources")
        if not 1 <= self.max_bytes <= 1_000_000 or not 1 <= self.max_claims <= 100:
            raise ValueError("research content and claim limits are invalid")
        if not 0 < self.timeout_seconds <= 120:
            raise ValueError("research timeout must be within 120 seconds")
        if not self.network_allowed and any(
            item in {LearningSourceType.WEBSITE, LearningSourceType.GITHUB_REPOSITORY}
            for item in self.source_types
        ):
            raise ValueError("network source types require explicit network scope")


@dataclass(frozen=True, slots=True, kw_only=True)
class ResearchPermissionRequest:
    topic: str
    question: str
    reason: str
    scope: ResearchScope
    sensitivity: PrivacyClassification
    task_id: str = field(default_factory=new_correlation_id)
    permission_id: str = field(default_factory=new_correlation_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "permission_id": self.permission_id,
            "task_id": self.task_id,
            "topic": self.topic,
            "question": self.question,
            "reason": self.reason,
            "source_types": [item.value for item in self.scope.source_types],
            "network_required": self.scope.network_allowed,
            "persist_allowed": self.scope.persist_allowed,
            "sensitivity": self.sensitivity.value,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class LearningSource:
    source_type: LearningSourceType
    origin: str
    approved: bool
    content_hash: str | None
    authority: float
    sensitivity: PrivacyClassification
    provenance: str
    source_id: str = field(default_factory=new_correlation_id)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        _text(self.origin, "origin")
        _text(self.provenance, "provenance")
        if (
            "://" in self.origin
            and "@" in self.origin.split("://", 1)[1].split("/", 1)[0]
        ):
            raise ValueError("source origin must not contain credentials")
        _confidence(self.authority)
        if self.content_hash is not None and len(self.content_hash) != 64:
            raise ValueError("content_hash must be SHA-256")

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type.value,
            "origin": self.origin,
            "approved": self.approved,
            "content_hash": self.content_hash,
            "authority": self.authority,
            "sensitivity": self.sensitivity.value,
            "provenance": self.provenance,
            "retrieved_at": self.retrieved_at.isoformat(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class Evidence:
    source_id: str
    excerpt: str
    direct: bool
    relevant: bool = True
    evidence_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        _text(self.source_id, "source_id")
        _text(self.excerpt, "excerpt")
        if len(self.excerpt) > 500:
            raise ValueError("evidence excerpt is too large")


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeClaim:
    statement: str
    topic: str
    evidence_ids: tuple[str, ...]
    confidence: float
    status: ClaimStatus
    scope: KnowledgeScope
    scope_key: str
    privacy: PrivacyClassification
    provenance: str
    claim_id: str = field(default_factory=new_correlation_id)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_verified_at: datetime | None = None
    supersedes: str | None = None
    superseded_by: str | None = None

    def __post_init__(self) -> None:
        _text(self.statement, "statement")
        _text(self.topic, "topic")
        _text(self.scope_key, "scope_key")
        _text(self.provenance, "provenance")
        _confidence(self.confidence)
        if self.status is ClaimStatus.VERIFIED and not self.evidence_ids:
            raise ValueError("verified claims require evidence provenance")


@dataclass(frozen=True, slots=True, kw_only=True)
class QualityEvaluation:
    decision: QualityDecision
    confidence: float
    reasons: tuple[str, ...]
    duplicate: bool = False
    contradictory: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class LearningProposal:
    claims: tuple[KnowledgeClaim, ...]
    sources: tuple[LearningSource, ...]
    evidence: tuple[Evidence, ...]
    evaluations: tuple[QualityEvaluation, ...]
    contradictions: tuple[str, ...]
    intended_persistence: bool
    proposal_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        if not self.claims or len(self.claims) != len(self.evaluations):
            raise ValueError("learning proposal requires evaluated claims")


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskOutcomeLearningCandidate:
    task_id: str
    outcome: str
    lesson: str
    scope: KnowledgeScope
    reusable: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class SkillCandidate:
    name: str
    guidance: tuple[str, ...]
    source_claim_ids: tuple[str, ...]
    executable: bool = False
    permissions_mutable: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class EvaluationExample:
    input_text: str
    expected_behavior: str
    source_claim_ids: tuple[str, ...]


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")


def _confidence(value: float) -> None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not 0 <= value <= 1
    ):
        raise ValueError("confidence/authority must be between zero and one")
