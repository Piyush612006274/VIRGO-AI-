"""Protocol for implementation-neutral structured error serialization."""

from typing import Protocol, runtime_checkable

from virgo.contracts.models.error_info import ErrorDictionary


@runtime_checkable
class SerializableErrorProtocol(Protocol):
    """A value that exposes the canonical safe error dictionary."""

    def to_dict(self) -> ErrorDictionary:
        """Return the canonical declared error fields."""
        ...
