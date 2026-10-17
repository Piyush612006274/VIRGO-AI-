"""Local generation and validation of opaque correlation identifiers."""

from uuid import UUID, uuid4


def new_correlation_id() -> str:
    """Return a locally generated canonical UUID correlation identifier."""
    return str(uuid4())


def is_valid_correlation_id(value: str) -> bool:
    """Return whether *value* is a canonical UUID string."""
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        return False
    return str(parsed) == value


def require_valid_correlation_id(value: str) -> None:
    """Raise ``ValueError`` when *value* is not a canonical UUID string."""
    if not is_valid_correlation_id(value):
        raise ValueError("correlation_id must be a canonical UUID string")
