"""Project-aware bounded coding executor built on the existing creation core."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from virgo.application.permissions import PermissionGate
from virgo.application.tasks import CreationCoordinator, ControlledCreationWorkflow
from virgo.capabilities.creation import (
    CreationGenerator,
    SafeWorkspace,
    validate_content,
)
from virgo.contracts.errors import ProviderUnavailableError, SecurityViolationError, ValidationError
from virgo.contracts.models import (
    CreationAction,
    CreationOperation,
    CreationRequest,
    GeneratedFileProposal,
    PermissionDecision,
    ToolRiskLevel,
    ValidationStatus,
)
from virgo.infrastructure.events import EventDispatcher
from virgo.intelligence.planner import CreationPlanner

MAX_TARGETS = 4
MAX_CONTEXT_FILES = 8
MAX_CONTEXT_BYTES = 80_000
ALLOWED_SUFFIXES = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".rs", ".html", ".htm",
    ".css", ".scss", ".json", ".md", ".txt", ".yaml", ".yml", ".toml",
}
SENSITIVE_FILE_NAMES = {
    ".env", ".env.local", ".env.production", "credentials.json", "secrets.json",
    "id_rsa", "id_ed25519", "token.json",
}


@dataclass(frozen=True, slots=True)
class CodingExecutionResult:
    summary: str
    changed_files: tuple[str, ...]
    validation: tuple[str, ...]
    project_summary: str


class PersonalCodingExecutor:
    """Use the existing safe creation workflow for LLM-assisted project edits."""

    def __init__(
        self,
        *,
        dispatcher: EventDispatcher,
        permission_gate: PermissionGate,
        journal_root: Path,
        llm: Any,
        model: str | None,
    ) -> None:
        self.dispatcher = dispatcher
        self.permission_gate = permission_gate
        self.journal_root = journal_root
        self.llm = llm
        self.model = model
        self._planner = CreationPlanner()
        self._coordinator = CreationCoordinator(dispatcher, self._planner)

    def set_model(self, model: str | None) -> None:
        self.model = model

    def execute(
        self,
        objective: str,
        workspace_root: Path | str | None,
        *,
        personal_permission_granted: bool,
    ) -> CodingExecutionResult:
        if not personal_permission_granted:
            raise ValidationError(
                "Project mutation requires explicit task approval", source_module=__name__
            )
        if workspace_root is None:
            raise ValidationError(
                "Coding requires an explicit workspace root", source_module=__name__
            )
        workspace = SafeWorkspace(Path(workspace_root))
        project_summary, existing_files = self._project_context(workspace)
        targets = self._select_targets(objective, workspace, existing_files)
        proposals = self._build_proposals(objective, workspace, targets, project_summary)
        request = CreationRequest(
            intent=objective,
            workspace_root=str(workspace.root),
            requested_paths=targets,
            requirements=("Preserve the approved workspace boundary",),
            constraints=(
                "No secrets or credentials",
                "No shell commands in generated content",
                "Do not change files outside requested targets",
            ),
        )
        task_id = request.request_id
        workflow = ControlledCreationWorkflow(
            request,
            proposals,
            self._coordinator,
            self.permission_gate,
            self.journal_root,
            task_id=task_id,
            normalized_intent=objective,
            capability="coding",
            provider_explanation="LLM generated an untrusted proposal; Virgo creation core validated and permissioned the mutation.",
        )
        permissions = workflow.approve()
        try:
            workflow.apply()
            validation = tuple(
                f"{item.target}: {item.status.value}"
                for item in workflow.validation_results
            )
            changed = tuple(item.operation.target for item in proposals)
            workflow.accept()
            return CodingExecutionResult(
                summary=f"Updated {len(changed)} approved file(s) and validated the result",
                changed_files=changed,
                validation=validation,
                project_summary=project_summary,
            )
        except Exception:
            try:
                if workflow.state.status.value in {
                    "approved", "awaiting_acceptance", "failed", "cancelled"
                }:
                    workflow.rollback()
            except Exception:
                pass
            raise
        finally:
            del permissions

    def _project_context(self, workspace: SafeWorkspace) -> tuple[str, tuple[str, ...]]:
        inspection = workspace.inspect((".",))
        files = tuple(item.relative_path for item in inspection.files)
        code_files = tuple(
            path for path in files if Path(path).suffix.lower() in ALLOWED_SUFFIXES
        )[:MAX_CONTEXT_FILES]
        sections: list[str] = [
            f"Workspace: {workspace.root}",
            f"Files inspected: {len(files)}; total bytes: {inspection.total_bytes}",
        ]
        used = 0
        for path in code_files:
            try:
                content = workspace.read_text(path)
            except Exception:
                continue
            block = f"\n--- {path} ---\n{content[:12_000]}\n"
            if used + len(block) > MAX_CONTEXT_BYTES:
                break
            sections.append(block)
            used += len(block)
        return "\n".join(sections), files

    def _select_targets(
        self,
        objective: str,
        workspace: SafeWorkspace,
        existing_files: tuple[str, ...],
    ) -> tuple[str, ...]:
        explicit = _extract_paths(objective)
        if explicit:
            return self._validate_targets(explicit, workspace)
        if not self.model:
            raise ProviderUnavailableError(
                "No local coding model is selected", source_module=__name__
            )
        # Use the model only for target selection; target paths are still validated locally.
        prompt = (
            "Return JSON only: {\"targets\":[\"relative/path.ext\"]}. "
            f"Choose at most {MAX_TARGETS} files from this project that should be changed "
            "to fulfill the user request. Existing files are preferred; never select a "
            "secret or credential file.\n"
            f"User request: {objective}\n"
            f"Project files: {json.dumps(existing_files[:200])}"
        )
        try:
            response = self.llm.generate(
                __import__("virgo.contracts.models", fromlist=["LLMRequest"]).LLMRequest(
                    prompt=prompt,
                    model=self.model,
                    temperature=0.0,
                )
            )
            payload = json.loads(response.text)
            raw = payload.get("targets") if isinstance(payload, dict) else None
        except Exception as error:
            raise ProviderUnavailableError(
                "The local coding model could not select safe project targets",
                technical_detail=str(error), source_module=__name__, cause=error,
            ) from error
        if not isinstance(raw, list) or not raw:
            raise ValidationError(
                "The coding model did not return safe target paths", source_module=__name__
            )
        return self._validate_targets(tuple(str(item) for item in raw[:MAX_TARGETS]), workspace)

    def _validate_targets(
        self, targets: tuple[str, ...], workspace: SafeWorkspace
    ) -> tuple[str, ...]:
        if not 1 <= len(targets) <= MAX_TARGETS:
            raise ValidationError("Coding target count exceeds the safe limit", source_module=__name__)
        normalized: list[str] = []
        for target in targets:
            candidate = Path(target)
            if candidate.is_absolute():
                try:
                    target = candidate.resolve().relative_to(workspace.root).as_posix()
                except ValueError as error:
                    raise SecurityViolationError(
                        "Coding target must remain inside the selected workspace",
                        source_module=__name__,
                    ) from error
            target = Path(target).as_posix()
            if target.startswith("../") or target in {".", ""}:
                raise SecurityViolationError(
                    "Coding target escapes the selected workspace", source_module=__name__
                )
            name = Path(target).name
            suffix = Path(target).suffix.lower()
            if name in SENSITIVE_FILE_NAMES or suffix not in ALLOWED_SUFFIXES:
                raise SecurityViolationError(
                    f"Coding target is not an approved text source: {target}", source_module=__name__
                )
            normalized.append(target)
        if len(set(normalized)) != len(normalized):
            raise ValidationError("Coding target list contains duplicates", source_module=__name__)
        return tuple(normalized)

    def _build_proposals(
        self,
        objective: str,
        workspace: SafeWorkspace,
        targets: tuple[str, ...],
        project_summary: str,
    ) -> tuple[GeneratedFileProposal, ...]:
        if not self.model:
            raise ProviderUnavailableError(
                "No local coding model is selected", source_module=__name__
            )
        generator = CreationGenerator(self.llm)
        proposals: list[GeneratedFileProposal] = []
        for target in targets:
            path = workspace.root / target
            existing = workspace.read_text(target) if path.is_file() else None
            operation = CreationOperation(
                action=CreationAction.UPDATE if existing is not None else CreationAction.CREATE,
                target=target,
                summary=f"Implement the requested bounded change in {target}",
                risk_level=ToolRiskLevel.REVERSIBLE_WRITE,
                tool_name="create_text_file",
                reversible=True,
                requires_permission=True,
            )
            intent = (
                f"User request: {objective}\n\nProject context:\n{project_summary[:50_000]}\n\n"
                "Modify only the approved target and preserve surrounding behavior."
            )
            proposal = generator.propose(
                operation, intent=intent, model=self.model, existing_content=existing
            )
            deterministic = validate_content(target, proposal.proposed_content)
            if deterministic.status is not ValidationStatus.PASSED:
                raise ValidationError(
                    f"Generated code failed deterministic validation for {target}: {deterministic.message}",
                    source_module=__name__,
                )
            proposals.append(proposal)
        return tuple(proposals)


def _extract_paths(objective: str) -> tuple[str, ...]:
    patterns = (
        r"(?:file|files|path|paths|in|edit|modify|update|change)\s+[`\"']?([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+)",
        r"[`\"']([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+)[`\"']",
    )
    values: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, objective, flags=re.IGNORECASE):
            value = match.group(1).replace("\\", "/")
            if value not in values:
                values.append(value)
    return tuple(values[:MAX_TARGETS])
