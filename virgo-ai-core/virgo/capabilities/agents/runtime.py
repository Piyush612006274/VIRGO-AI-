"""Deterministic Stage 5 coordinator; capabilities remain separately owned."""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from platform import system
from queue import Queue
from threading import Event, Thread
from time import monotonic

from virgo.application import ApplicationStateStore
from virgo.capabilities.creation import SafeWorkspace
from virgo.capabilities.creation.workspace import SENSITIVE_FILE_NAMES
from virgo.capabilities.tools import CancellationToken, ValidationProcessTool
from virgo.contracts.errors import PermissionDeniedError, ValidationError
from virgo.contracts.events import (
    ApplicationState,
    PersonalTaskCancelledEvent,
    PersonalTaskCompletedEvent,
    PersonalTaskFailedEvent,
    PersonalTaskPlanCreatedEvent,
    PersonalTaskStartedEvent,
)
from virgo.contracts.models.capability_execution import (
    CapabilityDescriptor,
    CapabilityExecutionEvidence,
    CapabilityExecutionRequest,
    CapabilityExecutionResult,
    CapabilityExecutionStatus,
    CapabilityResolution,
    CapabilityResolutionStatus,
    CapabilityType,
    EnvironmentFacts,
    RollbackState,
)
from virgo.contracts.models.cognitive import (
    CognitiveDecision,
    CognitiveStrategy,
    UncertaintyState,
)
from virgo.contracts.models.conversation import ConversationUnderstanding
from virgo.contracts.models.correlation import new_correlation_id
from virgo.contracts.models.creation_execution import ProcessRequest
from virgo.contracts.models.knowledge_on_demand import (
    KnowledgeEvidencePackage,
    KnowledgeNeed,
)
from virgo.contracts.models.learning import KnowledgeScope
from virgo.contracts.models.personal_runtime import (
    ActionRisk,
    AgentDefinition,
    AgentType,
    MemoryCandidate,
    PersonalCapability,
    PersonalPreference,
    PersonalTaskPermission,
    PersonalTaskPlan,
    PersonalTaskRequest,
    PersonalTaskResult,
    PersonalTaskStatus,
    PersonalTaskStep,
    PersonalTaskVerification,
    RetrievedMemory,
    RuntimeProviderStatus,
    RuntimeTool,
    UserContext,
)
from virgo.contracts.models.verification import (
    VerificationRequest,
    VerificationResult,
    VerificationStatus,
)
from virgo.infrastructure.events import EventDispatcher
from virgo.infrastructure.storage import SQLiteKnowledgeRepository
from virgo.intelligence.cognitive import (
    BoundedCognitivePlanner,
    CognitiveContextBuilder,
)
from virgo.intelligence.knowledge_on_demand import KnowledgeOnDemandService
from virgo.intelligence.verification import ResponseVerifier

CapabilityHandler = Callable[[PersonalTaskRequest, PersonalTaskStep, Event], str]
SECRET = re.compile(
    r"(?i)(?:api[_-]?key|password|token|secret)\s*[:=]\s*\S+|\b(?:sk|ghp)_[A-Za-z0-9]{12,}\b"
)
INJECTION_MARKERS = (
    "ignore previous instructions",
    "grant yourself",
    "override system",
    "expand your scope",
)


