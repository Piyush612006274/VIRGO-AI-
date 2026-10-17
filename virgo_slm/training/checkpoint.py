"""Checkpoint save/load/resume.

A checkpoint is a single ``torch.save`` file containing everything Task
13 requires to resume correctly: model state, optimizer state, scheduler
state, step, epoch, the exact model/training config used (so an
incompatible resume attempt fails loudly instead of silently training a
different architecture), tokenizer identity (name/version/vocab_size —
not the tokenizer artifact itself, which is Phase 2's to own), RNG state,
and free-form metadata.

:class:`CheckpointManager` owns the directory-level policy: periodic
saves, a retention limit (``keep_last_n``), and a ``latest.txt`` pointer
file so "resume from the latest checkpoint" doesn't require the caller to
know step numbers.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

from virgo_slm.model.config import VirgoSLMConfig
from virgo_slm.training.config import TrainingConfig
from virgo_slm.training.errors import IncompatibleCheckpointError, InvalidCheckpointError

CHECKPOINT_FORMAT_VERSION = "0.1.0"
LATEST_POINTER_FILE = "latest.txt"


@dataclass(frozen=True, slots=True)
class TokenizerIdentity:
    name: str
    version: str
    vocab_size: int


@dataclass(frozen=True, slots=True)
class CheckpointMetadata:
    checkpoint_format_version: str
    step: int
    epoch: int
    model_config: dict[str, Any]
    training_config_name: str
    training_config_version: str
    tokenizer_identity: dict[str, Any]
    seed: int
    extra: dict[str, Any]


def _rng_state() -> dict[str, Any]:
    state: dict[str, Any] = {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch_cpu": torch.random.get_rng_state(),
    }
    if torch.cuda.is_available():
        state["torch_cuda"] = torch.cuda.get_rng_state_all()
    return state


def _restore_rng_state(state: dict[str, Any]) -> None:
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch.random.set_rng_state(state["torch_cpu"])
    if "torch_cuda" in state and torch.cuda.is_available():
        torch.cuda.set_rng_state_all(state["torch_cuda"])


def save_checkpoint(
    path: str | Path,
    *,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    scheduler: torch.optim.lr_scheduler.LRScheduler,
    step: int,
    epoch: int,
    model_config: VirgoSLMConfig,
    training_config: TrainingConfig,
    tokenizer_identity: TokenizerIdentity,
    extra: dict[str, Any] | None = None,
) -> None:
    """Write one checkpoint file containing everything needed to resume."""
    metadata = CheckpointMetadata(
        checkpoint_format_version=CHECKPOINT_FORMAT_VERSION,
        step=step,
        epoch=epoch,
        model_config=asdict(model_config),
        training_config_name=training_config.name,
        training_config_version=training_config.version,
        tokenizer_identity=asdict(tokenizer_identity),
        seed=training_config.seed,
        extra=extra or {},
    )
    payload = {
        "metadata": asdict(metadata),
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "scheduler_state_dict": scheduler.state_dict(),
        "rng_state": _rng_state(),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file then rename: an interrupted save (Task 15)
    # leaves the previous checkpoint at `path` untouched rather than a
    # half-written file, since os.replace/rename is atomic on the same
    # filesystem.
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, tmp_path)
    tmp_path.replace(path)


def load_checkpoint(path: str | Path, *, map_location: str = "cpu") -> dict[str, Any]:
    """Load and structurally validate a checkpoint file.

    Raises :class:`InvalidCheckpointError` for a missing file, a file
    that isn't a valid torch checkpoint, or one missing required keys --
    never returns a partially-usable result silently.
    """
    path = Path(path)
    if not path.exists():
        raise InvalidCheckpointError(f"Checkpoint does not exist: {path}")
    try:
        payload = torch.load(path, map_location=map_location, weights_only=False)
    except Exception as exc:  # noqa: BLE001 - re-raised as a typed error below
        raise InvalidCheckpointError(f"Could not load checkpoint {path}: {exc}") from exc

    required_keys = {
        "metadata", "model_state_dict", "optimizer_state_dict",
        "scheduler_state_dict", "rng_state",
    }
    if not isinstance(payload, dict) or not required_keys.issubset(payload.keys()):
        missing = required_keys - (payload.keys() if isinstance(payload, dict) else set())
        raise InvalidCheckpointError(
            f"Checkpoint {path} is missing required keys: {sorted(missing)}"
        )
    return payload


def verify_checkpoint_compatibility(
    checkpoint: dict[str, Any], *, model_config: VirgoSLMConfig
) -> None:
    """Raise :class:`IncompatibleCheckpointError` if configs genuinely mismatch.

    Checks the fields that would make resuming *wrong* (silently training
    a different architecture) rather than every cosmetic field (e.g.
    ``name``/``version`` strings are informational, not checked here).
    """
    saved = checkpoint["metadata"]["model_config"]
    load_bearing_fields = (
        "vocab_size", "hidden_size", "num_layers", "num_heads",
        "num_kv_heads", "max_position_embeddings",
    )
    mismatches = [
        f"{field}: checkpoint={saved.get(field)!r} vs current={getattr(model_config, field)!r}"
        for field in load_bearing_fields
        if saved.get(field) != getattr(model_config, field)
    ]
    if mismatches:
        raise IncompatibleCheckpointError(
            "Checkpoint model_config does not match the current model "
            "config on load-bearing fields: " + "; ".join(mismatches)
        )


def apply_checkpoint(
    checkpoint: dict[str, Any],
    *,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    scheduler: torch.optim.lr_scheduler.LRScheduler,
    restore_rng: bool = True,
) -> tuple[int, int]:
    """Load state dicts from ``checkpoint`` into the given objects.

    Returns ``(step, epoch)`` to resume from. Caller is expected to have
    already called :func:`verify_checkpoint_compatibility`.
    """
    model.load_state_dict(checkpoint["model_state_dict"])
    optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
    scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
    if restore_rng:
        _restore_rng_state(checkpoint["rng_state"])
    metadata = checkpoint["metadata"]
    return int(metadata["step"]), int(metadata["epoch"])


class CheckpointManager:
    """Directory-level checkpoint policy: naming, retention, "latest" pointer."""

    def __init__(self, output_dir: str | Path, keep_last_n: int) -> None:
        self.output_dir = Path(output_dir)
        self.keep_last_n = keep_last_n
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def path_for_step(self, step: int) -> Path:
        return self.output_dir / f"checkpoint-step{step}.pt"

    def save(
        self,
        step: int,
        *,
        model: torch.nn.Module,
        optimizer: torch.optim.Optimizer,
        scheduler: torch.optim.lr_scheduler.LRScheduler,
        epoch: int,
        model_config: VirgoSLMConfig,
        training_config: TrainingConfig,
        tokenizer_identity: TokenizerIdentity,
        extra: dict[str, Any] | None = None,
    ) -> Path:
        path = self.path_for_step(step)
        save_checkpoint(
            path,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            step=step,
            epoch=epoch,
            model_config=model_config,
            training_config=training_config,
            tokenizer_identity=tokenizer_identity,
            extra=extra,
        )
        self._update_latest_pointer(path)
        self._enforce_retention()
        return path

    def _update_latest_pointer(self, path: Path) -> None:
        pointer_path = self.output_dir / LATEST_POINTER_FILE
        tmp_pointer = pointer_path.with_suffix(".tmp")
        tmp_pointer.write_text(path.name, encoding="utf-8")
        tmp_pointer.replace(pointer_path)

    def latest_checkpoint_path(self) -> Path | None:
        pointer_path = self.output_dir / LATEST_POINTER_FILE
        if not pointer_path.exists():
            return None
        name = pointer_path.read_text(encoding="utf-8").strip()
        candidate = self.output_dir / name
        return candidate if candidate.exists() else None

    def _all_checkpoint_paths_by_step(self) -> list[tuple[int, Path]]:
        results: list[tuple[int, Path]] = []
        for p in self.output_dir.glob("checkpoint-step*.pt"):
            try:
                step = int(p.stem.removeprefix("checkpoint-step"))
            except ValueError:  # pragma: no cover - defensive, not expected
                continue
            results.append((step, p))
        return sorted(results, key=lambda item: item[0])

    def _enforce_retention(self) -> None:
        checkpoints = self._all_checkpoint_paths_by_step()
        excess = len(checkpoints) - self.keep_last_n
        if excess <= 0:
            return
        for _step, path in checkpoints[:excess]:
            path.unlink(missing_ok=True)


def load_checkpoint_metadata_only(path: str | Path) -> dict[str, Any]:
    """Return checkpoint metadata for inspection.

    The current PyTorch checkpoint format still deserializes the checkpoint
    payload; this helper centralizes the operation and avoids callers relying
    on the internal payload layout. It is intentionally not described as a
    zero-tensor-memory metadata reader.
    """
    checkpoint = load_checkpoint(path)
    return dict(checkpoint["metadata"])


def _json_safe(metadata: dict[str, Any]) -> str:
    return json.dumps(metadata, indent=2, default=str)
