"""Public tokenizer API with lazy import of the optional ``tokenizers`` package."""

from __future__ import annotations

from virgo_slm.tokenizer.config import TokenizerConfig
from virgo_slm.tokenizer.special_tokens import (
    ASSISTANT_TOKEN,
    ASSISTANT_TOKEN_ID,
    BOS_TOKEN,
    BOS_TOKEN_ID,
    EOS_TOKEN,
    EOS_TOKEN_ID,
    IM_END_TOKEN,
    IM_END_TOKEN_ID,
    IM_START_TOKEN,
    IM_START_TOKEN_ID,
    PAD_TOKEN,
    PAD_TOKEN_ID,
    SPECIAL_TOKENS,
    SYSTEM_TOKEN,
    SYSTEM_TOKEN_ID,
    TOOL_CALL_TOKEN,
    TOOL_CALL_TOKEN_ID,
    TOOL_ERROR_TOKEN,
    TOOL_ERROR_TOKEN_ID,
    TOOL_RESULT_TOKEN,
    TOOL_RESULT_TOKEN_ID,
    UNK_TOKEN,
    UNK_TOKEN_ID,
    USER_TOKEN,
    USER_TOKEN_ID,
)

__all__ = (
    "ASSISTANT_TOKEN", "ASSISTANT_TOKEN_ID", "BOS_TOKEN", "BOS_TOKEN_ID",
    "EOS_TOKEN", "EOS_TOKEN_ID", "IM_END_TOKEN", "IM_END_TOKEN_ID",
    "IM_START_TOKEN", "IM_START_TOKEN_ID", "PAD_TOKEN", "PAD_TOKEN_ID",
    "SPECIAL_TOKENS", "SYSTEM_TOKEN", "SYSTEM_TOKEN_ID", "TOOL_CALL_TOKEN",
    "TOOL_CALL_TOKEN_ID", "TOOL_ERROR_TOKEN", "TOOL_ERROR_TOKEN_ID",
    "TOOL_RESULT_TOKEN", "TOOL_RESULT_TOKEN_ID", "TokenizerConfig",
    "UNK_TOKEN", "UNK_TOKEN_ID", "USER_TOKEN", "USER_TOKEN_ID", "VirgoTokenizer",
)


def __getattr__(name: str) -> object:
    if name == "VirgoTokenizer":
        from virgo_slm.tokenizer.tokenizer import VirgoTokenizer
        return VirgoTokenizer
    raise AttributeError(name)