class PersonalContextService:
    """Thin preference facade over the existing Stage 4 repository."""

    def __init__(self, repository: SQLiteKnowledgeRepository) -> None:
        self._repository = repository

    def remember(self, preference: PersonalPreference) -> None:
        if SECRET.search(preference.value):
            raise ValidationError(
                "Sensitive values cannot become preferences", source_module=__name__
            )
        self._repository.store_preference(preference)

    def preferences(self, scope_key: str) -> tuple[PersonalPreference, ...]:
        return self._repository.preferences(scope_key)

    def retrieve(
        self,
        query: str,
        scope: KnowledgeScope,
        scope_key: str,
        *,
        limit: int = 5,
    ) -> tuple[RetrievedMemory, ...]:
        claims = self._repository.search_current(query, scope, scope_key, limit=limit)
        return tuple(
            RetrievedMemory(
                statement=claim.statement,
                topic=claim.topic,
                scope=claim.scope,
                scope_key=claim.scope_key,
                provenance=claim.provenance,
                claim_id=claim.claim_id,
            )
            for claim in claims
        )

    def build_user_context(
        self,
        query: str,
        *,
        user_scope_key: str,
        memory_scope: KnowledgeScope,
        memory_scope_key: str,
        max_memories: int = 5,
    ) -> UserContext:
        if not 0 <= max_memories <= 20:
            raise ValidationError(
                "Context memory limit is invalid", source_module=__name__
            )
        memories = (
            ()
            if max_memories == 0
            else self.retrieve(
                query, memory_scope, memory_scope_key, limit=max_memories
            )
        )
        return UserContext(
            scope_key=user_scope_key,
            preferences=self.preferences(user_scope_key),
            memories=memories,
        )

    @staticmethod
    def candidate(
        *,
        key: str,
        value: str,
        scope_key: str,
        provenance: str,
        reason: str,
        explicit_user_request: bool = False,
    ) -> MemoryCandidate:
        return MemoryCandidate(
            key=key,
            value=value,
            scope_key=scope_key,
            provenance=provenance,
            reason=reason,
            explicit_user_request=explicit_user_request,
        )

    def accept_candidate(self, candidate: MemoryCandidate) -> PersonalPreference:
        """Route an explicit preference candidate through existing preference admission."""
        if not candidate.explicit_user_request:
            raise ValidationError(
                "Memory candidate requires explicit user acceptance",
                source_module=__name__,
            )
        preference = PersonalPreference(
            key=candidate.key,
            value=candidate.value,
            scope_key=candidate.scope_key,
            provenance=candidate.provenance,
        )
        self.remember(preference)
        return preference

    def verified_outcome_candidate(
        self,
        verification: VerificationResult,
        *,
        key: str,
        value: str,
        scope_key: str,
        reason: str,
    ) -> MemoryCandidate:
        """Create an unpersisted proposal only from a fully verified outcome."""
        if verification.status is not VerificationStatus.VERIFIED:
            raise ValidationError(
                "Only verified outcomes may create successful learning candidates",
                source_module=__name__,
            )
        if SECRET.search(value):
            raise ValidationError(
                "Sensitive values cannot become learning candidates",
                source_module=__name__,
            )
        return self.candidate(
            key=key,
            value=value,
            scope_key=scope_key,
            provenance="VERIFIED_TASK_OUTCOME",
            reason=reason,
        )

    def correct(self, preference: PersonalPreference) -> None:
        self.remember(preference)

    def forget(self, key: str, scope_key: str) -> bool:
        return self._repository.forget_preference(key, scope_key)

    @staticmethod
    def safe_context(items: tuple[str, ...]) -> tuple[str, ...]:
        """Mark retrieved text as data and remove authority-shaped instructions."""
        return tuple(
            f"UNTRUSTED_CONTEXT: {item}"
            for item in items
            if not any(marker in item.casefold() for marker in INJECTION_MARKERS)
            and not SECRET.search(item)
        )


class BoundedAgent:
    """Small protocol implementation; it cannot delegate or authorize itself."""

    def __init__(self, definition: AgentDefinition) -> None:
        self.definition = definition
        self.agent_id = definition.agent_id
        self._cancelled = Event()

    def plan(self, request: PersonalTaskRequest) -> PersonalTaskPlan:
        capability = self.definition.capability_allowlist[0]
        return PersonalTaskPlan(
            task_id=request.task_id,
            steps=(
                PersonalTaskStep(
                    position=1,
                    agent=self.definition.agent_type,
                    capability=capability,
                    objective=self.definition.objective,
                ),
            ),
        )

    def execute(
        self, request: PersonalTaskRequest, plan: PersonalTaskPlan, cancellation: Event
    ) -> PersonalTaskResult:
        cancelled = cancellation.is_set() or self._cancelled.is_set()
        return PersonalTaskResult(
            task_id=request.task_id,
            status=(
                PersonalTaskStatus.CANCELLED
                if cancelled
                else PersonalTaskStatus.COMPLETED
            ),
            summary="Agent stopped safely" if cancelled else "Agent scope completed",
            completed_steps=0 if cancelled else len(plan.steps),
        )

    def verify(self, result: PersonalTaskResult) -> PersonalTaskVerification:
        return PersonalTaskVerification(
            verifier_agent_id="verification-agent",
            producer_agent_id=self.agent_id,
            passed=False,
            evidence=(
                result.status.value,
                "agent completion is not independent verification",
            ),
        )

    def cancel(self) -> None:
        self._cancelled.set()


