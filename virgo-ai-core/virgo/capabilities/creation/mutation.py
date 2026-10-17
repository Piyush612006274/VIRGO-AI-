"""Permission-bound controlled file mutation and real rollback."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

from virgo.application.permissions import PermissionGate
from virgo.contracts.errors import (
    SecurityViolationError,
    ToolExecutionError,
    ValidationError,
)
from virgo.contracts.models import (
    ChangePreview,
    CreationAction,
    CreationOperation,
    GeneratedFileProposal,
    MutationJournalEntry,
    MutationStatus,
    ValidationStatus,
)
from virgo.infrastructure.filesystem import validate_workspace_path
from virgo.infrastructure.storage import MutationJournal


class _RustMutationProtocol(Protocol):
    def atomic_write_text(self, *args: str) -> tuple[bool, str | None, str]: ...
    def reversible_delete_file(self, *args: str) -> str: ...
    def rollback_file(self, *args: object) -> str | None: ...
    def discard_backup(self, *args: str) -> None: ...


class ControlledMutationService:
    """Apply exact approved operations and retain backups until accept/rollback."""

    def __init__(
        self,
        workspace_root: Path,
        task_id: str,
        permission_gate: PermissionGate,
        journal_root: Path,
    ) -> None:
        if not workspace_root.is_absolute() or not workspace_root.is_dir():
            raise ValidationError(
                "Mutation workspace is invalid", source_module=__name__
            )
        self.workspace_root = workspace_root.resolve(strict=True)
        self.task_id = task_id
        self.permission_gate = permission_gate
        self.journal = MutationJournal(journal_root, task_id)

    def apply(
        self,
        proposal: GeneratedFileProposal,
        preview: ChangePreview,
        permission_id: str,
    ) -> MutationJournalEntry:
        operation = proposal.operation
        if operation.target != preview.target:
            raise SecurityViolationError(
                "Approved operation target does not match preview",
                source_module=__name__,
            )
        if not proposal.validated:
            raise ValidationError(
                "Generated proposal must pass validation before apply",
                source_module=__name__,
            )
        self.permission_gate.require(
            permission_id,
            task_id=self.task_id,
            operation=operation,
        )
        current_hash = self._current_hash(operation.target)
        expected_hash = preview.rollback.previous_sha256
        if current_hash != expected_hash:
            raise SecurityViolationError(
                "Workspace target changed after preview approval",
                source_module=__name__,
            )
        if operation.action is CreationAction.CREATE and current_hash is not None:
            raise SecurityViolationError(
                "Create target already exists", source_module=__name__
            )
        if operation.action is CreationAction.UPDATE and current_hash is None:
            raise SecurityViolationError(
                "Update target no longer exists", source_module=__name__
            )
        if operation.action not in (CreationAction.CREATE, CreationAction.UPDATE):
            raise ValidationError(
                "Proposal action is not a text write", source_module=__name__
            )
        try:
            core = cast(_RustMutationProtocol, import_module("virgo._rust_core"))
            existed, _, _ = core.atomic_write_text(
                str(self.workspace_root),
                operation.target,
                proposal.proposed_content,
                str(self.journal.backup_directory),
                operation.operation_id,
            )
        except (ValueError, OSError) as error:
            raise ToolExecutionError(
                "Approved file mutation failed safely",
                technical_detail=str(error),
                source_module=__name__,
                cause=error,
            ) from error
        after_hash = self._current_hash(operation.target)
        expected_after = sha256(proposal.proposed_content.encode("utf-8")).hexdigest()
        if after_hash != expected_after:
            raise ToolExecutionError(
                "Post-write SHA-256 verification failed", source_module=__name__
            )
        entry = MutationJournalEntry(
            task_id=self.task_id,
            operation=operation,
            existed_before=bool(existed),
            before_sha256=current_hash,
            backup_reference=(
                f"backups/{operation.operation_id}.bak" if existed else None
            ),
            after_sha256=after_hash,
            apply_status=MutationStatus.APPLIED,
        )
        self.journal.append(entry)
        return entry

    def delete(
        self,
        operation: CreationOperation,
        preview: ChangePreview,
        permission_id: str,
    ) -> MutationJournalEntry:
        if operation.action is not CreationAction.DELETE or not operation.reversible:
            raise ValidationError(
                "Delete operation must be reversible", source_module=__name__
            )
        if operation.target != preview.target:
            raise SecurityViolationError(
                "Delete target does not match preview", source_module=__name__
            )
        self.permission_gate.require(
            permission_id, task_id=self.task_id, operation=operation
        )
        before_hash = self._current_hash(operation.target)
        if before_hash is None or before_hash != preview.rollback.previous_sha256:
            raise SecurityViolationError(
                "Delete target changed after preview approval", source_module=__name__
            )
        try:
            core = cast(_RustMutationProtocol, import_module("virgo._rust_core"))
            core.reversible_delete_file(
                str(self.workspace_root),
                operation.target,
                str(self.journal.backup_directory),
                operation.operation_id,
            )
        except (ValueError, OSError) as error:
            raise ToolExecutionError(
                "Approved file deletion failed safely",
                technical_detail=str(error),
                source_module=__name__,
                cause=error,
            ) from error
        entry = MutationJournalEntry(
            task_id=self.task_id,
            operation=operation,
            existed_before=True,
            before_sha256=before_hash,
            backup_reference=f"backups/{operation.operation_id}.bak",
            after_sha256=None,
            apply_status=MutationStatus.APPLIED,
        )
        self.journal.append(entry)
        return entry

    def set_validation(
        self, operation_id: str, status: ValidationStatus
    ) -> MutationJournalEntry:
        entry = self._entry(operation_id)
        updated = replace(entry, validation_status=status)
        self.journal.replace(updated)
        return updated

    def rollback(self) -> tuple[MutationJournalEntry, ...]:
        updated: list[MutationJournalEntry] = []
        for entry in reversed(self.journal.entries):
            if entry.rollback_status is MutationStatus.ROLLED_BACK:
                updated.append(entry)
                continue
            try:
                core = cast(_RustMutationProtocol, import_module("virgo._rust_core"))
                core.rollback_file(
                    str(self.workspace_root),
                    entry.operation.target,
                    str(self.journal.backup_directory),
                    entry.operation.operation_id,
                    entry.existed_before,
                )
            except (ValueError, OSError) as error:
                failed = replace(entry, rollback_status=MutationStatus.FAILED)
                self.journal.replace(failed)
                raise ToolExecutionError(
                    "Creation rollback failed",
                    technical_detail=str(error),
                    source_module=__name__,
                    cause=error,
                ) from error
            restored_hash = self._current_hash(entry.operation.target)
            if restored_hash != entry.before_sha256:
                raise ToolExecutionError(
                    "Rollback content verification failed", source_module=__name__
                )
            rolled_back = replace(entry, rollback_status=MutationStatus.ROLLED_BACK)
            self.journal.replace(rolled_back)
            updated.append(rolled_back)
        return tuple(updated)

    def accept(self) -> tuple[MutationJournalEntry, ...]:
        accepted: list[MutationJournalEntry] = []
        for entry in self.journal.entries:
            core = cast(_RustMutationProtocol, import_module("virgo._rust_core"))
            core.discard_backup(
                str(self.journal.backup_directory), entry.operation.operation_id
            )
            current = replace(entry, apply_status=MutationStatus.ACCEPTED)
            self.journal.replace(current)
            accepted.append(current)
        return tuple(accepted)

    def _entry(self, operation_id: str) -> MutationJournalEntry:
        for entry in self.journal.entries:
            if entry.operation.operation_id == operation_id:
                return entry
        raise ValidationError(
            "Mutation operation is not journaled", source_module=__name__
        )

    def _current_hash(self, relative_path: str) -> str | None:
        try:
            path = validate_workspace_path(self.workspace_root, relative_path)
        except SecurityViolationError:
            path = self.workspace_root / relative_path
            if path.exists():
                raise
            return None
        if not path.is_file():
            return None
        return sha256(path.read_bytes()).hexdigest()
