"""CLI for the Phase 4 training system.

Commands
--------

``validate-config``
    Load and validate a training config JSON file; prints OK or the exact
    validation error. Also checks tokenizer/model vocab compatibility if
    ``--tokenizer-dir`` is given.

``smoke-train``
    Run a short CPU training run from a config file -- intended for the
    Task 18 smoke test / a quick "does this config actually work" check,
    not production training.

``train``
    Run training for ``--max-steps`` steps (or the config's
    ``scheduler.total_steps`` if omitted).

``evaluate``
    Run the validation loop only, from a checkpoint (or a freshly
    initialized model if none given), and print the result.

``resume``
    Resume from a checkpoint and continue training for
    ``--additional-steps`` more steps.

``inspect-checkpoint``
    Print a checkpoint's metadata without loading its full tensors.

Config file shape mirrors ``TrainingConfig``'s field names, e.g.::

    {
      "model_preset": "virgo-slm-103m",
      "data": {"dataset_output_dir": "...", "tokenizer_dir": "...", "block_size": 128},
      "optimizer": {"learning_rate": 0.0003},
      "scheduler": {"warmup_steps": 10, "total_steps": 100},
      "checkpoint": {"output_dir": "checkpoints", "save_every_n_steps": 50},
      "device": {"device": "cpu"},
      "seed": 42
    }

Any sub-config omitted uses its dataclass defaults.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from virgo_slm.configs.presets import PRESETS
from virgo_slm.tokenizer.tokenizer import VirgoTokenizer
from virgo_slm.training.checkpoint import load_checkpoint_metadata_only
from virgo_slm.training.config import (
    CheckpointConfig,
    DataConfig,
    DeviceConfig,
    LoggingConfig,
    OptimizerConfig,
    PrecisionConfig,
    SchedulerConfig,
    TrainingConfig,
)
from virgo_slm.training.errors import InvalidTrainingConfigError, TrainingError
from virgo_slm.training.trainer import build_trainer, verify_vocab_compatibility

_SUBCONFIG_TYPES = {
    "data": DataConfig,
    "optimizer": OptimizerConfig,
    "scheduler": SchedulerConfig,
    "checkpoint": CheckpointConfig,
    "precision": PrecisionConfig,
    "device": DeviceConfig,
    "logging": LoggingConfig,
}


def load_training_config(path: str | Path) -> TrainingConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    kwargs: dict[str, object] = {}
    for key, value in raw.items():
        if key in _SUBCONFIG_TYPES and isinstance(value, dict):
            kwargs[key] = _SUBCONFIG_TYPES[key](**value)
        else:
            kwargs[key] = value
    if "data" not in kwargs:
        raise InvalidTrainingConfigError("Training config must include a 'data' section")
    return TrainingConfig(**kwargs)  # type: ignore[arg-type]


def _resolve_model_config(training_config: TrainingConfig) -> "VirgoSLMConfigT":
    from virgo_slm.model.config import VirgoSLMConfig  # local import: typing only

    if training_config.model_preset not in PRESETS:
        raise InvalidTrainingConfigError(
            f"Unknown model_preset {training_config.model_preset!r}; "
            f"available presets: {sorted(PRESETS)}"
        )
    config = PRESETS[training_config.model_preset]
    assert isinstance(config, VirgoSLMConfig)
    return config


# Only used for the local-import type hint above; avoids a hard module-level
# dependency ordering requirement between config.py and cli.py.
VirgoSLMConfigT = object


def _cmd_validate_config(args: argparse.Namespace) -> int:
    try:
        training_config = load_training_config(args.config)
        model_config = _resolve_model_config(training_config)
        print(f"OK: {args.config} is a valid TrainingConfig")
        print(f"  model_preset: {training_config.model_preset}")
        print(f"  effective_batch_size: {training_config.effective_batch_size}")
        if args.tokenizer_dir:
            tokenizer = VirgoTokenizer.load(args.tokenizer_dir)
            verify_vocab_compatibility(tokenizer, model_config)
            print(f"  tokenizer vocab_size {tokenizer.vocab_size} compatible with model")
        return 0
    except TrainingError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1


def _cmd_train(args: argparse.Namespace, *, smoke: bool = False) -> int:
    training_config = load_training_config(args.config)
    model_config = _resolve_model_config(training_config)
    tokenizer = VirgoTokenizer.load(training_config.data.tokenizer_dir)
    trainer = build_trainer(training_config, model_config, tokenizer)
    max_steps = args.max_steps or training_config.scheduler.total_steps
    result = trainer.train(max_steps)
    label = "Smoke training" if smoke else "Training"
    print(f"{label} complete: step={result.final_step} epoch={result.final_epoch} "
          f"tokens_processed={result.tokens_processed} "
          f"last_train_loss={result.last_train_loss}")
    return 0


def _cmd_resume(args: argparse.Namespace) -> int:
    training_config = load_training_config(args.config)
    model_config = _resolve_model_config(training_config)
    tokenizer = VirgoTokenizer.load(training_config.data.tokenizer_dir)
    trainer = build_trainer(training_config, model_config, tokenizer)
    trainer.resume_from_checkpoint(args.checkpoint)
    target_step = trainer.step + args.additional_steps
    result = trainer.train(target_step)
    print(f"Resumed and trained to step={result.final_step} "
          f"last_train_loss={result.last_train_loss}")
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    training_config = load_training_config(args.config)
    model_config = _resolve_model_config(training_config)
    tokenizer = VirgoTokenizer.load(training_config.data.tokenizer_dir)
    trainer = build_trainer(training_config, model_config, tokenizer)
    if args.checkpoint:
        trainer.resume_from_checkpoint(args.checkpoint)
    result = trainer.validate()
    print(f"validation_loss={result.loss:.4f} "
          f"validation_perplexity={result.perplexity:.2f} "
          f"tokens_evaluated={result.tokens_evaluated}")
    return 0


def _cmd_inspect_checkpoint(args: argparse.Namespace) -> int:
    metadata = load_checkpoint_metadata_only(args.checkpoint)
    print(json.dumps(metadata, indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="virgo_slm.training", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-config", help="Validate a training config file")
    validate.add_argument("--config", required=True)
    validate.add_argument("--tokenizer-dir", default=None)
    validate.set_defaults(func=_cmd_validate_config)

    smoke = subparsers.add_parser("smoke-train", help="Run a short CPU smoke training run")
    smoke.add_argument("--config", required=True)
    smoke.add_argument("--max-steps", type=int, default=None)
    smoke.set_defaults(func=lambda a: _cmd_train(a, smoke=True))

    train = subparsers.add_parser("train", help="Run training")
    train.add_argument("--config", required=True)
    train.add_argument("--max-steps", type=int, default=None)
    train.set_defaults(func=lambda a: _cmd_train(a, smoke=False))

    resume = subparsers.add_parser("resume", help="Resume from a checkpoint")
    resume.add_argument("--config", required=True)
    resume.add_argument("--checkpoint", required=True)
    resume.add_argument("--additional-steps", type=int, required=True)
    resume.set_defaults(func=_cmd_resume)

    evaluate = subparsers.add_parser("evaluate", help="Run validation only")
    evaluate.add_argument("--config", required=True)
    evaluate.add_argument("--checkpoint", default=None)
    evaluate.set_defaults(func=_cmd_evaluate)

    inspect = subparsers.add_parser("inspect-checkpoint", help="Print checkpoint metadata")
    inspect.add_argument("--checkpoint", required=True)
    inspect.set_defaults(func=_cmd_inspect_checkpoint)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except TrainingError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
