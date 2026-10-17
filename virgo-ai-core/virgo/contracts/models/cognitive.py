"""Immutable advisory contracts for bounded cognitive preparation."""

from dataclasses import dataclass
from enum import StrEnum

from virgo.contracts.models.conversation import ConversationUnderstanding
from virgo.contracts.models.personal_runtime import UserContext


class UncertaintyState(StrEnum):
    KNOWN = "known"
    LIKELY = "likely"
    UNKNOWN = "unknown"
    CONFLICTING = "conflicting"
    OUTDATED = "outdated"
    NEEDS_VERIFICATION = "needs_verification"


class CognitiveStrategy(StrEnum):
    RESPOND_DIRECTLY = "respond_directly"
    ASK_CLARIFICATION = "ask_clarification"
    USE_EXISTING_CONTEXT = "use_existing_context"
    USE_RELEVANT_MEMORY = "use_relevant_memory"
    REASON_WITH_CONFIGURED_MODEL = "reason_with_configured_model"
    REQUIRE_CURRENT_KNOWLEDGE = "require_current_knowledge"
    REQUIRE_CAPABILITY = "require_capability"
    WAIT_FOR_PERMISSION = "wait_for_permission"
    DECLINE_UNSUPPORTED_OR_UNSAFE = "decline_unsupported_or_unsafe"


class CognitiveTaskStatus(StrEnum):
    READY = "ready"
    WAITING_CLARIFICATION = "waiting_clarification"
    WAITING_PERMISSION = "waiting_permission"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True, kw_only=True)
class CognitiveContext:
    request: str
    understanding: ConversationUnderstanding
    user_context: UserContext
    recent_context: tuple[str, ...] = ()
    contextual_evidence: tuple[str, ...] = ()
    configured_models: tuple[str, ...] = ()
    working_scope: str | None = None

    def __post_init__(self) -> None:
        if not self.request.strip():
            raise ValueError("cognitive request must be non-empty")
        if len(self.recent_context) > 5 or len(self.contextual_evidence) > 5:
            raise ValueError("cognitive context exceeds attention budget")
        if self.working_scope is not None and not self.working_scope.strip():
            raise ValueError("cognitive working scope must be non-empty")


@dataclass(frozen=True, slots=True, kw_only=True)
class CognitivePlanStep:
    position: int
    purpose: str
    expected_outcome: str
    preconditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            self.position < 1
            or not self.purpose.strip()
            or not self.expected_outcome.strip()
        ):
            raise ValueError("cognitive plan step is invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class CognitiveDecision:
    task_id: str
    user_goal: str
    strategy: CognitiveStrategy
    uncertainty: UncertaintyState
    uncertainty_reason: str
    status: CognitiveTaskStatus
    context: CognitiveContext
    plan: tuple[CognitivePlanStep, ...] = ()
    selected_model: str | None = None
    requires_permission: bool = False
    stop_conditions: tuple[str, ...] = (
        "cancelled",
        "clarification required",
        "permission required",
        "unsupported capability required",
    )

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.user_goal.strip():
            raise ValueError("cognitive decision identity is invalid")
        if len(self.plan) > 5:
            raise ValueError("cognitive plan exceeds five steps")
