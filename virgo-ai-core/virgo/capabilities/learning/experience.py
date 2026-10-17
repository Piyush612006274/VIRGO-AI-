"""Bounded experience, evaluation, skill, and self-inspection services."""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from threading import Event
from time import monotonic

from virgo.application import ApplicationStateStore
from virgo.capabilities.security import SecurityAnalysisCoordinator
from virgo.contracts.errors import SecurityViolationError, ValidationError
from virgo.contracts.events import (
    ImprovementProposalReadyEvent,
    SelfInspectionCompletedEvent,
    SelfInspectionStartedEvent,
)
from virgo.contracts.models import (
    DefensiveObjective,
    SecurityAnalysisRequest,
    SecurityScope,
    SecurityTarget,
    SecurityTargetType,
)
from virgo.contracts.models.learning_experience import (
    CauseStatus,
    ComparisonResult,
    EvaluationComparison,
    EvaluationEvidence,
    EvaluationRecord,
    EvaluationType,
    FailureAnalysis,
    FailureCategory,
    FailureCause,
    FindingSeverity,
    ImprovementOpportunity,
    ImprovementProposal,
    ReusableLesson,
    SelfInspectionCategory,
    SelfInspectionEvidence,
    SelfInspectionFinding,
    SelfInspectionPlan,
    SelfInspectionRequest,
    SelfInspectionResult,
    StructuredSkill,
    TaskOutcome,
    TaskOutcomeStatus,
    ValidationState,
)
from virgo.infrastructure.events import EventDispatcher
from virgo.infrastructure.storage import SQLiteKnowledgeRepository

EXCLUDED = {".git", ".venv", "__pycache__", "node_modules", "target", "data"}
ALLOWED_SKILL_CAPABILITIES = {"conversation", "creation", "security", "learning"}


class ExperienceLearningService:
    def __init__(self, repository: SQLiteKnowledgeRepository) -> None:
        self.repository = repository

    def analyze_failure(self, outcome: TaskOutcome) -> FailureAnalysis:
        category = outcome.failure_category or self._category(outcome.outcome)
        observed = (
            f"Outcome {outcome.outcome.value}; validation: {outcome.validation_summary}"
        )
        reusable = category in {
            FailureCategory.SYSTEM_DEFECT,
            FailureCategory.KNOWLEDGE_GAP,
            FailureCategory.PROCESS_DEFECT,
        }
        cause = FailureCause(
            statement=f"The recorded {category.value} may explain this outcome",
            evidence_refs=(outcome.correlation_id,),
            confidence=0.8 if outcome.failure_category else 0.55,
            status=(
                CauseStatus.SUPPORTED
                if outcome.failure_category
                else CauseStatus.UNVERIFIED
            ),
        )
        return FailureAnalysis(
            outcome_id=outcome.task_id,
            category=category,
            facts=(observed,),
            inferences=(cause.statement,) if reusable else (),
            unknowns=(
                ()
                if outcome.failure_category
                else ("root cause requires verification",)
            ),
            causes=(cause,),
            recommended_verification=("Reproduce under the same bounded scope",),
        )

    def lesson(self, outcome: TaskOutcome) -> ReusableLesson | None:
        if outcome.outcome is TaskOutcomeStatus.SUCCESS:
            statement = f"For {outcome.objective}, retain the validated {outcome.capability} workflow."
            confidence = 0.75
        else:
            analysis = self.analyze_failure(outcome)
            if not analysis.inferences:
                return None
            statement = f"For {outcome.capability}, verify {analysis.category.value} before retrying."
            confidence = analysis.causes[0].confidence
        return ReusableLesson(
            statement=statement,
            outcome_ids=(outcome.task_id,),
            evidence_refs=(outcome.correlation_id,),
            scope=outcome.scope,
            scope_key=outcome.scope_key,
            confidence=confidence,
            applicability=(outcome.capability, outcome.objective),
            limitations=("One outcome does not establish universal correctness",),
            validation_status=ValidationState.VALIDATED,
            provenance="VALIDATED_TASK_OUTCOME",
        )

    def accept_lesson(self, lesson: ReusableLesson) -> ReusableLesson:
        if lesson.validation_status is not ValidationState.VALIDATED:
            raise ValidationError(
                "Only validated lessons may be accepted", source_module=__name__
            )
        accepted = replace(lesson, validation_status=ValidationState.ACCEPTED)
        self.repository.store_lesson(accepted)
        return accepted

    @staticmethod
    def repeated_failure_opportunity(
        outcomes: tuple[TaskOutcome, ...],
    ) -> ImprovementOpportunity | None:
        if len(outcomes) > 100:
            raise ValidationError(
                "Outcome aggregation exceeds the bounded limit", source_module=__name__
            )
        keys = Counter(
            (item.capability, item.failure_category)
            for item in outcomes
            if item.failure_category
        )
        repeated = next((key for key, count in keys.items() if count >= 2), None)
        if repeated is None:
            return None
        matching = tuple(
            item
            for item in outcomes
            if (item.capability, item.failure_category) == repeated
        )
        return ImprovementOpportunity(
            problem=f"Repeated {repeated[1].value} outcomes in {repeated[0]}",
            evidence_ids=tuple(item.correlation_id for item in matching),
            affected_subsystem=repeated[0],
            severity=FindingSeverity.MEDIUM,
            confidence=min(0.95, 0.6 + len(matching) * 0.1),
            suggested_objective="Prevent the repeated validated failure pattern",
            expected_benefit="Fewer repeated failures under the same scope",
            risk_category="proposal_only",
        )

    @staticmethod
    def _category(outcome: TaskOutcomeStatus) -> FailureCategory:
        return {
            TaskOutcomeStatus.PROVIDER_UNAVAILABLE: FailureCategory.ENVIRONMENTAL,
            TaskOutcomeStatus.VALIDATION_FAILED: FailureCategory.PROCESS_DEFECT,
            TaskOutcomeStatus.SECURITY_REJECTED: FailureCategory.USER_ERROR,
            TaskOutcomeStatus.USER_CORRECTED: FailureCategory.KNOWLEDGE_GAP,
        }.get(outcome, FailureCategory.UNKNOWN)


