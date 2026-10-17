"""Typed immutable interruption request contract."""

from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic_ns
from typing import TypedDict

from virgo.contracts.models.correlation import require_valid_correlation_id


class InterruptionSource(StrEnum):
    """Explicit sources that may request cancellation of active work."""

    USER_ACTION = "user_action"
    MICROPHONE_CAPTURE = "microphone_capture"
    SYSTEM = "system"


class InterruptionRequestDictionary(TypedDict):
    correlation_id: str
    source: str
    reason: str
    monotonic_timestamp_ns: int


@dataclass(frozen=True, slots=True, kw_only=True)
class InterruptionRequest:
    """Identify one explicit request to stop the current operation."""

    correlation_id: str
    source: InterruptionSource
    reason: str
    monotonic_timestamp_ns: int = field(default_factory=monotonic_ns)

    def __post_init__(self) -> None:
        require_valid_correlation_id(self.correlation_id)
        if not isinstance(self.source, InterruptionSource):
            raise ValueError("source must be an InterruptionSource")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must not be empty")
        object.__setattr__(self, "reason", self.reason.strip())
        if (
            not isinstance(self.monotonic_timestamp_ns, int)
            or isinstance(self.monotonic_timestamp_ns, bool)
            or self.monotonic_timestamp_ns < 0
        ):
            raise ValueError("monotonic_timestamp_ns must be a non-negative integer")

    def to_dict(self) -> InterruptionRequestDictionary:
        return {
            "correlation_id": self.correlation_id,
            "source": self.source.value,
            "reason": self.reason,
            "monotonic_timestamp_ns": self.monotonic_timestamp_ns,
        }
