"""Immutable contracts for local sessions, history, and runtime preferences."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from virgo.contracts.models.correlation import (
    new_correlation_id,
    require_valid_correlation_id,
)


def utc_now() -> datetime:
    """Return a timezone-aware current UTC timestamp."""
    return datetime.now(UTC)


def _require_utc(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must be a timezone-aware UTC datetime")


class SessionMessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True, kw_only=True)
class Session:
    session_id: str
    created_at: datetime
    updated_at: datetime
    title: str | None = None
    archived_at: datetime | None = None

    def __post_init__(self) -> None:
        require_valid_correlation_id(self.session_id)
        _require_utc(self.created_at, "created_at")
        _require_utc(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        if self.title is not None:
            if not isinstance(self.title, str) or not self.title.strip():
                raise ValueError("title must be non-empty when supplied")
            object.__setattr__(self, "title", self.title.strip())
        if self.archived_at is not None:
            _require_utc(self.archived_at, "archived_at")

    @classmethod
    def create(cls, *, title: str | None = None) -> "Session":
        timestamp = utc_now()
        return cls(
            session_id=new_correlation_id(),
            created_at=timestamp,
            updated_at=timestamp,
            title=title,
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "title": self.title,
            "archived_at": (
                None if self.archived_at is None else self.archived_at.isoformat()
            ),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class StorageUsage:
    session_bytes: int
    memory_bytes: int
    active_sessions: int
    archived_sessions: int
    cleanup_session_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            min(
                self.session_bytes,
                self.memory_bytes,
                self.active_sessions,
                self.archived_sessions,
            )
            < 0
        ):
            raise ValueError("storage usage values must not be negative")

    @property
    def total_bytes(self) -> int:
        return self.session_bytes + self.memory_bytes


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionMessage:
    message_id: str
    session_id: str
    role: SessionMessageRole
    text: str
    created_at: datetime
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        require_valid_correlation_id(self.message_id)
        require_valid_correlation_id(self.session_id)
        if not isinstance(self.role, SessionMessageRole):
            raise ValueError("role must be a SessionMessageRole")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("text must not be empty")
        object.__setattr__(self, "text", self.text.strip())
        _require_utc(self.created_at, "created_at")
        if self.correlation_id is not None:
            require_valid_correlation_id(self.correlation_id)

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        role: SessionMessageRole,
        text: str,
        correlation_id: str | None = None,
    ) -> "SessionMessage":
        return cls(
            message_id=new_correlation_id(),
            session_id=session_id,
            role=role,
            text=text,
            created_at=utc_now(),
            correlation_id=correlation_id,
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "message_id": self.message_id,
            "session_id": self.session_id,
            "role": self.role.value,
            "text": self.text,
            "created_at": self.created_at.isoformat(),
            "correlation_id": self.correlation_id,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class PersistedSettings:
    microphone_device_id: int | None = None
    output_device_id: int | None = None
    local_llm_model: str | None = None
    tts_voice: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("microphone_device_id", self.microphone_device_id),
            ("output_device_id", self.output_device_id),
        ):
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative integer")
        for field_name, text_value in (
            ("local_llm_model", self.local_llm_model),
            ("tts_voice", self.tts_voice),
        ):
            if text_value is not None:
                if not isinstance(text_value, str) or not text_value.strip():
                    raise ValueError(f"{field_name} must be non-empty")
                object.__setattr__(self, field_name, text_value.strip())

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "microphone_device_id": self.microphone_device_id,
            "output_device_id": self.output_device_id,
            "local_llm_model": self.local_llm_model,
            "tts_voice": self.tts_voice,
        }
