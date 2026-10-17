"""Immutable local language-model contracts."""

from dataclasses import dataclass
from math import isfinite

from virgo.contracts.models.correlation import require_valid_correlation_id

LLMRequestDictionary = dict[str, str | float | int | None]
LLMResponseDictionary = dict[str, str | bool | float | int | None]
LLMStreamChunkDictionary = dict[str, str | bool | None]


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMRequest:
    """One explicit local text-generation request."""

    prompt: str
    model: str
    system_instruction: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise ValueError("prompt must not be empty")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("model must not be empty")
        if self.system_instruction is not None and not self.system_instruction.strip():
            raise ValueError("system_instruction must not be empty when provided")
        if (
            not isinstance(self.temperature, int | float)
            or not isfinite(self.temperature)
            or not 0.0 <= self.temperature <= 2.0
        ):
            raise ValueError("temperature must be finite and between zero and two")
        if self.max_tokens is not None and (
            not isinstance(self.max_tokens, int) or self.max_tokens <= 0
        ):
            raise ValueError("max_tokens must be a positive integer when provided")
        if self.correlation_id is not None:
            require_valid_correlation_id(self.correlation_id)

    def to_dict(self) -> LLMRequestDictionary:
        return {
            "prompt": self.prompt,
            "model": self.model,
            "system_instruction": self.system_instruction,
            "temperature": float(self.temperature),
            "max_tokens": self.max_tokens,
            "correlation_id": self.correlation_id,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMResponse:
    """Backend-neutral completed local generation result."""

    text: str
    model: str
    provider: str
    completed: bool
    generation_duration_seconds: float | None = None
    prompt_token_count: int | None = None
    completion_token_count: int | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("text must not be empty")
        for field_name, value in (("model", self.model), ("provider", self.provider)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")
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
        if self.correlation_id is not None:
            require_valid_correlation_id(self.correlation_id)

    def to_dict(self) -> LLMResponseDictionary:
        return {
            "text": self.text,
            "model": self.model,
            "provider": self.provider,
            "completed": self.completed,
            "generation_duration_seconds": self.generation_duration_seconds,
            "prompt_token_count": self.prompt_token_count,
            "completion_token_count": self.completion_token_count,
            "correlation_id": self.correlation_id,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMStreamChunk:
    """One ordered provider-level text delta."""

    text_delta: str
    done: bool
    model: str
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text_delta, str) or (
            not self.text_delta and not self.done
        ):
            raise ValueError("text_delta must not be empty before completion")
        if not isinstance(self.done, bool):
            raise ValueError("done must be a boolean")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("model must not be empty")
        if self.correlation_id is not None:
            require_valid_correlation_id(self.correlation_id)

    def to_dict(self) -> LLMStreamChunkDictionary:
        return {
            "text_delta": self.text_delta,
            "done": self.done,
            "model": self.model,
            "correlation_id": self.correlation_id,
        }
