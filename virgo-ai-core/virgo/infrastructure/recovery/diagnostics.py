"""In-memory safe diagnostic aggregation without telemetry or file output."""

from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from platform import platform, python_version

from virgo.application.state_store import ApplicationStateStore
from virgo.contracts.errors import UnknownInternalError
from virgo.contracts.models import (
    DiagnosticReport,
    ProviderHealthResult,
    ProviderHealthStatus,
)
from virgo.infrastructure.recovery.health import HealthCheckProtocol


class DiagnosticService:
    def __init__(
        self,
        health_checks: tuple[HealthCheckProtocol, ...],
        rust_status: Callable[[], str],
        state_store: ApplicationStateStore,
    ) -> None:
        self._health_checks = health_checks
        self._rust_status = rust_status
        self._state_store = state_store

    def collect(self) -> DiagnosticReport:
        results: list[ProviderHealthResult] = []
        for check in self._health_checks:
            try:
                results.append(check.check())
            except Exception as error:
                failure = UnknownInternalError(
                    "Health check failed unexpectedly",
                    technical_detail=f"{type(error).__name__}: {error}",
                    source_module=__name__,
                    cause=error,
                )
                results.append(
                    ProviderHealthResult(
                        provider_name=check.provider_name,
                        component_type=check.component_type,
                        status=ProviderHealthStatus.UNKNOWN,
                        message=failure.user_safe_explanation,
                        checked_at=datetime.now(UTC),
                        recoverable=False,
                        error=failure.error_info,
                        correlation_id=failure.error_info.correlation_id,
                    )
                )
        try:
            rust_core_status = self._rust_status()
        except Exception:
            rust_core_status = "unavailable"
        return DiagnosticReport(
            application_version=_application_version(),
            python_version=python_version(),
            platform=platform(),
            rust_core_status=rust_core_status,
            application_state=self._state_store.snapshot.state.value,
            checked_at=datetime.now(UTC),
            health_results=tuple(results),
        )


def _application_version() -> str:
    try:
        return version("virgo-ai")
    except PackageNotFoundError:
        return "development"
