"""Configurable quality filters.

Each filter is independently callable and independently testable, returns
``None`` when a record passes, or a short machine-readable rejection
reason string when it doesn't. :func:`apply_filters` runs every filter and
collects *all* triggered reasons (not just the first) so the manifest can
report why records were actually rejected instead of a single generic
"filtered" bucket.

Filters are deliberately conservative: the thresholds default to values
that should not reject legitimate short code snippets, JSON fragments,
URLs, paths, or short multilingual conversational lines. Domains that are
inherently repetitive/structured (``"code"``, ``"json"``) skip the
repetition filter, which is tuned for prose and would otherwise punish
normal code patterns (e.g. repeated ``import`` lines, repeated braces).
"""

from __future__ import annotations

from collections import Counter

from virgo_slm.dataset.config import DatasetPipelineConfig
from virgo_slm.dataset.record import DatasetRecord

_REPETITION_EXEMPT_DOMAINS = frozenset({"code", "json"})


def filter_empty(text: str, config: DatasetPipelineConfig) -> str | None:
    if not text.strip():
        return "empty_text"
    if len(text) < config.min_chars:
        return "below_min_chars"
    return None


def filter_max_length(text: str, config: DatasetPipelineConfig) -> str | None:
    if config.max_chars is not None and len(text) > config.max_chars:
        return "above_max_chars"
    return None


def filter_whitespace_ratio(text: str, config: DatasetPipelineConfig) -> str | None:
    if not text:
        return None
    whitespace_count = sum(1 for c in text if c.isspace())
    ratio = whitespace_count / len(text)
    if ratio > config.whitespace_ratio_threshold:
        return "excessive_whitespace"
    return None


def filter_character_diversity(
    text: str, config: DatasetPipelineConfig
) -> str | None:
    """Reject near-constant text (e.g. ``"aaaaaaaaaa..."``).

    Measures the share of the single most frequent character in the text,
    NOT distinct-character-count / length. The latter looks appealing but
    is a broken metric here: alphabet size is bounded (tens of characters)
    regardless of text length, so distinct/length trends towards zero for
    *any* sufficiently long text -- it flagged normal English prose and
    Python code as "low diversity" in manual verification (real English
    prose measured ~0.03 distinct/length over 1,480 chars, comfortably
    under a 0.05 threshold, despite being completely normal text). Most-
    common-character ratio does not have this problem: normal prose tops
    out around 0.12-0.15 (usually the space character), while truly
    degenerate repeated-character text sits at 1.0.

    Only applied to texts long enough (>= 40 chars) that the measure is
    meaningful -- short strings can legitimately be dominated by one
    character (e.g. ``"{{{{}}}}"``, ``"...."``) without being garbage.
    ``config.low_diversity_threshold`` is reused as this ratio's
    threshold, inverted in meaning (now "reject if ABOVE"), to avoid
    adding a second config knob for what is conceptually the same "is
    this text degenerate" setting; see config docstring.
    """
    if len(text) < 40:
        return None
    most_common_count = Counter(text).most_common(1)[0][1]
    ratio = most_common_count / len(text)
    if ratio > (1.0 - config.low_diversity_threshold):
        return "low_character_diversity"
    return None


def filter_line_repetition(
    text: str, config: DatasetPipelineConfig, *, domain: str
) -> str | None:
    """Reject text dominated by one repeated line.

    Skipped for ``code``/``json`` domains, where repeated short lines
    (imports, braces, boilerplate keys) are normal and not a quality
    signal.
    """
    if domain in _REPETITION_EXEMPT_DOMAINS:
        return None
    lines = [line for line in text.split("\n") if line.strip()]
    if len(lines) < 4:
        return None
    counts = Counter(lines)
    most_common_count = counts.most_common(1)[0][1]
    ratio = most_common_count / len(lines)
    if ratio > config.max_line_repetition_ratio:
        return "excessive_line_repetition"
    return None


def filter_invalid_encoding(text: str, config: DatasetPipelineConfig) -> str | None:
    if not text:
        return None
    replacement_count = text.count("\ufffd")
    if replacement_count / max(len(text), 1) > 0.01:
        return "invalid_encoding_markers"
    return None


ALL_FILTERS = (
    filter_empty,
    filter_max_length,
    filter_whitespace_ratio,
    filter_character_diversity,
    filter_invalid_encoding,
)


def apply_filters(
    record: DatasetRecord, config: DatasetPipelineConfig
) -> tuple[str, ...]:
    """Run every filter against ``record.text``; return all triggered reasons."""
    reasons: list[str] = []
    for filter_fn in ALL_FILTERS:
        reason = filter_fn(record.text, config)
        if reason is not None:
            reasons.append(reason)

    line_rep_reason = filter_line_repetition(record.text, config, domain=record.domain)
    if line_rep_reason is not None:
        reasons.append(line_rep_reason)

    return tuple(reasons)
