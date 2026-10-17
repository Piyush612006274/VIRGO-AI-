"""Immutable contracts for bounded personal-AI orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from virgo.contracts.models.verification import VerificationResult

from virgo.contracts.models.correlation import new_correlation_id
from virgo.contracts.models.learning import KnowledgeScope, PrivacyClassification


class PersonalCapability(StrEnum):
    CONVERSATION = "conversation"
    RESEARCH = "research"
    CODING = "coding"
    CREATION = "creation"
    PRODUCTIVITY = "productivity"
    SYSTEM_DIAGNOSTICS = "system_diagnostics"
    DEFENSIVE_SECURITY = "defensive_security"
    VERIFICATION = "verification"
    BROWSER = "browser"
    DESKTOP = "desktop"
    FILES = "files"
    VOICE = "voice"
    IMAGE = "image"
    VIDEO = "video"


class AgentType(StrEnum):
    RESEARCH = "research_agent"
    CODING = "coding_agent"
    CREATION = "creation_agent"
    PRODUCTIVITY = "productivity_agent"
    SYSTEM_DIAGNOSTIC = "system_diagnostic_agent"
    DEFENSIVE_SECURITY = "defensive_security_agent"
    VERIFICATION = "verification_agent"


class ActionRisk(StrEnum):
    READ_ONLY = "read_only"
    REVERSIBLE_MUTATION = "reversible_mutation"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    SENSITIVE = "sensitive"
    PROTECTED = "protected"


class RuntimeProviderStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"


class PersonalTaskStatus(StrEnum):
    PLANNED = "planned"
    PERMISSION_REQUIRED = "permission_required"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonalTaskBudget:
    max_agents: int = 4
    max_delegation_depth: int = 1
    max_steps: int = 8
    max_duration_seconds: float = 60.0
    max_research_sources: int = 5
    max_files: int = 20
    max_bytes: int = 200_000
    max_tool_calls: int = 8
    max_retries: int = 1

    def __post_init__(self) -> None:
        values = (
            self.max_agents,
            self.max_steps,
            self.max_research_sources,
            self.max_files,
            self.max_bytes,
            self.max_tool_calls,
        )
        if any(value < 1 for value in values):
            raise ValueError("task budget limits must be positive")
        if not 0 <= self.max_delegation_depth <= 1:
            raise ValueError("delegation depth must be zero or one")
        if not 0 <= self.max_retries <= 3 or self.max_duration_seconds <= 0:
            raise ValueError("retry and duration limits are invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonalTaskContext:
    session_id: str | None = None
    project_id: str | None = None
    workspace_root: str | None = None
    active_application: str | None = None
    privacy: PrivacyClassification = PrivacyClassification.USER_PRIVATE
    memory_scope: KnowledgeScope = KnowledgeScope.SESSION
    memory_scope_key: str = "current"
    retrieved_context: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.memory_scope_key, "memory_scope_key")
        if any(not item.strip() for item in self.retrieved_context):
            raise ValueError("retrieved context must contain non-empty text")


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonalTaskRequest:
    objective: str
    context: PersonalTaskContext = field(default_factory=PersonalTaskContext)
    budget: PersonalTaskBudget = field(default_factory=PersonalTaskBudget)
    input_source: str = "text"
    task_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        _text(self.objective, "objective")
        if self.input_source not in {"text", "voice"}:
            raise ValueError("input_source must be text or voice")


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonalTaskPermission:
    task_id: str
    capability: PersonalCapability
    purpose: str
    scope: str
    risk: ActionRisk
    permission_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        _text(self.task_id, "task_id")
        _text(self.purpose, "purpose")
        _text(self.scope, "scope")


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonalTaskStep:
    position: int
    agent: AgentType | None
    capability: PersonalCapability
    objective: str
    tool_ids: tuple[str, ...] = ()
    risk: ActionRisk = ActionRisk.READ_ONLY
    permission: PersonalTaskPermission | None = None

    def __post_init__(self) -> None:
        if self.position < 1:
            raise ValueError("step position must be positive")
        _text(self.objective, "objective")


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonalTaskPlan:
    task_id: str
    steps: tuple[PersonalTaskStep, ...]
    direct_response: bool = False
    clarification: str | None = None
    plan_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        if not self.steps and self.clarification is None:
            raise ValueError("task plan requires steps or clarification")
        if tuple(step.position for step in self.steps) != tuple(
            range(1, len(self.steps) + 1)
        ):
            raise ValueError("task plan steps must be contiguous")


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonalTaskVerification:
    verifier_agent_id: str
    producer_agent_id: str
    passed: bool
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.verifier_agent_id, "verifier_agent_id")
        _text(self.producer_agent_id, "producer_agent_id")
        if self.verifier_agent_id == self.producer_agent_id:
            raise ValueError("verification must be independent")


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonalTaskResult:
    task_id: str
    status: PersonalTaskStatus
    summary: str
    completed_steps: int
    provider_status: RuntimeProviderStatus | None = None
    verification: PersonalTaskVerification | VerificationResult | None = None
    audit: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentDefinition:
    agent_id: str
    agent_type: AgentType
    objective: str
    scope: tuple[PersonalCapability, ...]
    capability_allowlist: tuple[PersonalCapability, ...]
    tool_allowlist: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    verifier: AgentType

    def __post_init__(self) -> None:
        _text(self.agent_id, "agent_id")
        _text(self.objective, "objective")
        if self.agent_type is AgentType.VERIFICATION:
            raise ValueError("verification agent has a separate fixed definition")
        if not set(self.capability_allowlist) <= set(self.scope):
            raise ValueError("agent capability allowlist exceeds scope")


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeTool:
    tool_id: str
    capability: PersonalCapability
    risk: ActionRisk
    permission_required: bool
    availability: RuntimeProviderStatus
    provider: str
    input_contract: str
    output_contract: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonalPreference:
    key: str
    value: str
    scope_key: str
    provenance: str = "EXPLICIT_USER"

    def __post_init__(self) -> None:
        for value, name in (
            (self.key, "key"),
            (self.value, "value"),
            (self.scope_key, "scope_key"),
            (self.provenance, "provenance"),
        ):
            _text(value, name)


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievedMemory:
    statement: str
    topic: str
    scope: KnowledgeScope
    scope_key: str
    provenance: str
    claim_id: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.statement, "statement"),
            (self.topic, "topic"),
            (self.scope_key, "scope_key"),
            (self.provenance, "provenance"),
            (self.claim_id, "claim_id"),
        ):
            _text(value, name)


@dataclass(frozen=True, slots=True, kw_only=True)
class UserContext:
    scope_key: str
    preferences: tuple[PersonalPreference, ...] = ()
    memories: tuple[RetrievedMemory, ...] = ()

    def __post_init__(self) -> None:
        _text(self.scope_key, "scope_key")

    def preference(self, key: str) -> str | None:
        return next((item.value for item in self.preferences if item.key == key), None)


@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryCandidate:
    key: str
    value: str
    scope_key: str
    provenance: str
    reason: str
    explicit_user_request: bool = False

    def __post_init__(self) -> None:
        for value, name in (
            (self.key, "key"),
            (self.value, "value"),
            (self.scope_key, "scope_key"),
            (self.provenance, "provenance"),
            (self.reason, "reason"),
        ):
            _text(value, name)


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
