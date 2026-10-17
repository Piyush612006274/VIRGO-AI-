"""Optional dynamic INT8 quantization for CPU inference."""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict
from pathlib import Path

import torch
from torch import nn

from virgo_slm.inference.runtime import (
    ARTIFACT_FORMAT_VERSION,
    ARTIFACT_MANIFEST_FILE,
    MODEL_CONFIG_FILE,
    MODEL_WEIGHTS_FILE,
    TOKENIZER_DIR_NAME,
    _sha256,
    _tokenizer_hash,
    load_artifact,
)
from virgo_slm.model import VirgoSLMForCausalLM


def quantize_dynamic(input_artifact: str | Path, output_artifact: str | Path) -> Path:
    """Create a CPU dynamic-INT8 artifact without changing the source."""
    source = load_artifact(input_artifact)
    model = VirgoSLMForCausalLM(source.model_config)
    state = torch.load(
        source.weights_path,
        map_location="cpu",
        weights_only=True,
    )
    model.load_state_dict(state, strict=True)
    model.eval()
    quantized = torch.ao.quantization.quantize_dynamic(
        model, {nn.Linear}, dtype=torch.qint8
    )

    target = Path(output_artifact)
    target.mkdir(parents=True, exist_ok=True)
    for name in (
        ARTIFACT_MANIFEST_FILE,
        MODEL_CONFIG_FILE,
        MODEL_WEIGHTS_FILE,
    ):
        (target / name).unlink(missing_ok=True)
    target_tokenizer = target / TOKENIZER_DIR_NAME
    if target_tokenizer.exists():
        shutil.rmtree(target_tokenizer)

    config_path = target / MODEL_CONFIG_FILE
    weights_path = target / MODEL_WEIGHTS_FILE
    config_path.write_text(
        json.dumps(asdict(source.model_config), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    torch.save(quantized.state_dict(), weights_path)
    shutil.copytree(source.tokenizer_dir, target_tokenizer)
    manifest = {
        "format_version": ARTIFACT_FORMAT_VERSION,
        "model_name": source.metadata.model_name,
        "model_version": source.metadata.model_version,
        "model_config_sha256": _sha256(config_path),
        "weights_sha256": _sha256(weights_path),
        "tokenizer_sha256": _tokenizer_hash(target_tokenizer),
        "source_checkpoint": source.root.as_posix(),
        "created_at_unix": time.time(),
        "quantization": "dynamic-int8",
    }
    (target / ARTIFACT_MANIFEST_FILE).write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target
