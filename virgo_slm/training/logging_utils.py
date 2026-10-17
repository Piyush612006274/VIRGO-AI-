"""Structured training metrics + console/JSONL logging.

No external experiment-tracking dependency (Task 16 explicitly does not
require one) -- console output plus a machine-readable ``metrics.jsonl``
file (one JSON object per logged event) is enough to plot/inspect a run
afterward, and the interface (:class:`MetricsLogger`) is narrow enough
that swapping in a real tracker later is a new implementation of the same
two methods, not a rewrite of the trainer.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol


def perplexity_from_loss(loss: float) -> float:
    """``exp(loss)``, mathematically valid only for a mean cross-entropy loss.

    Guards against overflow for pathological (very large) loss values --
    returns ``float('inf')`` rather than raising, since "the model is
    currently producing garbage" is a valid, reportable training state,
    not an error.
    """
    try:
        return math.exp(loss)
    except OverflowError:
        return float("inf")


@dataclass(frozen=True, slots=True)
class TrainingMetrics:
    """One logged event's worth of metrics (Task 11/16's required fields)."""

    step: int
    epoch: int
    train_loss: float | None
    validation_loss: float | None
    validation_perplexity: float | None
    learning_rate: float
    tokens_processed: int
    elapsed_seconds: float
    event: str = "train_step"  # or "validation", "checkpoint"
    timestamp_unix: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp_unix == 0.0:
            object.__setattr__(self, "timestamp_unix", time.time())


class MetricsSink(Protocol):
    def log(self, metrics: TrainingMetrics) -> None: ...


class ConsoleLogger:
    def log(self, metrics: TrainingMetrics) -> None:
        parts = [f"step={metrics.step}", f"epoch={metrics.epoch}"]
        if metrics.train_loss is not None:
            parts.append(f"train_loss={metrics.train_loss:.4f}")
        if metrics.validation_loss is not None:
            parts.append(f"val_loss={metrics.validation_loss:.4f}")
        if metrics.validation_perplexity is not None:
            parts.append(f"val_ppl={metrics.validation_perplexity:.2f}")
        parts.append(f"lr={metrics.learning_rate:.6g}")
        parts.append(f"tokens={metrics.tokens_processed}")
        parts.append(f"elapsed={metrics.elapsed_seconds:.1f}s")
        print(f"[{metrics.event}] " + " ".join(parts))


class JsonlLogger:
    """Appends one JSON line per :meth:`log` call to ``log_dir/metrics.jsonl``."""

    def __init__(self, log_dir: str | Path) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.log_dir / "metrics.jsonl"

    def log(self, metrics: TrainingMetrics) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(metrics)) + "\n")


class MultiLogger:
    """Fans one metrics event out to several sinks (e.g. console + JSONL)."""

    def __init__(self, sinks: list[MetricsSink]) -> None:
        self._sinks = sinks

    def log(self, metrics: TrainingMetrics) -> None:
        for sink in self._sinks:
            sink.log(metrics)
