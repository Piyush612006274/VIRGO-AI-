"""Deterministic validation for generated local artifacts."""

import ast
import json
from html.parser import HTMLParser
from pathlib import Path

from virgo.contracts.models import ValidationResult, ValidationStatus


class _HTMLStructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        self.tags.add(tag)


def validate_content(target: str, content: str) -> ValidationResult:
    try:
        if not content.strip():
            raise ValueError("content is empty")
        suffix = Path(target).suffix.lower()
        if suffix == ".py":
            ast.parse(content, filename=target)
        elif suffix == ".json":
            json.loads(content)
        elif suffix in {".html", ".htm"}:
            parser = _HTMLStructureParser()
            parser.feed(content)
            if not parser.tags:
                raise ValueError("HTML must contain at least one element")
            if "html" in parser.tags and "body" not in parser.tags:
                raise ValueError("HTML must contain html and body elements")
        return ValidationResult(
            target=target,
            validator=suffix.removeprefix(".") or "text",
            status=ValidationStatus.PASSED,
            message="Content passed deterministic validation",
        )
    except (SyntaxError, ValueError, json.JSONDecodeError) as error:
        return ValidationResult(
            target=target,
            validator=Path(target).suffix.removeprefix(".") or "text",
            status=ValidationStatus.FAILED,
            message=str(error),
        )
