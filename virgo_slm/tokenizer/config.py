"""Configuration for the Virgo tokenizer.

Mirrors the versioning discipline of ``virgo_slm.model.config
.VirgoSLMConfig``: a frozen, validated dataclass, saved alongside the
trained tokenizer artifact so any checkpoint can pin the exact tokenizer
version it was trained/evaluated against (Phase 2's "tokenizer versioning"
requirement).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from virgo_slm.tokenizer.special_tokens import SPECIAL_TOKENS


@dataclass(frozen=True, slots=True)
class TokenizerConfig:
    vocab_size: int
    model_type: str = "bpe"  # byte-level BPE
    special_tokens: tuple[str, ...] = field(default_factory=lambda: SPECIAL_TOKENS)
    min_frequency: int = 2
    byte_fallback: bool = True  # implicit for byte-level BPE; documents intent
    name: str = "virgo-tokenizer"
    version: str = "0.1.0"
    # Free-text note on what corpus this was trained on — filled in by
    # train.py at save time, not by hand, so it can't drift from reality.
    trained_on: str = "untrained"

    def __post_init__(self) -> None:
        if self.vocab_size <= len(self.special_tokens):
            raise ValueError(
                f"vocab_size ({self.vocab_size}) must exceed the number of "
                f"special tokens ({len(self.special_tokens)})"
            )
        if self.min_frequency < 1:
            raise ValueError("min_frequency must be >= 1")
        if len(set(self.special_tokens)) != len(self.special_tokens):
            raise ValueError("special_tokens must not contain duplicates")
