"""User-controlled session lifecycle over the existing persistence authority."""

from virgo.contracts.errors import ValidationError
from virgo.contracts.models import Session, StorageUsage
from virgo.infrastructure.storage import (
    SQLiteKnowledgeRepository,
    SQLiteSessionRepository,
)


class SessionLifecycleService:
    def __init__(
        self,
        sessions: SQLiteSessionRepository,
        knowledge: SQLiteKnowledgeRepository,
    ) -> None:
        self._sessions = sessions
        self._knowledge = knowledge
        self._active_session_id: str | None = None

    @property
    def active_session_id(self) -> str | None:
        return self._active_session_id

    def ensure_active(self) -> Session:
        current = (
            None
            if self._active_session_id is None
            else self._sessions.get_session(self._active_session_id)
        )
        if current is not None and current.archived_at is None:
            return current
        sessions = self._sessions.list_sessions()
        current = (
            sessions[0]
            if sessions
            else self._sessions.create_session(title="Virgo conversation")
        )
        self._active_session_id = current.session_id
        return current

    def select(self, session_id: str) -> Session:
        session = self._sessions.get_session(session_id)
        if session is None or session.archived_at is not None:
            raise ValidationError(
                "Active session must exist and not be archived", source_module=__name__
            )
        self._active_session_id = session.session_id
        return session

    def create(self, *, title: str = "Virgo conversation") -> Session:
        session = self._sessions.create_session(title=title)
        self._active_session_id = session.session_id
        return session

    def rename(self, session_id: str, title: str) -> Session:
        return self._sessions.rename_session(session_id, title)

    def search(
        self, query: str, *, include_archived: bool = False
    ) -> tuple[Session, ...]:
        return self._sessions.search_sessions(query, include_archived=include_archived)

    def archive(self, session_id: str) -> Session:
        session = self._sessions.archive_session(session_id)
        if session_id == self._active_session_id:
            self._active_session_id = None
            self.ensure_active()
        return session

    def restore(self, session_id: str) -> Session:
        return self._sessions.restore_session(session_id)

    def delete(self, session_id: str) -> bool:
        deleted = self._sessions.delete_session(session_id)
        if deleted and session_id == self._active_session_id:
            self._active_session_id = None
            self.ensure_active()
        return deleted

    def storage_usage(self) -> StorageUsage:
        active = self._sessions.list_sessions()
        archived = self._sessions.list_sessions(archived=True)
        return StorageUsage(
            session_bytes=self._sessions.database_size,
            memory_bytes=self._knowledge.database_size,
            active_sessions=len(active),
            archived_sessions=len(archived),
            cleanup_session_ids=tuple(session.session_id for session in archived),
        )