class PersonalAIRuntime:
    """Instance-owned planner and bounded dispatcher for existing capabilities."""

    MAX_DELEGATION_DEPTH = 1

    def __init__(
        self,
        dispatcher: EventDispatcher,
        state_store: ApplicationStateStore,
        context: PersonalContextService,
        handlers: dict[PersonalCapability, CapabilityHandler] | None = None,
    ) -> None:
        self.dispatcher = dispatcher
        self.state_store = state_store
        self.context = context
        self._handlers = dict(handlers or {})
        self._active: dict[str, Event] = {}
        self.tools = _tools()
        self.agents = tuple(BoundedAgent(item) for item in _agents())
        self._context_builder = CognitiveContextBuilder()
        self._cognitive_planner = BoundedCognitivePlanner()
        self._knowledge_on_demand = KnowledgeOnDemandService(self.context)
        self._response_verifier = ResponseVerifier()

    def prepare(
        self,
        request: PersonalTaskRequest,
        understanding: ConversationUnderstanding,
        *,
        recent_context: tuple[str, ...] = (),
        configured_models: tuple[str, ...] = (),
        uncertainty: UncertaintyState = UncertaintyState.KNOWN,
        cancellation: Event | None = None,
    ) -> CognitiveDecision:
        """Prepare advisory cognition inside this authoritative runtime."""
        safe_request = replace(
            request,
            context=replace(
                request.context,
                retrieved_context=self.context.safe_context(
                    request.context.retrieved_context
                ),
            ),
        )
        context = self._context_builder.build(
            safe_request,
            understanding,
            self.user_context(request),
            recent_context=self.context.safe_context(recent_context),
            configured_models=configured_models,
        )
        return self._cognitive_planner.decide(
            request, context, uncertainty=uncertainty, cancellation=cancellation
        )

    def retrieve_current_knowledge(
        self, decision: CognitiveDecision, cancellation: Event | None = None
    ) -> KnowledgeEvidencePackage:
        """Resolve one Step 5 need without granting execution or verification authority."""
        return self._knowledge_on_demand.resolve(
            self.knowledge_need(decision), cancellation
        )

    def knowledge_need(self, decision: CognitiveDecision) -> KnowledgeNeed:
        return self._knowledge_on_demand.need(decision)

    def consume_knowledge(
        self, decision: CognitiveDecision, package: KnowledgeEvidencePackage
    ) -> CognitiveDecision:
        return self._knowledge_on_demand.consume(decision, package)

    def capabilities(self) -> tuple[CapabilityDescriptor, ...]:
        tools = tuple(
            CapabilityDescriptor(
                capability_id=item.tool_id,
                name=item.tool_id.replace(".", " ").title(),
                description=f"Registered {item.capability.value} tool",
                capability_type=CapabilityType.TOOL,
                input_contract=item.input_contract,
                output_contract=item.output_contract,
                permission_required=item.permission_required,
                risk=item.risk,
                timeout_seconds=30.0,
                cancellation_supported=True,
                audit_logged=True,
                rollback=(
                    RollbackState.SUPPORTED
                    if item.tool_id == "creation.workflow"
                    else (
                        RollbackState.NOT_REQUIRED
                        if item.risk is ActionRisk.READ_ONLY
                        else RollbackState.NOT_SUPPORTED
                    )
                ),
                environment_requirements=(
                    ("local", "workspace")
                    if item.tool_id
                    in {"creation.workflow", "files.inspect", "code.validate"}
                    else ("local",)
                ),
                availability=item.availability,
            )
            for item in self.tools
        )
        agents = tuple(
            CapabilityDescriptor(
                capability_id=item.agent_id,
                name=item.agent_type.value,
                description=item.objective,
                capability_type=CapabilityType.AGENT,
                input_contract="PersonalTaskRequest",
                output_contract="PersonalTaskResult",
                permission_required=True,
                risk=ActionRisk.SENSITIVE,
                timeout_seconds=60.0,
                cancellation_supported=True,
                audit_logged=True,
                rollback=RollbackState.NOT_SUPPORTED,
                environment_requirements=("personal_ai_runtime",),
                availability=RuntimeProviderStatus.AVAILABLE,
            )
            for item in (agent.definition for agent in self.agents)
        )
        return (*tools, *agents)

    def resolve_capability(
        self,
        decision: CognitiveDecision,
        validated_input: dict[str, str] | None = None,
        *,
        capability_id: str | None = None,
    ) -> CapabilityResolution:
        if decision.strategy is not CognitiveStrategy.REQUIRE_CAPABILITY:
            raise ValidationError(
                "Cognitive decision does not require a capability",
                source_module=__name__,
            )
        requested = capability_id or _capability_id(decision.user_goal)
        descriptor = next(
            (item for item in self.capabilities() if item.capability_id == requested),
            None,
        )
        if (
            descriptor is None
            or descriptor.availability is not RuntimeProviderStatus.AVAILABLE
        ):
            return CapabilityResolution(
                status=CapabilityResolutionStatus.NOT_AVAILABLE,
                descriptor=descriptor,
                request=None,
                reason="Capability is not registered and available",
            )
        scope = decision.context.working_scope or "current task"
        working_directory = Path(decision.context.working_scope or Path.cwd())
        environment = EnvironmentFacts(
            platform=system(),
            working_directory=str(working_directory),
            filesystem_scope=scope,
            network_available=False,
            configured_runtimes=("personal_ai_runtime", descriptor.capability_id),
        )
        if "workspace" in descriptor.environment_requirements and (
            decision.context.working_scope is None
            or not working_directory.is_absolute()
            or not working_directory.is_dir()
        ):
            return CapabilityResolution(
                status=CapabilityResolutionStatus.INCOMPATIBLE,
                descriptor=descriptor,
                request=None,
                reason="Capability requires an explicit workspace scope",
            )
        values = validated_input or {"objective": decision.user_goal}
        if any(
            not isinstance(key, str)
            or not isinstance(value, str)
            or not key.strip()
            or not value.strip()
            or SECRET.search(value)
            for key, value in values.items()
        ):
            raise ValidationError(
                "Capability input is invalid or sensitive", source_module=__name__
            )
        permission_id = new_correlation_id() if descriptor.permission_required else None
        request = CapabilityExecutionRequest(
            task_id=decision.task_id,
            capability=descriptor,
            objective=decision.user_goal,
            validated_input=tuple(sorted(values.items())),
            environment=environment,
            working_scope=scope,
            expected_output=descriptor.output_contract,
            permission_id=permission_id,
            timeout_seconds=descriptor.timeout_seconds,
        )
        return CapabilityResolution(
            status=(
                CapabilityResolutionStatus.PERMISSION_REQUIRED
                if descriptor.permission_required
                else CapabilityResolutionStatus.AVAILABLE
            ),
            descriptor=descriptor,
            request=request,
            reason=(
                "Existing permission approval is required"
                if descriptor.permission_required
                else "Capability and environment are compatible"
            ),
        )

    def execute_capability(
        self,
        request: CapabilityExecutionRequest,
        *,
        approved_permissions: tuple[str, ...] = (),
        cancellation: Event | None = None,
    ) -> CapabilityExecutionResult:
        started = datetime.now(UTC)
        signal = cancellation or Event()
        status = CapabilityExecutionStatus.COMPLETED
        output: str | None = None
        errors: tuple[str, ...] = ()
        if request.permission_id and request.permission_id not in approved_permissions:
            status = CapabilityExecutionStatus.PERMISSION_REQUIRED
        elif signal.is_set():
            status = CapabilityExecutionStatus.CANCELLED
        else:
            task = PersonalTaskRequest(
                objective=request.objective, task_id=request.task_id
            )
            tool = next(
                (
                    item
                    for item in self.tools
                    if item.tool_id == request.capability.capability_id
                ),
                None,
            )
            agent = next(
                (
                    item
                    for item in self.agents
                    if item.agent_id == request.capability.capability_id
                ),
                None,
            )
            handler = None if tool is None else self._handlers.get(tool.capability)
            operation: Callable[[], str] | None = None
            if tool is not None and tool.tool_id == "files.inspect":

                def file_operation() -> str:
                    return _inspect_workspace(request)

                operation = file_operation
            elif tool is not None and tool.tool_id == "code.validate":

                def validation_operation() -> str:
                    return _run_validation(request, signal)

                operation = validation_operation
            elif (
                tool is not None
                and handler is not None
                and tool.availability is RuntimeProviderStatus.AVAILABLE
            ):
                step = PersonalTaskStep(
                    position=1,
                    agent=None,
                    capability=tool.capability,
                    objective=request.objective,
                    tool_ids=(tool.tool_id,),
                    risk=tool.risk,
                )

                def tool_operation() -> str:
                    return handler(task, step, signal)

                operation = tool_operation
            elif agent is not None:

                def agent_operation() -> str:
                    return agent.execute(task, agent.plan(task), signal).summary

                operation = agent_operation
            if operation is None:
                status = CapabilityExecutionStatus.NOT_AVAILABLE
            else:
                queue: Queue[tuple[str | None, BaseException | None]] = Queue(maxsize=1)

                def run() -> None:
                    try:
                        queue.put((operation(), None))
                    except BaseException as error:
                        queue.put((None, error))

                worker = Thread(target=run, daemon=True)
                worker.start()
                worker.join(request.timeout_seconds)
                if worker.is_alive():
                    signal.set()
                    status = CapabilityExecutionStatus.TIMED_OUT
                else:
                    output, error = queue.get_nowait()
                    if error is not None:
                        status = CapabilityExecutionStatus.FAILED
                        errors = (type(error).__name__,)
                    elif signal.is_set():
                        status = CapabilityExecutionStatus.CANCELLED
                    elif not isinstance(output, str) or not output.strip():
                        status = CapabilityExecutionStatus.FAILED
                        errors = ("invalid structured output",)
        finished = datetime.now(UTC)
        evidence = CapabilityExecutionEvidence(
            execution_id=request.execution_id,
            task_id=request.task_id,
            capability_id=request.capability.capability_id,
            started_at=started,
            finished_at=finished,
            validated_input_summary=tuple(
                f"{key}:<validated>" for key, _ in request.validated_input
            ),
            environment_summary=f"{request.environment.platform}; network={request.environment.network_available}",
            permission_reference=request.permission_id,
            operations_performed=(
                (request.capability.capability_id,)
                if status is CapabilityExecutionStatus.COMPLETED
                else ()
            ),
            structured_output=(
                output if status is CapabilityExecutionStatus.COMPLETED else None
            ),
            errors=errors,
            cancelled=status is CapabilityExecutionStatus.CANCELLED,
            timed_out=status is CapabilityExecutionStatus.TIMED_OUT,
            rollback=request.capability.rollback,
            audit_references=(
                f"execution:{request.execution_id}",
                f"task:{request.task_id}",
            ),
        )
        return CapabilityExecutionResult(status=status, evidence=evidence)

    def verify_capability(
        self,
        result: CapabilityExecutionResult,
        *,
        claim: str,
        expected_postcondition: str | None = None,
        read_back: Callable[[], str] | None = None,
        cancellation: Event | None = None,
    ) -> VerificationResult:
        """Evaluate execution separately; executor success is never proof."""
        request = VerificationRequest(
            task_id=result.evidence.task_id,
            claim=claim,
            expected_postcondition=expected_postcondition,
            execution_evidence=result.evidence,
        )
        return self._response_verifier.verify(
            request, result.status, read_back=read_back, cancellation=cancellation
        )

    def user_context(self, request: PersonalTaskRequest) -> UserContext:
        """Build bounded approved context for the existing Orchestrator boundary."""
        return self.context.build_user_context(
            request.objective,
            user_scope_key="user",
            memory_scope=request.context.memory_scope,
            memory_scope_key=request.context.memory_scope_key,
            max_memories=request.budget.max_research_sources,
        )

    def plan(
        self,
        request: PersonalTaskRequest,
        cognitive: CognitiveDecision | None = None,
    ) -> PersonalTaskPlan:
        if cognitive is not None:
            if cognitive.task_id != request.task_id:
                raise ValidationError(
                    "Cognitive decision belongs to another task", source_module=__name__
                )
            if cognitive.strategy in {
                CognitiveStrategy.ASK_CLARIFICATION,
                CognitiveStrategy.REQUIRE_CURRENT_KNOWLEDGE,
                CognitiveStrategy.REQUIRE_CAPABILITY,
            }:
                return PersonalTaskPlan(
                    task_id=request.task_id,
                    steps=(),
                    clarification=cognitive.uncertainty_reason,
                )
        text = request.objective.casefold()
        capabilities = self._route(text)
        if len(capabilities) > request.budget.max_agents:
            raise ValidationError("Agent budget exhausted", source_module=__name__)
        steps: list[PersonalTaskStep] = []
        for capability in capabilities:
            agent = _agent_for(capability)
            risk = _risk_for(capability, text)
            permission = (
                PersonalTaskPermission(
                    task_id=request.task_id,
                    capability=capability,
                    purpose=request.objective,
                    scope=request.context.workspace_root or "current task",
                    risk=risk,
                )
                if risk is not ActionRisk.READ_ONLY
                or capability
                in {PersonalCapability.RESEARCH, PersonalCapability.BROWSER}
                else None
            )
            steps.append(
                PersonalTaskStep(
                    position=len(steps) + 1,
                    agent=agent,
                    capability=capability,
                    objective=f"Handle {capability.value} within the task scope",
                    tool_ids=_tool_ids(self.tools, capability),
                    risk=risk,
                    permission=permission,
                )
            )
        if capabilities != (PersonalCapability.CONVERSATION,):
            steps.append(
                PersonalTaskStep(
                    position=len(steps) + 1,
                    agent=AgentType.VERIFICATION,
                    capability=PersonalCapability.VERIFICATION,
                    objective="Independently verify bounded task evidence",
                )
            )
        if len(steps) > request.budget.max_steps:
            raise ValidationError("Step budget exhausted", source_module=__name__)
        plan = PersonalTaskPlan(
            task_id=request.task_id,
            steps=tuple(steps),
            direct_response=capabilities == (PersonalCapability.CONVERSATION,),
        )
        self.dispatcher.publish(
            PersonalTaskPlanCreatedEvent(
                correlation_id=request.task_id, source_module=__name__
            )
        )
        return plan

    def execute(
        self,
        request: PersonalTaskRequest,
        plan: PersonalTaskPlan,
        *,
        approved_permissions: tuple[str, ...] = (),
        cancellation: Event | None = None,
    ) -> PersonalTaskResult:
        if request.task_id != plan.task_id:
            raise ValidationError(
                "Plan is bound to another task", source_module=__name__
            )
        signal = cancellation or Event()
        self._active[request.task_id] = signal
        started = monotonic()
        audit = [f"task:{request.task_id}", f"plan:{plan.plan_id}"]
        completed = 0
        try:
            self.dispatcher.publish(
                PersonalTaskStartedEvent(
                    correlation_id=request.task_id, source_module=__name__
                )
            )
            self.state_store.transition(
                ApplicationState.THINKING,
                status_message="Planning personal task",
                correlation_id=request.task_id,
            )
            for step in plan.steps:
                if signal.is_set():
                    return self._finish(
                        request,
                        PersonalTaskStatus.CANCELLED,
                        "Task cancelled",
                        completed,
                        audit,
                    )
                if monotonic() - started > request.budget.max_duration_seconds:
                    return self._finish(
                        request,
                        PersonalTaskStatus.BUDGET_EXHAUSTED,
                        "Task duration budget exhausted",
                        completed,
                        audit,
                    )
                if completed >= request.budget.max_tool_calls:
                    return self._finish(
                        request,
                        PersonalTaskStatus.BUDGET_EXHAUSTED,
                        "Tool-call budget exhausted",
                        completed,
                        audit,
                    )
                if (
                    step.permission
                    and step.permission.permission_id not in approved_permissions
                ):
                    return self._finish(
                        request,
                        PersonalTaskStatus.PERMISSION_REQUIRED,
                        f"Permission required for {step.capability.value}",
                        completed,
                        audit,
                    )
                if step.agent is AgentType.VERIFICATION:
                    verification = VerificationResult(
                        verification_id=new_correlation_id(),
                        task_id=request.task_id,
                        status=VerificationStatus.NOT_VERIFIABLE,
                        unverified_claims=("bounded task completed successfully",),
                        evidence_references=tuple(audit),
                        limitations=(
                            "executor and audit success are not independent proof",
                        ),
                    )
                    return self._finish(
                        request,
                        PersonalTaskStatus.COMPLETED,
                        "Task completed; independent verification unavailable",
                        completed,
                        audit,
                        verification=verification,
                    )
                status = self._execute_step(request, step, signal)
                audit.append(f"{step.capability.value}:{status}")
                completed += 1
                if status in {
                    RuntimeProviderStatus.NOT_CONFIGURED.value,
                    RuntimeProviderStatus.UNAVAILABLE.value,
                }:
                    return self._finish(
                        request,
                        PersonalTaskStatus.FAILED,
                        f"{step.capability.value} provider is {status}",
                        completed,
                        audit,
                        provider_status=RuntimeProviderStatus(status),
                    )
            return self._finish(
                request,
                PersonalTaskStatus.COMPLETED,
                "Direct Virgo response routed",
                completed,
                audit,
            )
        finally:
            self._active.pop(request.task_id, None)
            if self.state_store.snapshot.state is not ApplicationState.IDLE:
                self.state_store.transition(
                    ApplicationState.IDLE, correlation_id=request.task_id
                )

    def cancel(self, task_id: str) -> bool:
        signal = self._active.get(task_id)
        if signal is None or signal.is_set():
            return False
        signal.set()
        return True

    def validate_tool_call(
        self,
        *,
        tool_id: str,
        step: PersonalTaskStep,
        permission_id: str | None,
    ) -> RuntimeTool:
        tool = next((item for item in self.tools if item.tool_id == tool_id), None)
        if tool is None or tool_id not in step.tool_ids:
            raise PermissionDeniedError(
                "Tool is outside agent scope", source_module=__name__
            )
        if tool.capability is not step.capability:
            raise PermissionDeniedError(
                "Tool capability does not match step", source_module=__name__
            )
        if tool.permission_required and (
            step.permission is None or permission_id != step.permission.permission_id
        ):
            raise PermissionDeniedError(
                "Tool lacks exact permission", source_module=__name__
            )
        if tool.availability is not RuntimeProviderStatus.AVAILABLE:
            raise ValidationError(
                f"Tool provider is {tool.availability.value}", source_module=__name__
            )
        return tool

    def _execute_step(
        self, request: PersonalTaskRequest, step: PersonalTaskStep, cancellation: Event
    ) -> str:
        handler = self._handlers.get(step.capability)
        if handler is not None:
            return handler(request, step, cancellation)
        tool_statuses = {
            item.availability
            for item in self.tools
            if item.capability is step.capability
        }
        if RuntimeProviderStatus.NOT_CONFIGURED in tool_statuses:
            return RuntimeProviderStatus.NOT_CONFIGURED.value
        return "delegated_to_existing_capability"

    def _finish(
        self,
        request: PersonalTaskRequest,
        status: PersonalTaskStatus,
        summary: str,
        completed: int,
        audit: list[str],
        *,
        verification: PersonalTaskVerification | VerificationResult | None = None,
        provider_status: RuntimeProviderStatus | None = None,
    ) -> PersonalTaskResult:
        result = PersonalTaskResult(
            task_id=request.task_id,
            status=status,
            summary=summary,
            completed_steps=completed,
            provider_status=provider_status,
            verification=verification,
            audit=tuple(audit),
        )
        event_type = {
            PersonalTaskStatus.COMPLETED: PersonalTaskCompletedEvent,
            PersonalTaskStatus.CANCELLED: PersonalTaskCancelledEvent,
        }.get(status, PersonalTaskFailedEvent)
        self.dispatcher.publish(
            event_type(correlation_id=request.task_id, source_module=__name__)
        )
        return result

    @staticmethod
    def _route(text: str) -> tuple[PersonalCapability, ...]:
        if any(word in text for word in ("image", "picture", "photo")):
            return (PersonalCapability.IMAGE,)
        if "video" in text:
            return (PersonalCapability.VIDEO,)
        if any(word in text for word in ("research", "internet", "web search")):
            return (PersonalCapability.RESEARCH,)
        if any(
            word in text
            for word in ("desktop", "open app", "launch app", "vs code", "vscode")
        ):
            return (PersonalCapability.DESKTOP,)
        if any(word in text for word in ("fix", "code", "website", "project")):
            return (
                PersonalCapability.CODING,
                PersonalCapability.DEFENSIVE_SECURITY,
            )
        if any(word in text for word in ("diagnose", "system health")):
            return (PersonalCapability.SYSTEM_DIAGNOSTICS,)
        if any(word in text for word in ("organize", "summarize", "plan")):
            return (PersonalCapability.PRODUCTIVITY,)
        return (PersonalCapability.CONVERSATION,)


