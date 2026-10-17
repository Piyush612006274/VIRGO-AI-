"""Immutable base contract for in-process application events."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar

from virgo.contracts.models import is_valid_correlation_id, new_correlation_id

EventDictionary = dict[str, object]


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplicationEvent:
    """Common identity and provenance shared by all application events."""

    event_id: str = field(default_factory=new_correlation_id)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str | None = None
    source_module: str | None = None

    EVENT_NAME: ClassVar[str] = "application_event"

    def __post_init__(self) -> None:
        """Validate portable event metadata without external side effects."""
        if not is_valid_correlation_id(self.event_id):
            raise ValueError("event_id must be a canonical UUID string")
        if (
            self.created_at.tzinfo is None
            or self.created_at.utcoffset() != UTC.utcoffset(self.created_at)
        ):
            raise ValueError("created_at must use the UTC timezone")
        if self.correlation_id is not None and not is_valid_correlation_id(
            self.correlation_id
        ):
            raise ValueError("correlation_id must be a canonical UUID string")
        if self.source_module is not None and not self.source_module.strip():
            raise ValueError("source_module must not be empty when provided")

    @property
    def event_name(self) -> str:
        """Return the stable machine-readable event name."""
        return self.EVENT_NAME

    def to_dict(self) -> EventDictionary:
        """Serialize only declared event metadata."""
        return {
            "event_id": self.event_id,
            "event_name": self.event_name,
            "created_at": self.created_at.isoformat(),
            "correlation_id": self.correlation_id,
            "source_module": self.source_module,
        }
