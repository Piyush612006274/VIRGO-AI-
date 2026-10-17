"""Pure bounded collaborators used by the authoritative PersonalAIRuntime."""

from threading import Event

from virgo.contracts.models.cognitive import (
    CognitiveContext,
    CognitiveDecision,
    CognitivePlanStep,
    CognitiveStrategy,
    CognitiveTaskStatus,
    UncertaintyState,
)
from virgo.contracts.models.conversation import (
    ConversationIntent,
    ConversationUnderstanding,
)
from virgo.contracts.models.personal_runtime import PersonalTaskRequest, UserContext


class CognitiveContextBuilder:
    """Select active context without mutating any source."""

    def build(
        self,
        request: PersonalTaskRequest,
        understanding: ConversationUnderstanding,
        user_context: UserContext,
        *,
        recent_context: tuple[str, ...] = (),
        configured_models: tuple[str, ...] = (),
    ) -> CognitiveContext:
        recent = _unique(recent_context)[-5:]
        supplied = _unique(request.context.retrieved_context)[:5]
        return CognitiveContext(
            request=request.objective,
            understanding=understanding,
            user_context=user_context,
            recent_context=recent,
            contextual_evidence=supplied,
            configured_models=_unique(configured_models),
            working_scope=request.context.workspace_root,
        )


class ConfiguredModelRouter:
    """Choose only from model identifiers supplied by existing configuration."""

    @staticmethod
    def select(context: CognitiveContext) -> str | None:
        return context.configured_models[0] if context.configured_models else None


class BoundedCognitivePlanner:
    """Prepare advisory strategy and plan metadata; never execute it."""

    def decide(
        self,
        request: PersonalTaskRequest,
        context: CognitiveContext,
        *,
        uncertainty: UncertaintyState = UncertaintyState.KNOWN,
        cancellation: Event | None = None,
    ) -> CognitiveDecision:
        if cancellation is not None and cancellation.is_set():
            return self._decision(
                request,
                context,
                CognitiveStrategy.DECLINE_UNSUPPORTED_OR_UNSAFE,
                uncertainty,
                "Preparation was cancelled",
                CognitiveTaskStatus.CANCELLED,
            )
        understanding = context.understanding
        if understanding.needs_clarification or uncertainty in {
            UncertaintyState.UNKNOWN,
            UncertaintyState.CONFLICTING,
        }:
            return self._decision(
                request,
                context,
                CognitiveStrategy.ASK_CLARIFICATION,
                uncertainty,
                "Material intent or context is missing or conflicting",
                CognitiveTaskStatus.WAITING_CLARIFICATION,
            )
        if uncertainty in {
            UncertaintyState.OUTDATED,
            UncertaintyState.NEEDS_VERIFICATION,
        }:
            return self._decision(
                request,
                context,
                CognitiveStrategy.REQUIRE_CURRENT_KNOWLEDGE,
                uncertainty,
                "Current independently verifiable knowledge is required",
                CognitiveTaskStatus.READY,
            )
        text = request.objective.casefold()
        if any(
            term in text for term in ("latest", "current news", "today's", "research")
        ):
            return self._decision(
                request,
                context,
                CognitiveStrategy.REQUIRE_CURRENT_KNOWLEDGE,
                UncertaintyState.NEEDS_VERIFICATION,
                "The request depends on current external knowledge",
                CognitiveTaskStatus.READY,
            )
        if any(
            term in text
            for term in (
                "edit file",
                "inspect file",
                "read file",
                "search files",
                "run ",
                "run tests",
                "git status",
                "send ",
                "fix code",
                "diagnose",
                "system health",
            )
        ) or (
            "create" in text
            and any(term in text for term in ("image", "video", "file"))
        ):
            return self._decision(
                request,
                context,
                CognitiveStrategy.REQUIRE_CAPABILITY,
                uncertainty,
                "An external capability is required; no execution occurred",
                CognitiveTaskStatus.WAITING_PERMISSION,
                requires_permission=True,
                plan=self._plan(
                    request,
                    "Identify the required capability",
                    ("existing permission approval", "Step 6 capability available"),
                ),
            )
        if (
            understanding.intent is ConversationIntent.CONVERSE
            and len(text.split()) <= 4
        ):
            return self._decision(
                request,
                context,
                CognitiveStrategy.RESPOND_DIRECTLY,
                uncertainty,
                "The request is simple and current context is sufficient",
                CognitiveTaskStatus.READY,
            )
        if context.user_context.memories:
            strategy = CognitiveStrategy.USE_RELEVANT_MEMORY
        elif context.contextual_evidence or context.recent_context:
            strategy = CognitiveStrategy.USE_EXISTING_CONTEXT
        else:
            strategy = CognitiveStrategy.REASON_WITH_CONFIGURED_MODEL
        model = (
            ConfiguredModelRouter.select(context)
            if strategy is CognitiveStrategy.REASON_WITH_CONFIGURED_MODEL
            else None
        )
        return self._decision(
            request,
            context,
            strategy,
            (
                uncertainty
                if model is not None
                or strategy is not CognitiveStrategy.REASON_WITH_CONFIGURED_MODEL
                else UncertaintyState.UNKNOWN
            ),
            (
                "Bounded context selected for a non-trivial request"
                if model is not None
                or strategy is not CognitiveStrategy.REASON_WITH_CONFIGURED_MODEL
                else "No configured model is available"
            ),
            (
                CognitiveTaskStatus.READY
                if model is not None
                or strategy is not CognitiveStrategy.REASON_WITH_CONFIGURED_MODEL
                else CognitiveTaskStatus.WAITING_CLARIFICATION
            ),
            plan=self._plan(request, "Prepare a bounded response proposal"),
            selected_model=model,
        )

    @staticmethod
    def _plan(
        request: PersonalTaskRequest,
        outcome: str,
        preconditions: tuple[str, ...] = (),
    ) -> tuple[CognitivePlanStep, ...]:
        steps = (
            CognitivePlanStep(
                position=1,
                purpose="Use bounded approved context",
                expected_outcome="Relevant task context only",
            ),
            CognitivePlanStep(
                position=2,
                purpose="Prepare the smallest safe proposal",
                expected_outcome=outcome,
                preconditions=preconditions,
            ),
        )
        return steps[: min(5, request.budget.max_steps)]

    @staticmethod
    def _decision(
        request: PersonalTaskRequest,
        context: CognitiveContext,
        strategy: CognitiveStrategy,
        uncertainty: UncertaintyState,
        reason: str,
        status: CognitiveTaskStatus,
        *,
        requires_permission: bool = False,
        plan: tuple[CognitivePlanStep, ...] = (),
        selected_model: str | None = None,
    ) -> CognitiveDecision:
        return CognitiveDecision(
            task_id=request.task_id,
            user_goal=request.objective,
            strategy=strategy,
            uncertainty=uncertainty,
            uncertainty_reason=reason,
            status=status,
            context=context,
            plan=plan,
            selected_model=selected_model,
            requires_permission=requires_permission,
        )


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value.strip()))
