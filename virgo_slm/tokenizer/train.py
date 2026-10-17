"""Train a Virgo tokenizer from a directory of plain-text files.

Usage:
    python -m virgo_slm.tokenizer.train \\
        --corpus-dir virgo_slm/tokenizer/sample_corpus \\
        --vocab-size 2000 \\
        --out-dir virgo_slm/tokenizer/artifacts/smoke

This is the Phase 2 training entry point. It is deliberately corpus-agnostic
— point it at a real, large multilingual+code corpus once Phase 3 (dataset
pipeline) produces one; nothing here is specific to the small sample corpus
checked in for smoke testing.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from virgo_slm.tokenizer.config import TokenizerConfig
from virgo_slm.tokenizer.tokenizer import VirgoTokenizer


def _discover_files(corpus_dir: Path) -> list[Path]:
    files = sorted(p for p in corpus_dir.rglob("*.txt") if p.is_file())
    if not files:
        raise FileNotFoundError(f"No .txt files found under {corpus_dir}")
    return files


def train(
    *,
    corpus_dir: Path,
    out_dir: Path,
    vocab_size: int,
    min_frequency: int = 2,
) -> VirgoTokenizer:
    files = _discover_files(corpus_dir)
    config = TokenizerConfig(vocab_size=vocab_size, min_frequency=min_frequency)

    tokenizer = VirgoTokenizer.train_from_files(
        [str(f) for f in files], config=config
    )

    manifest = {
        "corpus_dir": str(corpus_dir),
        "files": [str(f.relative_to(corpus_dir)) for f in files],
        "num_files": len(files),
        "total_bytes": sum(f.stat().st_size for f in files),
    }
    trained_config = replace(
        tokenizer.config, trained_on=json.dumps(manifest, ensure_ascii=False)
    )
    tokenizer.config = trained_config

    tokenizer.save(out_dir)
    (out_dir / "training_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return tokenizer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--vocab-size", type=int, required=True)
    parser.add_argument("--min-frequency", type=int, default=2)
    args = parser.parse_args(argv)

    tokenizer = train(
        corpus_dir=args.corpus_dir,
        out_dir=args.out_dir,
        vocab_size=args.vocab_size,
        min_frequency=args.min_frequency,
    )
    print(f"Trained tokenizer, vocab_size={tokenizer.vocab_size}, saved to {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
