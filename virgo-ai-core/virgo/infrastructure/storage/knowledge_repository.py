"""Versioned SQLite repository for accepted structured knowledge."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from virgo.contracts.errors import StorageError
from virgo.contracts.models.learning import (
    ClaimStatus,
    Evidence,
    KnowledgeClaim,
    KnowledgeScope,
    LearningSource,
    PrivacyClassification,
)
from virgo.contracts.models.learning_experience import (
    EvaluationRecord,
    EvaluationType,
    ReusableLesson,
    StructuredSkill,
    ValidationState,
)
from virgo.contracts.models.personal_runtime import PersonalPreference

SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_sources (
 source_id TEXT PRIMARY KEY, source_type TEXT NOT NULL, origin TEXT NOT NULL,
 content_hash TEXT, authority REAL NOT NULL, sensitivity TEXT NOT NULL,
 provenance TEXT NOT NULL, retrieved_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_evidence (
 evidence_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES knowledge_sources(source_id),
 excerpt TEXT NOT NULL, direct INTEGER NOT NULL, relevant INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_claims (
 claim_id TEXT PRIMARY KEY, statement TEXT NOT NULL, topic TEXT NOT NULL,
 evidence_ids TEXT NOT NULL, confidence REAL NOT NULL, status TEXT NOT NULL,
 scope TEXT NOT NULL, scope_key TEXT NOT NULL, privacy TEXT NOT NULL,
 provenance TEXT NOT NULL, created_at TEXT NOT NULL, last_verified_at TEXT,
 supersedes TEXT, superseded_by TEXT
);
CREATE INDEX IF NOT EXISTS knowledge_lookup
ON knowledge_claims(topic, scope, scope_key, status, created_at);
CREATE TABLE IF NOT EXISTS learning_audit (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, claim_id TEXT NOT NULL,
 action TEXT NOT NULL, reason TEXT NOT NULL, occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claim_evidence (
 claim_id TEXT NOT NULL REFERENCES knowledge_claims(claim_id) ON DELETE CASCADE,
 evidence_id TEXT NOT NULL REFERENCES knowledge_evidence(evidence_id),
 PRIMARY KEY(claim_id, evidence_id)
);
CREATE TABLE IF NOT EXISTS learning_assets (
 asset_id TEXT PRIMARY KEY, asset_type TEXT NOT NULL, name TEXT NOT NULL,
 version INTEGER NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS learning_asset_lookup
ON learning_assets(asset_type, name, status, version);
CREATE TABLE IF NOT EXISTS personal_preferences (
 preference_key TEXT NOT NULL, scope_key TEXT NOT NULL, value TEXT NOT NULL,
 provenance TEXT NOT NULL, updated_at TEXT NOT NULL,
 PRIMARY KEY(preference_key, scope_key)
);
"""