class SkillValidationService:
    def __init__(self, repository: SQLiteKnowledgeRepository) -> None:
        self.repository = repository

    def validate(self, skill: StructuredSkill) -> StructuredSkill:
        if any(
            item not in ALLOWED_SKILL_CAPABILITIES for item in skill.tool_references
        ):
            raise ValidationError(
                "Skill references an unregistered capability", source_module=__name__
            )
        if any(
            "permission" not in item.casefold()
            for item in skill.permission_requirements
        ):
            raise ValidationError(
                "Skill permission requirements are not explicit", source_module=__name__
            )
        if (
            "mutation" in " ".join(skill.applicability).casefold()
            and not skill.rollback_guidance
        ):
            raise ValidationError(
                "Mutation guidance requires rollback guidance", source_module=__name__
            )
        return replace(skill, status=ValidationState.VALIDATED)

    def accept(self, skill: StructuredSkill) -> StructuredSkill:
        if skill.status is not ValidationState.VALIDATED:
            raise ValidationError(
                "Only validated skills may be accepted", source_module=__name__
            )
        active = replace(skill, status=ValidationState.ACTIVE)
        self.repository.store_skill(active)
        return active


class EvaluationEngine:
    def __init__(self, repository: SQLiteKnowledgeRepository) -> None:
        self.repository = repository

    def accept(self, evaluation: EvaluationRecord) -> None:
        if not evaluation.accepted:
            raise ValidationError(
                "Rejected evaluations cannot be persisted", source_module=__name__
            )
        self.repository.store_evaluation(evaluation)

    def compare(
        self,
        evaluations: tuple[EvaluationRecord, ...],
        baseline: dict[str, str],
        candidate: dict[str, str],
    ) -> EvaluationComparison:
        if not evaluations or len(evaluations) > 100:
            raise ValidationError(
                "Evaluation comparison requires 1-100 examples", source_module=__name__
            )
        evidence: list[EvaluationEvidence] = []
        improved = regressed = False
        for item in evaluations:
            before = self._passes(item, baseline.get(item.input_reference))
            after = self._passes(item, candidate.get(item.input_reference))
            improved |= before is False and after is True
            regressed |= before is True and after is False
            evidence.append(
                EvaluationEvidence(
                    evaluation_id=item.evaluation_id,
                    baseline_passed=before,
                    candidate_passed=after,
                    detail=f"baseline={before}; candidate={after}",
                )
            )
        result = (
            ComparisonResult.REGRESSED
            if regressed
            else (
                ComparisonResult.IMPROVED
                if improved
                else (
                    ComparisonResult.INCONCLUSIVE
                    if any(item.candidate_passed is None for item in evidence)
                    else ComparisonResult.UNCHANGED
                )
            )
        )
        return EvaluationComparison(
            result=result,
            evidence=tuple(evidence),
            passed=sum(item.candidate_passed is True for item in evidence),
            failed=sum(item.candidate_passed is False for item in evidence),
            regression_detected=regressed,
        )

    @staticmethod
    def _passes(evaluation: EvaluationRecord, actual: str | None) -> bool | None:
        if actual is None:
            return None
        if evaluation.evaluation_type is EvaluationType.CONTAINS_REQUIRED_FACT:
            return evaluation.expected in actual
        if evaluation.evaluation_type is EvaluationType.DOES_NOT_CONTAIN_FORBIDDEN_FACT:
            return evaluation.expected not in actual
        return actual == evaluation.expected


