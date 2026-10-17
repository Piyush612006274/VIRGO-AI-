"""Integrated, local-first Stage 2 creation routing and verification."""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path
from uuid import uuid4

from virgo.contracts.errors import ValidationError
from virgo.contracts.models.creation_engine import (
    AnalysisFinding,
    ArtifactKind,
    ArtifactMetadata,
    CreationCapability,
    EnrichedCreationSpecification,
    ExternalOperationPreview,
    MediaRequest,
    ProviderSelection,
    ProviderState,
    WebsiteAnalysisReport,
)
from virgo.contracts.protocols import (
    ExternalCreationProviderProtocol,
    MediaProviderProtocol,
)

_PROHIBITED = re.compile(
    r"\b(port scan|vulnerability scan|exploit|malware|credential attack|"
    r"self[- ]improv|autonomous agent|browser automation|desktop automation)\b",
    re.IGNORECASE,
)
_WEBSITE_REQUEST = re.compile(
    r"\b(?:website|web\s*page|landing\s+page|portfolio(?:\s+(?:site|website))?)\b",
    re.IGNORECASE,
)
_EXPLICIT_HEADING = re.compile(
    r"\b(?:heading|title)\s+(?:of\s+|is\s+)?[\"']?" r"(?P<heading>[^.!?\r\n\"']+)",
    re.IGNORECASE,
)


def is_website_creation_request(request: str) -> bool:
    """Return whether normalized user language names a website artifact."""

    return _WEBSITE_REQUEST.search(" ".join(request.split())) is not None


class CreationCapabilityRouter:
    """Classify intent without executing it or trusting executable names."""

    def route(self, request: str) -> CreationCapability:
        text = request.strip().lower()
        if not text:
            raise ValidationError("Creation request is empty", source_module=__name__)
        if _PROHIBITED.search(text):
            raise ValidationError(
                "Requested capability belongs to a later or prohibited stage",
                source_module=__name__,
            )
        rules = (
            (("wordpress",), CreationCapability.WORDPRESS_WORKFLOW),
            (("shopify",), CreationCapability.SHOPIFY_WORKFLOW),
            (("seo",), CreationCapability.ANALYZE_SEO),
            (
                ("analytics", "analyze website", "website analysis"),
                CreationCapability.ANALYZE_WEBSITE,
            ),
            (("enhance image", "upscale image"), CreationCapability.ENHANCE_IMAGE),
            (("edit image", "modify image"), CreationCapability.EDIT_IMAGE),
            (("image", "illustration"), CreationCapability.GENERATE_IMAGE),
            (("video",), CreationCapability.GENERATE_VIDEO),
            (("test",), CreationCapability.TEST_CODE),
            (
                ("analyze project", "inspect project", "explain project"),
                CreationCapability.ANALYZE_PROJECT,
            ),
            (("backend", "api"), CreationCapability.CREATE_BACKEND),
            (("application", " app "), CreationCapability.CREATE_APPLICATION),
            (("frontend",), CreationCapability.CREATE_FRONTEND),
            (("modify website", "edit website"), CreationCapability.MODIFY_WEBSITE),
            (("generate code", "write code"), CreationCapability.GENERATE_CODE),
        )
        padded = f" {text} "
        for terms, capability in rules:
            if any(term in padded for term in terms):
                return capability
        if is_website_creation_request(text):
            return CreationCapability.CREATE_WEBSITE
        return CreationCapability.EDIT_PROJECT


class PromptEnricher:
    """Turn user language into a bounded specification without inventing facts."""

    def enrich(
        self, request: str, capability: CreationCapability
    ) -> EnrichedCreationSpecification:
        text = request.strip()
        requirements = tuple(
            item
            for item in (
                "responsive layout" if "responsive" in text.lower() else "",
                "local JavaScript interaction" if "javascript" in text.lower() else "",
                (
                    "preserve existing project conventions"
                    if "existing" in text.lower()
                    else ""
                ),
            )
            if item
        )
        kind = self._kind(capability)
        heading_match = _EXPLICIT_HEADING.search(text)
        heading = (
            heading_match.group("heading").strip()
            if heading_match is not None
            else None
        )
        missing: tuple[str, ...] = ()
        if capability in {
            CreationCapability.EDIT_IMAGE,
            CreationCapability.ENHANCE_IMAGE,
        } and not re.search(r"\b[\w.-]+\.(png|jpe?g|webp)\b", text, re.IGNORECASE):
            missing = ("Which source image should be used?",)
        return EnrichedCreationSpecification(
            original_request=text,
            capability=capability,
            project_type=capability.value,
            requirements=requirements or ("fulfil the stated request",),
            constraints=(
                "local-first",
                "no deployment",
                "no unapproved dependency installation",
            ),
            target_artifacts=(kind,),
            validation_expectations=(
                "non-empty output",
                "approved scope only",
                "deterministic validation",
            ),
            missing_requirements=missing,
            heading=heading,
        )

    @staticmethod
    def _kind(capability: CreationCapability) -> ArtifactKind:
        if capability in {
            CreationCapability.CREATE_WEBSITE,
            CreationCapability.MODIFY_WEBSITE,
            CreationCapability.CREATE_FRONTEND,
        }:
            return ArtifactKind.WEBSITE
        if capability in {
            CreationCapability.GENERATE_IMAGE,
            CreationCapability.EDIT_IMAGE,
            CreationCapability.ENHANCE_IMAGE,
        }:
            return ArtifactKind.IMAGE
        if capability is CreationCapability.GENERATE_VIDEO:
            return ArtifactKind.VIDEO
        if capability in {
            CreationCapability.WORDPRESS_WORKFLOW,
            CreationCapability.SHOPIFY_WORKFLOW,
        }:
            return ArtifactKind.REMOTE_OPERATION
        return ArtifactKind.CODE