class SQLiteKnowledgeRepository:
    """Store only accepted claims; raw source contents never enter the database."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.connection: sqlite3.Connection | None = None

    def initialize(self) -> None:
        if self.connection is not None:
            return
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(
                self.database_path, check_same_thread=False
            )
            self.connection.execute("PRAGMA foreign_keys = ON")
            with self.connection:
                self.connection.executescript(SCHEMA)
        except (OSError, sqlite3.Error) as error:
            raise StorageError(
                "Knowledge repository could not be initialized",
                technical_detail=type(error).__name__,
                source_module=__name__,
            ) from error

    def store(
        self,
        claim: KnowledgeClaim,
        sources: tuple[LearningSource, ...] = (),
        evidence: tuple[Evidence, ...] = (),
    ) -> None:
        connection = self._connection()
        if claim.status is not ClaimStatus.VERIFIED:
            raise StorageError(
                "Only verified knowledge may be stored", source_module=__name__
            )
        with connection:
            for source in sources:
                connection.execute(
                    "INSERT OR IGNORE INTO knowledge_sources VALUES (?,?,?,?,?,?,?,?)",
                    (
                        source.source_id,
                        source.source_type.value,
                        source.origin,
                        source.content_hash,
                        source.authority,
                        source.sensitivity.value,
                        source.provenance,
                        source.retrieved_at.isoformat(),
                    ),
                )
            for item in evidence:
                connection.execute(
                    "INSERT OR IGNORE INTO knowledge_evidence VALUES (?,?,?,?,?)",
                    (
                        item.evidence_id,
                        item.source_id,
                        item.excerpt,
                        item.direct,
                        item.relevant,
                    ),
                )
            if claim.supersedes:
                connection.execute(
                    "UPDATE knowledge_claims SET status=?, superseded_by=? WHERE claim_id=?",
                    (ClaimStatus.SUPERSEDED.value, claim.claim_id, claim.supersedes),
                )
            connection.execute(
                "INSERT INTO knowledge_claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    claim.claim_id,
                    claim.statement,
                    claim.topic,
                    "\n".join(claim.evidence_ids),
                    claim.confidence,
                    claim.status.value,
                    claim.scope.value,
                    claim.scope_key,
                    claim.privacy.value,
                    claim.provenance,
                    claim.created_at.isoformat(),
                    (
                        claim.last_verified_at.isoformat()
                        if claim.last_verified_at
                        else None
                    ),
                    claim.supersedes,
                    claim.superseded_by,
                ),
            )
            connection.executemany(
                "INSERT INTO claim_evidence VALUES (?,?)",
                ((claim.claim_id, item) for item in claim.evidence_ids),
            )
            self._audit(connection, claim.claim_id, "accepted", "explicit acceptance")

    def provenance(self, claim_id: str) -> tuple[tuple[str, str, str], ...]:
        rows = (
            self._connection()
            .execute(
                "SELECT s.origin,s.provenance,e.excerpt FROM claim_evidence ce "
                "JOIN knowledge_evidence e ON e.evidence_id=ce.evidence_id "
                "JOIN knowledge_sources s ON s.source_id=e.source_id WHERE ce.claim_id=? "
                "ORDER BY e.evidence_id",
                (claim_id,),
            )
            .fetchall()
        )
        return tuple((str(row[0]), str(row[1]), str(row[2])) for row in rows)

    def store_lesson(self, lesson: ReusableLesson) -> None:
        self._store_asset(
            lesson.lesson_id,
            "lesson",
            lesson.statement,
            lesson.version,
            lesson.validation_status.value,
            {
                "statement": lesson.statement,
                "outcome_ids": lesson.outcome_ids,
                "evidence_refs": lesson.evidence_refs,
                "scope": lesson.scope.value,
                "scope_key": lesson.scope_key,
                "confidence": lesson.confidence,
                "applicability": lesson.applicability,
                "limitations": lesson.limitations,
                "provenance": lesson.provenance,
            },
        )

    def lessons(self) -> tuple[ReusableLesson, ...]:
        values = self._assets("lesson")
        return tuple(
            ReusableLesson(
                lesson_id=asset_id,
                statement=str(value["statement"]),
                outcome_ids=self._strings(value["outcome_ids"]),
                evidence_refs=self._strings(value["evidence_refs"]),
                scope=KnowledgeScope(str(value["scope"])),
                scope_key=str(value["scope_key"]),
                confidence=float(str(value["confidence"])),
                applicability=self._strings(value["applicability"]),
                limitations=self._strings(value["limitations"]),
                validation_status=ValidationState(status),
                provenance=str(value["provenance"]),
                version=version,
            )
            for asset_id, version, status, value in values
        )

    def store_skill(self, skill: StructuredSkill) -> None:
        self._store_asset(
            skill.skill_id,
            "skill",
            skill.name,
            skill.version,
            skill.status.value,
            {
                "name": skill.name,
                "objective": skill.objective,
                "applicability": skill.applicability,
                "prerequisites": skill.prerequisites,
                "guidance": skill.guidance,
                "tool_references": skill.tool_references,
                "permission_requirements": skill.permission_requirements,
                "validation": skill.validation,
                "failure_conditions": skill.failure_conditions,
                "rollback_guidance": skill.rollback_guidance,
                "provenance_refs": skill.provenance_refs,
            },
        )

    def skills(self) -> tuple[StructuredSkill, ...]:
        return tuple(
            StructuredSkill(
                skill_id=asset_id,
                name=str(value["name"]),
                objective=str(value["objective"]),
                applicability=self._strings(value["applicability"]),
                prerequisites=self._strings(value["prerequisites"]),
                guidance=self._strings(value["guidance"]),
                tool_references=self._strings(value["tool_references"]),
                permission_requirements=self._strings(value["permission_requirements"]),
                validation=self._strings(value["validation"]),
                failure_conditions=self._strings(value["failure_conditions"]),
                rollback_guidance=self._strings(value["rollback_guidance"]),
                provenance_refs=self._strings(value["provenance_refs"]),
                status=ValidationState(status),
                version=version,
            )
            for asset_id, version, status, value in self._assets("skill")
        )

    def store_evaluation(self, evaluation: EvaluationRecord) -> None:
        self._store_asset(
            evaluation.evaluation_id,
            "evaluation",
            evaluation.name,
            evaluation.version,
            "accepted" if evaluation.accepted else "rejected",
            {
                "name": evaluation.name,
                "evaluation_type": evaluation.evaluation_type.value,
                "input_reference": evaluation.input_reference,
                "expected": evaluation.expected,
                "scope": evaluation.scope.value,
                "scope_key": evaluation.scope_key,
                "provenance": evaluation.provenance,
                "privacy": evaluation.privacy.value,
                "accepted": evaluation.accepted,
            },
        )

    def evaluations(self) -> tuple[EvaluationRecord, ...]:
        return tuple(
            EvaluationRecord(
                evaluation_id=asset_id,
                name=str(value["name"]),
                evaluation_type=EvaluationType(str(value["evaluation_type"])),
                input_reference=str(value["input_reference"]),
                expected=str(value["expected"]),
                scope=KnowledgeScope(str(value["scope"])),
                scope_key=str(value["scope_key"]),
                provenance=str(value["provenance"]),
                privacy=PrivacyClassification(str(value["privacy"])),
                accepted=bool(value["accepted"]),
                version=version,
            )
            for asset_id, version, _status, value in self._assets("evaluation")
        )

    def retrieve(
        self, topic: str, scope: KnowledgeScope, scope_key: str
    ) -> tuple[KnowledgeClaim, ...]:
        rows = (
            self._connection()
            .execute(
                "SELECT * FROM knowledge_claims WHERE topic=? AND status=? AND "
                "((scope=? AND scope_key=?) OR scope=?) ORDER BY created_at, claim_id",
                (
                    topic,
                    ClaimStatus.VERIFIED.value,
                    scope.value,
                    scope_key,
                    KnowledgeScope.GLOBAL.value,
                ),
            )
            .fetchall()
        )
        return tuple(self._claim(row) for row in rows)

    def search_current(
        self,
        query: str,
        scope: KnowledgeScope,
        scope_key: str,
        *,
        limit: int = 5,
    ) -> tuple[KnowledgeClaim, ...]:
        """Return bounded verified matches from the exact scope plus global knowledge."""
        normalized = query.strip() if isinstance(query, str) else ""
        if not normalized or not 1 <= limit <= 20:
            return ()
        terms = tuple(
            dict.fromkeys(re.findall(r"[A-Za-z0-9_-]{3,}", normalized.casefold()))
        )[:8]
        if not terms:
            return ()
        clauses = " OR ".join("lower(topic || ' ' || statement) LIKE ?" for _ in terms)
        rows = (
            self._connection()
            .execute(
                "SELECT * FROM knowledge_claims WHERE status=? AND "
                "((scope=? AND scope_key=?) OR scope=?) AND ("
                f"{clauses}) ORDER BY last_verified_at DESC,created_at DESC,claim_id LIMIT ?",
                (
                    ClaimStatus.VERIFIED.value,
                    scope.value,
                    scope_key,
                    KnowledgeScope.GLOBAL.value,
                    *(f"%{term}%" for term in terms),
                    limit,
                ),
            )
            .fetchall()
        )
        return tuple(self._claim(row) for row in rows)

    def all_current(self) -> tuple[KnowledgeClaim, ...]:
        rows = (
            self._connection()
            .execute(
                "SELECT * FROM knowledge_claims WHERE status=? ORDER BY topic, created_at, claim_id",
                (ClaimStatus.VERIFIED.value,),
            )
            .fetchall()
        )
        return tuple(self._claim(row) for row in rows)

    def store_preference(self, preference: PersonalPreference) -> None:
        """Store an explicit preference separately from factual knowledge."""
        with self._connection():
            self._connection().execute(
                "INSERT OR REPLACE INTO personal_preferences VALUES (?,?,?,?,?)",
                (
                    preference.key,
                    preference.scope_key,
                    preference.value,
                    preference.provenance,
                    datetime.now().astimezone().isoformat(),
                ),
            )

    def preferences(self, scope_key: str) -> tuple[PersonalPreference, ...]:
        rows = (
            self._connection()
            .execute(
                "SELECT preference_key,value,scope_key,provenance "
                "FROM personal_preferences WHERE scope_key=? ORDER BY preference_key",
                (scope_key,),
            )
            .fetchall()
        )
        return tuple(
            PersonalPreference(
                key=str(row[0]),
                value=str(row[1]),
                scope_key=str(row[2]),
                provenance=str(row[3]),
            )
            for row in rows
        )

    def forget_preference(self, key: str, scope_key: str) -> bool:
        with self._connection():
            cursor = self._connection().execute(
                "DELETE FROM personal_preferences WHERE preference_key=? AND scope_key=?",
                (key, scope_key),
            )
        return cursor.rowcount == 1

    def forget(self, claim_id: str) -> bool:
        connection = self._connection()
        with connection:
            cursor = connection.execute(
                "DELETE FROM knowledge_claims WHERE claim_id=?", (claim_id,)
            )
            if cursor.rowcount:
                self._audit(connection, claim_id, "forgotten", "explicit user removal")
                connection.execute(
                    "DELETE FROM knowledge_evidence WHERE evidence_id NOT IN "
                    "(SELECT evidence_id FROM claim_evidence)"
                )

                connection.execute(
                    "DELETE FROM knowledge_sources WHERE source_id NOT IN "
                    "(SELECT source_id FROM knowledge_evidence)"
                )
        return cursor.rowcount == 1

    @property
    def database_size(self) -> int:
        return self.database_path.stat().st_size if self.database_path.exists() else 0

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def _connection(self) -> sqlite3.Connection:
        if self.connection is None:
            raise StorageError(
                "Knowledge repository is not initialized", source_module=__name__
            )
        return self.connection

    def _store_asset(
        self,
        asset_id: str,
        asset_type: str,
        name: str,
        version: int,
        status: str,
        payload: dict[str, object],
    ) -> None:
        connection = self._connection()
        with connection:
            connection.execute(
                "INSERT INTO learning_assets VALUES (?,?,?,?,?,?,?)",
                (
                    asset_id,
                    asset_type,
                    name,
                    version,
                    status,
                    json.dumps(payload, sort_keys=True),
                    datetime.now().astimezone().isoformat(),
                ),
            )
            self._audit(
                connection, asset_id, f"{asset_type}_stored", "explicit acceptance"
            )

    def _assets(
        self, asset_type: str
    ) -> tuple[tuple[str, int, str, dict[str, object]], ...]:
        rows = (
            self._connection()
            .execute(
                "SELECT asset_id,version,status,payload FROM learning_assets "
                "WHERE asset_type=? ORDER BY name,version,asset_id",
                (asset_type,),
            )
            .fetchall()
        )
        return tuple(
            (str(row[0]), int(str(row[1])), str(row[2]), json.loads(str(row[3])))
            for row in rows
        )

    @staticmethod
    def _strings(value: object) -> tuple[str, ...]:
        if not isinstance(value, list):
            raise StorageError(
                "Stored learning asset list is invalid", source_module=__name__
            )
        return tuple(str(item) for item in value)

    @staticmethod
    def _audit(
        connection: sqlite3.Connection, claim_id: str, action: str, reason: str
    ) -> None:
        connection.execute(
            "INSERT INTO learning_audit(claim_id,action,reason,occurred_at) VALUES(?,?,?,?)",
            (claim_id, action, reason, datetime.now().astimezone().isoformat()),
        )

    @staticmethod
    def _claim(row: tuple[object, ...]) -> KnowledgeClaim:
        return KnowledgeClaim(
            claim_id=str(row[0]),
            statement=str(row[1]),
            topic=str(row[2]),
            evidence_ids=tuple(str(row[3]).splitlines()),
            confidence=float(str(row[4])),
            status=ClaimStatus(str(row[5])),
            scope=KnowledgeScope(str(row[6])),
            scope_key=str(row[7]),
            privacy=PrivacyClassification(str(row[8])),
            provenance=str(row[9]),
            created_at=datetime.fromisoformat(str(row[10])),
            last_verified_at=(
                datetime.fromisoformat(str(row[11])) if row[11] else None
            ),
            supersedes=str(row[12]) if row[12] else None,
            superseded_by=str(row[13]) if row[13] else None,
        )
