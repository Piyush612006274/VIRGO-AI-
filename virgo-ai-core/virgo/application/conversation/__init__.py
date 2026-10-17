"""Public single-turn conversation orchestration foundation."""

from virgo.application.conversation.interruption import BargeInCoordinator
from virgo.application.conversation.orchestrator import (
    VIRGO_IDENTITY_SYSTEM_INSTRUCTION,
    ConversationOrchestrator,
    build_virgo_system_instruction,
)
from virgo.contracts.models import (
    ConversationInput,
    ConversationInputSource,
    ConversationResponse,
    ConversationStreamChunk,
    InterruptionRequest,
    InterruptionSource,
)

__all__ = (
    "BargeInCoordinator",
    "ConversationInput",
    "ConversationInputSource",
    "ConversationOrchestrator",
    "ConversationResponse",
    "ConversationStreamChunk",
    "VIRGO_IDENTITY_SYSTEM_INSTRUCTION",
    "InterruptionRequest",
    "InterruptionSource",
    "build_virgo_system_instruction",
)

from virgo.application.conversation.identity import resolve_identity_response

