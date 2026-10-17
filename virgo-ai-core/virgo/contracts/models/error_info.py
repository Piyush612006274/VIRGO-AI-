"""Canonical structured error information shared across Virgo modules."""

from dataclasses import dataclass

from virgo.contracts.errors.codes import ErrorCategory, ErrorCode
from virgo.contracts.models.correlation import require_valid_correlation_id

ErrorDictionary = dict[str, str | bool | None]


@dataclass(frozen=True, slots=True)
class ErrorInfo:
    """Immutable, explicitly serializable error information."""

    code: ErrorCode
    category: ErrorCategory
    message: str
    technical_detail: str | None
    user_safe_explanation: str
    recoverable: bool
    retry_advice: str | None
    source_module: str
    correlation_id: str

    def __post_init__(self) -> None:
        """Validate fields required for safe cross-module use."""
        for field_name, value in (
            ("message", self.message),
            ("user_safe_explanation", self.user_safe_explanation),
            ("source_module", self.source_module),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        require_valid_correlation_id(self.correlation_id)

    def to_dict(self) -> ErrorDictionary:
        """Serialize only the declared error contract fields."""
        return {
            "code": self.code.value,
            "category": self.category.value,
            "message": self.message,
            "technical_detail": self.technical_detail,
            "user_safe_explanation": self.user_safe_explanation,
            "recoverable": self.recoverable,
            "retry_advice": self.retry_advice,
            "source_module": self.source_module,
            "correlation_id": self.correlation_id,
        }