class SelfInspectionService:
    def __init__(
        self,
        dispatcher: EventDispatcher,
        state_store: ApplicationStateStore,
    ) -> None:
        self.dispatcher = dispatcher
        self.state_store = state_store

    def inspect(
        self, request: SelfInspectionRequest, cancellation: Event | None = None
    ) -> SelfInspectionResult:
        started = monotonic()
        cancellation = cancellation or Event()
        root = Path(request.scope.repository_root)
        if (
            not root.is_absolute()
            or not root.is_dir()
            or str(root.resolve(strict=True)) != str(root)
        ):
            raise SecurityViolationError(
                "Inspection root must be an exact canonical directory",
                source_module=__name__,
            )
        plan = SelfInspectionPlan(
            request_id=request.request_id, categories=request.scope.categories
        )
        self.dispatcher.publish(
            SelfInspectionStartedEvent(
                correlation_id=request.request_id,
                request_id=request.request_id,
                category_count=len(plan.categories),
            )
        )
        files = tuple(
            self._files(root, request.scope.max_files, request.scope.max_file_bytes)
        )
        evidence: list[SelfInspectionEvidence] = []
        findings: list[SelfInspectionFinding] = []
        for category in request.scope.categories:
            if cancellation.is_set():
                break
            category_evidence, category_findings = self._category(category, root, files)
            evidence.extend(category_evidence)
            findings.extend(category_findings)
            if len(findings) >= request.scope.max_findings:
                findings = findings[: request.scope.max_findings]
                break
        if (
            SelfInspectionCategory.SECURITY_REVIEW in request.scope.categories
            and not cancellation.is_set()
        ):
            security_result = SecurityAnalysisCoordinator(
                self.dispatcher, self.state_store
            ).analyze(
                SecurityAnalysisRequest(
                    scope=SecurityScope(
                        target=SecurityTarget(
                            target_type=SecurityTargetType.LOCAL_PROJECT, root=str(root)
                        ),
                        ownership_confirmed=True,
                    ),
                    objective=DefensiveObjective.SECURE_CODE_REVIEW,
                ),
                cancellation,
            )
            summary = f"Reused Stage 3 security analysis: {len(security_result.findings)} findings"
            evidence.append(
                SelfInspectionEvidence(
                    category=SelfInspectionCategory.SECURITY_REVIEW,
                    path=".",
                    summary=summary,
                )
            )
        opportunities = tuple(self.opportunity(item) for item in findings)
        proposals = tuple(self.proposal(item) for item in opportunities)
        result = SelfInspectionResult(
            plan=plan,
            evidence=tuple(evidence),
            findings=tuple(findings),
            opportunities=opportunities,
            proposals=proposals,
            duration_seconds=monotonic() - started,
            files_inspected=len(files),
            cancelled=cancellation.is_set(),
        )
        if proposals:
            self.dispatcher.publish(
                ImprovementProposalReadyEvent(
                    correlation_id=request.request_id,
                    request_id=request.request_id,
                    proposal_count=len(proposals),
                )
            )
        self.dispatcher.publish(
            SelfInspectionCompletedEvent(
                correlation_id=request.request_id,
                request_id=request.request_id,
                finding_count=len(findings),
                cancelled=result.cancelled,
                mutation_performed=result.mutation_performed,
            )
        )
        return result

    @staticmethod
    def opportunity(finding: SelfInspectionFinding) -> ImprovementOpportunity:
        return ImprovementOpportunity(
            problem=finding.description,
            evidence_ids=finding.evidence_ids,
            affected_subsystem=finding.category.value,
            severity=finding.severity,
            confidence=finding.confidence,
            suggested_objective=f"Resolve {finding.title}",
            expected_benefit="Improve verified architecture or quality compliance",
            risk_category="requires_step_3_review",
        )

    @staticmethod
    def proposal(opportunity: ImprovementOpportunity) -> ImprovementProposal:
        return ImprovementProposal(
            opportunity_id=opportunity.opportunity_id,
            problem=opportunity.problem,
            evidence_ids=opportunity.evidence_ids,
            proposed_change_concept=f"Prepare a separately approved correction for {opportunity.affected_subsystem}",
            target_subsystem=opportunity.affected_subsystem,
            expected_benefit=opportunity.expected_benefit,
            risks=("Incorrect correction could introduce regression",),
            estimated_scope=(opportunity.affected_subsystem,),
            validation_plan=("Run focused tests", "Run full regression"),
            security_checks=("Run Stage 3 security analysis",),
            rollback_expectations=("Use a separate branch and rollback on failure",),
            evaluation_plan=("Compare baseline and candidate evaluations",),
        )

    def _category(
        self,
        category: SelfInspectionCategory,
        root: Path,
        files: tuple[Path, ...],
    ) -> tuple[list[SelfInspectionEvidence], list[SelfInspectionFinding]]:
        evidence: list[SelfInspectionEvidence] = []
        findings: list[SelfInspectionFinding] = []
        if category is SelfInspectionCategory.ARCHITECTURE_COMPLIANCE:
            violations = [
                path
                for path in files
                if (
                    "virgo/capabilities" in path.relative_to(root).as_posix()
                    and "PySide6" in path.read_text(encoding="utf-8", errors="ignore")
                )
                or "browser_automation" in path.name
            ]
            for path in violations:
                item = SelfInspectionEvidence(
                    category=category,
                    path=path.relative_to(root).as_posix(),
                    summary="Deterministic architecture boundary violation",
                    content_hash=sha256(path.read_bytes()).hexdigest(),
                )
                evidence.append(item)
                findings.append(
                    SelfInspectionFinding(
                        category=category,
                        title="Architecture boundary violation",
                        description=f"Forbidden coupling detected in {item.path}",
                        severity=FindingSeverity.HIGH,
                        confidence=1.0,
                        evidence_ids=(item.evidence_id,),
                    )
                )
        elif category is SelfInspectionCategory.STATIC_ANALYSIS:
            invalid = []
            for path in (item for item in files if item.suffix == ".py"):
                try:
                    ast.parse(path.read_text(encoding="utf-8"))
                except (SyntaxError, UnicodeDecodeError):
                    invalid.append(path)
            evidence.append(
                SelfInspectionEvidence(
                    category=category,
                    path=".",
                    summary=f"Parsed {sum(item.suffix == '.py' for item in files)} Python files; invalid={len(invalid)}",
                )
            )
        elif category is SelfInspectionCategory.DEPENDENCY_REVIEW:
            manifests = [
                item
                for item in files
                if item.name
                in {"pyproject.toml", "Cargo.toml", "requirements.txt", "package.json"}
            ]
            evidence.append(
                SelfInspectionEvidence(
                    category=category,
                    path=".",
                    summary=f"Found {len(manifests)} dependency manifests; no CVE intelligence claimed",
                )
            )
        elif category is SelfInspectionCategory.TEST_COVERAGE_REVIEW:
            tests = sum(item.name.startswith("test_") for item in files)
            evidence.append(
                SelfInspectionEvidence(
                    category=category,
                    path="tests",
                    summary=f"Detected {tests} test modules; COVERAGE_PERCENTAGE_NOT_AVAILABLE",
                )
            )
        elif category is SelfInspectionCategory.PERFORMANCE_REVIEW:
            evidence.append(
                SelfInspectionEvidence(
                    category=category,
                    path=".",
                    summary=f"Bounded inventory contained {len(files)} files; no optimization claim",
                )
            )
        elif category is SelfInspectionCategory.FAILURE_ANALYSIS:
            evidence.append(
                SelfInspectionEvidence(
                    category=category,
                    path=".",
                    summary="No structured failure outcomes supplied to this inspection",
                )
            )
        elif category is SelfInspectionCategory.SECURITY_REVIEW:
            pass
        return evidence, findings

    @staticmethod
    def _files(root: Path, maximum: int, max_bytes: int):  # type: ignore[no-untyped-def]
        count = 0
        for path in sorted(root.rglob("*")):
            if count >= maximum:
                return
            if not path.is_file() or any(
                part in EXCLUDED for part in path.relative_to(root).parts
            ):
                continue
            try:
                if path.stat().st_size > max_bytes:
                    continue
            except OSError:
                continue
            count += 1
            yield path
