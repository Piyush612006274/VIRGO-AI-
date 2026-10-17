"""Virgo SLM Phase 4 training system.

See ``virgo_slm/PROGRESS.md`` for status and ``virgo_slm/training/trainer.py``
for the orchestration entry point (``Trainer`` / ``build_trainer``).
"""

from virgo_slm.training.config import TrainingConfig
from virgo_slm.training.trainer import Trainer, TrainingRunResult, build_trainer

__all__ = [
    "Trainer",
    "TrainingConfig",
    "TrainingRunResult",
    "build_trainer",
]
