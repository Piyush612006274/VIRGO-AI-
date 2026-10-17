"""Provider-neutral protocols for external and non-text creation."""

from pathlib import Path
from typing import Protocol

from virgo.contracts.models.creation_engine import (
    ArtifactMetadata,
    EnrichedCreationSpecification,
    ExternalOperationPreview,
    MediaRequest,
    ProviderState,
)


class ExternalCreationProviderProtocol(Protocol):
    @property
    def name(self) -> str: ...

    def status(self) -> ProviderState: ...

    def preview(
        self, specification: EnrichedCreationSpecification
    ) -> ExternalOperationPreview: ...

    def apply(self, preview: ExternalOperationPreview) -> str: ...


class MediaProviderProtocol(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    def status(self) -> ProviderState: ...

    def generate(
        self, request: MediaRequest, staging_directory: Path
    ) -> ArtifactMetadata: ...
