"""Metadata-safe Stage 3 security events."""

from dataclasses import dataclass
from typing import ClassVar

from virgo.contracts.events.base import ApplicationEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityAnalysisStartedEvent(ApplicationEvent):
    analysis_id: str
    target_type: str
    check_count: int
    EVENT_NAME: ClassVar[str] = "security_analysis_started"

    def to_dict(self) -> dict[str, object]:
        value = super().to_dict()
        value.update(
            analysis_id=self.analysis_id,
            target_type=self.target_type,
            check_count=self.check_count,
        )
        return value


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityFindingDetectedEvent(ApplicationEvent):
    analysis_id: str
    finding_id: str
    severity: str
    category: str
    affected_path: str
    EVENT_NAME: ClassVar[str] = "security_finding_detected"

    def to_dict(self) -> dict[str, object]:
        value = super().to_dict()
        value.update(
            analysis_id=self.analysis_id,
            finding_id=self.finding_id,
            severity=self.severity,
            category=self.category,
            affected_path=self.affected_path,
        )
        return value


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityAnalysisCompletedEvent(ApplicationEvent):
    analysis_id: str
    finding_count: int
    cancelled: bool
    EVENT_NAME: ClassVar[str] = "security_analysis_completed"

    def to_dict(self) -> dict[str, object]:
        value = super().to_dict()
        value.update(
            analysis_id=self.analysis_id,
            finding_count=self.finding_count,
            cancelled=self.cancelled,
        )
        return value


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityAnalysisFailedEvent(ApplicationEvent):
    analysis_id: str
    error_type: str
    EVENT_NAME: ClassVar[str] = "security_analysis_failed"

    def to_dict(self) -> dict[str, object]:
        value = super().to_dict()
        value.update(analysis_id=self.analysis_id, error_type=self.error_type)
        return value
