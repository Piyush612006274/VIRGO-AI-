"""Production inference boundary for trained Virgo SLM artifacts.

The runtime deliberately knows nothing about the desktop UI or Virgo's tool
permissions. It owns only model/tokenizer loading and safe token generation.
The application integrates it through ``VirgoSLMProvider`` on the other side
of the provider contract.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event, RLock
from typing import TYPE_CHECKING, Any

from virgo_slm.model.config import VirgoSLMConfig

if TYPE_CHECKING:
    import torch
    from virgo_slm.model import VirgoSLMForCausalLM

ARTIFACT_FORMAT_VERSION = "1.0"
MODEL_CONFIG_FILE = "model_config.json"
MODEL_WEIGHTS_FILE = "model.pt"
ARTIFACT_MANIFEST_FILE = "artifact.json"
TOKENIZER_DIR_NAME = "tokenizer"


class ArtifactError(RuntimeError):
    """Raised when a model artifact is missing, malformed or incompatible."""


@dataclass(frozen=True, slots=True)
class GenerationConfig:
    temperature: float = 0.7
    top_k: int = 50
    top_p: float = 0.95
    repetition_penalty: float = 1.05
    max_new_tokens: int = 256
    min_new_tokens: int = 0

    def __post_init__(self) -> None:
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be in [0, 2]")
        if self.top_k < 0:
            raise ValueError("top_k must be >= 0")
        if not 0.0 < self.top_p <= 1.0:
            raise ValueError("top_p must be in (0, 1]")
        if self.repetition_penalty <= 0.0:
            raise ValueError("repetition_penalty must be positive")
        if self.max_new_tokens < 1:
            raise ValueError("max_new_tokens must be >= 1")
        if self.min_new_tokens < 0 or self.min_new_tokens > self.max_new_tokens:
            raise ValueError("min_new_tokens must be within max_new_tokens")


@dataclass(frozen=True, slots=True)
class ArtifactMetadata:
    format_version: str
    model_name: str
    model_version: str
    model_config_sha256: str
    weights_sha256: str
    tokenizer_sha256: str
    source_checkpoint: str | None = None
    created_at_unix: float = 0.0
    quantization: str | None = None

    def __post_init__(self) -> None:
        if self.created_at_unix == 0.0:
            object.__setattr__(self, "created_at_unix", time.time())


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    root: Path
    metadata: ArtifactMetadata
    model_config: VirgoSLMConfig
    tokenizer_dir: Path
    weights_path: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tokenizer_hash(tokenizer_dir: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(p for p in tokenizer_dir.rglob("*") if p.is_file())
    if not files:
        raise ArtifactError("Tokenizer artifact directory is empty")
    for path in files:
        digest.update(str(path.relative_to(tokenizer_dir)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def save_artifact(
    output_dir: str | Path,
    *,
    model: VirgoSLMForCausalLM,
    tokenizer_dir: str | Path,
    source_checkpoint: str | Path | None = None,
    overwrite: bool = False,
) -> ModelArtifact:
    """Export a trained PyTorch model + tokenizer into a portable local artifact."""
    import torch
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()) and not overwrite:
        raise ArtifactError(f"Artifact directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    config_path = output / MODEL_CONFIG_FILE
    weights_path = output / MODEL_WEIGHTS_FILE
    tokenizer_out = output / TOKENIZER_DIR_NAME
    tokenizer_source = Path(tokenizer_dir)
    if not tokenizer_source.is_dir():
        raise ArtifactError(f"Tokenizer directory does not exist: {tokenizer_source}")

    config_path.write_text(
        json.dumps(asdict(model.config), indent=2, sort_keys=True), encoding="utf-8"
    )
    torch.save(model.state_dict(), weights_path)
    if tokenizer_out.exists():
        shutil.rmtree(tokenizer_out)
    shutil.copytree(tokenizer_source, tokenizer_out)

    metadata = ArtifactMetadata(
        format_version=ARTIFACT_FORMAT_VERSION,
        model_name=model.config.name,
        model_version=model.config.version,
        model_config_sha256=_sha256(config_path),
        weights_sha256=_sha256(weights_path),
        tokenizer_sha256=_tokenizer_hash(tokenizer_out),
        source_checkpoint=(
            None if source_checkpoint is None else str(source_checkpoint)
        ),
        quantization=None,
    )
    (output / ARTIFACT_MANIFEST_FILE).write_text(
        json.dumps(asdict(metadata), indent=2, sort_keys=True), encoding="utf-8"
    )
    return load_artifact(output)


def load_artifact(path: str | Path) -> ModelArtifact:
    """Validate and load artifact metadata; tensor loading remains lazy."""
    root = Path(path)
    manifest_path = root / ARTIFACT_MANIFEST_FILE
    config_path = root / MODEL_CONFIG_FILE
    weights_path = root / MODEL_WEIGHTS_FILE
    tokenizer_dir = root / TOKENIZER_DIR_NAME
    for required in (manifest_path, config_path, weights_path, tokenizer_dir):
        if not required.exists():
            raise ArtifactError(f"Missing artifact component: {required}")

    try:
        manifest = ArtifactMetadata(**json.loads(manifest_path.read_text("utf-8")))
        config_dict = json.loads(config_path.read_text("utf-8"))
        model_config = VirgoSLMConfig(**config_dict)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise ArtifactError(f"Invalid model artifact metadata: {root}") from error

    if manifest.format_version != ARTIFACT_FORMAT_VERSION:
        raise ArtifactError(
            "Unsupported artifact format "
            f"{manifest.format_version!r}; expected {ARTIFACT_FORMAT_VERSION!r}"
        )
    if manifest.model_config_sha256 != _sha256(config_path):
        raise ArtifactError("Model config hash does not match artifact manifest")
    if manifest.weights_sha256 != _sha256(weights_path):
        raise ArtifactError("Model weights hash does not match artifact manifest")
    if manifest.tokenizer_sha256 != _tokenizer_hash(tokenizer_dir):
        raise ArtifactError("Tokenizer hash does not match artifact manifest")
    return ModelArtifact(root, manifest, model_config, tokenizer_dir, weights_path)


class SLMRuntime:
    """Thread-safe, lazy-loading local SLM runtime with bounded generation."""

    def __init__(
        self,
        artifact: ModelArtifact,
        *,
        device: str | object = "auto",
        dtype: object | None = None,
        tokenizer: Any | None = None,
        model: Any | None = None,
    ) -> None:
        self.artifact = artifact
        self.device = self._resolve_device(device)
        if (
            self.artifact.metadata.quantization is not None
            and self.device.type != "cpu"
        ):
            raise ArtifactError("Quantized Virgo SLM artifacts require CPU inference")
        import torch

        self.dtype = (
            dtype
            or (torch.float16 if self.device.type == "cuda" else torch.float32)
        )
        self._tokenizer = tokenizer
        self._model = model
        self._lock = RLock()

        if self._model is not None:
            self._model.to(device=self.device, dtype=self.dtype)
            self._model.eval()

    @staticmethod
    def _resolve_device(device: str | object) -> Any:
        import torch
        if isinstance(device, torch.device):
            return device
        if device == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if device not in {"cpu", "cuda"}:
            raise ValueError(f"Unsupported inference device: {device!r}")
        if device == "cuda" and not torch.cuda.is_available():
            raise ArtifactError("CUDA inference was requested but CUDA is unavailable")
        return torch.device(device)

    @property
    def model(self) -> Any:
        with self._lock:
            if self._model is None:
                import torch
                from virgo_slm.model import VirgoSLMForCausalLM
                model = VirgoSLMForCausalLM(self.artifact.model_config)
                if self.artifact.metadata.quantization is not None:
                    model = torch.ao.quantization.quantize_dynamic(
                        model, {torch.nn.Linear}, dtype=torch.qint8
                    )
                try:
                    state = torch.load(
                        self.artifact.weights_path,
                        map_location="cpu",
                        weights_only=True,
                    )
                except TypeError:
                    state = torch.load(self.artifact.weights_path, map_location="cpu")
                if not isinstance(state, dict):
                    raise ArtifactError("Model weights must be a state_dict mapping")
                model.load_state_dict(state, strict=True)
                model.to(device=self.device, dtype=self.dtype)
                model.eval()
                self._model = model
            return self._model

    @property
    def tokenizer(self) -> Any:
        with self._lock:
            if self._tokenizer is None:
                try:
                    from virgo_slm.tokenizer import VirgoTokenizer
                except ImportError as error:
                    raise ArtifactError(
                        "The SLM tokenizer runtime dependency is missing; "
                        "install the 'slm' extra"
                    ) from error
                self._tokenizer = VirgoTokenizer.load(self.artifact.tokenizer_dir)
                if self._tokenizer.vocab_size != self.artifact.model_config.vocab_size:
                    raise ArtifactError(
                        "Tokenizer vocabulary size does not match model vocabulary size"
                    )
            return self._tokenizer

    def health_check(self) -> bool:
        _ = self.model
        _ = self.tokenizer
        return True

    def stream(
        self,
        prompt: str,
        *,
        generation: GenerationConfig | None = None,
        cancellation: Event | None = None,
    ) -> Iterator[str]:
        """Generate text one decoded delta at a time."""
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must not be empty")
        config = generation or GenerationConfig()
        signal = cancellation or Event()
        tokenizer = self.tokenizer
        model = self.model
        import torch

        from virgo_slm.tokenizer.special_tokens import BOS_TOKEN, EOS_TOKEN

        prompt_ids = tokenizer.encode(prompt, add_special_tokens=False)
        bos_id = tokenizer.token_to_id(BOS_TOKEN)
        eos_id = tokenizer.token_to_id(EOS_TOKEN)
        input_ids = list(prompt_ids)
        if bos_id is not None:
            input_ids.insert(0, bos_id)
        if not input_ids:
            raise ValueError("prompt encoded to an empty token sequence")

        max_context = model.config.max_position_embeddings
        if len(input_ids) >= max_context:
            input_ids = input_ids[-(max_context - 1) :]

        generated_ids: list[int] = []
        emitted = ""
        caches = None
        current = torch.tensor([input_ids], device=self.device, dtype=torch.long)
        seen = set(input_ids)

        with torch.inference_mode():
            for step in range(config.max_new_tokens):
                if signal.is_set():
                    return
                output = model(
                    current,
                    kv_caches=caches,
                    use_cache=True,
                )
                caches = output.kv_caches
                logits = output.logits[:, -1, :].float()
                if config.repetition_penalty != 1.0 and seen:
                    indices = torch.tensor(tuple(seen), device=logits.device)
                    values = logits[:, indices]
                    logits[:, indices] = torch.where(
                        values < 0,
                        values * config.repetition_penalty,
                        values / config.repetition_penalty,
                    )
                next_id = _sample_next_token(logits, config)
                token_id = int(next_id.item())
                if (
                    eos_id is not None
                    and token_id == eos_id
                    and step >= config.min_new_tokens
                ):
                    break
                generated_ids.append(token_id)
                seen.add(token_id)
                full_text = tokenizer.decode(generated_ids, skip_special_tokens=True)
                delta = _text_delta(emitted, full_text)
                emitted = full_text
                if delta:
                    yield delta
                current = next_id.view(1, 1)
                if len(input_ids) + len(generated_ids) >= max_context:
                    # The cache has reached the architecture's context bound.
                    break

    def generate(
        self,
        prompt: str,
        *,
        generation: GenerationConfig | None = None,
        cancellation: Event | None = None,
    ) -> str:
        return "".join(
            self.stream(
                prompt, generation=generation, cancellation=cancellation
            )
        )


def _sample_next_token(logits: Any, config: GenerationConfig) -> Any:
    import torch

    if config.temperature <= 1e-6:
        return torch.argmax(logits, dim=-1)
    scores = logits / config.temperature
    if config.top_k:
        top_k = min(config.top_k, scores.size(-1))
        threshold = torch.topk(scores, top_k, dim=-1).values[..., -1, None]
        scores = scores.masked_fill(scores < threshold, float("-inf"))
    if config.top_p < 1.0:
        sorted_scores, sorted_indices = torch.sort(scores, descending=True, dim=-1)
        probabilities = torch.softmax(sorted_scores, dim=-1)
        cumulative = probabilities.cumsum(dim=-1)
        remove = cumulative > config.top_p
        remove[..., 1:] = remove[..., :-1].clone()
        remove[..., 0] = False
        sorted_scores = sorted_scores.masked_fill(remove, float("-inf"))
        scores = torch.full_like(scores, float("-inf"))
        scores.scatter_(dim=-1, index=sorted_indices, src=sorted_scores)
    probabilities = torch.softmax(scores, dim=-1)
    return torch.multinomial(probabilities, num_samples=1).squeeze(-1)


def _text_delta(previous: str, current: str) -> str:
    if current.startswith(previous):
        return current[len(previous) :]
    # Byte-level decoding can occasionally re-segment text; emit the current
    # suffix conservatively instead of dropping generated content.
    common = 0
    for left, right in zip(previous, current, strict=False):
        if left != right:
            break
        common += 1
    return current[common:]
