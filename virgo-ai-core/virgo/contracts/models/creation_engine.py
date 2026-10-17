"""Typed contracts for the complete Stage 2 Creation Engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CreationCapability(StrEnum):
    CREATE_WEBSITE = "create_website"
    MODIFY_WEBSITE = "modify_website"
    CREATE_FRONTEND = "create_frontend"
    CREATE_BACKEND = "create_backend"
    CREATE_APPLICATION = "create_application"
    EDIT_PROJECT = "edit_project"
    ANALYZE_PROJECT = "analyze_project"
    GENERATE_CODE = "generate_code"
    TEST_CODE = "test_code"
    ANALYZE_WEBSITE = "analyze_website"
    ANALYZE_SEO = "analyze_seo"
    WORDPRESS_WORKFLOW = "wordpress_workflow"
    SHOPIFY_WORKFLOW = "shopify_workflow"
    GENERATE_IMAGE = "generate_image"
    EDIT_IMAGE = "edit_image"
    ENHANCE_IMAGE = "enhance_image"
    GENERATE_VIDEO = "generate_video"


class ProviderState(StrEnum):
    AVAILABLE = "available"
    NOT_CONFIGURED = "not_configured"
    UNAVAILABLE = "unavailable"


class ArtifactKind(StrEnum):
    TEXT = "text"
    CODE = "code"
    WEBSITE = "website"
    IMAGE = "image"
    VIDEO = "video"
    REMOTE_OPERATION = "remote_operation"


@dataclass(frozen=True, slots=True, kw_only=True)
class EnrichedCreationSpecification:
    original_request: str
    capability: CreationCapability
    project_type: str
    requirements: tuple[str, ...]
    constraints: tuple[str, ...]
    target_artifacts: tuple[ArtifactKind, ...]
    validation_expectations: tuple[str, ...]
    missing_requirements: tuple[str, ...] = ()
    heading: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderSelection:
    provider: str
    model: str | None
    state: ProviderState
    explanation: str
    local: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisFinding:
    code: str
    severity: str
    explanation: str
    suggested_change: str
    target: str


@dataclass(frozen=True, slots=True, kw_only=True)
class WebsiteAnalysisReport:
    files_analyzed: tuple[str, ...]
    findings: tuple[AnalysisFinding, ...]
    content_words: int
    external_data_used: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactMetadata:
    artifact_id: str
    kind: ArtifactKind
    format: str
    size_bytes: int
    provider: str
    model: str | None
    staged_path: str
    verified: bool
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ExternalOperationPreview:
    capability: CreationCapability
    operation: str
    target: str
    exact_changes: tuple[str, ...]
    provider: ProviderSelection
    requires_permission: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class MediaRequest:
    capability: CreationCapability
    prompt: str
    source_path: str | None = None
    expected_format: str | None = None
    width: int | None = None
    height: int | None = None
