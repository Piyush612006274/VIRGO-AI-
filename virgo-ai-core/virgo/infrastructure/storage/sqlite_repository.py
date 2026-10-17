"""Explicit instance-owned SQLite persistence for Stage 1 session data."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from threading import RLock

from virgo.contracts.errors import StorageError, ValidationError
from virgo.contracts.models import (
    PersistedSettings,
    Session,
    SessionMessage,
    SessionMessageRole,
)
from virgo.contracts.models.session import utc_now

SCHEMA_VERSION = 2
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    title TEXT,
    archived_at TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT UNIQUE NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    text TEXT NOT NULL CHECK (length(trim(text)) > 0),
    created_at TEXT NOT NULL,
    correlation_id TEXT
);
CREATE INDEX IF NOT EXISTS messages_history_order
ON messages(session_id, sequence);
CREATE TABLE IF NOT EXISTS persisted_settings (
    settings_id INTEGER PRIMARY KEY CHECK (settings_id = 1),
    microphone_device_id INTEGER,
    output_device_id INTEGER,
    local_llm_model TEXT,
    tts_voice TEXT
);
"""


class SQLiteSessionRepository:
    """Persist sessions and runtime preferences in one explicitly opened DB."""

    def __init__(self, database_path: Path) -> None:
        if not isinstance(database_path, Path) or not database_path.name:
            raise ValidationError(
                "Session repository requires a database file path",
                source_module=__name__,
            )
        self._database_path = database_path
        self._connection: sqlite3.Connection | None = None
        self._lock = RLock()

    def initialize(self) -> None:
        if self._connection is not None:
            return
        connection: sqlite3.Connection | None = None
        try:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self._database_path, check_same_thread=False)
            connection.execute("PRAGMA foreign_keys = ON")
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version not in (0, 1, SCHEMA_VERSION):
                connection.close()
                raise StorageError(
                    "Session database schema version is incompatible",
                    technical_detail=f"Expected {SCHEMA_VERSION}, found {version}",
                    source_module=__name__,
                )
            if version == 0:
                with connection:
                    connection.executescript(SCHEMA_SQL)
                    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif version == 1:
                with connection:
                    connection.execute(
                        "ALTER TABLE sessions ADD COLUMN archived_at TEXT"
                    )
                    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._connection = connection
        except StorageError:
            if connection is not None:
                connection.close()
            raise
        except (OSError, sqlite3.Error) as error:
            if connection is not None:
                connection.close()
            raise self._storage_error(
                "Session database could not be initialized", error
            ) from error

    def create_session(self, *, title: str | None = None) -> Session:
        with self._lock:
            session = Session.create(title=title)
            connection = self._require_connection()
            try:
                with connection:
                    connection.execute(
                        "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                        (
                            session.session_id,
                            session.created_at.isoformat(),
                            session.updated_at.isoformat(),
                            session.title,
                            None,
                        ),
                    )
                return session
            except sqlite3.Error as error:
                raise self._storage_error(
                    "Session could not be created", error
                ) from error

    def get_session(self, session_id: str) -> Session | None:
        with self._lock:
            connection = self._require_connection()
            try:
                row = connection.execute(
                    "SELECT session_id, created_at, updated_at, title, archived_at "
                    "FROM sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                return None if row is None else self._session_from_row(row)
            except (sqlite3.Error, TypeError, ValueError) as error:
                raise self._storage_error(
                    "Session could not be loaded", error
                ) from error

    def list_sessions(self, *, archived: bool = False) -> tuple[Session, ...]:
        with self._lock:
            connection = self._require_connection()
            try:
                state = "NOT NULL" if archived else "NULL"
                rows = connection.execute(
                    "SELECT session_id, created_at, updated_at, title, archived_at "
                    f"FROM sessions WHERE archived_at IS {state} "
                    "ORDER BY updated_at DESC, session_id"
                ).fetchall()
                return tuple(self._session_from_row(row) for row in rows)
            except (sqlite3.Error, TypeError, ValueError) as error:
                raise self._storage_error(
                    "Sessions could not be listed", error
                ) from error

    def rename_session(self, session_id: str, title: str) -> Session:
        normalized = title.strip() if isinstance(title, str) else ""
        if not normalized:
            raise ValidationError(
                "Session title must not be empty", source_module=__name__
            )
        return self._update_session(
            session_id,
            "title=?, updated_at=?",
            (normalized, utc_now().isoformat()),
        )

    def search_sessions(
        self, query: str, *, include_archived: bool = False, limit: int = 20
    ) -> tuple[Session, ...]:
        normalized = query.strip() if isinstance(query, str) else ""
        if not normalized or not 1 <= limit <= 100:
            raise ValidationError("Session search is invalid", source_module=__name__)
        archived_clause = "" if include_archived else "AND s.archived_at IS NULL"
        with self._lock:
            try:
                rows = (
                    self._require_connection()
                    .execute(
                        "SELECT DISTINCT s.session_id,s.created_at,s.updated_at,s.title,"
                        "s.archived_at FROM sessions s LEFT JOIN messages m "
                        "ON m.session_id=s.session_id WHERE "
                        "(s.title LIKE ? ESCAPE '\\' OR m.text LIKE ? ESCAPE '\\') "
                        f"{archived_clause} ORDER BY s.updated_at DESC,s.session_id LIMIT ?",
                        (*(_like(normalized),) * 2, limit),
                    )
                    .fetchall()
                )
                return tuple(self._session_from_row(row) for row in rows)
            except (sqlite3.Error, TypeError, ValueError) as error:
                raise self._storage_error(
                    "Sessions could not be searched", error
                ) from error

    def archive_session(self, session_id: str) -> Session:
        timestamp = utc_now().isoformat()
        return self._update_session(
            session_id,
            "archived_at=?, updated_at=?",
            (timestamp, timestamp),
            require_archived=False,
        )

    def restore_session(self, session_id: str) -> Session:
        return self._update_session(
            session_id,
            "archived_at=NULL, updated_at=?",
            (utc_now().isoformat(),),
            require_archived=True,
        )

    def append_message(self, message: SessionMessage) -> None:
        if not isinstance(message, SessionMessage):
            raise ValidationError(
                "Session history requires a SessionMessage",
                source_module=__name__,
            )
        with self._lock:
            connection = self._require_connection()
            try:
                with connection:
                    connection.execute(
                        "INSERT INTO messages(message_id, session_id, role, text, "
                        "created_at, correlation_id) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            message.message_id,
                            message.session_id,
                            message.role.value,
                            message.text,
                            message.created_at.isoformat(),
                            message.correlation_id,
                        ),
                    )
                    connection.execute(
                        "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                        (message.created_at.isoformat(), message.session_id),
                    )
            except sqlite3.Error as error:
                raise self._storage_error(
                    "Session message could not be saved", error
                ) from error

    def load_history(self, session_id: str) -> tuple[SessionMessage, ...]:
        with self._lock:
            connection = self._require_connection()
            try:
                rows = connection.execute(
                    "SELECT message_id, session_id, role, text, created_at, "
                    "correlation_id FROM messages WHERE session_id = ? "
                    "ORDER BY sequence",
                    (session_id,),
                ).fetchall()
                return tuple(self._message_from_row(row) for row in rows)
            except (sqlite3.Error, TypeError, ValueError) as error:
                raise self._storage_error(
                    "Session history could not be loaded", error
                ) from error

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            connection = self._require_connection()
            try:
                with connection:
                    cursor = connection.execute(
                        "DELETE FROM sessions WHERE session_id = ?", (session_id,)
                    )
                return cursor.rowcount == 1
            except sqlite3.Error as error:
                raise self._storage_error(
                    "Session could not be deleted", error
                ) from error

    @property
    def database_size(self) -> int:
        return self._database_path.stat().st_size if self._database_path.exists() else 0

    def _update_session(
        self,
        session_id: str,
        assignment: str,
        values: tuple[str, ...],
        *,
        require_archived: bool | None = None,
    ) -> Session:
        condition = ""
        if require_archived is True:
            condition = " AND archived_at IS NOT NULL"
        elif require_archived is False:
            condition = " AND archived_at IS NULL"
        with self._lock:
            connection = self._require_connection()
            try:
                with connection:
                    cursor = connection.execute(
                        f"UPDATE sessions SET {assignment} WHERE session_id=?{condition}",
                        (*values, session_id),
                    )
                if cursor.rowcount != 1:
                    raise ValidationError(
                        "Session is missing or has an incompatible lifecycle state",
                        source_module=__name__,
                    )
                session = self.get_session(session_id)
                assert session is not None
                return session
            except ValidationError:
                raise
            except (sqlite3.Error, TypeError, ValueError) as error:
                raise self._storage_error(
                    "Session could not be updated", error
                ) from error

    def load_settings(self) -> PersistedSettings:
        with self._lock:
            connection = self._require_connection()
            try:
                row = connection.execute(
                    "SELECT microphone_device_id, output_device_id, local_llm_model, "
                    "tts_voice FROM persisted_settings WHERE settings_id = 1"
                ).fetchone()
                return (
                    PersistedSettings()
                    if row is None
                    else PersistedSettings(
                        microphone_device_id=row[0],
                        output_device_id=row[1],
                        local_llm_model=row[2],
                        tts_voice=row[3],
                    )
                )
            except (sqlite3.Error, TypeError, ValueError) as error:
                raise self._storage_error(
                    "Persisted settings could not be loaded", error
                ) from error

    def save_settings(self, settings: PersistedSettings) -> None:
        if not isinstance(settings, PersistedSettings):
            raise ValidationError(
                "Settings persistence requires PersistedSettings",
                source_module=__name__,
            )
        with self._lock:
            connection = self._require_connection()
            try:
                with connection:
                    connection.execute(
                        "INSERT INTO persisted_settings VALUES (1, ?, ?, ?, ?) "
                        "ON CONFLICT(settings_id) DO UPDATE SET "
                        "microphone_device_id=excluded.microphone_device_id, "
                        "output_device_id=excluded.output_device_id, "
                        "local_llm_model=excluded.local_llm_model, "
                        "tts_voice=excluded.tts_voice",
                        (
                            settings.microphone_device_id,
                            settings.output_device_id,
                            settings.local_llm_model,
                            settings.tts_voice,
                        ),
                    )
            except sqlite3.Error as error:
                raise self._storage_error(
                    "Persisted settings could not be saved", error
                ) from error

    def close(self) -> None:
        with self._lock:
            connection = self._connection
            self._connection = None
            if connection is not None:
                connection.close()

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise StorageError(
                "Session repository is not initialized",
                source_module=__name__,
            )
        return self._connection

    @staticmethod
    def _session_from_row(row: tuple[object, ...]) -> Session:
        return Session(
            session_id=str(row[0]),
            created_at=datetime.fromisoformat(str(row[1])),
            updated_at=datetime.fromisoformat(str(row[2])),
            title=None if row[3] is None else str(row[3]),
            archived_at=(
                None
                if len(row) < 5 or row[4] is None
                else datetime.fromisoformat(str(row[4]))
            ),
        )

    @staticmethod
    def _message_from_row(row: tuple[object, ...]) -> SessionMessage:
        return SessionMessage(
            message_id=str(row[0]),
            session_id=str(row[1]),
            role=SessionMessageRole(str(row[2])),
            text=str(row[3]),
            created_at=datetime.fromisoformat(str(row[4])),
            correlation_id=None if row[5] is None else str(row[5]),
        )

    @staticmethod
    def _storage_error(message: str, error: BaseException) -> StorageError:
        return StorageError(
            message,
            technical_detail=f"{type(error).__name__}: {error}",
            source_module=__name__,
            cause=error,
        )


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