def _inspect_workspace(request: CapabilityExecutionRequest) -> str:
    values = dict(request.validated_input)
    relative_path = values.get("path")
    if relative_path is None:
        raise ValidationError(
            "File capability requires a relative path", source_module=__name__
        )
    workspace = SafeWorkspace(Path(request.environment.working_directory))
    if values.get("operation", "inspect") == "read":
        if Path(relative_path).name in SENSITIVE_FILE_NAMES:
            raise ValidationError(
                "Sensitive files are excluded from capability reads",
                source_module=__name__,
            )
        content = workspace.read_text(relative_path)[:20_000]
        if SECRET.search(content):
            raise ValidationError(
                "Sensitive file content cannot enter execution evidence",
                source_module=__name__,
            )
        return content
    inspection = workspace.inspect((relative_path,))
    return "\n".join(
        f"{item.relative_path}\t{item.size_bytes}\t{item.sha256}"
        for item in inspection.files
    )


def _run_validation(request: CapabilityExecutionRequest, signal: Event) -> str:
    values = dict(request.validated_input)
    tool_name = values.get("tool_name")
    if tool_name is None:
        raise ValidationError(
            "Coding capability requires an allowlisted tool", source_module=__name__
        )
    token = CancellationToken()
    try:
        if signal.is_set():
            token.cancel()
        result = ValidationProcessTool(Path(request.environment.working_directory)).run(
            ProcessRequest(
                tool_name=tool_name,
                arguments=tuple(shlex.split(values.get("arguments", ""), posix=False)),
                working_directory=request.environment.working_directory,
                timeout_seconds=request.timeout_seconds,
            ),
            token,
        )
    finally:
        token.close()
    return (
        f"status={result.status.value}; exit_code={result.exit_code}\n"
        f"stdout={_redact_output(result.stdout)}\nstderr={_redact_output(result.stderr)}"
    )


