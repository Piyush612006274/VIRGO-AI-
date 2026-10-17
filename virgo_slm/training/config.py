"""Phase 4 training configuration.

Same convention as every other config in this repo (``model/config.py``,
``tokenizer/config.py``, ``dataset/config.py``): frozen dataclasses,
validated in ``__post_init__`` via a local ``require()`` helper, no
machine-specific defaults baked in.

Split into sub-configs per responsibility (Task 2/3) rather than one flat
dataclass: ``DataConfig``, ``OptimizerConfig``, ``SchedulerConfig``,
``CheckpointConfig``, ``PrecisionConfig``, ``DeviceConfig``,
``LoggingConfig``, aggregated into ``TrainingConfig``. All validation
errors raise :class:`virgo_slm.training.errors.InvalidTrainingConfigError`
(not a bare ``ValueError``, unlike the earlier phases) so Task 20/26's
"invalid configuration fails clearly and specifically" requirement is
satisfiable by ``except InvalidTrainingConfigError`` at call sites, not
by clearing on any ``ValueError``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from virgo_slm.training.errors import InvalidTrainingConfigError

Device = Literal["cpu", "cuda", "auto"]
Precision = Literal["fp32", "fp16", "bf16", "auto"]
SchedulerKind = Literal["cosine", "constant"]


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _raise_if_errors(errors: list[str], config_name: str) -> None:
    if errors:
        raise InvalidTrainingConfigError(
            f"Invalid {config_name}: " + "; ".join(errors)
        )


@dataclass(frozen=True, slots=True)
class DataConfig:
    """Where training/validation data comes from and how it's packed.

    ``dataset_manifest_path`` points at a Phase 3
    ``dataset_manifest.json`` (see ``virgo_slm.dataset.manifest``) --
    Phase 4 does not re-implement ingestion/filtering/splitting, it
    consumes Phase 3's already-split, already-deduplicated records.
    ``dataset_output_dir`` is the directory that manifest's split files
    live in (same directory Phase 3's ``run_pipeline`` wrote to).
    """

    dataset_output_dir: str
    tokenizer_dir: str
    block_size: int = 128
    num_workers: int = 0

    def __post_init__(self) -> None:
        errors: list[str] = []
        _require(bool(self.dataset_output_dir), "dataset_output_dir must not be empty", errors)
        _require(bool(self.tokenizer_dir), "tokenizer_dir must not be empty", errors)
        _require(self.block_size >= 2, "block_size must be >= 2 (need at least 1 supervised position)", errors)
        _require(self.num_workers >= 0, "num_workers must be non-negative", errors)
        _raise_if_errors(errors, "DataConfig")


@dataclass(frozen=True, slots=True)
class OptimizerConfig:
    learning_rate: float = 3e-4
    betas: tuple[float, float] = (0.9, 0.95)
    eps: float = 1e-8
    weight_decay: float = 0.1

    def __post_init__(self) -> None:
        errors: list[str] = []
        _require(self.learning_rate > 0, "learning_rate must be positive", errors)
        _require(len(self.betas) == 2, "betas must have exactly 2 elements", errors)
        _require(
            all(0.0 <= b < 1.0 for b in self.betas), "betas must be in [0, 1)", errors
        )
        _require(self.eps > 0, "eps must be positive", errors)
        _require(self.weight_decay >= 0, "weight_decay must be non-negative", errors)
        _raise_if_errors(errors, "OptimizerConfig")


@dataclass(frozen=True, slots=True)
class SchedulerConfig:
    kind: SchedulerKind = "cosine"
    warmup_steps: int = 10
    total_steps: int = 100
    min_lr_ratio: float = 0.1  # min_lr = learning_rate * min_lr_ratio

    def __post_init__(self) -> None:
        errors: list[str] = []
        _require(self.warmup_steps >= 0, "warmup_steps must be non-negative", errors)
        _require(self.total_steps >= 1, "total_steps must be >= 1", errors)
        _require(
            self.warmup_steps <= self.total_steps,
            "warmup_steps must not exceed total_steps",
            errors,
        )
        _require(
            0.0 <= self.min_lr_ratio <= 1.0, "min_lr_ratio must be in [0, 1]", errors
        )
        _raise_if_errors(errors, "SchedulerConfig")


@dataclass(frozen=True, slots=True)
class CheckpointConfig:
    output_dir: str = "checkpoints"
    save_every_n_steps: int = 50
    keep_last_n: int = 3
    resume_from: str | None = None

    def __post_init__(self) -> None:
        errors: list[str] = []
        _require(bool(self.output_dir), "output_dir must not be empty", errors)
        _require(self.save_every_n_steps >= 1, "save_every_n_steps must be >= 1", errors)
        _require(self.keep_last_n >= 1, "keep_last_n must be >= 1", errors)
        _raise_if_errors(errors, "CheckpointConfig")


@dataclass(frozen=True, slots=True)
class PrecisionConfig:
    precision: Precision = "fp32"

    def __post_init__(self) -> None:
        errors: list[str] = []
        _require(
            self.precision in ("fp32", "fp16", "bf16", "auto"),
            f"unsupported precision: {self.precision!r}",
            errors,
        )
        _raise_if_errors(errors, "PrecisionConfig")


@dataclass(frozen=True, slots=True)
class DeviceConfig:
    device: Device = "cpu"

    def __post_init__(self) -> None:
        errors: list[str] = []
        _require(
            self.device in ("cpu", "cuda", "auto"),
            f"unsupported device: {self.device!r}",
            errors,
        )
        _raise_if_errors(errors, "DeviceConfig")


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    log_every_n_steps: int = 10
    validate_every_n_steps: int = 50
    max_validation_batches: int | None = None
    log_dir: str = "logs"

    def __post_init__(self) -> None:
        errors: list[str] = []
        _require(self.log_every_n_steps >= 1, "log_every_n_steps must be >= 1", errors)
        _require(
            self.validate_every_n_steps >= 1, "validate_every_n_steps must be >= 1", errors
        )
        if self.max_validation_batches is not None:
            _require(
                self.max_validation_batches >= 1,
                "max_validation_batches must be >= 1 when set",
                errors,
            )
        _require(bool(self.log_dir), "log_dir must not be empty", errors)
        _raise_if_errors(errors, "LoggingConfig")


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    """Aggregates every Phase 4 sub-config into one run configuration."""

    model_preset: str
    data: DataConfig
    optimizer: OptimizerConfig = field(default_factory=OptimizerConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    checkpoint: CheckpointConfig = field(default_factory=CheckpointConfig)
    precision: PrecisionConfig = field(default_factory=PrecisionConfig)
    device: DeviceConfig = field(default_factory=DeviceConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    per_device_batch_size: int = 4
    gradient_accumulation_steps: int = 1
    max_grad_norm: float = 1.0
    seed: int = 42

    name: str = "virgo-slm-training-run"
    version: str = "0.1.0"

    def __post_init__(self) -> None:
        errors: list[str] = []
        _require(bool(self.model_preset), "model_preset must not be empty", errors)
        _require(self.per_device_batch_size >= 1, "per_device_batch_size must be >= 1", errors)
        _require(
            self.gradient_accumulation_steps >= 1,
            "gradient_accumulation_steps must be >= 1",
            errors,
        )
        _require(self.max_grad_norm > 0, "max_grad_norm must be positive", errors)
        _raise_if_errors(errors, "TrainingConfig")

    @property
    def effective_batch_size(self) -> int:
        """``per_device_batch_size * gradient_accumulation_steps`` (single device).

        Task 9 requires this be explicit and documented:
        ``effective_batch_size = per_device_batch_size *
        gradient_accumulation_steps * number_of_devices``. This repo's
        Phase 4 scope is single-device (CPU/one CUDA device) training, so
        ``number_of_devices`` is always 1 here; multi-device training is
        out of scope and not claimed.
        """
        return self.per_device_batch_size * self.gradient_accumulation_steps
