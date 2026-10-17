"""Authorized, bounded, read-only local security coordinator."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from threading import Event

from virgo.application import ApplicationStateStore
from virgo.capabilities.security.checks import (
    DangerousCodeCheck,
    DebugConfigurationCheck,
    DependencyManifestCheck,
    DynamicExecutionCheck,
    MalwareIndicatorCheck,
    PythonRiskPatternCheck,
    SecretCandidateCheck,
    SecurityConfigurationCheck,
    SelectedLogSecurityCheck,
)
from virgo.capabilities.security.registry import SecurityCheckRegistry
from virgo.contracts.errors import SecurityViolationError, ValidationError
from virgo.contracts.events import ApplicationState
from virgo.contracts.events.security import (
    SecurityAnalysisCompletedEvent,
    SecurityAnalysisFailedEvent,
    SecurityAnalysisStartedEvent,
    SecurityFindingDetectedEvent,
)
from virgo.contracts.models.security import (
    SecurityAnalysisPlan,
    SecurityAnalysisRequest,
    SecurityAnalysisResult,
    SecurityFinding,
    SecurityIntelligenceStatus,
    SecurityPermissionRequirement,
    SecurityProviderStatus,
)
from virgo.infrastructure.events import EventDispatcher
from virgo.infrastructure.filesystem import validate_workspace_path

EXCLUDED = {".git", ".venv", "__pycache__", "node_modules", "target", "data", "models"}
TEXT_EXTENSIONS = {
    ".py",
    ".toml",
    ".json",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".conf",
    ".env",
    ".txt",
    ".md",
    ".log",
    ".html",
    ".css",
    ".js",
    ".rs",
}
SENSITIVE_NAMES = {"credentials.json", "secrets.json", "id_rsa", "id_ed25519"}


class SecurityAnalysisCoordinator:
    def __init__(
        self,
        dispatcher: EventDispatcher,
        state_store: ApplicationStateStore,
        registry: SecurityCheckRegistry | None = None,
    ) -> None:
        self.dispatcher = dispatcher
        self.state_store = state_store
        self.registry = registry or SecurityCheckRegistry(
            (
                SecretCandidateCheck(),
                DangerousCodeCheck(),
                DebugConfigurationCheck(),
                DynamicExecutionCheck(),
                PythonRiskPatternCheck(),
                SecurityConfigurationCheck(),
                DependencyManifestCheck(),
                SelectedLogSecurityCheck(),
                MalwareIndicatorCheck(),
            )
        )

    def analyze(
        self, request: SecurityAnalysisRequest, cancellation: Event | None = None
    ) -> SecurityAnalysisResult:
        cancellation = cancellation or Event()
        scope = request.scope
        root = Path(scope.target.root)
        if not root.is_absolute() or not root.is_dir():
            raise ValidationError(
                "Security target must be an existing absolute directory",
                source_module=__name__,
            )
        root = root.resolve(strict=True)
        if str(root) != scope.target.root:
            raise SecurityViolationError(
                "Security scope root must be canonical", source_module=__name__
            )
        checks = self.registry.selected(request.requested_checks)
        selected_logs = self._selected_logs(root, request)
        plan = SecurityAnalysisPlan(
            request_id=request.request_id,
            check_ids=tuple(item.check_id for item in checks),
            permission=SecurityPermissionRequirement(),
            objective=request.objective,
        )
        self.dispatcher.publish(
            SecurityAnalysisStartedEvent(
                analysis_id=plan.analysis_id,
                target_type=scope.target.target_type.value,
                check_count=len(checks),
                correlation_id=request.request_id,
                source_module=__name__,
            )
        )
        self.state_store.transition(
            ApplicationState.THINKING,
            status_message="Analyzing authorized local security scope",
            correlation_id=request.request_id,
        )
        executed: set[str] = set()
        skipped: list[str] = []
        errors: list[str] = []
        findings: dict[tuple[str, str, str], SecurityFinding] = {}
        try:
            for path, relative in self._files(root, request, skipped, selected_logs):
                if cancellation.is_set() or len(findings) >= scope.max_findings:
                    break
                try:
                    data = path.read_bytes()
                    if b"\x00" in data[:4096]:
                        skipped.append(f"binary:{relative}")
                        continue
                    text = data.decode("utf-8")
                except (OSError, UnicodeDecodeError) as error:
                    errors.append(f"read_error:{relative}:{type(error).__name__}")
                    continue
                for check in checks:
                    if cancellation.is_set() or len(findings) >= scope.max_findings:
                        break
                    try:
                        for finding in check.execute(path, relative, text):
                            key = (
                                finding.category.value,
                                finding.affected_path,
                                finding.title,
                            )
                            findings.setdefault(key, finding)
                            self.dispatcher.publish(
                                SecurityFindingDetectedEvent(
                                    analysis_id=plan.analysis_id,
                                    finding_id=finding.finding_id,
                                    severity=finding.severity.value,
                                    category=finding.category.value,
                                    affected_path=finding.affected_path,
                                    correlation_id=request.request_id,
                                    source_module=__name__,
                                )
                            )
                        executed.add(check.check_id)
                    except Exception as error:
                        errors.append(
                            f"check_error:{check.check_id}:{type(error).__name__}"
                        )
            result = SecurityAnalysisResult(
                analysis_id=plan.analysis_id,
                target=scope.target,
                scope=scope,
                checks_executed=tuple(sorted(executed)),
                checks_skipped=tuple(skipped),
                findings=tuple(findings.values())[: scope.max_findings],
                errors=tuple(errors),
                intelligence=(
                    SecurityIntelligenceStatus(
                        provider="vulnerability-intelligence",
                        status=SecurityProviderStatus.NOT_CONFIGURED,
                        detail=(
                            "No vulnerability database is configured; manifest "
                            "findings are local observations and contain no CVE claims."
                        ),
                    ),
                    SecurityIntelligenceStatus(
                        provider="malware-intelligence",
                        status=SecurityProviderStatus.NOT_CONFIGURED,
                        detail="No malware reputation database is configured; only local potential indicators are reported.",
                    ),
                ),
                objective=request.objective,
                cancelled=cancellation.is_set(),
            )
            self.dispatcher.publish(
                SecurityAnalysisCompletedEvent(
                    analysis_id=plan.analysis_id,
                    finding_count=len(result.findings),
                    cancelled=result.cancelled,
                    correlation_id=request.request_id,
                    source_module=__name__,
                )
            )
            return result
        except Exception as error:
            self.dispatcher.publish(
                SecurityAnalysisFailedEvent(
                    analysis_id=plan.analysis_id,
                    error_type=type(error).__name__,
                    correlation_id=request.request_id,
                    source_module=__name__,
                )
            )
            raise
        finally:
            self.state_store.transition(
                ApplicationState.IDLE, correlation_id=request.request_id
            )

    @staticmethod
    def _files(
        root: Path,
        request: SecurityAnalysisRequest,
        skipped: list[str],
        selected_logs: frozenset[str],
    ) -> Iterable[tuple[Path, str]]:
        scope = request.scope
        count = 0
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            if len(path.relative_to(root).parts) > scope.max_depth or any(
                part in EXCLUDED for part in path.relative_to(root).parts
            ):
                continue
            if not path.is_file():
                continue
            validated = validate_workspace_path(root, relative)
            if validated.name in SENSITIVE_NAMES:
                skipped.append(f"private-credential-file:{relative}")
            elif validated.suffix.lower() == ".log":
                if relative not in selected_logs:
                    skipped.append(f"unselected-log:{relative}")
                    continue
                if validated.stat().st_size > scope.max_file_bytes:
                    skipped.append(f"oversized:{relative}")
                    continue
                yield validated, relative
                count += 1
            elif (
                validated.suffix.lower() in TEXT_EXTENSIONS
                or validated.name.startswith(".env")
            ):
                if validated.stat().st_size > scope.max_file_bytes:
                    skipped.append(f"oversized:{relative}")
                    continue
                yield validated, relative
                count += 1
            else:
                skipped.append(f"unsupported:{relative}")
            if count >= scope.max_files:
                break

    @staticmethod
    def _selected_logs(root: Path, request: SecurityAnalysisRequest) -> frozenset[str]:
        selected: set[str] = set()
        for requested in request.selected_log_paths:
            path = validate_workspace_path(root, requested)
            if path.suffix.lower() != ".log" or not path.is_file():
                raise ValidationError(
                    "Selected log must be an existing .log file in scope",
                    source_module=__name__,
                )
            selected.add(path.relative_to(root).as_posix())
        return frozenset(selected)