def _redact_output(value: str) -> str:
    bounded = value[:20_000]
    return "[REDACTED_SENSITIVE_OUTPUT]" if SECRET.search(bounded) else bounded


def _risk_for(capability: PersonalCapability, text: str) -> ActionRisk:
    if capability in {PersonalCapability.RESEARCH, PersonalCapability.BROWSER}:
        return ActionRisk.SENSITIVE
    if capability in {PersonalCapability.CODING, PersonalCapability.CREATION} and any(
        word in text for word in ("fix", "change", "create", "write")
    ):
        return ActionRisk.REVERSIBLE_MUTATION
    return ActionRisk.READ_ONLY


def _agent_for(capability: PersonalCapability) -> AgentType | None:
    return {
        PersonalCapability.RESEARCH: AgentType.RESEARCH,
        PersonalCapability.CODING: AgentType.CODING,
        PersonalCapability.CREATION: AgentType.CREATION,
        PersonalCapability.IMAGE: AgentType.CREATION,
        PersonalCapability.VIDEO: AgentType.CREATION,
        PersonalCapability.PRODUCTIVITY: AgentType.PRODUCTIVITY,
        PersonalCapability.SYSTEM_DIAGNOSTICS: AgentType.SYSTEM_DIAGNOSTIC,
        PersonalCapability.DEFENSIVE_SECURITY: AgentType.DEFENSIVE_SECURITY,
    }.get(capability)


