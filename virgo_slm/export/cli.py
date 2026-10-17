"""CLI for exporting a trained checkpoint and optional CPU quantization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from virgo_slm.configs.presets import PRESETS
from virgo_slm.export.quantize import quantize_dynamic
from virgo_slm.inference.runtime import save_artifact
from virgo_slm.model import VirgoSLMConfig, VirgoSLMForCausalLM
from virgo_slm.training.checkpoint import load_checkpoint


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m virgo_slm.export.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="Export a checkpoint as a portable inference artifact")
    export.add_argument("--checkpoint", required=True)
    export.add_argument("--tokenizer-dir", required=True)
    export.add_argument("--output", required=True)
    export.add_argument("--model-preset", default=None)
    export.add_argument("--overwrite", action="store_true")

    quantize = sub.add_parser("quantize-int8", help="Create a CPU dynamic INT8 artifact")
    quantize.add_argument("--input", required=True)
    quantize.add_argument("--output", required=True)
    return parser


def _cmd_export(args: argparse.Namespace) -> int:
    checkpoint = load_checkpoint(args.checkpoint)
    raw_config = checkpoint["metadata"]["model_config"]
    config = VirgoSLMConfig(**raw_config)
    if args.model_preset is not None:
        preset = PRESETS.get(args.model_preset)
        if preset is None:
            raise ValueError(f"Unknown model preset: {args.model_preset}")
        if preset.name != config.name or preset.vocab_size != config.vocab_size:
            raise ValueError("Checkpoint config does not match the selected preset")
    model = VirgoSLMForCausalLM(config)
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    model.eval()
    artifact = save_artifact(
        args.output,
        model=model,
        tokenizer_dir=args.tokenizer_dir,
        source_checkpoint=args.checkpoint,
        overwrite=args.overwrite,
    )
    print(json.dumps({"output": str(artifact.root), "model": artifact.metadata.model_name}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "export":
        return _cmd_export(args)
    if args.command == "quantize-int8":
        quantize_dynamic(args.input, args.output)
        print(json.dumps({"output": str(Path(args.output).resolve()), "quantization": "dynamic-int8"}, indent=2))
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
