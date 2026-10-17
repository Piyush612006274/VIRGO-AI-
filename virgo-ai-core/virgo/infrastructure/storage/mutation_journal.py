"""Small task-scoped JSON mutation journal and backup location."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from virgo.contracts.errors import StorageError
from virgo.contracts.models import MutationJournalEntry


class MutationJournal:
    """Persist ordered non-secret mutation metadata for one creation task."""

    def __init__(self, root: Path, task_id: str) -> None:
        if not root.is_absolute() or not task_id.strip():
            raise StorageError(
                "Mutation journal location is invalid", source_module=__name__
            )
        self.task_id = task_id
        self.directory = root / task_id
        self.backup_directory = self.directory / "backups"
        self.backup_directory.mkdir(parents=True, exist_ok=False)
        self.path = self.directory / "journal.json"
        self._entries: list[MutationJournalEntry] = []
        self._persist()

    @property
    def entries(self) -> tuple[MutationJournalEntry, ...]:
        return tuple(self._entries)

    def append(self, entry: MutationJournalEntry) -> None:
        if entry.task_id != self.task_id:
            raise StorageError(
                "Journal entry belongs to another task", source_module=__name__
            )
        self._entries.append(entry)
        self._persist()

    def replace(self, entry: MutationJournalEntry) -> None:
        for index, current in enumerate(self._entries):
            if current.operation.operation_id == entry.operation.operation_id:
                self._entries[index] = entry
                self._persist()
                return
        raise StorageError(
            "Mutation journal entry was not found", source_module=__name__
        )

    def _persist(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        payload = {
            "task_id": self.task_id,
            "entries": [self._serialize(entry) for entry in self._entries],
        }
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise StorageError(
                "Mutation journal could not be persisted",
                technical_detail=str(error),
                source_module=__name__,
                cause=error,
            ) from error

    @staticmethod
    def _serialize(entry: MutationJournalEntry) -> dict[str, object]:
        value = asdict(entry)
        operation = value["operation"]
        assert isinstance(operation, dict)
        operation["action"] = entry.operation.action.value
        operation["risk_level"] = entry.operation.risk_level.value
        value["apply_status"] = entry.apply_status.value
        value["validation_status"] = entry.validation_status.value
        value["rollback_status"] = entry.rollback_status.value
        return value
