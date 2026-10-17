"""Controlled learning capability."""

from virgo.capabilities.learning.engine import (
    KnowledgeQualityFilter,
    LearningEngine,
    UnconfiguredResearchProvider,
)
from virgo.capabilities.learning.experience import (
    EvaluationEngine,
    ExperienceLearningService,
    SelfInspectionService,
    SkillValidationService,
)
from virgo.capabilities.learning.self_improvement import SelfImprovementCoordinator

__all__ = (
    "EvaluationEngine",
    "ExperienceLearningService",
    "KnowledgeQualityFilter",
    "LearningEngine",
    "SelfInspectionService",
    "SelfImprovementCoordinator",
    "SkillValidationService",
    "UnconfiguredResearchProvider",
)