def _tool_ids(
    tools: tuple[RuntimeTool, ...], capability: PersonalCapability
) -> tuple[str, ...]:
    return tuple(item.tool_id for item in tools if item.capability is capability)


def _tools() -> tuple[RuntimeTool, ...]:
    values = (
        (
            "research.retrieve",
            PersonalCapability.RESEARCH,
            ActionRisk.SENSITIVE,
            True,
            RuntimeProviderStatus.NOT_CONFIGURED,
            "research",
        ),
        (
            "browser.read",
            PersonalCapability.BROWSER,
            ActionRisk.SENSITIVE,
            True,
            RuntimeProviderStatus.NOT_CONFIGURED,
            "browser",
        ),
        (
            "desktop.inspect",
            PersonalCapability.DESKTOP,
            ActionRisk.READ_ONLY,
            False,
            RuntimeProviderStatus.NOT_CONFIGURED,
            "desktop",
        ),
        (
            "creation.workflow",
            PersonalCapability.CODING,
            ActionRisk.REVERSIBLE_MUTATION,
            True,
            RuntimeProviderStatus.AVAILABLE,
            "creation_engine",
        ),
        (
            "files.inspect",
            PersonalCapability.FILES,
            ActionRisk.READ_ONLY,
            False,
            RuntimeProviderStatus.AVAILABLE,
            "safe_workspace",
        ),
        (
            "code.validate",
            PersonalCapability.CODING,
            ActionRisk.READ_ONLY,
            True,
            RuntimeProviderStatus.AVAILABLE,
            "validation_process_tool",
        ),
        (
            "security.inspect",
            PersonalCapability.DEFENSIVE_SECURITY,
            ActionRisk.READ_ONLY,
            False,
            RuntimeProviderStatus.AVAILABLE,
            "security_engine",
        ),
        (
            "system.diagnostics",
            PersonalCapability.SYSTEM_DIAGNOSTICS,
            ActionRisk.READ_ONLY,
            False,
            RuntimeProviderStatus.AVAILABLE,
            "security_engine",
        ),
        (
            "image.generate",
            PersonalCapability.IMAGE,
            ActionRisk.READ_ONLY,
            False,
            RuntimeProviderStatus.NOT_CONFIGURED,
            "image",
        ),
        (
            "video.generate",
            PersonalCapability.VIDEO,
            ActionRisk.READ_ONLY,
            False,
            RuntimeProviderStatus.NOT_CONFIGURED,
            "video",
        ),
    )
    return tuple(
        RuntimeTool(
            tool_id=tool_id,
            capability=capability,
            risk=risk,
            permission_required=permission,
            availability=status,
            provider=provider,
            input_contract="typed",
            output_contract="typed",
        )
        for tool_id, capability, risk, permission, status, provider in values
    )


