"""Training orchestration.

:class:`Trainer` wires together everything the other Phase 4 modules
build (model, optimizer, scheduler, dataloaders, checkpoint manager,
metrics logger) into the actual step loop. It is constructed from already
-built pieces (dependency injection) rather than doing all the wiring
itself, so unit tests can construct a ``Trainer`` around a tiny synthetic
dataset/model without touching disk/CLI/config-file machinery;
:func:`build_trainer` is the convenience factory that does the full
Phase-3-output -> tokenizer -> model -> Trainer wiring for real runs and
the CLI.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import torch
from torch.utils.data import DataLoader

from virgo_slm.model import VirgoSLMConfig, VirgoSLMForCausalLM
from virgo_slm.training.checkpoint import (
    CheckpointManager,
    TokenizerIdentity,
    apply_checkpoint,
    load_checkpoint,
    verify_checkpoint_compatibility,
)
from virgo_slm.training.config import TrainingConfig
from virgo_slm.training.data import build_block_dataset, build_dataloader
from virgo_slm.training.device import resolve_device, resolve_dtype

if TYPE_CHECKING:
    from virgo_slm.tokenizer.tokenizer import VirgoTokenizer

from virgo_slm.training.errors import (
    InvalidSequenceLengthError,
    VocabularySizeMismatchError,
)
from virgo_slm.training.logging_utils import (
    ConsoleLogger,
    JsonlLogger,
    MetricsSink,
    MultiLogger,
    TrainingMetrics,
    perplexity_from_loss,
)
from virgo_slm.training.optim import build_optimizer, build_scheduler
from virgo_slm.training.reproducibility import set_seed


@dataclass(slots=True)
class TrainingRunResult:
    final_step: int
    final_epoch: int
    tokens_processed: int
    last_train_loss: float | None
    last_validation_loss: float | None


@dataclass(slots=True)
class ValidationResult:
    loss: float
    perplexity: float
    tokens_evaluated: int
    batches_evaluated: int


def verify_vocab_compatibility(
    tokenizer: Any, model_config: VirgoSLMConfig
) -> None:
    if tokenizer.vocab_size != model_config.vocab_size:
        raise VocabularySizeMismatchError(
            f"Tokenizer vocab_size ({tokenizer.vocab_size}) does not match "
            f"the model configured vocab_size ({model_config.vocab_size}); "
            "training and inference artifacts require an exact vocabulary "
            "match. Regenerate the model config for this tokenizer."
        )


def verify_sequence_length(block_size: int, model_config: VirgoSLMConfig) -> None:
    if block_size > model_config.max_position_embeddings:
        raise InvalidSequenceLengthError(
            f"block_size ({block_size}) exceeds the model's "
            f"max_position_embeddings ({model_config.max_position_embeddings})."
        )
    if block_size < 2:
        raise InvalidSequenceLengthError("block_size must be >= 2.")


class Trainer:
    def __init__(
        self,
        *,
        model: torch.nn.Module,
        model_config: VirgoSLMConfig,
        training_config: TrainingConfig,
        optimizer: torch.optim.Optimizer,
        scheduler: torch.optim.lr_scheduler.LRScheduler,
        train_loader: DataLoader[dict[str, torch.Tensor]],
        val_loader: DataLoader[dict[str, torch.Tensor]] | None,
        device: torch.device,
        dtype: torch.dtype,
        checkpoint_manager: CheckpointManager,
        tokenizer_identity: TokenizerIdentity,
        metrics_sink: MetricsSink,
    ) -> None:
        self.model = model.to(device=device, dtype=dtype)
        self.model_config = model_config
        self.training_config = training_config
        self.optimizer = optimizer
        self.scheduler = scheduler
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.device = device
        self.dtype = dtype
        self.checkpoint_manager = checkpoint_manager
        self.tokenizer_identity = tokenizer_identity
        self.metrics_sink = metrics_sink

        self.step = 0
        self.epoch = 0
        self.tokens_processed = 0
        self._start_time = time.time()

    # -- checkpoint / resume -------------------------------------------

    def resume_from_checkpoint(self, path: str | Path) -> None:
        checkpoint = load_checkpoint(path)
        verify_checkpoint_compatibility(checkpoint, model_config=self.model_config)
        step, epoch = apply_checkpoint(
            checkpoint,
            model=self.model,
            optimizer=self.optimizer,
            scheduler=self.scheduler,
        )
        self.step = step
        self.epoch = epoch

    def save_checkpoint(self) -> Path:
        sampler = self._train_sampler()
        sampler_state = None if sampler is None else sampler.state_dict()
        return self.checkpoint_manager.save(
            self.step,
            model=self.model,
            optimizer=self.optimizer,
            scheduler=self.scheduler,
            epoch=self.epoch,
            model_config=self.model_config,
            training_config=self.training_config,
            tokenizer_identity=self.tokenizer_identity,
            extra={
                "tokens_processed": self.tokens_processed,
                "data_progress": {
                    "micro_batches_consumed": self.step
                    * self.training_config.gradient_accumulation_steps,
                    "batch_size": self.training_config.per_device_batch_size,
                    "dataset_size": len(self.train_loader.dataset),
                },
                "sampler_state": sampler_state,
            },
        )

    # -- validation -------------------------------------------------------

    @torch.no_grad()
    def validate(self) -> ValidationResult:
        if self.val_loader is None:
            raise RuntimeError("Trainer has no val_loader configured.")
        self.model.eval()
        total_loss = 0.0
        total_tokens = 0
        batches = 0
        max_batches = self.training_config.logging.max_validation_batches
        for batch in self.val_loader:
            if max_batches is not None and batches >= max_batches:
                break
            input_ids = batch["input_ids"].to(self.device)
            attention_mask = batch["attention_mask"].to(self.device)
            labels = batch["labels"].to(self.device)
            output = self.model(
                input_ids=input_ids, attention_mask=attention_mask, labels=labels
            )
            assert output.loss is not None
            n_supervised = int((labels[:, 1:] != -100).sum().item())
            total_loss += float(output.loss.item()) * max(n_supervised, 1)
            total_tokens += n_supervised
            batches += 1
        self.model.train()
        mean_loss = total_loss / total_tokens if total_tokens > 0 else float("nan")
        return ValidationResult(
            loss=mean_loss,
            perplexity=perplexity_from_loss(mean_loss),
            tokens_evaluated=total_tokens,
            batches_evaluated=batches,
        )

    # -- training loop -----------------------------------------------------

    def _prepare_train_sampler(self) -> None:
        sampler = self._train_sampler()
        if sampler is None:
            return
        consumed_micro_batches = (
            self.step * self.training_config.gradient_accumulation_steps
        )
        sampler.seek_batches(
            batch_size=self.training_config.per_device_batch_size,
            batches_consumed=consumed_micro_batches,
        )
        batches_per_epoch = max(
            1,
            (
                len(self.train_loader.dataset)
                + self.training_config.per_device_batch_size
                - 1
            )
            // self.training_config.per_device_batch_size,
        )
        self.epoch = consumed_micro_batches // batches_per_epoch

    def _train_sampler(self):
        sampler = self.train_loader.sampler
        return sampler if hasattr(sampler, "seek_batches") else None

    def train(self, max_steps: int) -> TrainingRunResult:
        """Run up to ``max_steps`` optimizer steps (Task 11).

        One "step" is one optimizer update, i.e. after
        ``gradient_accumulation_steps`` micro-batches have been
        accumulated -- matches ``training_config.scheduler.total_steps``'s
        units, so the scheduler and the loop agree on what "step" means.
        """
        self.model.train()
        accumulation = self.training_config.gradient_accumulation_steps
        last_train_loss: float | None = None
        last_val_loss: float | None = None

        self._prepare_train_sampler()
        data_iter = iter(self.train_loader)
        while self.step < max_steps:
            self.optimizer.zero_grad(set_to_none=True)
            accumulated_loss = 0.0
            for _ in range(accumulation):
                try:
                    batch = next(data_iter)
                except StopIteration:
                    # The number of available micro-batches in an epoch need
                    # not be divisible by gradient accumulation. Start the
                    # next deterministic sampler epoch instead of dropping or
                    # crashing on the final partial accumulation group.
                    data_iter = iter(self.train_loader)
                    batch = next(data_iter)
                input_ids = batch["input_ids"].to(self.device)
                attention_mask = batch["attention_mask"].to(self.device)
                labels = batch["labels"].to(self.device)

                output = self.model(
                    input_ids=input_ids, attention_mask=attention_mask, labels=labels
                )
                assert output.loss is not None
                loss = output.loss / accumulation
                loss.backward()
                accumulated_loss += float(output.loss.item())
                self.tokens_processed += int(attention_mask.sum().item())

            torch.nn.utils.clip_grad_norm_(
                self.model.parameters(), self.training_config.max_grad_norm
            )
            self.optimizer.step()
            self.scheduler.step()

            self.step += 1
            consumed_micro_batches = self.step * accumulation
            batches_per_epoch = max(
                1,
                (
                    len(self.train_loader.dataset)
                    + self.training_config.per_device_batch_size
                    - 1
                )
                // self.training_config.per_device_batch_size,
            )
            self.epoch = consumed_micro_batches // batches_per_epoch
            last_train_loss = accumulated_loss / accumulation

            if self.step % self.training_config.logging.log_every_n_steps == 0:
                self.metrics_sink.log(
                    TrainingMetrics(
                        step=self.step,
                        epoch=self.epoch,
                        train_loss=last_train_loss,
                        validation_loss=None,
                        validation_perplexity=None,
                        learning_rate=self.scheduler.get_last_lr()[0],
                        tokens_processed=self.tokens_processed,
                        elapsed_seconds=time.time() - self._start_time,
                        event="train_step",
                    )
                )

            if (
                self.val_loader is not None
                and self.step % self.training_config.logging.validate_every_n_steps == 0
            ):
                val_result = self.validate()
                last_val_loss = val_result.loss
                self.metrics_sink.log(
                    TrainingMetrics(
                        step=self.step,
                        epoch=self.epoch,
                        train_loss=None,
                        validation_loss=val_result.loss,
                        validation_perplexity=val_result.perplexity,
                        learning_rate=self.scheduler.get_last_lr()[0],
                        tokens_processed=self.tokens_processed,
                        elapsed_seconds=time.time() - self._start_time,
                        event="validation",
                    )
                )

            if self.step % self.training_config.checkpoint.save_every_n_steps == 0:
                self.save_checkpoint()
                self.metrics_sink.log(
                    TrainingMetrics(
                        step=self.step,
                        epoch=self.epoch,
                        train_loss=None,
                        validation_loss=None,
                        validation_perplexity=None,
                        learning_rate=self.scheduler.get_last_lr()[0],
                        tokens_processed=self.tokens_processed,
                        elapsed_seconds=time.time() - self._start_time,
                        event="checkpoint",
                    )
                )

        return TrainingRunResult(
            final_step=self.step,
            final_epoch=self.epoch,
            tokens_processed=self.tokens_processed,
            last_train_loss=last_train_loss,
            last_validation_loss=last_val_loss,
        )


def build_trainer(
    training_config: TrainingConfig,
    model_config: VirgoSLMConfig,
    tokenizer: Any,
    *,
    model: torch.nn.Module | None = None,
) -> Trainer:
    """Full real-run wiring: config -> device/dtype -> data -> model -> Trainer.

    ``model`` can be supplied directly (tests, or resuming into an
    already-constructed model); otherwise a fresh
    ``VirgoSLMForCausalLM(model_config)`` is built.
    """
    verify_vocab_compatibility(tokenizer, model_config)
    verify_sequence_length(training_config.data.block_size, model_config)

    set_seed(training_config.seed)

    device = resolve_device(training_config.device)
    dtype = resolve_dtype(training_config.precision, device)

    data_dir = Path(training_config.data.dataset_output_dir)
    train_dataset = build_block_dataset(
        data_dir / "train.jsonl", tokenizer, training_config.data.block_size
    )
    train_loader = build_dataloader(
        train_dataset,
        batch_size=training_config.per_device_batch_size,
        shuffle=True,
        seed=training_config.seed,
        num_workers=training_config.data.num_workers,
    )

    val_loader = None
    val_path = data_dir / "validation.jsonl"
    if val_path.exists() and val_path.stat().st_size > 0:
        val_dataset = build_block_dataset(
            val_path, tokenizer, training_config.data.block_size
        )
        val_loader = build_dataloader(
            val_dataset,
            batch_size=training_config.per_device_batch_size,
            shuffle=False,
            seed=training_config.seed,
            num_workers=training_config.data.num_workers,
        )

    resolved_model = model if model is not None else VirgoSLMForCausalLM(model_config)
    optimizer = build_optimizer(resolved_model, training_config.optimizer)
    scheduler = build_scheduler(optimizer, training_config.scheduler)
    checkpoint_manager = CheckpointManager(
        training_config.checkpoint.output_dir, training_config.checkpoint.keep_last_n
    )
    tokenizer_identity = TokenizerIdentity(
        name=tokenizer.config.name,
        version=tokenizer.config.version,
        vocab_size=tokenizer.vocab_size,
    )
    metrics_sink: MetricsSink = MultiLogger(
        [ConsoleLogger(), JsonlLogger(training_config.logging.log_dir)]
    )

    trainer = Trainer(
        model=resolved_model,
        model_config=model_config,
        training_config=training_config,
        optimizer=optimizer,
        scheduler=scheduler,
        train_loader=train_loader,
        val_loader=val_loader,
        device=device,
        dtype=dtype,
        checkpoint_manager=checkpoint_manager,
        tokenizer_identity=tokenizer_identity,
        metrics_sink=metrics_sink,
    )

    if training_config.checkpoint.resume_from is not None:
        trainer.resume_from_checkpoint(training_config.checkpoint.resume_from)

    return trainer
