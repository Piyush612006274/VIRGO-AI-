"""Instruction-tuning data formats and preparation utilities.

This package creates deterministic supervised examples; it deliberately does
not perform model training. Training remains an explicit operator action.
"""

from virgo_slm.instruction.dataset import (
    InstructionExample,
    InstructionDatasetBuilder,
    load_jsonl,
    save_jsonl,
)

__all__ = ("InstructionExample", "InstructionDatasetBuilder", "load_jsonl", "save_jsonl")
