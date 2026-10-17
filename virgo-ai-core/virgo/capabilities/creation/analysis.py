"""Bounded project-type analysis without secret or security scanning."""

from dataclasses import dataclass
from pathlib import Path

from virgo.capabilities.creation.workspace import (
    EXCLUDED_NAMES,
    SENSITIVE_FILE_NAMES,
    SafeWorkspace,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectAnalysis:
    project_type: str
    languages: tuple[str, ...]
    key_files: tuple[str, ...]
    test_files: tuple[str, ...]
    suggestions: tuple[str, ...]


class ProjectAnalyzer:
    def analyze(self, workspace: SafeWorkspace) -> ProjectAnalysis:
        inspection = workspace.inspect((".",))
        paths = tuple(
            item.relative_path
            for item in inspection.files
            if Path(item.relative_path).name not in SENSITIVE_FILE_NAMES
            and not any(
                part in EXCLUDED_NAMES for part in Path(item.relative_path).parts
            )
        )
        suffixes = {Path(path).suffix.lower() for path in paths}
        languages = tuple(
            language
            for suffix, language in (
                (".py", "Python"),
                (".html", "HTML"),
                (".css", "CSS"),
                (".js", "JavaScript"),
                (".rs", "Rust"),
            )
            if suffix in suffixes
        )
        project_type = (
            "Python"
            if "pyproject.toml" in paths
            else (
                "Rust"
                if "Cargo.toml" in paths
                else "Static website" if "index.html" in paths else "General"
            )
        )
        tests = tuple(
            path
            for path in paths
            if Path(path).name.startswith("test_") or "tests" in Path(path).parts
        )
        key_names = {
            "pyproject.toml",
            "Cargo.toml",
            "index.html",
            "README.md",
            "package.json",
        }
        key_files = tuple(path for path in paths if Path(path).name in key_names)
        suggestions = (
            ("Add focused automated tests for changed behavior",)
            if not tests
            else ("Run the detected focused tests after approved changes",)
        )
        return ProjectAnalysis(
            project_type=project_type,
            languages=languages,
            key_files=key_files,
            test_files=tests,
            suggestions=suggestions,
        )