class ModelSelector:
    """Explainable selection over explicitly configured providers only."""

    def select(
        self,
        capability: CreationCapability,
        *,
        local_model: str | None = None,
        configured_providers: tuple[str, ...] = (),
    ) -> ProviderSelection:
        if capability in {
            CreationCapability.WORDPRESS_WORKFLOW,
            CreationCapability.SHOPIFY_WORKFLOW,
        }:
            provider = (
                "wordpress"
                if capability is CreationCapability.WORDPRESS_WORKFLOW
                else "shopify"
            )
            state = (
                ProviderState.AVAILABLE
                if provider in configured_providers
                else ProviderState.NOT_CONFIGURED
            )
            return ProviderSelection(
                provider=provider,
                model=None,
                state=state,
                explanation=f"{provider} requires explicit external configuration; no operation was executed",
                local=False,
            )
        if capability in {
            CreationCapability.GENERATE_IMAGE,
            CreationCapability.EDIT_IMAGE,
            CreationCapability.ENHANCE_IMAGE,
        }:
            return self._optional_media("image", configured_providers)
        if capability is CreationCapability.GENERATE_VIDEO:
            return self._optional_media("video", configured_providers)
        if local_model:
            return ProviderSelection(
                provider="ollama",
                model=local_model,
                state=ProviderState.AVAILABLE,
                explanation="Selected the configured local model; no cloud fallback",
                local=True,
            )
        return ProviderSelection(
            provider="deterministic-local",
            model="builtin-v1",
            state=ProviderState.AVAILABLE,
            explanation="Selected deterministic local capability because no model is required",
            local=True,
        )

    @staticmethod
    def _optional_media(name: str, configured: tuple[str, ...]) -> ProviderSelection:
        state = (
            ProviderState.AVAILABLE
            if name in configured
            else ProviderState.NOT_CONFIGURED
        )
        return ProviderSelection(
            provider=name,
            model=None,
            state=state,
            explanation=(
                f"No configured {name} provider; automatic download and cloud fallback are disabled"
                if state is ProviderState.NOT_CONFIGURED
                else f"Selected explicitly configured {name} provider"
            ),
            local=name in configured,
        )


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = False
        self.meta_names: set[str] = set()
        self.headings: list[int] = []
        self.images_without_alt = 0
        self.links: list[str] = []
        self.words = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "title":
            self.title = True
        if tag == "meta" and values.get("name"):
            self.meta_names.add(values["name"].lower())  # type: ignore[union-attr]
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append(int(tag[1]))
        if tag == "img" and not values.get("alt"):
            self.images_without_alt += 1
        if tag == "a" and values.get("href"):
            self.links.append(values["href"] or "")

    def handle_data(self, data: str) -> None:
        self.words += len(data.split())


class WebsiteAnalyzer:
    """Deterministic local analytics/SEO; never implies live ranking data."""

    def analyze(self, root: Path) -> WebsiteAnalysisReport:
        findings: list[AnalysisFinding] = []
        files = tuple(sorted(path for path in root.rglob("*.html") if path.is_file()))
        words = 0
        for path in files:
            relative = path.relative_to(root).as_posix()
            parser = _PageParser()
            parser.feed(path.read_text(encoding="utf-8"))
            words += parser.words
            checks = (
                (
                    not parser.title,
                    "missing-title",
                    "high",
                    "Add a descriptive title element",
                ),
                (
                    "description" not in parser.meta_names,
                    "missing-description",
                    "medium",
                    "Add a concise meta description",
                ),
                (
                    "viewport" not in parser.meta_names,
                    "missing-viewport",
                    "high",
                    "Add a mobile viewport meta tag",
                ),
                (
                    not parser.headings or parser.headings[0] != 1,
                    "heading-hierarchy",
                    "medium",
                    "Start the main content with one h1",
                ),
                (
                    parser.images_without_alt > 0,
                    "missing-image-alt",
                    "medium",
                    "Add meaningful alt text to images",
                ),
            )
            for failed, code, severity, suggestion in checks:
                if failed:
                    findings.append(
                        AnalysisFinding(
                            code=code,
                            severity=severity,
                            explanation=f"{relative}: deterministic local check found {code.replace('-', ' ')}",
                            suggested_change=suggestion,
                            target=relative,
                        )
                    )
        return WebsiteAnalysisReport(
            files_analyzed=tuple(path.relative_to(root).as_posix() for path in files),
            findings=tuple(findings),
            content_words=words,
        )


