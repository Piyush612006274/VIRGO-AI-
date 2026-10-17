"""Configuration for the Virgo SLM decoder-only Transformer.

Every architectural knob called for by Phase 1 of the Virgo SLM task is
represented here: vocabulary size, hidden dimension, layer count, attention
head count (with optional grouped-query attention via ``num_kv_heads``),
feed-forward dimension, max sequence length, positional-encoding choice,
normalization, activation, dropout, weight tying, initialization and
precision.

The config is deliberately independent of any specific parameter budget so
the same code scales from the initial ~100M-150M target up to 300M, 500M,
1B+ without redesign — only the numbers in a preset change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PositionalEncoding = Literal["rope"]
NormType = Literal["rmsnorm", "layernorm"]
Activation = Literal["swiglu", "gelu"]
Precision = Literal["fp32", "fp16", "bf16"]


@dataclass(frozen=True, slots=True)
class VirgoSLMConfig:
    """Frozen, validated configuration for one Virgo SLM architecture.

    Frozen so a config that has produced a checkpoint can never be mutated
    out from under that checkpoint; construct a new config (e.g. via
    ``dataclasses.replace``) to change anything.
    """

    vocab_size: int
    hidden_size: int
    num_layers: int
    num_heads: int
    num_kv_heads: int | None = None  # None => num_kv_heads = num_heads (MHA)
    ffn_multiple_of: int = 256
    ffn_hidden_multiplier: float = 8.0 / 3.0  # SwiGLU convention (~ 8/3 * hidden)
    max_position_embeddings: int = 2048
    positional_encoding: PositionalEncoding = "rope"
    rope_theta: float = 10000.0
    norm_type: NormType = "rmsnorm"
    norm_eps: float = 1e-5
    activation: Activation = "swiglu"
    dropout: float = 0.0
    attention_dropout: float = 0.0
    tie_word_embeddings: bool = True
    initializer_range: float = 0.02
    precision: Precision = "fp32"
    pad_token_id: int = 0
    bos_token_id: int = 1
    eos_token_id: int = 2

    # Free-form identifiers, not used by the model itself but required for
    # reproducibility (Phase 5: versioned configuration) and checkpoint
    # provenance.
    name: str = "virgo-slm"
    version: str = "0.1.0"

    def __post_init__(self) -> None:
        errors: list[str] = []

        def require(condition: bool, message: str) -> None:
            if not condition:
                errors.append(message)

        require(self.vocab_size > 0, "vocab_size must be positive")
        require(self.hidden_size > 0, "hidden_size must be positive")
        require(self.num_layers > 0, "num_layers must be positive")
        require(self.num_heads > 0, "num_heads must be positive")
        require(
            self.hidden_size % self.num_heads == 0,
            "hidden_size must be divisible by num_heads",
        )
        kv_heads = self.effective_num_kv_heads
        require(kv_heads > 0, "num_kv_heads must be positive")
        require(
            self.num_heads % kv_heads == 0,
            "num_heads must be a multiple of num_kv_heads (grouped-query "
            "attention requires an integer group size)",
        )
        require(self.ffn_multiple_of > 0, "ffn_multiple_of must be positive")
        require(
            self.ffn_hidden_multiplier > 0, "ffn_hidden_multiplier must be positive"
        )
        require(
            self.max_position_embeddings > 0,
            "max_position_embeddings must be positive",
        )
        require(self.norm_eps > 0, "norm_eps must be positive")
        require(0.0 <= self.dropout < 1.0, "dropout must be in [0, 1)")
        require(
            0.0 <= self.attention_dropout < 1.0,
            "attention_dropout must be in [0, 1)",
        )
        require(
            self.initializer_range > 0, "initializer_range must be positive"
        )
        require(
            len({self.pad_token_id, self.bos_token_id, self.eos_token_id})
            == 3,
            "pad_token_id, bos_token_id and eos_token_id must be distinct",
        )

        if errors:
            raise ValueError(
                "Invalid VirgoSLMConfig: " + "; ".join(errors)
            )

    @property
    def head_dim(self) -> int:
        return self.hidden_size // self.num_heads

    @property
    def effective_num_kv_heads(self) -> int:
        return self.num_kv_heads if self.num_kv_heads is not None else self.num_heads

    @property
    def ffn_hidden_size(self) -> int:
        """SwiGLU-style FFN width, rounded up to a hardware-friendly multiple.

        Follows the standard convention popularized by LLaMA: the "raw"
        SwiGLU hidden size is ``2/3`` of the naive ``4 * hidden_size`` (to
        keep parameter count comparable to a plain GELU MLP despite SwiGLU's
        extra projection), then rounded up to ``ffn_multiple_of``.
        """
        if self.activation == "gelu":
            return 4 * self.hidden_size
        raw = int(self.ffn_hidden_multiplier * self.hidden_size)
        multiple = self.ffn_multiple_of
        return multiple * ((raw + multiple - 1) // multiple)


def estimate_parameter_count(config: VirgoSLMConfig) -> int:
    """Analytic (pre-instantiation) parameter count for ``config``.

    This is the estimator used by :func:`search_config_for_target_params`
    to pick hyperparameters *before* paying to build a real
    ``nn.Module``. It must be independently verified against the actual
    instantiated-model count (:func:`virgo_slm.model.architecture.
    count_parameters`) — that cross-check lives in
    ``virgo_slm/tests/test_model_architecture.py``. Treat this function as
    an estimate for planning, and the instantiated count as the exact,
    authoritative figure for any reported number.
    """
    h = config.hidden_size
    v = config.vocab_size
    L = config.num_layers
    kv = config.effective_num_kv_heads
    head_dim = config.head_dim
    ffn = config.ffn_hidden_size

    embedding_params = v * h

    # Attention: Q proj (h -> h), K/V proj (h -> kv*head_dim each), O proj (h -> h)
    attn_params = (
        h * h  # q_proj
        + 2 * (h * kv * head_dim)  # k_proj + v_proj
        + h * h  # o_proj
    )

    # SwiGLU MLP: gate_proj (h->ffn), up_proj (h->ffn), down_proj (ffn->h).
    # Plain GELU MLP: just up + down.
    mlp_params = 3 * h * ffn if config.activation == "swiglu" else 2 * h * ffn

    # Norms: RMSNorm/LayerNorm have `h` (RMSNorm) or `2*h` (LayerNorm, incl.
    # bias) parameters per instance; each block has 2 norms.
    norm_params_per_instance = h if config.norm_type == "rmsnorm" else 2 * h
    norms_per_layer = 2 * norm_params_per_instance

    per_layer = attn_params + mlp_params + norms_per_layer
    final_norm = norm_params_per_instance

    lm_head_params = 0 if config.tie_word_embeddings else v * h

    total = embedding_params + L * per_layer + final_norm + lm_head_params
    return total


def search_config_for_target_params(
    *,
    target_min: int,
    target_max: int,
    vocab_size: int,
    max_position_embeddings: int = 2048,
    num_kv_heads_ratio: int = 1,
    name: str = "virgo-slm",
) -> VirgoSLMConfig:
    """Grid-search a config whose estimated parameter count lands in range.

    Searches a small, sane grid of (hidden_size, num_layers, num_heads)
    combinations — all commonly used shapes, not arbitrary values — and
    returns the first (smallest search-order) config whose
    :func:`estimate_parameter_count` falls within
    ``[target_min, target_max]``. Raises ``ValueError`` if nothing in the
    grid fits, rather than silently returning something out of range.
    """
    candidate_hidden_sizes = (384, 448, 512, 576, 640, 704, 768, 832, 896, 960, 1024)
    candidate_layers = range(6, 25)

    for hidden_size in candidate_hidden_sizes:
        for num_heads in (h for h in (4, 6, 8, 12, 16) if hidden_size % h == 0):
            num_kv_heads = max(1, num_heads // num_kv_heads_ratio)
            if num_heads % num_kv_heads != 0:
                continue
            for num_layers in candidate_layers:
                config = VirgoSLMConfig(
                    vocab_size=vocab_size,
                    hidden_size=hidden_size,
                    num_layers=num_layers,
                    num_heads=num_heads,
                    num_kv_heads=num_kv_heads,
                    max_position_embeddings=max_position_embeddings,
                    name=name,
                )
                estimate = estimate_parameter_count(config)
                if target_min <= estimate <= target_max:
                    return config

    raise ValueError(
        f"No config in the search grid estimates within "
        f"[{target_min:,}, {target_max:,}] parameters for vocab_size="
        f"{vocab_size:,}"
    )
