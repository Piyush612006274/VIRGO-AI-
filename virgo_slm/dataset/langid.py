"""Deterministic, dependency-free language identification.

This is a Unicode-script histogram heuristic, not a statistical language
model. It is intentionally simple:

- It counts letters by Unicode script (Devanagari, Arabic, Cyrillic,
  Hiragana/Katakana, Hangul, CJK ideographs, Latin) and picks the dominant
  script.
- Hindi (Devanagari script) is separated from Hinglish (Hindi written in
  Latin script, code-mixed with English) using a small curated marker-word
  list, since script alone cannot tell them apart -- both are Latin.
- Japanese is separated from Chinese by the presence of any
  Hiragana/Katakana (kana), since kanji alone (CJK ideographs) is
  ambiguous between the two.

KNOWN LIMITATIONS (documented, not hidden):

- The Hinglish marker-word list is small and curated by hand, not learned.
  It will under-detect Hinglish that avoids those specific words, and can
  over-fire on English text that happens to contain a marker word used as
  a name or unrelated token. Treat "hinglish" output as a heuristic
  signal, not ground truth.
- Short texts (a few characters) are inherently ambiguous; confidence is
  not modeled, only a best-effort label.
- Mixed-language text is reported as ``"mixed"`` when no script clears the
  dominance threshold rather than guessing one language.
- This will not distinguish closely related Latin-script languages (e.g.
  English vs. French vs. Spanish) -- everything Latin-script and not
  Hinglish is labeled ``"en"``. That is an explicit scope limitation of a
  script-based detector, not a bug; a real language-ID model is future
  work if the target language list grows beyond what script alone can
  separate.
"""

from __future__ import annotations

import unicodedata

SUPPORTED_LANGUAGES = ("en", "hi", "hinglish", "ru", "zh", "ja", "ko", "ar")
UNKNOWN = "unknown"
MIXED = "mixed"

_DOMINANCE_THRESHOLD = 0.6
_MIXED_SECONDARY_THRESHOLD = 0.15

# Small, explicitly non-exhaustive marker-word list for Hinglish detection.
# Common Hindi function words/verbs frequently romanized in code-mixed text.
#
# NOTE: "the" was deliberately excluded despite being a common Hindi word
# transliteration collision-point ("the" as in "tha"/"thi" variants is
# NOT included here) -- it is also the single most common English word,
# and including it caused ordinary English sentences to misclassify as
# Hinglish during test verification. Every word below was checked against
# common English function/stop words to avoid the same collision.
_HINGLISH_MARKERS = frozenset(
    {
        "hai", "hain", "tha", "thi", "nahi", "nahin", "kya", "kyun",
        "kaise", "kar", "karo", "karna", "raha", "rahi", "rahe", "acha",
        "accha", "yaar", "matlab", "bhi", "aur", "lekin", "abhi", "bahut",
        "thoda", "chalo", "haan", "theek", "bilkul", "zyada", "kuch",
        "mujhe", "tumhe", "apna", "hoga", "hogi", "gaya", "gayi",
    }
)


def _script_of(char: str) -> str | None:
    if not char.isalpha():
        return None
    code = ord(char)
    if 0x0900 <= code <= 0x097F:
        return "devanagari"
    if 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F:
        return "arabic"
    if 0x0400 <= code <= 0x04FF:
        return "cyrillic"
    if 0x3040 <= code <= 0x309F or 0x30A0 <= code <= 0x30FF:
        return "kana"
    if 0xAC00 <= code <= 0xD7A3 or 0x1100 <= code <= 0x11FF:
        return "hangul"
    if (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0xF900 <= code <= 0xFAFF
    ):
        return "han"
    try:
        name = unicodedata.name(char)
    except ValueError:
        return None
    if name.startswith("LATIN"):
        return "latin"
    return None


def script_histogram(text: str) -> dict[str, int]:
    """Count letters in ``text`` by Unicode script."""
    counts: dict[str, int] = {}
    for char in text:
        script = _script_of(char)
        if script is None:
            continue
        counts[script] = counts.get(script, 0) + 1
    return counts


def _is_hinglish(text: str) -> bool:
    words = [w.strip(".,!?;:()[]{}\"'").lower() for w in text.split()]
    words = [w for w in words if w]
    if not words:
        return False
    marker_hits = sum(1 for w in words if w in _HINGLISH_MARKERS)
    return marker_hits / len(words) >= 0.08


def detect_language(text: str) -> str:
    """Return one of ``SUPPORTED_LANGUAGES`` plus ``"unknown"``/``"mixed"``.

    See module docstring for the algorithm and its documented limitations.
    """
    counts = script_histogram(text)
    total = sum(counts.values())
    if total == 0:
        return UNKNOWN

    dominant_script, dominant_count = max(counts.items(), key=lambda kv: kv[1])
    dominant_ratio = dominant_count / total

    secondary_scripts = [
        s for s, c in counts.items()
        if s != dominant_script and c / total >= _MIXED_SECONDARY_THRESHOLD
    ]
    if dominant_ratio < _DOMINANCE_THRESHOLD and secondary_scripts:
        return MIXED

    if dominant_script == "devanagari":
        return "hi"
    if dominant_script == "arabic":
        return "ar"
    if dominant_script == "cyrillic":
        return "ru"
    if dominant_script == "hangul":
        return "ko"
    if dominant_script == "kana" or "kana" in counts:
        return "ja"
    if dominant_script == "han":
        return "zh"
    if dominant_script == "latin":
        return "hinglish" if _is_hinglish(text) else "en"
    return UNKNOWN