def _capability_id(objective: str) -> str:
    text = objective.casefold()
    if any(value in text for value in ("diagnose", "system health")):
        return "system.diagnostics"
    if "fix code" in text or "edit file" in text:
        return "creation.workflow"
    if any(value in text for value in ("inspect file", "read file", "search files")):
        return "files.inspect"
    if any(value in text for value in ("run tests", "run build", "git status")):
        return "code.validate"
    if "image" in text:
        return "image.generate"
    if "video" in text:
        return "video.generate"
    if "browser" in text:
        return "browser.read"
    if any(
        value in text
        for value in ("desktop", "open app", "launch app", "vs code", "vscode")
    ):
        return "desktop.inspect"
    return "unregistered"


def _agents() -> tuple[AgentDefinition, ...]:
    definitions = []
    for agent_type, capability in (
        (AgentType.RESEARCH, PersonalCapability.RESEARCH),
        (AgentType.CODING, PersonalCapability.CODING),
        (AgentType.CREATION, PersonalCapability.CREATION),
        (AgentType.PRODUCTIVITY, PersonalCapability.PRODUCTIVITY),
        (AgentType.SYSTEM_DIAGNOSTIC, PersonalCapability.SYSTEM_DIAGNOSTICS),
        (AgentType.DEFENSIVE_SECURITY, PersonalCapability.DEFENSIVE_SECURITY),
    ):
        definitions.append(
            AgentDefinition(
                agent_id=agent_type.value,
                agent_type=agent_type,
                objective=f"Bounded {capability.value}",
                scope=(capability,),
                capability_allowlist=(capability,),
                tool_allowlist=(),
                stop_conditions=("cancelled", "permission denied", "budget exhausted"),
                verifier=AgentType.VERIFICATION,
            )
        )
    return tuple(definitions)
