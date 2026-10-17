"""Immutable single-turn conversation contracts."""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from virgo.contracts.models.correlation import require_valid_correlation_id
from virgo.contracts.models.personal_runtime import MemoryCandidate

ConversationDictionary = dict[str, str | bool | float | int | None]


class ConversationInputSource(StrEnum):
    """Supported sources for one conversation turn."""

    TEXT = "text"
    STT = "stt"


class ConversationIntent(StrEnum):
    CONVERSE = "converse"
    CORRECT = "correct"
    STOP = "stop"
    CHANGE_PREFERENCE = "change_preference"
    CONTINUE_TASK = "continue_task"


class ConversationAct(StrEnum):
    REQUEST = "request"
    CORRECTION = "correction"
    REFERENCE = "reference"
    CLARIFICATION_RESPONSE = "clarification_response"


class IntentEvidence(StrEnum):
    EXPLICIT = "explicit"
    RULE_MATCH = "rule_match"
    DEFAULT = "default"


class InteractionState(StrEnum):
    NEUTRAL = "neutral"
    CORRECTING = "correcting"
    REPEATED = "repeated"
    URGENT = "urgent"
    FRUSTRATED = "frustrated"
    HESITANT = "hesitant"


class ConversationUrgency(StrEnum):
    NORMAL = "normal"
    HIGH = "high"


class ResponseStyle(StrEnum):
    CONCISE = "concise"
    NORMAL = "normal"
    DETAILED = "detailed"
    STEP_BY_STEP = "step_by_step"
    CLARIFYING = "clarifying"
    ACKNOWLEDGE_AND_CORRECT = "acknowledge_and_correct"
    URGENT_DIRECT = "urgent_direct"


@dataclass(frozen=True, slots=True, kw_only=True)
class ConversationReference:
    reference_id: str
    text: str
    kind: str = "turn"

    def __post_init__(self) -> None:
        for value, name in (
            (self.reference_id, "reference_id"),
            (self.text, "text"),
            (self.kind, "kind"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")


@dataclass(frozen=True, slots=True, kw_only=True)
class ConversationUnderstandingContext:
    references: tuple[ConversationReference, ...] = ()
    active_task_id: str | None = None
    session_id: str | None = None
    language_preference: str | None = None
    communication_preference: str | None = None

    def __post_init__(self) -> None:
        if len(self.references) > 5:
            raise ValueError("conversation references must be bounded to five")


@dataclass(frozen=True, slots=True, kw_only=True)
class ConversationUnderstanding:
    intent: ConversationIntent
    intent_evidence: IntentEvidence
    act: ConversationAct
    interaction_state: InteractionState
    urgency: ConversationUrgency
    response_style: ResponseStyle
    correction_reference_id: str | None = None
    resolved_reference_id: str | None = None
    needs_clarification: bool = False
    task_id: str | None = None
    session_id: str | None = None
    preference_candidate: MemoryCandidate | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ConversationInput:
    """One normalized user input without history or provider details."""

    text: str
    source: ConversationInputSource = ConversationInputSource.TEXT
    system_instruction: str | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("text must not be empty")
        object.__setattr__(self, "text", " ".join(self.text.split()))
        if not isinstance(self.source, ConversationInputSource):
            raise ValueError("source must be a ConversationInputSource")
        if self.system_instruction is not None:
            normalized_system = self.system_instruction.strip()
            if not normalized_system:
                raise ValueError("system_instruction must not be empty when provided")
            object.__setattr__(self, "system_instruction", normalized_system)
        if self.correlation_id is not None:
            require_valid_correlation_id(self.correlation_id)

    def to_dict(self) -> ConversationDictionary:
        return {
            "text": self.text,
            "source": self.source.value,
            "system_instruction": self.system_instruction,
            "correlation_id": self.correlation_id,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ConversationResponse:
    """One final or safely interrupted single-turn response."""

    user_input_text: str
    assistant_text: str
    model: str
    provider: str
    correlation_id: str
    completed: bool
    generation_duration_seconds: float | None = None
    prompt_token_count: int | None = None
    completion_token_count: int | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.user_input_text, str)
            or not self.user_input_text.strip()
        ):
            raise ValueError("user_input_text must not be empty")
        if not isinstance(self.assistant_text, str) or (
            self.completed and not self.assistant_text.strip()
        ):
            raise ValueError("completed responses require assistant text")
        for field_name, value in (("model", self.model), ("provider", self.provider)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        require_valid_correlation_id(self.correlation_id)
        if not isinstance(self.completed, bool):
            raise ValueError("completed must be a boolean")
        if self.generation_duration_seconds is not None and (
            not isfinite(self.generation_duration_seconds)
            or self.generation_duration_seconds < 0
        ):
            raise ValueError("generation_duration_seconds must be non-negative")
        for field_name, count in (
            ("prompt_token_count", self.prompt_token_count),
            ("completion_token_count", self.completion_token_count),
        ):
            if count is not None and (not isinstance(count, int) or count < 0):
                raise ValueError(f"{field_name} must be a non-negative integer")

    def to_dict(self) -> ConversationDictionary:
        return {
            "user_input_text": self.user_input_text,
            "assistant_text": self.assistant_text,
            "model": self.model,
            "provider": self.provider,
            "correlation_id": self.correlation_id,
            "completed": self.completed,
            "generation_duration_seconds": self.generation_duration_seconds,
            "prompt_token_count": self.prompt_token_count,
            "completion_token_count": self.completion_token_count,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ConversationStreamChunk:
    """One exact provider delta exposed by the conversation layer."""

    text_delta: str
    done: bool
    correlation_id: str
    model: str

    def __post_init__(self) -> None:
        if not isinstance(self.text_delta, str) or (
            not self.text_delta and not self.done
        ):
            raise ValueError("text_delta must not be empty before completion")
        if not isinstance(self.done, bool):
            raise ValueError("done must be a boolean")
        require_valid_correlation_id(self.correlation_id)
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("model must not be empty")

    def to_dict(self) -> ConversationDictionary:
        return {
            "text_delta": self.text_delta,
            "done": self.done,
            "correlation_id": self.correlation_id,
            "model": self.model,
        }
