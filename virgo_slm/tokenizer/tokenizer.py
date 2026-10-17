"""Virgo tokenizer: byte-level BPE, trained via HuggingFace ``tokenizers``.

Byte-level BPE (as used by GPT-2/GPT-4/LLaMA-family models) was chosen over
a Unicode-codepoint or SentencePiece-unigram tokenizer for one concrete
reason relevant to this project's language list: it operates on raw UTF-8
bytes, so Hindi (Devanagari), Russian (Cyrillic), Chinese/Japanese/Korean
(CJK, distinct scripts each), Arabic (RTL), Hinglish (Latin-script
code-mixing), and source code/JSON/URLs/file paths are *all* representable
without an out-of-vocabulary/``<unk>`` fallback — every byte has a token,
so encode→decode is lossless by construction for any input, which is
verified directly in ``virgo_slm/tests/test_tokenizer.py`` rather than
assumed.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from pathlib import Path

from tokenizers import Tokenizer, decoders, pre_tokenizers, processors
from tokenizers.models import BPE
from tokenizers.trainers import BpeTrainer

from virgo_slm.tokenizer.config import TokenizerConfig
from virgo_slm.tokenizer.special_tokens import BOS_TOKEN, EOS_TOKEN

TOKENIZER_FILE_NAME = "tokenizer.json"
CONFIG_FILE_NAME = "tokenizer_config.json"


class VirgoTokenizer:
    """Thin, explicit wrapper around a trained byte-level BPE tokenizer."""

    def __init__(self, tokenizer: Tokenizer, config: TokenizerConfig) -> None:
        self._tokenizer = tokenizer
        self.config = config

    # -- construction -----------------------------------------------------

    @classmethod
    def train_from_files(
        cls,
        files: Sequence[str],
        *,
        config: TokenizerConfig,
    ) -> VirgoTokenizer:
        """Train a fresh tokenizer from a list of plain-text file paths.

        Deterministic given the same files and config (the underlying BPE
        trainer has no random seed dependency — merges are chosen by
        frequency, with ties broken by insertion order).
        """
        tokenizer = Tokenizer(BPE(unk_token=None, byte_fallback=True))
        tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
        tokenizer.decoder = decoders.ByteLevel()

        trainer = BpeTrainer(  # type: ignore[no-untyped-call]  # tokenizers has no stubs
            vocab_size=config.vocab_size,
            min_frequency=config.min_frequency,
            special_tokens=list(config.special_tokens),
            initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
        )
        tokenizer.train(list(files), trainer=trainer)

        bos_id = tokenizer.token_to_id(BOS_TOKEN)
        eos_id = tokenizer.token_to_id(EOS_TOKEN)
        tokenizer.post_processor = processors.TemplateProcessing(
            single=f"{BOS_TOKEN} $A {EOS_TOKEN}",
            pair=f"{BOS_TOKEN} $A {EOS_TOKEN} {BOS_TOKEN} $B {EOS_TOKEN}",
            special_tokens=[(BOS_TOKEN, bos_id), (EOS_TOKEN, eos_id)],
        )

        return cls(tokenizer, config)

    @classmethod
    def load(cls, directory: str | Path) -> VirgoTokenizer:
        directory = Path(directory)
        tokenizer = Tokenizer.from_file(str(directory / TOKENIZER_FILE_NAME))
        config_dict = json.loads((directory / CONFIG_FILE_NAME).read_text("utf-8"))
        config_dict["special_tokens"] = tuple(config_dict["special_tokens"])
        config = TokenizerConfig(**config_dict)
        return cls(tokenizer, config)

    def save(self, directory: str | Path) -> None:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self._tokenizer.save(str(directory / TOKENIZER_FILE_NAME))
        (directory / CONFIG_FILE_NAME).write_text(
            json.dumps(asdict(self.config), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # -- encode/decode ------------------------------------------------------

    def encode(self, text: str, *, add_special_tokens: bool = True) -> list[int]:
        return self._tokenizer.encode(
            text, add_special_tokens=add_special_tokens
        ).ids

    def decode(self, ids: Sequence[int], *, skip_special_tokens: bool = True) -> str:
        return self._tokenizer.decode(list(ids), skip_special_tokens=skip_special_tokens)

    def encode_batch(
        self, texts: Iterable[str], *, add_special_tokens: bool = True
    ) -> list[list[int]]:
        encodings = self._tokenizer.encode_batch(
            list(texts), add_special_tokens=add_special_tokens
        )
        return [e.ids for e in encodings]

    def encode_batch_padded(
        self, texts: Iterable[str], *, add_special_tokens: bool = True
    ) -> tuple[list[list[int]], list[list[int]]]:
        """Batch-encode with right-padding to the longest sequence.

        Returns ``(input_ids, attention_mask)`` — the padding convention
        (mask=1 for real tokens, 0 for pad) matches
        ``VirgoSLMForCausalLM.forward``'s ``attention_mask`` argument
        directly.
        """
        pad_id = self.token_to_id(self.config.special_tokens[0])
        assert pad_id is not None  # pad token is always special_tokens[0]
        self._tokenizer.enable_padding(pad_id=pad_id, pad_token=self.config.special_tokens[0])
        try:
            encodings = self._tokenizer.encode_batch(
                list(texts), add_special_tokens=add_special_tokens
            )
        finally:
            self._tokenizer.no_padding()
        input_ids = [e.ids for e in encodings]
        attention_mask = [e.attention_mask for e in encodings]
        return input_ids, attention_mask


    def decode_batch(
        self, ids_batch: Iterable[Sequence[int]], *, skip_special_tokens: bool = True
    ) -> list[str]:
        return self._tokenizer.decode_batch(
            [list(ids) for ids in ids_batch], skip_special_tokens=skip_special_tokens
        )

    # -- introspection ------------------------------------------------------

    @property
    def vocab_size(self) -> int:
        return self._tokenizer.get_vocab_size()

    def token_to_id(self, token: str) -> int | None:
        return self._tokenizer.token_to_id(token)

    def id_to_token(self, token_id: int) -> str | None:
        return self._tokenizer.id_to_token(token_id)
