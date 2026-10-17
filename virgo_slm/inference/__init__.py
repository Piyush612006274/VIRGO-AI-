"""Local inference runtime for the Virgo SLM."""

from virgo_slm.inference.runtime import (
    ArtifactMetadata,
    GenerationConfig,
    ModelArtifact,
    SLMRuntime,
    load_artifact,
    save_artifact,
)

__all__ = (
    "ArtifactMetadata",
    "GenerationConfig",
    "ModelArtifact",
    "SLMRuntime",
    "load_artifact",
    "save_artifact",
)
