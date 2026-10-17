"""Phase 3 -> tokenizer -> packed training blocks.

Reads a Phase 3 pipeline's ``{split}.jsonl`` output (see
``virgo_slm.dataset.pipeline._write_split_jsonl_files`` for why JSONL,
not the flat ``.txt`` files, is used here: unambiguous document
boundaries), tokenizes each record with the Virgo tokenizer (which wraps
every record in BOS/EOS via ``encode``'s default
``add_special_tokens=True`` -- unchanged from Phase 2), concatenates the
resulting token stream, and packs it into fixed-length blocks for causal
LM training.

IMPORTANT -- matches the model's existing (already tested in Phase 1)
loss convention exactly: ``VirgoSLMForCausalLM.forward`` takes
``input_ids`` and ``labels`` at the *same* alignment and does the
input/target shift internally
(``logits[:, :-1]`` vs ``labels[:, 1:]``, see ``model/architecture.py``).
This module therefore does NOT pre-shift anything -- ``labels`` for a
block is that block's ``input_ids`` (with padding positions set to
``-100``), not a shifted copy. Re-shifting here in addition to the
model's internal shift would silently corrupt the training objective by
double-shifting; this is called out explicitly because it's the single
easiest mistake to make wiring a data pipeline to this model.

Streams from disk one JSON line at a time rather than loading the whole
split into memory (Task 4.8/Task 27): only the resulting integer token
blocks are kept in memory, not the raw text.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import torch
from torch import Tensor
from torch.utils.data import Dataset, Sampler

if TYPE_CHECKING:
    from virgo_slm.tokenizer.tokenizer import VirgoTokenizer

from virgo_slm.training.errors import CorruptedDatasetRecordError, MissingDatasetError

IGNORE_INDEX = -100


def _iter_jsonl_texts(jsonl_path: Path) -> Iterator[str]:
    if not jsonl_path.exists():
        raise MissingDatasetError(f"Dataset split file does not exist: {jsonl_path}")
    with jsonl_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CorruptedDatasetRecordError(
                    f"{jsonl_path}:{line_number}: invalid JSON: {exc}"
                ) from exc
            text = obj.get("text")
            if not isinstance(text, str) or not text:
                raise CorruptedDatasetRecordError(
                    f"{jsonl_path}:{line_number}: missing or empty 'text' field"
                )
            yield text


def encode_split_to_token_stream(
    jsonl_path: str | Path, tokenizer: Any
) -> list[int]:
    """Tokenize every record in a split's JSONL file into one flat token stream.

    Each record is encoded independently (so each gets its own BOS/EOS
    pair via the tokenizer's default special-token wrapping), then
    concatenated in file order -- the same deterministic order Phase 3
    wrote them in.
    """
    token_stream: list[int] = []
    for text in _iter_jsonl_texts(Path(jsonl_path)):
        token_stream.extend(tokenizer.encode(text, add_special_tokens=True))
    return token_stream


def pack_token_stream(
    token_stream: list[int], block_size: int, pad_token_id: int
) -> list[list[int]]:
    """Chunk a flat token stream into fixed-length ``block_size`` blocks.

    The final partial block (if any) is right-padded with
    ``pad_token_id``; :class:`LMBlockDataset` masks padded positions with
    ``IGNORE_INDEX`` in ``labels`` and 0 in ``attention_mask`` so they
    contribute nothing to loss or attention. Each block is trained as an
    independent sequence (no cross-block continuation), which is standard
    LM packing practice and costs at most one unsupervised position
    (predicting the first token of the *next* block) per block boundary.
    """
    if block_size < 2:
        raise ValueError("block_size must be >= 2")
    blocks: list[list[int]] = []
    for start in range(0, len(token_stream), block_size):
        block = token_stream[start : start + block_size]
        if len(block) < block_size:
            block = block + [pad_token_id] * (block_size - len(block))
        blocks.append(block)
    return blocks


class LMBlockDataset(Dataset[dict[str, Tensor]]):
    """A ``torch.utils.data.Dataset`` of fixed-length causal-LM blocks.

    Each item is ``{"input_ids": LongTensor[block_size],
    "labels": LongTensor[block_size], "attention_mask": LongTensor[block_size]}``.
    ``labels`` equals ``input_ids`` except at padded positions, which are
    ``IGNORE_INDEX`` (matching ``F.cross_entropy(..., ignore_index=-100)``
    already used inside ``VirgoSLMForCausalLM.forward``).
    """

    def __init__(self, blocks: list[list[int]], pad_token_id: int) -> None:
        self._blocks = blocks
        self._pad_token_id = pad_token_id

    def __len__(self) -> int:
        return len(self._blocks)

    def __getitem__(self, index: int) -> dict[str, Tensor]:
        block = self._blocks[index]
        input_ids = torch.tensor(block, dtype=torch.long)
        attention_mask = (input_ids != self._pad_token_id).long()
        # A real pad token could legitimately appear as *content* in
        # principle, but this tokenizer's pad id is never produced by
        # encode() on real text (it's reserved, only ever inserted by our
        # own padding above), so this equality check is unambiguous here.
        labels = input_ids.clone()
        labels[attention_mask == 0] = IGNORE_INDEX
        return {
            "input_ids": input_ids,
            "labels": labels,
            "attention_mask": attention_mask,
        }


def collate_lm_batch(batch: list[dict[str, Tensor]]) -> dict[str, Tensor]:
    """Stack a list of equal-length blocks into batch tensors.

    Explicit rather than relying on ``torch.utils.data.default_collate``
    so the shapes/dtypes/keys this function guarantees are documented and
    independently testable (Task 5), and so a future variable-length
    block size would have one obvious place to add real padding logic.
    """
    return {
        key: torch.stack([item[key] for item in batch], dim=0)
        for key in ("input_ids", "labels", "attention_mask")
    }



class StatefulShuffleSampler(Sampler[int]):
    """Deterministic epoch shuffle with a resumable logical sample cursor.

    The permutation for each epoch is derived only from ``seed`` and the
    epoch number, so a fresh process can reconstruct the same future batches.
    ``seek_batches`` positions the sampler from an optimizer-step-derived
    batch count; this avoids relying on DataLoader worker prefetch state when
    a run is resumed. Exact replay is therefore independent of prefetching.
    """

    def __init__(self, data_source: Dataset[dict[str, Tensor]], seed: int) -> None:
        self._length = len(data_source)
        self._seed = int(seed)
        self._epoch = 0
        self._position = 0

    def __len__(self) -> int:
        return self._length

    def __iter__(self) -> Iterator[int]:
        if self._length == 0:
            return
        generator = torch.Generator()
        generator.manual_seed(self._epoch_seed())
        permutation = torch.randperm(self._length, generator=generator).tolist()
        while self._position < self._length:
            index = int(permutation[self._position])
            self._position += 1
            yield index
        self._epoch += 1
        self._position = 0

    def seek_batches(self, *, batch_size: int, batches_consumed: int) -> None:
        """Seek to the exact logical point represented by consumed batches."""
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if batches_consumed < 0:
            raise ValueError("batches_consumed must be non-negative")
        batches_per_epoch = max(1, (self._length + batch_size - 1) // batch_size)
        epoch, batch_offset = divmod(batches_consumed, batches_per_epoch)
        self._epoch = epoch
        self._position = min(batch_offset * batch_size, self._length)

    def state_dict(self) -> dict[str, int]:
        return {
            "seed": self._seed,
            "length": self._length,
            "epoch": self._epoch,
            "position": self._position,
        }

    def load_state_dict(self, state: dict[str, int]) -> None:
        if state.get("seed") != self._seed:
            raise ValueError("sampler seed does not match")
        if state.get("length") != self._length:
            raise ValueError("sampler dataset length does not match")
        epoch = state.get("epoch")
        position = state.get("position")
        if not isinstance(epoch, int) or epoch < 0:
            raise ValueError("sampler epoch is invalid")
        if not isinstance(position, int) or not 0 <= position <= self._length:
            raise ValueError("sampler position is invalid")
        self._epoch = epoch
        self._position = position

    def _epoch_seed(self) -> int:
        modulus = (1 << 63) - 1
        return (self._seed + self._epoch) % modulus

def build_dataloader(
    dataset: LMBlockDataset,
    *,
    batch_size: int,
    shuffle: bool,
    seed: int,
    num_workers: int = 0,
) -> torch.utils.data.DataLoader[dict[str, Tensor]]:
    """Build a deterministic data loader with an optional resumable sampler."""
    if shuffle:
        sampler = StatefulShuffleSampler(dataset, seed)
        return torch.utils.data.DataLoader(
            dataset,
            batch_size=batch_size,
            sampler=sampler,
            num_workers=num_workers,
            collate_fn=collate_lm_batch,
            drop_last=False,
        )
    return torch.utils.data.DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        collate_fn=collate_lm_batch,
        drop_last=False,
    )


def build_block_dataset(
    jsonl_path: str | Path,
    tokenizer: Any,
    block_size: int,
) -> LMBlockDataset:
    """The full Phase 3 -> tokenizer -> packed-blocks bridge, in one call."""
    token_stream = encode_split_to_token_stream(jsonl_path, tokenizer)
    pad_token_id = tokenizer.token_to_id(tokenizer.config.special_tokens[0])
    if pad_token_id is None:  # pragma: no cover - special_tokens[0] is always pad
        raise CorruptedDatasetRecordError("tokenizer has no pad token configured")
    blocks = pack_token_stream(token_stream, block_size, pad_token_id)
    if not blocks:
        raise MissingDatasetError(
            f"{jsonl_path} produced zero tokens; the split is empty or all "
            "records failed to tokenize."
        )
    return LMBlockDataset(blocks, pad_token_id)
