"""Small deterministic registry for independently testable checks."""

from virgo.contracts.errors import ValidationError
from virgo.contracts.protocols.security_check import SecurityCheckProtocol


class SecurityCheckRegistry:
    def __init__(self, checks: tuple[SecurityCheckProtocol, ...] = ()) -> None:
        self._checks: dict[str, SecurityCheckProtocol] = {}
        for check in checks:
            self.register(check)

    def register(self, check: SecurityCheckProtocol) -> None:
        check_id = getattr(check, "check_id", "")
        if not check_id or check_id in self._checks:
            raise ValidationError(
                "Security check identifier is invalid or duplicated",
                source_module=__name__,
            )
        self._checks[check_id] = check

    def selected(self, requested: tuple[str, ...]) -> tuple[SecurityCheckProtocol, ...]:
        if not requested:
            return tuple(self._checks.values())
        unknown = set(requested) - self._checks.keys()
        if unknown:
            raise ValidationError(
                "Unknown security check requested", source_module=__name__
            )
        return tuple(self._checks[item] for item in requested)
