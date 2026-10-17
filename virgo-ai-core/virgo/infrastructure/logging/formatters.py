"""Console and JSON-line formatters with explicit sensitive-field redaction."""

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Final, cast

SENSITIVE_FIELD_NAMES: Final = frozenset(
    {"api_key", "authorization", "password", "secret", "token"}
)
REDACTED_VALUE: Final = "[REDACTED]"


def redact_sensitive_fields(fields: Mapping[str, object]) -> dict[str, object]:
    """Copy structured fields while redacting known sensitive field names."""
    return {
        key: (
            REDACTED_VALUE
            if key.lower() in SENSITIVE_FIELD_NAMES
            else _redact_value(value)
        )
        for key, value in fields.items()
    }


def _redact_value(value: object) -> object:
    if isinstance(value, Mapping):
        return redact_sensitive_fields({str(key): item for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    return value


class JsonLineFormatter(logging.Formatter):
    """Format developer logs as one deterministic JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "message": record.getMessage(),
        }
        correlation_id = cast(object, getattr(record, "correlation_id", None))
        if isinstance(correlation_id, str) and correlation_id:
            payload["correlation_id"] = correlation_id
        fields = cast(object, getattr(record, "fields", None))
        if isinstance(fields, Mapping):
            string_fields = {str(key): value for key, value in fields.items()}
            payload["fields"] = redact_sensitive_fields(string_fields)
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class ConsoleFormatter(logging.Formatter):
    """Readable console formatter with optional correlation context."""

    def format(self, record: logging.LogRecord) -> str:
        prefix = f"{self.formatTime(record)} {record.levelname} {record.name}"
        correlation_id = cast(object, getattr(record, "correlation_id", None))
        if isinstance(correlation_id, str) and correlation_id:
            prefix = f"{prefix} [{correlation_id}]"
        message = f"{prefix}: {record.getMessage()}"
        if record.exc_info is not None:
            message = f"{message}\n{self.formatException(record.exc_info)}"
        return message
