"""Virgo-owned deterministic controlled-learning core."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import Event

from virgo.application import ApplicationStateStore
from virgo.application.permissions import ResearchPermissionGate
from virgo.capabilities.learning.experience import (
    EvaluationEngine,
    ExperienceLearningService,
    SelfInspectionService,
    SkillValidationService,
)
from virgo.contracts.errors import PermissionDeniedError, ValidationError
from virgo.contracts.events import (
    KnowledgeAcceptedEvent,
    KnowledgeGapDetectedEvent,
    LearningProposalReadyEvent,
)
from virgo.contracts.models.learning import (
    ClaimStatus,
    EvaluationExample,
    Evidence,
    KnowledgeClaim,
    KnowledgeGap,
    KnowledgeGapStatus,
    KnowledgeScope,
    LearningProposal,
    LearningSource,
    LearningSourceType,
    PrivacyClassification,
    QualityDecision,
    QualityEvaluation,
    ResearchPermissionRequest,
    ResearchProviderStatus,
    ResearchScope,
    SkillCandidate,
    TaskOutcomeLearningCandidate,
)
from virgo.infrastructure.events import EventDispatcher
from virgo.infrastructure.storage import SQLiteKnowledgeRepository

SECRET = re.compile(
    r"(?i)(?:api[_-]?key|password|token|secret)\s*[:=]\s*\S+|\b(?:sk|ghp)_[A-Za-z0-9]{12,}\b"
)


class KnowledgeQualityFilter:
    """Explainable policy; no model-produced trust score is accepted."""

    def evaluate(
        self,
        source: LearningSource,
        evidence: Evidence,
        *,
        duplicate: bool = False,
        contradictory: bool = False,
        corroborated: bool = False,
    ) -> QualityEvaluation:
        reasons: list[str] = []
        confidence = source.authority
        if not source.approved:
            return QualityEvaluation(
                decision=QualityDecision.REJECT,
                confidence=0,
                reasons=("source was not explicitly approved",),
            )
        if not evidence.relevant:
            return QualityEvaluation(
                decision=QualityDecision.REJECT,
                confidence=0,
                reasons=("evidence is irrelevant to the objective",),
            )
        if duplicate:
            reasons.append("duplicate evidence adds no independent confidence")
            confidence = min(confidence, 0.5)
        age_days = (datetime.now(UTC) - source.retrieved_at).days
        if age_days > 365:
            reasons.append("source may be stale")
            confidence = max(0.0, confidence - 0.2)
        if corroborated:
            reasons.append("independently corroborated")
            confidence = min(1.0, confidence + 0.1)
        if evidence.direct:
            reasons.append("direct evidence")
            confidence = min(1.0, confidence + 0.15)
        else:
            reasons.append("opinion or indirect evidence")
            confidence = max(0.0, confidence - 0.25)
        if contradictory:
            return QualityEvaluation(
                decision=QualityDecision.DISPUTED,
                confidence=confidence,
                reasons=tuple(reasons + ["conflicts with current verified knowledge"]),
                duplicate=duplicate,
                contradictory=True,
            )
        decision = (
            QualityDecision.ACCEPT if confidence >= 0.7 else QualityDecision.UNCERTAIN
        )
        reasons.append(f"contextual source authority={source.authority:.2f}")
        return QualityEvaluation(
            decision=decision,
            confidence=confidence,
            reasons=tuple(reasons),
            duplicate=duplicate,
        )


class UnconfiguredResearchProvider:
    status = ResearchProviderStatus.NOT_CONFIGURED

    def retrieve(
        self, request: ResearchPermissionRequest
    ) -> tuple[LearningSource, ...]:
        raise ValidationError(
            "Internet research provider is not configured", source_module=__name__
        )


class LearningEngine:
    """Coordinate permission, evidence, proposal, persistence, and retrieval."""

    def __init__(
        self,
        repository: SQLiteKnowledgeRepository,
        permission_gate: ResearchPermissionGate | None = None,
        dispatcher: EventDispatcher | None = None,
        state_store: ApplicationStateStore | None = None,
    ) -> None:
        self.repository = repository
        self.permission_gate = permission_gate or ResearchPermissionGate()
        self.dispatcher = dispatcher or EventDispatcher()
        self.state_store = state_store or ApplicationStateStore(self.dispatcher)
        self.quality = KnowledgeQualityFilter()
        self.research_provider = UnconfiguredResearchProvider()
        self.experience = ExperienceLearningService(repository)
        self.skills = SkillValidationService(repository)
        self.evaluations = EvaluationEngine(repository)
        self.self_inspection = SelfInspectionService(self.dispatcher, self.state_store)

    def detect_gap(
        self, topic: str, question: str, scope: KnowledgeScope, scope_key: str
    ) -> KnowledgeGap:
        known = self.repository.retrieve(topic, scope, scope_key)
        status = KnowledgeGapStatus.KNOWN if known else KnowledgeGapStatus.UNKNOWN
        reason = (
            "verified scoped knowledge is available"
            if known
            else "no verified scoped knowledge is available"
        )
        gap = KnowledgeGap(topic=topic, question=question, status=status, reason=reason)
        self.dispatcher.publish(
            KnowledgeGapDetectedEvent(
                gap_id=gap.gap_id, topic=gap.topic, status=gap.status.value
            )
        )
        return gap

    def request_research(
        self,
        gap: KnowledgeGap,
        source_types: tuple[LearningSourceType, ...],
        *,
        network_allowed: bool = False,
        persist_allowed: bool = False,
        sensitivity: PrivacyClassification = PrivacyClassification.PUBLIC,
    ) -> ResearchPermissionRequest:
        if gap.status is KnowledgeGapStatus.KNOWN:
            raise ValidationError(
                "Known knowledge does not require research", source_module=__name__
            )
        scope = ResearchScope(
            topic=gap.topic,
            source_types=source_types,
            network_allowed=network_allowed,
            persist_allowed=persist_allowed,
        )
        return ResearchPermissionRequest(
            topic=gap.topic,
            question=gap.question,
            reason=gap.reason,
            scope=scope,
            sensitivity=sensitivity,
        )

    def learn_documents(
        self,
        request: ResearchPermissionRequest,
        documents: tuple[Path, ...],
        *,
        knowledge_scope: KnowledgeScope,
        scope_key: str,
        cancellation: Event | None = None,
    ) -> LearningProposal:
        self.permission_gate.require(request)
        if LearningSourceType.USER_DOCUMENT not in request.scope.source_types:
            raise PermissionDeniedError(
                "Document source is outside approved research scope",
                source_module=__name__,
            )
        if len(documents) > request.scope.max_sources:
            raise ValidationError(
                "Document count exceeds approved research scope", source_module=__name__
            )
        cancellation = cancellation or Event()
        sources: list[LearningSource] = []
        evidence_items: list[Evidence] = []
        claims: list[KnowledgeClaim] = []
        evaluations: list[QualityEvaluation] = []
        contradictions: list[str] = []
        total_bytes = 0
        seen: set[str] = set()
        current = self.repository.retrieve(request.topic, knowledge_scope, scope_key)
        for path in documents:
            if cancellation.is_set():
                raise ValidationError(
                    "Learning task was cancelled", source_module=__name__
                )
            raw = path.read_bytes()
            total_bytes += len(raw)
            if total_bytes > request.scope.max_bytes:
                raise ValidationError(
                    "Document bytes exceed approved research scope",
                    source_module=__name__,
                )
            text = raw.decode("utf-8")
            source = LearningSource(
                source_type=LearningSourceType.USER_DOCUMENT,
                origin=str(path.resolve()),
                approved=True,
                content_hash=sha256(raw).hexdigest(),
                authority=0.8,
                sensitivity=request.sensitivity,
                provenance="USER_APPROVED_DOCUMENT",
            )
            sources.append(source)
            for line in text.splitlines():
                if not line.strip() or ":" not in line:
                    continue
                marker, statement = (part.strip() for part in line.split(":", 1))
                if marker.lower() not in {"fact", "opinion"} or not statement:
                    continue
                if SECRET.search(statement):
                    continue
                evidence = Evidence(
                    source_id=source.source_id,
                    excerpt=statement[:500],
                    direct=marker.lower() == "fact",
                )
                normalized = " ".join(statement.split())
                duplicate = normalized.casefold() in seen
                seen.add(normalized.casefold())
                contradictory = any(
                    item.statement.casefold() != normalized.casefold()
                    for item in (*current, *claims)
                    if item.status not in {ClaimStatus.REJECTED, ClaimStatus.DISPUTED}
                )
                evaluation = self.quality.evaluate(
                    source, evidence, duplicate=duplicate, contradictory=contradictory
                )
                status = {
                    QualityDecision.ACCEPT: ClaimStatus.CANDIDATE,
                    QualityDecision.REJECT: ClaimStatus.REJECTED,
                    QualityDecision.UNCERTAIN: ClaimStatus.CANDIDATE,
                    QualityDecision.DISPUTED: ClaimStatus.DISPUTED,
                }[evaluation.decision]
                claim = KnowledgeClaim(
                    statement=normalized,
                    topic=request.topic,
                    evidence_ids=(evidence.evidence_id,),
                    confidence=evaluation.confidence,
                    status=status,
                    scope=knowledge_scope,
                    scope_key=scope_key,
                    privacy=request.sensitivity,
                    provenance=source.provenance,
                )
                evidence_items.append(evidence)
                claims.append(claim)
                evaluations.append(evaluation)
                if contradictory:
                    contradictions.append(claim.claim_id)
                if len(claims) >= request.scope.max_claims:
                    break
        if not claims:
            raise ValidationError(
                "No safe structured claims were extracted", source_module=__name__
            )
        proposal = LearningProposal(
            claims=tuple(claims),
            sources=tuple(sources),
            evidence=tuple(evidence_items),
            evaluations=tuple(evaluations),
            contradictions=tuple(contradictions),
            intended_persistence=request.scope.persist_allowed,
        )
        self.dispatcher.publish(
            LearningProposalReadyEvent(
                correlation_id=request.task_id,
                proposal_id=proposal.proposal_id,
                source_count=len(proposal.sources),
                claim_count=len(proposal.claims),
                disputed_count=len(proposal.contradictions),
            )
        )
        return proposal

    def accept(self, proposal: LearningProposal) -> tuple[KnowledgeClaim, ...]:
        if not proposal.intended_persistence:
            raise PermissionDeniedError(
                "Research scope did not approve persistence", source_module=__name__
            )
        accepted: list[KnowledgeClaim] = []
        for claim, evaluation in zip(
            proposal.claims, proposal.evaluations, strict=True
        ):
            if evaluation.decision is not QualityDecision.ACCEPT:
                continue
            verified = replace(
                claim, status=ClaimStatus.VERIFIED, last_verified_at=datetime.now(UTC)
            )
            claim_evidence = tuple(
                item
                for item in proposal.evidence
                if item.evidence_id in claim.evidence_ids
            )
            source_ids = {item.source_id for item in claim_evidence}
            claim_sources = tuple(
                item for item in proposal.sources if item.source_id in source_ids
            )
            self.repository.store(verified, claim_sources, claim_evidence)
            accepted.append(verified)
        self.dispatcher.publish(
            KnowledgeAcceptedEvent(
                proposal_id=proposal.proposal_id, accepted_count=len(accepted)
            )
        )
        return tuple(accepted)

    def accept_correction(
        self, existing: KnowledgeClaim, corrected_statement: str
    ) -> KnowledgeClaim:
        if SECRET.search(corrected_statement):
            raise ValidationError(
                "Sensitive values cannot become learned knowledge",
                source_module=__name__,
            )
        source = LearningSource(
            source_type=LearningSourceType.CORRECTED_RESPONSE,
            origin="explicit-user-correction",
            approved=True,
            content_hash=None,
            authority=1.0,
            sensitivity=existing.privacy,
            provenance="USER_CORRECTION",
        )
        evidence = Evidence(
            source_id=source.source_id,
            excerpt=corrected_statement[:500],
            direct=True,
        )
        correction = KnowledgeClaim(
            statement=corrected_statement,
            topic=existing.topic,
            evidence_ids=(evidence.evidence_id,),
            confidence=1.0,
            status=ClaimStatus.VERIFIED,
            scope=existing.scope,
            scope_key=existing.scope_key,
            privacy=existing.privacy,
            provenance="USER_CORRECTION",
            supersedes=existing.claim_id,
            last_verified_at=datetime.now(UTC),
        )
        self.repository.store(correction, (source,), (evidence,))
        return correction

    @staticmethod
    def outcome_candidate(
        task_id: str, outcome: str, lesson: str, scope: KnowledgeScope
    ) -> TaskOutcomeLearningCandidate:
        return TaskOutcomeLearningCandidate(
            task_id=task_id,
            outcome=outcome,
            lesson=lesson,
            scope=scope,
            reusable=bool(lesson.strip()),
        )

    @staticmethod
    def skill_candidate(
        name: str, guidance: tuple[str, ...], claim_ids: tuple[str, ...]
    ) -> SkillCandidate:
        return SkillCandidate(name=name, guidance=guidance, source_claim_ids=claim_ids)

    @staticmethod
    def evaluation_example(
        input_text: str, expected: str, claim_ids: tuple[str, ...]
    ) -> EvaluationExample:
        return EvaluationExample(
            input_text=input_text,
            expected_behavior=expected,
            source_claim_ids=claim_ids,
        )
