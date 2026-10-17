"""Deterministic evaluation helpers that operate through the inference seam."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EvalCase:
    case_id: str
    prompt: str
    expected_contains: tuple[str, ...] = ()
    expected_not_contains: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvalReport:
    total: int
    passed: int
    failed: int
    results: tuple[dict[str, object], ...]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": self.pass_rate,
            "results": self.results,
        }

    def save_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


class Evaluator:
    """Run simple, reproducible assertion cases against a generator."""

    def __init__(self, generate: Callable[[str], str]) -> None:
        self._generate = generate

    def evaluate(self, cases: Iterable[EvalCase]) -> EvalReport:
        results: list[dict[str, object]] = []
        for case in cases:
            output = self._generate(case.prompt)
            lower = output.casefold()
            required_ok = all(
                item.casefold() in lower for item in case.expected_contains
            )
            forbidden_ok = all(
                item.casefold() not in lower for item in case.expected_not_contains
            )
            passed = required_ok and forbidden_ok
            results.append(
                {"case_id": case.case_id, "passed": passed, "output": output}
            )
        passed_count = sum(bool(item["passed"]) for item in results)
        return EvalReport(
            len(results),
            passed_count,
            len(results) - passed_count,
            tuple(results),
        )
