"""Immutable safe provider-health and diagnostic contracts."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite

from virgo.contracts.models.correlation import require_valid_correlation_id
from virgo.contracts.models.error_info import ErrorInfo

APPLICATION_STATES = frozenset(
    {
        "idle",
        "listening",
        "processing_speech",
        "thinking",
        "responding",
        "speaking",
        "interrupted",
        "recovering",
        "error",
        "offline",
    }
)


class ProviderHealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class ProviderComponentType(StrEnum):
    STT = "stt"
    LLM = "llm"
    TTS = "tts"
    AUDIO_INPUT = "audio_input"
    AUDIO_OUTPUT = "audio_output"
    STORAGE = "storage"
    RUST_CORE = "rust_core"


def _require_utc(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must be a timezone-aware UTC datetime")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderHealthResult:
    provider_name: str
    component_type: ProviderComponentType
    status: ProviderHealthStatus
    message: str
    checked_at: datetime
    latency_seconds: float | None = None
    selected_resource: str | None = None
    available_count: int | None = None
    recoverable: bool = False
    error: ErrorInfo | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("provider_name", self.provider_name),
            ("message", self.message),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")
            object.__setattr__(self, field_name, value.strip())
        if not isinstance(self.component_type, ProviderComponentType):
            raise ValueError("component_type must be a ProviderComponentType")
        if not isinstance(self.status, ProviderHealthStatus):
            raise ValueError("status must be a ProviderHealthStatus")
        _require_utc(self.checked_at, "checked_at")
        if self.latency_seconds is not None and (
            not isinstance(self.latency_seconds, int | float)
            or isinstance(self.latency_seconds, bool)
            or not isfinite(self.latency_seconds)
            or self.latency_seconds < 0
        ):
            raise ValueError("latency_seconds must be non-negative")
        if self.selected_resource is not None:
            if not self.selected_resource.strip():
                raise ValueError("selected_resource must not be empty")
            object.__setattr__(
                self, "selected_resource", self.selected_resource.strip()
            )
        if self.available_count is not None and (
            not isinstance(self.available_count, int)
            or isinstance(self.available_count, bool)
            or self.available_count < 0
        ):
            raise ValueError("available_count must be a non-negative integer")
        if not isinstance(self.recoverable, bool):
            raise ValueError("recoverable must be a bool")
        if self.error is not None and not isinstance(self.error, ErrorInfo):
            raise ValueError("error must be an ErrorInfo")
        if self.correlation_id is not None:
            require_valid_correlation_id(self.correlation_id)

    def to_dict(self) -> dict[str, object]:
        safe_error = None
        if self.error is not None:
            safe_error = {
                "code": self.error.code.value,
                "category": self.error.category.value,
                "user_safe_explanation": self.error.user_safe_explanation,
                "recoverable": self.error.recoverable,
                "correlation_id": self.error.correlation_id,
            }
        return {
            "provider_name": self.provider_name,
            "component_type": self.component_type.value,
            "status": self.status.value,
            "message": self.message,
            "checked_at": self.checked_at.isoformat(),
            "latency_seconds": self.latency_seconds,
            "selected_resource": self.selected_resource,
            "available_count": self.available_count,
            "recoverable": self.recoverable,
            "error": safe_error,
            "correlation_id": self.correlation_id,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class DiagnosticReport:
    application_version: str
    python_version: str
    platform: str
    rust_core_status: str
    application_state: str
    checked_at: datetime
    health_results: tuple[ProviderHealthResult, ...]

    def __post_init__(self) -> None:
        for field_name, value in (
            ("application_version", self.application_version),
            ("python_version", self.python_version),
            ("platform", self.platform),
            ("rust_core_status", self.rust_core_status),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.application_state not in APPLICATION_STATES:
            raise ValueError("application_state must be a known application state")
        _require_utc(self.checked_at, "checked_at")
        if not all(
            isinstance(result, ProviderHealthResult) for result in self.health_results
        ):
            raise ValueError("health_results must contain ProviderHealthResult values")

    def to_dict(self) -> dict[str, object]:
        return {
            "application_version": self.application_version,
            "python_version": self.python_version,
            "platform": self.platform,
            "rust_core_status": self.rust_core_status,
            "application_state": self.application_state,
            "checked_at": self.checked_at.isoformat(),
            "health_results": [result.to_dict() for result in self.health_results],
        }