class UnconfiguredExternalProvider(ExternalCreationProviderProtocol):
    def __init__(self, name: str, capability: CreationCapability) -> None:
        self._name, self._capability = name, capability

    @property
    def name(self) -> str:
        return self._name

    def status(self) -> ProviderState:
        return ProviderState.NOT_CONFIGURED

    def preview(
        self, specification: EnrichedCreationSpecification
    ) -> ExternalOperationPreview:
        return ExternalOperationPreview(
            capability=self._capability,
            operation="preview only",
            target=self._name,
            exact_changes=(specification.original_request,),
            provider=ProviderSelection(
                provider=self._name,
                model=None,
                state=self.status(),
                explanation="Provider is not configured; no external request was made",
                local=False,
            ),
        )

    def apply(self, preview: ExternalOperationPreview) -> str:
        del preview
        raise ValidationError(
            "External provider is not configured", source_module=__name__
        )


class ExternalCreationWorkflow:
    """Keep remote previews non-mutating and require explicit operation approval."""

    def prepare(
        self,
        provider: ExternalCreationProviderProtocol,
        specification: EnrichedCreationSpecification,
    ) -> ExternalOperationPreview:
        return provider.preview(specification)

    def apply(
        self,
        provider: ExternalCreationProviderProtocol,
        preview: ExternalOperationPreview,
        *,
        approved: bool,
    ) -> str:
        if not approved:
            raise ValidationError(
                "External operation requires approval", source_module=__name__
            )
        if provider.status() is not ProviderState.AVAILABLE:
            raise ValidationError(
                "External provider is not configured", source_module=__name__
            )
        return provider.apply(preview)


class ArtifactStager:
    """Task-scoped temporary media staging with explicit placement and cleanup."""

    def __init__(self, task_id: str) -> None:
        if not task_id.strip():
            raise ValueError("task_id must not be empty")
        self.root = Path(tempfile.mkdtemp(prefix=f"virgo-{task_id[:12]}-"))

    def verify(self, artifact: ArtifactMetadata) -> ArtifactMetadata:
        path = Path(artifact.staged_path)
        if (
            not path.is_relative_to(self.root)
            or not path.is_file()
            or path.stat().st_size == 0
        ):
            raise ValidationError(
                "Staged artifact verification failed", source_module=__name__
            )
        supported = {
            ArtifactKind.IMAGE: {"png", "jpg", "jpeg", "webp"},
            ArtifactKind.VIDEO: {"mp4", "webm", "mov"},
        }
        if (
            artifact.kind in supported
            and artifact.format.lower() not in supported[artifact.kind]
        ):
            raise ValidationError(
                "Unsupported staged artifact format", source_module=__name__
            )
        return replace(artifact, size_bytes=path.stat().st_size, verified=True)

    def accept(self, artifact: ArtifactMetadata, destination: Path) -> Path:
        if not artifact.verified:
            raise ValidationError(
                "Artifact must be verified before acceptance", source_module=__name__
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        Path(artifact.staged_path).replace(destination)
        return destination

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


class MediaWorkflow:
    """Orchestrate provider output through task staging and explicit acceptance."""

    def stage(
        self,
        provider: MediaProviderProtocol,
        request: MediaRequest,
        stager: ArtifactStager,
    ) -> ArtifactMetadata:
        if provider.status() is not ProviderState.AVAILABLE:
            raise ValidationError(
                "Media provider is not configured", source_module=__name__
            )
        return stager.verify(provider.generate(request, stager.root))

    def accept(
        self,
        stager: ArtifactStager,
        artifact: ArtifactMetadata,
        destination: Path,
        *,
        approved: bool,
    ) -> Path:
        if not approved:
            raise ValidationError(
                "Artifact placement requires approval", source_module=__name__
            )
        return stager.accept(artifact, destination)


class CreationEngine:
    """Small facade joining typed routing, enrichment, selection, and safe previews."""

    def __init__(self) -> None:
        self.router = CreationCapabilityRouter()
        self.enricher = PromptEnricher()
        self.selector = ModelSelector()

    def prepare(
        self,
        request: str,
        *,
        local_model: str | None = None,
        configured_providers: tuple[str, ...] = (),
    ) -> tuple[EnrichedCreationSpecification, ProviderSelection]:
        capability = self.router.route(request)
        specification = self.enricher.enrich(request, capability)
        return specification, self.selector.select(
            capability,
            local_model=local_model,
            configured_providers=configured_providers,
        )


def new_artifact_id() -> str:
    return uuid4().hex
