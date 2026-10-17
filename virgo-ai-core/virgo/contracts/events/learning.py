"""Metadata-only controlled-learning events."""

from dataclasses import dataclass
from typing import ClassVar

from virgo.contracts.events.base import ApplicationEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeGapDetectedEvent(ApplicationEvent):
    gap_id: str
    topic: str
    status: str
    EVENT_NAME: ClassVar[str] = "knowledge_gap_detected"


@dataclass(frozen=True, slots=True, kw_only=True)
class LearningProposalReadyEvent(ApplicationEvent):
    proposal_id: str
    source_count: int
    claim_count: int
    disputed_count: int
    EVENT_NAME: ClassVar[str] = "learning_proposal_ready"


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeAcceptedEvent(ApplicationEvent):
    proposal_id: str
    accepted_count: int
    EVENT_NAME: ClassVar[str] = "knowledge_accepted"


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfInspectionStartedEvent(ApplicationEvent):
    request_id: str
    category_count: int
    EVENT_NAME: ClassVar[str] = "self_inspection_started"


@dataclass(frozen=True, slots=True, kw_only=True)
class ImprovementProposalReadyEvent(ApplicationEvent):
    request_id: str
    proposal_count: int
    EVENT_NAME: ClassVar[str] = "improvement_proposal_ready"


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfInspectionCompletedEvent(ApplicationEvent):
    request_id: str
    finding_count: int
    cancelled: bool
    mutation_performed: bool
    EVENT_NAME: ClassVar[str] = "self_inspection_completed"


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfImprovementApprovalRequiredEvent(ApplicationEvent):
    task_id: str
    risk: str
    target_count: int
    EVENT_NAME: ClassVar[str] = "self_improvement_approval_required"


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfImprovementAppliedEvent(ApplicationEvent):
    task_id: str
    branch: str
    target_count: int
    EVENT_NAME: ClassVar[str] = "self_improvement_applied"


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfImprovementAcceptedEvent(ApplicationEvent):
    task_id: str
    commit_hash: str
    EVENT_NAME: ClassVar[str] = "self_improvement_accepted"


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfImprovementRolledBackEvent(ApplicationEvent):
    task_id: str
    reason: str
    hashes_restored: bool
    EVENT_NAME: ClassVar[str] = "self_improvement_rolled_back"
