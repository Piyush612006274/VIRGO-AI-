"""Virgo SLM Phase 3 dataset pipeline.

See ``virgo_slm/PROGRESS.md`` for status and
``virgo_slm/dataset/pipeline.py`` for the orchestration entry point
(``run_pipeline``).
"""

from virgo_slm.dataset.config import DatasetPipelineConfig, DatasetSourceConfig
from virgo_slm.dataset.pipeline import PipelineResult, run_pipeline

__all__ = [
    "DatasetPipelineConfig",
    "DatasetSourceConfig",
    "PipelineResult",
    "run_pipeline",
]
