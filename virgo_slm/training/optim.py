"""Optimizer and LR scheduler construction.

AdamW (the standard choice for Transformer pretraining, and what the
task brief calls for by default) with a linear-warmup + cosine-decay
schedule down to ``min_lr_ratio * learning_rate`` -- no exotic
optimizers, matching Task 7's "do not introduce unnecessary exotic
optimization techniques."

The scheduler is a plain, checkpointable ``step -> LR multiplier``
callable wrapped in ``torch.optim.lr_scheduler.LambdaLR`` rather than a
hand-rolled stateful object, so its entire "state" is the optimizer step
count already tracked by the trainer -- resuming correctly is then just
restoring ``last_epoch`` on the ``LambdaLR``, natively supported.
"""

from __future__ import annotations

import math

import torch
from torch.optim.lr_scheduler import LambdaLR

from virgo_slm.training.config import OptimizerConfig, SchedulerConfig


def build_optimizer(
    model: torch.nn.Module, config: OptimizerConfig
) -> torch.optim.AdamW:
    return torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        betas=config.betas,
        eps=config.eps,
        weight_decay=config.weight_decay,
    )


class _CosineWithWarmup:
    """``step -> LR multiplier`` for linear warmup + cosine decay to a floor.

    - ``step < warmup_steps``: linear ramp from 0 to 1.
    - ``warmup_steps <= step <= total_steps``: cosine decay from 1 down to
      ``min_lr_ratio``.
    - ``step > total_steps``: held at ``min_lr_ratio`` (does not go
      negative or oscillate past the intended schedule length).

    A real class (not a closure) so it's unambiguous what state a
    checkpointed scheduler depends on.
    """

    def __init__(self, config: SchedulerConfig) -> None:
        self.warmup_steps = config.warmup_steps
        self.total_steps = config.total_steps
        self.min_lr_ratio = config.min_lr_ratio

    def __call__(self, step: int) -> float:
        if self.warmup_steps > 0 and step < self.warmup_steps:
            return step / self.warmup_steps
        decay_steps = max(self.total_steps - self.warmup_steps, 1)
        progress = min((step - self.warmup_steps) / decay_steps, 1.0)
        cosine = 0.5 * (1.0 + math.cos(math.pi * progress))
        return self.min_lr_ratio + (1.0 - self.min_lr_ratio) * cosine


def build_scheduler(
    optimizer: torch.optim.Optimizer, config: SchedulerConfig
) -> LambdaLR:
    if config.kind == "constant":
        return LambdaLR(optimizer, lr_lambda=lambda _step: 1.0)
    return LambdaLR(optimizer, lr_lambda=_CosineWithWarmup(config))
