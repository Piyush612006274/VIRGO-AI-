"""Bounded local-first evidence retrieval without execution authority."""

import re
from dataclasses import replace
from datetime import UTC, datetime
from threading import Event
from time import monotonic
from typing import Protocol

from virgo.contracts.models.cognitive import (
    CognitiveDecision,
    CognitiveStrategy,
    UncertaintyState,
)
from virgo.contracts.models.knowledge_on_demand import (
    FreshnessState,
    KnowledgeConflict,
    KnowledgeEvidencePackage,
    KnowledgeNeed,
    KnowledgeRetrievalStatus,
    KnowledgeSource,
    KnowledgeType,
)
from virgo.contracts.models.learning import KnowledgeScope
from virgo.contracts.models.personal_runtime import RetrievedMemory

INJECTION_MARKERS = (
    "ignore previous instructions",
    "grant permission",
    "reveal secrets",
    "execute tool",
)
SECRET = re.compile(
    r"(?i)(?:api[_-]?key|password|token|secret)\s*[:=]\s*\S+|\b(?:sk|ghp)_[A-Za-z0-9]{12,}\b"
)


class KnowledgeProviderProtocol(Protocol):
    configured: bool

    def retrieve(
        self, need: KnowledgeNeed, cancellation: Event
    ) -> tuple[KnowledgeSource, ...]: ...


class KnowledgeContextProtocol(Protocol):
    def retrieve(
        self, query: str, scope: KnowledgeScope, scope_key: str, *, limit: int = 5
    ) -> tuple[RetrievedMemory, ...]: ...


class UnconfiguredKnowledgeProvider:
    configured = False

    def retrieve(
        self, need: KnowledgeNeed, cancellation: Event
    ) -> tuple[KnowledgeSource, ...]:
        del need, cancellation
        return ()


