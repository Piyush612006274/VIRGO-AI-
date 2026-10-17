"""Minimal metadata describing an operation outcome."""

from dataclasses import dataclass

from virgo.contracts.models.correlation import require_valid_correlation_id


@dataclass(frozen=True, slots=True)
class OperationResult:
    """Immutable provider-neutral operation outcome metadata."""

    succeeded: bool
    message: str | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        """Validate optional metadata when it is supplied."""
        if self.message is not None and not self.message.strip():
            raise ValueError("message must not be empty when provided")
        if self.correlation_id is not None:
            require_valid_correlation_id(self.correlation_id)
