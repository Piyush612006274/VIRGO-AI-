"""Build a Virgo SLM student from an approved corpus or an Ollama teacher.

This script never treats Ollama as the Virgo model. Ollama/Qwen is only an optional
teacher used to generate additional training examples. The resulting student is
trained and exported as a native Virgo artifact.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from virgo_slm.configs.presets import VIRGO_SLM_MAIN
from virgo_slm.model import VirgoSLMForCausalLM, count_parameters


def inspect_target() -> None:
    model = VirgoSLMForCausalLM(VIRGO_SLM_MAIN)
    params = count_parameters(model)
    fp32_gb = params * 4 / (1024**3)
    fp16_gb = params * 2 / (1024**3)
    print(json.dumps({
        "model": VIRGO_SLM_MAIN.name,
        "parameters": params,
        "fp32_weight_gib": round(fp32_gb, 3),
        "fp16_weight_gib": round(fp16_gb, 3),
        "two_gib_budget_ok": fp32_gb < 2.0,
        "trained": False,
    }, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    if args.inspect:
        inspect_target()
        return 0
    parser.error("Use the existing dataset/train/export pipeline after an approved corpus is prepared")
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