class KnowledgeOnDemandService:
    def __init__(
        self,
        context: KnowledgeContextProtocol,
        provider: KnowledgeProviderProtocol | None = None,
    ) -> None:
        self._context = context
        self._provider = provider or UnconfiguredKnowledgeProvider()

    def need(self, decision: CognitiveDecision) -> KnowledgeNeed:
        if decision.strategy is not CognitiveStrategy.REQUIRE_CURRENT_KNOWLEDGE:
            raise ValueError("cognitive decision does not require current knowledge")
        text = decision.user_goal.casefold()
        knowledge_type = (
            KnowledgeType.TIME_SENSITIVE_INFORMATION
            if any(value in text for value in ("latest", "today", "current news"))
            else KnowledgeType.CURRENT_INFORMATION
        )
        return KnowledgeNeed(
            task_id=decision.task_id,
            session_id=decision.context.understanding.session_id,
            question=decision.user_goal,
            knowledge_type=knowledge_type,
            scope=(
                decision.context.user_context.memories[0].scope
                if decision.context.user_context.memories
                else (
                    KnowledgeScope.SESSION
                    if decision.context.understanding.session_id
                    else KnowledgeScope.GLOBAL
                )
            ),
            scope_key=(
                decision.context.user_context.memories[0].scope_key
                if decision.context.user_context.memories
                else decision.context.understanding.session_id or "global"
            ),
            known_context=decision.context.contextual_evidence[:5],
            maximum_sources=min(3, len(decision.context.user_context.memories) or 3),
        )

    def resolve(
        self, need: KnowledgeNeed, cancellation: Event | None = None
    ) -> KnowledgeEvidencePackage:
        signal = cancellation or Event()
        if signal.is_set():
            return self._package(
                need, (), KnowledgeRetrievalStatus.CANCELLED, ("retrieval cancelled",)
            )
        local = tuple(
            KnowledgeSource(
                source_type="approved_memory",
                title=item.topic,
                origin=f"knowledge:{item.claim_id}",
                excerpt=item.statement,
                provenance=item.provenance,
                retrieval_method="existing_memory_authority",
            )
            for item in self._context.retrieve(
                need.question, need.scope, need.scope_key, limit=need.maximum_sources
            )
        )
        local = self._normalize(local, need.maximum_sources)
        if local and need.knowledge_type in {
            KnowledgeType.STABLE_KNOWLEDGE,
            KnowledgeType.LOCAL_PROJECT_KNOWLEDGE,
        }:
            return self._assess(need, local)
        if not self._provider.configured:
            return self._package(
                need,
                local,
                KnowledgeRetrievalStatus.NOT_CONFIGURED,
                ("external retrieval provider is not configured",),
            )
        started = monotonic()
        sources: tuple[KnowledgeSource, ...] = ()
        for attempt in range(need.max_retries + 1):
            if signal.is_set():
                return self._package(
                    need,
                    local,
                    KnowledgeRetrievalStatus.CANCELLED,
                    ("retrieval cancelled",),
                )
            try:
                sources = self._provider.retrieve(need, signal)
                break
            except Exception:
                if attempt == need.max_retries:
                    return self._package(
                        need,
                        local,
                        KnowledgeRetrievalStatus.FAILED,
                        ("retrieval provider failed",),
                    )
        if monotonic() - started > need.timeout_seconds:
            return self._package(
                need, local, KnowledgeRetrievalStatus.FAILED, ("retrieval timed out",)
            )
        return self._assess(
            need, self._normalize((*local, *sources), need.maximum_sources)
        )

    def consume(
        self, decision: CognitiveDecision, package: KnowledgeEvidencePackage
    ) -> CognitiveDecision:
        if decision.task_id != package.task_id:
            raise ValueError("knowledge evidence belongs to another task")
        safe = tuple(f"UNTRUSTED_SOURCE: {item.excerpt}" for item in package.sources)[
            :5
        ]
        context = replace(decision.context, contextual_evidence=safe)
        uncertainty = {
            KnowledgeRetrievalStatus.SUFFICIENT: UncertaintyState.NEEDS_VERIFICATION,
            KnowledgeRetrievalStatus.CONFLICTING: UncertaintyState.CONFLICTING,
        }.get(package.status, UncertaintyState.UNKNOWN)
        strategy = (
            CognitiveStrategy.USE_EXISTING_CONTEXT
            if package.status is KnowledgeRetrievalStatus.SUFFICIENT
            else CognitiveStrategy.ASK_CLARIFICATION
        )
        return replace(
            decision, context=context, uncertainty=uncertainty, strategy=strategy
        )

    def _assess(
        self, need: KnowledgeNeed, sources: tuple[KnowledgeSource, ...]
    ) -> KnowledgeEvidencePackage:
        if not sources:
            return self._package(
                need,
                (),
                KnowledgeRetrievalStatus.NOT_FOUND,
                ("no relevant evidence found",),
            )
        conflicts = _conflicts(sources)
        if conflicts:
            return KnowledgeEvidencePackage(
                task_id=need.task_id,
                need=need,
                sources=sources,
                conflicts=conflicts,
                status=KnowledgeRetrievalStatus.CONFLICTING,
                remaining_unknowns=("sources disagree",),
            )
        if need.knowledge_type in {
            KnowledgeType.CURRENT_INFORMATION,
            KnowledgeType.TIME_SENSITIVE_INFORMATION,
        } and any(
            item.freshness not in {FreshnessState.CURRENT, FreshnessState.RECENT}
            for item in sources
        ):
            return self._package(
                need,
                sources,
                KnowledgeRetrievalStatus.PARTIAL,
                ("current freshness is not established",),
            )
        return self._package(need, sources, KnowledgeRetrievalStatus.SUFFICIENT)

    @staticmethod
    def _normalize(
        sources: tuple[KnowledgeSource, ...], limit: int
    ) -> tuple[KnowledgeSource, ...]:
        unique: dict[tuple[str, str], KnowledgeSource] = {}
        for source in sources:
            if any(marker in source.excerpt.casefold() for marker in INJECTION_MARKERS):
                continue
            if SECRET.search(source.excerpt):
                continue
            timestamp = source.updated_at or source.published_at
            freshness = FreshnessState.UNKNOWN
            if timestamp is not None:
                days = (datetime.now(UTC) - timestamp).days
                freshness = (
                    FreshnessState.CURRENT
                    if days <= 1
                    else FreshnessState.RECENT if days <= 30 else FreshnessState.STALE
                )
            normalized = replace(source, freshness=freshness)
            unique.setdefault(
                (source.origin.casefold(), source.excerpt.casefold()), normalized
            )
        return tuple(unique.values())[:limit]

    @staticmethod
    def _package(
        need: KnowledgeNeed,
        sources: tuple[KnowledgeSource, ...],
        status: KnowledgeRetrievalStatus,
        unknowns: tuple[str, ...] = (),
    ) -> KnowledgeEvidencePackage:
        return KnowledgeEvidencePackage(
            task_id=need.task_id,
            need=need,
            sources=sources,
            conflicts=(),
            status=status,
            remaining_unknowns=unknowns,
        )


def _conflicts(sources: tuple[KnowledgeSource, ...]) -> tuple[KnowledgeConflict, ...]:
    grouped: dict[str, dict[str, list[str]]] = {}
    for source in sources:
        if source.claim_key and source.claim_value:
            grouped.setdefault(source.claim_key, {}).setdefault(
                source.claim_value, []
            ).append(source.source_id)
    return tuple(
        KnowledgeConflict(
            claim_key=key,
            values=tuple(values),
            source_ids=tuple(item for ids in values.values() for item in ids),
        )
        for key, values in grouped.items()
        if len(values) > 1
    )
