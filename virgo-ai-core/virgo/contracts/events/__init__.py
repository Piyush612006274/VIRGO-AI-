"""Public typed application event contracts."""

from virgo.contracts.events.application import (
    ApplicationStartedEvent,
    ApplicationStoppingEvent,
)
from virgo.contracts.events.base import ApplicationEvent, EventDictionary
from virgo.contracts.events.conversation import (
    ConversationCancelledEvent,
    ConversationChunkEvent,
    ConversationCompletedEvent,
    ConversationFailedEvent,
    ConversationStartedEvent,
)
from virgo.contracts.events.creation import (
    CreationPermissionRequestedEvent,
    CreationPlanPreparedEvent,
)
from virgo.contracts.events.interruption import (
    InterruptionCompletedEvent,
    InterruptionRequestedEvent,
)
from virgo.contracts.events.learning import (
    ImprovementProposalReadyEvent,
    KnowledgeAcceptedEvent,
    KnowledgeGapDetectedEvent,
    LearningProposalReadyEvent,
    SelfImprovementAcceptedEvent,
    SelfImprovementAppliedEvent,
    SelfImprovementApprovalRequiredEvent,
    SelfImprovementRolledBackEvent,
    SelfInspectionCompletedEvent,
    SelfInspectionStartedEvent,
)
from virgo.contracts.events.personal_runtime import (
    PersonalTaskCancelledEvent,
    PersonalTaskCompletedEvent,
    PersonalTaskFailedEvent,
    PersonalTaskPlanCreatedEvent,
    PersonalTaskStartedEvent,
)
from virgo.contracts.events.recovery import (
    RecoveryAttemptEvent,
    RecoveryFailedEvent,
    RecoveryStartedEvent,
    RecoverySucceededEvent,
)
from virgo.contracts.events.security import (
    SecurityAnalysisCompletedEvent,
    SecurityAnalysisFailedEvent,
    SecurityAnalysisStartedEvent,
    SecurityFindingDetectedEvent,
)
from virgo.contracts.events.state import (
    ApplicationState,
    ApplicationStateChangedEvent,
    ApplicationStateSnapshot,
)
from virgo.contracts.events.status import ErrorOccurredEvent, StatusMessageEvent

__all__ = (
    "ApplicationEvent",
    "ApplicationStartedEvent",
    "ApplicationState",
    "ApplicationStateChangedEvent",
    "ApplicationStateSnapshot",
    "ApplicationStoppingEvent",
    "ConversationCancelledEvent",
    "ConversationChunkEvent",
    "ConversationCompletedEvent",
    "ConversationFailedEvent",
    "ConversationStartedEvent",
    "CreationPermissionRequestedEvent",
    "CreationPlanPreparedEvent",
    "InterruptionCompletedEvent",
    "InterruptionRequestedEvent",
    "KnowledgeAcceptedEvent",
    "KnowledgeGapDetectedEvent",
    "LearningProposalReadyEvent",
    "PersonalTaskCancelledEvent",
    "PersonalTaskCompletedEvent",
    "PersonalTaskFailedEvent",
    "PersonalTaskPlanCreatedEvent",
    "PersonalTaskStartedEvent",
    "ImprovementProposalReadyEvent",
    "SelfInspectionCompletedEvent",
    "SelfInspectionStartedEvent",
    "SelfImprovementAcceptedEvent",
    "SelfImprovementApprovalRequiredEvent",
    "SelfImprovementAppliedEvent",
    "SelfImprovementRolledBackEvent",
    "RecoveryAttemptEvent",
    "RecoveryFailedEvent",
    "RecoveryStartedEvent",
    "RecoverySucceededEvent",
    "ErrorOccurredEvent",
    "EventDictionary",
    "StatusMessageEvent",
    "SecurityAnalysisCompletedEvent",
    "SecurityAnalysisFailedEvent",
    "SecurityAnalysisStartedEvent",
    "SecurityFindingDetectedEvent",
)
