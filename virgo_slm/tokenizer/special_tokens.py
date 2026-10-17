"""Canonical Virgo SLM special tokens.

Ids here are pinned by position (index in ``SPECIAL_TOKENS`` == token id)
and MUST stay aligned with :class:`virgo_slm.model.config.VirgoSLMConfig`'s
``pad_token_id=0``, ``bos_token_id=1``, ``eos_token_id=2`` defaults — that
alignment is asserted in ``virgo_slm/tests/test_tokenizer.py`` so the model
and tokenizer can never silently drift apart.

Beyond the three the model config already knows about:

* ``<unk>`` — byte-level BPE (used here) never actually needs this for
  encoding, since every byte has a token; it exists as a defensive decode
  target only.
* ``<|im_start|>`` / ``<|im_end|>`` — turn delimiters for instruction
  tuning (Phase 8), ChatML-style so existing tooling/expectations transfer.
* ``<|system|>`` / ``<|user|>`` / ``<|assistant|>`` — role markers used
  after ``<|im_start|>``.
* ``<|tool_call|>`` / ``<|tool_result|>`` / ``<|tool_error|>`` — structural
  markers for Phase 9 tool-calling data, wrapping the JSON payload
  (``{"type": "tool_call", "tool": ..., "arguments": {}}``) so the model
  can learn to emit/consume it as a distinct span rather than plain text
  indistinguishable from prose.
"""

from __future__ import annotations

PAD_TOKEN = "<pad>"
BOS_TOKEN = "<bos>"
EOS_TOKEN = "<eos>"
UNK_TOKEN = "<unk>"
IM_START_TOKEN = "<|im_start|>"
IM_END_TOKEN = "<|im_end|>"
SYSTEM_TOKEN = "<|system|>"
USER_TOKEN = "<|user|>"
ASSISTANT_TOKEN = "<|assistant|>"
TOOL_CALL_TOKEN = "<|tool_call|>"
TOOL_RESULT_TOKEN = "<|tool_result|>"
TOOL_ERROR_TOKEN = "<|tool_error|>"

# Order defines id: SPECIAL_TOKENS[i] has token id i. Append-only — never
# reorder or remove an entry once a tokenizer has been trained against it,
# or every existing checkpoint's token ids silently become wrong.
SPECIAL_TOKENS: tuple[str, ...] = (
    PAD_TOKEN,  # 0
    BOS_TOKEN,  # 1
    EOS_TOKEN,  # 2
    UNK_TOKEN,  # 3
    IM_START_TOKEN,  # 4
    IM_END_TOKEN,  # 5
    SYSTEM_TOKEN,  # 6
    USER_TOKEN,  # 7
    ASSISTANT_TOKEN,  # 8
    TOOL_CALL_TOKEN,  # 9
    TOOL_RESULT_TOKEN,  # 10
    TOOL_ERROR_TOKEN,  # 11
)

PAD_TOKEN_ID = SPECIAL_TOKENS.index(PAD_TOKEN)
BOS_TOKEN_ID = SPECIAL_TOKENS.index(BOS_TOKEN)
EOS_TOKEN_ID = SPECIAL_TOKENS.index(EOS_TOKEN)
UNK_TOKEN_ID = SPECIAL_TOKENS.index(UNK_TOKEN)
IM_START_TOKEN_ID = SPECIAL_TOKENS.index(IM_START_TOKEN)
IM_END_TOKEN_ID = SPECIAL_TOKENS.index(IM_END_TOKEN)
SYSTEM_TOKEN_ID = SPECIAL_TOKENS.index(SYSTEM_TOKEN)
USER_TOKEN_ID = SPECIAL_TOKENS.index(USER_TOKEN)
ASSISTANT_TOKEN_ID = SPECIAL_TOKENS.index(ASSISTANT_TOKEN)
TOOL_CALL_TOKEN_ID = SPECIAL_TOKENS.index(TOOL_CALL_TOKEN)
TOOL_RESULT_TOKEN_ID = SPECIAL_TOKENS.index(TOOL_RESULT_TOKEN)
TOOL_ERROR_TOKEN_ID = SPECIAL_TOKENS.index(TOOL_ERROR_TOKEN)
