"""Typed immutable single-turn conversation events."""

from dataclasses import dataclass
from typing import ClassVar

from virgo.contracts.events.base import ApplicationEvent, EventDictionary
from virgo.contracts.models import (
    ConversationInput,
    ConversationResponse,
    ConversationStreamChunk,
    ErrorInfo,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ConversationStartedEvent(ApplicationEvent):
    conversation_input: ConversationInput
    model: str

    EVENT_NAME: ClassVar[str] = "conversation_started"

    def __post_init__(self) -> None:
        ApplicationEvent.__post_init__(self)
        if not isinstance(self.conversation_input, ConversationInput):
            raise ValueError("conversation_input must be a ConversationInput")
        if not self.model.strip():
            raise ValueError("model must not be empty")

    def to_dict(self) -> EventDictionary:
        serialized = ApplicationEvent.to_dict(self)
        serialized["conversation_input"] = self.conversation_input.to_dict()
        serialized["model"] = self.model
        return serialized


@dataclass(frozen=True, slots=True, kw_only=True)
class ConversationChunkEvent(ApplicationEvent):
    chunk: ConversationStreamChunk

    EVENT_NAME: ClassVar[str] = "conversation_chunk"

    def __post_init__(self) -> None:
        ApplicationEvent.__post_init__(self)
        if not isinstance(self.chunk, ConversationStreamChunk):
            raise ValueError("chunk must be a ConversationStreamChunk")

    def to_dict(self) -> EventDictionary:
        serialized = ApplicationEvent.to_dict(self)
        serialized["chunk"] = self.chunk.to_dict()
        return serialized


@dataclass(frozen=True, slots=True, kw_only=True)
class ConversationCompletedEvent(ApplicationEvent):
    response: ConversationResponse

    EVENT_NAME: ClassVar[str] = "conversation_completed"

    def __post_init__(self) -> None:
        ApplicationEvent.__post_init__(self)
        if (
            not isinstance(self.response, ConversationResponse)
            or not self.response.completed
        ):
            raise ValueError("response must be a completed ConversationResponse")

    def to_dict(self) -> EventDictionary:
        serialized = ApplicationEvent.to_dict(self)
        serialized["response"] = self.response.to_dict()
        return serialized


@dataclass(frozen=True, slots=True, kw_only=True)
class ConversationFailedEvent(ApplicationEvent):
    error: ErrorInfo

    EVENT_NAME: ClassVar[str] = "conversation_failed"

    def __post_init__(self) -> None:
        ApplicationEvent.__post_init__(self)
        if not isinstance(self.error, ErrorInfo):
            raise ValueError("error must be an ErrorInfo")

    def to_dict(self) -> EventDictionary:
        serialized = ApplicationEvent.to_dict(self)
        serialized["error"] = self.error.to_dict()
        return serialized


@dataclass(frozen=True, slots=True, kw_only=True)
class ConversationCancelledEvent(ApplicationEvent):
    response: ConversationResponse

    EVENT_NAME: ClassVar[str] = "conversation_cancelled"

    def __post_init__(self) -> None:
        ApplicationEvent.__post_init__(self)
        if (
            not isinstance(self.response, ConversationResponse)
            or self.response.completed
        ):
            raise ValueError("response must be an incomplete ConversationResponse")

    def to_dict(self) -> EventDictionary:
        serialized = ApplicationEvent.to_dict(self)
        serialized["response"] = self.response.to_dict()
        return serialized
