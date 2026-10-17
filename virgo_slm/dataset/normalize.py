"""Deterministic multilingual/code-safe text normalization.

The guiding rule: normalize only what is unambiguously safe across *every*
target language and domain (EN/HI/Hinglish/RU/ZH/JA/KO/AR + code/JSON/URLs/
paths). Concretely this means:

- Unicode NFC normalization (canonicalizes combining-mark order/precomposed
  vs decomposed forms; does not remove or reorder actual characters, and is
  the standard safe choice for Devanagari, Arabic, and CJK text).
- Line-ending normalization (CRLF/CR -> LF).
- Stripping trailing whitespace per line (never leading whitespace, since
  leading whitespace is semantically significant in Python/YAML/Markdown).
- Collapsing runs of 3+ blank lines to 2 (formatting noise, not content).
- Stripping leading/trailing whitespace from the whole text.

It explicitly does NOT:

- Lowercase (would destroy code identifiers, JSON keys, and is not even
  meaningful for scripts like Devanagari/Arabic/CJK that have no case).
- Collapse internal (non-trailing) whitespace or tabs, which would corrupt
  code indentation and JSON/CSV formatting.
- Strip punctuation, since URLs, file paths and code depend on it.
"""

from __future__ import annotations

import re
import unicodedata

_BLANK_LINE_RUN = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """Apply the conservative, domain-agnostic normalization described above.

    Deterministic: same input always produces the same output, with no
    locale or environment dependence (``unicodedata`` NFC is
    version-pinned by the interpreter's Unicode database, which is the
    same reproducibility guarantee the rest of this repo relies on for
    stdlib behavior).
    """
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in normalized.split("\n")]
    normalized = "\n".join(lines)
    normalized = _BLANK_LINE_RUN.sub("\n\n", normalized)
    return normalized.strip()


def whitespace_collapsed(text: str) -> str:
    """Collapse all whitespace runs to a single space, for dedup hashing only.

    This is intentionally *not* used as the stored/training text -- only as
    a secondary hash key to catch near-duplicates that differ purely in
    formatting (see :mod:`virgo_slm.dataset.dedup`).
    """
    return re.sub(r"\s+", " ", text).strip()
