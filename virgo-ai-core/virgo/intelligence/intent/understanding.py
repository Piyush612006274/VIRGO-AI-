"""Ephemeral intent and interaction signals; never an execution authority."""

import re

from virgo.contracts.models import (
    ConversationAct,
    ConversationIntent,
    ConversationReference,
    ConversationUnderstanding,
    ConversationUnderstandingContext,
    ConversationUrgency,
    IntentEvidence,
    InteractionState,
    MemoryCandidate,
    ResponseStyle,
)

CORRECTION = re.compile(
    r"(?i)^(?:no[, ]|actually\b)|\b(?:i meant|not that|that's wrong|that answer is wrong)\b"
)
STOP = re.compile(r"(?i)^(?:stop|cancel|never mind|nevermind)\b")
URGENT = re.compile(r"(?i)\b(?:urgent|asap|immediately|right now)\b")
FRUSTRATED = re.compile(
    r"(?i)\b(?:already told you|again|that's wrong|that answer is wrong)\b"
)
HESITANT = re.compile(r"(?i)\b(?:maybe|not sure|i think|um+|uh+)\b")
REFERENCE = re.compile(
    r"(?i)\b(?:previous one|other file|same|this project|that one|it)\b"
)


class ConversationUnderstandingService:
    """Interpret one turn from bounded supplied context without side effects."""

    def understand(
        self, text: str, context: ConversationUnderstandingContext
    ) -> ConversationUnderstanding:
        normalized = " ".join(text.split())
        if not normalized:
            raise ValueError("conversation text must not be empty")
        lowered = normalized.casefold()
        correction = bool(CORRECTION.search(normalized))
        stopped = bool(STOP.search(normalized))
        hesitant = bool(HESITANT.search(normalized))
        preference = None if hesitant else _preference_candidate(normalized)
        reference_requested = bool(REFERENCE.search(normalized))
        reference, ambiguous = _resolve_reference(lowered, context.references)
        repeated = any(lowered == item.text.casefold() for item in context.references)
        urgency = (
            ConversationUrgency.HIGH
            if URGENT.search(normalized)
            else ConversationUrgency.NORMAL
        )
        interaction = _interaction_state(
            correction=correction,
            repeated=repeated,
            urgent=urgency is ConversationUrgency.HIGH,
            frustrated=bool(FRUSTRATED.search(normalized)),
            hesitant=hesitant,
        )
        intent = (
            ConversationIntent.STOP
            if stopped
            else (
                ConversationIntent.CHANGE_PREFERENCE
                if preference is not None
                else (
                    ConversationIntent.CORRECT
                    if correction
                    else (
                        ConversationIntent.CONTINUE_TASK
                        if reference_requested
                        else ConversationIntent.CONVERSE
                    )
                )
            )
        )
        act = (
            ConversationAct.CORRECTION
            if correction
            else (
                ConversationAct.REFERENCE
                if reference_requested
                else (
                    ConversationAct.CLARIFICATION_RESPONSE
                    if lowered in {"yes", "no", "correct", "that's right"}
                    else ConversationAct.REQUEST
                )
            )
        )
        needs_clarification = reference_requested and (reference is None or ambiguous)
        return ConversationUnderstanding(
            intent=intent,
            intent_evidence=(
                IntentEvidence.EXPLICIT
                if stopped or correction or preference is not None
                else (
                    IntentEvidence.RULE_MATCH
                    if reference_requested
                    or interaction is not InteractionState.NEUTRAL
                    else IntentEvidence.DEFAULT
                )
            ),
            act=act,
            interaction_state=interaction,
            urgency=urgency,
            response_style=_response_style(
                lowered,
                context.communication_preference,
                interaction,
                needs_clarification,
            ),
            correction_reference_id=(
                reference.reference_id if correction and reference is not None else None
            ),
            resolved_reference_id=(
                None
                if needs_clarification or reference is None
                else reference.reference_id
            ),
            needs_clarification=needs_clarification,
            task_id=context.active_task_id,
            session_id=context.session_id,
            preference_candidate=preference,
        )


def _resolve_reference(
    text: str, references: tuple[ConversationReference, ...]
) -> tuple[ConversationReference | None, bool]:
    if not REFERENCE.search(text):
        return None, False
    if "previous one" in text or "that one" in text or text.endswith(" it"):
        return (references[-1], False) if references else (None, True)
    if "other file" in text:
        files = tuple(item for item in references if item.kind == "file")
        return (files[-2], False) if len(files) == 2 else (None, True)
    if "this project" in text:
        projects = tuple(item for item in references if item.kind == "project")
        return (projects[0], False) if len(projects) == 1 else (None, True)
    return (references[-1], False) if len(references) == 1 else (None, True)


def _interaction_state(
    *, correction: bool, repeated: bool, urgent: bool, frustrated: bool, hesitant: bool
) -> InteractionState:
    if correction:
        return InteractionState.CORRECTING
    if frustrated:
        return InteractionState.FRUSTRATED
    if urgent:
        return InteractionState.URGENT
    if repeated:
        return InteractionState.REPEATED
    if hesitant:
        return InteractionState.HESITANT
    return InteractionState.NEUTRAL


def _response_style(
    text: str,
    preference: str | None,
    interaction: InteractionState,
    needs_clarification: bool,
) -> ResponseStyle:
    if needs_clarification:
        return ResponseStyle.CLARIFYING
    if interaction is InteractionState.CORRECTING:
        return ResponseStyle.ACKNOWLEDGE_AND_CORRECT
    if interaction is InteractionState.URGENT:
        return ResponseStyle.URGENT_DIRECT
    value = text if preference is None else preference.casefold()
    if "step-by-step" in value or "step by step" in value:
        return ResponseStyle.STEP_BY_STEP
    if "detailed" in value:
        return ResponseStyle.DETAILED
    if "concise" in value or "shorter" in value:
        return ResponseStyle.CONCISE
    return ResponseStyle.NORMAL


def _preference_candidate(text: str) -> MemoryCandidate | None:
    language = re.search(r"(?i)\buse ([A-Za-z][A-Za-z -]{1,24})\s*$", text)
    if language and language.group(1).casefold() not in {
        "this",
        "that",
        "it",
        "the previous one",
        "this project",
    }:
        return MemoryCandidate(
            key="language",
            value=language.group(1).strip(),
            scope_key="user",
            provenance="EXPLICIT_USER",
            reason="Explicit conversational language preference",
            explicit_user_request=True,
        )
    if re.search(r"(?i)\b(?:make it shorter|be concise|use concise responses)\b", text):
        return MemoryCandidate(
            key="response_style",
            value="concise",
            scope_key="user",
            provenance="EXPLICIT_USER",
            reason="Explicit conversational response-style preference",
            explicit_user_request=True,
        )
    return None
