"""Deterministic instruction-tuning dataset preparation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class InstructionExample:
    """One supervised instruction/response example."""

    instruction: str
    response: str
    system: str | None = None
    input: str | None = None
    source: str = "manual"
    example_id: str = ""

    def __post_init__(self) -> None:
        if not self.instruction.strip():
            raise ValueError("instruction must not be empty")
        if not self.response.strip():
            raise ValueError("response must not be empty")
        if not self.example_id:
            payload = "\n".join(
                (self.system or "", self.instruction, self.input or "", self.response)
            )
            object.__setattr__(
                self,
                "example_id",
                hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16],
            )


class InstructionDatasetBuilder:
    """Build and deterministically deduplicate instruction examples."""

    def __init__(self) -> None:
        self._examples: dict[str, InstructionExample] = {}

    def add(self, example: InstructionExample) -> None:
        self._examples[example.example_id] = example

    def extend(self, examples: Iterable[InstructionExample]) -> None:
        for example in examples:
            self.add(example)

    def build(self) -> tuple[InstructionExample, ...]:
        return tuple(self._examples[key] for key in sorted(self._examples))


def save_jsonl(path: str | Path, examples: Iterable[InstructionExample]) -> None:
    """Serialize instruction examples as deterministic UTF-8 JSONL."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(
                json.dumps(asdict(example), ensure_ascii=False, sort_keys=True) + "\n"
            )


def load_jsonl(path: str | Path) -> tuple[InstructionExample, ...]:
    """Load and validate instruction examples from JSONL."""
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(target)
    examples: list[InstructionExample] = []
    with target.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                examples.append(InstructionExample(**payload))
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid instruction record at line {line_number}"
                ) from error
    return tuple(examples)
