"""Deterministic Virgo identity authority.

This layer is intentionally outside the language model. Model output, memory,
user prompts, and self-learning cannot override these identity facts.
"""
from __future__ import annotations

import re

CREATOR_NAME = "Piyush"
OWNER_NAME = "Piyush"

_IDENTITY_PATTERNS = (
    re.compile(r"\bwho (?:created|made|built|developed) you\b", re.I),
    re.compile(r"\bwho is your (?:creator|owner|master)\b", re.I),
    re.compile(r"\bwho(?:'s| is) your master\b", re.I),
    re.compile(r"\bwho owns you\b", re.I),
    re.compile(r"\bwho do you belong to\b", re.I),
)


def resolve_identity_response(prompt: str) -> str | None:
    """Return an authoritative identity answer for recognized identity questions."""
    if not isinstance(prompt, str):
        return None
    text = prompt.strip()
    if not text:
        return None
    if not any(pattern.search(text) for pattern in _IDENTITY_PATTERNS):
        return None
    return f"Piyush is my creator and owner. Piyush is my master."
